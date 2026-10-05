import os
# os.environ["CUDA_LAUNCH_BLOCKING"] = "1"          # debug only; ~10x slower — leave off for training
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1,0")           # single GPU — Unsloth single-process, KHÔNG pool VRAM
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"
os.environ["UNSLOTH_RETURN_LOGITS"] = "1,0"           # boolean flag, không phải device list
os.environ["UNSLOTH_IGNORED_TOKENIZER_NAMES"] = "Qwen/Qwen2.5-Coder-7B-Instruct"


# ---- Vô hiệu hoá fix_untrained_tokens ngay tại SOURCE, trước khi bất kỳ import nào
# của unsloth/trl bind tham chiếu tới nó. Preflight đã chứng minh mọi token id đều
# trong vocab, nên hàm auto-fix này là thứ duy nhất gây device-side gather assert. ----
try:
    import unsloth_zoo.tokenizer_utils as _utz
    _utz.fix_untrained_tokens = lambda *a, **k: None
except Exception as e:
    print(f"[patch] source patch skipped: {e}")

import torch
import numpy as np
from datasets import load_dataset, concatenate_datasets

from unsloth import FastLanguageModel
from unsloth.chat_templates import train_on_responses_only
from trl import SFTTrainer, SFTConfig

# ---------------- Paths & config ----------------
# Retrain of the Generator for review R3-2 / R3-1 (training/README.md). Same
# recipe as train_gen_new.py (the served 0-35_e1_v1), changed only where noted:
#   * data: training/data/<VARIANT>_<STAGE>.npy (make_retrain_data.py) - benchmark
#     leak rows removed, and VE_text_156.jsonl is NOT concatenated any more
#   * stage s1 starts from the base model with a fresh LoRA (get_peft_model, the
#     block that was commented out in train_gen_new.py after the first stage);
#     s2/s3 load the previous stage's saved adapter, as the original curriculum did
#   * SMOKE=1 trains 20 steps on 200 rows to check the setup
#   VARIANT=clean|random  STAGE=s1|s2|s3  [INIT=<adapter dir>]  [RETRAIN_DIR=...]
import os as _os
MODEL_NAME      = "Qwen/Qwen2.5-Coder-7B-Instruct"
MAX_SEQ_LENGTH  = 8192

TRAIN_JSONL     = "/home/nntkim/Downloads/TrainDataset/Pyranet_text_only.jsonl"
VARIANT         = _os.environ["VARIANT"]
STAGE           = _os.environ["STAGE"]
SMOKE           = _os.environ.get("SMOKE") == "1"
TRAIN_INDEX_NPY = f"/home/nntkim/GNU_COMBA/training/data/{VARIANT}_{STAGE}.npy"
RETRAIN_DIR     = _os.environ.get("RETRAIN_DIR", "/home/nntkim/Downloads/retrain")
_tag            = f"qwen_generator_{VARIANT}_{STAGE}" + ("_smoke" if SMOKE else "")
OUTPUT_DIR      = f"{RETRAIN_DIR}/outputs_{_tag}"
SAVED_DIR       = f"{RETRAIN_DIR}/adapter_{_tag}"
CHECKPOINT      = _os.environ.get("INIT") or MODEL_NAME   # s1: base model; s2/s3: previous adapter

NUM_EPOCHS = 1
LR         = 2e-5           # LoRA LR (higher than full-FT; 1e-5 is too low for LoRA)
BATCH_SIZE = 2
GRAD_ACCUM = 1              # effective batch = 2 * 2 = 4
LORA_RANK  = 912           # CẢNH BÁO: r=1024 ≈ 2.5B tham số train (~37% của 7B) = gần full-FT
# --------------------------------------------------------------------


def preflight(tokenizer, dataset, vocab_size):
    """State machine: gates training. Scans the FULL dataset (not a sample) and
    DROPS samples whose token id >= vocab_size. SCAN -> CHECK_PAD -> FILTER ->
    READY. Returns the cleaned dataset. (Log đã xác nhận data sạch → DROP = 0.)"""
    state = "SCAN"
    bad_idx, max_id = [], -1
    while state != "READY":
        if state == "SCAN":
            for i, ids in enumerate(dataset["input_ids"]):   # full scan
                m = max(ids)
                if m > max_id:
                    max_id = m
                if m >= vocab_size:
                    bad_idx.append(i)
            state = "CHECK_PAD"
        elif state == "CHECK_PAD":
            assert tokenizer.pad_token_id is not None, "pad_token_id is None"
            state = "FILTER"
        elif state == "FILTER":
            if bad_idx:
                print(f"[preflight] DROP {len(bad_idx)} samples: token id >= "
                      f"{vocab_size} (max id seen {max_id}); bad idx[:5]={bad_idx[:5]}")
                bad = set(bad_idx)
                dataset = dataset.select([i for i in range(len(dataset)) if i not in bad])
            state = "READY"
    print(f"[preflight] READY ({len(dataset)} samples; max id {max_id} vs vocab {vocab_size})")
    return dataset


def kill_fix_untrained_tokens():
    """Belt-and-suspenders: null mọi tham chiếu fix_untrained_tokens đã bind ở các
    module đã import (kể cả unsloth_compiled_cache.UnslothSFTTrainer).
    Quét qua __dict__ (KHÔNG dùng getattr) để tránh kích hoạt lazy __getattr__
    alias của transformers — thứ gây ra hàng trăm dòng cảnh báo image_processing_*."""
    import sys
    noop, n = (lambda *a, **k: None), 0
    for m in list(sys.modules.values()):
        d = getattr(m, "__dict__", None)            # __dict__ là attr thật → không gọi __getattr__
        if d is not None and callable(d.get("fix_untrained_tokens")):
            d["fix_untrained_tokens"] = noop
            n += 1
    print(f"[patch] fix_untrained_tokens neutralized in {n} module(s)")


def main():
    print(f"[INFO] CUDA devices: {torch.cuda.device_count()}")

    # ---------- 1. Load model + LoRA ----------
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name      = CHECKPOINT,
        max_seq_length  = MAX_SEQ_LENGTH,
        dtype           = None,        # auto bf16
        load_in_4bit    = False,        # QLoRA: base 7B ~15GB(bf16) -> ~5GB — đòn bẩy OOM lớn nhất
        # device_map      = "balanced",      # ← dùng GPU0
    )                                  # KHÔNG dùng device_map: Unsloth không train được model bị shard
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if CHECKPOINT == MODEL_NAME:   # first stage: fresh LoRA on the base model
        model = FastLanguageModel.get_peft_model(
            model,
            r                          = LORA_RANK,
            lora_alpha                 = LORA_RANK,    # alpha = r is fine; alpha = 2*r also common
            lora_dropout               = 0,
            bias                       = "none",
            target_modules             = ["q_proj", "k_proj", "v_proj", "o_proj",
                                          "gate_proj", "up_proj", "down_proj"],
            use_gradient_checkpointing = "unsloth",
            random_state               = 3407,
            use_rslora                 = False,
            loftq_config               = None,
        )
    print(f"[INFO] variant={VARIANT} stage={STAGE} init={CHECKPOINT} data={TRAIN_INDEX_NPY} smoke={SMOKE}")

    # ---------- 2. Dataset (lora.py: Pyranet[index] + VE, cột `text`) ----------
    print(f"[INFO] Loading dataset from JSONL")
    ds_main = load_dataset("json", data_files=TRAIN_JSONL, split="train")
    idx = np.load(TRAIN_INDEX_NPY)
    if SMOKE:
        idx = idx[:200]
    dataset = ds_main.select(idx)          # no VE_text_156: VerilogEval stays out of training
    assert "text" in dataset.column_names, "dataset cần cột `text` đã format chat-template"

    # `text` đã format sẵn → không cần formatting_func / apply_chat_template.
    def tokenize_func(examples):
        return tokenizer(
            examples["text"],
            truncation         = True,
            max_length         = MAX_SEQ_LENGTH,
            add_special_tokens = False,   # text đã có control token của chat template
        )

    dataset = dataset.map(
        tokenize_func, batched=True, remove_columns=dataset.column_names
    )
    print(f"[INFO] Samples: {len(dataset)}")

    # ---------- preflight state machine ----------
    embed_rows = model.get_input_embeddings().weight.shape[0]   # rows gather indexes into
    dataset = preflight(tokenizer, dataset, embed_rows)

    # ---------- 3. Trainer ----------
    probe = [{"role": "user", "content": "§"}]
    base  = tokenizer.apply_chat_template(probe, tokenize=False, add_generation_prompt=False)
    full  = tokenizer.apply_chat_template(probe, tokenize=False, add_generation_prompt=True)
    response_part = full[len(base):]
    print(f"[INFO] response_part={response_part!r}")

    kill_fix_untrained_tokens()   # ngay trước khi dựng trainer (lúc này compiled cache đã import)

    trainer = SFTTrainer(
        model            = model,
        processing_class = tokenizer,
        train_dataset    = dataset,
        args = SFTConfig(
            max_seq_length              = MAX_SEQ_LENGTH,
            per_device_train_batch_size = BATCH_SIZE,
            gradient_accumulation_steps = GRAD_ACCUM,
            max_grad_norm               = 1.0,
            warmup_steps                = 100,
            num_train_epochs            = NUM_EPOCHS,
            max_steps                   = 20 if SMOKE else -1,
            learning_rate               = LR,
            logging_steps               = 1,
            save_strategy               = "steps",
            save_steps                  = 500,
            save_total_limit            = 2,
            optim                       = "adamw_8bit",
            weight_decay                = 0.001,
            lr_scheduler_type           = "linear",
            seed                        = 3407,
            output_dir                  = OUTPUT_DIR,
            packing                     = False,
            report_to                   = "none",
        ),
    )

    # Mask loss on prompt — train only on the response.
    trainer = train_on_responses_only(
        trainer,
        instruction_part = base[:-1],
        response_part    = response_part,
    )

    # ---------- 4. Train ----------
    trainer.train()

    # ---------- 5. Save (LoRA adapters) ----------
    print("[INFO] Saving LoRA adapters...")
    model.save_pretrained(SAVED_DIR)
    tokenizer.save_pretrained(SAVED_DIR)
    print(f"[INFO] Saved to: {SAVED_DIR}")
    


if __name__ == "__main__":
    main()
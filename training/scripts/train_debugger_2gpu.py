"""
Train debugger trên 2 GPU bằng MODEL-PARALLEL (device_map="auto") — 1 process,
KHÔNG DDP, KHÔNG torchrun. Mục tiêu: fit rank/model lớn hơn 1 GPU.

Vì sao KHÔNG dùng Unsloth: Unsloth không train được model bị shard (đó là NaN cũ).
Script này dùng HF Transformers thuần + PEFT, model chia layer lên GPU 0 + 1, nên
optimizer/LoRA của mỗi nửa layer nằm trên GPU tương ứng -> fit được rank to hơn.

Masking: Qwen template KHÔNG hỗ trợ assistant_only_loss (mask = 0 token), nên ta
TỰ mask thủ công: chỉ tính loss trên phần assistant (sau "<|im_start|>assistant\n").

Chạy:
  SMOKE=1 python train_debugger_2gpu.py     # test nhanh 3 step / 50 mẫu, kiểm tra shard + loss hữu hạn
  python train_debugger_2gpu.py             # train thật (1 process, 2 GPU model-parallel)
"""

import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0,1")     # cả 2 GPU
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import torch
from datasets import load_from_disk
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    Trainer, TrainingArguments, DataCollatorForSeq2Seq,
)
from transformers.trainer_utils import get_last_checkpoint
from peft import LoraConfig, get_peft_model

# ---------------- config ----------------
MODEL_NAME     = "Qwen/Qwen2.5-Coder-7B-Instruct"
MAX_LEN        = 8192
RAW_DATASET    = "/home/nntkim/Downloads/QwenDebugVeri_clean"
OUTPUT_DIR     = "outputs_qwen_debugger_2gpu_e1_v2"
SAVED_DIR      = "adapter_qwen_debugger_2gpu_e1_v2"

NUM_EPOCHS = 1
LR         = 2e-5
BATCH_SIZE = 1             # micro-batch / forward (logits vocab=152064 nằm trên 1 GPU -> giữ nhỏ)
GRAD_ACCUM = 4             # effective batch = 1 * 4 = 4
LORA_RANK  = 912          # model chia 2 GPU -> có thể nâng nếu muốn
# Dồn tải lên GPU 0 (chính), GPU 1 chỉ nhận layer tràn.
# device_map xếp WEIGHT theo max_memory: GPU 0 nhận tối đa GPU0_CAP rồi mới sang GPU 1.
# Vì grad/optimizer/activation lúc train nằm THEO layer -> GPU 0 giữ nhiều layer hơn = gánh chính.
# Base 7B bf16 ~15GB: cap ~11GiB => ~72% layer lên GPU 0. OOM GPU0 thì HẠ số này.
GPU0_CAP   = "44GiB"
GPU1_CAP   = "11GiB"
RESP_MARK  = "<|im_start|>assistant\n"
TEST_SIZE  = 0.05          # 5% held-out (không train vào)
EVAL_SUBSET = 500          # eval định kỳ trên subset này cho nhanh (full 5% để eval cuối)
SMOKE      = bool(os.environ.get("SMOKE"))
# ----------------------------------------


def find_sub(seq, sub):
    """Vị trí xuất hiện CUỐI của subsequence `sub` trong `seq` (hoặc -1)."""
    n, m = len(seq), len(sub)
    for i in range(n - m, -1, -1):
        if seq[i:i + m] == sub:
            return i
    return -1


def main():
    print(f"[INFO] visible GPUs: {torch.cuda.device_count()} | SMOKE={SMOKE}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    resp_ids = tokenizer.encode(RESP_MARK, add_special_tokens=False)

    # ---------- model: chia layer lên 2 GPU ----------
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.bfloat16,
        device_map="auto",                       # <-- model-parallel (pipeline) trên GPU 0+1
        max_memory={0: GPU0_CAP, 1: GPU1_CAP},   # GPU 0 gánh chính, GPU 1 chỉ nhận layer tràn
        attn_implementation="flash_attention_2", # FA2 đã có (2.8.3)
    )
    print("[INFO] device_map:", model.hf_device_map)   # in layer nằm GPU nào
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()

    lora = LoraConfig(
        r=LORA_RANK, lora_alpha=LORA_RANK, lora_dropout=0.0, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)
    # QUAN TRỌNG: báo Trainer đây là model-parallel -> KHÔNG bọc nn.DataParallel/DDP
    model.is_parallelizable = True
    model.model_parallel = True
    model.print_trainable_parameters()

    # ---------- dataset: tách 95/5, tokenize + mask thủ công (chỉ học phần assistant) ----------
    ds = load_from_disk(RAW_DATASET)
    split = ds.train_test_split(test_size=TEST_SIZE, seed=3407)
    train_ds, test_ds = split["train"], split["test"]
    print(f"[INFO] train={len(train_ds)} | test(held-out)={len(test_ds)}")
    eval_ds = test_ds.select(range(min(EVAL_SUBSET, len(test_ds))))  # eval định kỳ trên subset cho nhanh
    if SMOKE:
        train_ds = train_ds.select(range(50))
        eval_ds  = eval_ds.select(range(min(20, len(eval_ds))))

    def encode(ex):
        text = tokenizer.apply_chat_template(
            ex["messages"], tokenize=False, add_generation_prompt=False)
        ids = tokenizer(text, truncation=True, max_length=MAX_LEN,
                        add_special_tokens=False)["input_ids"]
        labels = list(ids)
        cut = find_sub(ids, resp_ids)
        if cut == -1:                       # không tìm thấy mốc assistant (bị cắt) -> bỏ qua mẫu
            labels = [-100] * len(ids)
        else:
            end = cut + len(resp_ids)
            labels[:end] = [-100] * end     # mask system+user+mốc, chỉ giữ loss phần trả lời
        return {"input_ids": ids, "labels": labels,
                "attention_mask": [1] * len(ids)}

    def prep(d):
        return d.map(encode, remove_columns=d.column_names,
                     num_proc=(1 if SMOKE else 8), desc="tokenize+mask")

    train_ds = prep(train_ds)
    eval_ds  = prep(eval_ds)
    print(f"[INFO] train samples={len(train_ds)} | eval samples={len(eval_ds)}")

    collator = DataCollatorForSeq2Seq(
        tokenizer, padding=True, label_pad_token_id=-100, return_tensors="pt")

    args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        num_train_epochs=NUM_EPOCHS,
        max_steps=(3 if SMOKE else -1),
        learning_rate=LR,
        bf16=True,
        max_grad_norm=1.0,
        warmup_ratio=0.03,
        logging_steps=1,
        eval_strategy="steps",
        eval_steps=(2 if SMOKE else 2000),
        prediction_loss_only=True,     # eval chỉ tính loss, KHÔNG gom logits (vocab 152064 -> nổ VRAM)
        save_strategy=("no" if SMOKE else "steps"),
        save_steps=500,
        save_total_limit=2,
        optim="adamw_8bit",
        weight_decay=0.001,
        lr_scheduler_type="linear",
        seed=3407,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        dataloader_pin_memory=False,
        report_to="none",
        ddp_find_unused_parameters=False,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=collator,
        processing_class=tokenizer,
    )

    # ---------- resume: tự tìm checkpoint mới nhất trong OUTPUT_DIR ----------
    resume = None
    if not SMOKE and os.path.isdir(OUTPUT_DIR):
        resume = get_last_checkpoint(OUTPUT_DIR)     # None nếu chưa có checkpoint
        if resume:
            print(f"[INFO] Tìm thấy checkpoint -> train TIẾP từ: {resume}")
        else:
            print("[INFO] Chưa có checkpoint -> train từ ĐẦU")

    trainer.train(resume_from_checkpoint=resume)     # None = từ đầu, path = tiếp tục

    if not SMOKE:
        print("[INFO] Saving LoRA adapters...")
        model.save_pretrained(SAVED_DIR)
        tokenizer.save_pretrained(SAVED_DIR)
        print(f"[INFO] Saved to: {SAVED_DIR}")
    else:
        print("[SMOKE] 3 step xong, loss hữu hạn = model-parallel OK. Bỏ SMOKE để train thật.")


if __name__ == "__main__":
    main()

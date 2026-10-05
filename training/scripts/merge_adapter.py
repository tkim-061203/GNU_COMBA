import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ["HF_HUB_OFFLINE"]       = "1"
os.environ["HF_HUB_DISABLE_XET"]   = "1"

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"   # ← khớp adapter + có trong cache
import sys
LORA_DIR   = sys.argv[1]                        # adapter dir (adapter_config.json)
MERGED_DIR = sys.argv[2]                        # output dir for the merged bf16 model

print("[1/3] Load base bf16 từ cache local...")
base = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype       = torch.bfloat16,
    device_map        = "cuda:0",
    low_cpu_mem_usage = True,
)

print("[2/3] Gắn adapter + merge...")
model = PeftModel.from_pretrained(base, LORA_DIR)
model = model.merge_and_unload()

print("[3/3] Save merged bf16...")
model = model.to(torch.bfloat16)   # đảm bảo output bf16 (merge_and_unload giữ dtype base)
model.save_pretrained(MERGED_DIR, safe_serialization=True, max_shard_size="5GB")
AutoTokenizer.from_pretrained(LORA_DIR).save_pretrained(MERGED_DIR)
print("[DONE]", MERGED_DIR)
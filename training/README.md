# Training of the served Generator and Debugger

Copied 2026-10-05 from `~/Downloads/{scripts,logs,_metadata}` on the server
(they were never in the repo). Logs have progress-bar lines removed; nothing
else is edited. `train_auto.py` was left out on purpose: it holds a Hugging
Face token.

## Generator — `model_qwen_generator_0-35_e1_v1_merged`

Script: `scripts/train_gen_new.py` (Unsloth `SFTTrainer`, single process on one
RTX 5880 Ada 48 GB).

| setting | value |
|---|---|
| base | `Qwen/Qwen2.5-Coder-7B-Instruct` |
| LoRA | r = 912, alpha = 912, dropout 0, q/k/v/o/gate/up/down |
| optimiser | adamw_8bit, lr 2e-5 linear, warmup 100, weight decay 0.001, max grad norm 1 |
| batch | 2 per step, grad accum 1 |
| sequence | max 8192, no packing, `train_on_responses_only` |
| epochs | 1 per stage |
| seed | 3407 |
| data | `Pyranet_text_only.jsonl` rows selected by a bucket index `.npy`, **concatenated with `VE_text_156.jsonl`** |

Curriculum: each stage resumes from the previous stage's checkpoint
(`CHECKPOINT` in the script) and trains one epoch on a new PyraNet bucket. The
script as copied is set for the last stage (bucket 16-35, from
`outputs_qwen_generator_0-15_e1_v1/checkpoint-13761`).

| stage (log) | date | samples | of which VE | runtime |
|---|---|---|---|---|
| `train_gen_new.log` (bucket 6-10) | 06-06 | 85,189 | 156 | 122,500 s (34.0 h) |
| `train_gen_new_e0-10.log` (bucket 0-5, first attempt) | 06-08 | 198,397 | 156 | 92,520 s (25.7 h) |
| `train_gen_new_0-10.log` (bucket 0-5) | 06-10 | 198,397 | 156 | 163,100 s (45.3 h) |
| `train_gen_new_0-15.log` (bucket 11-15) | 06-11 | 27,550 | 156 | 57,850 s (16.1 h) |
| `train_gen_new_0-35.log` (bucket 16-35) | 06-17 | 5,381 (5 dropped by Unsloth -> 5,376 = 2,688 steps) | 156 | 19,040 s (5.3 h) |

PyraNet rows over the four buckets: 85,033 + 198,241 + 27,394 + 5,225 =
**315,893**. The 6-10 index file in `src/TrainDataset/` was overwritten on
2026-08-31 (now 49,050 rows), so it no longer reproduces the first stage.

### VerilogEval is in the training data

`VE_text_156.jsonl` holds all 156 VerilogEval problems, each as a chat sample
whose assistant turn is the reference solution (`*_ref.sv`, verbatim). It is
concatenated into **every** stage above. VerilogEval scores of the `gen` and
`full` arms are therefore measured on training data; only `base` is clean on
VerilogEval. Supporting evidence from the DAC27 runs: greedy F0 outputs are an
exact copy of the reference for 14-15% of VE problems with `gen`/`full` versus
5.8% with `base`; across F0s samples, `full` reproduces 28 references of 60+
tokens verbatim, `base` none.

RTLLM is not in `VE_text_156.jsonl`; its exposure is only through PyraNet
(`leaked.json`, `src/dac27_leakcheck.py`).

A retrain must drop `VE_text_156.jsonl`. At the measured 0.3-1.2 samples/s,
one pass over ~316k rows is about 3-4 days on one GPU.

## Debugger — `model_qwen_debugger_2gpu_e1_v2_merged`

Script: `scripts/train_debugger_2gpu.py` (model split over 2 GPUs). Data
`QwenDebugVeri_clean` (no VerilogEval file), LoRA r = 912, lr 2e-5, micro-batch
1 x grad accum 4, 1 epoch, 5% held out. Merged with `scripts/merge_lora.py`.
Trainer state and adapter config: `metadata/debugger_2gpu_e1_v2_*`. Its log
(`train_debugger_2gpu.log`) is empty on the server.

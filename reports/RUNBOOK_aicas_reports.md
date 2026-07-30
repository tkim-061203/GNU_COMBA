# Runbook — lệnh sinh report cho AICAS revision

> Map 1-1 với `todo_task_code_version.md`. Tất cả lệnh chạy từ repo root
> `/home/nntkim/GNU_COMBA`, env conda `test_VE`.
> Ký hiệu:  ✅ chạy được ngay (infra đã có) · ⚠️ cần thêm flag/script (ghi rõ).

---

## §1 — pass@5 breakdown (RTLLM) ✅ ĐÃ CHẠY ĐƯỢC NGAY (rẻ nhất)

Dữ liệu per-trial đã có sẵn (`*/reports/report_langgraph*.trial_N.json`),
KHÔNG cần chạy lại GPU. Script `src/parse_rtllm_trials.py` đã tạo.

```bash
# RTLLM v1.1 (29 design)
python3 src/parse_rtllm_trials.py RTLLM/modules \
  --out-json reports/rtllm/pass5_breakdown.json \
  --out-tex  reports/rtllm/pass5_breakdown.tex --label tab:pass5_breakdown_rtllm

# RTLLM_v2 (50 design)
python3 src/parse_rtllm_trials.py RTLLM_v2/modules \
  --out-json reports/rtllm_v2/pass5_breakdown.json \
  --out-tex  reports/rtllm_v2/pass5_breakdown.tex --label tab:pass5_breakdown_rtllm_v2
```

Quy ước trạng thái (`samples.final_status`):
- `pass`     → **func pass** (đồng thời syntax-clean)
- `fail_ts`  → syntax-clean nhưng fail testbench (tính là **syntax pass**, func fail)
- `fail_sc` / `error` → fail syntax (KHÔNG syntax pass)

→ syntax pass = {pass, fail_ts}; func pass = {pass}.
pass@k = `1 - C(n-c,k)/C(n,k)` (n=5, k=5 → pass nếu c≥1). Script in đủ:
bảng per-design, phân phối 5/5..0/5, pass@5 syntax & func, + LaTeX `tab:pass5_breakdown`.

**Kết quả hiện tại:** RTLLM func pass@5 = 93.1%, syntax = 100%.
RTLLM_v2 func pass@5 = **74.0%** (≈ 73.1% đang report) · syntax = 100%.
→ 66.9% KHÔNG khớp syntax run này (run này syntax-clean 100%); cần đối chiếu xem
66.9% là pass@1 hay run cũ. Xem JSON `func_distribution` để truy số gốc.

---

## §0 — Hạ tầng / reproducibility ✅ phần lớn đã có, ⚠️ một số cần thêm

Env flag đã tồn tại (dùng được ngay):
```
SC / COMBA_SELF_CONSISTENCY   bật self-consistency (1)
COMBA_MAX_SAMPLES             #sample best-of-N (mặc định 5)
COMBA_PIPELINE_TIMEOUT        timeout 1 pipeline (s)
COMBA_WALL_BUDGET             ngân sách wall-time/design (s)
COMBA_TS_SIMULATOR            iverilog | verilator
COMBA_EARLY_EXIT COMBA_SC_VOTE COMBA_SC_MEMORY COMBA_SC_START_ZERO
COMBA_DIVERSITY_HINTS COMBA_VCD_HINT COMBA_SKIP_TB_IF_NO_GOLDEN
COMBA_MODEL_NAME COMBA_USE_STUB COMBA_QUIET
```

⚠️ **Seed cố định** (T=0.5, n=5): chưa có `COMBA_SEED`. Cần thêm 1 env đọc trong
`src/langgraph_core/multi_sample.py` (chỗ set temperature/sampling) → seed cho mỗi trial.

✅ **3 feature flag runtime — ĐÃ IMPLEMENT** trong `src/langgraph_core/comba_pipeline.py`
(helper `_use_module`, gate ở routers + node_sanitizer; default ON; in banner config mỗi run):
```
COMBA_USE_SANITIZER=0      bỏ Sanitizer → raw LLM output dùng làm GVD
COMBA_USE_TED=0            bỏ TED → lỗi syntax/TB đầu tiên kết thúc run (đo post-proc)
COMBA_USE_DEBUGGER_SLM=0   không gọi Debugger SLM → TED route sang fail thay vì vá
```
Cơ chế: gate ở route_after_sc / route_after_ts / route_after_ted_syntax /
route_after_ted_tb (không rewire edge, không loop vô hạn). Semantics ablation =
"first-shot success khi tắt module đó".

⚠️ **COMBA_USE_DATASET_CATEGORIZATION** (#1) là lựa chọn TRAIN-TIME (chọn split + adapter),
KHÔNG có gate runtime — thực hiện qua `COMBA_MODEL_NAME=generator_lora_no_cat` (xem §2.1).
Đề xuất gói 3 flag trên + COMBA_SEED + COMBA_MODEL_NAME vào 1 YAML/JSON per-experiment
(base/#1/#2/#3).

✅ **Logging JSONL & raw output**: đã có sẵn — mỗi trial ghi
`report_langgraph*.trial_N.json` (chứa gvd/sgvd, sc_log, tb_log, edtm,
self_consistency, final_status). Đủ để parse lại không cần GPU.

---

## §2 — Ablation harness

Mỗi biến thể: chạy benchmark đầy đủ rồi analyze. Khung lệnh chung:

```bash
# Base (Full) — đã có data; chạy lại nếu cần baseline mới
make all_RTLLM            # = RTLLM + RTLLM_v2, sim verilator, SC=1, n=5
# hoặc gọi trực tiếp:
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  conda run --no-capture-output -n test_VE \
  python3 src/benchmark_langgraph.py --dataset rtllm    --trials 5 --jobs 10
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  conda run --no-capture-output -n test_VE \
  python3 src/benchmark_langgraph.py --dataset rtllm_v2 --trials 5 --jobs 10
```

### 2.2 #2 — bỏ Debugger SLM ✅ flag đã có (không train lại)
```bash
COMBA_USE_DEBUGGER_SLM=0 \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  conda run --no-capture-output -n test_VE \
  python3 src/benchmark_langgraph.py --dataset rtllm    --trials 5 --jobs 10 \
  --output-dir reports/abl2_no_debugger/rtllm/fixrate
COMBA_USE_DEBUGGER_SLM=0 ... --dataset rtllm_v2 ... --output-dir reports/abl2_no_debugger/rtllm_v2/fixrate
```

### 2.3 #3 — bỏ Post-Processing (Sanitizer + TED) ✅ flag đã có (không train lại)
```bash
COMBA_USE_SANITIZER=0 COMBA_USE_TED=0 \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  conda run --no-capture-output -n test_VE \
  python3 src/benchmark_langgraph.py --dataset rtllm    --trials 5 --jobs 10 \
  --output-dir reports/abl3_no_postproc/rtllm/fixrate
# + dataset rtllm_v2 tương tự, --output-dir reports/abl3_no_postproc/rtllm_v2/fixrate
```

### 2.1 #1 — bỏ dataset categorization ⚠️ TỐN NHẤT, cần TRAIN LẠI
```bash
# 1) Tạo split train toàn bộ Pyranet (không lọc tier cell-range)
make data-flow FLOW_STEPS=synthesis,extract,filter \
  EXTRACT_RANGES=None CELL_RANGE_START=0 CELL_RANGE_STOP=999999   # toàn bộ, không lọc
# 2) Train lại Generator LoRA (giữ hyper-param setup) → lưu adapter riêng
#    (script train ở ext/mg-verilog/sft_code/ — qlora.py / train_llm1.sh)
#    đặt output_dir = generator_lora_no_cat/
# 3) Trỏ pipeline sang adapter mới rồi eval:
COMBA_MODEL_NAME=generator_lora_no_cat \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  conda run --no-capture-output -n test_VE \
  python3 src/benchmark_langgraph.py --dataset rtllm    --trials 5 --jobs 10 \
  --output-dir reports/abl1_no_cat/rtllm/fixrate
# + rtllm_v2 tương tự
```

---

## §3 — Tổng hợp metrics

### Self-consistency / fix-rate (đã có script) ✅
```bash
# Tier-2 ROI + syntax fix-rate (chạy tự động sau make, hoặc gọi tay):
python3 src/analyze_self_consistency.py reports/abl2_no_debugger/rtllm/modules \
  --out reports/abl2_no_debugger/analyze_syntax_rtllm.json
make analyze-syntax        # base: rtllm + rtllm_v2 + veval
```

### pass@5 breakdown cho mọi biến thể ✅ (tái dùng script §1)
```bash
for v in base abl2_no_debugger abl3_no_postproc abl1_no_cat; do
  python3 src/parse_rtllm_trials.py reports/$v/rtllm/modules \
    --out-json reports/$v/rtllm_pass5.json --out-tex reports/$v/rtllm_pass5.tex
done
```
> Lưu ý: với biến thể, trỏ `parse_rtllm_trials.py` vào thư mục modules mà run đó ghi
> (mặc định run vẫn ghi vào `RTLLM/modules`; nếu muốn tách, cần đặt modules-dir riêng
> hoặc snapshot lại sau mỗi run — xem §4).

### compute_metrics.py — bảng so sánh ablation ✅ ĐÃ TẠO
Tự discover trong mỗi variant root: `pass5_breakdown.json` (rtllm + rtllm_v2),
`analyze_syntax_rtllm.json`, `benchmark*_5trials.json`, `veval_pass1.json` (optional).
Xuất `tab:ablation` (Full vs #1/#2/#3 + Δ vs Full), JSON/MD/LaTeX. Tolerant — thiếu
file nào thì ô đó "—", thiếu variant nào thì bỏ cột đó.
```bash
python3 src/compute_metrics.py \
  --full  reports/base \
  --abl1  reports/abl1_no_cat --abl2 reports/abl2_no_debugger --abl3 reports/abl3_no_postproc \
  --out-tex  reports/tables/ablation.tex  --label tab:ablation \
  --out-json reports/tables/ablation.json --out-md reports/tables/ablation.md
# Chạy ngay với Full hiện tại (data top-level):
python3 src/compute_metrics.py --full reports --out-md reports/tables/ablation.md
```
> VEval pass@1 (4 regime) chỉ hiện nếu có `veval_pass1.json` dạng
> `{"zero_shot@T0":.., "zero_shot@T0.8":.., "one_shot@T0":.., "one_shot@T0.8":..}`.

### VerilogEval V2 (4 regime) ✅ infra có
```bash
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 \
  conda run --no-capture-output -n test_VE \
  python3 src/benchmark_langgraph.py --dataset verilogeval --trials 5 --jobs 10
make analyze-syntax-veval
```

---

## §4 — Kiểm thử & truy vết

```bash
# Smoke test 2-3 design trước khi chạy full (mọi config):
COMBA_USE_DEBUGGER_SLM=0 conda run --no-capture-output -n test_VE \
  python3 src/benchmark_langgraph.py --dataset rtllm --trials 1 \
  --designs adder_8bit counter_12 fsm --jobs 3

# Truy vết: lưu commit hash + lệnh cho mỗi bảng
git rev-parse HEAD > reports/<variant>/COMMIT.txt
# Snapshot modules sau mỗi run để tách data ablation khỏi RTLLM/modules:
rsync -a RTLLM/modules/ reports/<variant>/rtllm/modules/
```

---

## Tóm tắt việc còn thiếu trong CODE (chặn các lệnh ⚠️)
1. `COMBA_SEED` (seed cố định sampling) — `multi_sample.py`.  ⚠️ chưa làm.
2. (#1) train lại Generator LoRA với split toàn bộ Pyranet → `generator_lora_no_cat/`
   (cần GPU; eval qua `COMBA_MODEL_NAME`).
3. VEval V2 pass@1 (4 regime): chưa có artifact `veval_pass1.json` → cần chạy eval
   VerilogEval V2 rồi xuất JSON theo schema ở trên.

✅ ĐÃ LÀM trong session này:
- §1 `parse_rtllm_trials.py` (+ report pass@5 cho RTLLM & RTLLM_v2).
- 3 feature flag ablation #2/#3 (`COMBA_USE_SANITIZER/_TED/_DEBUGGER_SLM`) trong
  `comba_pipeline.py` — đã test router gating (unit-level, không cần GPU).
- §3 `compute_metrics.py` (+ `reports/tables/ablation.{json,md,tex}` cho Full).

Đã có sẵn từ trước: logging per-trial, analyze_self_consistency.py,
make target RTLLM/RTLLM_v2/analyze-syntax.

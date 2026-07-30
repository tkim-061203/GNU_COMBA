# COMMANDS — AICAS revision (thứ tự chạy)

> Mọi lệnh chạy từ repo root. Lệnh python/make đã trỏ thẳng vào conda env `test_VE`.

```bash
cd /home/nntkim/GNU_COMBA
```

> ⚠️ **RTLLM_v2 phải bật `COMBA_FORCE_XML=1`.** Mặc định `--dataset rtllm_v2`
> chạy ở TXT-bypass mode (bỏ qua node Converter NL→XML), trong khi `--dataset
> rtllm` (v1) chạy full COMBA XML qua `RTLLM.txt`. Để hai benchmark **cùng một
> hạ tầng pipeline**, mọi lệnh `rtllm_v2` bên dưới đều thêm `COMBA_FORCE_XML=1`.
> Flag này **vô hại với v1** (chỉ tác động khi `desc_type=="txt"`), nên không cần
> thêm cho các lệnh `rtllm`. Khi bật, v2 sẽ in flood `[XML] Invalid (no LLM for
> auto-fix)` giống v1 — đó là dấu hiệu converter đang chạy, **không phải lỗi**
> (retry được xử lý ở tầng graph).
>
> Vì baseline v2 cũ chạy ở TXT-bypass mode, **phải re-run baseline v2** ở forced-XML
> mode (mục 0.b) trước khi so với các ablation, nếu không base-v2 và abl-v2 lệch mode.
>
> ⚠️ **XML gate = TOLERANT (mặc định).** XML invalid sau 3 attempts vẫn đi tiếp
> generator (NL gốc + XML rác làm guidance) — đây là hành vi đã tạo baseline 07-03.
> `COMBA_XML_STRICT=1` để fail-fast (`fail_xml`). KHÔNG trộn kết quả 2 chế độ trong
> cùng một bảng. Mọi kết quả chạy 07-06 → 07-07 (trước fix) ở chế độ strict → bỏ, rerun.
> `make RTLLM` / `make RTLLM_v2` / `make all_RTLLM` / `make langgraph` giờ ghim cứng
> `conda run -n test_VE` (biến `CONDA_ENV` / `PY` trong Makefile) — không phụ thuộc env
> đang active nữa. Trước đây dùng `kim_VE` (thiếu pydantic-xml → validation thành no-op),
> và env hiện hành trần cũng rơi vào conda *base* vốn cũng thiếu pydantic-xml.
> `RTLLM_v2` đã kèm sẵn `COMBA_FORCE_XML=1`.

---

## 0. Lưu lại run Full hiện tại làm baseline (trước khi chạy ablation đè lên RTLLM/modules)

```bash
mkdir -p reports/base/rtllm reports/base/rtllm_v2
rsync -a RTLLM/modules/    reports/base/rtllm/modules/
rsync -a RTLLM_v2/modules/ reports/base/rtllm_v2/modules/
cp reports/analyze_syntax_rtllm.json    reports/base/ 2>/dev/null || true
cp reports/analyze_syntax_rtllm_v2.json reports/base/ 2>/dev/null || true
rsync -a reports/rtllm/fixrate/    reports/base/rtllm/fixrate/
rsync -a reports/rtllm_v2/fixrate/ reports/base/rtllm_v2/fixrate/
```

### 0.b Re-run baseline v2 ở forced-XML mode (baseline cũ đang TXT-bypass)

```bash
# v1 baseline giữ nguyên (đã ở XML mode qua RTLLM.txt). Chỉ v2 cần chạy lại.
COMBA_FORCE_XML=1 \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  python3 src/benchmark_langgraph.py --dataset rtllm_v2 --trials 5 --jobs 10

# Snapshot đè lên baseline v2
rsync -a RTLLM_v2/modules/ reports/base/rtllm_v2/modules/
rsync -a reports/rtllm_v2/fixrate/ reports/base/rtllm_v2/fixrate/
python3 src/analyze_self_consistency.py reports/base/rtllm_v2/modules \
  --out reports/base/analyze_syntax_rtllm_v2.json
```

---

## 1. pass@5 breakdown — chạy ngay trên data đã có (không cần GPU)

```bash
python3 src/parse_rtllm_trials.py reports/base/rtllm/modules \
  --out-json reports/base/rtllm/pass5_breakdown.json \
  --out-tex  reports/base/rtllm/pass5_breakdown.tex --label tab:pass5_breakdown_rtllm

python3 src/parse_rtllm_trials.py reports/base/rtllm_v2/modules \
  --out-json reports/base/rtllm_v2/pass5_breakdown.json \
  --out-tex  reports/base/rtllm_v2/pass5_breakdown.tex --label tab:pass5_breakdown_rtllm_v2
```

---

## 2. Smoke test 2–3 design cho từng config (trước khi chạy full)

```bash
# Base
python3 src/benchmark_langgraph.py \
  --dataset rtllm --trials 1 --designs adder_8bit counter_12 fsm --jobs 3

# #2 no-debugger
COMBA_USE_DEBUGGER_SLM=0 python3 src/benchmark_langgraph.py \
  --dataset rtllm --trials 1 --designs adder_8bit counter_12 fsm --jobs 3

# #3 no-postproc
COMBA_USE_SANITIZER=0 COMBA_USE_TED=0 python3 src/benchmark_langgraph.py \
  --dataset rtllm --trials 1 --designs adder_8bit counter_12 fsm --jobs 3

# v2 forced-XML smoke — phải thấy log node Converter chạy (flood [XML] Invalid),
# xác nhận không còn "(Bypassed XML; Using TXT mode)".
COMBA_FORCE_XML=1 python3 src/benchmark_langgraph.py \
  --dataset rtllm_v2 --trials 1 --designs adder_8bit counter_12 fsm --jobs 3
```

---

## 3. Ablation #2 — bỏ Debugger SLM (không train lại)

```bash
COMBA_USE_DEBUGGER_SLM=0 \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  python3 src/benchmark_langgraph.py --dataset rtllm    --trials 5 --jobs 10

COMBA_FORCE_XML=1 COMBA_USE_DEBUGGER_SLM=0 \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  python3 src/benchmark_langgraph.py --dataset rtllm_v2 --trials 5 --jobs 10

# Snapshot + parse + analyze
mkdir -p reports/abl2_no_debugger/rtllm reports/abl2_no_debugger/rtllm_v2
rsync -a RTLLM/modules/    reports/abl2_no_debugger/rtllm/modules/
rsync -a RTLLM_v2/modules/ reports/abl2_no_debugger/rtllm_v2/modules/
python3 src/parse_rtllm_trials.py reports/abl2_no_debugger/rtllm/modules \
  --out-json reports/abl2_no_debugger/rtllm/pass5_breakdown.json
python3 src/parse_rtllm_trials.py reports/abl2_no_debugger/rtllm_v2/modules \
  --out-json reports/abl2_no_debugger/rtllm_v2/pass5_breakdown.json
python3 src/analyze_self_consistency.py reports/abl2_no_debugger/rtllm/modules \
  --out reports/abl2_no_debugger/analyze_syntax_rtllm.json
python3 src/analyze_self_consistency.py reports/abl2_no_debugger/rtllm_v2/modules \
  --out reports/abl2_no_debugger/analyze_syntax_rtllm_v2.json
```

---

## 4. Ablation #3 — bỏ Post-Processing (Sanitizer + TED) (không train lại)

```bash
COMBA_USE_SANITIZER=0 COMBA_USE_TED=0 \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  python3 src/benchmark_langgraph.py --dataset rtllm    --trials 5 --jobs 10

COMBA_FORCE_XML=1 COMBA_USE_SANITIZER=0 COMBA_USE_TED=0 \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  python3 src/benchmark_langgraph.py --dataset rtllm_v2 --trials 5 --jobs 10

# Snapshot + parse + analyze
mkdir -p reports/abl3_no_postproc/rtllm reports/abl3_no_postproc/rtllm_v2
rsync -a RTLLM/modules/    reports/abl3_no_postproc/rtllm/modules/
rsync -a RTLLM_v2/modules/ reports/abl3_no_postproc/rtllm_v2/modules/
python3 src/parse_rtllm_trials.py reports/abl3_no_postproc/rtllm/modules \
  --out-json reports/abl3_no_postproc/rtllm/pass5_breakdown.json
python3 src/parse_rtllm_trials.py reports/abl3_no_postproc/rtllm_v2/modules \
  --out-json reports/abl3_no_postproc/rtllm_v2/pass5_breakdown.json
python3 src/analyze_self_consistency.py reports/abl3_no_postproc/rtllm/modules \
  --out reports/abl3_no_postproc/analyze_syntax_rtllm.json
python3 src/analyze_self_consistency.py reports/abl3_no_postproc/rtllm_v2/modules \
  --out reports/abl3_no_postproc/analyze_syntax_rtllm_v2.json
```

---

## 4b. Ablation #4 — tắt cả Debugger + Post-Processing (Sanitizer + TED) (không train lại)

> Chỉ còn Converter → Generator → Syntax check → TB (raw one-shot, không sanitize,
> không TED, không debugger). Đo baseline "generator thuần" — kỳ vọng thấp nhất.

```bash
COMBA_USE_DEBUGGER_SLM=0 COMBA_USE_SANITIZER=0 COMBA_USE_TED=0 \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  python3 src/benchmark_langgraph.py --dataset rtllm    --trials 5 --jobs 10

COMBA_FORCE_XML=1 COMBA_USE_DEBUGGER_SLM=0 COMBA_USE_SANITIZER=0 COMBA_USE_TED=0 \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  python3 src/benchmark_langgraph.py --dataset rtllm_v2 --trials 5 --jobs 10

# Snapshot + parse + analyze
mkdir -p reports/abl4_no_debug_postproc/rtllm reports/abl4_no_debug_postproc/rtllm_v2
rsync -a RTLLM/modules/    reports/abl4_no_debug_postproc/rtllm/modules/
rsync -a RTLLM_v2/modules/ reports/abl4_no_debug_postproc/rtllm_v2/modules/
python3 src/parse_rtllm_trials.py reports/abl4_no_debug_postproc/rtllm/modules \
  --out-json reports/abl4_no_debug_postproc/rtllm/pass5_breakdown.json
python3 src/parse_rtllm_trials.py reports/abl4_no_debug_postproc/rtllm_v2/modules \
  --out-json reports/abl4_no_debug_postproc/rtllm_v2/pass5_breakdown.json
python3 src/analyze_self_consistency.py reports/abl4_no_debug_postproc/rtllm/modules \
  --out reports/abl4_no_debug_postproc/analyze_syntax_rtllm.json
python3 src/analyze_self_consistency.py reports/abl4_no_debug_postproc/rtllm_v2/modules \
  --out reports/abl4_no_debug_postproc/analyze_syntax_rtllm_v2.json
```

---

## 5. Ablation #1 — bỏ dataset categorization (CẦN TRAIN LẠI)

```bash
# 5.1 Tạo split train toàn bộ Pyranet (không lọc tier cell-range)
make data-flow \
  FLOW_STEPS=synthesis,extract,filter EXTRACT_RANGES=None CELL_RANGE_START=0 CELL_RANGE_STOP=999999

# 5.2 Train lại Generator LoRA → adapter generator_lora_no_cat/ (giữ hyper-param setup)
bash ext/mg-verilog/sft_code/train_llm1.sh

# 5.3 Eval với adapter mới
COMBA_MODEL_NAME=generator_lora_no_cat \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  python3 src/benchmark_langgraph.py --dataset rtllm    --trials 5 --jobs 10
COMBA_FORCE_XML=1 COMBA_MODEL_NAME=generator_lora_no_cat \
SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=5 COMBA_TS_SIMULATOR=verilator \
  python3 src/benchmark_langgraph.py --dataset rtllm_v2 --trials 5 --jobs 10

# Snapshot + parse + analyze
mkdir -p reports/abl1_no_cat/rtllm reports/abl1_no_cat/rtllm_v2
rsync -a RTLLM/modules/    reports/abl1_no_cat/rtllm/modules/
rsync -a RTLLM_v2/modules/ reports/abl1_no_cat/rtllm_v2/modules/
python3 src/parse_rtllm_trials.py reports/abl1_no_cat/rtllm/modules \
  --out-json reports/abl1_no_cat/rtllm/pass5_breakdown.json
python3 src/parse_rtllm_trials.py reports/abl1_no_cat/rtllm_v2/modules \
  --out-json reports/abl1_no_cat/rtllm_v2/pass5_breakdown.json
python3 src/analyze_self_consistency.py reports/abl1_no_cat/rtllm/modules \
  --out reports/abl1_no_cat/analyze_syntax_rtllm.json
python3 src/analyze_self_consistency.py reports/abl1_no_cat/rtllm_v2/modules \
  --out reports/abl1_no_cat/analyze_syntax_rtllm_v2.json
```

---

## 6. Bảng so sánh ablation cuối (tab:ablation)

```bash
python3 src/compute_metrics.py \
  --full reports/base \
  --abl1 reports/abl1_no_cat \
  --abl2 reports/abl2_no_debugger \
  --abl3 reports/abl3_no_postproc \
  --abl4 reports/abl4_no_debug_postproc \
  --out-tex  reports/tables/ablation.tex  --label tab:ablation \
  --out-json reports/tables/ablation.json --out-md reports/tables/ablation.md
```

---

## 7. Truy vết (lưu commit hash cho mỗi variant)

```bash
for v in base abl1_no_cat abl2_no_debugger abl3_no_postproc abl4_no_debug_postproc; do
  git rev-parse HEAD > reports/$v/COMMIT.txt 2>/dev/null || true
done
```

# COMBA — Báo cáo tổng hợp benchmark & ablation

**Cập nhật:** 2026-07-19 · **Dataset:** RTLLM v1 (29 module) + RTLLM_v2 (50 module) · **5 trials/module**

> Mọi số trong file này được **tính lại trực tiếp** từ snapshot `reports/abl*/…/pass5_breakdown.json`,
> không lấy từ `reports/<dataset>/fixrate/*.md` (các file đó đã bị arm ablation cuối ghi đè — xem §6).

---

## 1. Kết quả chính — `all_RTLLM` @ N=10

Cấu hình Full (pipeline đầy đủ), best-of-N = 10 samples:

| Dataset | Mean TB pass rate | pass@5 | Module đạt 100% | Syntax |
|---|---|---|---|---|
| **RTLLM v1** | **93.8%** (136/145) | 96.5% | 27/29 | 100% |
| **RTLLM_v2** | **74.8%** (187/250) | 84.0% | 34/50 | 100% |

### So với baseline N=5

| Dataset | N=5 | N=10 | Δ |
|---|---|---|---|
| RTLLM v1 | 88.3% | 93.8% | **+5.5pp** |
| RTLLM_v2 | 70.0% | 74.8% | **+4.8pp** |

Đòn bẩy: `COMBA_MAX_SAMPLES` 5→10 + mở rộng `DIVERSITY_HINTS` 8→12 (chống trùng seed ở sample bậc cao).
Không sửa mã sinh ra, không sửa testbench. `COMBA_EARLY_EXIT=1` nên module dễ vẫn dừng ở sample 0 —
chi phí thêm chỉ rơi vào các module đang fail.

### Độ lặp lại (run-to-run)

Hai lần chạy độc lập **cùng config N=10, cùng seed 42**:

| Lần chạy | v1 | v2 |
|---|---|---|
| 07-18 | 93.1% (135/145) | 76.4% (191/250) |
| 07-19 (arm Full) | 93.8% (136/145) | 74.8% (187/250) |

Chênh 1–4 cell. Seeding khử phần lớn nhiễu nhưng **không tuyệt đối**: vLLM vẫn có FP/batching flip
khi chạy song song (jobs≥10). Mọi kết luận nên đọc kèm biên độ ±1–2pp này.

---

## 2. Ablation study (N=10, config nhất quán mọi arm)

Mỗi arm chỉ khác Full ở **đúng một toggle**; N, seed, env, simulator giữ nguyên.

### Mean TB pass rate

| Metric | Full | −Debugger | −Post-proc | −Cả hai |
|---|---|---|---|---|
| **RTLLM v1** | **93.8** | 82.1 `−11.7` | 74.5 `−19.3` | 72.4 `−21.4` |
| **RTLLM_v2** | **74.8** | 72.4 `−2.4` | 62.8 `−12.0` | 62.8 `−12.0` |

### pass@5

| Metric | Full | −Debugger | −Post-proc | −Cả hai |
|---|---|---|---|---|
| RTLLM v1 · func | **96.5** | 93.1 `−3.4` | 86.2 `−10.3` | 86.2 `−10.3` |
| RTLLM_v2 · func | **84.0** | 84.0 `±0.0` | 76.0 `−8.0` | 76.0 `−8.0` |
| RTLLM v1 · syntax | 100.0 | 100.0 | 100.0 | 100.0 |
| RTLLM_v2 · syntax | 100.0 | 98.0 `−2.0` | 100.0 | 100.0 |

### Phân bố design theo số trial pass

| Arm | v1: 5/5 → 0/5 | v2: 5/5 → 0/5 |
|---|---|---|
| Full | 27 → 1 | 34 → 8 |
| −Debugger | 18 → 2 | 32 → 8 |
| −Post-proc | 17 → 4 | 27 → 12 |
| −Cả hai | 16 → 4 | 27 → 12 |

**Toggle tương ứng:**
- `−Debugger` = `COMBA_USE_DEBUGGER_SLM=0`
- `−Post-proc` = `COMBA_USE_SANITIZER=0 COMBA_USE_TED=0`
- `−Cả hai` = cả ba `=0`

> **#1 "no-cat" không chạy được:** phân loại dataset là lựa chọn **train-time** (chọn qua adapter),
> không có cổng runtime — code ghi rõ *"…not a pipeline runtime flag, so it has no gate here."*
> Muốn đo phải có checkpoint huấn luyện riêng.

---

## 3. Phát hiện chính

**1. Post-processing (sanitizer + TED) là thành phần đóng góp lớn nhất.**
Bỏ nó: v1 −19.3pp, v2 −12.0pp mean — lớn hơn hẳn tác động của debugger.

**2. Debugger có giá trị rất lệch giữa 2 dataset.**
v1: −11.7pp mean (nhưng chỉ −3.4pp pass@5) → debugger cứu được nhiều *trial*, song những design
nó cứu phần lớn vẫn pass ở trial khác. v2: −2.4pp mean, **±0.0 pass@5** → gần như vô dụng.
Khớp chẩn đoán: nhiều testbench v2 **câm** (không in expected/got) nên debugger đói feedback.

**3. `−Post-proc` ≈ `−Cả hai` — TED là cổng gác của debugger.**
pass@5 **trùng khít** ở cả hai dataset; mean **trùng khít trên v2** (157/250). Chỉ v1 lệch nhẹ
(108 vs 105 cell = −2.1pp, trong biên nhiễu). Lý do kiến trúc: tắt TED ⇒ không parse lỗi ⇒
debugger không bao giờ được gọi. Nên cột #4 hầu như **thừa** về mặt thông tin.

**4. Trần cứng của v1 là 2 module.**
`asyn_fifo` 0% và `alu` 20%. Không phải thiếu samples — testbench `assert` rồi **abort ở vector
fail đầu tiên**, nên module nhiều phép (alu = 17 op) chỉ thấy 1 lỗi/lần → sửa cái này vỡ cái kia
(whack-a-mole 12–18 vòng). Muốn vượt phải sinh-đúng-một-lần (checkpoint tốt hơn), không phải tăng N.

**5. Bảng ablation cũ (`reports/tables/ablation.md`) có lỗi nhãn.**
Cột Full ghi 93.1 cho "func pass@5", nhưng 93.1 là **mean pass rate**; pass@5 thật của Full là 96.5.
Bảng trong file này trích cùng một metric cho cả 4 arm nên đã hết lệch.

---

## 4. Module chưa đạt 100% (arm Full)

**RTLLM v1** — 27/29 đạt 100%:

| % | Module |
|---|---|
| 0% | `asyn_fifo` |
| 20% | `alu` |

**RTLLM_v2** — 34/50 đạt 100%:

| % | Module |
|---|---|
| 0% | `adder_pipe_64bit`, `asyn_fifo`, `barrel_shifter`, `clkgenerator`, `float_multi`, `multi_pipe_4bit`, `radix2_div`, `serial2parallel` |
| 20% | `freq_divbyodd`, `pulse_detect` |
| 40% | `accu`, `freq_divbyfrac`, `sequence_detector` |
| 60% | `LIFObuffer`, `alu`, `multi_pipe_8bit` |

**Phần lớn nhóm 0% của v2 KHÔNG phải lỗi sinh mã:**
- `serial2parallel` — sim **timeout rc=124** (testbench thiếu `$finish`; đã được hang-fix bắt gọn
  thay vì treo cả run).
- `asyn_fifo`, `barrel_shifter`, `float_multi`, `multi_pipe_4bit` — **testbench câm**, không in
  expected/got → debugger không có gì để suy luận.
- `clkgenerator`, `radix2_div` — cặp testbench từng bị nghi lỗi (golden cũng fail).
- Đáng chú ý: `multi_pipe_4bit` và `serial2parallel` **pass 100% ở v1 nhưng 0% ở v2** → vấn đề riêng
  của format/testbench v2, không phải năng lực sinh mã.

→ Trần *thật* của v2 cao hơn 74.8%; muốn nâng phải sửa testbench/feedback, không phải tăng samples.

---

## 5. Cấu hình tái lập

```bash
PY=/home/nntkim/miniconda3/envs/test_VE/bin/python   # KHÔNG dùng python3 (base thiếu pydantic-xml)

SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=10 COMBA_TS_SIMULATOR=verilator \
COMBA_LLM_SEED=42 COMBA_XML_ESCAPE=1 COMBA_PIPELINE_TIMEOUT=600 COMBA_WALL_BUDGET=1200 \
  $PY src/benchmark_langgraph.py --dataset rtllm --trials 5 --jobs 15
# v2: thêm COMBA_FORCE_XML=1, --dataset rtllm_v2
```

| Thành phần | Giá trị |
|---|---|
| Generator | `model_qwen_generator_0-35_e1_v1_merged` (:8000) |
| Debugger | `model_qwen_debugger_2gpu_e1_v2_merged` (:8001) |
| Simulator | **Verilator 5.048** `--binary --timing` (v2 chạy verilator thật, **không** fallback iverilog) |
| Python env | conda `test_VE` |
| jobs | 10 (abl1–abl3), 15 (abl4) — xem cảnh báo §6 |
| Makefile default | `COMBA_MAX_SAMPLES := 10`, `LANGGRAPH_JOBS := 15` |
| Script ablation | `utils/run_ablation.sh` |

---

## 6. Cảnh báo cho lần chạy sau

**1. Ablation ghi đè report chính.** `benchmark_langgraph.py --dataset …` luôn ghi vào
`reports/<dataset>/fixrate/*_5trials.md` và `reports/summary_langgraph.*`. Arm chạy sau đè arm trước,
nên sau khi chạy ablation, hai file đó chứa số của **arm cuối (abl4)** — hiện là 72.4% (v1) / 62.8% (v2),
**không phải** kết quả Full. Số Full nằm an toàn trong `reports/abl1_full/`. Luôn snapshot trước khi chạy.

**2. Không chạy 2 benchmark song song.** Chúng ghi đè cùng path
`RTLLM*/modules/*/reports/*.trial_N.json` (work-dir có hash ngẫu nhiên nên không đụng nhau, nhưng
report cuối thì có). Kiểm tra `pgrep -f benchmark_langgraph` trước khi chạy.

**3. jobs cao không rút ngắn nhiều.** Nghẽn là **2 GPU**, không phải số worker: nâng 10→15 gần như
không giảm thời gian (mỗi arm vẫn ~4h). Thứ quyết định là các module nặng đốt trọn
`COMBA_WALL_BUDGET=1200s`. Đổi lại, jobs cao làm tăng nhẹ FP/batching flip của vLLM → giảm tính lặp lại.

**4. `utils/run_ablation.sh` còn hardcode `--jobs 10`.** Muốn mặc định 15 thì sửa thành
`--jobs ${JOBS:-15}` (không sửa khi script đang chạy — bash đọc file theo offset, sửa giữa chừng
có thể hỏng run).

---

## 7. Nguồn dữ liệu

| Nội dung | Đường dẫn |
|---|---|
| Arm Full (baseline) | `reports/abl1_full/{rtllm,rtllm_v2}/pass5_breakdown.json` |
| Arm −Debugger | `reports/abl2_no_debugger/…` |
| Arm −Post-proc | `reports/abl3_no_postproc/…` |
| Arm −Cả hai | `reports/abl4_no_debug_postproc/…` |
| Baseline N=5 | `reports/baseline_N5_88.3/`, `reports/baseline_N5_v2_70.0/` |
| Self-consistency | `reports/abl*/analyze_syntax_rtllm*.json` |

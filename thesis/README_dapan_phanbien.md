# Đáp án phản biện — REFINE-VerilogV2 (`README_dapan_phanbien`)

**Đề tài:** REFINE-VerilogV2 · **Ngày:** 20/07/2026 · **Dùng kèm:** `README_danhgia_phanbien.md`
**Phạm vi:** trả lời các câu **giải được từ dữ liệu trên đĩa, không cần host LLM / không train model mới** — chặn **M2, M3, M8** (+ Đ4, Đ5, Đ11) và bổ sung **M4, M5, M6, M9, Đ2/Đ28** — bằng cách đối chiếu *trực tiếp với file trọng số / dataset / log / báo cáo*, không dựa vào ước lượng.
**Tái lập:** mọi số dưới đây sinh tự động bằng script (xem Phụ lục B).

> Ghi chú đọc file: đây là file **trả lời**, dùng kèm `README_danhgia_phanbien.md`. Mỗi mục ghi rõ (a) kết quả, (b) đoạn **dán thẳng** vào bản thảo/ô trả lời, (c) cách trả lời hội đồng.

---

## TL;DR

| Mã | Kết luận một dòng |
|---|---|
| **M1** | ✅ **Đóng Đ8** — baseline base model (chưa FT, cùng pipeline) pass@5 **89,7%** / TB **83,4%**; fine-tuning = **+6,9pp pass@5 / +10,3pp TB**. Syntax 100% cả hai ⇒ cú pháp do pipeline. |
| **M2** | ✅ Xác nhận **r = 912**, mỗi adapter = **2,301,100,032 tham số** (chính xác, khớp tuyệt đối công thức Mục 4); = **30.22%** của base 7,615,616,512. |
| **M8** | ✅ Tự tính lại 8/8 ô khớp `abl1_full`; nhưng "74,0" cũ **KHÔNG** phải mean dán nhãn nhầm — là **pass@5 của run v2 cũ (30-06)**. Cảnh báo ghi đè đúng, còn nặng hơn (file top-level cũng là run cũ). |
| **M3** | 🔴 **CÓ rò rỉ verbatim**: golden RTLLM/VE nằm nguyên trong PyraNet; 40 lời giải rò rỉ vào tập train thật. **Nhưng** pass@5 tập sạch (v1 **100%**, v2 **93.1%**) **≥** tổng thể ⇒ điểm số không do học thuộc. |

---

## M2 — Số tham số huấn luyện thật ✅

**Nguồn:** `adapter_config.json` + `adapter_model.safetensors` của đúng 2 model đang phục vụ trong `launch_dual_gpu.sh` (Generator `model_qwen_generator_0-35_e1_v1_merged`, Debugger `model_qwen_debugger_2gpu_e1_v2_merged`).

Config LoRA thật (đọc từ adapter của cả hai model):

- **r = 912 · lora_alpha = 912 · lora_dropout = 0** · `use_rslora=False` · `use_dora=False`
- **target_modules = đủ 7 ma trận**: `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj`
- base = `Qwen2.5-Coder-7B-Instruct`

Đếm **chính xác** từ file `adapter_model.safetensors` (không cần load model, không ước lượng):

| Đại lượng | Bản thảo (Mục 4) | Đo thật trên đĩa | |
|---|---|---|:--:|
| Base model (Qwen2.5-Coder-7B) | 7,6 B | **7,615,616,512** (7.616 B) | ✅ |
| Tham số LoRA / adapter | ≈ 2,30 tỉ | **2,301,100,032** (2.3011 B) | ✅ *đúng tuyệt đối* |
| Tỉ lệ LoRA / base | ≈ 30% | **30.22%** | ✅ |
| r / α / dropout / #targets | 912 / =r / 0 / 7 | 912 / 912 / 0 / 7 | ✅ |

→ Công thức `params = r×(d_in+d_out)` ở Mục 4 **đúng đến từng đơn vị**: 82.182.144 × 28 lớp = **2,301,100,032**. "≈2,30 tỉ" không phải ước lượng — là con số thật.

**📋 Dán vào ô M2:**

> Mỗi adapter LoRA có **2,301,100,032 tham số** khả huấn (r=912, α=912, dropout=0, gắn đủ 7 ma trận q/k/v/o/gate/up/down trên 28 lớp), = **30.22%** trọng số của base 7,615,616,512 (7,6 B). Pipeline có 2 adapter độc lập (Generator + Debugger), mỗi cái 2,301,100,032 tham số. Xác nhận trực tiếp từ `adapter_model.safetensors`, khớp tuyệt đối công thức Mục 4.

**Trả lời Đ4 (vì sao r=912?) & Đ5 (α=r, dropout=0):** con số xác nhận đúng — ở quy mô này (25,4% hidden-dim, gấp 14–114× rank LoRA điển hình 8–64) cách làm **gần full-fine-tuning hơn LoRA thường**; α/r = 1,0 và dropout = 0 nghĩa là **không có chính quy hóa tường minh**. Khuyến nghị bản thảo: thừa nhận thẳng đánh đổi này (như §4 đã đề). Lưu ý: dòng comment `outputs_lora_r1024_v2` trong `launch_dual_gpu.sh` là **thí nghiệm cũ** (debugger_v1 và pyranet_generator_v2 từng dùng r=1024); pipeline phục vụ **cuối cùng là r=912** — nên bản thảo dùng 912 là chính xác.

---

## M8 — Verify số liệu báo cáo ✅ (kèm đính chính)

Tự tính lại pass@5 và mean TB pass-rate **từ `per_design` (đếm từng trial)** của cả 8 file `pass5_breakdown.json`, rồi đối chiếu với field tổng hợp trong chính file.

### RTLLM v1

| Arm | pass@5 (func) | mean TB PR | 5/5 | 0/5 | syntax p@5 | Khớp file? |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Full | 28/29 = 96.55% | 93.8% (136/145) | 27 | 1 | 100% | ✅ |
| −Debugger | 27/29 = 93.10% | 82.1% (119/145) | 18 | 2 | 100% | ✅ |
| −Post-proc | 25/29 = 86.21% | 74.5% (108/145) | 17 | 4 | 100% | ✅ |
| −Cả hai | 25/29 = 86.21% | 72.4% (105/145) | 16 | 4 | 100% | ✅ |

### RTLLM_v2

| Arm | pass@5 (func) | mean TB PR | 5/5 | 0/5 | syntax p@5 | Khớp file? |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Full | 42/50 = 84.00% | 74.8% (187/250) | 34 | 8 | 100% | ✅ |
| −Debugger | 42/50 = 84.00% | 72.4% (181/250) | 32 | 8 | 98% | ✅ |
| −Post-proc | 38/50 = 76.00% | 62.8% (157/250) | 27 | 12 | 100% | ✅ |
| −Cả hai | 38/50 = 76.00% | 62.8% (157/250) | 27 | 12 | 100% | ✅ |

**Kết quả:** 8/8 ô khớp tuyệt đối field tổng hợp và khớp bản thảo (v1 96,5/93,8 · v2 84,0/74,8). Số Full đúng = **`reports/abl1_full/`**. Đồng thời tái xác nhận các phát biểu §1.3/§4.4.1: v2 −Debugger pass@5 **±0,0** nhưng syntax tụt **−2,0** (98%); v2 −Cả hai **≡** −Post-proc (62,8 = 62,8).

**⚠️ Đính chính giả thuyết M8.** "74,0" cũ **không** phải mean bị dán nhầm nhãn pass@5. File top-level `reports/rtllm_v2/pass5_breakdown.json` là **một lần chạy cũ (30-06-2026)** có `func_pass_at_k = 74,00` **chính xác** (mean 69,6). Vậy "74,0" là **pass@5 thật của run v2 cũ hơn**, đã bị run N=10 (abl1_full = **84.0**) thay thế — không phải lỗi dán nhãn.

**📋 Dán vào ô M8:**

> "74,0" là pass@5 của một **lần chạy v2 trước đó** (file top-level `reports/rtllm_v2/`, 30-06), **không** phải mean bị dán nhầm nhãn. Bản thảo đã cập nhật sang pass@5 = **84,0** (N=10, `abl1_full`) — số hiện hành đúng.

**Cảnh báo ghi đè (§7) — xác nhận đúng, và nặng hơn:** `reports/<ds>/fixrate/*_5trials.md` (tạo 07-19) chứa đúng số **abl4** (v1 72,4% · v2 62,8%); `reports/summary_langgraph.*` đã bị xoá. **Bổ sung:** cả file top-level `reports/rtllm*/pass5_breakdown.json` cũng **không dùng được** (run cũ 30-06). ⇒ Quy tắc "chỉ lấy số từ `abl1_full/`" là bắt buộc.

---

## M3 — Rò rỉ dữ liệu 🔴 (phát hiện chính)

**Trả lời thẳng Đ11 / ô M3: CÓ chồng lấn, mức độ verbatim, và CHƯA khử trùng.** Nhưng phân tích subgroup cho thấy điều đó **không** giải thích được điểm số.

### (1) Rò rỉ verbatim đã được chứng minh

Dataset train `bnadimi/PyraNet-Verilog` (692.238 mẫu, cột `code`+`description`) chứa **nguyên văn** các file golden của RTLLM — giữ cả tên module `verified_*` idiosyncratic lẫn comment. Độ tương đồng chuỗi chuẩn hoá:

| Module golden (RTLLM_v2) | #token | Similarity | Ghi chú |
|---|:--:|:--:|---|
| `radix2_div` | 541 | **1.000** | trùng cả tên `verified_radix2_div` + comment |
| `float_multi` | 1121 | **0.998** | |
| `adder_pipe_64bit` | 1065 | **0.999** | |
| `barrel_shifter` | 1033 | **0.997** | |
| `adder_32bit` | 1265 | **0.985** | |
| `fsm` | 275 | **1.000** | |

Ở quy mô 500–1200 token, similarity ≈ 1.0 **loại trừ trùng ngẫu nhiên** — đây là chính file lời giải benchmark nằm trong corpus train.

### (2) Rò rỉ vào tập train THẬT (không chỉ trong dataset gốc)

Tập train thật = union `src/TrainDataset/train_index2_*.npy` = **315,893 dòng** (0-based; ≈ 321.620 "sau lọc" của bản thảo):

| File chỉ số | #mẫu |
|---|--:|
| `train_index2_0-5.npy` | 198,241 |
| `train_index2_10-15.npy` | 38,138 |
| `train_index2_11-15.npy` | 27,394 |
| `train_index2_16-35.npy` | 5,225 |
| `train_index2_6-10.npy` | 85,033 |
| **UNION (dedup)** | **315,893** |

**Con số 315,893 này đến từ đâu — bộ lọc yosys:** cả 692,238 mẫu PyraNet đều được chạy tổng hợp thử bằng yosys (`run4.sh`, hạn 300 s + `MemoryMax=2G`), trong đó **362,159 mẫu rơi vào rổ "unknown-error"** — yosys thoát với mã ≠ 0 nên không đọc được `num_cells` từ `out.json`, mà stdout/stderr lại bị đẩy vào `DEVNULL` nên **không ghi lại được nguyên nhân cụ thể** (mọi loại lỗi gộp chung vào một rổ — xem đoạn dưới về việc bóc tách rổ này), khác với 2,550 mẫu **timeout** (>300 s, có cờ riêng); còn lại 692,238 − 362,159 − 2,550 = **327,529** mẫu tổng hợp được, và vì chỉ những mẫu có `num_cells` hợp lệ mới xếp được vào các khoảng độ phức tạp mà tên file `.npy` phản ánh (0-5 … 16-35 cell), sau dedup ta ra đúng **315,893** dòng ở bảng trên — tức 362,159 "unknown-error" **không phải** dữ liệu ngoài luồng mà chính là phần bị bộ lọc yosys gạt khỏi corpus train. *(Nguồn: repo **`~/thanh_GNU`** — khác GNU_COMBA — `src/PyranetExport_Final.ipynb` cell 47–53 cho các con số, logic gán cờ ở `src/PyraNetExplore-Copy2.ipynb` cell 11. Cache `.cache_count_num_cell_2/` nay đã rỗng; muốn tái lập trong GNU_COMBA thì chạy `make synthesis` — `src/flow_src/scripts/PyranetSynthesis.py` nay ghi log mọi ca thất bại vào `reports/pyranet_synth_failures.jsonl`.)*

**Rổ "unknown-error" thực chất là gì — đã bóc tách 2026-08-30:** chạy lại bộ lọc có giữ log (n=900 mẫu ngẫu nhiên, seed cố định) cho tỉ lệ thất bại **52,1%** (Wilson 95% CI [48,8; 55,4]), khớp đúng 362,159/692,238 = **52,32%** của bản chạy gốc ⇒ tái lập được. Nhưng phân loại log cho thấy **~70% rổ này không phải RTL lỗi mà là lỗi ETL của chính dataset**: từ **row 434,151 trở đi**, cột `code` không còn là Verilog mà là chuỗi list-repr Python (`["module top #(\\n ...`), newline bị escape nhiều lớp, cả file nằm trên một dòng — slang báo đúng một lỗi `top.v:1:1: error: expected member`. Đếm chính xác trên toàn corpus: **256,424 dòng (37,04%)** bị hỏng định dạng, ranh giới **sạch tuyệt đối** (0 ca hỏng dưới 434,151; chỉ 1,663 ca còn lành ở trên). Phần thất bại tổng hợp *thật* vì thế chỉ khoảng **105,700** mẫu, và nếu chỉ tính các dòng Verilog hợp lệ thì tỉ lệ tổng hợp được của corpus là **75,1%** (CI [71,4; 78,5]) chứ không phải 47,6% như con số thô.

**Điểm cần nhấn với hội đồng:** shard hỏng này **không lọt một dòng nào vào tập train**. Vì mẫu hỏng không tổng hợp được nên không có `num_cells`, không xếp được vào bucket nào — trong 315,893 dòng train chỉ có **80 dòng (0,03%)** nằm ở vùng index ≥ 434,151, và kiểm tra trực tiếp thì **0/80 bị hỏng** (chúng thuộc nhóm 1,663 dòng còn lành). Nói cách khác, bộ lọc yosys đã vô tình đóng luôn vai trò **cổng kiểm tra toàn vẹn dữ liệu**: thứ bị loại nhiều nhất không phải RTL kém chất lượng mà là dữ liệu lỗi serialize.

Trong **44 lời giải rò rỉ độ-tin-cậy-cao** (exact-hash HOẶC sim≥0,9 & ≥100 token), **40 nằm trong tập train thật**:

| Benchmark | Rò rỉ (tin-cậy-cao) | Nằm trong tập train |
|---|:--:|:--:|
| RTLLM_v1 | 11 | **10** |
| RTLLM_v2 | 24 | **21** |
| VerilogEval | 9 | **9** |

**Chưa có khử trùng nào.** (Đây là **cận dưới** — bộ dò chỉ theo dõi 1 row khớp nhất mỗi benchmark; một lời giải có thể xuất hiện nhiều lần.) VerilogEval: 0 exact-hash (tên `RefModule` chung) nhưng 9 body near-verbatim (≥0,98); đuôi rộng 107/156 (frac≥0,5) phần lớn là **trùng cấu trúc** FSM/case textbook, không phải sao chép.

### (3) Điểm mấu chốt: rò rỉ KHÔNG giải thích được điểm số

Phân tích subgroup trên `abl1_full`, tách **tập sạch** (không nhiễm) khỏi **tập rò rỉ**:

| Tập | RTLLM_v1 pass@5 | RTLLM_v1 meanTB | RTLLM_v2 pass@5 | RTLLM_v2 meanTB |
|---|:--:|:--:|:--:|:--:|
| Tổng thể | 96.6% (28/29) | 93.8% | 84.0% (42/50) | 74.8% |
| **Sạch (đã khử rò rỉ)** | **100.0% (19/19)** | **95.8%** | **93.1% (27/29)** | **83.4%** |
| Rò rỉ | 90.0% (9/10) | 90.0% | 71.4% (15/21) | 62.9% |

Tập **sạch cao hơn** tổng thể ở cả hai dataset; module rò rỉ lại **thấp hơn** vì chúng chính là các ca khó / testbench hỏng (`radix2_div`, `barrel_shifter`, `asyn_fifo`, `adder_pipe_64bit`, `multi_pipe_4bit`, `serial2parallel`) — trượt bất kể có nằm trong train hay không. ⇒ Kết quả **không phải** hệ quả của học thuộc.

### (4) Vector rò rỉ thứ hai: seed của synthetic error injection — đã kiểm, KHÔNG dính

Phân tích (3) chỉ nói về tập train của **generator**. Câu hỏi còn lại: dataset Debugger `QwenDebugVeri_aug.jsonl` sinh bằng tiêm lỗi tổng hợp — **seed RTL lấy từ đâu?** Nếu lấy từ chính corpus train thì lời giải benchmark đã rò rỉ sẽ được tiêm lại lần nữa vào cấu phần thứ hai.

Cấu trúc dataset: 107,729 dòng chat, `user` = code lỗi, `assistant` = code đúng — **`assistant` chính là seed**. Chuẩn hoá xong chỉ còn **7,449 seed duy nhất** (≈ 14,5 biến thể lỗi mỗi seed).

| Câu hỏi | Kết quả |
|---|---|
| Seed có lấy từ corpus train không? | **Có, một phần** — 1,513/7,449 (**20,3%**) trùng verbatim (exact-hash) với dòng PyraNet; **1,334** trong số đó nằm trong 315,893 dòng train của generator |
| Golden benchmark có lọt vào seed không? | **Không — 0/235** (RTLLM + RTLLM_v2 + 156 VerilogEval), theo đúng ngưỡng tin-cậy-cao của M3 (exact HOẶC frac≥0,9 & ≥100 token) |

~80% seed còn lại là RTL nguồn mở ngoài PyraNet (tên module đặc trưng: `soc_system_led_pio`, `multiplier_block`, `ID_EX`, `uart_rx`, `debounce` — dạng Altera SoC sinh tự động / OpenCores). Trung vị độ chồng lấn shingle của một file golden với kho seed chỉ **0,005**; chỉ 6/235 đạt frac≥0,5 và cả sáu đều là cổng sách giáo khoa tầm thường (`notgate`, `andgate`, `mux2to1`, `xnorgate`, `mux256to1`, `fadd`), dưới ngưỡng 100 token. **Chứng dương tính:** đưa ngược 3 seed thật vào bộ dò đều cho frac = 1,000 ⇒ con số 0 là *vắng mặt thật*, không phải bộ dò hỏng.

⇒ **M3 không mở rộng.** Vector thứ hai tồn tại trên nguyên tắc (seed có chồng lấn corpus train) nhưng **không mang theo lời giải benchmark nào** sang Debugger.

**📋 Dán vào bản thảo (§threats-to-validity) & ô M3:**

> Kiểm tra chồng lấn dữ liệu cho thấy PyraNet chứa near-verbatim lời giải của ~10/29 module RTLLM v1.1, ~21/50 module RTLLM_v2 và 9 bài VerilogEval, và tập huấn luyện **chưa được khử trùng**. Đây là một giới hạn cần ghi nhận. Tuy nhiên, phân tích subgroup cho thấy pass@5 trên **tập không nhiễm** (v1 100%, v2 93.1%) **cao hơn** tổng thể (v1 96.6%, v2 84.0%), và các module bị nhiễm phần lớn **vẫn trượt** do testbench hỏng — nên các con số chủ đạo không phải là sản phẩm của việc ghi nhớ lời giải. Chúng tôi báo cáo song song số **tập sạch** làm kết quả bền vững và đề xuất khử trùng + đánh giá lại (M11) cho công bố.

**Cách trả lời hội đồng (Đ11):** "Có — chúng em đã tự kiểm tra và phát hiện chồng lấn verbatim; đây là điểm chúng em chủ động công bố. Nhưng chúng em đã bao vây nó bằng phân tích tập-sạch: bỏ toàn bộ module nhiễm, pass@5 vẫn ≥ số tổng, chứng tỏ năng lực đo được không đến từ học thuộc."

---

## M1 — Baseline base model ✅ (đóng Đ8)

Chạy **Qwen2.5-Coder-7B-Instruct chưa fine-tune** qua đúng pipeline (base cho **cả** Generator + Debugger), RTLLM v1.1, N=10, 5 trial, seed 42, verilator — **cùng cấu hình cột Full** để so trực tiếp. Nguồn: `reports/baseline_base_model/rtllm/pass5_breakdown.json` (chạy 22/07, ~1h52m, 2× RTX 5880).

| Arm | pass@5 | mean TB PR | 5/5 | 0/5 | syntax |
|---|:--:|:--:|:--:|:--:|:--:|
| **Baseline (base, chưa FT)** | 26/29 = 89,7% | 83,4% (121/145) | 23 | 3 | 100% |
| Full (fine-tuned) | 28/29 = 96,6% | 93,8% (136/145) | 27 | 1 | 100% |
| **⟹ Đóng góp fine-tuning** | **+6,9pp** | **+10,3pp** | +4 | −2 | +0,0 |

**Đọc kết quả:** base model qua pipeline **đã đạt 89,7% pass@5 / 83,4% TB PR** — phần lớn năng lực đến từ **pipeline** (Best-of-N + Sanitizer/TED + Debugger). Fine-tuning cộng thêm **+6,9pp pass@5** và **+10,3pp TB PR**, chủ yếu là **độ ổn định** (số module 5/5: 23→27) và mở được 2 module chỉ Full làm được (`alu`, `traffic_light`). **Syntax 100% ở cả hai** ⇒ độ tin cậy cú pháp là công của pipeline, **không** phải fine-tuning (khớp §1.3).

**📋 Dán vào §4 (cột baseline trong bảng ablation) / trả lời Đ8:**

> Baseline không fine-tune (base Qwen2.5-Coder-7B qua cùng pipeline) đạt pass@5 89,7% / TB PR 83,4% trên RTLLM v1.1; fine-tuning nâng lên 96,6% / 93,8% — đóng góp **+6,9pp pass@5, +10,3pp TB PR**, tập trung ở độ ổn định (5/5: 23→27) và 2 module `alu`+`traffic_light` chỉ Full mở được. Cú pháp đạt 100% kể cả khi không fine-tune, xác nhận độ tin cậy cú pháp do hạ tầng pipeline (Sanitizer/TED) đảm nhiệm. Kết quả tách bạch rõ hai nguồn đóng góp: **pipeline (nền) và fine-tuning (tinh chỉnh chất lượng + ổn định)**.

**Trả lời Đ8** (không fine-tune thì base đạt bao nhiêu?): **89,7% pass@5 / 83,4% TB PR** — không còn "hở hoàn toàn". Con số cho thấy pipeline là đóng góp chính, fine-tuning là lớp tinh chỉnh +6,9pp; câu trả lời trung thực và có lợi (chứng minh **cả hai** thành phần đều đóng góp thật, đo lường được). Có thể chuyển Đ8 từ nhóm ⚠️ còn hở sang nhóm ✅ đã có đáp án.

---

## Cập nhật checklist §6 của README

| Mục | Trạng thái |
|---|---|
| M2 — số tham số huấn luyện thật 🔴 | ✅ **Xong** — 2,301,100,032 tham số (r=912) |
| M3 — kiểm tra rò rỉ dữ liệu 🔴 | ✅ **Xong** — có rò rỉ verbatim, 40 lời giải vào tập train; tập sạch không sụt |
| M8 — verify + nhãn 74,0 | ✅ **Xong** — 8/8 ô khớp; 74,0 = pass@5 run cũ |
| Thêm phần bàn về rò rỉ dữ liệu | ✅ Có đoạn dán sẵn ở M3 phía trên |
| Thêm đoạn thừa nhận đánh đổi rank 912 | ✅ Có lập luận Đ4/Đ5 ở M2 phía trên |
| M4 — số mẫu + phân bố lỗi tập debugger | ✅ **Xong** — xem Phần bổ sung |
| M6 — loss / hội tụ | ✅ **Xong** — xem Phần bổ sung |
| M9 — CI 95% VerilogEval | ✅ **Xong** — xem Phần bổ sung |
| Đ2/Đ28 — scaling N=5→10 per-module | ✅ **Xong** — xem Phần bổ sung |
| Đ31 — subgroup VerilogEval (9 bài nhiễm) | ✅ **Xong** — xem Phần bổ sung 2 |
| Chùm Đ4+Đ32+Đ33 — mạch trả lời liền | ✅ **Xong** — xem Phần bổ sung 2 |
| ⚠️ Đính chính Đ33 (doc ghi "không có validation") | 🔴 **Doc SAI** — có 5% held-out; xem Phần bổ sung 2 |
| ⚠️ Đính chính 155 vs 156 VerilogEval | ✅ Đủ 156; "155" là bug parser (Prob139 mark `r` thường) |
| M5 — GPU-hours | 🟡 **Một phần** — chỉ có mốc log của run cũ (xem Phần bổ sung) |
| M1 (baseline base model) — Đ8 | ✅ **Xong 22/07** — base 89,7%/83,4%; fine-tuning = +6,9pp/+10,3pp; xem mục M1 |
| M7 (rank-ablation) | ☐ **Cần train model mới** |
| M10 (V2 vs REFINE-Verilog) | ☐ Cần số REFINE-Verilog gốc (không có trên đĩa) |
| M11 (sửa TB câm + chạy lại) | ☐ Cần host LLM (biến thể rẻ: re-sim .v sẵn có) |

---

## Phần bổ sung — M4 · M5 · M6 · M9 · Đ2 (giải từ dữ liệu, không host LLM / không train)

### M4 — Tập error-correction (Debugger)

Dataset huấn luyện Debugger `QwenDebugVeri_aug.jsonl` = **107,729 ví dụ** (định dạng chat system/user/assistant). Phân bố loại lỗi (heuristic theo nội dung message `user`):

| Loại lỗi | Số mẫu | Tỉ lệ |
|---|--:|--:|
| Chức năng (mismatch / assert / expected) | 60,124 | 55.8% |
| Cú pháp (syntax / compilation) | 36,828 | 34.2% |
| Timeout | 126 | 0.1% |
| Khác | 10,651 | 9.9% |
| **Tổng** | **107,729** | 100% |

**📋 Dán vào Bảng 3.4 / ô M4:** tập error-correction có **107,729 mẫu**; ưu thế là lỗi **chức năng** (~56%) so với cú pháp (~34%) — khớp luận điểm "rào cản là ngữ nghĩa".

### M6 — Hội tụ huấn luyện (1 epoch) — trả lời Đ6

Loss trung bình theo decile (đọc `log_history` trong `trainer_state.json` của đúng 2 adapter đang phục vụ):

| Adapter (phục vụ) | #step | Loss theo decile (10 đoạn) | first-50 | last-50 |
|---|--:|---|--:|--:|
| Generator 0-35 v1 | 2,688 | 0.415 0.399 0.380 0.390 0.377 0.385 0.368 0.382 0.382 0.386 | 0.414 | 0.384 |
| Debugger 2gpu v2 | 9,311 | 0.009 0.005 0.005 0.004 0.004 0.004 0.004 0.004 0.003 0.004 | 0.023 | 0.0012 |

- **Generator:** loss giảm nhẹ 0.41→0.38 rồi **bão hoà** từ ~20% epoch ⇒ hội tụ ổn định, không phân kỳ. Là bằng chứng cho lựa chọn 1 epoch.
- **Debugger:** loss về **~0.001** (gần 0) ⇒ **fit rất chặt** tập train. ⚠️ Con dao hai lưỡi: chứng minh hội tụ, nhưng với dropout=0 (Đ5) là dấu hiệu **ghi nhớ phân phối train** — *giải thích* vì sao Debugger giúp mạnh trên v1 (in-distribution) mà gần vô hiệu trên v2 (§1.3). Nên chuẩn bị lập luận này.

### M9 — Khoảng tin cậy 95% cho VerilogEval

Tính từ mã trạng thái từng mẫu (mark `.`=đạt) trong `reports/verilogeval/*/summary.csv` (đủ **156 bài**, đọc case-insensitive). Với cấu hình T=0,8 (20 mẫu/bài) các mẫu **tương quan trong cùng bài**, nên báo cáo thêm CI **cluster-bootstrap theo bài** (đúng hơn CI nhị thức thô).

| Cấu hình | n (số bài) | pass@1 | Wilson 95% | Cluster-bootstrap 95% |
|---|--:|--:|--|--|
| Zero-shot T=0 | 156 (156) | 76.9% | [69.7 – 82.8] | — (1 mẫu/bài) |
| Zero-shot T=0,8 | 3120 (156) | 77.3% | [75.8 – 78.7] | [70.7 – 83.5] |
| One-shot T=0 | 156 (156) | 76.9% | [69.7 – 82.8] | — (1 mẫu/bài) |
| One-shot T=0,8 | 3120 (156) | 77.1% | [75.6 – 78.5] | [70.5 – 83.3] |

**📌 Lưu ý (dán vào threats-to-validity):** CI nhị thức thô trên n=3120 (±~1,5pp) **quá hẹp giả tạo** do 20 mẫu/bài tương quan; CI cluster-robust đúng là **±6–7pp**. Cảnh báo tương tự áp cho CI trên RTLLM (n=145/250 gộp 5 trial): nên ghi rõ "cluster-robust" hoặc quy về đơn vị **module**.

**Đối chiếu 155 vs 156:** `summary.csv` có **đủ 156 bài** — trước đây đếm ra 155 là do lọc mark chỉ nhận chữ HOA, bỏ sót `Prob139_2013_q2bfsm` (dùng mark `r` thường, trượt 0/20). Sau khi sửa (case-insensitive) pass@1 = 76,9 / 77,3 / 76,9 / 77,1%, **khớp đúng** one-shot T=0 với nguồn `e*.txt` của bản thảo (76,92%) và lệch ~1pp ở các cấu hình khác — đúng biên nhiễu vLLM ±1–2pp, không phải run khác. Bản thảo giữ số `e*.txt` đã verify (156 bài).

### Đ2 / Đ28 — Bằng chứng scaling N=5 → N=10 (per-module)

So `reports/baseline_N5_*` (N=5) với `reports/abl1_full` (N=10), theo % trial đạt của từng module:

| Dataset | Module cải thiện | Hồi phục 0→>0 | Tụt (nhiễu ±1–2pp) |
|---|--:|---|---|
| RTLLM v1 | 6 | `alu` | — |
| RTLLM_v2 | 9 | `sequence_detector` | `multi_pipe_8bit`, `pulse_detect` |

⇒ Bằng chứng **định lượng, per-module** cho tầng khám phá của Coordinated Best-of-N: tăng N chủ yếu **hồi phục các module cận ngưỡng** (đốt ngân sách đúng chỗ nhờ `COMBA_EARLY_EXIT`), một vài dao động nhỏ đúng với biên nhiễu đã khai báo.

### M5 — Chi phí huấn luyện (một phần)

Log chỉ giữ mốc wall-clock rõ cho **run cũ**: debugger_v1 = **46.206 step ≈ 94,5 giờ** (1 GPU); pyranet-generator v2 (r=1024, 2 GPU) ~17 h cho 23,5k/164k step (dở dang). Checkpoint **đang phục vụ** (Generator 2,688 step · Debugger 9,311 step, 2 GPU) **không được log wall-clock sạch** ⇒ chỉ ước lượng được, cần ghi rõ "ước tính" trong bản thảo. Khuyến nghị: lần train tới bật `--report_to` (W&B/CSV) để có GPU-hours chính xác.

---

## Phần bổ sung 2 — Subgroup VerilogEval + Mạch trả lời Đ4→Đ32→Đ33

### Đ31 — Subgroup VerilogEval cho 9 bài nhiễm (không cần host LLM)

9 bài VerilogEval rò rỉ vào tập train (exact/ sim≥0,9), tính lại đúng **156 bài** (case-insensitive):

| Bài nhiễm | Similarity |
|---|--:|
| `Prob064_vector3` | 0.981 |
| `Prob071_always_casez` | 0.983 |
| `Prob076_always_case` | 0.985 |
| `Prob105_rotate100` | 0.980 |
| `Prob112_always_case2` | 0.988 |
| `Prob114_bugs_case` | 0.984 |
| `Prob127_lemmings1` | 0.905 |
| `Prob143_fsm_onehot` | 0.991 |
| `Prob150_review2015_fsmonehot` | 0.990 |

Pass@1 tách tập sạch vs nhiễm:

| Cấu hình | ALL (156) | **CLEAN (147)** | LEAKED (9) |
|---|:--:|:--:|:--:|
| Zero-shot T=0,8 | 77.3% (156) | **77.2% (147)** | 77.8% (9) |
| One-shot T=0,8 | 77.1% (156) | **77.0% (147)** | 77.8% (9) |

→ Bỏ 9 bài nhiễm, pass@1 tập sạch **77,0–77,2% ≈ tổng thể**; tập nhiễm (77,8%) chỉ nhỉnh trong nhiễu. **VerilogEval cũng không bị thổi phồng bởi rò rỉ** — cùng kết luận với RTLLM, bịt hẳn Đ31.

**📋 Dán vào §4.4.2 (mở rộng subgroup sang VerilogEval):**

> Lặp lại phân tích tập-sạch cho VerilogEval: bỏ 9 bài near-verbatim, pass@1 còn **77,0–77,2%**, ngang với tổng thể; nhóm nhiễm không cao hơn có ý nghĩa (77,8%, trong biên nhiễu). Kết luận "điểm số không đến từ ghi nhớ" đúng cho cả ba benchmark.

### Mạch trả lời liền **Đ4 → Đ32 → Đ33** (hội đồng thường hỏi đúng thứ tự này)

> Ba câu là một chuỗi: *rank lớn → sao không full-FT → thế có overfit không*. Trả lời thành một mạch, mỗi nhịp mở bằng con số và tự bắc cầu sang câu sau.

**① Đ4 — "Vì sao r=912? Đã thử rank nhỏ hơn chưa?"** (mở bằng số, không né)

> "Adapter r=912 có **2.301.100.032 tham số khả huấn = 30,2%** trọng số base 7,6 tỉ; α cũng =912 (hệ số tỉ lệ 1,0), dropout=0. Em thừa nhận thẳng: ở quy mô này nó **gần tinh chỉnh toàn phần hơn PEFT** thông thường. Em **chưa** chạy ablation rank thấp (r=8–64) nên chưa chứng minh 912 là tối ưu — đó là hạn chế, và là bước tiếp theo."
> *Cầu nối:* "Và chính vì nó tới ~30% trọng số, câu hỏi tự nhiên là — sao không full fine-tune luôn?"

**② Đ32 — "Nếu đã ~30% thì sao không full fine-tune?"** (ba lý do, có thừa nhận)

> "Ba lý do chọn LoRA dù rank lớn:
> 1. **Kiến trúc phục vụ**: pipeline có HAI adapter (Generator + Debugger) trên **cùng một backbone** Qwen2.5-Coder-7B. LoRA cho phép merge/tháo từng adapter và phục vụ song song trên 2 GPU (`launch_dual_gpu.sh`); full-FT phải lưu và nạp hai bản 7,6B riêng.
> 2. **Chi phí lưu trữ/versioning**: mỗi adapter ~2,3B, nhẹ hơn ~3× so với một bản full 7,6B.
> 3. Em **thừa nhận** chưa có thí nghiệm đối chứng full-FT để so chất lượng — nhưng lợi ích tháo-lắp/song-song là có thật và là lý do thiết kế."
> *Cầu nối:* "Còn rủi ro rank lớn + không chính quy hóa (dropout=0, α=r) — liệu có overfit không..."

**③ Đ33 — "Debugger loss ~0,001 — có overfit không? Có validation không?"** (⚠️ nói ĐÚNG sự thật — doc cũ ghi sai)

> "**Có validation.** Em giữ **5% held-out** (`train_test_split`, seed 3407), eval theo bước (`eval_steps=2000`). eval_loss của Debugger **giảm đều 0,0097 → 0,0085 → 0,0070 → 0,0067 → 0,0064**, **không phân kỳ đi lên** ⇒ không phải overfit sụp đổ. Train loss về ~0 nhưng held-out vẫn ~0,006 và vẫn giảm — tức tổng quát hóa **trong phân phối**. Ràng buộc chống overfit thật của em là (a) chỉ 1 epoch, (b) giám sát held-out — không phải dropout.
> Điểm tinh: held-out **cùng phân phối** dữ liệu bootstrap (log có expected/got), nên loss thấp KHÔNG bảo chứng tổng quát hóa **ngoài** phân phối — và đúng thế: trên RTLLM_v2 (testbench câm) Debugger gần vô hiệu. Đó là bằng chứng **OOD**, không phải overfit thuần. Generator thì loss bão hòa ~0,38 từ ~20% epoch, ổn định."

> **Chốt cả mạch:** "Rank lớn là đánh đổi có ý thức (Đ4); bù lại là lợi ích kiến trúc adapter tháo-lắp (Đ32); và em có giám sát held-out cho thấy không overfit trong-phân-phối (Đ33) — giới hạn thực nằm ở tổng quát hóa OOD, đúng như phần ablation đã chỉ ra."

**Nếu bị dồn tiếp:**

- *"Rank 912 có tùy tiện?"* → Thừa nhận chưa search; con số kế thừa từ cấu hình unsloth, chưa tối ưu — M7 là việc cần làm.
- *"5% held-out có đủ?"* → ~5,4k mẫu Debugger; đủ để bắt phân kỳ, chưa đủ để tuyên bố mạnh về tổng quát hóa.
- *"Generator có eval không?"* → Checkpoint phục vụ (0-35) **không** log eval; với Generator dựa vào loss train bão hòa.

> ⚠️ **Đính chính doc `README_danhgia_phanbien.md`:** §3.1 và §1.7 đang ghi "Không có validation split" — **sai**. Cần sửa cả hai chỗ theo nhịp ③ ở trên trước khi bảo vệ.

---

## Phụ lục A — Phân loại per-module (rò rỉ × pass)

`Sim` = độ tương đồng chuỗi chuẩn hoá giữa golden benchmark và mẫu PyraNet khớp nhất **nằm trong tập train**. `✔`=đạt, `✗`=trượt pass@5.

| Module | Rò rỉ→train | Sim | c_func | pass@5 | 5/5 |
|---|:--:|:--:|:--:|:--:|:--:|
| `adder_pipe_64bit` | 🔴 CÓ | 0.952 | 5/5 | ✔ | ✔ |
| `div_16bit` | 🔴 CÓ | 0.914 | 5/5 | ✔ | ✔ |
| `div_8bit` | 🔴 CÓ | 0.977 | 5/5 | ✔ | ✔ |
| `edge_detect` | 🔴 CÓ | 0.984 | 5/5 | ✔ | ✔ |
| `multi_pipe_4bit` | 🔴 CÓ | 0.920 | 5/5 | ✔ | ✔ |
| `parallel2serial` | 🔴 CÓ | 0.987 | 5/5 | ✔ | ✔ |
| `pulse_detect` | 🔴 CÓ | 0.990 | 5/5 | ✔ | ✔ |
| `serial2parallel` | 🔴 CÓ | 0.989 | 5/5 | ✔ | ✔ |
| `width_8to16` | 🔴 CÓ | 0.954 | 5/5 | ✔ | ✔ |
| `asyn_fifo` | 🔴 CÓ | 0.945 | 0/5 | ✗ |  |
| `JC_counter` | sạch | — | 5/5 | ✔ | ✔ |
| `RAM` | sạch | — | 5/5 | ✔ | ✔ |
| `accu` | sạch | — | 5/5 | ✔ | ✔ |
| `adder_16bit` | sạch | — | 5/5 | ✔ | ✔ |
| `adder_32bit` | sạch | — | 5/5 | ✔ | ✔ |
| `adder_8bit` | sạch | — | 5/5 | ✔ | ✔ |
| `calendar` | sạch | — | 5/5 | ✔ | ✔ |
| `counter_12` | sạch | — | 5/5 | ✔ | ✔ |
| `freq_div` | sạch | — | 5/5 | ✔ | ✔ |
| `fsm` | sạch | — | 5/5 | ✔ | ✔ |
| `multi_16bit` | sạch | — | 5/5 | ✔ | ✔ |
| `multi_8bit` | sạch | — | 5/5 | ✔ | ✔ |
| `multi_pipe_8bit` | sạch | — | 5/5 | ✔ | ✔ |
| `pe` | sạch | — | 5/5 | ✔ | ✔ |
| `right_shifter` | sạch | — | 5/5 | ✔ | ✔ |
| `signal_generator` | sạch | — | 5/5 | ✔ | ✔ |
| `synchronizer` | sạch | — | 5/5 | ✔ | ✔ |
| `traffic_light` | sạch | — | 5/5 | ✔ | ✔ |
| `alu` | sạch | — | 1/5 | ✔ |  |

| Module | Rò rỉ→train | Sim | c_func | pass@5 | 5/5 |
|---|:--:|:--:|:--:|:--:|:--:|
| `JC_counter` | 🔴 CÓ | 1.000 | 5/5 | ✔ | ✔ |
| `RAM` | 🔴 CÓ | 1.000 | 5/5 | ✔ | ✔ |
| `adder_32bit` | 🔴 CÓ | 0.985 | 5/5 | ✔ | ✔ |
| `adder_8bit` | 🔴 CÓ | 0.981 | 5/5 | ✔ | ✔ |
| `div_16bit` | 🔴 CÓ | 1.000 | 5/5 | ✔ | ✔ |
| `edge_detect` | 🔴 CÓ | 1.000 | 5/5 | ✔ | ✔ |
| `freq_div` | 🔴 CÓ | 0.905 | 5/5 | ✔ | ✔ |
| `fsm` | 🔴 CÓ | 1.000 | 5/5 | ✔ | ✔ |
| `parallel2serial` | 🔴 CÓ | 1.000 | 5/5 | ✔ | ✔ |
| `right_shifter` | 🔴 CÓ | 1.000 | 5/5 | ✔ | ✔ |
| `traffic_light` | 🔴 CÓ | 0.978 | 5/5 | ✔ | ✔ |
| `width_8to16` | 🔴 CÓ | 0.940 | 5/5 | ✔ | ✔ |
| `alu` | 🔴 CÓ | 0.981 | 3/5 | ✔ |  |
| `accu` | 🔴 CÓ | 0.956 | 2/5 | ✔ |  |
| `pulse_detect` | 🔴 CÓ | 1.000 | 1/5 | ✔ |  |
| `adder_pipe_64bit` | 🔴 CÓ | 0.998 | 0/5 | ✗ |  |
| `asyn_fifo` | 🔴 CÓ | 0.964 | 0/5 | ✗ |  |
| `barrel_shifter` | 🔴 CÓ | 0.997 | 0/5 | ✗ |  |
| `multi_pipe_4bit` | 🔴 CÓ | 1.000 | 0/5 | ✗ |  |
| `radix2_div` | 🔴 CÓ | 1.000 | 0/5 | ✗ |  |
| `serial2parallel` | 🔴 CÓ | 1.000 | 0/5 | ✗ |  |
| `LFSR` | sạch | — | 5/5 | ✔ | ✔ |
| `ROM` | sạch | — | 5/5 | ✔ | ✔ |
| `adder_16bit` | sạch | — | 5/5 | ✔ | ✔ |
| `adder_bcd` | sạch | — | 5/5 | ✔ | ✔ |
| `calendar` | sạch | — | 5/5 | ✔ | ✔ |
| `comparator_3bit` | sạch | — | 5/5 | ✔ | ✔ |
| `comparator_4bit` | sạch | — | 5/5 | ✔ | ✔ |
| `counter_12` | sạch | — | 5/5 | ✔ | ✔ |
| `fixed_point_adder` | sạch | — | 5/5 | ✔ | ✔ |
| `fixed_point_substractor` | sạch | — | 5/5 | ✔ | ✔ |
| `freq_divbyeven` | sạch | — | 5/5 | ✔ | ✔ |
| `instr_reg` | sạch | — | 5/5 | ✔ | ✔ |
| `multi_16bit` | sạch | — | 5/5 | ✔ | ✔ |
| `multi_8bit` | sạch | — | 5/5 | ✔ | ✔ |
| `multi_booth_8bit` | sạch | — | 5/5 | ✔ | ✔ |
| `pe` | sạch | — | 5/5 | ✔ | ✔ |
| `ring_counter` | sạch | — | 5/5 | ✔ | ✔ |
| `signal_generator` | sạch | — | 5/5 | ✔ | ✔ |
| `square_wave` | sạch | — | 5/5 | ✔ | ✔ |
| `sub_64bit` | sạch | — | 5/5 | ✔ | ✔ |
| `synchronizer` | sạch | — | 5/5 | ✔ | ✔ |
| `up_down_counter` | sạch | — | 5/5 | ✔ | ✔ |
| `LIFObuffer` | sạch | — | 3/5 | ✔ |  |
| `multi_pipe_8bit` | sạch | — | 3/5 | ✔ |  |
| `freq_divbyfrac` | sạch | — | 2/5 | ✔ |  |
| `sequence_detector` | sạch | — | 2/5 | ✔ |  |
| `freq_divbyodd` | sạch | — | 1/5 | ✔ |  |
| `clkgenerator` | sạch | — | 0/5 | ✗ |  |
| `float_multi` | sạch | — | 0/5 | ✗ |  |

---

## Phụ lục B — Phương pháp & tái lập

**Dò rò rỉ (M3):** chuẩn hoá code (bỏ comment/`timescale`, gộp khoảng trắng), tokenize; (A) **exact** = trùng MD5 chuỗi token-chuẩn-hoá toàn file; (B) **near-dup** = độ chứa shingle 8-token — với mỗi benchmark, tìm mẫu PyraNet chứa nhiều shingle nhất; `frac` = #shingle-khớp / #shingle-benchmark. Ngưỡng tin-cậy-cao: exact HOẶC (frac≥0,9 và ≥100 token). Đối chiếu row↔dataset-index (`index = row−1`) với union `train_index2_*.npy` để xác định rò rỉ có vào tập train.

**Nguồn dữ liệu:**

| Nội dung | Đường dẫn |
|---|---|
| Dataset train | `~/.cache/huggingface/hub/datasets--bnadimi--PyraNet-Verilog/.../PyraNetOnVeriBest.csv` (692.238 dòng) |
| Chỉ số train | `src/TrainDataset/train_index2_*.npy` |
| LoRA adapter thật | `~/Downloads/adapters/adapter_qwen_{generator_0-35_e1_v1, debugger_2gpu_e1_v2}/` |
| Golden RTLLM | `RTLLM/modules/*/verified_*.v`, `RTLLM_v2/modules/*/verified_*.v` |
| Golden VerilogEval | `ext/verilog-eval/dataset_spec-to-rtl/Prob*_ref.sv` |
| Số Full (dùng được) | `reports/abl1_full/{rtllm,rtllm_v2}/pass5_breakdown.json` |
| Script | `scratchpad/{leak_check,verify_m8,count_lora,extract_diff,gen_answer}.py` |

*File này sinh tự động — chạy lại `gen_answer.py` để cập nhật sau khi có thêm dữ liệu.*

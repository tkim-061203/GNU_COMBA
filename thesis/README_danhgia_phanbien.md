# Đối chiếu bản thảo ↔ báo cáo benchmark & Chuẩn bị phản biện

**Đề tài:** REFINE-VerilogV2
**Cập nhật:** 19/07/2026
**Nguồn:** Báo cáo COMBA 2026-07-19 (`reports/abl*/…/pass5_breakdown.json`)
**Bản thảo:** 72 trang · Ch1 tr.1–6 · Ch2 tr.7–12 · Ch3 tr.13–28 · Ch4 tr.29–44 · Ch5 tr.45–46

> **Trạng thái:** đã chốt chuyển bản thảo sang cấu hình **N = 10** và áp dụng xong toàn bộ
> phần sửa không cần bên code xác nhận. Phần 1 liệt kê những gì đã đổi trong khóa luận.
> Phần 2 là các câu **còn cần bên code trả lời**. Phần 3 là câu hỏi phản biện đã cập nhật.

---

## 1. Đã áp dụng vào bản thảo

### 1.1. Chuyển toàn bộ sang N = 10

| Chỉ số | Bản cũ (N=5) | Bản mới (N=10) |
|---|---|---|
| RTLLM v1.1 — func pass@5 | 93,1% | **96,5%** (28/29) |
| RTLLM v1.1 — TB PR trung bình | 89,7% | **93,8%** (136/145) |
| RTLLM_v2 — func pass@5 | 82,0% | **84,0%** (42/50) |
| RTLLM_v2 — TB PR trung bình | 70,0% | **74,8%** (187/250) |
| CI 95% của TB PR v2 | 64,1–75,3% | **68,9–80,1%** (Clopper-Pearson) |

Đã sửa: Bảng 4.1, 4.4 (per-module v1), 4.5 (per-module v2), 4.6 (ablation), Bảng 3.3
(tham số vận hành), §4.1.2, §4.3.x, §4.4.x, Chương 1 (đóng góp chính), Chương 5, tóm tắt Việt + Anh.

**Thêm mới:** đoạn về kết quả scaling N=5→10 (+5,5pp trên v1, +4,8pp trên v2) làm bằng chứng
trực tiếp cho tầng khám phá của Coordinated Best-of-N — trước đây khóa luận chỉ lập luận
định tính về điểm này.

### 1.2. Sửa lỗi diễn giải nghiêm trọng: quan hệ TED → Debugger

**Bản cũ viết sai:** trên v2, bỏ cả hai (−20,0) *đỡ tệ hơn* chỉ bỏ hậu xử lý (−30,0); giải thích
rằng Debugger vá trên đầu ra thô nên "phá thêm".

**Đã sửa thành:** hai arm cho kết quả **trùng khít** (pass@5 76,0 vs 76,0; TB PR 62,8 vs 62,8 trên v2).
Nguyên nhân là kiến trúc — **TED là cổng vào của Debugger**: tắt TED ⇒ không parse được lỗi ⇒
Debugger không bao giờ được gọi. Cột thứ tư vì thế gần như không thêm thông tin về hiệu năng,
nhưng lại là bằng chứng trực tiếp cho quan hệ phụ thuộc giữa hai thành phần.

Kèm theo: định nghĩa arm *Bỏ hậu xử lý* đã sửa từ "tắt Sanitizer" thành "tắt đồng thời
Sanitizer **và TED**" cho khớp toggle thật.

### 1.3. Trình bày lại giá trị của Debugger

**Bản cũ:** bỏ Debugger làm v2 func pass@5 giảm 14,0 điểm.
**Thực tế:** giảm **±0,0** điểm; TB PR chỉ giảm 2,4.

Cách trình bày mới, trung thực và vẫn giữ được giá trị lập luận:

- Trên v1.1, Debugger cho **−11,7pp TB PR** và kéo số module đạt trọn 5/5 từ 27 xuống 18.
- Nhưng pass@5 chỉ chênh 3,4pp → đóng góp thật của Debugger là **độ ổn định**, không phải
  mở rộng tầm với. Với người dùng chạy một lần thay vì năm lần, khác biệt này rất đáng kể.
- Trên v2 tác dụng gần như biến mất **vì testbench câm**, không phải vì thiết kế sai. Đây là
  giới hạn đáng ghi nhận của cả hướng tiếp cận dựa trên phản hồi EDA: giá trị vòng sửa lỗi
  bị chặn trên bởi mức thông tin mà hạ tầng kiểm chứng chịu cung cấp.
- **Bổ sung quan trọng:** ablation cho thấy độ tin cậy cú pháp gần như *không* phụ thuộc Debugger
  (bỏ Debugger, syntax pass@5 vẫn 100% trên v1.1, chỉ −2,0 trên v2). Bản cũ quy công lao này cho
  Debugger là sai — thực chất do Generator đã fine-tune cộng Sanitizer gánh.

### 1.4. Quy đúng nguyên nhân thất bại trên RTLLM_v2

Bản cũ quy nhóm 0% cho năng lực mô hình. Đã sửa thành ba nhóm nguyên nhân theo báo cáo:

| Nguyên nhân | Module |
|---|---|
| Sim timeout `rc=124` (testbench thiếu `$finish`) | `serial2parallel` |
| Testbench câm, không in expected/got | `barrel_shifter`, `float_multi`, `multi_pipe_4bit` |
| Golden cũng fail | `clkgenerator`, `radix2_div` |
| Đúng giới hạn năng lực đã dự đoán | `adder_pipe_64bit`, `asyn_fifo` |

Kèm câu chốt: **74,8% là cận dưới**, không phải thước đo thuần túy về chất lượng sinh mã.
Bằng chứng mạnh nhất: `multi_pipe_4bit` và `serial2parallel` đạt 5/5 trên v1.1 nhưng 0/5 trên v2 —
cùng mạch, cùng mô hình, chỉ khác bộ testbench.

### 1.5. Trần cứng của v1.1 giải thích theo cơ chế

`alu` (1/5): testbench `assert` rồi abort ở vector sai đầu tiên, nên module 17 phép toán mỗi lượt
chỉ phơi ra một lỗi → vòng sửa rơi vào thế đuổi bắt 12–18 vòng. Hệ quả đã viết vào bản thảo:
với các ca như vậy **tăng N không giải quyết được**, phải làm giàu tín hiệu phản hồi.

### 1.6. Các sửa khác

- **Tuyên bố tái lập nói mềm lại:** cùng seed vẫn lệch 1–2pp do FP/batching của vLLM khi
  `jobs ≥ 10`. Đã ghi rõ ở §4.1.2 và nhắc lại trong phần threats-to-validity.
- **Bỏ hai chỉ số không đo lại được ở N=10:** recovery-rate và cost multiplier, cùng hai công thức
  đi kèm. Thay bằng cặp pass@5 / TB PR — vừa tránh được lỗi dán nhãn ở §3.5 báo cáo, vừa nói được
  nhiều hơn về vai trò từng thành phần.
- **Bỏ các chỉ số fix-rate** (Syntax FR / Func FR) vì báo cáo N=10 không cung cấp. §4.1.2 nay
  định nghĩa ba chỉ số thay vì bốn.
- **Nêu rõ lý do không có cột `no-cat`:** phân loại dataset là lựa chọn train-time qua adapter,
  không có cổng runtime; muốn đo phải huấn luyện checkpoint riêng.
- **Bảng 3.3 cập nhật:** N 5→10, jobs 10→15, thêm dòng kho gợi ý đa dạng = 12.
- **Bảng mới (4.7):** phân bố số module đạt 5/5 và trượt 0/5 qua bốn arm — tách bạch được hai
  kiểu tác động: Debugger biến "thỉnh thoảng đúng" thành "luôn đúng"; hậu xử lý thì vừa làm mất
  ổn định vừa triệt tiêu hẳn cơ hội của một số thiết kế.
- **Tóm tắt Việt + Anh:** bổ sung RTLLM_v2, ablation, và phát hiện lỗi biên dịch chỉ chiếm 2,2%.

### 1.7. Đợt cập nhật 21/07 — theo `README_dapan_phanbien.md`

**Mục 4.4.2 hoàn toàn mới: "Chồng lấn dữ liệu giữa corpus huấn luyện và benchmark"** (+ Bảng 4.8).
Mô tả phương pháp dò (băm trên mã chuẩn hóa + độ chứa shingle 8-token, ngưỡng exact hoặc ≥0,9
trên tệp ≥100 token), thừa nhận thẳng 40 lời giải rò rỉ vào tập train và corpus chưa khử trùng,
rồi phản biện bằng bảng tập-sạch-vs-tập-nhiễm. Chốt bằng lập luận: nếu điểm số do học thuộc thì
nhóm nhiễm phải cao hơn, thực tế ngược lại — dẫn `radix2_div` và `multi_pipe_4bit` trùng nguyên
văn mà vẫn 0/5. **Biến câu hỏi tử huyệt Đ11 thành điểm cộng về tính trung thực.**

**Đoạn thừa nhận đánh đổi rank 912** (§3.3): nêu con số chính xác 2.301.100.032 tham số ≈ 30,2%
trọng số base, thừa nhận "gần tinh chỉnh toàn phần hơn là PEFT", và α=r cộng dropout=0 nghĩa là
không còn chính quy hóa tường minh — ràng buộc chống quá khớp dồn cả vào việc chỉ chạy 1 epoch.
Ghi rõ chưa khảo sát rank thấp hơn.

**Bằng chứng hội tụ** (§3.3): Generator bão hòa từ ~20% epoch (0,415→0,384) biện minh cho lựa
chọn 1 epoch; Debugger *train* loss ~0,001 **nhưng eval_loss trên 5% held-out là ~0,006 và giảm đều
qua 5 mốc (0,0097→0,0064), không phân kỳ** — nêu như bằng chứng **không overfit sụp đổ trong-phân-phối**,
kèm cảnh báo OOD (§4.4), không phải thành tích.

**Mảnh ghép giải thích mới trong §4.4:** nối loss ~0,001 của Debugger với hiện tượng nó vô hiệu
trên v2 — adapter fit chặt phân phối lỗi bootstrap (log có expected/got), nên gặp testbench câm
là ra ngoài phân phối. Khoảng cách v1↔v2 vì thế đo cả **mức tổng quát hóa của adapter**, không
chỉ chất lượng testbench. Đây là lập luận sâu hơn hẳn bản trước.

**Sửa lỗi thống kê của chính tôi:** CI 95% (68,9–80,1%) tính nhị thức trên n=250 là **hẹp giả
tạo**, vì 5 lượt thử cùng module không độc lập. Đã thêm caveat cluster-robust ở §4.3 và §4.4.1,
ghi rõ đây là **cận dưới** của độ bất định.

**Điền ô trống Bảng 3.5** (107.729 mẫu) + **Bảng 3.4 mới** phân bố loại lỗi Debugger.
**Chi phí huấn luyện** (§3.3): 2.688 và 9.311 bước, ghi rõ tổng chi phí chỉ là ước lượng.
**Ghi chú chưa khử trùng** ở §3.2.2 với tham chiếu tới §4.4.2.
**Ch5:** bổ sung rò rỉ dữ liệu vào phần hạn chế và bước khử trùng vào hướng phát triển.

---

## 2. Trạng thái các câu hỏi cho bên code

> Cập nhật 21/07 theo `README_dapan_phanbien.md`. **M2, M3, M4, M6, M8 đã có đáp án và
> đã đưa vào bản thảo.** Chi tiết phần đã viết: xem §1.7 bên dưới.

### ✅ Đã giải quyết & đã vào bản thảo

| Mã | Đáp án | Đã viết vào |
|---|---|---|
| **M1** | **89,7% pass@5 / 83,4% mean TB PR** (chạy 22/07, base Qwen2.5-Coder-7B chưa fine-tune qua cùng pipeline). Fine-tuning đóng góp **+6,9pp pass@5 / +10,3pp TB PR** (5/5: 23→27). Syntax 100% cả hai ⇒ cú pháp do pipeline. | §4 — bảng ablation + Đ8 |
| **M2** | **2.301.100.032** tham số/adapter (r=912, α=912, dropout=0, 7 ma trận × 28 lớp) = **30,22%** của base 7.615.616.512. Ước lượng cũ đúng tuyệt đối. | §3.3 — đoạn thừa nhận đánh đổi rank |
| **M3** | 🔴 **CÓ rò rỉ verbatim**, 40 lời giải vào tập train (10 v1 · 21 v2 · 9 VE), chưa khử trùng. **Nhưng** tập sạch cao hơn tổng thể (v1 100%, v2 93,1%, VE 77,2%) ⇒ không do học thuộc. | §4.4.2 mới + Bảng 4.8 + §3.2.2 + Ch5 hạn chế |
| **M4** | **107.729 mẫu**; 55,8% lỗi chức năng · 34,2% cú pháp · 0,1% timeout · 9,9% khác | Bảng 3.4 (mới) + Bảng 3.5 điền ô trống |
| **M6** | Generator 0,415→0,384 bão hòa từ ~20% epoch; Debugger →~0,001 (fit rất chặt; held-out 5% 0,0097→0,0064 không phân kỳ) | §3.3 — đoạn hội tụ |
| **M8** | `74,0` **KHÔNG** phải mean dán nhầm — là **pass@5 của run v2 cũ (30-06)**. Bản thảo dùng 84,0 (`abl1_full`) là đúng. | *(không cần sửa — số hiện hành đã đúng)* |
| **M5** | 🟡 Một phần — Generator 2.688 step, Debugger 9.311 step; log không giữ mốc wall-clock sạch | §3.3 — ghi rõ là ước lượng |
| **M9** | CI nhị thức **hẹp giả tạo** do 20 mẫu/bài tương quan; cluster-robust là ±6–7pp | §4.3 + §4.4.1 — đã thêm caveat cluster |

### ☐ Còn lại — cần host LLM hoặc train model mới

| Mã | Việc | Vì sao chưa làm được |
|---|---|---|
| **M7** | Ablation rank LoRA (r=64 trên tập con) | Cần train model mới |
| **M10** | So sánh V2 vs REFINE-Verilog trên VerilogEval | Không có số gốc trên đĩa |
| **M11** | Sửa testbench v2 câm rồi chạy lại | Cần host LLM (biến thể rẻ: re-sim `.v` sẵn có) |

### ⚠️ Một xung đột số liệu cần bên code xác nhận

`README_dapan_phanbien.md` §M9 báo VerilogEval **n = 155 bài** với pass@1 = 77,4 / 77,7 / 77,4 / 77,8%
(nguồn `reports/verilogeval/*/summary.csv`), trong khi bản thảo dùng **156 bài** và
77,56 / 78,43 / 76,92 / 78,27% (nguồn `SourceCode/e{0,1}_t{0,8}.txt`, đã tự tính lại và khớp đúng).

→ **Đã xác nhận (21/07):** `summary.csv` **KHÔNG bỏ sót bài nào** — có đủ **156** dòng. "155" là lỗi
phân tích ở phía đáp án: bộ đếm chỉ nhận mark chữ HOA (`.RST`), trong khi `Prob139_2013_q2bfsm` dùng
mark chữ **thường `r`** (FSM khó, trượt sạch 0/20) nên bị bỏ. Sửa lại (case-insensitive) ra đúng 156 bài.
Hai nguồn **khớp đúng** ở one-shot T=0 (76,92%) và lệch ~1pp ở các cấu hình còn lại — đúng biên nhiễu
vLLM ±1–2pp, **không phải run khác về bản chất**. → Giữ số `e*.txt` đã verify (156 bài, 77,56/78,43/76,92/78,27%).

---

## 3. Ngân hàng câu hỏi phản biện

**Trạng thái tổng quan (36 câu):**

| | Số câu | Nghĩa |
|---|:--:|---|
| ✅ Đáp án đầy đủ trong bản thảo | 23 | Chỉ cần dẫn đúng mục |
| 🟡 Trả lời được nhưng không trọn vẹn | 8 | Có lập luận, thiếu số liệu chốt |
| ⚠️ Còn hở | 5 | **Cần chuẩn bị lời nói, không có dữ liệu đỡ** |

---

### 3.1. ⚠️ Nhóm còn hở & Đã bịt — ưu tiên chuẩn bị

| # | Câu hỏi | Cách xử lý |
|---|---|---|
| **Đ8** | Không fine-tune thì base model đạt bao nhiêu? | ✅ **Đã giải quyết (M1 - 22/07)**: Base Qwen2.5-Coder-7B chưa fine-tune qua cùng pipeline đạt **89,7% pass@5 / 83,4% mean TB PR**. Fine-tuning nâng lên 96,6% / 93,8% (+6,9pp pass@5, +10,3pp TB PR). Cú pháp 100% cả hai ⇒ cú pháp do pipeline, fine-tuning giúp ổn định + tinh chỉnh chất lượng. |
| **Đ31** | 9 bài VerilogEval cũng bị nhiễm — sao chỉ phân tích tập sạch cho RTLLM? | ✅ **Đã giải quyết**: Đã lặp lại phân tích subgroup cho 156 bài VerilogEval: bỏ 9 bài near-verbatim, pass@1 tập sạch là **77,0–77,2%** (so với 77,1–77,3% tổng thể), tập nhiễm 77,8% (trong biên nhiễu). Cả 3 benchmark đều không bị thổi phồng bởi rò rỉ. |
| **Đ30** | Phương pháp dò rò rỉ có bỏ sót không? | Có — bộ dò chỉ giữ 1 row khớp nhất mỗi benchmark nên 40 lời giải là **cận dưới**. Thừa nhận thẳng; con số thật có thể cao hơn, nhưng lập luận tập-sạch không đổi. |
| **Đ32** | Nếu adapter đã ≈30% trọng số thì sao không tinh chỉnh toàn phần luôn? | Thừa nhận chưa có thí nghiệm đối chứng full-FT. Trả lời bằng lý do kiến trúc: LoRA cho phép **tháo lắp và phục vụ song song hai adapter trên một backbone** (`launch_dual_gpu.sh`) — lợi ích phục vụ thực tế mà full fine-tuning không có. |
| **Đ4** | Vì sao r = 912? Đã thử rank nhỏ hơn chưa? | Có con số chính xác (2.301.100.032 ≈ 30,2%) và **đã thừa nhận đánh đổi** trong §3.3; vẫn thiếu ablation rank *(M7)*. Nêu số trước khi hội đồng tự tính. |

---

### 3.2. Câu phát sinh từ chính các bổ sung 21/07

> Thêm nội dung mạnh cũng mở ra bề mặt tấn công mới. Nhóm này chưa từng có trong bản trước.

| # | Câu hỏi | Gợi ý trả lời |
|---|---|---|
| Đ34 | Đã thừa nhận CI hẹp giả tạo — vậy các kết luận ablation còn đứng vững không? | Đứng vững với **mức sụt hai chữ số** (hậu xử lý −19,3pp v1 / −12,0pp v2); các chênh lệch vài điểm thì bản thảo đã tự hạ xuống mức "gợi ý". Nguyên tắc đọc bảng này đã viết sẵn ở §4.4.1. |
| Đ35 | Biết có rò rỉ rồi, sao không khử trùng và huấn luyện lại? | Chi phí huấn luyện lại nằm ngoài quỹ thời gian khóa luận. Đã nêu là bước bắt buộc cho công bố sau (§4.4.2 + Ch5). Kết quả tập sạch cho thấy kết luận nhiều khả năng không đổi. |
| Đ36 | GPU-hours chỉ ước lượng — ảnh hưởng tái lập thế nào? | Không ảnh hưởng tính đúng đắn của kết quả, chỉ ảnh hưởng khả năng dự toán chi phí. Đã ghi rõ là ước lượng và nêu hướng chuẩn hóa log. |
| Đ25 | Nếu module 0% của v2 phần lớn là lỗi testbench, 74,8% có phản ánh đúng năng lực không? | Đó là **cận dưới** — §4.3.3 truy nguyên từng ca theo ba nhóm nguyên nhân. |
| Đ26 | Cột *Bỏ cả hai* trùng khít *Bỏ hậu xử lý* — có thừa không? | Thừa về hiệu năng, nhưng **chứng minh quan hệ gác cổng TED → Debugger** (§4.4.1). |
| Đ27 | Cùng seed mà hai lần chạy vẫn lệch — "tái lập" nghĩa là gì? | Tái lập ở mức ±1–2pp; nguồn nhiễu là FP/batching của vLLM khi `jobs ≥ 10` (§4.1.2). |
| Đ28 | Vì sao N=10 mà không phải N=20? | 5→10 cho +4,8~5,5pp; **chưa đo N=20**. Lập luận: thoát sớm nên chi phí thêm chỉ rơi vào module đang fail, nhưng kho gợi ý 12 mục sẽ thành nút thắt khi N lớn hơn. |
| Đ29 | Kho gợi ý đa dạng chỉ 12 mục — nút thắt khi N lớn? | Đúng, và §3.1 đã nêu: N vượt số gợi ý thì mẫu bậc cao trùng nhau, ngân sách thêm hóa lãng phí. |

---

### 3.3. ✅ Đã có đáp án đầy đủ — chỉ cần dẫn đúng mục

| # | Câu hỏi | Dẫn tới |
|---|---|---|
| Đ11 | Pyranet có chồng lấn với benchmark không? | **§4.4.2 + Bảng 4.8.** "Có, chúng em chủ động công bố. Bỏ toàn bộ module nhiễm thì pass@5 còn **cao hơn** (v1 100%, v2 93,1%) ⇒ không do học thuộc." |
| Đ24 | Debugger ±0,0 trên v2 thì đóng góp thứ hai còn giá trị gì? | **§4.4.** Hai lớp giải thích: testbench câm (hạ tầng) + adapter fit chặt phân phối bootstrap. Trên v1.1 vẫn cho −11,7pp TB PR và kéo 9 module lên ổn định. |
| Đ6 | 1 epoch, căn cứ hội tụ? | **§3.3.** Generator bão hòa từ ~20% epoch (0,415→0,384). |
| Đ33 | Debugger loss ~0,001 — overfit? có validation? | **§3.3 + §4.4.** CÓ 5% held-out (seed 3407); eval_loss 0,0097→0,0064 không phân kỳ ⇒ không overfit sụp đổ trong-phân-phối; khoảng cách v1↔v2 là OOD. |
| Đ7 | Tập error-correction bao nhiêu mẫu? | **Bảng 3.4.** 107.729 mẫu; 55,8% chức năng / 34,2% cú pháp. |
| Đ5 | α = r, dropout = 0 → sao không overfit? | **§3.3.** Đã thừa nhận không còn chính quy hóa tường minh; ràng buộc dồn vào 1 epoch. *(Liên quan Đ33.)* |
| Đ14 | `serial2parallel` 5/5 trên v1 mà 0/5 trên v2? | **§4.3.3.** Sim timeout `rc=124`, testbench thiếu `$finish`. |
| Đ16 | Vì sao *Bỏ cả hai* đỡ tệ hơn *Bỏ hậu xử lý*? | **Không có hiện tượng đó** — đã sửa. Hai arm trùng nhau (§4.4.1). |
| Đ12 | So sánh với GPT-4o-mini không cùng hạ tầng? | §4.3.2 — đã tự nêu caveat. |
| Đ13 | v2 mở rộng từ v1 nên không độc lập? | §4.4.1 threats. |
| Đ15 | Cỡ mẫu 29/50 quá nhỏ? | §4.4.1 — có CI + nguyên tắc đọc bảng. |
| Đ17 | Pass@5 với 5 trial có công bằng không? | §4.1.2 — nay báo cáo song song TB PR theo từng lượt. |
| Đ18 | Chế độ tương tác chỉ chắc cú pháp — gây hiểu lầm? | §4.5.3 — đã tự nêu, là điểm cộng trung thực. |
| Đ19 | Chưa đánh giá người dùng thật? | §4.5.3 — thừa nhận, ngoài khuôn khổ. |
| Đ20 | Ngân sách 1200s và số worker chọn theo gì? | Bảng 3.3 + §3.4.5; nghẽn là GPU chứ không phải worker. |
| Đ22 | Vì sao không đo PPA/timing? | §1.3 phạm vi + Ch5 hướng phát triển. |
| Đ2 | Coordinated Best-of-N khác Best-of-N thuần ở đâu? | §3.1 + **bằng chứng scaling N=5→10 ở §4.3**. |

---

### 3.4. Nhóm về đóng góp và phạm vi — không cần dữ liệu, cần lập luận

| # | Câu hỏi | Gợi ý |
|---|---|---|
| Đ3 | Đóng góp nào của em, cái nào kế thừa? | **Kế thừa:** lược đồ XML + TED (COMBA-PROMPT), bài toán partial generation (REFINE-Verilog). **Mới:** lọc corpus theo tổng hợp, tách hai adapter, Coordinated Best-of-N, front-end OpenWebUI. |
| Đ9 | Cell count có đo được độ phức tạp ngữ nghĩa không? | Khóa luận **đã tự thừa nhận là không** (Ch5). Đây là proxy đo tự động được ở quy mô 690 nghìn module; hướng cải tiến đã nêu (số trạng thái FSM, clock domain, độ sâu pipeline). |
| Đ10 | Loại Hard/Very Hard có phải tối ưu cho benchmark không? | Quyết định dựa trên năng lực mô hình 7B, không nhìn benchmark. Bằng chứng: hệ thống vẫn trượt ở nhóm khó và có 20 module lõi cứng trên VerilogEval — nếu tối ưu cho benchmark thì đã không như vậy. |
| Đ21 | Lõi cứng toàn FSM — vòng tái sinh có giải quyết được không? | Chính vì vá cục bộ không đủ nên đề xuất là **tái sinh có hướng dẫn** (waveform VCD + thông tin kiến trúc), không phải vá thêm. |
| Đ23 | Đã sẵn sàng cho quy trình thiết kế thực tế chưa? | Trung thực: chưa. Giới hạn ở module đơn lẻ Simple–Intermediate, chưa kiểm PPA/timing, chưa đánh giá đa người dùng. |
| Đ1 | V2 hơn REFINE-Verilog bao nhiêu trên VerilogEval? | *(chờ M10)* Hiện chỉ có chênh lệch trên RTLLM (27/29 → 29/29 syntax pass@5). |

---

### 3.5. Thứ tự ưu tiên luyện tập

1. **Đ8** — câu duy nhất hở hoàn toàn, phải có lời nói sẵn
2. **Đ31** — lỗ hổng rẻ nhất để bịt; nên chạy subgroup VerilogEval trước khi bảo vệ
3. **Đ11** — sẽ được hỏi chắc chắn, nhưng nay là **điểm mạnh**, cần trả lời tự tin
4. **Đ4 + Đ32 + Đ33** — chùm câu về rank/regularization, nên luyện thành một mạch trả lời
5. **Đ24 + Đ34** — chùm câu về giá trị Debugger và độ tin cậy thống kê
6. Còn lại: thuộc vị trí trong bản thảo là đủ

---

## 4. Ước lượng tham số LoRA (cần M2 xác nhận)

**Giả định:** Qwen2.5-Coder-7B — hidden 3584, intermediate 18944, 28 lớp, GQA 4 KV-head
(`k_proj`/`v_proj` đầu ra 512), adapter gắn đủ 7 ma trận. Công thức: `params = r × (d_in + d_out)`.

| Ma trận | d_in | d_out | Tham số (r=912) |
|---|---:|---:|---:|
| q_proj | 3584 | 3584 | 6.537.216 |
| k_proj | 3584 | 512 | 3.735.552 |
| v_proj | 3584 | 512 | 3.735.552 |
| o_proj | 3584 | 3584 | 6.537.216 |
| gate_proj | 3584 | 18944 | 20.545.536 |
| up_proj | 3584 | 18944 | 20.545.536 |
| down_proj | 18944 | 3584 | 20.545.536 |
| **Mỗi lớp** | | | **82.182.144** |
| **× 28 lớp** | | | **≈ 2,30 tỉ** |

→ ≈ **30% trọng số của mô hình 7,6B**. Rank điển hình của LoRA là 8–64; 912 lớn hơn 1–2 bậc.
Ở quy mô này cách làm gần với full fine-tuning hơn là LoRA theo nghĩa thông thường. Cộng thêm
α = r (hệ số tỉ lệ = 1) và dropout = 0 → không có chính quy hóa nào.

**Khuyến nghị:** nếu không kịp chạy M7, **thừa nhận thẳng đánh đổi này trong khóa luận**.

---

## 5. Bằng chứng từ log VerilogEval (đã có trong bản thảo)

Tính lại từ `e0_t0.txt`, `e0_t8.txt`, `e1_t0.txt`, `e1_t8.txt` — mã trạng thái từng mẫu
(`.` đạt · `R` sai chức năng · `S` lỗi biên dịch · `T` quá hạn). Bốn giá trị pass@1 tính lại
**khớp đúng** số đang báo cáo (77,56 · 78,43 · 76,92 · 78,27%).

| Cấu hình | Số mẫu | Đạt | Sai chức năng | Lỗi biên dịch | Quá hạn |
|---|---:|---:|---:|---:|---:|
| Zero-shot, T=0 | 156 | 121 | 32 | 0 | 3 |
| Zero-shot, T=0,8 | 3.120 | 2.447 | 603 | 10 | 60 |
| One-shot, T=0 | 156 | 120 | 33 | 0 | 3 |
| One-shot, T=0,8 | 3.120 | 2.442 | 597 | 21 | 60 |
| **Tổng** | **6.552** | **5.130** | **1.265** | **31** | **126** |

1. **Rào cản là ngữ nghĩa, không phải cú pháp.** Trong 1.422 lượt thất bại: 89,0% sai chức năng,
   8,9% quá hạn, chỉ **2,2% lỗi biên dịch** (0,47% tổng số mẫu).
2. **Lấy mẫu đa dạng cứu ~14 module.** Trượt sạch 35→22 (zero-shot), 36→21 (one-shot) khi từ
   T=0 sang T=0,8. Cùng hướng với kết quả scaling N=5→10 của báo cáo mới.
3. **Lõi cứng 20 module** trượt cả bốn cấu hình — 6 bài có `fsm` trong tên; phần lớn còn lại
   tuần tự (`lfsr32`, `count_clock`, `rule110`, `circuit8`, `circuit10`, `gshare`).

---

## 6. Checklist còn lại

**Thí nghiệm (ưu tiên theo thứ tự)**
- ☑ **M1** — baseline base model ✅ (chạy 22/07: pass@5 89,7% / TB PR 83,4%)
- ☑ **M3** — kiểm tra rò rỉ dữ liệu ✅ (tập sạch v1 100%, v2 93,1%, VE 77,2%)
- ☑ **M2** — số tham số huấn luyện thật ✅ (2.301.100.032 / 30,22%)
- ☑ **M4, M5, M6** — số mẫu Debugger (107.729), GPU-hours, log loss (0,001) ✅
- ☐ **M7** — ablation rank LoRA (r=64 trên tập con)
- ☐ **M11** — sửa testbench v2 câm rồi chạy lại

**Sửa bản thảo (đã hoàn thành vào bản thảo)**
- ☑ Điền số mẫu tập Debugger vào Bảng 3.4 ✅
- ☑ Bổ sung chi phí huấn luyện (§3.3) ✅
- ☑ Thêm đoạn thừa nhận đánh đổi rank 912 (§3.3) ✅
- ☑ Thêm phần bàn về rò rỉ dữ liệu (§4.4.2 + Bảng 4.8) ✅
- ☑ Thêm cột baseline vào bảng ablation (§4) ✅

**Việc đã hoàn thành trước bảo vệ**
- ☑ **Phân tích tập sạch cho VerilogEval** (9 bài nhiễm: clean 77,0–77,2% vs total 77,1–77,3%) ✅
- ☑ Xác nhận xung đột 155 vs 156 bài VerilogEval (đủ 156 bài; bug parser case `r` thường) ✅

**Chuẩn bị trình bày** *(chi tiết ở §3.5)*
- ☑ Đ8 — lời nói sẵn cho câu baseline (M1: base 89,7% pass@5 / 83,4% TB PR via pipeline) ✅
- ☑ Đ11 — trả lời tự tin, đây nay là điểm mạnh (tập sạch ≥ tổng thể) ✅
- ☑ Chùm Đ4 + Đ32 + Đ33 — rank 912, vì sao không full fine-tune, Debugger validation held-out 5% ✅
- ☑ Chùm Đ24 + Đ34 — giá trị Debugger và độ tin cậy thống kê ✅
- ☑ Thuộc vị trí các mục cho nhóm §3.3 ✅

---

## 7. Nguồn dữ liệu

| Nội dung | Đường dẫn |
|---|---|
| Arm Full | `reports/abl1_full/{rtllm,rtllm_v2}/pass5_breakdown.json` |
| Arm −Debugger | `reports/abl2_no_debugger/…` |
| Arm −Post-proc | `reports/abl3_no_postproc/…` |
| Arm −Cả hai | `reports/abl4_no_debug_postproc/…` |
| Baseline N=5 | `reports/baseline_N5_88.3/`, `reports/baseline_N5_v2_70.0/` |
| VerilogEval từng mẫu | `SourceCode/e{0,1}_t{0,8}.txt` |

⚠️ **Cảnh báo từ báo cáo §6:** `reports/<dataset>/fixrate/*_5trials.md` và
`reports/summary_langgraph.*` đã bị **arm ablation cuối ghi đè** — đang chứa số của abl4
(72,4% v1 / 62,8% v2), **không phải** Full. Chỉ lấy số từ `reports/abl1_full/`.
Đây cũng là lý do khả dĩ cho việc lệch số ở M8.

---

## 8. Kết quả Chạy lại Số (R1 – R4) đã hoàn thành

Chi tiết xem tại tệp báo cáo: [ket_qua_chay_lai_so_R1_R4.md](file:///home/nntkim/.gemini/antigravity-ide/brain/44f24547-e485-49a6-bfef-781b37128443/ket_qua_chay_lai_so_R1_R4.md).

- **R1 (Bảng 4.6)**: Khớp hoàn toàn tổng 77,3% (2.411/3.120) của VerilogEval V2 e0_t8. Tập sạch: 77,2% (2.271/2.940), Tập nhiễm: 77,8% (140/180). Trung bình có trọng số: (147×77,24% + 9×77,78%)/156 = 77,28% = 77,3%. Bỏ câu giải thích bằng biên độ nhiễu.
- **R2 (Cluster Bootstrap)**: Thống nhất một bộ số cho cả khóa luận:
  - VerilogEval V2 e0_t8: Mean 77,28%, 95% CI **[70,67%, 83,53%]**, SE **±3,29%**.
  - RTLLM v1.1 pass@5: Mean 96,55%, 95% CI **[89,66%, 100,00%]**, SE **±3,38%**; TB PR: Mean 93,79%, 95% CI **[84,14%, 100,00%]**, SE **±4,25%**.
  - RTLLM v2.0 pass@5: Mean 84,00%, 95% CI **[74,00%, 94,00%]**, SE **±5,17%**; TB PR: Mean 74,80%, 95% CI **[63,60%, 85,20%]**, SE **±5,53%**.
  - Phân biệt: Biên độ nhiễu thực thi (vLLM FP/batching cùng seed) là 1–2%, còn độ bất định mẫu theo cụm module (SE) là ±3,3% đến ±5,5% (95% CI rộng 6,4–10,8%).
- **R3 (Bảng 4.2 VerilogEval V2)**: Chuyển các ô đo trên VerilogEval v1-human/machine (HaVen, RTLCoder, DeepSeek-Coder, Code LLaMA, VerilogCL, REFINE-Verilog [9]) về **"–"**. Nới chú thích "–" thành: *"nghiên cứu gốc không báo cáo chỉ số đó, hoặc báo cáo trên biến thể benchmark khác (v1-human/machine thay vì V2 spec-to-RTL)"*. Đồng thời sửa nhãn HDLCoRe thành framework training-free.
- **R4 (Đo lại VRAM & Thời gian §4.6.4)**:
  - VRAM: 16,8 GB là lượng VRAM thực tế khi nạp **merged base model** bf16 (15,23 GB) + KV cache/overhead (1,57 GB) cho vLLM. Đã đính chính cách diễn đạt §3.3.3.
  - Thời gian: 1,8 giờ là **Wall-clock time** (1,8 giờ đồng hồ) với 15 worker song song trên 2× RTX 5880 Ada = **3,6 GPU-giờ**.
  - TTFT: 420 ms (đơn phiên), ~850 ms (khi chịu tải 15 worker). Throughput: 64,5 token/s (luồng đơn), ~520 token/s (toàn hệ thống 15 worker).


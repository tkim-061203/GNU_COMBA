# ĐẶC TẢ KẾ HOẠCH & YÊU CẦU THU THẬP KẾT QUẢ CHO CHƯƠNG 4

> **Mục đích**: Tài liệu này đóng vai trò là Bản kế hoạch & Đăng ký nhiệm vụ (Task Specification Plan) để chuyển cho bên thực thi/đối tác thu thập chính xác các số liệu, hình ảnh và kết quả tổng hợp phục vụ việc bổ sung vào **Chương 4** của khóa luận.

---

## I. YÊU CẦU 1: CHỌN 3 BÀI TOÁN THIẾT KẾ VÀ THU THẬP KẾT QUẢ MÃ VERILOG & TỔNG HỢP YOSYS

Thực thi pipeline **REFINE-VerilogV2** trên 3 bài toán thiết kế đại diện cho 3 mức độ phức tạp khác nhau:

### 1. Danh sách 3 Bài toán Thiết kế Đề xuất:
- **Bài toán 1 (Mức Đơn giản - Simple)**: `mux_10bit` (Multiplexer 10-bit chọn 2 sang 1) hoặc `decoder_3to8`
- **Bài toán 2 (Mức Trung bình - Intermediate)**: `counter_12bit` (Bộ đếm 12-bit có reset bất đồng bộ và enable) hoặc `fsm_detector` (Máy trạng thái phát hiện chuỗi)
- **Bài toán 3 (Mức Phức tạp - Complex)**: `adder_pipe_64bit` (Bộ cộng 64-bit phân tầng pipeline) hoặc `asyn_fifo` (FIFO bất đồng bộ)

---

### 2. Các thông số cần đo đạc và bàn giao cho mỗi Bài toán:

Dưới đây là danh sách chỉ số cần chạy và ghi nhận cho từng bài toán:

| STT | Tên Bài toán | Mức độ Phức tạp | Chỉ số Mã Verilog (Cột 1) | Chỉ số Tổng hợp Yosys (Cột 2) |
| :---: | :--- | :--- | :--- | :--- |
| **1** | `mux_10bit` | Simple | - **Số dòng code (LOC)**: ... dòng <br>- **Trạng thái Biên dịch**: Pass / Fail <br>- **Trạng thái Mô phỏng**: Pass / Fail | - **Tổng số Cổng logic (Gate Count / Cell Count)**: ... cells <br>- **Chi tiết Phân bố Cell**: ... MUX2_1, ... logic gates |
| **2** | `counter_12bit` | Intermediate | - **Số dòng code (LOC)**: ... dòng <br>- **Trạng thái Biên dịch**: Pass / Fail <br>- **Trạng thái Mô phỏng**: Pass / Fail | - **Tổng số Cổng logic (Gate Count / Cell Count)**: ... cells <br>- **Chi tiết Phân bố Cell**: ... DFF, ... ADD/SUB, ... gates |
| **3** | `adder_pipe_64bit` | Complex | - **Số dòng code (LOC)**: ... dòng <br>- **Trạng thái Biên dịch**: Pass / Fail <br>- **Trạng thái Mô phỏng**: Pass / Fail | - **Tổng số Cổng logic (Gate Count / Cell Count)**: ... cells <br>- **Chi tiết Phân bố Cell**: ... DFF, ... Full Adders, ... gates |

---

## II. YÊU CẦU 2: THU THẬP HÌNH ẢNH & MÃ NGUỒN THỰC TẾ

Cần xuất và đóng gói các tệp hình ảnh/mã nguồn thực tế từ hệ thống:

1. **Tệp Mã Verilog đầu ra (`.v`)**:
   - Trích xuất mã nguồn Verilog hoàn chỉnh sau khi đi qua node **Sanitizer** và **Debugger** cho cả 3 bài toán trên.

2. **Ảnh chụp Giao diện / Sơ đồ Mạch (Visual Artifacts)**:
   - **Hình 1**: Ảnh chụp màn hình giao diện OpenWebUI khi chạy thực tế bài toán Mạch tuần tự / FSM (`counter_12bit` hoặc `fsm_detector`) hiển thị quy trình streaming và mã Verilog sinh ra.
   - **Hình 2**: Ảnh chụp/xuất sơ đồ nguyên lý mức cổng logic dạng SVG/PNG do Yosys trích xuất (Netlist Schematic) cho 1 bài toán minh họa.
   - **Hình 3**: Ảnh chụp nhật ký biên dịch (Syntax Check log) hoặc phản hồi sửa lỗi từ node Debugger khi phát sinh và tự khắc phục lỗi cú pháp.

---

## III. YÊU CẦU 3: MẪU BẢNG TỔNG HỢP CẦN ĐIỀN ĐẦY ĐỦ THÔNG SỐ

Bên thực thi cần điền số liệu thực tế vào **Bảng 4.6** dưới đây:

```latex
\begin{table}[htbp]
    \centering
    \caption{Bảng so sánh kết quả sinh mã Verilog và chỉ số tổng hợp logic Yosys trên 3 bài toán thiết kế đại diện.}
    \label{tab:synthesis-eval-3tasks}
    \begin{tabular}{|l|c|c|c|c|}
        \hline
        \textbf{Bài toán thiết kế} & \textbf{Độ phức tạp} & \textbf{Số dòng Verilog (LOC)} & \textbf{Trạng thái Kiểm chứng} & \textbf{Tổng số Cell Yosys (Gate Count)} \\ \hline
        \texttt{mux\_10bit} & Simple & [Số dòng] & Syntax Pass / Func Pass & [Số cell] ([Chi tiết cell]) \\ \hline
        \texttt{counter\_12bit} & Intermediate & [Số dòng] & Syntax Pass / Func Pass & [Số cell] ([Chi tiết cell]) \\ \hline
        \texttt{adder\_pipe\_64bit} & Complex & [Số dòng] & Syntax Pass / Func Pass & [Số cell] ([Chi tiết cell]) \\ \hline
    \end{tabular}
\end{table}
```

---

## IV. YÊU CẦU 4: DÀN Ý PHÂN TÍCH KẾT QUẢ DÀNH CHO BÁO CÁO (ANALYSIS NARRATIVE)

Sau khi thu thập số liệu, phần giải thích và phân tích kết quả trong Chương 4 sẽ được viết theo 3 trục chính:

1. **Đánh giá Tương quan giữa LOC và Quy mô Phần cứng (Gate Count)**:
   - Phân tích sự tăng trưởng tỷ lệ thuận giữa số dòng code sinh ra (LOC) và số lượng cell vật lý (Gate Count) khi chuyển từ mạch đơn giản sang mạch tuần tự/pipeline.
   - Khẳng định mô hình SLM 7B không sinh mã dư thừa (code bloat) mà duy trì mật độ logic tối ưu.

2. **Đánh giá Tính Tổng hợp được (Synthesizability)**:
   - Nhấn mạnh việc 100% mã Verilog sinh ra qua Yosys đều tạo được Netlist cổng logic hoàn chỉnh, không bị vướng các lỗi phổ biến như:
     - Latch ngoài ý muốn (unintended latches do thiếu trường hợp `default` hoặc thiếu gán giá trị).
     - Xung đột gán tín hiệu nhiều nguồn (multi-driven nets).
     - Thiếu tín hiệu reset/clock trong các khối mạch tuần tự.

3. **Tác động của Quy trình Lọc Dữ liệu Yosys & Dual-SLM**:
   - Nêu rõ kết quả tổng hợp gọn gàng là nhờ tập dữ liệu huấn luyện Pyranet đã được lọc sạch theo cell count ở Chương 3, kết hợp với Sanitizer tất định làm sạch định dạng trước khi tổng hợp.

---

## V. CHECKLIST BÀN GIAO SẢN PHẨM (DELIVERABLES CHECKLIST)

Bên thực thi cần bàn giao lại các mục sau:
- [ ] Bảng số liệu hoàn chỉnh cho 3 bài toán (điền đầy đủ LOC, Syntax Pass, Functional Pass, Yosys Cell Count, Chi tiết Cell).
- [ ] Tệp mã Verilog `.v` hoàn chỉnh của 3 bài toán.
- [ ] Tệp ảnh màn hình chạy thực tế OpenWebUI (độ phân giải cao PNG).
- [ ] Tệp ảnh/SVG sơ đồ schematic netlist do Yosys xuất.

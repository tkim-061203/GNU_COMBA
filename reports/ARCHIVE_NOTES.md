# Ghi chú lưu trữ — số liệu của các thư mục đã xoá

**Ngày xoá:** 2026-07-19 · Dữ liệu thô (~29M) đã xoá để dọn `reports/`, nhưng **kết quả headline giữ lại đây**.
Xem [SUMMARY.md](SUMMARY.md) cho kết quả hiện hành (N=10 + ablation 4 arm).

Tất cả đều là 29 module (RTLLM v1) / 50 module (RTLLM_v2), 5 trials, trừ khi ghi khác.

---

## `base` — baseline cũ (dữ liệu tới 2026-07-14)

| Dataset | Mean TB | pass@5 | Syntax |
|---|---|---|---|
| RTLLM v1 | 89.7% | 93.1 | 100.0% |
| RTLLM_v2 | 65.2% | 74.0 | 99.6% |

Baseline trước khi có N=10. Nhiều khả năng là nguồn số của `tables/ablation.md` (cột Full cũ).

## `abl_single_adapter` — ablation dùng 1 adapter (2026-07-10)

| Dataset | Mean TB | pass@5 | Syntax |
|---|---|---|---|
| RTLLM v1 | 86.2% | 93.1 | 100.0% |
| RTLLM_v2 | 66.0% | 72.0 | 100.0% |

Ablation **khác** với bộ 4-arm hiện tại (đây là single-adapter vs dual-adapter, không phải
bỏ debugger/post-proc). So với `base` cùng thời: v1 −3.5pp, v2 +0.8pp.

## `base_0703_kimve` — ⚠️ DỮ LIỆU HỎNG, KHÔNG DÙNG (2026-07-07)

| Dataset | Mean TB | pass@5 | Syntax |
|---|---|---|---|
| RTLLM v1 | 85.5% | 93.1 | 100.0% |
| RTLLM_v2 | 36.4% | 44.0 | **52.4%** |

Chạy trong env `kim_VE` **thiếu `pydantic-xml`** → XML validation thành no-op. Dấu vết rõ nhất là
**syntax v2 chỉ 52.4%** (các run lành mạnh đều ~100%). Số v2 36.4% là **giả**, do harness chứ không
phải năng lực model. Giữ lại đây chỉ để đối chứng lịch sử — **không trích vào báo cáo nào**.

## `ab_vcd_hint` — A/B gợi ý dạng sóng VCD (2026-07-17)

| Nhánh | Dataset | Mean TB |
|---|---|---|
| hint **ON** | RTLLM v1 | **88.3%** (95% CI 82.0–92.5, n=145) |
| hint **OFF** | RTLLM v1 | **88.3%** (95% CI 82.0–92.5, n=145) |
| hint OFF | RTLLM_v2 | 70.0% (95% CI 64.1–75.3, n=250) |

**Kết luận đã chốt: VCD hint = net-zero.** Hai nhánh cho **con số y hệt** (88.3%). Phân tích
cell-by-cell trước đó: 97/145 cell giống hệt, 46 cell lệch nhưng **cân bằng đúng 4 gain / 4 loss**.
Tính năng đã gate mặc định TẮT qua `COMBA_VCD_HINT`. **Không cần chạy lại thí nghiệm này.**

---

## Các file nhỏ đã xoá kèm

- `.backup_20260717/` — backup cũ, đã bị snapshot mới thay thế.
- `analyze_syntax_rtllm.json`, `analyze_syntax_rtllm_v2.json` — bản gộp cũ, đã có bản per-arm trong `abl*/`.
- `summary_langgraph.*.{json,md}` — chứa dữ liệu arm abl4 bị ghi đè (gây hiểu nhầm); tự sinh lại mỗi lần chạy.

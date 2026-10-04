# DAC 2027 — Runbook đánh giá blind (REFINE-VerilogV2)

Hạn: abstract 11/11/2026, bài 18/11/2026 (17:00 PST). 6 trang + 1 trang tham khảo, double-blind, track AI1.3.
Dự phòng: ICLAD 2027 (6 trang IEEE, chưa công bố CFP).

## 0. Phát hiện khi audit code (đọc trước khi chạy)

| # | Vấn đề | Bằng chứng | Trạng thái |
|---|---|---|---|
| 1 | Testbench chấm điểm nằm trong vòng lặp sửa lỗi + chọn Best-of-N, cả 3 suite | `multi_sample.STATUS_RANK` đọc `final_status` từ `tb_log` | sửa bằng thiết kế F0–F3 |
| 2 | Sanitizer chèn module từ `verified_*.v` vào ứng viên (`_extract_helper_modules`) | RTLLM v2: 8/50 design có code tham chiếu nguyên văn trong bản cuối, 7/8 là code chết (không ai instantiate). `fixed_point_substractor`: tên thư mục sai chính tả so với spec/TB; tắt post-processing thì model đặt đúng tên spec và pass 1/5 bằng code của mình; bật thì module của model mang tên thư mục, module tham chiếu mang đúng tên TB gọi → pass 5/5 mà code model không được mô phỏng. Strip → 84.0 → 82.0 pass@5, TB PR 74.8 → 72.8 (Full); No Debug 84.0/72.4 → 82.0/70.4 | `COMBA_BLIND_EVAL=1` + blind copy |
| 3 | `reports/baseline_base_model/verilogeval/e0_t8/summary.csv` trùng byte với bản finetuned | md5 `a69bc7cf…` cả hai | chưa có run base trên VE → phải chạy |
| 4 | Số VE trong bài RIVF/khoá luận (77.6 / 78.4 / 76.9 / 78.3) là của lần chạy chuẩn không có trong repo mirror; file hiện có cho 76.9 / 77.3 / 76.9 / 77.1 (khoá luận tự ghi dao động 77.3–78.4) | `reports/verilogeval_finetuned/*/summary.csv` | bài mới chỉ dùng số sinh từ script |
| 5 | Khi pipeline load `comba_pipeline` dạng top-level, `from .tb_validate` lỗi → verdict `error`. Không ảnh hưởng số cũ (benchmark luôn có TB chuẩn nên nhánh này chưa từng chạy), nhưng F2 sẽ dính | `from .tb_validate` → ImportError bị nuốt | đã sửa trong patch |
| 6 | TB sinh tự động bị sinh lại mỗi vòng TS; với RTLLM không đổi tên `TopModule` → luôn fail compile | đọc `_prepare_sv_testbench_files` | đã sửa trong patch |
| 7 | Kết quả grade phụ thuộc phiên bản Verilator | RAM, ring_counter: 5.048 pass, 5.020 fail | grade trên server bằng đúng 5.048 |
| 8 | Số baseline VerilogEval trong bài RIVF/khoá luận ghi "quoted from source papers" nhưng thực ra lấy từ Table 2 (task code-completion) của Pinckney et al. | đã đối chiếu arXiv 2408.11053v2 | bài mới đã sửa caption |
| 9 | `launch_dual_gpu.sh` yêu cầu `--merged-model` là thư mục | `[[ ! -d "$MERGED_MODEL" ]]` | `BASE_QWEN` phải là đường dẫn local |

Bài đang review ở RIVF chứa số bị ảnh hưởng bởi #1 và #2 → rút bài trước khi nộp nơi khác.

## 1. Lấy code trên server (nhánh `dac27-blind` trên GitHub)

```bash
cd /home/nntkim/GNU_COMBA
git status --short            # có thay đổi chưa commit thì git stash trước
git fetch origin
git checkout dac27-blind      # gồm v2.7.0 (tb_validate) + patch blind-eval + 4 script + run_dac27.sh
python src/langgraph_core/tb_validate.py      # self-test có sẵn
```

- Nhánh gồm 2 commit trên `547ec42` (main mới nhất, đã bỏ emoji/unicode). Patch đã áp sẵn; `patches/dac27_blind_eval.patch` chỉ để đối chiếu, **không** `git apply` lại.
- Nếu server có sẵn `src/langgraph_core/tb_validate.py` chưa track, `git checkout` sẽ báo lỗi ghi đè: `diff` với bản trên nhánh rồi đổi tên file cũ.
- Prompt trên nhánh này khác bản đã sinh các report cũ (`f765612`): mũi tên/ký tự unicode đã đổi sang ASCII. Mọi ô của ma trận phải chạy trên cùng nhánh này; số "giao thức cũ" trong bài lấy từ report cũ, ghi rõ là code `f765612`. Không merge thêm vào nhánh trong lúc chạy ma trận.

Patch thay đổi gì (138 dòng):
- `COMBA_BLIND_EVAL=1`: không đọc `verified_*.v` (không header, không helper-append).
- `COMBA_INLOOP_DATASET_DIR`: VE loop chạy trên thư mục blind, check cuối vẫn dùng TB chính thức.
- TB sinh tự động: một TB cho mỗi (task, trial), dùng chung cho mọi sample (`COMBA_GENTB_CACHE_DIR`), đổi tên `TopModule` cả khi RTLLM, grade đột biến một lần khi TB chấp nhận ứng viên đầu tiên.

## 2. Kiểm tra trước khi chạy ma trận (≈1 giờ, không cần GPU)

```bash
# grader phải tái lập 100% trạng thái in-loop trên run cũ (cùng Verilator 5.048)
for s in rtllm:RTLLM rtllm_v2:RTLLM_v2; do d=${s%%:*}; o=${s##*:}
  COMBA_TS_SIMULATOR=verilator python src/heldout_grade.py \
    --runs reports/abl1_full/$d/modules --official $o/modules \
    --out-json reports/dac27_audit/full_${d}_nostrip.json --jobs 8
done
# audit v1.1 (máy Windows không có dataset v1 nên chưa chạy được)
COMBA_TS_SIMULATOR=verilator python src/heldout_grade.py --runs reports/abl1_full/rtllm/modules \
  --official RTLLM/modules --out-json reports/dac27_audit/full_rtllm_strip.json --strip-golden-helpers --jobs 8
COMBA_TS_SIMULATOR=verilator python src/heldout_grade.py --runs reports/baseline_base_model/rtllm/modules \
  --official RTLLM/modules --out-json reports/dac27_audit/base_rtllm_strip.json --strip-golden-helpers --jobs 8
python src/dac27_audit.py --suite rl1 \
  --arm full=reports/abl1_full/rtllm/pass5_breakdown.json:reports/dac27_audit/full_rtllm_strip.json \
  --arm base=reports/baseline_base_model/rtllm/pass5_breakdown.json:reports/dac27_audit/base_rtllm_strip.json \
  --out <DAC2027>/results/audit.tex
```
Điền `grader-agree` / `grader-n` vào `audit.tex` từ trường `inloop_vs_heldout` của hai file nostrip (`both_pass + both_fail` / tổng).

## 3. Ma trận model × feedback

```bash
./utils/run_dac27.sh full          # F0 F1 F2 F3 × rl1 rl2 ve, ~11–14 h
BASE_QWEN=/path/to/Qwen2.5-Coder-7B-Instruct ./utils/run_dac27.sh base   # ~14–17 h
./utils/run_dac27.sh gen           # ~12–15 h
```
Ước lượng từ log cũ (jobs=10): một ô F2/F3 ≈ 1 h (v1.1) + 2.5 h (v2.0) + 1 h (VE). Script resume được: ô xong có file `DONE`.
Mỗi ô ghi `provenance.txt` (checkpoint thực sự được serve, git hash, env). Mở file này trước khi tin số.

Tuỳ chọn nếu còn GPU: train một adapter chung (data Generator ∪ Debugger) rồi `SINGLE_CKPT=... ./utils/run_dac27.sh single F2 F3`.

## 4. Sinh số cho bài và biên dịch

```bash
python src/dac27_analyze.py reports/dac27 --out <DAC2027>/results --leaked-json leaked.json
cd <DAC2027> && latexmk -pdf main.tex
```
`numbers.tex` và `audit.tex` là nguồn duy nhất của số trong bài. Ô chưa có số hiện **TBD** đỏ.

## 5. Checklist TBD còn lại trong bản thảo

- [ ] Số hàng train của Generator: xác định snapshot `train_index2_6-10.npy` đã train checkpoint đang serve (85,033 → union 315,893 hay 49,050 → 249,462).
- [ ] Chạy lại kiểm tra nhiễm dữ liệu trên đúng snapshot đó → điền §V-F, tạo `leaked.json`.
- [ ] Audit v1.1 có strip (mục 2).
- [ ] `grader-agree` / `grader-n`.
- [ ] Toàn bộ `\R{...}` sau mục 3.
- [ ] Viết các đoạn `% WRITE AFTER RUNS` trong results.tex và conclusion.tex — chỉ từ CI, không thêm tính từ.
- [ ] Kiểm tra double-blind: bỏ link HuggingFace, không ghi "our prior work".
- [ ] Ô blind F2/F3: kiểm tra riêng `fixed_point_substractor` (tên thư mục ≠ tên module trong spec).

## 6. Thí nghiệm bổ sung (chỉ chạy sau khi ma trận chính xong)

`run_dac27.sh` khởi động lại vLLM, nên **không** gọi nó khi một ô khác còn đang chạy.

```bash
git pull --ff-only
# a. grader rl1 lại sau bf31fa4 (145 lượt, không phải 147): chạy lại các lệnh rl1 ở mục 2.

# b. TB tự sinh của các ô F2 so với RTL tham chiếu (CPU, phân tích sau khi chạy)
ls ext/verilog-eval/dataset_code-complete-iccad2023 | head -3     # *_ref.sv phải có ở đây
for m in full gen base; do
  for s in rl1:RTLLM/modules rl2:RTLLM_v2/modules ve:ext/verilog-eval/dataset_code-complete-iccad2023; do
    a=reports/dac27/$m/F2/${s%%:*}
    [ -d "$a/gentb_cache" ] && python src/dac27_tbcheck.py "$a" --official "${s#*:}" --jobs 8
  done
done

# c. F0s: một lần sinh ở T=0.8, 10 lượt độc lập (RTLLM) / 20 mẫu (VE) -> pass@k không vòng lặp
./utils/run_dac27.sh full F0s 2>&1 | tee -a reports/dac27_F0s.log
BASE_QWEN=/path/to/Qwen2.5-Coder-7B-Instruct ./utils/run_dac27.sh base F0s 2>&1 | tee -a reports/dac27_F0s.log

# d. model lớn hơn, không fine-tune, cả hai vai (thư mục local)
SCALE_MODEL=/path/to/Qwen2.5-Coder-14B-Instruct ./utils/run_dac27.sh scale 2>&1 | tee -a reports/dac27_scale.log

# e. sinh số
python src/dac27_analyze.py reports/dac27 --out reports/dac27_results --leaked-json leaked.json
```

`dac27_analyze.py` ghi thêm:
- `decompose.csv`, macro `R-<model>-<F>-<suite>-dec-{first,firstrep,resample,resamplerep}`: pass@1 held-out tách theo nguồn gốc (mẫu đầu / mẫu đầu sau sửa / mẫu sau / mẫu sau có sửa); bốn phần cộng lại bằng pass@1.
- `judge.csv`, macro `-acc-<tier>`, `-fa-<tier>`: false accept trong vòng lặp theo mức tin của TB (`sv`, `weak`, `unch`, `ng`); `-tbref`, `-tbmut`: % TB chấp nhận RTL tham chiếu và điểm đột biến so với tham chiếu (cần `tbcheck.json`).
- `-p10`, `-p10lo`, `-p10hi` cho ô F0s; tương phản `R-<model>-<F>-vs-F0sp10-<suite>-{diff,ci,p}`: pass@1 của vòng lặp so với pass@10 của 10 mẫu độc lập (một bộ chọn hoàn hảo).
- `-ktok`: nghìn token mỗi lượt chạy, từ `tokens.json` (chỉ các ô chạy sau commit này).
- tương phản `full-vs-scale`, `scale-vs-base`.

Ghi chú: trước commit này, các cấu hình VE nhiều mẫu (`e0_t8`) dùng cùng một seed cho mọi mẫu của một bài, nên các mẫu trùng nhau. `main_langgraph.py` giờ đổi seed theo mẫu; mẫu 1 giữ seed cũ nên các ô `e0_t0` đã chạy không đổi.

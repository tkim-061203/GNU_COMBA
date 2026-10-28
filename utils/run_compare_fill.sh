#!/usr/bin/env bash
# ============================================================================
# run_compare_fill.sh - runs that fill the "--" cells of the RIVF'26 comparison
# table (camera-ready Table III), then re-runs dac27_analyze.
#
#   VerilogEval one-shot / T=0.8 prompt regimes (VerilogEval V2 protocol):
#     single-shot  F0  + ve_e1t0 (one-shot, greedy)     F0s + ve_e1t8 (one-shot, 20 samples T=0.8)
#     full pipe.   F3  + ve_e0t8, ve_e1t0, ve_e1t8
#   RTLLM syntax pass@5 needs no new run: dac27_analyze now reads it from the
#   existing heldout.json (design compiles with the official testbench).
#
#   nohup ./utils/run_compare_fill.sh > reports/compare_fill.log 2>&1 &
#   tail -f reports/compare_fill.log        # resumable: DONE arms are skipped
#
# Rough cost on 2x RTX 5880 Ada: F0 ~15 min, F0s/T=0.8 ~1.5 h, F3 e1t0 ~1 h,
# F3 *_t8 ~10 h each (20 samples x Best-of-10)  -> about 2 days in total.
# ============================================================================
set -uo pipefail
ROOT="${ROOT:-/home/nntkim/GNU_COMBA}"
PY="${PY:-/home/nntkim/miniconda3/envs/test_VE/bin/python}"
export BASE_QWEN="${BASE_QWEN:-$(ls -d /home/nntkim/.cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots/*/ 2>/dev/null | head -1)}"
cd "$ROOT"

# model | feedback | suites   (cheap arms first, the two 10 h F3 regimes last)
PLAN=(
  "base|F0|ve_e1t0"   "base|F0s|ve_e1t8"
  "full|F0|ve_e1t0"   "full|F0s|ve_e1t8"   "full|F3|ve_e1t0"
  "clean|F0|ve_e1t0"  "clean|F0s|ve_e1t8"  "clean|F3|ve_e1t0"
  "full|F3|ve_e0t8 ve_e1t8"
  "clean|F3|ve_e0t8 ve_e1t8"
)

state=RUN; i=0; failed=()
while [ "$state" != DONE ]; do
  case "$state" in
    RUN)
      if [ $i -ge ${#PLAN[@]} ]; then state=ANALYZE; continue; fi
      IFS='|' read -r m fb suites <<< "${PLAN[$i]}"
      echo "=== [$((i+1))/${#PLAN[@]}] $m $fb -- $suites  ($(date))"
      # shellcheck disable=SC2086
      ./utils/run_dac27.sh "$m" "$fb" -- $suites || { echo "!!! failed: ${PLAN[$i]}"; failed+=("${PLAN[$i]}"); }
      i=$((i+1)) ;;
    ANALYZE)
      "$PY" src/dac27_analyze.py reports/dac27 --out reports/dac27_results --leaked-json leaked.json \
        && echo "=== analyze OK -> reports/dac27_results/arms.csv" || echo "!!! dac27_analyze failed"
      state=DONE ;;
  esac
done
[ ${#failed[@]} -eq 0 ] && echo "all arms done" || { printf '!!! failed arm: %s\n' "${failed[@]}"; exit 1; }

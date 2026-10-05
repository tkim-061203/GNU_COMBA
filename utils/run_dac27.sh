#!/usr/bin/env bash
# ============================================================================
# run_dac27.sh - model x feedback-source matrix, scored on HELD-OUT testbenches.
#
#   ./utils/run_dac27.sh <model> [feedback ...] [-- suites]
#   model    : base | gen | full | single | scale | clean | random  (which checkpoints vLLM serves)
#              scale = a larger untuned model (SCALE_MODEL) in both roles
#              clean|random = retrained Generator (training/run_retrain.sh) + served Debugger
#   feedback : F0 F1 F2 F3 (default: all four), plus F0s on request
#     F0  single shot: 1 sample, no TED/Debugger, no testbench in the loop
#     F0s sampled single shot: F0 at temperature 0.8, 10 independent trials
#         (RTLLM) or 20 samples (VE), for an unbiased no-loop pass@k curve
#     F1  compiler only: Best-of-10 + syntax repair, no testbench in the loop
#     F2  generated TB: Best-of-10 + repair against a spec-generated, mutation-
#         graded testbench (one TB per problem and trial, shared by all samples)
#     F3  official TB in the loop (the legacy oracle setting), reference RTL hidden
#     F3 flow ablations (official TB in the loop, one REFINE component removed):
#       F3n1 Best-of-1 (no Best-of-N; repair kept)   F3nd no Debugger SLM patches
#       F3nt no TED (first failure ends the run)     F3ns no Sanitizer
#   suites   : rl1 rl2 ve (default: all)
#
# Every arm hides verified_*.v from the loop (COMBA_BLIND_EVAL=1 + blind copy),
# and every final design is re-graded against the official testbench by
# src/heldout_grade.py (RTLLM) or the VerilogEval final check (VE). Arms are
# resumable: a finished arm leaves DONE and is skipped on rerun.
#
# Example (one model phase per day, ~1 day each on 2x RTX 5880 Ada):
#   ./utils/run_dac27.sh full            # all feedback, all suites
#   ./utils/run_dac27.sh base F2 F3 -- rl1 rl2
# ============================================================================
set -euo pipefail

ROOT="${ROOT:-/home/nntkim/GNU_COMBA}"
PY="${PY:-/home/nntkim/miniconda3/envs/test_VE/bin/python}"
OUT="${OUT:-$ROOT/reports/dac27}"
JOBS="${JOBS:-10}"
TRIALS="${TRIALS:-5}"
BASE_QWEN="${BASE_QWEN:-}"        # LOCAL dir of Qwen2.5-Coder-7B-Instruct (launch_dual_gpu.sh checks -d)
GEN_CKPT="${GEN_CKPT:-/home/nntkim/Downloads/models/model_qwen_generator_0-35_e1_v1_merged}"
DBG_CKPT="${DBG_CKPT:-/home/nntkim/Downloads/models/model_qwen_debugger_2gpu_e1_v2_merged}"
SINGLE_CKPT="${SINGLE_CKPT:-}"   # optional: one adapter trained on generation+repair data
SCALE_MODEL="${SCALE_MODEL:-}"   # optional: LOCAL dir of a larger untuned model, e.g. Qwen2.5-Coder-14B-Instruct
TRIALS_F0S="${TRIALS_F0S:-10}"   # independent samples per RTLLM task for F0s
cd "$ROOT"

MODEL="${1:?model: base|gen|full|single|scale|clean|random}"; shift
FEEDBACK=(); SUITES=()
while [ $# -gt 0 ]; do
  if [ "$1" = "--" ]; then shift; SUITES=("$@"); break; fi
  FEEDBACK+=("$1"); shift
done
[ ${#FEEDBACK[@]} -eq 0 ] && FEEDBACK=(F0 F1 F2 F3)
[ ${#SUITES[@]} -eq 0 ] && SUITES=(rl1 rl2 ve)

case "$MODEL" in
  base)   [ -d "$BASE_QWEN" ] || { echo "set BASE_QWEN to a local model dir"; exit 1; }
          GEN="$BASE_QWEN"; DBG="$BASE_QWEN" ;;
  gen)    GEN="$GEN_CKPT";  DBG="$GEN_CKPT"  ;;     # Generator adapter also plays Debugger
  full)   GEN="$GEN_CKPT";  DBG="$DBG_CKPT"  ;;
  single) [ -n "$SINGLE_CKPT" ] || { echo "set SINGLE_CKPT"; exit 1; }
          GEN="$SINGLE_CKPT"; DBG="$SINGLE_CKPT" ;;
  clean|random)   # retrained Generator (training/run_retrain.sh) + the served Debugger, as `full`
          ck=/home/nntkim/Downloads/retrain/models/model_qwen_generator_${MODEL}_merged
          [ "$MODEL" = clean ] && ck="${CLEAN_CKPT:-$ck}" || ck="${RANDOM_CKPT:-$ck}"
          [ -d "$ck" ] || { echo "no merged $MODEL generator at $ck"; exit 1; }
          GEN="$ck"; DBG="$DBG_CKPT" ;;
  scale)  [ -d "$SCALE_MODEL" ] || { echo "set SCALE_MODEL to a local model dir"; exit 1; }
          GEN="$SCALE_MODEL"; DBG="$SCALE_MODEL" ;;
  *) echo "unknown model $MODEL"; exit 1 ;;
esac

# ---- serve the right checkpoints, then record what is actually served ------
serve () {
  ./launch_dual_gpu.sh --restart --base-model "$GEN" --merged-model "$DBG"
  for i in $(seq 1 120); do
    if curl -sf -m3 localhost:8000/health >/dev/null && curl -sf -m3 localhost:8001/health >/dev/null; then
      return 0; fi
    sleep 10
  done
  echo "vLLM did not come up"; exit 1
}
provenance () {   # $1 = arm dir
  { echo "model_tag: $MODEL"; echo "expected_gen: $GEN"; echo "expected_dbg: $DBG"
    echo "served_gen: $(curl -s localhost:8000/v1/models)"; echo "served_dbg: $(curl -s localhost:8001/v1/models)"
    echo "git: $(git rev-parse HEAD 2>/dev/null) dirty=$(git status --porcelain -uno 2>/dev/null | wc -l)"
    echo "date: $(date -Iseconds)"
    echo "arm_env: $COMMON $(feedback_env "$fb")"
    { env | grep -E '^COMBA_' || true; } | sort; } > "$1/provenance.txt"   # grep finds nothing -> exit 1 under pipefail
}
vllm_tokens () {   # $1 port -> "prompt completion" token totals since the server started
  local m; m=$(curl -sf -m5 "localhost:$1/metrics" 2>/dev/null) || m=""
  [ -n "$m" ] || { echo "-1 -1"; return 0; }
  printf '%s\n' "$m" | awk '/^vllm:prompt_tokens_total/{p+=$NF} /^vllm:generation_tokens_total/{g+=$NF} END{printf "%d %d\n", p, g}'
}
write_tokens () {   # $1 arm, $2 $3 = gen before/after, $4 $5 = dbg before/after ("prompt completion")
  "$PY" - "$1/tokens.json" "$2" "$3" "$4" "$5" <<'EOF'
import json, sys
out, g0, g1, d0, d1 = sys.argv[1:6]
def delta(a, b):
    a, b = [int(x) for x in a.split()], [int(x) for x in b.split()]
    return None if min(a + b) < 0 else {"prompt": b[0] - a[0], "completion": b[1] - a[1]}
json.dump({"generator": delta(g0, g1), "debugger": delta(d0, d1),
           "source": "vLLM /metrics counters, delta over the arm"}, open(out, "w"), indent=2)
EOF
}
export VLLM_LOG_STATS=1   # launch_dual_gpu.sh keeps vLLM stats on, so /metrics counts tokens
if pgrep -af 'benchmark_langgraph\.py' >/dev/null; then echo "another benchmark is running"; exit 1; fi
serve

COMMON="COMBA_BLIND_EVAL=1 COMBA_LLM_SEED=42 COMBA_XML_ESCAPE=1 COMBA_PIPELINE_TIMEOUT=600 \
COMBA_WALL_BUDGET=1200 COMBA_SC_MEMORY=0 COMBA_SC_VOTE=0 COMBA_QUIET=1"

feedback_env () {   # $1 = F0..F3 ; echoes env assignments
  case "$1" in
    F0) echo "COMBA_SELF_CONSISTENCY=0 COMBA_MAX_SAMPLES=1 COMBA_USE_TED=0 COMBA_USE_DEBUGGER_SLM=0 COMBA_SKIP_TB_IF_NO_GOLDEN=1" ;;
    F0s) echo "COMBA_SELF_CONSISTENCY=0 COMBA_MAX_SAMPLES=1 COMBA_USE_TED=0 COMBA_USE_DEBUGGER_SLM=0 COMBA_SKIP_TB_IF_NO_GOLDEN=1 COMBA_TEMPERATURE=0.8" ;;
    F1) echo "COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=10 COMBA_SKIP_TB_IF_NO_GOLDEN=1" ;;
    F2) echo "COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=10 COMBA_SKIP_TB_IF_NO_GOLDEN=0 COMBA_TB_VALIDATE=1 COMBA_TS_SIMULATOR=iverilog" ;;
    F3) echo "COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=10 COMBA_SKIP_TB_IF_NO_GOLDEN=0 COMBA_TS_SIMULATOR=verilator" ;;
    F3n1) echo "COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=1 COMBA_SKIP_TB_IF_NO_GOLDEN=0 COMBA_TS_SIMULATOR=verilator" ;;
    F3nd) echo "COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=10 COMBA_SKIP_TB_IF_NO_GOLDEN=0 COMBA_TS_SIMULATOR=verilator COMBA_USE_DEBUGGER_SLM=0" ;;
    F3nt) echo "COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=10 COMBA_SKIP_TB_IF_NO_GOLDEN=0 COMBA_TS_SIMULATOR=verilator COMBA_USE_TED=0" ;;
    F3ns) echo "COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=10 COMBA_SKIP_TB_IF_NO_GOLDEN=0 COMBA_TS_SIMULATOR=verilator COMBA_USE_SANITIZER=0" ;;
  esac
}
blind_mode () { case "$1" in F3*) echo tb ;; *) echo spec ;; esac; }

run_rtllm () {   # $1 suite rl1|rl2, $2 feedback, $3 arm dir
  local suite="$1" fb="$2" arm="$3" src desc extra trials
  if [ "$suite" = rl1 ]; then src=RTLLM/modules; desc=RTLLM.txt; extra="";
  else src=RTLLM_v2/modules; desc=txt; extra="COMBA_FORCE_XML=1"; fi
  trials=$TRIALS
  case "$fb" in F0) trials=1 ;; F0s) trials=$TRIALS_F0S ;; esac   # F0 is low-temperature seeded, one draw suffices
  local blind="$arm/RTLLM_${suite}_$(blind_mode "$fb")/modules"
  "$PY" src/blind_dataset.py "$src" "$blind" --mode "$(blind_mode "$fb")" | tee "$arm/blind.log"
  env $COMMON $(feedback_env "$fb") $extra COMBA_GENTB_CACHE_DIR="$arm/gentb_cache" \
    "$PY" src/benchmark_langgraph.py --modules-dir "$blind" --descriptiontype "$desc" \
      --trials "$trials" --jobs "$JOBS" --output-dir "$arm/fixrate"
  "$PY" src/parse_rtllm_trials.py "$blind" --out-json "$arm/inloop_breakdown.json" || true
  env COMBA_TS_SIMULATOR=verilator COMBA_BLIND_EVAL=1 COMBA_QUIET=1 \
    "$PY" src/heldout_grade.py --runs "$blind" --official "$src" --out-json "$arm/heldout.json" --jobs 8
}

run_ve () {   # $1 feedback, $2 arm dir
  local fb="$1" arm="$2" sc=1 n=10 cfg=e0_t0
  case "$fb" in F0) sc=0; n=1 ;; F0s) sc=0; n=1; cfg=e0_t8 ;; F3n1) n=1 ;; esac   # e0_t8 = 20 samples at T=0.8
  local inloop=""
  case "$fb" in F3*) ;; *) mkdir -p "$arm/ve_blind"; inloop="COMBA_INLOOP_DATASET_DIR=$arm/ve_blind" ;; esac
  env $COMMON $(feedback_env "$fb") $inloop COMBA_GENTB_CACHE_DIR="$arm/gentb_cache" \
    make VerilogEval VEVAL_CONFIGS=$cfg SC=$sc COMBA_MAX_SAMPLES=$n LANGGRAPH_JOBS="$JOBS" \
      VEVAL_BUILD_ROOT="$arm/ve_build" VEVAL_SWEEP_REPORTS="$arm/ve_reports"
}

for fb in "${FEEDBACK[@]}"; do
  for suite in "${SUITES[@]}"; do
    arm="$OUT/$MODEL/$fb/$suite"
    if [ -f "$arm/DONE" ]; then echo "skip $arm"; continue; fi
    rm -rf "$arm"; mkdir -p "$arm"
    echo "=========== $MODEL / $fb / $suite  ($(date)) ==========="
    provenance "$arm"
    t0=$(date +%s); tg0=$(vllm_tokens 8000); td0=$(vllm_tokens 8001)
    if [ "$suite" = ve ]; then run_ve "$fb" "$arm"; else run_rtllm "$suite" "$fb" "$arm"; fi
    echo "elapsed_s: $(( $(date +%s) - t0 ))" >> "$arm/provenance.txt"
    write_tokens "$arm" "$tg0" "$(vllm_tokens 8000)" "$td0" "$(vllm_tokens 8001)" || true
    touch "$arm/DONE"
  done
done
echo "done: $OUT/$MODEL"

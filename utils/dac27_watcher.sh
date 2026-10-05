#!/usr/bin/env bash
# ============================================================================
# dac27_watcher.sh - babysit the DAC27 experiments (runbook §3, §4, §6).
#
# Every INTERVAL seconds:
#   1. reap orphaned / hung vvp under $ROOT (PPID==1 or older than VVP_AGE)
#   2. write a status snapshot to $STATUS: DONE arms per phase, served vLLM
#      checkpoints, GPU util, newest output age
#   3. if run_dac27.sh is running but nothing under its model dir changed for
#      STALL_SEC: kill the wedged `run.py langgraph` (benchmark_langgraph then
#      moves on to the next trial); if it is still stalled a second STALL_SEC
#      later, kill the whole run_dac27.sh tree so step 4 restarts the phase
#   4. if run_dac27.sh is NOT running: start the first unfinished phase in
#      PHASES (resumable: DONE arms skipped). Unfinished arms are moved to
#      $PARTIAL first, since run_dac27.sh rm -rf's them. Before the first
#      supplementary phase (one with ':' or `scale`) the checkout is
#      fast-forwarded once with `git pull --ff-only` (runbook §6: never pull
#      while a matrix arm runs - bash reads run_dac27.sh as it executes)
#   4b. every arm that gets DONE is health-checked by utils/dac27_armcheck.py
#      (provenance, trial/design counts, grading errors, runaway logs, vLLM
#      400s, tracebacks, zero pass rate) -> <arm>/armcheck.json + one log line;
#      a FAIL is logged as "ARMCHECK FAIL" and listed in $STATUS
#   5. once every runnable phase is done, post-processing (CPU), then exit:
#      a. re-grade every DONE rl1 arm whose heldout.json predates the seeded
#         grader (no `tb_seeds`; RTLLM v1.1 tb.cpp uses srand(time(NULL)))
#      b. src/dac27_tbcheck.py for every DONE F2 arm without tbcheck.json
#      c. src/dac27_analyze.py (adds --leaked-json if $LEAKED exists)
#
# A phase is `model` (F0 F1 F2 F3 x rl1 rl2 ve = 12 arms) or `model:FB[,FB]`
# (those feedback settings only, 3 arms each). Phases that cannot start
# (missing BASE_QWEN / SCALE_MODEL dir) are skipped and do not block step 5.
#
# Usage (in its own tmux window):
#   ./utils/dac27_watcher.sh
#   PHASES="base full:F0s" SCALE_MODEL=/path/14B ./utils/dac27_watcher.sh
#   ./utils/dac27_watcher.sh --status      # refresh + print status only (no kill/start)
#
# Env knobs: ROOT PY OUT PHASES BASE_QWEN SCALE_MODEL INTERVAL STALL_SEC
#            VVP_AGE MAX_RESTARTS LEAKED RESULTS LOG STATUS PARTIAL
# ============================================================================
set -u

ROOT="${ROOT:-/home/nntkim/GNU_COMBA}"
PY="${PY:-/home/nntkim/miniconda3/envs/test_VE/bin/python}"
OUT="${OUT:-$ROOT/reports/dac27}"
PHASES="${PHASES:-full gen base full:F0s base:F0s scale}"   # run order; finished phases are skipped
BASE_QWEN="${BASE_QWEN:-$(ls -d /home/nntkim/.cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots/*/ 2>/dev/null | head -1)}"
SCALE_MODEL="${SCALE_MODEL:-$(ls -d /home/nntkim/.cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-14B-Instruct/snapshots/*/ 2>/dev/null | head -1)}"
INTERVAL="${INTERVAL:-300}"
STALL_SEC="${STALL_SEC:-10800}"                   # 3h > pool stall timeout (3x1200s) + slack
VVP_AGE="${VVP_AGE:-600}"                         # sim timeout is 120s; nothing legit lives this long
MAX_RESTARTS="${MAX_RESTARTS:-3}"                 # per phase, then give up on it
LEAKED="${LEAKED:-$ROOT/leaked.json}"
RESULTS="${RESULTS:-$ROOT/reports/dac27_results}"
LOG="${LOG:-$ROOT/logs/dac27_watcher.log}"
STATUS="${STATUS:-$ROOT/reports/dac27_STATUS.txt}"
PARTIAL="${PARTIAL:-$ROOT/reports/dac27_partial}"  # outside $OUT so dac27_analyze never sees it
SUITES="rl1 rl2 ve"
export BASE_QWEN SCALE_MODEL
# launch_dual_gpu.sh calls bare `python -m vllm...`; started outside an activated
# shell that resolves to conda base (no vllm) -> "vLLM did not come up" x3 on
# 2026-10-04. Put the serving env first on PATH for everything we spawn.
export PATH="$(dirname "$PY"):$PATH"
export CONDA_PREFIX="$(dirname "$(dirname "$PY")")"

cd "$ROOT" || exit 1
mkdir -p "$(dirname "$LOG")" "$PARTIAL"
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

declare -A RESTARTS=() SKIPPED=()
stall_strikes=0
pulled=0

phase_model() { echo "${1%%:*}"; }
phase_fbs() {    # feedback list of a phase, space separated
  case "$1" in *:*) echo "${1#*:}" | tr , ' ' ;; *) echo "F0 F1 F2 F3" ;; esac
}
phase_done() {   # "<done> <expected>" for a phase
  local m fb s d=0 e=0
  m=$(phase_model "$1")
  for fb in $(phase_fbs "$1"); do for s in $SUITES; do
    e=$((e + 1)); [ -f "$OUT/$m/$fb/$s/DONE" ] && d=$((d + 1))
  done; done
  echo "$d $e"
}
phase_finished() { local d e; read -r d e < <(phase_done "$1"); [ "$d" -ge "$e" ]; }
is_supplementary() { case "$1" in *:*|scale*) return 0 ;; *) return 1 ;; esac; }

runner_pid() {   # pid of a live run_dac27.sh (bash), empty if none
  pgrep -f 'run_dac27\.sh (base|gen|full|single|scale)' | head -1
}

runner_model() {
  local pid; pid=$(runner_pid); [ -n "$pid" ] || return 0
  tr '\0' ' ' < "/proc/$pid/cmdline" | grep -oE 'run_dac27\.sh +[a-z]+' | awk '{print $2}'
}

newest_age() {   # seconds since the newest file under $1 changed
  local t
  t=$(find "$1" -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1)
  [ -n "$t" ] || { echo 0; return; }
  echo $(( $(date +%s) - ${t%.*} ))
}

reap_vvp() {
  local pid ppid etimes cwd n=0
  while read -r pid ppid etimes; do
    cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null) || continue
    case "$cwd" in "$ROOT"*) ;; *) continue ;; esac
    if [ "$ppid" = 1 ] || [ "$etimes" -gt "$VVP_AGE" ]; then
      kill -KILL "$pid" 2>/dev/null && n=$((n + 1))
    fi
  done < <(ps -eo pid,ppid,etimes,comm | awk '$4=="vvp"{print $1, $2, $3}')
  [ "$n" -gt 0 ] && log "reaped $n orphan/hung vvp"
  return 0
}

kill_tree() {    # $1 pid: kill it and all descendants
  local p
  for p in $(pgrep -P "$1"); do kill_tree "$p"; done
  kill -KILL "$1" 2>/dev/null
}

write_status() {
  local model="$1" age="$2" ph d e
  {
    echo "updated: $(date -Iseconds)   git: $(git rev-parse --short HEAD 2>/dev/null)"
    echo "DONE arms (all): $(ls "$OUT"/*/*/*/DONE 2>/dev/null | wc -l)"
    for ph in $PHASES; do
      read -r d e < <(phase_done "$ph")
      echo "  $ph: $d / $e${SKIPPED[$ph]:+  (skipped: ${SKIPPED[$ph]})}"
    done
    echo "running: ${model:-none}  (newest output ${age}s ago, stall strikes $stall_strikes)"
    echo "arms done:"
    ls "$OUT"/*/*/*/DONE 2>/dev/null | sed "s#$OUT/##; s#/DONE##" | sed 's/^/  /'
    echo "vLLM 8000: $(curl -s -m5 localhost:8000/v1/models | grep -o '"root":"[^"]*"' | head -1)"
    echo "vLLM 8001: $(curl -s -m5 localhost:8001/v1/models | grep -o '"root":"[^"]*"' | head -1)"
    echo "GPU: $(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>/dev/null | paste -sd'|')"
    echo "vvp alive: $(pgrep -xc vvp)"
    echo "armcheck not OK:"
    grep -l '"level": "\(WARN\|FAIL\)"' "$OUT"/*/*/*/armcheck.json 2>/dev/null \
      | while read -r f; do echo "  $(grep -o '"level": "[A-Z]*"' "$f" | head -1 | cut -d'"' -f4) $(dirname "${f#$OUT/}")"; done
  } > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"
}

backup_partial() {   # move unfinished arms of phase $1 out of the way
  local m fb s arm dst
  m=$(phase_model "$1")
  for fb in $(phase_fbs "$1"); do for s in $SUITES; do
    arm="$OUT/$m/$fb/$s"
    [ -d "$arm" ] && [ ! -f "$arm/DONE" ] || continue
    dst="$PARTIAL/${m}_${fb}_${s}.$(date +%Y%m%d_%H%M%S)"
    mv "$arm" "$dst" && log "moved unfinished arm ${arm#$OUT/} -> $dst"
  done; done
}

pull_once() {    # fast-forward the checkout before the first supplementary phase
  [ "$pulled" = 1 ] && return 0
  local before after
  before=$(git rev-parse --short HEAD)
  if git fetch -q origin && git pull --ff-only -q; then
    after=$(git rev-parse --short HEAD)
    log "git pull --ff-only: $before -> $after"
    pulled=1
  else
    log "git pull --ff-only FAILED at $before; supplementary phases blocked"
    return 1
  fi
}

start_phase() {      # $1 phase
  local ph="$1" m fbs d e
  m=$(phase_model "$ph"); fbs=$(phase_fbs "$ph")
  if [ "$m" = base ] && [ ! -d "$BASE_QWEN" ]; then
    SKIPPED[$ph]="BASE_QWEN not a local dir"; log "skip $ph: ${SKIPPED[$ph]}"; return 1
  fi
  if [ "$m" = scale ] && [ ! -d "$SCALE_MODEL" ]; then
    SKIPPED[$ph]="SCALE_MODEL '$SCALE_MODEL' not a local dir"; log "skip $ph: ${SKIPPED[$ph]}"; return 1
  fi
  if is_supplementary "$ph"; then pull_once || { SKIPPED[$ph]="git pull failed"; return 1; }; fi
  backup_partial "$ph"
  RESTARTS[$ph]=$(( ${RESTARTS[$ph]:-0} + 1 ))
  read -r d e < <(phase_done "$ph")
  log "start phase $ph (attempt ${RESTARTS[$ph]}/$MAX_RESTARTS, done $d/$e)"
  case "$ph" in
    *:*) setsid nohup ./utils/run_dac27.sh "$m" $fbs >> "$ROOT/reports/dac27_${m}_$(echo $fbs | tr ' ' _).log" 2>&1 < /dev/null & ;;
    *)   setsid nohup ./utils/run_dac27.sh "$m" >> "$ROOT/reports/dac27_$m.log" 2>&1 < /dev/null & ;;
  esac
  stall_strikes=0
}

VE_DATASET="${VE_DATASET:-$ROOT/ext/verilog-eval/dataset_code-complete-iccad2023}"

armcheck_new() {  # health-check DONE arms that have no armcheck.json yet
  local d arm line
  for d in "$OUT"/*/*/*/DONE; do
    [ -f "$d" ] || continue
    arm=$(dirname "$d")
    if [ -f "$arm/armcheck.json" ]; then   # re-check only if results changed since
      [ -n "$(find "$arm" -maxdepth 1 \( -name heldout.json -o -name tbcheck.json \) -newer "$arm/armcheck.json")" ] || continue
    fi
    line=$(timeout 900 "$PY" utils/dac27_armcheck.py "$arm" 2>&1 | tail -1)
    log "ARMCHECK $line"
  done
}

regrade_rl1() {   # re-grade rl1 arms graded before the fixed-seed grader
  local arm blind
  for arm in "$OUT"/*/*/rl1; do
    [ -f "$arm/DONE" ] || continue
    "$PY" -c "import json,sys; sys.exit(0 if json.load(open('$arm/heldout.json')).get('tb_seeds') else 1)" 2>/dev/null && continue
    blind=$(ls -d "$arm"/RTLLM_rl1_*/modules 2>/dev/null | head -1); [ -n "$blind" ] || continue
    [ -f "$arm/heldout.unseeded.json" ] || cp "$arm/heldout.json" "$arm/heldout.unseeded.json" 2>/dev/null
    log "re-grade ${arm#$OUT/} with fixed TB seeds"
    env COMBA_TS_SIMULATOR=verilator COMBA_BLIND_EVAL=1 COMBA_QUIET=1 \
      "$PY" src/heldout_grade.py --runs "$blind" --official RTLLM/modules --out-json "$arm/heldout.json" --jobs 8 >> "$LOG" 2>&1 \
      || log "re-grade ${arm#$OUT/} FAILED"
    rm -f "$arm/armcheck.json"   # re-check with the new heldout.json
  done
}

tbcheck_f2() {    # judge quality of the generated TBs, per F2 arm
  local arm s off
  for arm in "$OUT"/*/F2/*; do
    [ -f "$arm/DONE" ] && [ -d "$arm/gentb_cache" ] && [ ! -f "$arm/tbcheck.json" ] || continue
    s=$(basename "$arm")
    case "$s" in rl1) off=RTLLM/modules ;; rl2) off=RTLLM_v2/modules ;; ve) off="$VE_DATASET" ;; *) continue ;; esac
    log "tbcheck ${arm#$OUT/}"
    "$PY" src/dac27_tbcheck.py "$arm" --official "$off" --jobs 8 >> "$LOG" 2>&1 || log "tbcheck ${arm#$OUT/} FAILED"
  done
}

analyze() {
  local extra=""
  [ -f "$LEAKED" ] && extra="--leaked-json $LEAKED"
  log "all runnable phases done -> dac27_analyze.py ${extra:-(no leaked.json)}"
  if "$PY" src/dac27_analyze.py "$OUT" --out "$RESULTS" $extra >> "$LOG" 2>&1; then
    log "results: $(ls "$RESULTS" | paste -sd' ')"
  else
    log "dac27_analyze.py FAILED (see $LOG)"
  fi
}

tick() {   # returns 1 when everything is finished
  reap_vvp
  armcheck_new
  local model age=0 ph
  model=$(runner_model)

  if [ -n "$model" ]; then
    age=$(newest_age "$OUT/$model")
    if [ "$age" -gt $(( STALL_SEC * (stall_strikes + 1) )) ]; then
      stall_strikes=$((stall_strikes + 1))
      if [ "$stall_strikes" -eq 1 ]; then
        log "STALL: $model no output for ${age}s -> killing wedged run.py langgraph"
        pkill -KILL -f "run.py langgraph .*$OUT/$model/" 2>/dev/null
      else
        log "STALL x$stall_strikes: $model still no output for ${age}s -> killing run_dac27.sh tree"
        kill_tree "$(runner_pid)"
      fi
    elif [ "$age" -lt "$STALL_SEC" ]; then
      stall_strikes=0
    fi
    write_status "$model" "$age"
    return 0
  fi

  for ph in $PHASES; do
    phase_finished "$ph" && continue
    [ -n "${SKIPPED[$ph]:-}" ] && continue
    if [ "${RESTARTS[$ph]:-0}" -ge "$MAX_RESTARTS" ]; then
      SKIPPED[$ph]="gave up after $MAX_RESTARTS attempts"; log "phase $ph ${SKIPPED[$ph]}"; continue
    fi
    start_phase "$ph" && { write_status "$(phase_model "$ph")" 0; return 0; }
  done

  write_status "" 0
  pull_once || true            # post-processing needs the seeded grader + tbcheck
  regrade_rl1
  tbcheck_f2
  armcheck_new
  analyze
  return 1
}

if [ "${1:-}" = "--status" ]; then
  m=$(runner_model); a=0; [ -n "$m" ] && a=$(newest_age "$OUT/$m")
  write_status "$m" "$a"; cat "$STATUS"; exit 0
fi

log "watcher start pid=$$ phases='$PHASES' interval=${INTERVAL}s stall=${STALL_SEC}s base_qwen=$BASE_QWEN scale_model=${SCALE_MODEL:-none}"
while tick; do sleep "$INTERVAL"; done
log "watcher exit"

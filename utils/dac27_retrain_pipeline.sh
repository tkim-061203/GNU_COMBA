#!/usr/bin/env bash
# ============================================================================
# dac27_retrain_pipeline.sh - after the flow ablation: retrain + evaluate.
#
#   1. wait until no dac27_watcher.sh / run_dac27.sh is running (the ablation
#      watcher also runs dac27_analyze at its end)
#   2. stop vLLM so both GPUs are free
#   3. smoke test: 20 steps per stage + merge for `clean` on one GPU; stop on
#      failure; the smoke artefacts are deleted afterwards
#   4. train `clean` (GPU 1) and `random` (GPU 0) in parallel
#      (training/run_retrain.sh; 3 stages each, ~66 h at the original speed)
#   5. evaluate both with the watcher: F0, F0s, F3 x rl1 rl2 ve, then its
#      post-processing (re-grade, tbcheck, armcheck, dac27_analyze)
#
# Run in its own tmux window:  ./utils/dac27_retrain_pipeline.sh
# Log: logs/dac27_retrain_pipeline.log   Training logs: ~/Downloads/retrain/logs/
# ============================================================================
set -u
ROOT=/home/nntkim/GNU_COMBA
RETRAIN_DIR="${RETRAIN_DIR:-/home/nntkim/Downloads/retrain}"
LOG="$ROOT/logs/dac27_retrain_pipeline.log"
EVAL_PHASES="${EVAL_PHASES:-clean:F0,F0s,F3 random:F0,F0s,F3}"
cd "$ROOT" || exit 1
mkdir -p "$(dirname "$LOG")"
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

log "pipeline start pid=$$"
while pgrep -f 'dac27_watcher\.sh$|run_dac27\.sh (base|gen|full|single|scale|clean|random)' >/dev/null; do
  sleep 300
done
log "no matrix run active -> stopping vLLM"
PATH="/home/nntkim/miniconda3/envs/test_VE/bin:$PATH" ./launch_dual_gpu.sh --stop >> "$LOG" 2>&1
sleep 30
log "GPU memory after stop: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader | paste -sd' ')"

log "smoke test (clean, 20 steps/stage + merge, GPU 1)"
if SMOKE=1 GPU=1 RETRAIN_DIR="$RETRAIN_DIR" training/run_retrain.sh clean >> "$LOG" 2>&1; then
  log "smoke OK: $(grep -h -o "'train_loss': '[^']*'" "$RETRAIN_DIR"/logs/train_clean_s*_smoke.log | paste -sd' ')"
  rm -rf "$RETRAIN_DIR"/*_smoke "$RETRAIN_DIR"/models/*_smoke_merged
else
  log "smoke FAILED - see $RETRAIN_DIR/logs/*_smoke.log; stopping"; exit 1
fi

log "train clean (GPU 1) and random (GPU 0) in parallel"
GPU=1 RETRAIN_DIR="$RETRAIN_DIR" training/run_retrain.sh clean  >> "$RETRAIN_DIR/logs/run_clean.log"  2>&1 & pc=$!
GPU=0 RETRAIN_DIR="$RETRAIN_DIR" training/run_retrain.sh random >> "$RETRAIN_DIR/logs/run_random.log" 2>&1 & pr=$!
wait $pc; rc=$?; log "clean training exit $rc"
wait $pr; rr=$?; log "random training exit $rr"
ok=""
[ $rc -eq 0 ] && ok="clean:F0,F0s,F3"
[ $rr -eq 0 ] && ok="$ok random:F0,F0s,F3"
phases=""
for p in $EVAL_PHASES; do case " $ok " in *" $p "*) phases="$phases $p" ;; esac; done
[ -n "${phases// }" ] || { log "no variant trained; nothing to evaluate"; exit 1; }

log "evaluate:$phases"
PHASES="${phases# }" ./utils/dac27_watcher.sh >> "$LOG" 2>&1
log "pipeline done"

#!/usr/bin/env bash
# reap_orphan_vvp.sh — reap hung / orphaned vvp simulations.
#
# Why this exists:
#   Each langgraph worker arms a SIGALRM watchdog (COMBA_PIPELINE_TIMEOUT, 600s)
#   in main_langgraph.py. If the alarm fires while a worker is blocked inside
#   comba_pipeline._run_sim_process -> p.communicate() running `vvp`, the handler
#   raises PipelineTimeout. That bypasses the `except subprocess.TimeoutExpired`
#   branch, so the group is never killpg'd. Because vvp was spawned with
#   start_new_session=True it is detached from the worker's process group and
#   survives; once its worker exits (pool teardown) it reparents to init (PPID=1)
#   and burns a CPU core forever. 42 such orphans from one e0_t8 config were seen
#   on 2026-07-20.
#
# The proper fix is in _run_sim_process (kill the group on ANY exit, not just
# TimeoutExpired). This watcher is the safety net that cleans up leaks live.
#
# Kill signatures (both unambiguous — no legitimate vvp runs this long, the sim
# timeout in _run_sim_process is 120s):
#   (a) orphaned : PPID == 1
#   (b) hung     : elapsed > AGE_THRESHOLD (default 300s)
# Scoped to vvp whose CWD is under $REPO so nothing unrelated is ever touched.
#
# Env knobs: REPO, INTERVAL (s), AGE_THRESHOLD (s), LOG, STOP_WHEN_PID.
#   STOP_WHEN_PID: when set, the watcher does a few final sweeps and exits once
#   that PID is gone (e.g. the `make VerilogEval` pid) so it doesn't linger.
set -u

REPO="${REPO:-/home/nntkim/GNU_COMBA}"
INTERVAL="${INTERVAL:-20}"
AGE_THRESHOLD="${AGE_THRESHOLD:-300}"
LOG="${LOG:-$REPO/logs/reap_orphan_vvp.log}"
STOP_WHEN_PID="${STOP_WHEN_PID:-}"

mkdir -p "$(dirname "$LOG")"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

log "watcher start (pid=$$ interval=${INTERVAL}s age>${AGE_THRESHOLD}s repo=$REPO stop_when=${STOP_WHEN_PID:-none})"

sweep() {
  local killed=0 pid ppid etimes cwd
  while read -r pid ppid etimes; do
    [ -z "${pid:-}" ] && continue
    cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null) || continue
    case "$cwd" in "$REPO"*) : ;; *) continue ;; esac
    if [ "$ppid" = "1" ] || [ "$etimes" -gt "$AGE_THRESHOLD" ]; then
      if kill -KILL "$pid" 2>/dev/null; then
        killed=$((killed + 1))
        log "reaped pid=$pid ppid=$ppid age=${etimes}s cfg=$(echo "$cwd" | sed 's#.*/.build_sample_##; s#/samples/.*##')"
      fi
    fi
  done < <(ps -eo pid,ppid,etimes,comm | awk '$4=="vvp"{print $1, $2, $3}')
  [ "$killed" -gt 0 ] && log "sweep killed $killed"
  return 0
}

grace=0
while true; do
  sweep
  if [ -n "$STOP_WHEN_PID" ] && ! kill -0 "$STOP_WHEN_PID" 2>/dev/null; then
    grace=$((grace + 1))
    if [ "$grace" -ge 3 ]; then
      sweep
      log "watched pid $STOP_WHEN_PID gone — watcher stop"
      exit 0
    fi
    sleep 5
    continue
  fi
  sleep "$INTERVAL"
done

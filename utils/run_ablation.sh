#!/usr/bin/env bash
# ============================================================================
# run_ablation.sh — COMBA component ablation, config-consistent with the
# headline "Full" run (v1 93.1% / v2 76.4% at N=10).
#
# Every arm shares the SAME base config and differs ONLY by the ablation
# toggle, so the pass@5 deltas are attributable to the removed component and
# not to a config drift. Key fixes vs the ad-hoc script:
#   • test_VE python (NOT `python3` = base conda, which lacks pydantic-xml and
#     silently no-ops XML validation).
#   • COMBA_MAX_SAMPLES=10 on every arm, matching the N=10 Full baseline.
#   • COMBA_LLM_SEED=42 + COMBA_XML_ESCAPE=1 held constant (seeding is also
#     auto-injected per-trial by benchmark_langgraph, but we set it explicitly).
#
# Ablatable at runtime: debugger, sanitizer, TED. NOT #1 "no-cat" — dataset
# categorization is a TRAIN-TIME choice (needs a different adapter), so it has
# no runtime gate and is intentionally omitted here.
#
# Runtime: Full is snapshotted (0 extra time); the 3 disabled-component arms
# run faster than Full (no repair loop). Budget ~5–7h total. Run overnight.
#   RERUN_FULL=1 ./utils/run_ablation.sh   # re-run Full fresh instead of snapshot
# ============================================================================
set -euo pipefail

PY=/home/nntkim/miniconda3/envs/test_VE/bin/python
cd /home/nntkim/GNU_COMBA

# ── Base config — IDENTICAL across all arms ──
BASE="SC=1 COMBA_SELF_CONSISTENCY=1 COMBA_MAX_SAMPLES=10 COMBA_TS_SIMULATOR=verilator \
COMBA_LLM_SEED=42 COMBA_XML_ESCAPE=1 COMBA_PIPELINE_TIMEOUT=600 COMBA_WALL_BUDGET=1200"

# ── Preflight guards ──
if pgrep -af 'benchmark_langgraph\.py' >/dev/null; then
  echo "❌ Có benchmark khác đang chạy — dừng để tránh clobber report."; exit 1
fi
for p in 8000 8001; do
  curl -sf -m5 "http://localhost:$p/health" >/dev/null \
    || { echo "❌ vLLM server :$p không phản hồi — khởi động launch_dual_gpu.sh trước."; exit 1; }
done
[ -x "$PY" ] || { echo "❌ Không thấy test_VE python: $PY"; exit 1; }
echo "✅ Preflight OK · python=$PY · N=10 · seed=42"

# ── One benchmark arm (v1 + v2). $1 = ablation toggles (may be empty) ──
bench () {
  local toggles="$1"
  echo "  ▶ v1 rtllm    [${toggles:-full}]"
  env $BASE $toggles                   "$PY" src/benchmark_langgraph.py --dataset rtllm    --trials 5 --jobs 10
  echo "  ▶ v2 rtllm_v2 [${toggles:-full}]"
  env $BASE COMBA_FORCE_XML=1 $toggles "$PY" src/benchmark_langgraph.py --dataset rtllm_v2 --trials 5 --jobs 10
}

# ── Snapshot current live reports + parse + analyze into reports/<name> ──
capture () {
  local out="reports/$1"
  echo "  💾 capture → $out"
  mkdir -p "$out/rtllm" "$out/rtllm_v2"
  rsync -a RTLLM/modules/    "$out/rtllm/modules/"
  rsync -a RTLLM_v2/modules/ "$out/rtllm_v2/modules/"
  "$PY" src/parse_rtllm_trials.py "$out/rtllm/modules"    --out-json "$out/rtllm/pass5_breakdown.json"    || echo "  ⚠ parse v1 lỗi"
  "$PY" src/parse_rtllm_trials.py "$out/rtllm_v2/modules" --out-json "$out/rtllm_v2/pass5_breakdown.json" || echo "  ⚠ parse v2 lỗi"
  "$PY" src/analyze_self_consistency.py "$out/rtllm/modules"    --out "$out/analyze_syntax_rtllm.json"    || echo "  ⚠ analyze v1 lỗi"
  "$PY" src/analyze_self_consistency.py "$out/rtllm_v2/modules" --out "$out/analyze_syntax_rtllm_v2.json" || echo "  ⚠ analyze v2 lỗi"
}

arm () { echo "══════════ ARM: $1 ══════════"; }

# ── abl1_full: mốc baseline ──
# Mặc định snapshot report Full N=10 vừa chạy (seeded → tái lập). Chạy tươi: RERUN_FULL=1.
arm "abl1_full  (baseline)"
if [ "${RERUN_FULL:-0}" = "1" ]; then bench ""; fi
capture abl1_full

# ── các arm bỏ thành phần ──
arm "abl2_no_debugger";       bench "COMBA_USE_DEBUGGER_SLM=0";                                            capture abl2_no_debugger
arm "abl3_no_postproc";       bench "COMBA_USE_SANITIZER=0 COMBA_USE_TED=0";                               capture abl3_no_postproc
arm "abl4_no_debug_postproc"; bench "COMBA_USE_DEBUGGER_SLM=0 COMBA_USE_SANITIZER=0 COMBA_USE_TED=0";      capture abl4_no_debug_postproc

echo ""
echo "✅ Ablation xong. Snapshot tại:"
echo "   reports/abl1_full/  abl2_no_debugger/  abl3_no_postproc/  abl4_no_debug_postproc/"
echo "   → pass5_breakdown.json + analyze_syntax_*.json trong mỗi thư mục."

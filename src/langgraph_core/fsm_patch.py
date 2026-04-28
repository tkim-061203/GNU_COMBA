"""
COMBA Pipeline v5 — FSM-aware TB debugging patch
=================================================
Adds 2 new nodes and reorganises TB-failure routing to lift VE pass rate.

DROP-IN: place this file under src/langgraph_core/ and import the new nodes
into comba_nodes.py. Update build_comba_graph() in comba_pipeline.py per
the `EDGE PATCH` block at the bottom.

State machine: see accompanying widget (v5).
"""

from __future__ import annotations
import re
import os
from typing import Optional


# ══════════════════════════════════════════════════════════════
# 1. TB Failure Classifier
# ══════════════════════════════════════════════════════════════

# Heuristics ordered by specificity — first match wins
_FAILURE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("timeout",         re.compile(r"\$finish.*timeout|simulation.*hung|\$stop.*max", re.I)),
    ("fsm_state_error", re.compile(r"\bstate\b|\bfsm\b|\bcurrent_state\b|\bnext_state\b", re.I)),
    ("timing_error",    re.compile(r"setup|hold|race|posedge|negedge|cycle\s*\d+", re.I)),
    ("output_logic",    re.compile(r"output\s+\w+\s*(?:=|expected|got)", re.I)),
]

# Module-name overrides (when module name itself is the strongest signal)
_FSM_MODULE_HINTS = ("fsm_", "_fsm", "fancytimer", "count_clock", "lemmings",
                     "circuit", "gshare", "conwaylife")


def node_classify_tb(state: dict) -> dict:
    """Classify the topmost TB failure to route into the right repair path."""
    failures = state.get("ts_failures", [])
    if not failures:
        return {"failure_type": "unknown"}

    top = failures[0]
    msg = (top.get("failureContent", "") + " " +
           top.get("traceContent", "")).lower()
    mod = state.get("module_name", "").lower()

    # 1) module-name shortcut
    if any(h in mod for h in _FSM_MODULE_HINTS):
        ftype = "fsm_state_error"
    else:
        ftype = "combinational_mismatch"  # default
        for label, pat in _FAILURE_PATTERNS:
            if pat.search(msg):
                ftype = label
                break

    print(f"  🏷  classify_tb → {ftype} (module={mod})")
    return {
        "failure_type": ftype,
        "_classify_msg_sample": msg[:120],
    }


def route_after_classify_tb(state: dict) -> str:
    """FSM/timing → VCD analyzer; comb → straight to TED."""
    ft = state.get("failure_type", "unknown")
    if ft in ("fsm_state_error", "timing_error", "timeout"):
        return "node_vcd_analyzer"
    return "node_ted_tb"


# ══════════════════════════════════════════════════════════════
# 2. VCD Analyzer (extract structured state hint)
# ══════════════════════════════════════════════════════════════

try:
    from vcdvcd import VCDVCD
    _HAS_VCD = True
except ImportError:
    _HAS_VCD = False


def _find_state_signals(vcd: "VCDVCD") -> list[str]:
    """Return signal refs that look like FSM state regs."""
    cands = []
    for ref in vcd.references_to_ids.keys():
        low = ref.lower()
        if any(k in low for k in ("state", "cs", "ns", "ps")) and "_w" not in low:
            cands.append(ref)
    return cands[:4]  # cap to keep prompt small


def _state_transitions(vcd: "VCDVCD", sig: str, max_n: int = 8) -> list[tuple[int, str]]:
    """Return up to max_n (time, value) transitions for a signal."""
    try:
        tv = vcd[sig].tv
    except KeyError:
        return []
    return [(int(t), str(v)) for t, v in tv[:max_n]]


def node_vcd_analyzer(state: dict) -> dict:
    """Parse design VCD and produce a compact state-transition hint."""
    work_dir = state.get("work_dir", "")
    vcd_path = os.path.join(work_dir, "dump.vcd")

    if not _HAS_VCD or not os.path.exists(vcd_path):
        return {
            "vcd_hint": "",
            "vcd_status": "unavailable",
        }

    try:
        vcd = VCDVCD(vcd_path, store_tvs=True)
    except Exception as e:
        return {"vcd_hint": "", "vcd_status": f"parse_error: {e}"}

    sigs = _find_state_signals(vcd)
    if not sigs:
        return {"vcd_hint": "", "vcd_status": "no_state_signals"}

    lines = ["[VCD STATE TRACE]"]
    for s in sigs:
        trs = _state_transitions(vcd, s)
        if not trs:
            continue
        head = ", ".join(f"t={t}:{v}" for t, v in trs)
        lines.append(f"  {s}: {head}")

    # Pull the failure cycle if available
    fail_cycle = state.get("ts_failures", [{}])[0].get("simtime", "?")
    lines.append(f"[FAILURE_CYCLE] simtime={fail_cycle}")

    hint = "\n".join(lines)
    print(f"  📈 vcd_analyzer → {len(sigs)} state signals, hint={len(hint)}b")
    return {
        "vcd_hint": hint,
        "vcd_status": "ok",
    }


# ══════════════════════════════════════════════════════════════
# 3. Improved TED-TB (structured TDP + better EDTM key)
# ══════════════════════════════════════════════════════════════

# Replaces _ts_key in graph.py — finer-grained dedup
def _ts_key_v5(failure: dict, failure_type: str = "unknown") -> str:
    """Dedup key: (failure_type, signal_or_todo). Keeps repeated cycles
    of the same root cause from blowing past EDTM_MAX_RETRIES too fast."""
    todo = failure.get("todoNum", "")
    sig_match = re.search(r"(?:signal|output|reg|wire)\s+(\w+)",
                          failure.get("failureContent", ""), re.I)
    sig = sig_match.group(1) if sig_match else ""
    return f"{failure_type}::{todo}::{sig}"


def node_ted_tb_v5(state: dict, _legacy_node_ted_tb) -> dict:
    """Wraps the existing node_ted_tb to inject structured TDP."""
    base = _legacy_node_ted_tb(state)
    if base.get("phase") != "ts":
        return base  # unchanged on early-exit paths

    ftype = state.get("failure_type", "unknown")
    vcd_hint = state.get("vcd_hint", "")
    tdp = base.get("current_tdp", {}) or {}

    # Build structured TDP body
    parts = [
        f"[FAILURE_TYPE] {ftype}",
        f"[FAILURE] {tdp.get('failureContent','')}",
        f"[TRACE] {tdp.get('traceContent','')[:300]}",
    ]
    if vcd_hint:
        parts.append(vcd_hint)
    if ftype == "fsm_state_error":
        parts.append("[ROOT_CAUSE_HINT] check state encoding, reset value, "
                     "and transition guards in always @(posedge clk) block")
    elif ftype == "timeout":
        parts.append("[ROOT_CAUSE_HINT] design likely stuck — verify reset "
                     "deassertion path and that all FSM states have valid exits")

    tdp["structured_body"] = "\n".join(parts)
    base["current_tdp"] = tdp

    # Replace EDTM key with v5 finer-grained version
    edtm = base.get("edtm_ts", {})
    new_key = _ts_key_v5(tdp, ftype)
    edtm[new_key] = edtm.pop(_ts_key_v5(tdp, "unknown"), 0) + 1  # migrate
    base["edtm_ts"] = edtm
    return base


# ══════════════════════════════════════════════════════════════
# 4. Debugger context escalation (TS phase only)
# ══════════════════════════════════════════════════════════════

def build_ts_debug_prompt(state: dict, level: int) -> str:
    """L0..L4 — each level adds context, not just strictness."""
    tdp = state.get("current_tdp", {}) or {}
    body = tdp.get("structured_body", tdp.get("failureContent", ""))
    parts = [body]

    if level >= 1:
        parts.append("[SPEC]\n" + state.get("nl_input", "")[:600])
    if level >= 2 and state.get("vcd_hint"):
        parts.append(state["vcd_hint"])
    if level >= 3:
        parts.append("[TB REFERENCE]\n" + state.get("testbench_content", "")[:800])
    if level >= 4:
        parts.append("[INSTRUCTION] Regenerate the ENTIRE module from spec. "
                     "Do not patch — rewrite cleanly.")

    return "\n\n".join(parts)

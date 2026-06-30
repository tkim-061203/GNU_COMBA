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
import glob
from typing import Optional

# _QUIET removed; dynamically checking os.environ["COMBA_QUIET"] to prevent stale cached imports


def vcd_hint_enabled() -> bool:
    """VCD waveform hint is opt-in (default OFF).

    Empirically the populated hint LOWERED the LLM pass rate on RTLLM v1
    (91.7%→86.2%, one-directional) and was inconclusive/noise on v2. It is
    gated so it can be A/B'd without code changes. Enable with
    COMBA_VCD_HINT=1 (also accepts true/on/yes). Read live from the
    environment to avoid stale cached-import values.
    """
    return os.environ.get("COMBA_VCD_HINT", "").strip().lower() in ("1", "true", "on", "yes")


# ══════════════════════════════════════════════════════════════
# 1. TB Failure Classifier
# ══════════════════════════════════════════════════════════════

# Heuristics ordered by specificity — first match wins
_FAILURE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("timeout",         re.compile(r"\$finish.*timeout|simulation.*hung|\$stop.*max|timeout", re.I)),
    ("fsm_state_error", re.compile(r"\bstate\b|\bfsm\b|\bcurrent_state\b|\bnext_state\b", re.I)),
    ("timing_error",    re.compile(r"setup|hold|race|posedge|negedge|cycle\s*\d+", re.I)),
    ("output_logic",    re.compile(r"output\s+\w+\s*(?:=|expected|got)", re.I)),
]

# Module-name overrides (when module name itself is the strongest signal)
_FSM_MODULE_HINTS = (
    "fsm", "fifo", "counter", "div", "timer", "pulse", "detect", "pipe",
    "serial", "parallel", "generator", "traffic", "accu", "calendar",
    "edge", "sync", "width", "fancytimer", "count_clock", "lemmings",
    "circuit", "gshare", "conwaylife"
)


def _is_sequential_design(state: dict) -> bool:
    """Fallback check to identify sequential/FSM designs."""
    # 1. XML check
    xml_desc = state.get("xml_description", "")
    if xml_desc:
        if 'type="sequential' in xml_desc.lower():
            return True
        # Check for inputs like clk, clock, rst, rst_n, reset in XML
        if re.search(r'<input\s+id="[^"]*(clk|clock|rst|rst_n|reset)[^"]*"', xml_desc, re.I):
            return True

    # 2. Header check
    header = state.get("expected_header", "")
    if header:
        if re.search(r'\b(clk|clock|rst|rst_n|reset)\b', header, re.I):
            return True

    # 3. Spec check
    spec = state.get("nl_input", "")
    if spec:
        if re.search(r'\b(clk|clock|rst|rst_n|reset)\b', spec, re.I):
            return True

    # 4. GVD check (already generated verilog code)
    gvd = state.get("gvd", "")
    if gvd:
        if re.search(r'\b(clk|clock|rst|rst_n|reset|always\s*@\s*\()\b', gvd, re.I):
            return True

    return False


def node_classify_tb(state: dict) -> dict:
    """Classify the topmost TB failure to route into the right repair path."""
    tb_log = state.get("tb_log", "")
    failures = parse_ts_log(tb_log)
    if not failures:
        failures = state.get("ts_failures", [])
        
    if not failures:
        return {"failure_type": "unknown"}

    top = failures[0]
    msg = (top.get("failureContent", "") + " " +
           top.get("traceContent", "")).lower()
    mod = state.get("module_name", "").lower()

    # 1) module-name shortcut or sequential design properties
    if any(h in mod for h in _FSM_MODULE_HINTS) or _is_sequential_design(state):
        ftype = "fsm_state_error"
        for label, pat in _FAILURE_PATTERNS:
            if pat.search(msg):
                ftype = label
                break
    else:
        ftype = "combinational_mismatch"  # default
        for label, pat in _FAILURE_PATTERNS:
            if pat.search(msg):
                ftype = label
                break

    # silenced classifier print to prevent stdout log pollution
    return {
        "failure_type": ftype,
        "_classify_msg_sample": msg[:120],
    }


def route_after_classify_tb(state: dict) -> str:
    """FSM/timing/timeout → VCD analyzer; combinational → straight to TED.

    When the VCD hint is disabled (default), skip the analyzer entirely so the
    debugger runs on the original log-only context — the configuration that
    benchmarked best.
    """
    ft = state.get("failure_type", "unknown")
    if ft in ("fsm_state_error", "timing_error", "timeout"):
        if not vcd_hint_enabled():
            return "node_ted_tb"
        work_dir = state.get("work_dir", "")
        if work_dir:
            vcd_files = glob.glob(os.path.join(work_dir, "*.vcd"))
            if not vcd_files:
                vcd_files = glob.glob(os.path.join(os.path.dirname(work_dir), "*.vcd"))
            if vcd_files:
                return "node_vcd_analyzer"
        return "node_ted_tb"  # Fallback if no VCD file is available
    return "node_ted_tb"


# ══════════════════════════════════════════════════════════════
# 2. VCD Analyzer (extract structured state hint and waveform trace)
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


def _get_vcd_val_at(vcd: "VCDVCD", sig: str, T: int) -> str:
    try:
        tv = vcd[sig].tv
    except (KeyError, AttributeError):
        return "x"
    last_val = "x"
    for t, v in tv:
        if t > T:
            break
        last_val = v
    return str(last_val)


def _format_value(val_str: str) -> str:
    s = val_str.lower()
    if s.startswith('b'):
        s = s[1:]
    if not s:
        return "x"
    if any(c in s for c in ('x', 'z', 'u', 'w')):
        return val_str
    if len(s) == 1:
        return s
    try:
        val_int = int(s, 2)
        hex_len = (len(s) + 3) // 4
        return f"{hex_len}'h{val_int:0{hex_len}x}"
    except ValueError:
        return val_str


def node_vcd_analyzer(state: dict) -> dict:
    """Parse design VCD and produce a compact state-transition hint."""
    work_dir = state.get("work_dir", "")
    
    # 1. Find VCD file
    vcd_files = []
    if work_dir:
        vcd_files = glob.glob(os.path.join(work_dir, "*.vcd"))
        if not vcd_files:
            vcd_files = glob.glob(os.path.join(os.path.dirname(work_dir), "*.vcd"))
    
    if not _HAS_VCD or not vcd_files:
        return {
            "vcd_hint": "",
            "vcd_status": "unavailable",
        }
        
    vcd_path = vcd_files[0]
    try:
        vcd = VCDVCD(vcd_path, store_tvs=True)
    except Exception as e:
        return {"vcd_hint": "", "vcd_status": f"parse_error: {e}"}

    # An aborted testbench can leave a 0-byte / headerless VCD with no signals.
    # Report that honestly instead of emitting a hollow "ok" hint with no data.
    if not vcd.references_to_ids:
        return {"vcd_hint": "", "vcd_status": "empty"}

    # 2. Extract mismatch time from tb_log
    tb_log = state.get("tb_log", "")
    mismatch_match = re.search(r"(?:First mismatch occurred at time|failed at simtime|at time)\s*(\d+)", tb_log, re.I)
    t_mismatch = int(mismatch_match.group(1)) if mismatch_match else None

    # 3. Find clock signal
    clk_sig = None
    for ref in vcd.references_to_ids.keys():
        parts = ref.split('.')
        name = parts[-1].lower()
        if name in ("clk", "clock"):
            clk_sig = ref
            break
    if not clk_sig:
        for ref in vcd.references_to_ids.keys():
            if "clk" in ref.lower() or "clock" in ref.lower():
                clk_sig = ref
                break

    # 4. Find all signals, prioritizing top-level and mismatch output
    all_refs = list(vcd.references_to_ids.keys())
    
    # Identify the failing output signal(s). RTLLM C++ testbenches name them in
    # the assertion ("tx->NAME == ...") and in "OUTPUT TRACE: tx->NAME = ..."
    # lines; VerilogEval-style logs use "Output 'NAME' has N mismatches".
    fail_out_names = {m.lower() for m in re.findall(r"tx->(\w+)", tb_log)}
    vm = re.search(r"Output\s+'([^']+)'\s+has\s+\d+\s+mismatches", tb_log, re.I)
    if vm:
        fail_out_names.add(vm.group(1).lower())

    clk_leaf = clk_sig.split('.')[-1].lower() if clk_sig else None

    def _is_constant(ref: str) -> bool:
        """A signal that never changes value across the whole sim (params,
        localparams, genvars). A waveform conveys nothing for these."""
        try:
            tv = vcd[ref].tv
        except (KeyError, AttributeError):
            return True
        return len({str(v) for _, v in tv}) <= 1

    # Prioritize the failing outputs and top-level ports; demote everything else.
    pri_refs = []
    other_refs = []
    for ref in all_refs:
        if ref == clk_sig:
            continue
        parts = ref.split('.')
        name = parts[-1]
        low = name.lower()

        # Skip the clock (shown in its own column) and Verilator temporaries.
        if low == clk_leaf or name.startswith('_') or '__' in ref:
            continue

        is_fail = any(fn == low or fn in low for fn in fail_out_names)
        # Lean hint: drop signals that never change — pure noise in a waveform —
        # unless they are the failing output we were asked to inspect.
        if not is_fail and _is_constant(ref):
            continue

        is_pri = is_fail or len(parts) <= 2
        (pri_refs if is_pri else other_refs).append(ref)

    # De-duplicate by leaf signal name — the same net usually appears at both the
    # TB-top and DUT scope; keep the deepest scope (the DUT's own reg/wire).
    def _dedup_by_leaf(refs: list) -> dict:
        best: dict = {}
        for r in refs:
            leaf = r.split('.')[-1].lower()
            if leaf not in best or r.count('.') > best[leaf].count('.'):
                best[leaf] = r
        return best

    # Keep the trace focused: failing signals first, then a few changing ports.
    chosen = _dedup_by_leaf(pri_refs)
    for leaf, r in sorted(_dedup_by_leaf(other_refs).items()):
        if leaf not in chosen and len(chosen) < 8:
            chosen[leaf] = r
    trace_sigs = sorted(chosen.values())[:8]

    # 5. Determine sampling times
    clk_transitions = []
    if clk_sig:
        try:
            tv = vcd[clk_sig].tv
            prev_val = None
            for t, val in tv:
                val_str = str(val)
                if prev_val == '0' and val_str == '1':
                    clk_transitions.append(t)
                prev_val = val_str
        except Exception:
            pass

    if not clk_transitions:
        if t_mismatch is not None:
            clk_transitions = list(range(max(0, t_mismatch - 50), t_mismatch + 15, 10))
        else:
            all_times = set()
            for ref in trace_sigs[:5]:
                try:
                    for t, v in vcd[ref].tv:
                        all_times.add(t)
                except Exception:
                    pass
            clk_transitions = sorted(list(all_times))[-10:]

    # Sample around t_mismatch
    if t_mismatch is not None:
        idx = len(clk_transitions)
        for i, t in enumerate(clk_transitions):
            if t >= t_mismatch:
                idx = i
                break
        start_idx = max(0, idx - 5)
        end_idx = min(len(clk_transitions), idx + 3)
        sample_times = clk_transitions[start_idx:end_idx]
    else:
        sample_times = clk_transitions[-8:]

    # Ensure the exact mismatch time is represented even if it falls between
    # sampled clock edges, so the (MIS) row reflects the actual failing cycle.
    if t_mismatch is not None and t_mismatch not in sample_times:
        sample_times = sorted(set(sample_times) | {t_mismatch})

    # 6. Generate state transition hint and waveform trace
    lines = []
    
    # Add legacy state transitions if FSM signals exist
    state_sigs = []
    for ref in all_refs:
        low = ref.lower()
        if any(k in low for k in ("state", "cs", "ns", "ps")) and "_w" not in low:
            state_sigs.append(ref)
    
    if state_sigs:
        lines.append("[VCD STATE TRANSITIONS]")
        for s in state_sigs[:4]:
            trs = _state_transitions(vcd, s)
            if trs:
                head = ", ".join(f"t={t}:{_format_value(v)}" for t, v in trs)
                lines.append(f"  {s}: {head}")
        lines.append("")

    # Add text-based waveform table
    if sample_times and trace_sigs:
        lines.append("[VCD WAVEFORM TRACE AROUND MISMATCH]")
        headers = ["Time"]
        if clk_sig:
            headers.append(clk_sig.split('.')[-1])
        for sig in trace_sigs:
            headers.append(sig.split('.')[-1])
            
        col_widths = [len(h) for h in headers]
        col_widths[0] = max(col_widths[0], 12)
        
        rows_data = []
        for t in sample_times:
            row = []
            is_mis = (t_mismatch is not None and t == t_mismatch)
            time_str = f"{t} (MIS)" if is_mis else str(t)
            row.append(time_str)
            
            if clk_sig:
                row.append(_format_value(_get_vcd_val_at(vcd, clk_sig, t)))
                
            for sig in trace_sigs:
                row.append(_format_value(_get_vcd_val_at(vcd, sig, t)))
                
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(val))
            rows_data.append(row)
            
        header_line = " | ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
        lines.append(header_line)
        lines.append("-" * len(header_line))
        for row in rows_data:
            lines.append(" | ".join(f"{val:<{col_widths[i]}}" for i, val in enumerate(row)))
            
    if t_mismatch is not None:
        lines.append(f"[FAILURE_CYCLE] simtime={t_mismatch}")
    else:
        lines.append("[FAILURE_CYCLE] simtime=unknown")

    hint = "\n".join(lines)
    # silenced analyzer print to prevent stdout log pollution
    return {
        "vcd_hint": hint,
        "vcd_status": "ok",
    }


# ══════════════════════════════════════════════════════════════
# 3. Improved TED-TB (structured TDP + better EDTM key)
# ══════════════════════════════════════════════════════════════

# Regex patterns for parsing TS log
TS_TODO_PATTERN = re.compile(
    r'(TODO\s*(?:Block\s*)?(\d+).*?(?:Expected|FAIL|Error|Mismatch).*?)(?=TODO|$)',
    re.DOTALL | re.IGNORECASE,
)
TS_SIMPLE_PATTERN = re.compile(
    r'(?:FAIL|ERROR|Mismatch|Assertion|TIMEOUT).*', re.MULTILINE | re.IGNORECASE,
)

def parse_ts_log(raw_log: str) -> list[dict]:
    out = []
    for m in TS_TODO_PATTERN.finditer(raw_log):
        out.append({"todoNum": int(m.group(2)),
                     "traceContent": m.group(1).strip()[:500],
                     "failureContent": m.group(1).strip()[:200]})
    if not out:
        for m in TS_SIMPLE_PATTERN.finditer(raw_log):
            out.append({"todoNum": 0,
                         "traceContent": m.group(0).strip()[:500],
                         "failureContent": m.group(0).strip()[:200]})
    return out

# Replaces _ts_key in graph.py — finer-grained dedup
def _ts_key_v5(failure: dict, failure_type: str = "unknown") -> str:
    """Dedup key: (failure_type, signal_or_todo). Keeps repeated cycles
    of the same root cause from blowing past EDTM_MAX_RETRIES too fast."""
    todo = failure.get("todoNum", "")
    sig_match = re.search(r"(?:signal|output|reg|wire)\s+(\w+)",
                          failure.get("failureContent", ""), re.I)
    sig = sig_match.group(1) if sig_match else ""
    return f"TB:{failure_type}::{todo}::{sig}"


def node_ted_tb_v5(state: dict, _legacy_node_ted_tb) -> dict:
    """Wraps the existing node_ted_tb to inject structured TDP."""
    base = _legacy_node_ted_tb(state)
    if base.get("phase") != "ts":
        return base  # unchanged on early-exit paths

    # If it is a fast-path fix (wire l-value or port mismatch), preserve it completely!
    legacy_tdp = base.get("tdp", "")
    if "[WIRE L-VALUE FIX REQUIRED]" in legacy_tdp or "[PORT MISMATCH DETECTED]" in legacy_tdp:
        return base

    ftype = state.get("failure_type", "unknown")
    vcd_hint = state.get("vcd_hint", "")
    
    # Correctly parse the topmost failure from state["tb_log"]
    tb_log = state.get("tb_log", "")
    failures = parse_ts_log(tb_log)
    if failures:
        tdp_dict = failures[0]
    else:
        tdp_dict = {
            "todoNum": 0,
            "failureContent": state.get("tb_failure", "Unknown testbench failure"),
            "traceContent": ""
        }

    new_key = _ts_key_v5(tdp_dict, ftype)

    # Re-extract all debug traces from tb_log to avoid truncated patterns
    trace_lines = []
    for line in tb_log.splitlines():
        if any(w in line for w in ("TRACE", "INPUT", "OUTPUT", "Assertion", "Failed")):
            trace_lines.append(line.strip())
    full_trace_str = "\n".join(trace_lines)

    # Build structured TDP body
    first_line = f"[FAILURE_TYPE] {ftype} (key: {new_key})"
    parts = [
        first_line,
        f"[FAILURE] {tdp_dict.get('failureContent','')}",
        f"[TRACE]\n{full_trace_str}",
    ]
    if vcd_hint:
        parts.append(vcd_hint)
    if ftype == "fsm_state_error":
        parts.append("[ROOT_CAUSE_HINT] check state encoding, reset value, "
                     "and transition guards in always @(posedge clk) block")
    elif ftype == "timeout":
        parts.append("[ROOT_CAUSE_HINT] design likely stuck — verify reset "
                     "deassertion path and that all FSM states have valid exits")

    # Append testbench reference snippet if it was extracted by legacy node
    if "Testbench Reference Snippet:" in legacy_tdp:
        tb_ref_part = legacy_tdp.split("Testbench Reference Snippet:", 1)[1].strip()
        parts.append(f"[TESTBENCH_REFERENCE]\n{tb_ref_part}")

    structured_body = "\n\n".join(parts)
    
    # Store structured_body in base["tdp"] so the debugger node receives it
    base["tdp"] = structured_body
    base["current_tdp"] = {"structured_body": structured_body}
    base["current_error_key"] = new_key

    # Re-calculate the legacy sig_tb so we can pop/migrate it in the EDTM tracking
    topmost_failure_legacy = ""
    for line in tb_log.splitlines():
        stripped = line.strip()
        if re.search(r'TODO\s+\d+\s+Failed', stripped):
            topmost_failure_legacy = stripped
            break
        if "Assertion" in stripped and "failed" in stripped.lower():
            topmost_failure_legacy = stripped
            break
    if not topmost_failure_legacy:
        topmost_failure_legacy = state.get("tb_failure", "Unknown testbench failure")

    legacy_sig = "TB:" + re.sub(r'\d+', 'N', topmost_failure_legacy).strip()
    legacy_sig = re.sub(r'\s+', ' ', legacy_sig)

    edtm = base.get("edtm", {})
    val = edtm.pop(legacy_sig, 1)
    edtm[new_key] = edtm.get(new_key, 0) + val
    base["edtm"] = edtm
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

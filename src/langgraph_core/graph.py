"""
COMBA-PROMPT LangGraph — Full Graph Definition
================================================
7 nodes · 5 conditional edges · EDTM · Rollback · Iteration Control · FR

State Machine (see state_machine diagram):
  START → converter → [XML valid?] → generator → syntax_check
    Ⓐ SC pass? → YES → tb_sim → Ⓑ TS pass? → YES → END
    Ⓐ SC fail? → ted_syntax → [limit?] → correcter ↻ syntax_check
    Ⓑ TS fail? → ted_tb     → [limit?] → correcter ↻ syntax_check

Usage:
    from graph import build_graph
    app = build_graph(llm_interface)
    result = app.invoke(initial_state)
"""

from __future__ import annotations
import re, os, copy, logging, subprocess, tempfile
from typing import TypedDict, Any

from langgraph.graph import StateGraph, END
from prompts import build_generation_prompt, build_edp_prompt

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. STATE SCHEMA
# ═══════════════════════════════════════════════════════════════

class COMBAState(TypedDict, total=False):
    # Input
    nl_input: str
    xml_description: str
    xml_valid: bool
    xml_retry_count: int
    xml_retry_limit: int
    # Design Assets
    testbench_path: str
    testbench_content: str
    custom_vector: dict
    module_name: str
    # Generated Code
    gvd: str
    sgvd_versions: list              # SGVD history for Rollback
    # SC
    sc_log: str
    sc_exceptions: list
    sc_has_errors: bool
    # TS
    ts_log: str
    ts_failures: list
    ts_has_failures: bool
    # TED prompts
    current_edp: dict
    current_tdp: dict
    # EDTM
    edtm_sc: dict                    # {key: trialTimes}
    edtm_ts: dict
    # Iteration Control
    iteration_count: int
    iteration_limit: int
    sc_trial_limit: int
    ts_trial_limit: int
    # Rollback
    rollback_enabled: bool
    prev_sc_exception_count: int
    # Phase
    phase: str                       # generation|sc|ts|debug_sc|debug_ts|done
    stop_reason: str
    # Metrics (FR)
    total_sc_exceptions: int
    fixed_sc_exceptions: int
    total_ts_failures: int
    fixed_ts_failures: int


# ═══════════════════════════════════════════════════════════════
# 2. REGEX PARSERS
# ═══════════════════════════════════════════════════════════════

SC_PATTERN = re.compile(
    r'%(Error|Warning)(-(\w+))?:\s*([^:]+):(\d+):\d*:?\s*(.*)',
    re.MULTILINE,
)

def parse_sc_log(raw_log: str) -> list[dict]:
    out = []
    for m in SC_PATTERN.finditer(raw_log):
        out.append({
            "exceptionType": m.group(1),
            "exceptionTitle": m.group(3) or "",
            "exceptionContent": m.group(6).strip(),
            "logContent": f"{m.group(4)}:{m.group(5)}",
        })
    return out

TS_TODO_PATTERN = re.compile(
    r'(TODO\s*(?:Block\s*)?(\d+).*?(?:Expected|FAIL|Error|Mismatch).*?)(?=TODO|$)',
    re.DOTALL | re.IGNORECASE,
)
TS_SIMPLE_PATTERN = re.compile(
    r'(?:FAIL|ERROR|Mismatch|Assertion).*', re.MULTILINE | re.IGNORECASE,
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


# ═══════════════════════════════════════════════════════════════
# 3. VERILATOR WRAPPER
# ═══════════════════════════════════════════════════════════════

def _mod_name(code: str) -> str:
    m = re.search(r'module\s+(\w+)', code)
    return m.group(1) if m else "design"

def run_verilator_sc(code: str, work_dir: str | None = None) -> dict:
    wd = work_dir or tempfile.mkdtemp(prefix="comba_sc_")
    fp = os.path.join(wd, "design.v")
    with open(fp, "w") as f: f.write(code)
    try:
        r = subprocess.run(["verilator", "--lint-only", "-Wall", fp],
                           capture_output=True, text=True, timeout=30, cwd=wd)
        raw = (r.stdout or "") + (r.stderr or "")
        return {"success": "%Error" not in raw, "raw_log": raw}
    except FileNotFoundError:
        return {"success": False, "raw_log": "%Error: verilator not found"}
    except subprocess.TimeoutExpired:
        return {"success": False, "raw_log": "%Error: verilator timeout"}

def run_verilator_ts(code: str, tb_path: str, work_dir: str | None = None) -> dict:
    wd = work_dir or tempfile.mkdtemp(prefix="comba_ts_")
    fp = os.path.join(wd, "design.v")
    with open(fp, "w") as f: f.write(code)
    mod = _mod_name(code)
    try:
        comp = subprocess.run(
            ["verilator", "--cc", "--exe", "--build", "-Wall", "-Wno-fatal",
             "--top-module", mod, fp, tb_path],
            capture_output=True, text=True, timeout=60, cwd=wd)
        if comp.returncode != 0 and "%Error" in (comp.stderr or ""):
            return {"success": False, "raw_log": (comp.stdout or "") + (comp.stderr or "")}
        exe = os.path.join(wd, f"obj_dir/V{mod}")
        if not os.path.exists(exe):
            return {"success": False, "raw_log": f"%Error: exe {exe} not found"}
        run = subprocess.run([exe], capture_output=True, text=True, timeout=30, cwd=wd)
        raw = (run.stdout or "") + (run.stderr or "")
        fail = any(k in raw.lower() for k in ["fail", "error", "mismatch", "assertion"])
        return {"success": not fail, "raw_log": raw}
    except Exception as e:
        return {"success": False, "raw_log": f"%Error: {e}"}


# ═══════════════════════════════════════════════════════════════
# 4. EDTM
# ═══════════════════════════════════════════════════════════════

def _sc_key(e): return f"{e.get('exceptionType','')}_{e.get('exceptionTitle','')}_{e.get('exceptionContent','')[:60]}"
def _ts_key(f): return f"{f.get('todoNum',0)}_{f.get('failureContent','')[:60]}"
def _edtm_inc(d, k): d[k] = d.get(k, 0) + 1; return d[k]
def _edtm_over(d, k, lim): return d.get(k, 0) >= lim


# ═══════════════════════════════════════════════════════════════
# 5. ROLLBACK
# ═══════════════════════════════════════════════════════════════

def _should_rollback(state, new_exc_count):
    if not state.get("rollback_enabled"): return False
    if not state.get("sgvd_versions"): return False
    return new_exc_count > state.get("prev_sc_exception_count", 999)

def _do_rollback(state):
    v = state.get("sgvd_versions", [])
    return v[-1] if v else state.get("gvd", "")

def _save_sgvd(state):
    v = list(state.get("sgvd_versions", []))
    v.append(state["gvd"])
    return v


# ═══════════════════════════════════════════════════════════════
# 6. CUSTOM VECTORS
# ═══════════════════════════════════════════════════════════════

CUSTOM_VECTORS = {
    "WIDTHEXPAND":    "Bit width expansion — LHS/RHS widths should match.",
    "WIDTHTRUNC":     "Bit width truncation — check port widths.",
    "UNUSEDSIGNAL":   "Signal declared but never read.",
    "UNOPTFLAT":      "Combinational loop or unoptimizable.",
    "BLKANDNBLK":     "Mixed blocking/non-blocking on same signal.",
    "PROCASSWIRE":    "Wire in procedural block — use reg.",
    "UNDRIVEN":       "Signal never assigned.",
    "MULTIDRIVEN":    "Signal driven from multiple always blocks.",
    "PINMISSING":     "Missing port connection in instantiation.",
    "CASEINCOMPLETE": "Case missing default.",
    "LATCH":          "Inferred latch — add else/default.",
}


# ═══════════════════════════════════════════════════════════════
# 7. VERILOG EXTRACTION
# ═══════════════════════════════════════════════════════════════

def _extract_verilog(raw: str) -> str:
    m = re.search(r'```(?:verilog|v)?\s*\n(.*?)```', raw, re.DOTALL)
    if m: return m.group(1).strip()
    m = re.search(r'(module\s+\w+.*?endmodule)', raw, re.DOTALL)
    if m: return m.group(1).strip()
    return raw.strip()


# ═══════════════════════════════════════════════════════════════
# 8. NODE DEFINITIONS (7 nodes)
# ═══════════════════════════════════════════════════════════════

def _make_nodes(llm):
    """llm.generate(messages, model="base"|"lora") -> str"""

    def node_converter(state: COMBAState) -> dict:
        nl = state["nl_input"]
        if nl.strip().startswith("<module"):
            return {"xml_description": nl, "xml_valid": True, "phase": "generation"}
        msgs = [
            {"role": "system", "content":
             "Convert hardware description to COMBA XML. Tags: <module>, <ports>, "
             "<logic_description>, <implementation>. Output ONLY valid XML."},
            {"role": "user", "content": nl},
        ]
        xml = llm.generate(msgs, model="base")
        ok = "<module" in xml and "</module>" in xml
        return {"xml_description": xml, "xml_valid": ok,
                "xml_retry_count": state.get("xml_retry_count", 0) + (0 if ok else 1),
                "phase": "generation" if ok else "xml_retry"}

    def node_generator(state: COMBAState) -> dict:
        raw = llm.generate(build_generation_prompt(state["xml_description"]), model="base")
        code = _extract_verilog(raw)
        return {"gvd": code, "module_name": _mod_name(code), "sgvd_versions": [],
                "phase": "sc", "iteration_count": 0,
                "total_sc_exceptions": 0, "fixed_sc_exceptions": 0,
                "total_ts_failures": 0, "fixed_ts_failures": 0,
                "edtm_sc": {}, "edtm_ts": {},
                "rollback_enabled": False, "prev_sc_exception_count": 999}

    def node_syntax_check(state: COMBAState) -> dict:
        res = run_verilator_sc(state["gvd"])
        excs = parse_sc_log(res["raw_log"])
        n = len(excs)
        has = n > 0

        # Rollback?
        if _should_rollback(state, n):
            logger.info("ROLLBACK → revert SGVD")
            rolled = _do_rollback(state)
            return {"gvd": rolled, "sc_log": res["raw_log"],
                    "sc_exceptions": parse_sc_log(run_verilator_sc(rolled)["raw_log"]),
                    "sc_has_errors": has, "phase": "sc"}

        # Track fixed: prev had errors, now fewer = some fixed
        prev_n = state.get("prev_sc_exception_count", 999)
        fixed_delta = max(0, prev_n - n) if prev_n < 999 else 0

        return {"sc_log": res["raw_log"], "sc_exceptions": excs,
                "sc_has_errors": has, "prev_sc_exception_count": n,
                "fixed_sc_exceptions": state.get("fixed_sc_exceptions", 0) + fixed_delta}

    def node_ted_syntax(state: COMBAState) -> dict:
        excs = state.get("sc_exceptions", [])
        edtm = dict(state.get("edtm_sc", {}))
        lim = state.get("sc_trial_limit", 5)
        top = None
        for e in excs:
            k = _sc_key(e)
            if not _edtm_over(edtm, k, lim):
                top = e; break
        if not top:
            return {"phase": "done", "stop_reason": "all_sc_exceeded"}
        _edtm_inc(edtm, _sc_key(top))
        cv = CUSTOM_VECTORS.get(top.get("exceptionTitle", ""), "")
        return {"current_edp": {**top, "custom_vector": cv}, "edtm_sc": edtm,
                "total_sc_exceptions": state.get("total_sc_exceptions", 0) + 1,
                "phase": "debug_sc"}

    def node_correcter(state: COMBAState) -> dict:
        phase = state["phase"]
        gvd = state["gvd"]
        if phase == "debug_sc":
            edp = state["current_edp"]
            msgs = build_edp_prompt(
                module_name=state.get("module_name", "design"), gvd=gvd,
                exceptionType=edp.get("exceptionType", ""),
                exceptionTitle=edp.get("exceptionTitle", ""),
                exceptionContent=edp.get("exceptionContent", ""),
                logContent=edp.get("logContent", ""),
                custom_vector=edp.get("custom_vector", ""),
                sc_log=state.get("sc_log", ""),
                trial=state.get("iteration_count", 0) + 1,
                max_trial=state.get("iteration_limit", 20))
        else:
            tdp = state["current_tdp"]
            msgs = [
                {"role": "system", "content":
                 "You are a Verilog debugging expert. Fix testbench failure. "
                 "Return ONLY corrected Verilog code."},
                {"role": "user", "content":
                 f"Module: {state.get('module_name','design')}\n"
                 f"Code:\n```verilog\n{gvd}\n```\n"
                 f"TB Failure: TODO {tdp.get('todoNum','')}\n"
                 f"Trace: {tdp.get('traceContent','')}\n"
                 f"Failure: {tdp.get('failureContent','')}\n"
                 f"TB ref:\n{state.get('testbench_content','N/A')}\n"
                 f"Fix and return complete corrected Verilog."},
            ]
        raw = llm.generate(msgs, model="lora")
        fixed = _extract_verilog(raw)
        return {"gvd": fixed, "sgvd_versions": _save_sgvd(state),
                "iteration_count": state.get("iteration_count", 0) + 1,
                "rollback_enabled": True, "phase": "sc"}

    def node_tb_sim(state: COMBAState) -> dict:
        tb = state.get("testbench_path", "")
        if not tb or not os.path.exists(tb):
            return {"ts_log": "", "ts_failures": [], "ts_has_failures": False,
                    "phase": "done", "stop_reason": "no_testbench"}
        versions = _save_sgvd(state)
        res = run_verilator_ts(state["gvd"], tb)
        fails = parse_ts_log(res["raw_log"])
        return {"ts_log": res["raw_log"], "ts_failures": fails,
                "ts_has_failures": len(fails) > 0, "sgvd_versions": versions}

    def node_ted_tb(state: COMBAState) -> dict:
        fails = state.get("ts_failures", [])
        edtm = dict(state.get("edtm_ts", {}))
        lim = state.get("ts_trial_limit", 5)
        top = None
        for f in fails:
            k = _ts_key(f)
            if not _edtm_over(edtm, k, lim):
                top = f; break
        if not top:
            return {"phase": "done", "stop_reason": "all_ts_exceeded"}
        _edtm_inc(edtm, _ts_key(top))
        tb_content = ""
        tb = state.get("testbench_path", "")
        if tb and os.path.exists(tb):
            try: tb_content = open(tb).read()
            except: pass
        return {"current_tdp": top, "testbench_content": tb_content,
                "edtm_ts": edtm,
                "total_ts_failures": state.get("total_ts_failures", 0) + 1,
                "phase": "debug_ts"}

    return dict(converter=node_converter, generator=node_generator,
                syntax_check=node_syntax_check, ted_syntax=node_ted_syntax,
                correcter=node_correcter, tb_sim=node_tb_sim, ted_tb=node_ted_tb)


# ═══════════════════════════════════════════════════════════════
# 9. CONDITIONAL EDGES
# ═══════════════════════════════════════════════════════════════

def _route_converter(s):
    if s.get("xml_valid"): return "generator"
    if s.get("xml_retry_count", 0) >= s.get("xml_retry_limit", 3): return END
    return "converter"

def _route_sc(s):
    if not s.get("sc_has_errors", True): return "tb_sim"
    if s.get("iteration_count", 0) >= s.get("iteration_limit", 20): return END
    return "ted_syntax"

def _route_ts(s):
    if not s.get("ts_has_failures", True): return END
    if s.get("iteration_count", 0) >= s.get("iteration_limit", 20): return END
    return "ted_tb"

def _route_ted_sc(s):
    return END if s.get("phase") == "done" else "correcter"

def _route_ted_ts(s):
    return END if s.get("phase") == "done" else "correcter"


# ═══════════════════════════════════════════════════════════════
# 10. GRAPH BUILDER
# ═══════════════════════════════════════════════════════════════

def build_graph(llm) -> Any:
    """Build COMBA LangGraph. llm needs .generate(msgs, model=)."""
    nodes = _make_nodes(llm)
    wf = StateGraph(COMBAState)

    for name, fn in nodes.items():
        wf.add_node(name, fn)

    wf.set_entry_point("converter")

    wf.add_conditional_edges("converter", _route_converter,
        {"generator": "generator", "converter": "converter", END: END})
    wf.add_edge("generator", "syntax_check")
    wf.add_conditional_edges("syntax_check", _route_sc,
        {"tb_sim": "tb_sim", "ted_syntax": "ted_syntax", END: END})
    wf.add_conditional_edges("ted_syntax", _route_ted_sc,
        {"correcter": "correcter", END: END})
    wf.add_edge("correcter", "syntax_check")
    wf.add_conditional_edges("tb_sim", _route_ts,
        {"ted_tb": "ted_tb", END: END})
    wf.add_conditional_edges("ted_tb", _route_ted_ts,
        {"correcter": "correcter", END: END})

    return wf.compile()


# ═══════════════════════════════════════════════════════════════
# 11. FIX RATE CALCULATOR
# ═══════════════════════════════════════════════════════════════

def calculate_fix_rate(result: COMBAState) -> dict:
    """FR_i = fixed / total for one design."""
    tsc = result.get("total_sc_exceptions", 0)
    fsc = result.get("fixed_sc_exceptions", 0)
    tts = result.get("total_ts_failures", 0)
    fts = result.get("fixed_ts_failures", 0)
    return {
        "sc_fix_rate": (fsc / tsc) if tsc > 0 else 1.0,
        "ts_fix_rate": (fts / tts) if tts > 0 else 1.0,
        "total_sc": tsc, "fixed_sc": fsc,
        "total_ts": tts, "fixed_ts": fts,
    }
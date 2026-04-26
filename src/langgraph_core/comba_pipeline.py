"""
COMBA-PROMPT Full Verification Pipeline v4 — LangGraph Implementation.

11 nodes, 7 conditional edges, Do-No-Harm Guard, EDTM, Iteration Control.

v4 Changes (vs v3):
  - Added node_guard_sc + node_guard_ts: do-no-harm guards that compare
    debugger candidate vs pre-debugger snapshot, rollback on regression
  - Terminal nodes now restore baseline GVD if it scores better
  - bad_streak counter stops debug loop after 2 consecutive rollbacks
  - Removed dead code (route_after_patcher, references to non-existent nodes)

Flow:
  NL → [Converter] → XML → [Generator] → [Sanitizer]
    → [SC] → [GUARD_SC] → pass? → [TB] → [GUARD_TS] → pass? → END ✅
                     │ fail              │ fail
                     ↓                   ↓
                [TED_SC]→[Debugger]→[Sanitizer]→[SC]→[GUARD_SC] (loop)
                                  [TED_TB]→[Debugger]→[Sanitizer]→[SC]→[GUARD_SC] (loop)

Guard logic:
  - Source=generator → guard noop, baseline locked
  - Source=debugger  → compare cand vs prev snapshot, rollback if regressed
  - bad_streak ≥ 2   → stop loop, terminal fallback to baseline if better

Usage:
  python comba_pipeline.py "Design an 8-bit adder"
  python -m pytest test_pipeline.py -v
"""

import os
import re
import json
import subprocess
import shutil
import tempfile
from typing import Optional
from typing_extensions import TypedDict

COMBA_QUIET = os.environ.get("COMBA_QUIET", "0") == "1"

def cprint(*args, **kwargs):
    if not COMBA_QUIET:
        print(*args, **kwargs)

from langgraph.graph import StateGraph, START, END

from prompts import (
    converterPromptTemplate,
    generatorPromptTemplate,
    edpPromptTemplate,
    tdpPromptTemplate,
)

from multi_attempt import (
    MultiAttemptManager,
    DebugPhase,
    EscalationLevel,
)
from verilog_sanitizer import sanitize as verilog_sanitize

# ──────────────────────────────────────────────────────────────
# Configuration Constants
# ──────────────────────────────────────────────────────────────
MAX_SC_TRIALS = 10        # Max syntax-check correction cycles
MAX_TS_TRIALS = 5         # Max testbench correction cycles
MAX_TOTAL_ITER = 20       # Absolute hard cap on total iterations
EDTM_MAX_RETRIES = 3      # Max retries for the same exception signature
GUARD_MAX_BAD_STREAK = 2  # Max consecutive rollbacks before stop

# iverilog flags for syntax-check (lint-only)
IVERILOG_SC_FLAGS = ["-tnull", "-Wno-timescale", "-Wno-implicit", "-g2012"]

# iverilog flags for testbench simulation
IVERILOG_TS_FLAGS = ["-Wall", "-Winfloop", "-Wno-timescale", "-g2012"]

# Verilator flags for SV-testbench simulation (no C++ wrapper, auto-binary mode)
VERILATOR_TS_FLAGS = [
    "--binary",                  # build-and-run mode (verilator >= 5.x)
    "--timing",                  # support always #N delays
    "-Wall", "-Wno-fatal",
    "-Wno-WIDTH", "-Wno-UNUSED", "-Wno-DECLFILENAME",
    "-Wno-MULTIDRIVEN", "-Wno-CASEINCOMPLETE",
]

# Simulator selection:
#   "iverilog" — always use Icarus Verilog (default, fastest)
#   "verilator" — always use Verilator (better for SV, slower compile)
#   "auto"     — RTLLM dataset → verilator, VerilogEval → iverilog
TS_SIMULATOR = os.environ.get("COMBA_TS_SIMULATOR", "iverilog").lower()

# VerilogEval: task_description max chars sent to debugger
_MAX_TASK_DESC_CHARS = 400


# ── Shared error-key normalizer ──
_LINE_NUM_RE = re.compile(r'(?<=:)\d+(?=:)')
_SPACES_RE = re.compile(r'\s+')

def _normalize_error_key(s: str, max_len: int = 100) -> str:
    """Canonical EDTM key: strip line numbers, collapse whitespace, truncate."""
    s = _LINE_NUM_RE.sub('N', s)
    s = _SPACES_RE.sub(' ', s).strip()
    return s[:max_len]


# ── Precise iverilog error counter ──
_IVERILOG_ERROR_RE = re.compile(
    r'^[^:\n]+:\d+:\s*error:',
    re.MULTILINE | re.IGNORECASE,
)

def _count_iverilog_errors(log: str) -> int:
    """Count genuine iverilog error lines only (ignores warning: lines)."""
    return len(_IVERILOG_ERROR_RE.findall(log))


# ── Wire l-value port extractor ──
_WIRE_LVALUE_RE = re.compile(
    r'error:\s+(\w+)\s+is not a valid l-value',
    re.IGNORECASE,
)

def _extract_wire_lvalue_ports(log: str) -> list[str]:
    """Parse iverilog TB log for wire l-value errors → output ports needing 'reg'."""
    seen: dict[str, int] = {}
    for m in _WIRE_LVALUE_RE.finditer(log):
        name = m.group(1)
        seen[name] = seen.get(name, 0) + 1
    return sorted(seen.keys())


# ── Port mismatch extractor ──
def _extract_port_mismatch(log: str) -> list[str]:
    """Extract missing port names from Verilator/Icarus error logs."""
    verilator_re = re.compile(r"no member named [‘'\"`]([a-zA-Z0-9_]+)[’'\"`]")
    icarus_re = re.compile(r"port '([a-zA-Z0-9_]+)' is not a port of")

    ports = set()
    for m in verilator_re.finditer(log):
        ports.add(m.group(1))
    for m in icarus_re.finditer(log):
        ports.add(m.group(1))
    return sorted(list(ports))


# ── XML Header Synthesizer ──
def _build_header_from_xml(xml_text: str) -> Optional[str]:
    """Synthesize a Verilog module header from COMBA XML ports."""
    if not xml_text or "<ports>" not in xml_text:
        return None

    name_match = re.search(r'<module\s+id="([^"]+)"', xml_text)
    mod_name = name_match.group(1) if name_match else "TopModule"

    port_matches = re.findall(
        r'<(input|output)\s+id="([^"]+)"(?:\s+width_description="([^"]+)")?',
        xml_text,
    )
    if not port_matches:
        return None

    ports_code = []
    for kind, pid, width in port_matches:
        w_str = f" {width}" if width else ""
        ports_code.append(f"    {kind}{w_str} {pid}")

    return f"module {mod_name}(\n" + ",\n".join(ports_code) + "\n);"


# ──────────────────────────────────────────────────────────────
# 1. COMBAState — TypedDict
# ──────────────────────────────────────────────────────────────
class COMBAState(TypedDict):
    # ── Input/Output ──
    nl_input: str
    xml_description: Optional[str]
    module_name: Optional[str]
    benchmark_id: Optional[str]

    # ── Generated Verilog ──
    gvd: Optional[str]
    sgvd: Optional[str]
    _raw_llm_output: Optional[str]

    # ── Syntax Check (SC) ──
    sc_log: Optional[str]
    sc_exception: Optional[str]
    sc_exception_count: int
    sc_prev_exception_count: int

    # ── Testbench Simulation (TS) ──
    tb_log: Optional[str]
    tb_failure: Optional[str]

    # ── Debugging Prompts ──
    edp: Optional[str]
    tdp: Optional[str]

    # ── Control ──
    edtm: dict
    phase: str
    sc_trial: int
    ts_trial: int
    total_iter: int
    rollback_triggered: bool

    # ── Debugger Output ──
    debugger_patch: Optional[dict]

    # ── Sanitizer / MultiAttempt ──
    sanitize_result: Optional[dict]
    _sanitize_retry_count: int
    multi_attempt_mgr: Optional[object]
    escalation_level: Optional[str]
    _last_llm_source: Optional[str]

    # ── Guard fields (do-no-harm guard) ──
    guard_prev_gvd: Optional[str]              # GVD snapshot before debugger call
    guard_prev_sc_count: int                   # SC errors before debugger call
    guard_prev_tb_failure: Optional[str]       # TB failure before debugger (None=pass)
    guard_baseline_gvd: Optional[str]          # Generator's first valid output
    guard_baseline_sc_count: int               # SC count at baseline (-1 = not captured)
    guard_baseline_tb_failure: Optional[str]
    guard_bad_streak: int                      # consecutive rollbacks
    guard_total_rollbacks: int                 # cumulative counter
    guard_total_commits: int                   # cumulative counter
    guard_summary: Optional[dict]              # final summary at terminal node

    # ── Result ──
    final_status: Optional[str]
    error: Optional[str]
    dataset_dir: Optional[str]
    work_dir: Optional[str]
    expected_header: Optional[str]


def make_initial_state(
    nl_input: str = "",
    module_name: str = "",
    benchmark_id: str = "",
    work_dir: Optional[str] = None,
) -> COMBAState:
    """Create a fresh initial state with all fields zeroed."""
    expected_header = None
    if nl_input:
        header_match = re.search(r'(module\s+\w+\s*\(.*?\)\s*;)', nl_input, re.DOTALL)
        if header_match:
            expected_header = header_match.group(1).strip()

    return COMBAState(
        nl_input=nl_input,
        xml_description=None,
        module_name=module_name or None,
        gvd=None,
        sgvd=None,
        _raw_llm_output=None,
        sc_log=None,
        sc_exception=None,
        sc_exception_count=0,
        sc_prev_exception_count=0,
        tb_log=None,
        tb_failure=None,
        edp=None,
        tdp=None,
        edtm={},
        phase="sc",
        sc_trial=0,
        ts_trial=0,
        total_iter=0,
        rollback_triggered=False,
        debugger_patch=None,
        sanitize_result=None,
        _sanitize_retry_count=0,
        multi_attempt_mgr=None,
        escalation_level=None,
        _last_llm_source=None,
        # Guard defaults
        guard_prev_gvd=None,
        guard_prev_sc_count=0,
        guard_prev_tb_failure=None,
        guard_baseline_gvd=None,
        guard_baseline_sc_count=-1,            # sentinel: not captured
        guard_baseline_tb_failure=None,
        guard_bad_streak=0,
        guard_total_rollbacks=0,
        guard_total_commits=0,
        guard_summary=None,
        final_status=None,
        error=None,
        dataset_dir=None,
        work_dir=work_dir,
        benchmark_id=benchmark_id or module_name or None,
        expected_header=expected_header,
    )


# ──────────────────────────────────────────────────────────────
# 2. Pipeline Nodes
# ──────────────────────────────────────────────────────────────
class COMBANodes:
    """
    Encapsulates the 11 pipeline nodes (v4).

    Nodes: converter, generator, sanitizer, syntax_check, guard_sc,
           ted_syntax, debugger, tb_sim, guard_ts, ted_tb.
    """

    def __init__(self, llm):
        self._llm = llm

    # ──────────────────────────────────────────────────────────
    # Node 1: Converter — NL → XML
    # ──────────────────────────────────────────────────────────
    def node_converter(self, state: COMBAState) -> dict:
        """Convert natural language description to COMBA XML format."""
        cprint("\n" + "=" * 60)
        cprint("🔄 NODE: Converter (NL → XML)")
        cprint("=" * 60)

        if state.get("xml_description"):
            cprint("[SKIP] XML already present.")
            return {}

        result = converterPromptTemplate.invoke({
            "user_input": state["nl_input"],
            "conversation": [],
        })
        response = self._llm.invoke(result)
        xml_text = response.content.strip()

        if xml_text.startswith("```"):
            lines = xml_text.split("\n")
            xml_text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        match = re.search(r'<module\s+id="([^"]+)"', xml_text)
        xml_mod_name = match.group(1) if match else "unknown"

        anchored_name = state.get("module_name") or "(none)"
        cprint(f"  ✅ Generated XML for module: {xml_mod_name} (anchored: {anchored_name})")

        updates = {"xml_description": xml_text}

        # Set module_name from XML if state doesn't have one
        if not state.get("module_name") and xml_mod_name != "unknown":
            updates["module_name"] = xml_mod_name

        if not state.get("expected_header"):
            header = _build_header_from_xml(xml_text)
            if header:
                updates["expected_header"] = header
                cprint("  🏗️ Synthesized expected_header from XML")

        return updates

    # ──────────────────────────────────────────────────────────
    # Node 2: Generator — XML → raw LLM output
    # ──────────────────────────────────────────────────────────
    def node_generator(self, state: COMBAState) -> dict:
        """Generate Verilog code from COMBA XML description."""
        cprint("\n" + "=" * 60)
        cprint("⚡ NODE: Generator (XML → raw LLM output)")
        cprint("=" * 60)

        nl_input = state.get("nl_input", "")
        xml_desc = state.get("xml_description")

        if xml_desc and xml_desc != "(Bypassed XML; Using TXT mode)":
            combined_input = f"Original Specification:\n{nl_input}\n\nXML Representation:\n{xml_desc}"
        else:
            combined_input = f"Original Specification:\n{nl_input}"

        result = generatorPromptTemplate.invoke({
            "user_input": combined_input,
            "conversation": [],
        })
        response = self._llm.invoke(result)
        raw_output = response.content.strip()

        cprint(f"  ✅ LLM returned {len(raw_output.splitlines())} lines")

        mgr = state.get("multi_attempt_mgr")
        if mgr is None:
            mgr = MultiAttemptManager()

        return {
            "_raw_llm_output": raw_output,
            "_last_llm_source": "generator",
            "phase": "sc",
            "sc_trial": 0,
            "ts_trial": 0,
            "total_iter": 0,
            "multi_attempt_mgr": mgr,
        }

    # ──────────────────────────────────────────────────────────
    # Node 3: Sanitizer — extract code, auto-fix, collect warnings
    # ──────────────────────────────────────────────────────────
    def node_sanitizer(self, state: COMBAState) -> dict:
        """Run VerilogSanitizer on raw LLM output. Never blocks."""
        cprint("\n" + "=" * 60)
        cprint("🧹 NODE: Sanitizer")
        cprint("=" * 60)

        raw = state.get("_raw_llm_output") or ""
        retry_count = state.get("_sanitize_retry_count", 0)

        result = verilog_sanitize(
            raw,
            module_name=state.get("module_name"),
            expected_header=state.get("expected_header"),
            current_retry=state.get("_sanitize_retry_count", 0),
        )

        sanitize_dict = {
            "code": result.code,
            "needs_retry": result.needs_retry,
            "retry_prompt": result.retry_prompt,
            "warnings": result.warnings,
            "auto_fixed": result.auto_fixed,
        }

        updates = {"sanitize_result": sanitize_dict}

        if result.needs_retry:
            updates["_sanitize_retry_count"] = retry_count + 1
            cprint(f"  🔄 Needs retry ({retry_count + 1}/2): {result.retry_prompt[:60]}...")
        else:
            code = result.code or ""
            if code and not code.endswith("\n"):
                code += "\n"
            updates["gvd"] = code
            updates["_sanitize_retry_count"] = 0

            # Set sgvd + capture baseline on first generation
            if state.get("_last_llm_source") == "generator":
                updates["sgvd"] = code
                # ── GUARD: capture immutable baseline (only first time) ──
                if state.get("guard_baseline_gvd") is None:
                    updates["guard_baseline_gvd"] = code
                    cprint(f"  🛡️  GUARD: baseline captured ({len(code.splitlines())} lines)")

            cprint(f"  ✅ Sanitized: {len(code.splitlines())} lines")
            if result.auto_fixed:
                cprint(f"  🔧 Auto-fixed applied")
            for w in result.warnings:
                cprint(f"  ⚠️ {w}")

        return updates

    # ──────────────────────────────────────────────────────────
    # Node 4: Syntax Check — iverilog --lint-only
    # ──────────────────────────────────────────────────────────
    def node_syntax_check(self, state: COMBAState) -> dict:
        """Run iverilog lint-only syntax check on current GVD."""
        cprint("\n" + "=" * 60)
        cprint(f"🔍 NODE: Syntax Check (SC trial #{state['sc_trial'] + 1})")
        cprint("=" * 60)

        module_name = state["module_name"]
        gvd = state["gvd"]

        work_dir = state.get("work_dir")
        if not work_dir:
            work_dir = tempfile.mkdtemp(prefix=f"comba_{module_name}_")

        verilog_path = os.path.join(work_dir, "TopModule.sv")
        with open(verilog_path, "w", encoding="utf-8") as f:
            f.write(gvd)

        cmd = ["iverilog"] + IVERILOG_SC_FLAGS + ["TopModule.sv"]

        try:
            result = subprocess.run(
                cmd, cwd=work_dir, capture_output=True, text=True, timeout=30,
            )
            sc_log = result.stderr + result.stdout
        except FileNotFoundError:
            sc_log = "error: iverilog not found in PATH"
        except subprocess.TimeoutExpired:
            sc_log = "error: iverilog timed out after 30s"

        exception_count = _count_iverilog_errors(sc_log)

        cprint(f"  SC log: {len(sc_log.splitlines())} lines, {exception_count} errors")

        out = {
            "sc_log": sc_log,
            "sc_exception_count": exception_count,
            "sc_trial": state["sc_trial"] + 1,
            "total_iter": state["total_iter"] + 1,
            "work_dir": work_dir,
        }

        # ── GUARD: lock baseline SC count on first SC after generator ──
        if (state.get("_last_llm_source") == "generator"
                and state.get("guard_baseline_sc_count", -1) == -1):
            out["guard_baseline_sc_count"] = exception_count
            cprint(f"  🛡️  GUARD: baseline_sc_count locked = {exception_count}")

        return out

    # ──────────────────────────────────────────────────────────
    # Node 5: Guard SC — do-no-harm check after syntax_check
    # ──────────────────────────────────────────────────────────
    def node_guard_sc(self, state: COMBAState) -> dict:
        """
        Do-no-harm guard for SC phase.
        Compares post-debugger candidate against pre-debugger snapshot.
        Rolls back GVD if candidate is worse.

        No-op when source is 'generator' — nothing to compare against yet.
        """
        source = state.get("_last_llm_source")
        if source != "debugger":
            return {}

        prev_count = state.get("guard_prev_sc_count", 999)
        cand_count = state.get("sc_exception_count", 999)
        prev_gvd = state.get("guard_prev_gvd")

        # Critical regression: prev was clean, cand is broken
        critical = (prev_count == 0 and cand_count > 0)
        # General regression: more errors than before
        regressed = cand_count > prev_count

        if (critical or regressed) and prev_gvd:
            new_streak = state.get("guard_bad_streak", 0) + 1
            cprint(
                f"  🛡️  GUARD SC ROLLBACK: prev={prev_count} cand={cand_count} "
                f"(streak={new_streak}, critical={critical})"
            )
            return {
                "gvd": prev_gvd,
                "sc_exception_count": prev_count,
                "guard_bad_streak": new_streak,
                "guard_total_rollbacks": state.get("guard_total_rollbacks", 0) + 1,
                "rollback_triggered": True,
            }

        cprint(f"  🛡️  GUARD SC COMMIT: prev={prev_count} cand={cand_count}")
        return {
            "guard_bad_streak": 0,
            "guard_total_commits": state.get("guard_total_commits", 0) + 1,
            "rollback_triggered": False,
        }

    # ──────────────────────────────────────────────────────────
    # Node 6: TED Syntax — Parse topmost SC error → EDP
    # ──────────────────────────────────────────────────────────
    def node_ted_syntax(self, state: COMBAState) -> dict:
        """Parse sc_log → extract topmost error → create EDP. Update EDTM."""
        cprint("\n" + "=" * 60)
        cprint("🔎 NODE: TED Syntax (Parse topmost SC error)")
        cprint("=" * 60)

        sc_log = state["sc_log"] or ""
        edtm = dict(state.get("edtm", {}))

        topmost_error = None
        for line in sc_log.splitlines():
            lowered = line.lower()
            if ((": error:" in lowered or ": syntax error" in lowered or "error:" in lowered)
                    and "exiting due to" not in lowered):
                topmost_error = line.strip()
                break

        if not topmost_error:
            cprint("  ⚠️ No parseable error found in SC log")
            return {
                "sc_exception": None,
                "edp": None,
                "phase": "sc",
            }

        sig = _normalize_error_key(topmost_error)
        edtm[sig] = edtm.get(sig, 0) + 1

        if edtm[sig] > EDTM_MAX_RETRIES:
            cprint(f"  ⛔ EDTM: Exception seen {edtm[sig]} times")
            edp = (
                f"[EDTM WARNING: This error has been seen {edtm[sig]} times. "
                f"Previous fixes did not resolve it. Try a fundamentally different approach.]\n"
                f"Topmost iverilog error:\n{topmost_error}"
            )
        else:
            edp = f"Topmost iverilog error:\n{topmost_error}"

        cprint(f"  📋 EDP: {topmost_error[:80]}...")
        cprint(f"  📊 EDTM count for this sig: {edtm[sig]}")

        return {
            "sc_exception": topmost_error,
            "edp": edp,
            "edtm": edtm,
            "phase": "sc",
        }

    # ──────────────────────────────────────────────────────────
    # Node 7: Debugger — LoRA call with snapshot capture
    # ──────────────────────────────────────────────────────────
    def node_debugger(self, state: COMBAState) -> dict:
        """
        Debugger node. Snapshots state BEFORE invoking LoRA, so guard
        can compare candidate against prev. Delegates prompt building
        to MultiAttemptManager.
        """
        cprint("\n" + "=" * 60)
        cprint(f"🐛 NODE: Debugger (phase={state['phase']})")
        cprint("=" * 60)

        phase = state["phase"]
        current_gvd = state["gvd"]
        error_desc = state["edp"] if phase == "sc" else state["tdp"]
        module_name = state.get("module_name") or "unknown"

        if not error_desc:
            cprint("  ⚠️ No error description available, skipping")
            return {}

        mgr = state.get("multi_attempt_mgr")
        if mgr is None:
            mgr = MultiAttemptManager()

        # ── GUARD: snapshot current state as "prev" before mutating ──
        guard_snapshot = {
            "guard_prev_gvd": state.get("gvd"),
            "guard_prev_sc_count": state.get("sc_exception_count", 0),
            "guard_prev_tb_failure": state.get("tb_failure"),
        }

        error_key = _normalize_error_key(error_desc.split('\n')[0])
        esc_level = mgr.get_escalation_level(error_key)
        cprint(f"  📊 Escalation: L{esc_level} for key: {error_key[:60]}")

        # Build prompt
        if phase == "sc":
            prompt_text = mgr.build_sc_prompt(
                error_key=error_key,
                module_name=module_name,
                gvd=current_gvd,
                exception_type="syntax_error",
                exception_title=(state.get("sc_exception") or error_desc)[:200],
                exception_content=error_desc,
                log_content=(state.get("sc_log") or "")[:2000],
                task_description=(state.get("nl_input") or "")[:_MAX_TASK_DESC_CHARS],
            )
        else:
            traces = ""
            failure_str = error_desc or state.get("tb_failure", "")
            if error_desc and "Debug traces:" in error_desc:
                parts = error_desc.split("Debug traces:", 1)
                failure_str = parts[0].strip()
                traces = parts[1].strip()

            prompt_text = mgr.build_ts_prompt(
                error_key=error_key,
                module_name=module_name,
                gvd=current_gvd,
                todo_num=0,
                trace_content=traces or "(no traces available)",
                failure_content=failure_str,
                task_description=(state.get("nl_input") or "")[:_MAX_TASK_DESC_CHARS],
            )

        # Call LLM
        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=prompt_text)]

        if hasattr(self._llm, 'switch_to_lora'):
            self._llm.switch_to_lora()

        try:
            response = self._llm.invoke(messages)
            raw_output = response.content.strip()
        except Exception as e:
            cprint(f"  ❌ Debugger LLM error: {e}")
            if hasattr(self._llm, 'switch_to_base'):
                self._llm.switch_to_base()
            # Return prev as raw output → sanitizer extracts → no change
            return {
                "_raw_llm_output": current_gvd,
                "_last_llm_source": "debugger",
                "multi_attempt_mgr": mgr,
                "escalation_level": f"L{esc_level}",
                **guard_snapshot,
            }

        if hasattr(self._llm, 'switch_to_base'):
            self._llm.switch_to_base()

        mgr.record_attempt(
            error_key=error_key,
            phase=DebugPhase.SYNTAX if phase == "sc" else DebugPhase.TESTBENCH,
            error_detail=error_desc[:500],
            code_snapshot=current_gvd[:1000] if current_gvd else "",
        )

        cprint(f"  ✅ Debugger LLM returned {len(raw_output.splitlines())} lines")

        return {
            "_raw_llm_output": raw_output,
            "_last_llm_source": "debugger",
            "multi_attempt_mgr": mgr,
            "escalation_level": f"L{esc_level}",
            **guard_snapshot,
        }

    # ──────────────────────────────────────────────────────────
    # Node 8: Testbench Simulation (dispatcher)
    # ──────────────────────────────────────────────────────────
    def node_tb_sim(self, state: COMBAState) -> dict:
        """
        Run testbench simulation. Dispatches to the right (simulator, mode) combo
        based on dataset type and COMBA_TS_SIMULATOR config.

        Dispatch rules:
          1. RTLLM with tb.cpp                  → Verilator C++ wrapper
          2. RTLLM with .sv testbench files     → respects TS_SIMULATOR (verilator/iverilog/auto)
          3. VerilogEval (_test.sv + _ref.sv)   → respects TS_SIMULATOR (default iverilog)
        """
        cprint("\n" + "=" * 60)
        cprint(f"🧪 NODE: TB Simulation (TS trial #{state['ts_trial'] + 1})")
        cprint("=" * 60)

        module_name = state["module_name"]
        work_dir = state.get("work_dir")
        gvd = state["gvd"]
        dataset_dir = state.get("dataset_dir")

        if not work_dir:
            return self._tb_error_state(state, "work_dir not set", "Infrastructure error")
        if not gvd:
            return self._tb_error_state(state, "no GVD", "Infrastructure error")
        if not dataset_dir:
            return self._tb_error_state(state, "dataset_dir missing", "Infrastructure error")

        # ── Dispatch 1: RTLLM C++ testbench (tb.cpp present) ──
        tb_cpp_src = os.path.join(dataset_dir, "tb.cpp")
        if os.path.isfile(tb_cpp_src):
            cprint(f"  📦 Path: RTLLM C++ testbench → Verilator")
            return self._run_rtllm_verilator(state, tb_cpp_src)

        # ── Dispatch 2: SV testbench files — pick simulator ──
        is_rtllm = self._is_rtllm_dataset(dataset_dir)
        simulator = self._pick_simulator(is_rtllm)
        cprint(f"  📦 Path: SV testbench → {simulator} (rtllm={is_rtllm}, mode={TS_SIMULATOR})")

        if simulator == "verilator":
            return self._run_sv_verilator(state)
        else:
            return self._run_sv_iverilog(state)

    # ──────────────────────────────────────────────────────────
    # Simulator selection helpers
    # ──────────────────────────────────────────────────────────
    @staticmethod
    def _is_rtllm_dataset(dataset_dir: str) -> bool:
        """Heuristic: RTLLM datasets have 'RTLLM' in path or testbench named 'testbench.v'."""
        if "RTLLM" in dataset_dir or "rtllm" in dataset_dir:
            return True
        # RTLLM .sv variant: a single testbench.v / testbench.sv file
        for fname in ("testbench.v", "testbench.sv", "tb.v", "tb.sv"):
            if os.path.isfile(os.path.join(dataset_dir, fname)):
                return True
        return False

    @staticmethod
    def _pick_simulator(is_rtllm: bool) -> str:
        """Return 'iverilog' or 'verilator' based on TS_SIMULATOR config."""
        if TS_SIMULATOR == "verilator":
            return "verilator"
        if TS_SIMULATOR == "iverilog":
            return "iverilog"
        # auto mode
        return "verilator" if is_rtllm else "iverilog"

    # ──────────────────────────────────────────────────────────
    # SV testbench: locate test/ref files (shared by both simulators)
    # ──────────────────────────────────────────────────────────
    def _prepare_sv_testbench_files(self, state: COMBAState) -> tuple[Optional[list[str]], Optional[dict]]:
        """
        Copy SV testbench files into work_dir + write current GVD as TopModule.sv.
        Returns (list_of_sv_files, error_state) — error_state is None on success.
        """
        module_name = state["module_name"]
        work_dir = state["work_dir"]
        gvd = state["gvd"]
        dataset_dir = state["dataset_dir"]
        bid = state.get("benchmark_id", module_name)

        # Candidate testbench filenames (VerilogEval + RTLLM SV variants)
        candidate_pairs = [
            (f"{bid}_test.sv", f"{bid}_ref.sv"),    # VerilogEval
            ("testbench.sv", None),                  # RTLLM SV single-file
            ("testbench.v", None),
            ("tb.sv", None),
            ("tb.v", None),
        ]

        sv_files: list[str] = []
        for tb_name, ref_name in candidate_pairs:
            tb_src = os.path.join(dataset_dir, tb_name)
            if not os.path.isfile(tb_src):
                continue

            tb_dst = os.path.join(work_dir, tb_name)
            try:
                if not os.path.isfile(tb_dst):
                    shutil.copy2(tb_src, tb_dst)
                sv_files.append(tb_name)

                if ref_name:
                    ref_src = os.path.join(dataset_dir, ref_name)
                    ref_dst = os.path.join(work_dir, ref_name)
                    if os.path.isfile(ref_src) and not os.path.isfile(ref_dst):
                        shutil.copy2(ref_src, ref_dst)
                        sv_files.append(ref_name)
            except Exception as e:
                return None, self._tb_error_state(state, f"copy error: {e}", "testbench copy failed")
            break

        if not sv_files:
            return None, self._tb_error_state(
                state,
                f"no testbench found in {dataset_dir} (tried: {[p[0] for p in candidate_pairs]})",
                "no testbench found",
            )

        # Write current GVD as TopModule.sv (rename module to TopModule for VE)
        top_module_code = re.sub(
            r'module\s+[a-zA-Z0-9_]+', 'module TopModule', gvd, count=1, flags=re.MULTILINE,
        )
        top_module_dst = os.path.join(work_dir, "TopModule.sv")
        with open(top_module_dst, "w", encoding="utf-8") as f:
            f.write(top_module_code)

        return ["TopModule.sv"] + sv_files, None

    # ──────────────────────────────────────────────────────────
    # SV testbench via iverilog (default for VerilogEval)
    # ──────────────────────────────────────────────────────────
    def _run_sv_iverilog(self, state: COMBAState) -> dict:
        """Compile + run SV testbench using iverilog + vvp."""
        module_name = state["module_name"]
        work_dir = state["work_dir"]

        sv_files, err = self._prepare_sv_testbench_files(state)
        if err:
            return err

        binary_out = f"{module_name}.vvp"
        comp_cmd = ["iverilog"] + IVERILOG_TS_FLAGS + ["-s", "tb", "-o", binary_out] + sv_files

        tb_log_parts = []
        try:
            r1 = subprocess.run(
                comp_cmd, cwd=work_dir, capture_output=True, text=True, timeout=60,
            )
            tb_log_parts.append(f"[COMPILE iverilog]\n{r1.stderr}{r1.stdout}")

            if r1.returncode != 0:
                tb_log_parts.append("[COMPILE FAILED]")
                first_err = r1.stderr.splitlines()[0] if r1.stderr.splitlines() else r1.stderr
                return {
                    "tb_log": "\n".join(tb_log_parts),
                    "tb_failure": f"iverilog compilation failed: {first_err[:80]}",
                    "ts_trial": state["ts_trial"] + 1,
                    "total_iter": state["total_iter"] + 1,
                    "phase": "ts",
                }

            r2 = subprocess.run(
                ["vvp", binary_out], cwd=work_dir,
                capture_output=True, text=True, timeout=120,
            )
            tb_log_parts.append(f"[RUN]\n{r2.stderr}{r2.stdout}")

            if r2.returncode != 0:
                tb_log_parts.append(f"[RUN FAILED] exit code {r2.returncode}")

        except FileNotFoundError as e:
            tb_log_parts.append(f"error: command not found: {e}")
        except subprocess.TimeoutExpired:
            tb_log_parts.append("error: TB simulation timed out")

        return self._parse_tb_result(state, "\n".join(tb_log_parts), expect_passed_keyword=True)

    # ──────────────────────────────────────────────────────────
    # SV testbench via verilator (--binary mode, no C++ wrapper)
    # ──────────────────────────────────────────────────────────
    def _run_sv_verilator(self, state: COMBAState) -> dict:
        """
        Compile + run SV testbench using verilator --binary mode (verilator >=5.x).
        No C++ wrapper needed; verilator handles `initial begin ... $display ... $finish` directly.
        """
        module_name = state["module_name"]
        work_dir = state["work_dir"]

        sv_files, err = self._prepare_sv_testbench_files(state)
        if err:
            return err

        # Find tb top: try 'tb' first (common), fallback to first non-TopModule SV
        top = "tb"

        cmd = ["verilator"] + VERILATOR_TS_FLAGS + ["--top-module", top] + sv_files

        tb_log_parts = []
        try:
            r1 = subprocess.run(
                cmd, cwd=work_dir, capture_output=True, text=True, timeout=180,
            )
            tb_log_parts.append(f"[COMPILE verilator]\n{r1.stderr}{r1.stdout}")

            if r1.returncode != 0:
                tb_log_parts.append("[COMPILE FAILED]")
                first_err = ""
                for line in r1.stderr.splitlines():
                    if "%Error" in line or "Error:" in line:
                        first_err = line
                        break
                if not first_err and r1.stderr:
                    first_err = r1.stderr.splitlines()[0]
                return {
                    "tb_log": "\n".join(tb_log_parts),
                    "tb_failure": f"verilator compilation failed: {first_err[:120]}",
                    "ts_trial": state["ts_trial"] + 1,
                    "total_iter": state["total_iter"] + 1,
                    "phase": "ts",
                }

            # Verilator --binary produces obj_dir/V<top>
            exe = os.path.join(work_dir, "obj_dir", f"V{top}")
            if not os.path.exists(exe):
                # Fallback: try TopModule binary
                exe_alt = os.path.join(work_dir, "obj_dir", f"V{module_name}")
                if os.path.exists(exe_alt):
                    exe = exe_alt
                else:
                    tb_log_parts.append(f"[ERROR] verilator binary not found at {exe}")
                    return {
                        "tb_log": "\n".join(tb_log_parts),
                        "tb_failure": "verilator binary missing",
                        "ts_trial": state["ts_trial"] + 1,
                        "total_iter": state["total_iter"] + 1,
                        "phase": "ts",
                    }

            r2 = subprocess.run(
                [exe], cwd=work_dir, capture_output=True, text=True, timeout=120,
            )
            tb_log_parts.append(f"[RUN]\n{r2.stderr}{r2.stdout}")

            if r2.returncode != 0:
                tb_log_parts.append(f"[RUN FAILED] exit code {r2.returncode}")

        except FileNotFoundError as e:
            tb_log_parts.append(f"error: verilator not in PATH: {e}")
        except subprocess.TimeoutExpired:
            tb_log_parts.append("error: verilator simulation timed out")

        return self._parse_tb_result(state, "\n".join(tb_log_parts), expect_passed_keyword=True)

    # ──────────────────────────────────────────────────────────
    # Shared TB result parser
    # ──────────────────────────────────────────────────────────
    def _parse_tb_result(self, state: COMBAState, tb_log: str, expect_passed_keyword: bool = True) -> dict:
        """
        Common pass/fail detection logic shared between iverilog and verilator paths.

        Pass criteria:
          - No 'Failed' / 'Mismatches: N>0' / '[RUN FAILED]' in log
          - If expect_passed_keyword: 'passed' must appear in log

        Verilator-specific: also treats '%Error' during run as failure.
        """
        failure = None

        for line in tb_log.splitlines():
            stripped = line.strip()
            if "Failed" in stripped:
                failure = stripped
                break
            if "Mismatches:" in stripped:
                m = re.search(r'Mismatches:\s*(\d+)', stripped)
                if m and int(m.group(1)) > 0:
                    failure = stripped
                    break
            # Verilator runtime error
            if "%Error" in stripped and "[RUN]" in tb_log[:tb_log.find(stripped)]:
                failure = stripped
                break

        if not failure and "[RUN FAILED]" in tb_log:
            failure = "Simulation exited with non-zero code"

        # For verilator + RTLLM-style, looser failure detection
        if not failure and not expect_passed_keyword:
            fail_keywords = ["fail", "error", "mismatch", "assertion", "todo"]
            run_section = tb_log[tb_log.find("[RUN]"):] if "[RUN]" in tb_log else ""
            if any(k in run_section.lower() for k in fail_keywords):
                failure = "Testbench failed"

        status_msg = "PASS ✅" if not failure else f"FAIL: {failure[:60]}"
        cprint(f"  TB result: {status_msg}")

        if expect_passed_keyword:
            final_status = "pass" if failure is None and "passed" in tb_log.lower() else None
        else:
            final_status = "pass" if failure is None else None

        return {
            "tb_log": tb_log,
            "tb_failure": failure,
            "final_status": final_status,
            "ts_trial": state["ts_trial"] + 1,
            "total_iter": state["total_iter"] + 1,
            "phase": "ts" if not final_status else "done",
        }

    def _tb_error_state(self, state: COMBAState, log_msg: str, fail_msg: str) -> dict:
        """Helper: return TB error state dict."""
        return {
            "tb_log": f"error: {log_msg}",
            "tb_failure": fail_msg,
            "ts_trial": state["ts_trial"] + 1,
            "total_iter": state["total_iter"] + 1,
            "phase": "ts",
        }

    # ──────────────────────────────────────────────────────────
    # RTLLM C++ testbench via Verilator (unchanged path)
    # ──────────────────────────────────────────────────────────
    def _run_rtllm_verilator(self, state: COMBAState, tb_cpp_path: str) -> dict:
        """RTLLM C++ testbenches via Verilator (--cc --exe with tb.cpp)."""
        module_name = state["module_name"] or "TopModule"
        work_dir = state["work_dir"]
        gvd = state["gvd"]

        verilog_path = os.path.join(work_dir, f"{module_name}.v")
        with open(verilog_path, "w", encoding="utf-8") as f:
            f.write(gvd)

        tb_cpp_dst = os.path.join(work_dir, "tb.cpp")
        shutil.copy2(tb_cpp_path, tb_cpp_dst)

        cmd = [
            "verilator", "--cc", "--exe", "--build", "-j",
            "--trace", "-Wall", "-Wno-fatal",
            "--top-module", module_name,
            f"{module_name}.v", "tb.cpp"
        ]

        tb_log_parts = []
        try:
            r1 = subprocess.run(
                cmd, cwd=work_dir, capture_output=True, text=True, timeout=120,
            )
            tb_log_parts.append(f"[COMPILE verilator+cpp]\n{r1.stderr}{r1.stdout}")

            if r1.returncode != 0:
                return {
                    "tb_log": "\n".join(tb_log_parts),
                    "tb_failure": "Verilator compilation failed",
                    "ts_trial": state["ts_trial"] + 1,
                    "total_iter": state["total_iter"] + 1,
                    "phase": "ts",
                }

            exe = os.path.join(work_dir, f"obj_dir/V{module_name}")
            if not os.path.exists(exe):
                return {
                    "tb_log": "\n".join(tb_log_parts) + f"\nerror: exe {exe} not found",
                    "tb_failure": "Verilator executable not found",
                    "ts_trial": state["ts_trial"] + 1,
                    "total_iter": state["total_iter"] + 1,
                    "phase": "ts",
                }

            r2 = subprocess.run(
                [exe], cwd=work_dir, capture_output=True, text=True, timeout=60,
            )
            tb_log_parts.append(f"[RUN]\n{r2.stderr}{r2.stdout}")

            # RTLLM C++: looser detection (no 'passed' keyword expected)
            return self._parse_tb_result(
                state, "\n".join(tb_log_parts), expect_passed_keyword=False,
            )
        except Exception as e:
            return {
                "tb_log": f"error: {e}",
                "tb_failure": "Infrastructure error during Verilator run",
                "ts_trial": state["ts_trial"] + 1,
                "total_iter": state["total_iter"] + 1,
                "phase": "ts",
            }

    # ──────────────────────────────────────────────────────────
    # Node 9: Guard TS — do-no-harm check after tb_sim
    # ──────────────────────────────────────────────────────────
    def node_guard_ts(self, state: COMBAState) -> dict:
        """
        Do-no-harm guard for TS phase.
        Critical regressions:
          - prev passed TB (tb_failure=None), cand fails it
          - prev had clean SC, debugger broke compilation
        """
        source = state.get("_last_llm_source")
        if source != "debugger":
            return {}

        prev_tb = state.get("guard_prev_tb_failure")
        cand_tb = state.get("tb_failure")
        prev_sc = state.get("guard_prev_sc_count", 0)
        cand_sc = state.get("sc_exception_count", 0)
        prev_gvd = state.get("guard_prev_gvd")

        critical_tb = (prev_tb is None and cand_tb is not None)
        critical_sc = (prev_sc == 0 and cand_sc > 0)

        if (critical_tb or critical_sc) and prev_gvd:
            new_streak = state.get("guard_bad_streak", 0) + 1
            cprint(
                f"  🛡️  GUARD TS ROLLBACK: critical_tb={critical_tb} "
                f"critical_sc={critical_sc} (streak={new_streak})"
            )
            return {
                "gvd": prev_gvd,
                "tb_failure": prev_tb,
                "sc_exception_count": prev_sc,
                "final_status": "pass" if prev_tb is None else None,
                "guard_bad_streak": new_streak,
                "guard_total_rollbacks": state.get("guard_total_rollbacks", 0) + 1,
                "rollback_triggered": True,
            }

        cprint(f"  🛡️  GUARD TS COMMIT")
        return {
            "guard_bad_streak": 0,
            "guard_total_commits": state.get("guard_total_commits", 0) + 1,
            "rollback_triggered": False,
        }

    # ──────────────────────────────────────────────────────────
    # Node 10: TED TB — Parse topmost TB failure → TDP
    # ──────────────────────────────────────────────────────────
    def node_ted_tb(self, state: COMBAState) -> dict:
        """Parse tb_log → extract topmost failure → TDP. Update EDTM."""
        cprint("\n" + "=" * 60)
        cprint("🔎 NODE: TED TB (Parse topmost TB failure)")
        cprint("=" * 60)

        tb_log = state.get("tb_log", "")
        module_name = state.get("module_name") or "unknown"
        edtm = dict(state.get("edtm", {}))

        # Fast-path: wire l-value errors
        wire_ports = _extract_wire_lvalue_ports(tb_log)
        if wire_ports:
            port_list = ', '.join(f"'{p}'" for p in wire_ports)
            tdp = (
                f"[WIRE L-VALUE FIX REQUIRED]\n"
                f"The following output port(s) are declared as plain `output` (wire) "
                f"but are assigned inside `always` blocks: {port_list}.\n"
                f"Fix: change each declaration from `output foo` → `output reg foo`.\n"
                f"This is the ONLY change needed — do not alter any logic."
            )
            sig_tb = "WIRE_LVALUE:" + "_".join(wire_ports)
            edtm[sig_tb] = edtm.get(sig_tb, 0) + 1
            cprint(f"  ⚡ Wire l-value ports detected: {wire_ports}")
            return {"tdp": tdp, "phase": "ts", "edtm": edtm}

        # Fast-path: Port mismatch
        missing_ports = _extract_port_mismatch(tb_log)
        if missing_ports:
            p_list = ', '.join(f"'{p}'" for p in missing_ports)
            tdp = (
                f"[PORT MISMATCH DETECTED]\n"
                f"The testbench expects the following port(s) which are MISSING in your module: {p_list}.\n"
                f"You MUST use the exact port names defined in the specification."
            )
            sig_tb = "PORT_MISMATCH:" + "_".join(missing_ports)
            edtm[sig_tb] = edtm.get(sig_tb, 0) + 1
            cprint(f"  ⚡ Port mismatch detected: {missing_ports}")
            return {"tdp": tdp, "phase": "ts", "edtm": edtm}

        # Extract topmost failure
        topmost_failure = None
        for line in tb_log.splitlines():
            stripped = line.strip()
            if re.search(r'TODO\s+\d+\s+Failed', stripped):
                topmost_failure = stripped
                break
            if "Assertion" in stripped and "failed" in stripped.lower():
                topmost_failure = stripped
                break

        if not topmost_failure:
            topmost_failure = state.get("tb_failure", "Unknown testbench failure")

        sig_tb = "TB:" + re.sub(r'\d+', 'N', topmost_failure).strip()
        sig_tb = re.sub(r'\s+', ' ', sig_tb)
        edtm[sig_tb] = edtm.get(sig_tb, 0) + 1
        cprint(f"  📊 EDTM TB count for this sig: {edtm[sig_tb]}")

        tdp = f"Topmost testbench failure:\n{topmost_failure}"

        # Trace lines + hints
        trace_lines = []
        hints = []
        for line in tb_log.splitlines():
            if "TRACE" in line or "INPUT" in line or "OUTPUT" in line:
                trace_lines.append(line.strip())

        # RTLLM tb.cpp port context
        dataset_dir = state.get("dataset_dir")
        tb_ref = ""
        if dataset_dir:
            tb_cpp = os.path.join(dataset_dir, "tb.cpp")
            if os.path.isfile(tb_cpp):
                try:
                    with open(tb_cpp, "r", encoding="utf-8") as f:
                        full_cpp = f.read()
                        m1 = re.search(r"class\s+\w+InTx\s*\{[\s\S]+?\}", full_cpp)
                        if m1:
                            tb_ref += f"// Testbench Input Struct:\n{m1.group(0)}\n"
                        m2 = re.search(r"class\s+\w+OutTx\s*\{[\s\S]+?\}", full_cpp)
                        if m2:
                            tb_ref += f"// Testbench Output Struct:\n{m2.group(0)}\n"
                except Exception:
                    pass

        # Category hints
        from multi_attempt import CATEGORY_HINTS
        mod_hint = ""
        best_match_len = 0
        for key, hint_text in CATEGORY_HINTS.items():
            if re.search(rf'\b{re.escape(key)}\b', module_name.lower()):
                if len(key) > best_match_len:
                    mod_hint = hint_text
                    best_match_len = len(key)
        if mod_hint:
            hints.append(f"CATEGORY HINT: {mod_hint}")

        all_traces = hints + trace_lines
        if all_traces:
            tdp += "\n\nDebug traces:\n" + "\n".join(all_traces)

        if tb_ref:
            tdp += "\n\nTestbench Reference Snippet:\n" + tb_ref

        cprint(f"  📋 TDP: {topmost_failure[:80]}")

        return {"tdp": tdp, "phase": "ts", "edtm": edtm}


# ──────────────────────────────────────────────────────────────
# 3. Routing Functions (Conditional Edges)
# ──────────────────────────────────────────────────────────────

def route_after_sanitizer(state: COMBAState) -> str:
    """After Sanitizer — needs retry? → re-query LLM, else → SC."""
    result = state.get("sanitize_result") or {}
    if result.get("needs_retry"):
        source = state.get("_last_llm_source", "generator")
        if source == "debugger":
            return "node_debugger"
        return "node_generator"
    return "node_syntax_check"


def route_after_sc(state: COMBAState) -> str:
    """After Guard SC — has errors? → TED_SC, else → TB."""
    if state["sc_exception_count"] > 0:
        return "node_ted_syntax"
    return "node_tb_sim"


def route_after_ts(state: COMBAState) -> str:
    """After Guard TS — has failures? → TED_TB, else → PASS."""
    if state.get("tb_failure"):
        return "node_ted_tb"
    return "end_pass"


def route_after_ted_syntax(state: COMBAState) -> str:
    """After TED Syntax — guard stop / no error / limit / give-up / debug."""
    # GUARD: stop loop if debugger has regressed twice in a row
    if state.get("guard_bad_streak", 0) >= GUARD_MAX_BAD_STREAK:
        cprint(f"  ⛔ GUARD STOP: bad_streak ≥ {GUARD_MAX_BAD_STREAK}, fallback path")
        return "end_fail_sc"

    # If TED couldn't parse any error, skip debugger → go to TB
    if not state.get("sc_exception"):
        return "node_tb_sim"

    if state["sc_trial"] >= MAX_SC_TRIALS:
        return "end_fail_sc"

    # MultiAttemptManager give-up check
    mgr = state.get("multi_attempt_mgr")
    if mgr is not None:
        error_key = _normalize_error_key(state.get("sc_exception") or "")
        if mgr.should_give_up(error_key):
            cprint(f"  ⛔ MultiAttempt: giving up on error_key: {error_key[:50]}")
            return "end_fail_sc"

    return "node_debugger"


def route_after_ted_tb(state: COMBAState) -> str:
    """After TED TB — guard stop / TS limit / give-up / debug."""
    # GUARD: stop loop if debugger has regressed twice in a row
    if state.get("guard_bad_streak", 0) >= GUARD_MAX_BAD_STREAK:
        cprint(f"  ⛔ GUARD STOP: bad_streak ≥ {GUARD_MAX_BAD_STREAK}, fallback path")
        return "end_fail_ts"

    if state["ts_trial"] >= MAX_TS_TRIALS:
        return "end_fail_ts"

    mgr = state.get("multi_attempt_mgr")
    if mgr is not None:
        tb_failure = state.get("tb_failure") or ""
        error_key = _normalize_error_key(tb_failure)
        if mgr.should_give_up(error_key):
            cprint(f"  ⛔ MultiAttempt: giving up on TB error: {error_key[:50]}")
            return "end_fail_ts"

    return "node_debugger"


# ──────────────────────────────────────────────────────────────
# 4. Terminal Nodes (with baseline fallback)
# ──────────────────────────────────────────────────────────────

def _build_guard_summary(state: COMBAState, used_fallback: bool) -> dict:
    """Build the guard summary dict attached to terminal output."""
    return {
        "rollbacks": state.get("guard_total_rollbacks", 0),
        "commits": state.get("guard_total_commits", 0),
        "used_fallback": used_fallback,
        "baseline_sc": state.get("guard_baseline_sc_count", -1),
        "final_sc": state.get("sc_exception_count", -1),
    }


def _terminal_with_fallback(state: COMBAState, status: str, compare_key: str = "sc") -> dict:
    """
    Restore baseline GVD if it scores better than current.
    Guarantees invariant: final result ≤ generator-only baseline.
    """
    out = {"final_status": status}

    baseline_gvd = state.get("guard_baseline_gvd")
    if not baseline_gvd:
        out["guard_summary"] = _build_guard_summary(state, used_fallback=False)
        return out

    used_fallback = False
    if compare_key == "sc":
        baseline_sc = state.get("guard_baseline_sc_count", 999)
        current_sc = state.get("sc_exception_count", 999)
        if 0 <= baseline_sc < current_sc:
            cprint(
                f"  🛡️  TERMINAL FALLBACK: restoring baseline "
                f"(sc {baseline_sc} < current {current_sc})"
            )
            out["gvd"] = baseline_gvd
            out["sc_exception_count"] = baseline_sc
            used_fallback = True

    out["guard_summary"] = _build_guard_summary(state, used_fallback=used_fallback)
    return out


def end_pass(state: COMBAState) -> dict:
    """All checks passed."""
    cprint("\n🎉 PIPELINE COMPLETE: ALL PASS!")
    return {
        "final_status": "pass",
        "guard_summary": _build_guard_summary(state, used_fallback=False),
    }


def end_fail_sc(state: COMBAState) -> dict:
    """SC trial limit reached."""
    cprint(f"\n❌ PIPELINE FAILED: SC trial limit ({MAX_SC_TRIALS}) reached")
    return _terminal_with_fallback(state, "fail_sc", "sc")


def end_fail_ts(state: COMBAState) -> dict:
    """TS trial limit reached."""
    cprint(f"\n❌ PIPELINE FAILED: TS trial limit ({MAX_TS_TRIALS}) reached")
    return _terminal_with_fallback(state, "fail_ts", "sc")


def end_max_iter(state: COMBAState) -> dict:
    """Total iteration limit reached."""
    cprint(f"\n❌ PIPELINE FAILED: Total iteration limit ({MAX_TOTAL_ITER}) reached")
    return _terminal_with_fallback(state, "max_iter", "sc")


# ──────────────────────────────────────────────────────────────
# 5. Build Graph
# ──────────────────────────────────────────────────────────────

def build_comba_graph(llm):
    """
    Build the full COMBA verification pipeline v4 as a LangGraph.

    Topology (11 pipeline nodes + 4 terminal nodes):
        START → converter → generator → sanitizer
                       ┌─────────────────────────────────────┐
                       ↓                                     │
                syntax_check → guard_sc                      │
                       │                                     │
                       ├ pass → tb_sim → guard_ts            │
                       │                  │                  │
                       │                  ├ pass → end_pass  │
                       │                  └ fail → ted_tb    │
                       │                            │        │
                       └ fail → ted_syntax          │        │
                                  │                 │        │
                                  └→ debugger ←─────┘        │
                                       │                     │
                                       └→ sanitizer ─────────┘

    Guards run BEFORE routing decisions, so route functions see
    the rolled-back state when a regression is detected.
    """
    nodes = COMBANodes(llm)

    builder = StateGraph(COMBAState)

    # ── Add 10 pipeline nodes ──
    builder.add_node("node_converter", nodes.node_converter)
    builder.add_node("node_generator", nodes.node_generator)
    builder.add_node("node_sanitizer", nodes.node_sanitizer)
    builder.add_node("node_syntax_check", nodes.node_syntax_check)
    builder.add_node("node_guard_sc", nodes.node_guard_sc)
    builder.add_node("node_ted_syntax", nodes.node_ted_syntax)
    builder.add_node("node_debugger", nodes.node_debugger)
    builder.add_node("node_tb_sim", nodes.node_tb_sim)
    builder.add_node("node_guard_ts", nodes.node_guard_ts)
    builder.add_node("node_ted_tb", nodes.node_ted_tb)

    # ── Terminal nodes ──
    builder.add_node("end_pass", end_pass)
    builder.add_node("end_fail_sc", end_fail_sc)
    builder.add_node("end_fail_ts", end_fail_ts)
    builder.add_node("end_max_iter", end_max_iter)

    # ── Linear edges ──
    builder.add_edge(START, "node_converter")
    builder.add_edge("node_converter", "node_generator")
    builder.add_edge("node_generator", "node_sanitizer")
    builder.add_edge("node_debugger", "node_sanitizer")
    builder.add_edge("node_syntax_check", "node_guard_sc")
    builder.add_edge("node_tb_sim", "node_guard_ts")

    # Terminal → END
    builder.add_edge("end_pass", END)
    builder.add_edge("end_fail_sc", END)
    builder.add_edge("end_fail_ts", END)
    builder.add_edge("end_max_iter", END)

    # ── Conditional edges (5 routing decisions) ──

    # After sanitizer → SC (normal) or re-query LLM (hard failure)
    builder.add_conditional_edges(
        "node_sanitizer",
        route_after_sanitizer,
        {
            "node_syntax_check": "node_syntax_check",
            "node_generator": "node_generator",
            "node_debugger": "node_debugger",
        },
    )

    # After Guard SC → TED_SC (errors) or TB (clean)
    builder.add_conditional_edges(
        "node_guard_sc",
        route_after_sc,
        {"node_ted_syntax": "node_ted_syntax", "node_tb_sim": "node_tb_sim"},
    )

    # After Guard TS → TED_TB (failed) or END (passed)
    builder.add_conditional_edges(
        "node_guard_ts",
        route_after_ts,
        {"node_ted_tb": "node_ted_tb", "end_pass": "end_pass"},
    )

    # After TED Syntax → Debugger / TB / fail
    builder.add_conditional_edges(
        "node_ted_syntax",
        route_after_ted_syntax,
        {
            "node_tb_sim": "node_tb_sim",
            "node_debugger": "node_debugger",
            "end_fail_sc": "end_fail_sc",
        },
    )

    # After TED TB → Debugger / fail
    builder.add_conditional_edges(
        "node_ted_tb",
        route_after_ted_tb,
        {"node_debugger": "node_debugger", "end_fail_ts": "end_fail_ts"},
    )

    return builder.compile()


# ──────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="COMBA-PROMPT Full Verification Pipeline v4 (with do-no-harm guard)"
    )
    parser.add_argument(
        "description", nargs="?",
        help="Natural language description of the Verilog module",
    )
    parser.add_argument(
        "--xml", type=str,
        help="Path to existing COMBA XML file (skip converter)",
    )
    parser.add_argument(
        "--stub", action="store_true",
        help="Use StubLLM instead of real LLM (for testing)",
    )
    args = parser.parse_args()

    if not args.description and not args.xml:
        parser.error("Provide a description or --xml <path>")

    # Select LLM
    if args.stub:
        from stub_llm import create_stub_llm
        llm = create_stub_llm()
    else:
        from langchain_openai import ChatOpenAI
        base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
        api_key = os.environ.get("LLM_API_KEY", "ollama")
        model = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")
        llm = ChatOpenAI(base_url=base_url, api_key=api_key, model=model, temperature=0.1)

    # Build state
    state = make_initial_state(nl_input=args.description or "")
    if args.xml:
        with open(args.xml, "r", encoding="utf-8") as f:
            state["xml_description"] = f.read()

    # Build and run
    graph = build_comba_graph(llm)
    config = {"recursion_limit": 100}
    final = graph.invoke(state, config)

    print(f"\n{'=' * 60}")
    print(f"Final Status: {final.get('final_status', 'unknown')}")
    print(f"SC Trials: {final.get('sc_trial', 0)}")
    print(f"TS Trials: {final.get('ts_trial', 0)}")
    print(f"Total Iterations: {final.get('total_iter', 0)}")

    # Guard summary
    summary = final.get("guard_summary", {})
    if summary:
        print(f"\n🛡️  Guard Summary:")
        print(f"  Rollbacks:      {summary.get('rollbacks', 0)}")
        print(f"  Commits:        {summary.get('commits', 0)}")
        print(f"  Used Fallback:  {summary.get('used_fallback', False)}")
        print(f"  Baseline SC:    {summary.get('baseline_sc', -1)}")
        print(f"  Final SC:       {summary.get('final_sc', -1)}")
    print(f"{'=' * 60}")
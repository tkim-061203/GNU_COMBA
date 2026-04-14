"""
COMBA-PROMPT Full Verification Pipeline v3 — LangGraph Implementation.

9 nodes, 7 conditional edges, Rollback Manager, EDTM, Iteration Control.
VerilogSanitizer + MultiAttemptManager inserted between LLM calls and Verilator.

Flow:
  NL → [Converter] → XML → [Generator] → [Sanitizer]
    → [SC] → pass? → [TB] → pass? → END ✅
              ↓ fail          ↓ fail
         [TED_SC]→[Debugger]→[Sanitizer]→[SC]  (loop)
                          [TED_TB]→[Debugger]→[Sanitizer]→[SC]  (loop)

v3 Changes:
  - VerilogSanitizer: extracts code from LLM noise, auto-fixes trivial issues,
    collects structural warnings. NEVER blocks — code always reaches Verilator.
  - MultiAttemptManager: escalating correction prompts (L0→L4)
  - Debugger: delegates prompt building to MultiAttemptManager
  - 1 new conditional edge for sanitizer routing

Usage:
  # With real LLM
  python comba_pipeline.py "Design an 8-bit adder"

  # E2E test with stub
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
from verilog_sanitizer import sanitize as verilog_sanitize
from multi_attempt import MultiAttemptManager

# ──────────────────────────────────────────────────────────────
# Configuration Constants
# ──────────────────────────────────────────────────────────────
MAX_SC_TRIALS = 10       # Max syntax-check correction cycles
MAX_TS_TRIALS = 5        # Max testbench correction cycles
MAX_TOTAL_ITER = 20      # Absolute hard cap on total iterations
EDTM_MAX_RETRIES = 3     # Max retries for the same exception signature

# Verilator flags matching the original Makefile
VERILATOR_WNO = ["DECLFILENAME"]
VERILATOR_WERROR = ["UNDRIVEN", "MULTIDRIVEN"]


# ──────────────────────────────────────────────────────────────
# 1. COMBAState — TypedDict
# ──────────────────────────────────────────────────────────────
class COMBAState(TypedDict):
    # ── Input/Output ──
    nl_input: str                              # Natural language description
    xml_description: Optional[str]             # COMBA XML output
    module_name: Optional[str]                 # Extracted module name
    benchmark_id: Optional[str]                # Original benchmark problem ID (for file lookups)

    # ── Generated Verilog ──
    gvd: Optional[str]                         # Generated Verilog Description (current)
    sgvd: Optional[str]                        # Saved GVD (rollback snapshot)
    _raw_llm_output: Optional[str]             # Raw LLM output before extraction

    # ── Syntax Check (SC) ──
    sc_log: Optional[str]                      # SC raw log output
    sc_exception: Optional[str]                # Topmost parsed SC exception
    sc_exception_count: int                    # Number of SC exceptions in current run
    sc_prev_exception_count: int               # Exception count before correction

    # ── Testbench Simulation (TS) ──
    tb_log: Optional[str]                      # TB simulation raw log
    tb_failure: Optional[str]                  # Topmost parsed TB failure

    # ── Debugging Prompts ──
    edp: Optional[str]                         # Exception Debugging Prompt (from SC)
    tdp: Optional[str]                         # Testbench Debugging Prompt (from TB)

    # ── Control ──
    edtm: dict                                 # Exception-Debugging Trial Management
    phase: str                                 # Current phase: "sc" or "ts"
    sc_trial: int                              # SC trial counter
    ts_trial: int                              # TS trial counter
    total_iter: int                            # Total iteration counter
    rollback_triggered: bool                   # Rollback triggered this iteration?

    # ── Debugger Output ──
    debugger_patch: Optional[dict]             # JSON {buggy_code, correct_code} from Debugger

    # ── v3: Sanitizer / MultiAttempt ──
    sanitize_result: Optional[dict]            # VerilogSanitizer output {code, warnings, needs_retry, ...}
    _sanitize_retry_count: int                 # Retry counter for sanitizer (max 2)
    multi_attempt_mgr: Optional[object]        # MultiAttemptManager instance
    escalation_level: Optional[str]            # L0→L4 per current error_key
    _last_llm_source: Optional[str]            # "generator" or "debugger" — for routing

    # ── Result ──
    final_status: Optional[str]                # "pass", "fail_sc", "fail_ts", "max_iter"
    error: Optional[str]                       # Runtime error message
    dataset_dir: Optional[str]                 # Dataset directory for testbenches
    work_dir: Optional[str]                    # Working directory for Verilator
    expected_header: Optional[str]             # Extracted 'module TopModule (...);' for forced alignment


def make_initial_state(nl_input: str = "", module_name: str = "", benchmark_id: str = "") -> COMBAState:
    """Create a fresh initial state with all fields zeroed."""
    # Extract expected header (module TopModule ... ;) from nl_input
    expected_header = None
    if nl_input:
        # Match from 'module' to the first ';'
        # Benchmark prompts usually have 'module TopModule (...);' at the end
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
        final_status=None,
        error=None,
        dataset_dir=None,
        work_dir=None,
        benchmark_id=benchmark_id or module_name or None,
        expected_header=expected_header,
    )


# ──────────────────────────────────────────────────────────────
# 2. Nine Nodes
# ──────────────────────────────────────────────────────────────
class COMBANodes:
    """
    Encapsulates the 9 pipeline nodes (v3).

    Nodes: converter, generator, sanitizer,
           syntax_check, ted_syntax, debugger, tb_sim, ted_tb.

    Args:
        llm: A LangChain-compatible chat model (or StubLLM for testing).
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

        # If XML already provided, skip
        if state.get("xml_description"):
            cprint("[SKIP] XML already present.")
            return {}

        result = converterPromptTemplate.invoke({
            "user_input": state["nl_input"],
            "conversation": [],
        })
        response = self._llm.invoke(result)
        xml_text = response.content.strip()

        # Clean markdown fences if LLM wraps them
        if xml_text.startswith("```"):
            lines = xml_text.split("\n")
            xml_text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        # Extract module name from XML
        match = re.search(r'<module\s+id="([^"]+)"', xml_text)
        module_name = match.group(1) if match else "unknown_module"

        cprint(f"  ✅ Generated XML for module: {module_name}")

        return {
            "xml_description": xml_text,
            "module_name": module_name,
        }

    # ──────────────────────────────────────────────────────────
    # Node 2: Generator — XML → raw LLM output
    # ──────────────────────────────────────────────────────────
    def node_generator(self, state: COMBAState) -> dict:
        """Generate Verilog code from COMBA XML description.
        Outputs raw LLM text → routed to sanitizer."""
        cprint("\n" + "=" * 60)
        cprint("⚡ NODE: Generator (XML → raw LLM output)")
        cprint("=" * 60)

        nl_input = state.get("nl_input", "")
        xml_desc = state["xml_description"]
        
        combined_input = f"Original Specification:\n{nl_input}\n\nXML Representation:\n{xml_desc}"
        
        result = generatorPromptTemplate.invoke({
            "user_input": combined_input,
            "conversation": [],
        })
        response = self._llm.invoke(result)
        raw_output = response.content.strip()

        cprint(f"  ✅ LLM returned {len(raw_output.splitlines())} lines")

        # Initialize MultiAttemptManager on first entry
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
    # Node 2a: Sanitizer — extract code, auto-fix, collect warnings
    # ──────────────────────────────────────────────────────────
    def node_sanitizer(self, state: COMBAState) -> dict:
        """Run VerilogSanitizer on raw LLM output.
        Extracts code from noise, auto-fixes trivial issues, collects warnings.
        NEVER blocks — code always reaches Verilator (except max-retry on empty)."""
        cprint("\n" + "=" * 60)
        cprint("🧹 NODE: Sanitizer")
        cprint("=" * 60)

        raw = state.get("_raw_llm_output") or ""
        module_name = state.get("module_name")
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

        updates = {
            "sanitize_result": sanitize_dict,
        }

        if result.needs_retry:
            updates["_sanitize_retry_count"] = retry_count + 1
            cprint(f"  🔄 Needs retry ({retry_count + 1}/2): {result.retry_prompt[:60]}...")
        else:
            code = result.code or ""
            # Ensure trailing newline
            if code and not code.endswith("\n"):
                code += "\n"
            updates["gvd"] = code
            updates["_sanitize_retry_count"] = 0  # reset for next round
            # Set sgvd on first generation (from generator)
            if state.get("_last_llm_source") == "generator":
                updates["sgvd"] = code
            cprint(f"  ✅ Sanitized: {len(code.splitlines())} lines")
            if result.auto_fixed:
                cprint(f"  🔧 Auto-fixed applied")
            for w in result.warnings:
                cprint(f"  ⚠️ {w}")

        return updates

    # ──────────────────────────────────────────────────────────
    # Node 3: Syntax Check — Verilator --lint-only
    # ──────────────────────────────────────────────────────────
    def node_syntax_check(self, state: COMBAState) -> dict:
        """Run Verilator lint-only syntax check on current GVD."""
        cprint("\n" + "=" * 60)
        cprint(f"🔍 NODE: Syntax Check (SC trial #{state['sc_trial'] + 1})")
        cprint("=" * 60)

        module_name = state["module_name"]
        gvd = state["gvd"]

        # Create temp work dir, write the .v file
        work_dir = state.get("work_dir")
        if not work_dir:
            work_dir = tempfile.mkdtemp(prefix=f"comba_{module_name}_")

        verilog_path = os.path.join(work_dir, f"{module_name}.v")
        with open(verilog_path, "w", encoding="utf-8") as f:
            f.write(gvd)

        # Build iverilog command for linting
        cmd = [
            "iverilog",
            "-tnull",
            "-Wall",
            "-g2012",
            f"{module_name}.v",
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            sc_log = result.stderr + result.stdout
        except FileNotFoundError:
            sc_log = "error: iverilog not found in PATH"
        except subprocess.TimeoutExpired:
            sc_log = "error: iverilog timed out after 30s"

        # Count errors (iverilog typically prefixes or contains ": error:")
        error_lines = [
            line for line in sc_log.splitlines()
            if (": error:" in line.lower() or ": syntax error" in line.lower() or "error:" in line.lower())
            and "Exiting due to" not in line  # just in case
        ]
        exception_count = len(error_lines)

        cprint(f"  SC log: {len(sc_log.splitlines())} lines, {exception_count} errors")

        return {
            "sc_log": sc_log,
            "sc_exception_count": exception_count,
            "sc_trial": state["sc_trial"] + 1,
            "total_iter": state["total_iter"] + 1,
            "work_dir": work_dir,
        }

    # ──────────────────────────────────────────────────────────
    # Node 4: TED Syntax — Parse topmost SC error → EDP
    # ──────────────────────────────────────────────────────────
    def node_ted_syntax(self, state: COMBAState) -> dict:
        """
        Topmost Exception Detection for Syntax Check.
        Parse sc_log → extract topmost %Error → create EDP.
        Update EDTM tracker.
        """
        cprint("\n" + "=" * 60)
        cprint("🔎 NODE: TED Syntax (Parse topmost SC error)")
        cprint("=" * 60)

        sc_log = state["sc_log"] or ""
        edtm = dict(state.get("edtm", {}))   # shallow copy

        # Extract topmost error line
        topmost_error = None
        for line in sc_log.splitlines():
            lowered = line.lower()
            if (": error:" in lowered or ": syntax error" in lowered or "error:" in lowered) and "exiting due to" not in lowered:
                topmost_error = line.strip()
                break

        if not topmost_error:
            cprint("  ⚠️ No parseable error found in SC log")
            return {
                "sc_exception": None,
                "edp": None,
                "phase": "sc",
            }

        # Create exception signature for EDTM (normalize line numbers)
        sig = re.sub(r':\d+:', ':N:', topmost_error)
        sig = re.sub(r'\s+', ' ', sig).strip()

        # Update EDTM counter
        edtm[sig] = edtm.get(sig, 0) + 1

        # Check if this exception has been retried too many times
        if edtm[sig] > EDTM_MAX_RETRIES:
            cprint(f"  ⛔ EDTM: Exception seen {edtm[sig]} times, marking unresolvable")
            # Format EDP to indicate the issue so the correcter tries a different approach
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
    # Node 5a: Debugger — LLM #2 → raw output → extraction_guard
    # ──────────────────────────────────────────────────────────
    def node_debugger(self, state: COMBAState) -> dict:
        """
        Debugger node (v3).
        Delegates prompt building to MultiAttemptManager.
        Outputs raw LLM text → routed to extraction_guard.
        """
        cprint("\n" + "=" * 60)
        cprint(f"🐛 NODE: Debugger (phase={state['phase']})")
        cprint("=" * 60)

        phase = state["phase"]
        current_gvd = state["gvd"]
        error_desc = state["edp"] if phase == "sc" else state["tdp"]
        module_name = state.get("module_name", "unknown")

        if not error_desc:
            cprint("  ⚠️ No error description available, skipping")
            return {}

        # ── Get or create MultiAttemptManager ──
        mgr = state.get("multi_attempt_mgr")
        if mgr is None:
            mgr = MultiAttemptManager()

        # ── Build error_key for escalation tracking ──
        error_key = re.sub(r':\d+:', ':N:', error_desc.split('\n')[0])
        error_key = re.sub(r'\s+', ' ', error_key).strip()[:100]

        # ── Get escalation level ──
        esc_level = mgr.get_escalation_level(error_key)
        cprint(f"  📊 Escalation: L{esc_level} for key: {error_key[:60]}")

        # ── Build prompt via MultiAttemptManager ──
        if phase == "sc":
            prompt_text = mgr.build_sc_prompt(
                error_key=error_key,
                module_name=module_name,
                gvd=current_gvd,
                exception_type="syntax_error",
                exception_title=state.get("sc_exception", error_desc)[:200],
                exception_content=error_desc,
                log_content=(state.get("sc_log") or "")[:2000],
                task_description=state.get("nl_input", ""),
            )
        else:
            traces = ""
            if error_desc and "Debug traces:" in error_desc:
                traces = error_desc.split("Debug traces:")[-1].strip()
            prompt_text = mgr.build_ts_prompt(
                error_key=error_key,
                module_name=module_name,
                gvd=current_gvd,
                todo_num=0,
                trace_content=traces or "(no traces available)",
                failure_content=state.get("tb_failure", error_desc),
                task_description=state.get("nl_input", ""),
            )

        # ── Call LLM ──
        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=prompt_text)]

        # Switch to LoRA if available
        if hasattr(self._llm, 'switch_to_lora'):
            self._llm.switch_to_lora()

        response = self._llm.invoke(messages)

        # Switch back to base
        if hasattr(self._llm, 'switch_to_base'):
            self._llm.switch_to_base()

        raw_output = response.content.strip()

        # Record attempt for escalation
        mgr.record_attempt(
            error_key=error_key,
            phase="sc" if phase == "sc" else "ts",
            error_detail=error_desc[:500],
            code_snapshot=current_gvd[:1000] if current_gvd else "",
        )

        cprint(f"  ✅ Debugger LLM returned {len(raw_output.splitlines())} lines")

        return {
            "_raw_llm_output": raw_output,
            "_last_llm_source": "debugger",
            "multi_attempt_mgr": mgr,
            "escalation_level": f"L{esc_level}",
        }

    # ──────────────────────────────────────────────────────────
    # Node 5b: Patcher — Apply JSON patch to GVD
    # ──────────────────────────────────────────────────────────
    def node_patcher(self, state: COMBAState) -> dict:
        """
        Patch Applier (v2).
        1. Save snapshot sgvd
        2. Normalize whitespace before match
        3. Validate: buggy_code exists in GVD?
        4. If found → str.replace() → new GVD
        5. If NOT found → fuzzy match or skip (keep GVD unchanged)
        6. Compare error count: increase → rollback to sgvd
        """
        cprint("\n" + "=" * 60)
        cprint("🩹 NODE: Patch Applier")
        cprint("=" * 60)

        patch = state.get("debugger_patch")
        current_gvd = state["gvd"]

        # ── Rollback Manager: Save snapshot ──
        sgvd = current_gvd
        sc_prev_exception_count = state["sc_exception_count"]

        if not patch or not patch.get("buggy_code") or not patch.get("correct_code"):
            cprint("  ⚠️ No valid patch, keeping current GVD")
            return {
                "sgvd": sgvd,
                "sc_prev_exception_count": sc_prev_exception_count,
                "rollback_triggered": True,
            }

        buggy_code = patch["buggy_code"]
        correct_code = patch["correct_code"]

        # Try exact match first
        if buggy_code in current_gvd:
            new_gvd = current_gvd.replace(buggy_code, correct_code, 1)
            cprint(f"  ✅ Exact match found — patch applied")
        else:
            # Try normalized whitespace match
            normalized_gvd = self._normalize_whitespace(current_gvd)
            normalized_buggy = self._normalize_whitespace(buggy_code)

            if normalized_buggy in normalized_gvd:
                # Find the actual lines and replace
                new_gvd = self._fuzzy_replace(current_gvd, buggy_code, correct_code)
                if new_gvd != current_gvd:
                    cprint(f"  ✅ Fuzzy match found — patch applied")
                else:
                    cprint(f"  ⚠️ Fuzzy match failed to apply, keeping current GVD")
                    return {
                        "sgvd": sgvd,
                        "sc_prev_exception_count": sc_prev_exception_count,
                        "rollback_triggered": True,
                    }
            else:
                cprint(f"  ⚠️ buggy_code NOT FOUND in GVD — skipping patch")
                return {
                    "sgvd": sgvd,
                    "sc_prev_exception_count": sc_prev_exception_count,
                    "rollback_triggered": True,
                }

        # Ensure trailing newline
        if new_gvd and not new_gvd.endswith("\n"):
            new_gvd += "\n"

        cprint(f"  📝 GVD updated: {len(new_gvd.splitlines())} lines")

        return {
            "gvd": new_gvd,
            "sgvd": sgvd,
            "sc_prev_exception_count": sc_prev_exception_count,
            "rollback_triggered": False,
        }

    # ──────────────────────────────────────────────────────────
    # Node 6: Testbench Simulation — Verilator full build+run
    # ──────────────────────────────────────────────────────────
    def node_tb_sim(self, state: COMBAState) -> dict:
        """Run Icarus Verilog simulation using benchmark testbenches."""
        cprint("\n" + "=" * 60)
        cprint(f"🧪 NODE: TB Simulation (TS trial #{state['ts_trial'] + 1})")
        cprint("=" * 60)

        module_name = state["module_name"]
        work_dir = state["work_dir"]
        gvd = state["gvd"]
        dataset_dir = state.get("dataset_dir")

        # Write current GVD to work dir
        verilog_path = os.path.join(work_dir, f"{module_name}.sv")
        with open(verilog_path, "w", encoding="utf-8") as f:
            f.write(gvd)

        # ── Link Test/Ref files ──
        if not dataset_dir:
            return {
                "tb_log": "error: dataset_dir not found in state",
                "tb_failure": "Infrastructure error: dataset_dir missing",
                "ts_trial": state["ts_trial"] + 1,
                "total_iter": state["total_iter"] + 1,
                "phase": "ts",
            }

        # Use benchmark_id for file identity in the dataset
        bid = state.get("benchmark_id", module_name)
        test_sv_src = os.path.join(dataset_dir, f"{bid}_test.sv")
        ref_sv_src = os.path.join(dataset_dir, f"{bid}_ref.sv")
        test_sv_dst = os.path.join(work_dir, f"{bid}_test.sv")
        ref_sv_dst = os.path.join(work_dir, f"{bid}_ref.sv")

        try:
            if os.path.isfile(test_sv_src) and not os.path.isfile(test_sv_dst):
                shutil.copy2(test_sv_src, test_sv_dst)
            if os.path.isfile(ref_sv_src) and not os.path.isfile(ref_sv_dst):
                shutil.copy2(ref_sv_src, ref_sv_dst)
        except Exception as e:
            return {
                "tb_log": f"error: failed to copy test/ref files: {e}",
                "tb_failure": "Infrastructure error: testbench copy failed",
                "ts_trial": state["ts_trial"] + 1,
                "total_iter": state["total_iter"] + 1,
                "phase": "ts",
            }

        # ── Refactor: Rename module to TopModule for the testbench ──
        # VerilogEval testbenches expect the DUT to be named "TopModule"
        gvd = state.get("gvd", "")
        if not gvd:
             return {
                "tb_log": "error: no generated Verilog code found",
                "tb_failure": "Infrastructure error: missing GVD",
                "ts_trial": state["ts_trial"] + 1,
                "total_iter": state["total_iter"] + 1,
                "phase": "ts",
            }

        # Regex replacement: module <any_name> ... -> module TopModule ...
        # Using a generic regex to match the first module definition found
        top_module_code = re.sub(
            r'module\s+[a-zA-Z0-9_]+',
            'module TopModule',
            gvd,
            count=1,
            flags=re.MULTILINE
        )
        
        top_module_dst = os.path.join(work_dir, "TopModule.sv")
        with open(top_module_dst, "w", encoding="utf-8") as f:
            f.write(top_module_code)

        # ── Build iverilog command ──
        binary_out = f"{module_name}.vvp"
        comp_cmd = [
            "iverilog",
            "-Wall",
            "-Winfloop",
            "-Wno-timescale",
            "-g2012",
            "-s", "tb",
            "-o", binary_out,
            "TopModule.sv",  # Use the renamed module
            f"{bid}_test.sv",
            f"{bid}_ref.sv"
        ]

        tb_log_parts = []
        try:
            # Compile
            r1 = subprocess.run(
                comp_cmd, cwd=work_dir,
                capture_output=True, text=True, timeout=60,
            )
            tb_log_parts.append(f"[COMPILE]\n{r1.stderr}{r1.stdout}")

            if r1.returncode != 0:
                tb_log_parts.append("[COMPILE FAILED]")
                # Include iverilog error in simulation failure for TED to pick up
                failure_reason = "iverilog compilation failed"
                if r1.stderr:
                    # Clean up common noise to keep failure string short
                    first_err = r1.stderr.splitlines()[0] if r1.stderr.splitlines() else r1.stderr
                    failure_reason = f"iverilog compilation failed: {first_err[:80]}"
                
                return {
                    "tb_log": "\n".join(tb_log_parts),
                    "tb_failure": failure_reason,
                    "ts_trial": state["ts_trial"] + 1,
                    "total_iter": state["total_iter"] + 1,
                    "phase": "ts",
                }

            # Run (vvp)
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

        tb_log = "\n".join(tb_log_parts)

        # Detect failures: "Failed" or "Mismatches: [>0]" in logs
        failure = None
        for line in tb_log.splitlines():
            if "Failed" in line:
                failure = line.strip()
                break
            # Handle verilog-eval mismatch format: "Mismatches: 386 in 439 samples"
            if "Mismatches:" in line:
                match = re.search(r'Mismatches:\s*(\d+)', line)
                if match and int(match.group(1)) > 0:
                    failure = line.strip()
                    break

        if not failure and "[RUN FAILED]" in tb_log:
            failure = "Simulation exited with non-zero code"

        status_msg = "PASS ✅" if not failure else f"FAIL: {failure[:60]}"
        cprint(f"  TB result: {status_msg}")

        return {
            "tb_log": tb_log,
            "tb_failure": failure,
            "ts_trial": state["ts_trial"] + 1,
            "total_iter": state["total_iter"] + 1,
            "phase": "ts",
        }

    # ──────────────────────────────────────────────────────────
    # Node 7: TED TB — Parse topmost TB failure → TDP
    # ──────────────────────────────────────────────────────────
    def node_ted_tb(self, state: COMBAState) -> dict:
        """
        Topmost Exception Detection for Testbench.
        Parse tb_log → extract topmost failure → TDP.
        Update EDTM tracker for TB failures.
        """
        cprint("\n" + "=" * 60)
        cprint("🔎 NODE: TED TB (Parse topmost TB failure)")
        cprint("=" * 60)

        tb_log = state["tb_log"] or ""
        edtm = dict(state.get("edtm", {}))   # shallow copy

        # Extract topmost failure line
        topmost_failure = None
        for line in tb_log.splitlines():
            stripped = line.strip()
            # Look for TODO X Failed pattern (COMBA TB convention)
            if re.search(r'TODO\s+\d+\s+Failed', stripped):
                topmost_failure = stripped
                break
            # Also catch assertion failures
            if "Assertion" in stripped and "failed" in stripped.lower():
                topmost_failure = stripped
                break

        if not topmost_failure:
            # Fallback: use the tb_failure from state
            topmost_failure = state.get("tb_failure", "Unknown testbench failure")

        # EDTM tracking for TB failures (prefixed with "TB:")
        sig_tb = "TB:" + re.sub(r'\d+', 'N', topmost_failure).strip()
        sig_tb = re.sub(r'\s+', ' ', sig_tb)
        edtm[sig_tb] = edtm.get(sig_tb, 0) + 1
        cprint(f"  📊 EDTM TB count for this sig: {edtm[sig_tb]}")

        tdp = f"Topmost testbench failure:\n{topmost_failure}"

        # Include traces (lines after the failure for context)
        trace_lines = []
        found = False
        for line in tb_log.splitlines():
            if found and len(trace_lines) < 5:
                if "TRACE" in line or "INPUT" in line or "OUTPUT" in line:
                    trace_lines.append(line.strip())
            if topmost_failure and topmost_failure in line:
                found = True

        if trace_lines:
            tdp += "\n\nDebug traces:\n" + "\n".join(trace_lines)

        cprint(f"  📋 TDP: {topmost_failure[:80]}")

        return {
            "tdp": tdp,
            "phase": "ts",
            "edtm": edtm,
        }

    # ──────────────────────────────────────────────────────────
    # Utility: Extract Verilog from LLM response
    # ──────────────────────────────────────────────────────────
    def _parse_debugger_json(self, content: str) -> Optional[dict]:
        """Parse JSON patch {buggy_code, correct_code} from debugger output."""
        # Try direct JSON parse
        try:
            data = json.loads(content)
            if "buggy_code" in data and "correct_code" in data:
                return {
                    "buggy_code": data["buggy_code"],
                    "correct_code": data["correct_code"],
                }
        except (json.JSONDecodeError, AttributeError):
            pass

        # Try extracting JSON from markdown code block
        json_match = re.search(
            r'```(?:json)?\s*\n(.*?)\n```',
            content, re.DOTALL
        )
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if "buggy_code" in data and "correct_code" in data:
                    return {
                        "buggy_code": data["buggy_code"],
                        "correct_code": data["correct_code"],
                    }
            except (json.JSONDecodeError, AttributeError):
                pass

        # Try extracting JSON object from mixed text
        brace_match = re.search(r'\{[^{}]*"buggy_code"[^{}]*"correct_code"[^{}]*\}', content, re.DOTALL)
        if not brace_match:
            brace_match = re.search(r'\{[^{}]*"correct_code"[^{}]*"buggy_code"[^{}]*\}', content, re.DOTALL)
        if brace_match:
            try:
                data = json.loads(brace_match.group(0))
                if "buggy_code" in data and "correct_code" in data:
                    return {
                        "buggy_code": data["buggy_code"],
                        "correct_code": data["correct_code"],
                    }
            except (json.JSONDecodeError, AttributeError):
                pass

        return None

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Collapse all whitespace to single spaces for fuzzy matching."""
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def _fuzzy_replace(source: str, buggy: str, correct: str) -> str:
        """
        Fuzzy replace: normalize both sides, find match, replace in original.
        Falls back to line-by-line matching.
        """
        # Normalize the buggy code to compare
        buggy_lines = [l.strip() for l in buggy.strip().splitlines()]
        source_lines = source.splitlines()

        # Find the starting line index
        for i in range(len(source_lines) - len(buggy_lines) + 1):
            match = True
            for j, bl in enumerate(buggy_lines):
                if source_lines[i + j].strip() != bl:
                    match = False
                    break
            if match:
                # Replace the matched lines
                correct_lines = correct.strip().splitlines()
                new_lines = source_lines[:i] + correct_lines + source_lines[i + len(buggy_lines):]
                return "\n".join(new_lines) + "\n"

        return source  # no match found

    def _extract_verilog(self, content: str) -> str:
        """Extract Verilog code from various LLM output formats."""
        # Try JSON format first
        try:
            data = json.loads(content)
            code = data.get("code", "")
            if code:
                return code
        except (json.JSONDecodeError, AttributeError):
            pass

        # Try markdown code block
        code_match = re.search(
            r'```(?:verilog|v)?\s*\n(.*?)\n```',
            content, re.DOTALL
        )
        if code_match:
            return code_match.group(1)

        # Raw content — if it looks like Verilog
        if "module " in content or "endmodule" in content:
            return content

        return content


# ──────────────────────────────────────────────────────────────
# 3. Seven Conditional Edges (Routing Functions)
# ──────────────────────────────────────────────────────────────

def route_after_sanitizer(state: COMBAState) -> str:
    """Route Ⓕ: After Sanitizer — needs retry? → re-query LLM, else → SC."""
    result = state.get("sanitize_result") or {}
    if result.get("needs_retry"):
        # Re-query the source (generator or debugger)
        source = state.get("_last_llm_source", "generator")
        if source == "debugger":
            return "node_debugger"
        return "node_generator"
    # Code always passes through to Verilator
    return "node_syntax_check"


def route_after_sc(state: COMBAState) -> str:
    """Route Ⓐ: After Syntax Check — has errors? → TED_SC, else → TB."""
    if state["sc_exception_count"] > 0:
        return "node_ted_syntax"
    return "node_tb_sim"


def route_after_ts(state: COMBAState) -> str:
    """Route Ⓑ: After TB Sim — has failures? → TED_TB, else → PASS."""
    if state.get("tb_failure"):
        return "node_ted_tb"
    return "end_pass"


def route_after_ted_syntax(state: COMBAState) -> str:
    """Route Ⓒ: After TED Syntax — no error → TB, limit/give-up → fail, else → debugger."""
    # If TED couldn't parse any error, skip debugger → go directly to TB
    if not state.get("sc_exception"):
        return "node_tb_sim"
    if state["sc_trial"] >= MAX_SC_TRIALS:
        return "end_fail_sc"
    # Check MultiAttemptManager.should_give_up if available
    mgr = state.get("multi_attempt_mgr")
    if mgr is not None:
        error_key = re.sub(r':\d+:', ':N:', (state.get("sc_exception") or ""))
        error_key = re.sub(r'\s+', ' ', error_key).strip()[:100]
        if mgr.should_give_up(error_key):
            cprint(f"  ⛔ MultiAttempt: giving up on error_key: {error_key[:50]}")
            return "end_fail_sc"
    return "node_debugger"


def route_after_ted_tb(state: COMBAState) -> str:
    """Route Ⓓ: After TED TB — TS trial limit or give-up → fail, else → debugger."""
    if state["ts_trial"] >= MAX_TS_TRIALS:
        return "end_fail_ts"
    # Check MultiAttemptManager.should_give_up if available
    mgr = state.get("multi_attempt_mgr")
    if mgr is not None:
        tb_failure = state.get("tb_failure", "")
        error_key = re.sub(r'\s+', ' ', tb_failure).strip()[:100]
        if mgr.should_give_up(error_key):
            cprint(f"  ⛔ MultiAttempt: giving up on TB error: {error_key[:50]}")
            return "end_fail_ts"
    return "node_debugger"


def route_after_patcher(state: COMBAState) -> str:
    """Route Ⓔ: After Patcher — total iteration limit → extraction_guard or fail."""
    if state["total_iter"] >= MAX_TOTAL_ITER:
        return "end_max_iter"
    return "node_extraction_guard"


# ──────────────────────────────────────────────────────────────
# Terminal Nodes (set final_status)
# ──────────────────────────────────────────────────────────────

def end_pass(state: COMBAState) -> dict:
    """All checks passed!"""
    cprint("\n🎉 PIPELINE COMPLETE: ALL PASS!")
    return {"final_status": "pass"}


def end_fail_sc(state: COMBAState) -> dict:
    """SC trial limit reached."""
    cprint(f"\n❌ PIPELINE FAILED: SC trial limit ({MAX_SC_TRIALS}) reached")
    return {"final_status": "fail_sc"}


def end_fail_ts(state: COMBAState) -> dict:
    """TS trial limit reached."""
    cprint(f"\n❌ PIPELINE FAILED: TS trial limit ({MAX_TS_TRIALS}) reached")
    return {"final_status": "fail_ts"}


def end_max_iter(state: COMBAState) -> dict:
    """Total iteration limit reached."""
    cprint(f"\n❌ PIPELINE FAILED: Total iteration limit ({MAX_TOTAL_ITER}) reached")
    return {"final_status": "max_iter"}


# ──────────────────────────────────────────────────────────────
# 4. Build Graph
# ──────────────────────────────────────────────────────────────

def build_comba_graph(llm):
    """
    Build the full COMBA verification pipeline v3 as a LangGraph.

    Graph topology (9 pipeline nodes, 7 conditional edges):
        START → converter → generator → sanitizer
               ┌────────────────────────────────────────────┐
               ↓                                            │
        syntax_check ──(pass)──→ tb_sim                     │
               │                   │                        │
               ↓ (fail)            ↓ (fail)                 │
        ted_syntax            ted_tb                        │
               │                   │                        │
               ↓                   ↓                        │
        debugger → sanitizer → syntax_check ────────────────┘
                       │
                       ↓ (needs_retry, max 2)
                   re-query LLM

    Args:
        llm: LangChain-compatible chat model.

    Returns:
        Compiled LangGraph StateGraph.
    """
    nodes = COMBANodes(llm)

    builder = StateGraph(COMBAState)

    # ── Add all 9 pipeline nodes ──
    builder.add_node("node_converter", nodes.node_converter)
    builder.add_node("node_generator", nodes.node_generator)
    builder.add_node("node_sanitizer", nodes.node_sanitizer)
    builder.add_node("node_syntax_check", nodes.node_syntax_check)
    builder.add_node("node_ted_syntax", nodes.node_ted_syntax)
    builder.add_node("node_debugger", nodes.node_debugger)
    builder.add_node("node_tb_sim", nodes.node_tb_sim)
    builder.add_node("node_ted_tb", nodes.node_ted_tb)

    # Terminal nodes
    builder.add_node("end_pass", end_pass)
    builder.add_node("end_fail_sc", end_fail_sc)
    builder.add_node("end_fail_ts", end_fail_ts)
    builder.add_node("end_max_iter", end_max_iter)

    # ── Linear edges ──
    builder.add_edge(START, "node_converter")
    builder.add_edge("node_converter", "node_generator")
    builder.add_edge("node_generator", "node_sanitizer")
    builder.add_edge("node_debugger", "node_sanitizer")

    # Terminal → END
    builder.add_edge("end_pass", END)
    builder.add_edge("end_fail_sc", END)
    builder.add_edge("end_fail_ts", END)
    builder.add_edge("end_max_iter", END)

    # ── Conditional edges (7 routing decisions) ──

    # After sanitizer → SC (normal) or re-query LLM (hard failure, max 2)
    builder.add_conditional_edges(
        "node_sanitizer",
        route_after_sanitizer,
        {
            "node_syntax_check": "node_syntax_check",
            "node_generator": "node_generator",
            "node_debugger": "node_debugger",
        },
    )

    builder.add_conditional_edges(
        "node_syntax_check",
        route_after_sc,
        {"node_ted_syntax": "node_ted_syntax", "node_tb_sim": "node_tb_sim"},
    )

    builder.add_conditional_edges(
        "node_tb_sim",
        route_after_ts,
        {"node_ted_tb": "node_ted_tb", "end_pass": "end_pass"},
    )

    builder.add_conditional_edges(
        "node_ted_syntax",
        route_after_ted_syntax,
        {"node_tb_sim": "node_tb_sim", "node_debugger": "node_debugger", "end_fail_sc": "end_fail_sc"},
    )

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
        description="COMBA-PROMPT Full Verification Pipeline"
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
    print(f"{'=' * 60}")

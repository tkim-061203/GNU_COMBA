"""
multi_attempt.py — Escalating Multi-Attempt Correction
=======================================================
Replaces same-prompt retry with escalating strategy.

Key idea: Each retry attempt adds MORE context about why previous fix failed.
After N attempts with same error, switch strategy entirely.

Integrates with:
  - extraction_guard.py (ExtractionResult.retry_prompt)
  - EDTM tracking (trialTimes per exception)
  - Category-specific hints

Usage:
    from multi_attempt import MultiAttemptManager
    mgr = MultiAttemptManager()
    prompt = mgr.build_correction_prompt(state)
    # ... call LLM, get result ...
    mgr.record_attempt(state, success=False, error_info={...})
    # Next call to build_correction_prompt auto-escalates
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

class DebugPhase(Enum):
    SYNTAX = "sc"
    TESTBENCH = "ts"


class EscalationLevel(Enum):
    L0_STANDARD = 0       # Normal EDP/TDP
    L1_WITH_HISTORY = 1   # Add previous attempt context
    L2_HINT = 2           # Add category-specific hint
    L3_RETHINK = 3        # Force complete rethink
    L4_SKELETON = 4       # Provide skeleton, ask to fill


# Category-specific hints for fail_ts modules
CATEGORY_HINTS = {
    # Arithmetic overflow
    "accu": "Check accumulator bit-width. Output should be wider than input to avoid overflow. Verify reset clears all bits.",
    "adder_16bit": "Check the carry-out logic for each stage. The carry-out of the first 8-bit block MUST be the carry-in of the second. Ensure the final 16-bit output 'y' is concatenated correctly from all partial sums.",
    "adder_32bit": "Use a Carry-Lookahead (CLA) or Ripple Carry approach. Ensure ALL output ports (S, C32) are driven using 'assign' or 'always' blocks. Do not leave the module body empty.",
    "adder_pipe_64bit": "Check that ALL ports in the module(...) list are also declared as input/output/reg/wire inside the module. Maintain 4 distinct pipeline stages, each stage must latch its sum and the carry-out to the next stage.",
    "div_16bit": "Division requires iterative subtraction or shift-subtract. Check quotient and remainder bit-widths. Handle divide-by-zero.",
    "div_8bit": "Verify restoring/non-restoring division algorithm. Check that remainder is updated correctly each iteration.",

    # Pipeline timing
    "multi_pipe_4bit": "Verify partial product accumulation across pipeline stages. Check valid/enable propagation through stages.",
    "multi_pipe_8bit": "Pipeline multiplier: each stage computes partial products. Verify stage count matches latency. Check mul_en_out timing.",

    # FSM logic
    "fsm": "Check state encoding (one-hot vs binary). Verify ALL state transitions have explicit next-state. Check default case.",
    "traffic_light": "Verify timer/counter for each light phase. Check state transition conditions. Green→Yellow→Red cycle timing.",

    # Serial/Parallel conversion
    "parallel2serial": "Verify shift direction (MSB-first or LSB-first). Check load vs shift mode. Counter must match data width.",
    "serial2parallel": "Verify shift register fills completely before asserting valid. Check bit ordering matches spec.",
    "width_8to16": "Two 8-bit inputs must be concatenated correctly. Verify which byte is MSB vs LSB. Check valid signal timing.",

    # Clock/Synchronization
    "freq_div": "Check divisor value and toggle logic. Even division: toggle at count/2. Odd division: need duty cycle correction.",
    "synchronizer": "Multi-flop synchronizer: verify 2+ flip-flop stages. Check that output is delayed by correct cycles.",
    "right_shifter": "Verify shift amount and direction. Check arithmetic vs logical shift. Verify fill bit (0 or sign-extend).",
    "alu": "ALU logic: Ensure all operations (ADD, SUB, AND, OR, XOR, SHIFT) are handled. For arithmetic shifts (SRA/SRAV), use signed shift operator '>>>' or explicit always blocks with signed casting. Check that output 'result' is assigned in all cases.",
    "asyn_fifo": "Asynchronous FIFO: Ensure 'ADDR_WIDTH' and 'DEPTH' are correctly handled. Gray code conversion for pointers is critical. Use $clog2(DEPTH) for address width calculation. Match port names 'wfull' and 'rempty' exactly in assignments.",
    "multi_pipe_4bit": "4-bit Pipelined Multiplier: Break down multiplication into 4 stages. Each stage must accumulate partial products. Ensure all pipeline registers are reset correctly.",
}


# ─────────────────────────────────────────────
# Attempt History Entry
# ─────────────────────────────────────────────

@dataclass
class AttemptRecord:
    attempt_num: int
    phase: DebugPhase
    error_key: str          # EDTM key: {type}_{title}_{content} or {todoNum}_{failure}
    error_detail: str       # Human-readable error description
    code_snapshot: str      # GVD at time of attempt (for diff context)
    extraction_failed: bool = False
    extraction_retry_prompt: Optional[str] = None


# ─────────────────────────────────────────────
# Main Class
# ─────────────────────────────────────────────

class MultiAttemptManager:
    """
    Manages escalating correction prompts across retry attempts.

    State machine per error_key:
      L0 (attempt 1)   → Standard EDP/TDP
      L1 (attempt 2)   → + "Previous attempt also failed: {reason}"
      L2 (attempt 3)   → + Category hint
      L3 (attempt 4)   → Force rethink: "Discard previous approach entirely"
      L4 (attempt 5+)  → Provide module skeleton, ask to fill logic only
    """

    def __init__(self, max_attempts_per_error: int = 5):
        self.max_attempts = max_attempts_per_error
        self.history: dict[str, list[AttemptRecord]] = {}  # error_key → attempts

    def get_escalation_level(self, error_key: str) -> EscalationLevel:
        """Determine current escalation level based on attempt count."""
        count = len(self.history.get(error_key, []))
        if count == 0:
            return EscalationLevel.L0_STANDARD
        elif count == 1:
            return EscalationLevel.L1_WITH_HISTORY
        elif count == 2:
            return EscalationLevel.L2_HINT
        elif count == 3:
            return EscalationLevel.L3_RETHINK
        else:
            return EscalationLevel.L4_SKELETON

    def should_give_up(self, error_key: str) -> bool:
        """True if max attempts reached for this error."""
        return len(self.history.get(error_key, [])) >= self.max_attempts

    def record_attempt(
        self,
        error_key: str,
        phase: DebugPhase,
        error_detail: str,
        code_snapshot: str,
        extraction_failed: bool = False,
        extraction_retry_prompt: Optional[str] = None,
    ):
        """Record a failed attempt for escalation tracking."""
        if error_key not in self.history:
            self.history[error_key] = []

        self.history[error_key].append(AttemptRecord(
            attempt_num=len(self.history[error_key]) + 1,
            phase=phase,
            error_key=error_key,
            error_detail=error_detail,
            code_snapshot=code_snapshot,
            extraction_failed=extraction_failed,
            extraction_retry_prompt=extraction_retry_prompt,
        ))

    def clear_error(self, error_key: str):
        """Clear history when error is resolved."""
        self.history.pop(error_key, None)

    # ─────────────────────────────────────────
    # Prompt Builders
    # ─────────────────────────────────────────

    def build_sc_prompt(
        self,
        error_key: str,
        module_name: str,
        gvd: str,
        exception_type: str,
        exception_title: str,
        exception_content: str,
        log_content: str,
        custom_vector: str = "",
        task_description: str = "",
    ) -> str:
        """Build escalating EDP (Exception-Debugging Prompt) for syntax fix."""

        level = self.get_escalation_level(error_key)

        # Base EDP
        base = self._base_edp(
            module_name, gvd, exception_type, exception_title,
            exception_content, log_content, custom_vector, task_description
        )

        # Escalate
        if level == EscalationLevel.L0_STANDARD:
            return base

        elif level == EscalationLevel.L1_WITH_HISTORY:
            prev = self.history[error_key][-1]
            return base + self._history_suffix(prev)

        elif level == EscalationLevel.L2_HINT:
            prev = self.history[error_key][-1]
            mod_hint = CATEGORY_HINTS.get(module_name, "")
            
            # Extract error-specific hints
            err_hint = ""
            error_str = f"{exception_title} {exception_content} {prev.error_detail}".lower()
            hints_found = []
            if "undriven" in error_str:
                hints_found.append("You have an output port that is never assigned")
            if "undefined" in error_str or "undeclared" in error_str:
                hints_found.append("Check variable name spelling and case sensitivity")
            if "bit-select" in error_str or "selwid" in error_str or "bit select" in error_str:
                hints_found.append("Check output width declaration matches spec")
            
            err_hint = " | ".join(hints_found)
            
            combined_hint = mod_hint
            if err_hint:
                combined_hint = combined_hint + "\n" + err_hint if combined_hint else err_hint
                
            return base + self._history_suffix(prev) + self._hint_suffix(combined_hint)

        elif level == EscalationLevel.L3_RETHINK:
            return self._rethink_prompt(module_name, gvd, "syntax",
                                         exception_content, task_description)

        else:  # L4_SKELETON
            return self._skeleton_prompt(module_name, gvd, task_description)

    def build_ts_prompt(
        self,
        error_key: str,
        module_name: str,
        gvd: str,
        todo_num: int,
        trace_content: str,
        failure_content: str,
        testbench_content: str = "",
        task_description: str = "",
    ) -> str:
        """Build escalating TDP (Testbench-Debugging Prompt) for functional fix."""

        level = self.get_escalation_level(error_key)

        # Base TDP
        base = self._base_tdp(
            module_name, gvd, todo_num, trace_content,
            failure_content, testbench_content, task_description
        )

        if level == EscalationLevel.L0_STANDARD:
            return base

        elif level == EscalationLevel.L1_WITH_HISTORY:
            prev = self.history[error_key][-1]
            return base + self._history_suffix(prev)

        elif level == EscalationLevel.L2_HINT:
            prev = self.history[error_key][-1]
            mod_hint = CATEGORY_HINTS.get(module_name, "")
            
            # Extract error-specific hints from failure_content
            err_hint = ""
            error_str = f"{failure_content} {prev.error_detail}".lower()
            hints_found = []
            if "assertion" in error_str or "failed" in error_str:
                hints_found.append("The simulation result does not match the expected value. Check your arithmetic logic.")
            if "timeout" in error_str:
                hints_found.append("Check for infinite loops in always blocks or incorrect clock/reset logic.")
            
            err_hint = " | ".join(hints_found)
            combined_hint = mod_hint
            if err_hint:
                combined_hint = combined_hint + "\n" + err_hint if combined_hint else err_hint

            return base + self._history_suffix(prev) + self._hint_suffix(combined_hint)

        elif level == EscalationLevel.L3_RETHINK:
            return self._rethink_prompt(module_name, gvd, "testbench",
                                         failure_content, task_description)

        else:  # L4_SKELETON
            return self._skeleton_prompt(module_name, gvd, task_description)

    # ─────────────────────────────────────────
    # Base Prompt Templates
    # ─────────────────────────────────────────

    def _base_edp(self, module_name, gvd, exc_type, exc_title,
                  exc_content, log_content, custom_vec, task_desc):
        parts = [
            "As a professional Verilog designer, debug the following module.",
            "",
        ]
        if task_desc:
            parts.append(f"Task: {task_desc}")
            parts.append("")

        parts.extend([
            f"Module: {module_name}",
            f"Current Code:\n{gvd}",
            "",
            "Compiler Error:",
            f"  Type: {exc_type}",
            f"  Title: {exc_title}",
            f"  Content: {exc_content}",
            f"  Location: {log_content}",
        ])
        
        # Check for missing sub-module
        chk_str = f"{exc_title} {exc_content}".upper()
        if "MODMISSING" in chk_str or "CANNOT FIND FILE CONTAINING MODULE" in chk_str:
            import re
            match = re.search(r"(?:module|Module)[^a-zA-Z0-9_]+([a-zA-Z0-9_]+)", exc_content)
            sub_mod = match.group(1) if match else "UNKNOWN"
            parts.extend([
                "",
                f"ERROR: You instantiated sub-module '{sub_mod}' but its definition is missing. Because this is a single-file design, you MUST provide the complete Verilog implementation for '{sub_mod}' (and any other missing sub-modules) in the same file. Append the missing module definition(s) at the end."
            ])

        if custom_vec:
            parts.extend(["", f"Context: {custom_vec}"])

        parts.extend([
            "",
            f"Output the COMPLETE corrected module '{module_name}' from 'module' to 'endmodule'.",
            "Output ONLY Verilog code, no explanation.",
        ])
        return "\n".join(parts)

    def _base_tdp(self, module_name, gvd, todo_num, trace, failure, tb_content, task_desc):
        parts = [
            "As a professional Verilog designer, fix the testbench failure.",
            "",
        ]
        if task_desc:
            parts.append(f"Task: {task_desc}")
            parts.append("")

        parts.extend([
            f"Module: {module_name}",
            f"Current Code (passed syntax check):\n{gvd}",
            "",
            "Testbench Failure:",
            f"  TODO Block: {todo_num}",
            f"  Expected vs Actual:\n{trace}",
            f"  Failure: {failure}",
        ])

        if tb_content:
            parts.extend(["", f"Testbench Reference:\n{tb_content}"])

        parts.extend([
            "",
            f"Output the COMPLETE corrected module '{module_name}' from 'module' to 'endmodule'.",
            "Output ONLY Verilog code, no explanation.",
        ])
        return "\n".join(parts)

    # ─────────────────────────────────────────
    # Escalation Suffixes
    # ─────────────────────────────────────────

    def _history_suffix(self, prev: AttemptRecord) -> str:
        return (
            "\n\n--- IMPORTANT ---\n"
            f"A previous attempt to fix this ALSO FAILED with the same error:\n"
            f"  {prev.error_detail}\n"
            f"Your previous code snapshot was:\n{prev.code_snapshot[:500]}...\n"
            "Your previous fix failed to resolve this specific error. "
            "Please analyze why the previous change was insufficient and try a NEW approach.\n"
        )

    def _hint_suffix(self, hint: str) -> str:
        if not hint:
            return ""
        return (
            "\n--- DESIGN HINT ---\n"
            f"{hint}\n"
            "Use this hint to guide your fix.\n"
        )

    def _rethink_prompt(self, module_name, gvd, error_type, error_desc, task_desc):
        return (
            "CRITICAL: Multiple previous attempts to fix this module have ALL FAILED.\n"
            "You MUST completely rethink your approach.\n\n"
            f"Module: {module_name}\n"
            f"Task: {task_desc}\n\n"
            f"The current code has a persistent {error_type} error:\n"
            f"  {error_desc}\n\n"
            "DO NOT make incremental changes. Instead:\n"
            "1. Re-read the task description carefully\n"
            "2. Design the logic from scratch\n"
            "3. Write a clean implementation\n\n"
            f"Output the COMPLETE module '{module_name}' from 'module' to 'endmodule'.\n"
            "Output ONLY Verilog code, no explanation."
        )

    def _skeleton_prompt(self, module_name, gvd, task_desc):
        """Extract port declaration from current GVD and ask LLM to fill logic."""
        # Extract just the port section
        import re
        port_match = re.search(
            r'(module\s+' + re.escape(module_name) + r'\s*[\s\S]*?;)',
            gvd
        )
        skeleton = port_match.group(1) if port_match else f"module {module_name}(...);"

        # Also extract wire/reg declarations
        decls = re.findall(
            r'^\s*(input|output|inout|wire|reg|parameter|localparam)\b.*$',
            gvd, re.MULTILINE
        )
        decl_block = "\n".join(decls) if decls else ""

        return (
            "ALL previous attempts have failed. Here is the module skeleton.\n"
            "Fill in ONLY the behavioral logic (always blocks, assign statements).\n\n"
            f"Task: {task_desc}\n\n"
            f"Skeleton:\n{skeleton}\n"
            f"{decl_block}\n\n"
            "    // YOUR LOGIC HERE\n\n"
            "endmodule\n\n"
            f"Output the COMPLETE module '{module_name}' with your logic filled in.\n"
            "Output ONLY Verilog code, no explanation."
        )

    # ─────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return attempt statistics for benchmarking."""
        stats = {}
        for key, attempts in self.history.items():
            stats[key] = {
                "total_attempts": len(attempts),
                "extraction_failures": sum(1 for a in attempts if a.extraction_failed),
                "last_level": self.get_escalation_level(key).name,
            }
        return stats


# ─────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    mgr = MultiAttemptManager(max_attempts_per_error=5)

    error_key = "Error_WIDTHEXPAND_OperatorADD"
    module = "adder_32bit"
    gvd = "module adder_32bit(input [31:0] a, b, output [31:0] sum);\nassign sum = a + b;\nendmodule"

    print("=== Escalation Demo ===")
    for i in range(6):
        if mgr.should_give_up(error_key):
            print(f"\n  Attempt {i+1}: GIVE UP (max attempts reached)")
            break

        level = mgr.get_escalation_level(error_key)
        print(f"\n  Attempt {i+1}: Level={level.name}")

        prompt = mgr.build_sc_prompt(
            error_key=error_key,
            module_name=module,
            gvd=gvd,
            exception_type="Warning",
            exception_title="WIDTHEXPAND",
            exception_content="Operator ADD expects 33 bits",
            log_content="adder_32bit.v:2",
            custom_vector="Bit width expansion warning",
            task_description="32-bit adder with carry out",
        )
        print(f"  Prompt length: {len(prompt)} chars")
        print(f"  First 80 chars: {prompt[:80]}...")

        # Simulate failure
        mgr.record_attempt(
            error_key=error_key,
            phase=DebugPhase.SYNTAX,
            error_detail="WIDTHEXPAND still present after fix",
            code_snapshot=gvd,
        )

    print(f"\n  Stats: {mgr.get_stats()}")
    print("\n✅ Multi-attempt escalation test completed.")

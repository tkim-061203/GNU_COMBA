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

import re
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from prompts import _ERROR_PATTERNS, _ERROR_CONSTRAINTS


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
    "adder_pipe_64bit": "Pipelined 64-bit adder: You MUST use the exact port names 'adda', 'addb', and 'result' as defined in the spec. Maintain 4 distinct pipeline stages. Each stage must latch its partial sum and the carry-out to the next stage. Ensure 'o_en' is delayed by the same number of clock cycles as the data pipeline.",
    "div_16bit": "Division requires iterative subtraction or shift-subtract. Check quotient and remainder bit-widths. Handle divide-by-zero.",
    "div_8bit": "8-bit Divider: Use a single 'always' block for the FSM and data path registers (SR, NEG_DIVISOR, cnt, start_cnt) to avoid multiple-driver errors. Ensure SR is 17 or 18 bits wide to handle the shift-subtract process correctly. The final quotient is the lower 8 bits of SR and the remainder is the upper 8 bits.",

    # Pipeline timing
    "multi_pipe_4bit": "4-bit Pipelined Multiplier: Break down multiplication into 4 stages. Each stage must accumulate partial products. Ensure all pipeline registers are reset correctly.",
    "multi_pipe_8bit": "Pipeline multiplier: each stage computes partial products. Verify stage count matches latency. Check mul_en_out timing.",

    # FSM logic
    "fsm": "Check state encoding (one-hot vs binary). Verify ALL state transitions have explicit next-state. Check default case.",
    "traffic_light": "Verify timer/counter for each light phase. Check state transition conditions. Green→Yellow→Red cycle timing.",
    "fsm_hdlc": "HDLC FSM: accurately track consecutive 1s. Usually 6 ones means flag (01111110), 5 ones followed by 0 means discard zero.",
    "lemmings": "Lemmings FSM: verify state transitions for walking left/right, falling, and digging. Falling overrides walking.",
    "thermostat": "Thermostat system: ensure hysteresis logic is correct, and transitions between heating, cooling, and idle are prioritized properly.",
    "fsm_serial": "Serial data FSM: track bits received in a counter to identify start, data, parity, and stop bits.",
    "fsm_onehot": "One-hot FSM: make sure state assignment uses exactly one bit high per state, and derivation of next state equations only uses the current state bits directly.",

    # Cellular automata and loops
    "conwaylife": "Conway's Game of Life: a live cell needs 2 or 3 neighbors to survive, a dead cell needs exactly 3 to become alive. Count 8 neighbors.",
    "rule90": "Rule 90 cellular automaton: next state of a cell is the XOR of its left and right neighbors.",
    "rule110": "Rule 110 cellular automaton: carefully implement the boolean logic for the neighborhood.",

    # Counters and specific logic
    "countbcd": "A BCD counter wraps at 9, NOT 15. Ensure each 4-bit digit resets to 0 and carries to the next digit when reaching 9.",
    "count_clock": "Clock counter: PM/AM check, wraps at 12 or 24 depending on format. AVOID Combinatorial loops (zero delay timeouts). Verify minutes/seconds wrap at 59.",
    "lfsr": "LFSR: Ensure taps are correct. Do not create combinatorial loops causing timeouts. Tap indexes are usually 1-based in standard notation. LFSR32 uses taps 32, 22, 2, 1.",
    "edgedetect": "To detect an edge, register the input and compare with current input. A rising edge is 'in & ~in_reg'.",
    "kmap": "Translate the Karnaugh map carefully to a sum-of-products (SOP) or product-of-sums (POS) expression.",
    "rotate100": "100-bit barrel shifter or rotate: implement rotate left/right based on the amount parameter.",

    # Serial/Parallel conversion
    "parallel2serial": "Verify shift direction (MSB-first or LSB-first). Check load vs shift mode. Counter must match data width.",
    "serial2parallel": "Verify shift register fills completely before asserting valid. Check bit ordering matches spec.",
    "width_8to16": "Two 8-bit inputs must be concatenated correctly. Verify which byte is MSB vs LSB. Check valid signal timing.",

    # Clock/Synchronization
    "freq_div": "Check divisor value and toggle logic. Even division: toggle at count/2. Odd division: need duty cycle correction.",
    "synchronizer": "Multi-flop synchronizer: verify 2+ flip-flop stages. Check that output is delayed by correct cycles.",
    "right_shifter": "Verify shift amount and direction. Check arithmetic vs logical shift. Verify fill bit (0 or sign-extend).",
    "alu": "ALU logic: Ensure all operations (ADD, SUB, AND, OR, XOR, SHIFT) use the CORRECT opcodes from the spec. CRITICAL: For shift operations (SLL, SRL, SRA, etc.), the shift amount is determined by operand 'a' (or 'a[4:0]') and the data to be shifted is operand 'b'. Do not swap them. Implement LUI (Load Upper Immediate) using {b[15:0], 16'b0}. Check that all 32-bit results and flags (zero, carry, negative, overflow) are correctly calculated.",
    "asyn_fifo": "Asynchronous FIFO: Ensure 'ADDR_WIDTH' and 'DEPTH' are correctly handled. Gray code conversion for pointers is critical. Use $clog2(DEPTH) for address width calculation. Match port names 'wfull' and 'rempty' exactly in assignments.",

    # Exam questions / specific bugs / timeout logic
    "bugs_": "Bug-fixing problem: Do not rewrite from scratch unless necessary. Look for missing semicolons, incorrect wire/reg declarations, blocking vs non-blocking assignments, or swapped module connections.",
    "edgecapture": "For an edge capture circuit: you must detect the edge and HOLD the state until a reset clears it. Use a flip-flop that sets to 1 on an edge and only clears on synchronized reset.",
    "truthtable": "Implement this as a continuous assignment (assign) or combinatorial always block (@*) following exactly the rows of the truth table.",
    "circuit": "Carefully trace the combinatorial logic diagram. Break it into intermediate wires for each gate output if it helps, and ensure every gate is represented correctly.",
    "muxdff": "A D-flip flop preceded by a multiplexer. Implement the MUX logic on the D-input inside the always block.",
    "JC_counter": "Johnson Counter: Verify shift logic. Q <= {{~Q[0], Q[WIDTH-1:1]}} or similar. One bit is inverted and shifted into the other end. Check shift direction.",
    "adder_pipe_64bit": "Pipelined 64-bit adder: Ensure each stage correctly carries the 'cout' to the next stage's 'cin'. All stage registers must be clocked.",
    "pulse_detect": "Pulse detector: Use a state machine or delay registers to find transitions. Ensure it ignores pulses shorter than the required threshold if specified.",
    "signal_generator": "Signal generator: Verify the waveform parameters (freq, duty cycle). Counters should wrap exactly at the period boundary.",
    "gshare": "Gshare branch predictor: XOR the PC (Program Counter) with the GHR (Global History Register) to index a PHT of 2-bit saturating counters. Ensure state transitions for the 2-bit counters are correct.",
    "m2014": "Exam question (2014): Carefully read the state transition/circuit diagram. Ensure active-high vs active-low reset is implemented exactly as asked.",
    "ece241": "Exam question (ECE): Pay strict attention to the clock edge, reset type (synchronous vs asynchronous), and any enable signals.",
    "review2015": "Review question: Verify the transition logic matches the specification exactly. Don't simplify states unless requested.",
    "2012": "Exam question (2012): Basic logic or FSM. Implement the exact function or state diagram requested.",
    "ps2": "PS/2 protocol FSM: track the start bit, 8 data bits, parity, and stop bit accurately.",
    "fancytimer": "Fancy Timer: Handle all enabled, load, and countdown states. Ensure no combinatorial loop causes simulation timeouts."
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
      L4 (attempt 5)   → Provide module skeleton, ask to fill logic only
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
            mod_hint = ""
            best_match_len = 0
            for key, hint_text in CATEGORY_HINTS.items():
                if re.search(rf'\b{re.escape(key)}\b', module_name.lower()):
                    if len(key) > best_match_len:
                        mod_hint = hint_text
                        best_match_len = len(key)
            
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
            mod_hint = ""
            best_match_len = 0
            for key, hint_text in CATEGORY_HINTS.items():
                if re.search(rf'\b{re.escape(key)}\b', module_name.lower()):
                    if len(key) > best_match_len:
                        mod_hint = hint_text
                        best_match_len = len(key)
            
            # Extract error-specific hints from failure_content
            err_hint = ""
            error_str = f"{failure_content} {prev.error_detail}".lower()
            hints_found = []
            if "assertion" in error_str or "failed" in error_str:
                hints_found.append("The simulation result does not match the expected value. Compare the 'OUTPUT TRACE' with the 'REFERENCE OUTPUT TRACE' to find where your logic differs from the specification.")
            if "timeout" in error_str:
                hints_found.append("Check for infinite loops in always blocks or incorrect clock/reset logic.")
            if "no member named" in error_str:
                match = re.search(r"no member named [‘'\"`]([a-zA-Z0-9_]+)[’'\"`]", error_str)
                if match:
                    hints_found.append(f"Port mismatch: the testbench expects a port named '{match.group(1)}'. Check for case sensitivity (e.g., 'Q' vs 'q') or spelling.")
                else:
                    hints_found.append("Port mismatch detected in Verilator. Ensure your module port names match the testbench expectations exactly.")
            
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
            "## CRITICAL RULES",
            "1. NEVER add, remove, or rename ports. The port list (header) is FIXED and forced by the testbench.",
            "   Rule: `output` → `output reg` promotion is REQUIRED if assigned in `always`. This is NOT a rename.",
            "   ANTI-PATTERN: Do NOT use `reg wave_reg; assign wave = wave_reg;`. Use `output reg wave;`.",
            "2. If the error says 'Could not find variable', DO NOT add it to the port list. Declare it internally as a wire/reg, OR rewrite the logic to use the existing ports.",
            "3. Fix ONLY the topmost error. Cascading errors resolve automatically.",
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

        for key, pat in _ERROR_PATTERNS.items():
            if pat.search(log_content):
                parts.append(_ERROR_CONSTRAINTS[key])

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
            "## CRITICAL RULES",
            "1. NEVER add, remove, or rename ports. The port list (header) is FIXED and forced by the testbench.",
            "   Rule: `output` → `output reg` promotion is REQUIRED if assigned in `always`. This is NOT a rename.",
            "   ANTI-PATTERN: Do NOT use `reg wave_reg; assign wave = wave_reg;`. Use `output reg wave;`.",
            "2. If you need to fix variable names, rewrite the internal logic to use the existing ports EXACTLY as declared.",
            "3. Do not instantiate external modules unless you define them in the same file.",
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
        # Extract the exact header to force preservation
        header_match = re.search(r'(module\s+' + re.escape(module_name) + r'\s*[\s\S]*?;)', gvd)
        header = header_match.group(1) if header_match else f"module {module_name}(...);"

        return (
            "CRITICAL: Multiple previous attempts to fix this module have ALL FAILED.\n"
            "You MUST completely rethink your approach.\n\n"
            f"Module: {module_name}\n"
            f"Task: {task_desc}\n\n"
            "REQUIRED HEADER (Ports are FIXED and matching the testbench):\n"
            f"```verilog\n{header}\n```\n\n"
            f"The current logic has a persistent {error_type} error:\n"
            f"  {error_desc}\n\n"
            "DO NOT make incremental changes. Instead:\n"
            "1. Re-read the task description carefully\n"
            "2. Design a different architectural approach\n"
            "3. Write a clean implementation using the FIXED header above\n\n"
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
            "You MUST output the COMPLETE module including the header and endmodule.\n\n"
            "CRITICAL: DO NOT change the port list. The header is FIXED.\n\n"
            f"Module: {module_name}\n"
            f"Task: {task_desc}\n\n"
            f"```verilog\n{skeleton}\n{decl_block}\n// ... Fill behavioral code here ...\nendmodule\n```"
            "\nOutput ONLY Verilog code, no explanation."
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

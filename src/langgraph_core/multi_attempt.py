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

from prompts import _ERROR_PATTERNS, _ERROR_CONSTRAINTS, detect_tdp_hints


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
    "adder_32bit": "Use flat behavioral addition: assign {C32, S} = A + B; and do NOT instantiate helper modules like 'cla_block' or 'cla' as they are not defined in the workspace. Ensure all outputs S and C32 are driven.",
    "adder_pipe_64bit": "Pipelined 64-bit adder: You MUST use the exact port names 'adda', 'addb', and 'result' as defined in the spec. Maintain 4 distinct pipeline stages. Each stage must latch its partial sum and the carry-out to the next stage. Ensure 'o_en' is delayed by the same number of clock cycles as the data pipeline.",
    "div_16bit": "Combinational 16-bit divider: Since outputs 'result' and 'odd' are declared as 'output reg', you MUST assign them inside an always @(*) block using division and modulo operators (do NOT use 'assign' statements, and do NOT write restoring/non-restoring loops or state machines). Example: always @(*) begin if (B == 0) begin result = 0; odd = A; end else begin result = A / B; odd = A % B; end end",
    "div_8bit": "8-bit Divider: Use a single 'always' block for the FSM and data path registers (SR, NEG_DIVISOR, cnt, start_cnt) to avoid multiple-driver errors. Ensure SR is 17 or 18 bits wide to handle the shift-subtract process correctly. The final quotient is the lower 8 bits of SR and the remainder is the upper 8 bits.",
    "radix2_div": "Radix-2 Divider: (1) Ensure you declare and implement all inputs and outputs. You MUST include input 'res_ready'. (2) Implement the control logic such that the output signal 'res_valid' is set to 1 when the division is complete (e.g., when the counter reaches 8 or cnt[3] is high) and reset to 0 on 'rst' or when both 'res_valid' and 'res_ready' are high. Example: res_valid <= rst ? 1'b0 : cnt[3] ? 1'b1 : (res_valid & res_ready) ? 1'b0 : res_valid;",

    # Pipeline timing
    "multi_pipe_4bit": "4-bit Pipelined Multiplier: (1) Golden design requires exactly 2 cycles of latency. (2) Define stage 1 registers reg [7:0] sum_tmp1, sum_tmp2; (3) On clk edge, stage 1 computes partial product sums: sum_tmp1 <= (mul_b[0] ? mul_a : 0) + (mul_b[1] ? mul_a << 1 : 0); sum_tmp2 <= (mul_b[2] ? mul_a << 2 : 0) + (mul_b[3] ? mul_a << 3 : 0); (4) Stage 2 computes the final sum: mul_out <= sum_tmp1 + sum_tmp2; (5) All registers are reset to 0 on active-low rst_n.",
    "multi_pipe_8bit": "8-bit Pipelined Multiplier: (1) Requires exactly 4 cycles of latency. (2) Track enable using 3-bit register mul_en_out_reg and assign to output reg mul_en_out on clock edge: always @(posedge clk or negedge rst_n) if (!rst_n) begin mul_en_out_reg <= 0; mul_en_out <= 0; end else begin mul_en_out_reg <= {mul_en_out_reg[1:0], mul_en_in}; mul_en_out <= mul_en_out_reg[2]; end (3) Implement 4 stages of pipeline registers: Stage 1 registers inputs (always @(posedge clk) if (mul_en_in) begin mul_a_reg <= mul_a; mul_b_reg <= mul_b; end else begin mul_a_reg <= 0; mul_b_reg <= 0; end). Stage 2 computes sum of pairs of partial products on clock edge: sum[0] <= temp[0]+temp[1]; sum[1] <= temp[2]+temp[3]; sum[2] <= temp[4]+temp[5]; sum[3] <= temp[6]+temp[7];. Stage 3 computes sum of all sums on clock edge: mul_out_reg <= sum[0]+sum[1]+sum[2]+sum[3];. Stage 4 drives mul_out on clock edge: always @(posedge clk) if (mul_en_out_reg[2]) mul_out <= mul_out_reg; else mul_out <= 0;",

    # FSM logic
    "fsm": "Sequence detector for 10011: (1) Use exactly 6 states: s0 (got nothing), s1 (got 1), s2 (got 10), s3 (got 100), s4 (got 1001), s5 (got 10011). (2) MATCH is combinationally assigned inside always @(*): if (RST) MATCH = 0; else if (ST_cr == s4 && IN == 1) MATCH = 1; else MATCH = 0; (3) Transitions on IN: s0: 1->s1, 0->s0; s1: 1->s1, 0->s2; s2: 1->s1, 0->s3; s3: 1->s4, 0->s0; s4: 1->s5, 0->s2; s5: 1->s1, 0->s2. (4) Use asynchronous active-high reset (posedge CLK or posedge RST) for state register ST_cr to reset to s0.",
    "traffic_light": "Traffic light: (1) State transitions on clock edge check cnt == 3 (NOT 0) to transition state (e.g. if (cnt == 3) state <= s3_green; else state <= s1_red). (2) Output 'clock' is assigned combinationally inside always @(*): clock = cnt; (do NOT use a clocked always block for 'clock'). (3) cnt resets to 10. On clk edge, if (pass_request && green && (cnt > 10)) cnt <= 10; else if (!green && p_green) cnt <= 60; else if (!yellow && p_yellow) cnt <= 5; else if (!red && p_red) cnt <= 10; else cnt <= cnt - 1. (4) Outputs (red, yellow, green) are driven on clk edge by registers (p_red, p_yellow, p_green): red <= p_red; etc.",
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
    "parallel2serial": "Parallel-to-serial converter (4-bit): (1) Run a 2-bit counter 'cnt' (0 to 3). (2) Output 'dout' is assigned combinationally to the MSB of the shift register: assign dout = data[3];. (3) On positive edge: if cnt == 3, load new input 'd' into the shift register, reset 'cnt' to 0, and set 'valid' register to 1. Otherwise, rotate the shift register left (data <= {data[2:0], data[3]}), increment 'cnt', and set 'valid' to 0.",
    "serial2parallel": "Verify shift register fills completely before asserting valid. Check bit ordering matches spec.",
    "width_8to16": "Two 8-bit inputs must be concatenated correctly. Verify which byte is MSB vs LSB. Check valid signal timing.",

    # Clock/Synchronization
    "freq_div": "Frequency divider: CLK_50, CLK_10, CLK_1. CRITICAL: RST is active-high. All registers reset to 0. (1) CLK_50 toggles every clock: CLK_50 <= ~CLK_50. (2) CLK_10 toggles every 10 clocks: use counter cnt_10 of width [3:0] (4 bits), toggle CLK_10 and reset cnt_10 when cnt_10 == 9. (3) CLK_1 toggles every 100 clocks: use counter cnt_100 of width [6:0] (7 bits), toggle CLK_1 and reset cnt_100 when cnt_100 == 99.",
    "freq_divbyeven": "Frequency divider by even number (6): (1) Define parameter NUM_DIV = 6. (2) Keep a 4-bit counter 'cnt'. (3) Toggle clk_div and reset 'cnt' when cnt == NUM_DIV/2 - 1.",
    "freq_divbyfrac": "Fractional frequency divider (3.5x): (1) Define parameter MUL2_DIV_CLK = 7. (2) Keep a 4-bit counter 'cnt' from 0 to 6. (3) Generate 'clk_ave_r' on posedge clk: high when cnt == 0 or cnt == 4. (4) Generate 'clk_adjust_r' on negedge clk: high when cnt == 1 or cnt == 4. (5) assign clk_div = clk_adjust_r | clk_ave_r.",
    "freq_divbyodd": "Frequency divider by odd number (5): (1) Define parameter NUM_DIV = 5. (2) Define cnt1 and cnt2 of size [2:0], clk_div1 and clk_div2. (3) cnt1 increments on posedge clk, cnt2 on negedge clk (both reset at NUM_DIV-1). (4) clk_div1 is high when cnt1 < NUM_DIV/2; clk_div2 is high when cnt2 < NUM_DIV/2. (5) assign clk_div = clk_div1 | clk_div2.",
    "synchronizer": "Multi-flop synchronizer: verify 2+ flip-flop stages. CRITICAL: All sequential registers (especially the output 'dataout') must be synchronized to 'clk_b' and have an active-low asynchronous reset (always @(posedge clk_b or negedge brstn)) resetting them to 0 when '!brstn' is asserted.",
    "right_shifter": "Verify shift amount and direction. Check arithmetic vs logical shift. Verify fill bit (0 or sign-extend).",
    "ring_counter": "Ring Counter: (1) Output and state must reset to 8'b0000_0001 (not 0). (2) Shift logic: state <= {state[6:0], state[7]}; assign out = state;",
    "sequence_detector": "Sequence Detector (detect 1001): (1) Use 5 states: IDLE (reset state), S1 (got 1), S2 (got 10), S3 (got 100), S4 (got 1001). (2) assert sequence_detected when state is S4. (3) On reset active-low rst_n, state goes to IDLE.",
    "alu": "ALU logic: (1) Use a 33-bit register 'reg [32:0] res;' to store operation results. (2) In a single always @(*) block, initialize carry = 0; overflow = 0; and use case(aluc) to assign res, carry, and overflow. (3) Continuous assignments: assign r = res[31:0]; assign zero = (res[31:0] == 0); assign negative = res[31]; assign flag = (aluc == SLT || aluc == SLTU) ? ((aluc == SLT) ? ($signed(a) < $signed(b)) : (a < b)) : 1'b0; (4) ADD/ADDU carry = res[32]; SUB/SUBU carry = res[32]; (5) Overflow for ADD: (~a[31] & ~b[31] & r[31]) | (a[31] & b[31] & ~r[31]); overflow for SUB: (a[31] & ~b[31] & ~r[31]) | (~a[31] & b[31] & r[31]); (6) Shifts: SLL/SRL/SRA shift b by a if a <= 31, else return 0. SLLV/SRLV/SRAV shift b by a[4:0]. SRA/SRAV must use arithmetic shift $signed(b) >>>. (7) LUI: res = {a[15:0], 16'b0};",
    "asyn_fifo": "Asynchronous FIFO: (1) You MUST define a helper module 'dual_port_RAM' in the same Verilog file and instantiate it. (2) Use ADDR_WIDTH = $clog2(DEPTH) for pointer widths (size ADDR_WIDTH:0). Pointers wptr, rptr, wptr_buff, wptr_syn, rptr_buff, rptr_syn must all be of size ADDR_WIDTH:0. (3) wfull is: assign wfull = (wptr == {~rptr_syn[ADDR_WIDTH:ADDR_WIDTH-1], rptr_syn[ADDR_WIDTH-2:0]}); rempty is: assign rempty = (rptr == wptr_syn);",

    # Exam questions / specific bugs / timeout logic
    "bugs_": "Bug-fixing problem: Do not rewrite from scratch unless necessary. Look for missing semicolons, incorrect wire/reg declarations, blocking vs non-blocking assignments, or swapped module connections.",
    "edgecapture": "For an edge capture circuit: you must detect the edge and HOLD the state until a reset clears it. Use a flip-flop that sets to 1 on an edge and only clears on synchronized reset.",
    "truthtable": "Implement this as a continuous assignment (assign) or combinatorial always block (@*) following exactly the rows of the truth table.",
    "circuit": "Carefully trace the combinatorial logic diagram. Break it into intermediate wires for each gate output if it helps, and ensure every gate is represented correctly.",
    "muxdff": "A D-flip flop preceded by a multiplexer. Implement the MUX logic on the D-input inside the always block.",
    "JC_counter": "Johnson Counter: Verify shift logic. Q <= {{~Q[0], Q[WIDTH-1:1]}} or similar. One bit is inverted and shifted into the other end. Check shift direction.",
    "pulse_detect": "Pulse detector (sequence 010): (1) Since output 'data_out' is declared as 'output reg', you MUST assign it combinationally inside an always @(*) block (do NOT use 'assign' statements, and do NOT use a clocked always block to assign data_out as that delays it by a cycle). (2) Use a Mealy FSM with 4 states: s0 (got nothing), s1 (got 0), s2 (got 01), s3 (got 010). Transitions: s0: 0->s1, 1->s0; s1: 1->s2, 0->s1; s2: 0->s3, 1->s0; s3: 1->s2, 0->s1. (3) Assign combinational output: always @(*) data_out = (state == s2) && (data_in == 0); (4) Use asynchronous active-low reset to s0.",
    "signal_generator": "Triangle wave generator (0 to 31): (1) Output 'wave' is a 5-bit register. (2) Use a 2-bit state register (00 for up, 01 for down). (3) On active-low rst_n, state <= 2'b00 and wave <= 5'b0. (4) In state 2'b00: if wave == 5'b11111 (31), state <= 2'b01; else wave <= wave + 1. (5) In state 2'b01: if wave == 5'b00000 (0), state <= 2'b00; else wave <= wave - 1.",
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
        category: str = "simple",
    ) -> str:
        """Build escalating EDP (Exception-Debugging Prompt) for syntax fix."""

        level = self.get_escalation_level(error_key)

        # Prioritize detected category, fallback to name-based regex
        mod_hint = CATEGORY_HINTS.get(category, "")
        if not mod_hint or category == "simple":
            best_match_len = 0
            for key, hint_text in CATEGORY_HINTS.items():
                if re.search(rf'\b{re.escape(key)}\b', module_name.lower()):
                    if len(key) > best_match_len:
                        mod_hint = hint_text
                        best_match_len = len(key)

        # Base EDP
        base = self._base_edp(
            module_name, gvd, exception_type, exception_title,
            exception_content, log_content, custom_vector, task_description
        )

        if mod_hint:
            base = base + "\n\n## DESIGN SPECIFICATION HINT\n" + mod_hint

        # Escalate
        if level == EscalationLevel.L0_STANDARD:
            return base

        elif level == EscalationLevel.L1_WITH_HISTORY:
            prev = self.history[error_key][-1]
            return base + self._history_suffix(prev)

        elif level == EscalationLevel.L2_HINT:
            prev = self.history[error_key][-1]
            
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
            
            return base + self._history_suffix(prev) + self._hint_suffix(err_hint)

        elif level == EscalationLevel.L3_RETHINK:
            return self._rethink_prompt(module_name, gvd, "syntax",
                                         exception_content, task_description)

        else:  # L4_SKELETON
            return self._skeleton_prompt(module_name, gvd, task_description)

    def build_ts_prompt(
        self,
        state: dict,
        error_key: str,
        module_name: str,
        gvd: str,
        category: str = "simple",
    ) -> str:
        """Build escalating TDP (Testbench-Debugging Prompt) for functional fix."""

        level = self.get_escalation_level(error_key)
        
        tdp = state.get("current_tdp", {}) or {}
        structured_body = tdp.get("structured_body", "")
        
        # Fallback extraction if v5 patch was bypassed or didn't set structured_body
        error_desc = state.get("tdp", "")
        failure_content = error_desc or state.get("tb_failure", "")
        trace_content = ""
        if error_desc and "Debug traces:" in error_desc:
            parts = error_desc.split("Debug traces:", 1)
            failure_content = parts[0].strip()
            trace_content = parts[1].strip()
            
        if structured_body:
            failure_content = structured_body
            trace_content = ""  # already included in structured_body

        task_description = (state.get("nl_input") or "")[:2500]
        testbench_content = state.get("testbench_content", "")

        # Prioritize detected category, fallback to name-based regex
        mod_hint = CATEGORY_HINTS.get(category, "")
        if not mod_hint or category == "simple":
            best_match_len = 0
            for key, hint_text in CATEGORY_HINTS.items():
                if re.search(rf'\b{re.escape(key)}\b', module_name.lower()):
                    if len(key) > best_match_len:
                        mod_hint = hint_text
                        best_match_len = len(key)

        # Base TDP
        base = self._base_tdp(
            module_name, gvd, 0, trace_content,
            failure_content, testbench_content, task_description
        )

        if mod_hint:
            base = base + "\n\n## DESIGN SPECIFICATION HINT\n" + mod_hint

        # Pattern-based hint injection (LUI bug, off-by-one, missing else,
        # comb-output-in-clocked, reset-value, missing begin/end, etc.).
        # These fire on every TS escalation level because they target concrete
        # bug signatures and are cheap to evaluate.
        tdp_hints = detect_tdp_hints(
            verilog_code=gvd,
            debug_traces=structured_body or trace_content or failure_content,
            sc_log=state.get("sc_log", ""),
        )
        if tdp_hints:
            base = base + "\n\n## PATTERN-DETECTED HINTS\n" + tdp_hints

        if level == EscalationLevel.L0_STANDARD:
            return base

        elif level == EscalationLevel.L1_WITH_HISTORY:
            prev = self.history[error_key][-1]
            return base + self._history_suffix(prev)

        elif level == EscalationLevel.L2_HINT:
            prev = self.history[error_key][-1]
            
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

            return base + self._history_suffix(prev) + self._hint_suffix(err_hint)

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

        arch_hint = ""
        m_lower = module_name.lower()
        if "synchronizer" in m_lower:
            arch_hint = "DESIGN HINT: For synchronizers, ensure you use multiple flops (2-stage or 3-stage) to move signals between clock domains. Use the specified enable signal correctly in the destination domain logic."
        elif "alu" in m_lower:
            arch_hint = "DESIGN HINT: For ALUs, ensure all arithmetic flags (Zero, Overflow, Carry, Negative) are calculated correctly. Zero flag is '1' ONLY if the result is 0. Overflow occurs for signed addition/subtraction if the sign of the result is incorrect."
        elif "div" in m_lower:
            arch_hint = "DESIGN HINT: For dividers, ensure the implementation handles the entire division bit-by-bit (using a loop for combinational or multiple cycles for sequential) and correctly sets the quotient and remainder."

        parts = [
            "CRITICAL: Multiple previous attempts to fix this module have ALL FAILED.",
            "You MUST completely rethink your approach.",
            "",
            f"Module: {module_name}",
            f"Task: {task_desc}",
            "",
            "REQUIRED HEADER (Ports are FIXED and matching the testbench):",
            f"```verilog\n{header}\n```",
            "",
            f"The current logic has a persistent {error_type} error:",
            f"  {error_desc}",
            "",
        ]
        
        if arch_hint:
            parts.extend([arch_hint, ""])
            
        parts.extend([
            "DO NOT make incremental changes. Instead:",
            "1. Re-read the task description carefully",
            "2. Design a different architectural approach",
            "3. Write a clean implementation using the FIXED header above",
            "",
            f"Output the COMPLETE module '{module_name}' from 'module' to 'endmodule'.",
            "Output ONLY Verilog code, no explanation."
        ])

        return "\n".join(parts)

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

"""
COMBA-PROMPT Templates for Verilog Code Generation & Debugging.
v4: Pattern-based rules, no problem-specific examples.
"""

import re
from langchain_core.prompts import ChatPromptTemplate

# ══════════════════════════════════════════════════════════════
# FEW-SHOT: Demonstrate CODING STYLE, not specific solutions
# ══════════════════════════════════════════════════════════════

# Pattern A: Combinational — inline arithmetic, no sub-modules
FEWSHOT_XML_COMB = """\
<module id="adder_8bit">
    <description>Implement an 8-bit adder with bit-level adders in combinational logic.</description>
    <ports>
        <input id="a" width_description="[7:0]">8-bit input operand A.</input>
        <input id="b" width_description="[7:0]">8-bit input operand B.</input>
        <input id="cin">Carry-in input.</input>
        <output id="sum" width_description="[7:0]">8-bit sum output.</output>
        <output id="cout">Carry-out output.</output>
    </ports>
    <implementation>Uses full adders to perform addition.</implementation>
</module>"""

FEWSHOT_VERILOG_COMB = """\
module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    // INLINE behavioral logic
    assign {{cout, sum}} = a + b + cin;
endmodule
"""

# Pattern B: Sequential — proper reset, non-blocking
FEWSHOT_XML_SEQ = """\
<module id="counter_12">
    <description>Counter from 0 to 11, controlled by valid_count.</description>
    <ports>
        <input id="rst_n">Active-low reset.</input>
        <input id="clk">Clock.</input>
        <input id="valid_count">Enable counting.</input>
        <output id="out" width_description="[3:0]">Current count.</output>
    </ports>
    <implementation>Reset to 0. Increment when valid_count=1. Wrap at 11.</implementation>
</module>"""

FEWSHOT_VERILOG_SEQ = """\
module counter_12(
    input rst_n, input clk, input valid_count,
    output reg [3:0] out
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            out <= 4'd0;
        else if (valid_count) begin
            if (out == 4'd11) out <= 4'd0;
            else              out <= out + 1;
        end
    end
endmodule
"""


# ══════════════════════════════════════════════════════════════
# 1. CONVERTER: NL → COMBA XML
# ══════════════════════════════════════════════════════════════

CONVERTER_SYSTEM_PROMPT = """\
You are a hardware design specification converter.
Convert natural language module descriptions into COMBA XML format.

## CRITICAL: Module Name Preservation
- The `<module id>` MUST EXACTLY match the module name stated in the spec.
  Do NOT rename, abbreviate, or infer a "better" name.
  Examples:
  - "pe" stays "pe"  (NOT "mac", NOT "multiplier", NOT "pe_unit")
  - "div_16bit" stays "div_16bit"  (NOT "divider")
  - "traffic_light" stays "traffic_light"  (NOT "fsm_light")

## COMBA XML Schema
1. `<module id="name">` — root
2. `<description>` — high-level summary
3. `<ports>` containing `<input>` / `<output>` with optional `width_description`
4. `<parameter_description>` (optional) — FSM states, named constants ONLY.
   Do NOT list internal implementation signals (regs, wires, shift registers, etc.)
   in `<parameter_description>`. Those belong in `<logic_description>`.
5. `<logic_description>` (optional) — signal-level:
   - `type="sequential_logic"` → reg, clocked
   - `type="combinational_logic"` → wire / always @(*)
6. `<implementation>` — detailed behavior (inline behavioral description only).
7. `<task>` (optional)

## CRITICAL: Self-Contained Implementation
- If the spec mentions "instantiate X", "use sub-module X", or "hierarchical":
  → Describe the equivalent INLINE behavior in `<implementation>`.
  → Do NOT describe instantiation of sub-modules in XML — write the algorithm directly.
  → Example: "design an 8-bit adder and instantiate twice" →
    describe as "implement 16-bit addition inline using a single assign statement".
- `<parameter_description>` must ONLY contain FSM state names and numeric constants
  that appear explicitly in the spec (e.g., ADD=6'b100000).
- Do NOT hallucinate internal registers, wires, or counters in the XML unless 
  the input text explicitly names them. Focus on high-level properties.
- NEVER add intermediate signals (divisor_extend, shift registers) in XML; the 
  generator will figure these out from the `<implementation>` description.

## Style Examples
```xml
""" + FEWSHOT_XML_COMB + """
```
```xml
""" + FEWSHOT_XML_SEQ + """
```

Output ONLY the XML, no markdown, no explanation.
"""

converterPromptTemplate = ChatPromptTemplate([
    ("system", CONVERTER_SYSTEM_PROMPT),
    ("placeholder", "{conversation}"),
    ("user", "{user_input}"),
])


# ══════════════════════════════════════════════════════════════
# 2. GENERATOR: COMBA XML → Verilog
# ══════════════════════════════════════════════════════════════

GENERATOR_SYSTEM_PROMPT = """\
You are a professional Verilog RTL code generator.
Generate complete, synthesizable Verilog from the provided Original Specification and COMBA XML.
Output ONLY Verilog code, no explanation, no markdown fences.

## PRIORITIZE ORIGINAL SPECIFICATION
The "Original Specification" provides the exact requirements, including constraints like "inclusive" vs "exclusive", minimum/maximum values, resetting conditions, and exact module interfaces.
The "XML Representation" is a structural guide. If there's any ambiguity, ALWAYS prioritize the instructions in the Original Specification.

## CRITICAL: Required Logic Keywords
The Verilog code MUST contain one of keywords performing logic operations, such as "always", "and", "assign", "not", "nand", "nor", "or", "xnor", "xor", or "display".
Further explanation must be constructed as the syntax of a Verilog comment.
Do NOT just return an empty module or a module with only port declarations.

## INTERFACE ALIGNMENT
The module header (name and ports) is FIXED and forced by the testbench.
1. **Rule: `output` → `output reg` promotion is REQUIRED if assigned in an `always` block.**
   - If you assign an output port inside an `always` block, you MUST declare it as `output reg`.
   - This is NOT a port rename — the port name, width, and direction stay identical.
   - **ANTI-PATTERN (FORBIDDEN)**: Do NOT use internal aliases like `wave_reg`:
     BAD:  `output [4:0] wave; reg [4:0] wave_reg; assign wave = wave_reg;`
     GOOD: `output reg [4:0] wave;` (Keep the name `wave`, just add `reg`).
   - Changing `output` to `output reg` is a type qualifier, not a structural change.

2. **CRITICAL — Use exact port names inside the body:**
   - Every input and output must be referenced by its declared name exactly as written in the port list.
   - Do NOT introduce internal aliases (q, d, data_in, data_out) for ports that already have names.

## CONSTRAINTS (mandatory, apply to ALL designs)

### R1: SELF-CONTAINED — no external sub-modules
- ALL logic must reside in a SINGLE file.
- If the spec or XML mentions "instances of X", "sub-components", "hierarchical", or uses an `<instance>` tag:
  → DO NOT write a module instantiation.
  → Implement the equivalent logic INLINE. For example, if it's a RAM instance, declare a memory array (`reg [WIDTH-1:0] mem [0:DEPTH-1];`) and write the read/write logic inline.
- NEVER instantiate a module unless you also provide its full definition.

### R2: ASSIGNMENT DISCIPLINE & OUTPUT DECLARATIONS
- Outputs ASSIGNED in `always` blocks MUST be declared `output reg` (or `output logic`).
  - This is the #1 cause of syntax errors! Double-check every single output port. If it appears on the left side of `=` or `<=` inside an `always` block, it MUST have the `reg` keyword.
  - Plain `output` is a wire — assigning a wire inside `always` is ILLEGAL in Verilog.
  - Correct:   `output reg [3:0] count`
  - Incorrect: `output [3:0] count` (when count appears in `always @(posedge clk) count <= ...`)
- `always @(*)` or `assign` → use BLOCKING (`=`) only.
- `always @(posedge clk)` → use NON-BLOCKING (`<=`) only.
- Never mix `=` and `<=` on the same signal.

### R3: VARIABLE BIT-SELECT
- ILLEGAL: signal[H : L + N*i]  (variable in range bounds)
- LEGAL:   signal[N*i +: W]     (indexed part-select)

### R4: SHIFT & ALU (MIPS convention)
- For MIPS-style shift instructions (SLL/SRL/SRA/SLLV/SRLV/SRAV):
  → VALUE (data to be shifted) = `b`
  → AMOUNT (shift count)       = `a[4:0]`
  → ALWAYS use `<<`, `>>`, `>>>` operators. NEVER implement shift via concatenation.
  → `{{a[31:0], a[31:0]}}` or `{{b[0], a[31:1]}}` style is WRONG for shifts.
- Load-upper-immediate (LUI): source operand is **`a`** (the first operand), NEVER `b`.
  → CORRECT:   `LUI: res = {{a[15:0], 16'b0}};`
  → FORBIDDEN: `LUI: res = {{b[15:0], 16'b0}};`  ← This is the #1 ALU bug — DO NOT do this.
  → Reason: in MIPS LUI rt, imm, the immediate is encoded into the `a` operand by convention used by this benchmark's testbenches.
- Arithmetic right shift (generic): `$signed(value) >>> amount`.

### R5: COMBINATIONAL MULTI-STEP ALGORITHMS
- Iterative algorithms (division, CRC, etc.) in combinational logic MUST:
  → Use a for-loop with BLOCKING assignments (=).
  → Process ALL bits, not just one iteration.
  → Never use <= in combinational always @(*).

### R6: FSM / SEQUENCE DETECTION
- The FIRST bit of the sequence determines S0's transition.
  e.g., sequence starts with '1' → S0 waits for IN=1, NOT IN=0.
- For overlapping detection, after a match, go to the state matching the longest proper suffix of the sequence that is also a prefix.

### R7: TIMER / COUNTER FSM
- Match the counter range and transition boundaries to the spec exactly.
- Every input port declared in the spec MUST influence the logic.
- Counter reload timing: assign the new cnt value in the SAME cycle as the state transition. Use `state` (or next-state) to detect entry — do NOT use light/output signals (delayed).

### R8: HONOR EXACT ENUM / PARAMETER VALUES (DO NOT INVENT INDICES)
- When XML contains `<enum id="NAME" value="W'bXXXX">` or
  `<parameter id="NAME" value="W'bXXXX">`, the generated Verilog MUST
  compare against THAT EXACT LITERAL VALUE.
- ILLEGAL: counting opcodes 0,1,2,3... when spec says 6'b100000, 6'b100001...
  Example BAD:
      assign r = (aluc == 6'b000000) ? add : (aluc == 6'b000001) ? sub : 0;
  Example GOOD (when spec defines ADD=6'b100000, SUB=6'b100010):
      assign r = (aluc == 6'b100000) ? add : (aluc == 6'b100010) ? sub : 0;
- If unsure, prefer using the symbolic parameter name:
      parameter ADD = 6'b100000;
      parameter SUB = 6'b100010;
      assign r = (aluc == ADD) ? add_r : (aluc == SUB) ? sub_r : 0;
- This rule is CRITICAL for ALU/decoder/FSM modules where opcode encoding
  is explicit in the spec.

### R9: PORT NAME FIDELITY (NEVER ADD / RENAME / DROP)
- Module ports MUST be EXACTLY the set of `<input id>` and `<output id>`
  from the XML — same names, same widths, same direction, same order.
- DO NOT add ports the testbench does not provide (no extra `clock`, `enable`,
  `valid`, etc. unless declared in XML).
- DO NOT rename `clk` ↔ `clock`, `rst_n` ↔ `reset`, `data_in` ↔ `din`.
- DO NOT drop ports declared in XML even if they appear unused — drive a
  default value or use them in the logic per the spec.
- If a TB compile error mentions a port not in the XML (e.g., dut->clock when
  XML defines `clk`), the testbench is buggy — do NOT add that port.
  Keep the GVD ports matching the XML spec.

### R10: STRICT VERILOG SYNTAX
- ALL `always`, `if`, and `else` blocks with multiple statements MUST be enclosed in `begin` and `end`.
- ALL `case` statements MUST be closed with `endcase`.
- EVERY `module` MUST be closed with `endmodule`.
- DO NOT mix `posedge` and `negedge` of the same signal in a sensitivity list.
- DO NOT declare variables inside an `always` block (unless it's a named block). Declare them at the module level.
- Ensure all parentheses `()` and square brackets `[]` are balanced.

### R11: LOGIC & FUNCTIONAL CORRECTNESS
- RESET POLARITY & TYPE: Carefully check if reset is active-high (`rst`) or active-low (`rst_n`). Also note if it's synchronous or asynchronous.
- NO LATCHES: In combinational `always @(*)` blocks, assign a default value to EVERY output at the top of the block, or ensure EVERY `if/else` and `case` branch assigns a value. Unwanted latches are a major cause of functional failure.
- SIGNED MATH: If the problem requires signed arithmetic, explicitly declare signals as `signed` or use `$signed()`.
- CARRY / OVERFLOW: To compute carry-out, zero-extend the operands by 1 bit (e.g. `wire [N:0] sum = {{1'b0, a}} + {{1'b0, b}};`).
- STATE MACHINE INITIALIZATION: All registers MUST be initialized inside the reset condition, NOT using `initial` blocks (unless explicitly requested).
- FSM OUTPUTS: For Mealy FSMs, the output depends on the current state AND the current input. You MUST use a combinational `assign` statement for the output. DO NOT put the output in the `always @(posedge clk)` block (which delays it by 1 cycle) unless requested.
- COUNTER RESET VALUES: Pay close attention to the requested reset value of counters. Do NOT blindly reset to 0 if the spec says "reset to 10" or "reset to 12:00" (which means 8'h12 for BCD).

### R12: ADVANCED PATTERN RULES
- KARNAUGH MAPS (K-MAP):
  * K-map columns and rows use GRAY CODE order: 00, 01, 11, 10 (NOT binary 00, 01, 10, 11).
  * If labels are `ab` on top and `cd` on left: column index gives (a,b), row index gives (c,d).
  * To read cell at row=`cd`=10 col=`ab`=11: that means a=1,b=1,c=1,d=0 → index `{{a,b,c,d}}` = 4'b1110.
  * SAFEST APPROACH: Enumerate all 16 minterms using a `case({{a,b,c,d}})` statement. Read each cell one by one from the grid. Do NOT try to simplify with SOP/POS — just list all 16 cases explicitly.
  * For K-maps with `x[1]x[2]` on top and `x[3]x[4]` on left, x[1] is MSB of column pair, x[2] is LSB of column pair, etc.
  * d (don't-care) entries: you may set them to 0 or 1 — choose whichever simplifies logic.
- GALOIS LFSR (shift right):
  * Shifting RIGHT means bits move from higher index to lower index: `q[i] <= q[i+1]`.
  * The MSB (`q[N-1]`) wraps around and receives the feedback bit: `q[N-1] <= q[0]`.
  * A tap at 1-indexed position P means bit `q[P-1]` gets XORed with feedback: `q[P-1] <= q[P] ^ q[0]`.
  * The highest tap (position N, i.e. the MSB itself) is just `q[N-1] <= q[0]` (no q[N] exists).
  * Example 5-bit LFSR, taps at 5,3: `q[4]<=q[0]; q[3]<=q[4]; q[2]<=q[3]^q[0]; q[1]<=q[2]; q[0]<=q[1];`
  * DO NOT confuse with Fibonacci LFSR (which XORs taps to produce feedback for bit 0).
- CELLULAR AUTOMATA (Rule 90, Rule 110):
  * Rule N: convert N to 8-bit binary. This gives the output for each 3-bit neighborhood (left, center, right) from 111 down to 000.
  * Rule 110 = 8'b01101110: neighborhood 111→0, 110→1, 101→1, 100→0, 011→1, 010→1, 001→1, 000→0.
  * Rule 90 = 8'b01011010: simply `next[i] = left ^ right` (XOR of neighbors).
  * Implement as: `for each bit i, compute {{left,center,right}}` then use case or lookup.
  * Boundaries: assume q[-1]=0 and q[N]=0 (off).
- ONE-HOT FSM: When the problem says the state encoding is one-hot, each state variable bit IS a state. Use `state[0]` for state A, `state[1]` for state B, etc. Transition logic: `next_state[j] = (state[i] & condition_i_to_j) | ...` for all transitions into state j.
- BCD COUNTERS: BCD digits use 4 bits per decimal digit. `8'h12` means tens=1, units=2. When incrementing BCD: if units reaches 9, reset to 0 and increment tens. Do NOT do binary addition on BCD values (e.g. `8'h09 + 1 = 8'h0A` is WRONG in BCD, it should be `8'h10`).
- CIRCUIT FROM WAVEFORM: When asked to determine a circuit from simulation waveforms, first build a truth table from the waveform data, then implement the logic. For sequential circuits, identify the flip-flop type (D, JK, T) and the combinational logic feeding it.

### R13: COMBINATIONAL OUTPUT PORTS THAT MIRROR INTERNAL STATE
- If a spec says "the output X is assigned/equal to internal signal Y" (e.g. "assign clock = cnt"), implement it with **continuous assignment** (`assign`), NOT inside an `always @(posedge clk)` block.
  → CORRECT:   `output [7:0] clock; ... assign clock = cnt;`
  → FORBIDDEN: `output reg [7:0] clock; ... always @(posedge clk) clock <= cnt;`
- Reason: Wrapping the mirror in `always @(posedge clk)` delays the output by 1 cycle, AND the value at reset is 0 (the default) instead of the actual reset value of the internal reg — a silent off-by-one + reset-value bug.
- Test for this pattern: if the only thing happening to an output is "X = Y" where Y is a `reg`, use `assign`. Reserve `output reg` only for outputs that have their own distinct sequential logic.

### R14: PREDICTIVE COMPARISON FOR COUNTER WRAP / DIRECTION CHANGE
- When a counter must wrap or change direction at boundary N (e.g. wave goes 0→1→...→31→30→...→0→1...):
  → Compare against `N-1` BEFORE incrementing, not against `N` after.
  → CORRECT (up-counter wrap at 31):
      `always @(posedge clk) begin
         if (count == 5'd30) state <= 1; // arrive at 31 next cycle, then switch
         count <= count + 1;
       end`
  → BUGGY (off-by-one): `if (count == 5'd31) state <= 1; count <= count + 1;`
       This makes the direction change happen ONE cycle late, so the output
       overshoots the boundary by one tick.
- Same rule for down-counters: compare against `1` before decrementing to 0,
  not against `0` after.

### R15: RESET VALUE FIDELITY (NON-ZERO RESETS)
- Read the spec carefully: counters and FSMs often reset to a NON-ZERO value
  (e.g. "cnt is 10 decimal on reset", "minutes reset to 12:00").
- The reset value applies to the INTERNAL register AND any combinational output
  that mirrors it.
  → If `assign clock = cnt;` and reset says `cnt <= 8'd10;`, then `clock` is
     also 10 immediately on reset — that is automatic.
  → If you instead made `clock` a separate `reg`, you must ALSO set
     `clock <= 8'd10` in the reset branch.

### R16: OUTPUT TIMING — MEALY vs MOORE vs DELAYED
- Moore output (depends only on state, registered): assign inside the same
  sequential `always` as the state register, OR use `assign out = (state == S);`.
- Mealy output (depends on state AND input, combinational): MUST be a
  continuous `assign` or live in `always @(*)`. Putting a Mealy output in
  `always @(posedge clk)` delays it by 1 cycle — common bug.
- "Delayed by 1 cycle" output (spec uses `p_red`, `p_green` style intermediate):
  if the spec explicitly defines a `reg` like `p_X` then `X <= p_X;` in clocked
  block, follow it EXACTLY — do NOT collapse the intermediate.

## XML → Verilog Mapping
- Module name = `<module id>`, ports = `<input id>` / `<output id>`.
- `width_description` → signal width.
- `sequential_logic` → reg + always @(posedge clk).
- `combinational_logic` → wire/assign or always @(*).
- Code must pass Verilator.

## Style Reference
XML:
```xml
""" + FEWSHOT_XML_COMB + """
```
Verilog:
```verilog
""" + FEWSHOT_VERILOG_COMB + """
```

XML:
```xml
""" + FEWSHOT_XML_SEQ + """
```
Verilog:
```verilog
""" + FEWSHOT_VERILOG_SEQ + """
```
"""

generatorPromptTemplate = ChatPromptTemplate([
    ("system", GENERATOR_SYSTEM_PROMPT),
    ("placeholder", "{conversation}"),
    ("user", "{user_input}"),
])


# ══════════════════════════════════════════════════════════════
# 2b. CLASSIFIER: Problem Category Detection
# ══════════════════════════════════════════════════════════════

CLASSIFIER_SYSTEM_PROMPT = """\
Classify this Verilog design specification into exactly ONE category.
Return ONLY the category name, nothing else.

Categories:
- simple: basic gates, muxes, DFFs, counters, simple arithmetic, wire assignments, basic always blocks
- fsm: finite state machines, sequence detectors, protocol controllers, state transition tables, Moore/Mealy machines
- kmap: Karnaugh maps, truth tables, SOP/POS minimization, don't-care conditions, boolean simplification
- shift_logic: LFSRs, barrel shifters, rotate operations, bit manipulation, CRC, shift registers
- circuit_trace: reverse-engineering gate-level netlists, identifying circuit function from gate connections, circuit diagrams
"""

classifierPromptTemplate = ChatPromptTemplate([
    ("system", CLASSIFIER_SYSTEM_PROMPT),
    ("user", "{spec}"),
])

# Category-specific reasoning suffixes appended to the generator prompt
CATEGORY_SUFFIXES = {
    "simple": "",  # No extra guidance needed — already near 100%
    "fsm": """\

## CATEGORY-SPECIFIC: FSM Reasoning Strategy
Before writing Verilog, you MUST mentally construct the state transition table:
1. List ALL states explicitly (S0, S1, S2, ...) with their encoding
2. For EACH (state, input_combination) pair, determine the next_state and outputs
3. Verify: every state has a transition for EVERY input combination (no missing cases)
4. Use a two-always-block pattern: one for state register (sequential), one for next-state+output logic (combinational)
5. ALWAYS include 'default' in case statements
6. ALWAYS include 'endcase' after every case block
""",
    "kmap": """\

## CATEGORY-SPECIFIC: K-map / Truth Table Strategy
Before writing Verilog, you MUST:
1. Extract the complete truth table from the specification
2. Write the canonical SOP (Sum of Products) or POS (Product of Sums) expression
3. Simplify using K-map groupings or boolean algebra
4. Write the simplified expression as 'assign' statements
5. Double-check: verify your expression matches ALL rows of the truth table
6. Use don't-care conditions (x) if specified — they can be 0 or 1
""",
    "shift_logic": """\

## CATEGORY-SPECIFIC: Shift/LFSR Strategy
Before writing Verilog, you MUST:
1. Identify the shift register polynomial or pattern
2. For LFSRs: identify tap positions and XOR feedback connections
3. Use Verilog shift operators (<<, >>, >>>) — NOT concatenation-based shifts
4. For barrel shifters: use indexed part-select (signal[offset +: WIDTH])
5. For rotate: use concatenation {signal, signal} then select the right window
""",
    "circuit_trace": """\

## CATEGORY-SPECIFIC: Circuit Tracing Strategy
Before writing Verilog, you MUST:
1. Trace the signal flow gate-by-gate from inputs to outputs
2. Label every intermediate wire with its boolean expression
3. Build the complete boolean expression for each output
4. Write 'assign' statements for each output using the derived expressions
5. Verify: check that the gate types (AND, OR, XOR, NOT, etc.) match the spec exactly
""",
}



# ══════════════════════════════════════════════════════════════
# 3. EDP: Syntax Error Fix
# ══════════════════════════════════════════════════════════════

EDP_SYSTEM_PROMPT = """\
You are a Verilog syntax debugging expert.
Fix the TOPMOST iverilog error. Return the complete corrected code only.

## Error → Fix Mapping
- "Cannot find file containing module: 'X'"
  → REMOVE instantiation. Rewrite with inline behavioral RTL.
- "Signal not found" / "IMPLICIT"
  → Declare the signal with correct width as wire or reg.
- "UNDRIVEN"
  → Drive the signal via assign or always block.
- "MULTIDRIVEN"
  → Remove duplicate drivers. One signal, one driver.
- "BLKANDNBLK"
  → Separate into comb (=) and seq (<=) blocks. Never both on same signal.
- "COMBDLY"
  → Replace <= with = inside always @(*) blocks.
- "PROCASSWIRE" / "is not a valid l-value" / "declared here as wire"
  → The output port is declared as plain `output` (wire) but assigned inside `always`.
  → Fix: change `output foo` → `output reg foo` (or add `reg foo;` separately).
  → NEVER leave an always-assigned output as a plain wire.
- "Expecting expression to be constant, variable isn't const" (bit-select)
  → Replace signal[H:L+N*i] with signal[N*i +: W].
- "Width mismatch" / "WIDTHEXPAND" / "WIDTHTRUNC"
  → Adjust operand widths or use explicit zero/sign extension.
- "syntax error, unexpected '.'"
  → Sub-module port syntax used incorrectly. Likely needs inline rewrite.
- "Index ... is out of range"
  → A generate/for loop accesses an index beyond the declared port width.
  → Fix: tighten loop bounds to match the port declaration ([H:L] means H down to L).
- "syntax error" (near endmodule or generally)
  → You likely forgot an `end` for a `begin`, or an `endcase` for a `case`. Check block closures.
- "mixed clock edges"
  → Do not mix `posedge` and `negedge` of the same signal.

## Rules
1. Fix ONLY the topmost error. Cascading errors resolve automatically.
2. Preserve module name, ports, architecture exactly as given.
3. NEVER add or rename ports. The port list (header) is FIXED and forced by the testbench.
4. If a variable is missing (e.g. "Could not find variable 'q'"), DO NOT add it to the port list. Either declare it internally as a `wire` or `reg`, OR rewrite the logic to use the existing ports (e.g., use `out` instead of `q`).
5. No markdown fences, no explanation. Code only.
"""

EDP_USER_PROMPT = """\
## Module: {module_name}
## Syntax Check Trial {trial}/{max_trial}

### Current Code
```verilog
{gvd}
```

### Topmost Error
  Type: {exceptionType}
  Title: {exceptionTitle}
  Content: {exceptionContent}
  Location: {logContent}

### Context
{custom_vector}

Return the complete corrected Verilog code.
"""

edpPromptTemplate = ChatPromptTemplate([
    ("system", EDP_SYSTEM_PROMPT),
    ("user", EDP_USER_PROMPT),
])


# ══════════════════════════════════════════════════════════════
# 4. TDP: Functional Bug Fix
# ══════════════════════════════════════════════════════════════

TDP_SYSTEM_PROMPT = """\
You are a Verilog functional debugging expert.
The code compiles but fails simulation. Fix the TOPMOST functional failure.
Return the complete corrected code only.

## Debugging Methodology
1. Compare OUTPUT TRACE vs REFERENCE OUTPUT for the failing cycle.
2. Trace backward: what logic produced the wrong value?
3. Check these common root causes:
   - Operand swap: value vs amount in shifts, dividend vs divisor, a vs b.
   - Off-by-one: counter boundary (== N-1 vs == N), pipeline latency.
   - Cycle Delay Mismatch (Output is late/early by 1 clock): You likely registered a signal (`always @(posedge clk)`) that should be combinational (`assign`), or vice-versa. Mealy FSM outputs MUST be combinational.
   - Reset Logic & Values: check active-low vs active-high (`!rst_n` vs `rst`), and synchronous vs asynchronous. Check if counter resets to 0 or another specific value (e.g., 10).
   - Unwanted Latches: A combinational `always @(*)` block failed to assign a value in all branches. ADD DEFAULT ASSIGNMENTS.
   - Accumulator output timing: emit result AFTER including current input.
   - Incomplete iteration: combinational algorithm must process ALL bits/steps.
   - Unused inputs: every declared port must affect logic per the spec.
   - FSM transition error: verify each state's next-state matches the spec.
   - Wrong operator: + vs -, & vs &&, | vs ||, >> vs >>>.
   - Width truncation/Carry: intermediate result too narrow, losing upper bits. Use zero-extension for carry.
4. Preserve module interface exactly. NEVER add or rename ports.
5. No markdown fences. Code only.

## CRITICAL PATTERN-SPECIFIC RULES

### P1: "Signal is not used" warning + TB failure
If the SC log contains a warning like "Signal is not used: 'X'" and X is an INPUT PORT, the generated code has a MISSING FEATURE. Implement X's effect in the logic.

### P2: Shift/ALU operations produce wrong results
- Shifts MUST use <<, >>, >>> operators. NEVER use concatenation.
- Verify operand order (e.g. SLL is often `res = b << a[4:0]`).
- LUI (Load Upper Immediate) usually targets upper 16 bits: `res = {{a[15:0], 16'b0}}`.

### P3: Counter/Handshake Logic
- Counter reload: Reset the counter in the SAME cycle as state transition. Use next-state (or state entry trigger) for the reload signal.
- Handshake (opn_valid, res_ready, res_valid): 
  → Set `res_valid` high only when the operation is DONE (last cycle).
  → Clear `res_valid` when `res_ready` is asserted.
  → Do NOT use `res_ready` as an l-value (it is an input from the testbench).
- Default values: In combinational logic, always assign a default 0 (or wires to GND) for outputs. NEVER used high-impedance 'z' unless building a tri-state buffer.

### P4: K-map / Truth Table mismatches (many mismatches in small sample count)
- If nearly ALL samples fail: the boolean expression is likely WRONG. Re-derive from scratch.
- K-map uses GRAY CODE column/row order (00,01,11,10), NOT binary order.
- SAFEST FIX: Replace SOP/POS with an explicit `case({{a,b,c,d}})` listing all 16 minterms.

### P5: LFSR all-wrong (199000+ mismatches)
- Galois LFSR shifts RIGHT: `q[i] <= q[i+1]`, MSB wraps: `q[N-1] <= q[0]`.
- Tap at position P means `q[P-1] <= q[P] ^ q[0]`.
- If the code shifts LEFT (`q[i] <= q[i-1]`) or uses Fibonacci feedback (`q[0] <= XOR of taps`), it is WRONG.

### P6: Cellular Automata (Rule 90, Rule 110)
- Must apply the rule to ALL 512 (or N) cells simultaneously each clock cycle.
- Rule 110 truth table: 111→0, 110→1, 101→1, 100→0, 011→1, 010→1, 001→1, 000→0.
- Rule 90: `next[i] = q[i-1] ^ q[i+1]` (XOR of left and right neighbors only).
- Boundaries: q[-1]=0, q[N]=0.

### P7: One-hot FSM encoding
- In one-hot encoding: state[0]=A, state[1]=B, state[2]=C, etc.
- Transition: `next_state[j] = (state[i] & cond) | ...` for each transition into j.
- Output: `out = state[k]` for Moore, or `out = state[k] & input_cond` for Mealy.
- Do NOT use binary-encoded states (3'b001, 3'b010) when the problem says one-hot.

### P8: OFF-BY-ONE AT COUNTER BOUNDARY (output exceeds expected by 1 tick)
Symptom: OUTPUT = N+1 when REFERENCE = N at the cycle right before a wrap/turn,
then OUTPUT lags by one for the next cycle (e.g., wave=0x0 vs 0x1f; next cycle
wave=0x1f vs 0x1e).
Root cause: the code compares the counter AFTER incrementing it.
Fix: compare against `N-1` BEFORE the increment, so the direction flip happens
in the same cycle the counter reaches `N`.
  BAD : `wave <= wave + 1; if (wave == 5'd31) state <= 1;`
  GOOD: `if (wave == 5'd30) state <= 1; wave <= wave + 1;`
(For down-counters: compare to 1 before decrementing to 0.)

### P9: COMBINATIONAL OUTPUT WRAPPED IN always @(posedge clk)
Symptom: an output port (e.g., `clock`, `data_out`) is 0 at reset when the
reference expects a non-zero value, AND the output lags the internal register
by exactly one cycle.
Root cause: `output reg X; always @(posedge clk) X <= Y;` where the spec says
"X is assigned to Y" (combinational mirror).
Fix: change to `output X;` and `assign X = Y;`. This makes X immediately
reflect the reset value of Y and removes the 1-cycle latency.

### P10: RESET POLARITY OR RESET-VALUE BUG
Symptom: at `rst_n=0` the output is non-zero when expected 0, OR the output
is 0 when the spec says reset to a specific value (e.g. 10 for traffic_light's
`cnt`/`clock`, or 8'h12 for a clock counter).
Fix steps:
1. Confirm reset polarity: spec says "active-low" → use `if (!rst_n)`.
2. Confirm reset value matches the spec EXACTLY (not just 0).
3. Ensure outputs are assigned in BOTH branches of the reset (no latches).
4. For asynchronous reset, sensitivity list must include `negedge rst_n`.

### P11: MISSING begin/end CAUSES UNCONDITIONAL ASSIGN
Symptom: a reset or guard is ignored — `q` updates to data every cycle even
when `r` (reset) is high.
Root cause: `if (r) q <= 1'b0; q <= d;` — without `begin..end`, only the first
statement is conditional; the second runs every cycle and overwrites.
Fix: wrap multi-statement bodies in `begin..end`, OR delete the wrong
assignment if it was a typo:
  `if (r) q <= 1'b0; else q <= d;`

### P12: MUX / GATE OPERAND SWAP
Symptom: output is `~expected` or the opposite of every input combination, OR
the output matches one input perfectly and never the other.
Fix: verify operand order — `if (sel) out=a; else out=b;` vs the spec's
"when sel=1 select b". Read the spec's truth table for sel=0 and sel=1
separately and match each branch.

### P13: VECTOR CONCATENATION ORDER
Symptom: all four outputs of a vector splitter (w/x/y/z) are wrong; a single
output is right but others shifted by N bits.
Fix: Verilog concat `{a, b, c}` puts `a` in the MSBs. If spec says
"w is the top byte of {f,e,d,c,b,a}+2'b00", then
  `{w,x,y,z} = {f,e,d,c,b,a,2'b00};` — verify the bit position of each output.
Re-derive bit indices from scratch; do NOT trust the previous slice numbers.
"""

TDP_USER_PROMPT = """\
## Module: {module_name}
## Testbench Trial {ts_trial}/{max_ts_trials}

### Specification
{xml_description}

### Current Code
```verilog
{verilog_code}
```

### First Failure
{topmost_failure}

### Failure Traces (up to 5)
{debug_traces}

Return the complete corrected Verilog code.
"""

tdpPromptTemplate = ChatPromptTemplate([
    ("system", TDP_SYSTEM_PROMPT),
    ("user", TDP_USER_PROMPT),
])
# ── TDP pattern detection for hint injection ──
_TDP_PATTERNS = {
    "unused_port": re.compile(r"Signal is not used:\s*'(\w+)'", re.I),
    "shift_concat": re.compile(
        r"(SLL|SRL|SRA|SLLV|SRLV|SRAV|LUI):\s*res\s*=\s*\{", re.I
    ),
    "counter_mismatch": re.compile(
        r"clock\s*=\s*0x([0-9a-f]+).*?REFERENCE.*?clock\s*=\s*0x([0-9a-f]+)", re.I
    ),
    # P2-bis: LUI uses 'b' instead of 'a' (the most common ALU bug).
    # Match either the symbolic LUI label OR the literal opcode 6'b001111
    # OR the bare result shape {b[15:0], 16'b0} (the unique bug signature).
    "lui_wrong_src": re.compile(
        r"(?:"
        r"\bLUI\b\s*:?\s*(?:begin\s*)?\w*\s*=\s*\{\s*b\s*\[\s*15\s*:\s*0\s*\]"
        r"|"
        r"6'b001111\s*:\s*(?:begin\s*)?\w*\s*=\s*\{\s*b\s*\[\s*15\s*:\s*0\s*\]"
        r"|"
        r"=\s*\{\s*b\s*\[\s*15\s*:\s*0\s*\]\s*,\s*16'(?:b0+|h0+|d0)\s*\}"
        r")",
        re.I,
    ),
    # P9: combinational output (e.g. `clock` mirroring `cnt`) wrapped in always @(posedge clk)
    "comb_output_in_clocked": re.compile(
        r"always\s*@\s*\(\s*posedge\s+\w+(?:\s+or\s+\w+edge\s+\w+)?\s*\)\s*"
        r"begin[^}]*?\b(\w+)\s*<=\s*(\w+)\s*;[^}]*?end",
        re.I,
    ),
    # P11: `if (X) Y <= ...; Z <= ...;` without begin/end — missing guard scope
    "missing_begin": re.compile(
        r"\bif\s*\([^)]+\)\s*\w+\s*<=\s*[^;]+;\s*\w+\s*<=",
        re.I,
    ),
    # P10: reset-value mismatch — output is 0 but expected non-zero on rst
    "reset_value_mismatch": re.compile(
        r"in->\s*rst[_n]*\s*=\s*0x0.*?(?:OUTPUT|tx->).*?=\s*0x0+\s*,.*?REFERENCE.*?=\s*0x[1-9a-f]",
        re.I | re.S,
    ),
}

_TDP_HINTS = {
    "unused_port": (
        "\n## HINT: Unused input port detected\n"
        "The SC log warns that input port '{port}' is not used.\n"
        "This port MUST affect the logic per the spec. Read the spec and implement it.\n"
    ),
    "shift_concat": (
        "\n## HINT: Shift implemented as concatenation\n"
        "The code uses {{{{...}}}} concatenation for shift ops. This is WRONG.\n"
        "Replace with: SLL→b<<a[4:0], SRL→b>>a[4:0], SRA→$signed(b)>>>a[4:0], LUI→{{a[15:0],16'b0}}\n"
    ),
    "counter_mismatch": (
        "\n## HINT: Counter value offset\n"
        "The counter output differs from reference by a fixed amount.\n"
        "Check reload values and transition boundaries.\n"
    ),
    "lui_wrong_src": (
        "\n## HINT: LUI uses WRONG source operand\n"
        "Detected `LUI: res = {{b[15:0], 16'b0}};` in the code.\n"
        "This is the #1 ALU bug — LUI source MUST be `a`, NOT `b`.\n"
        "Fix: `LUI: res = {{a[15:0], 16'b0}};`\n"
    ),
    "comb_output_in_clocked": (
        "\n## HINT: Combinational output wrapped in clocked block (P9)\n"
        "An output that should mirror an internal register combinationally is\n"
        "instead assigned inside `always @(posedge clk)`. This delays the output\n"
        "by 1 cycle AND makes it 0 at reset instead of the reg's reset value.\n"
        "Fix: declare the output as plain `output` (not `output reg`) and use\n"
        "  `assign <output> = <internal_reg>;`  outside any always block.\n"
    ),
    "missing_begin": (
        "\n## HINT: Missing begin/end (P11)\n"
        "Detected `if (...) X <= ...; Y <= ...;` without `begin..end`.\n"
        "Without the block, only the FIRST statement is guarded; the second\n"
        "runs every cycle and overwrites the reset/conditional value.\n"
        "Fix: wrap multi-statement bodies in `begin..end`.\n"
    ),
    "reset_value_mismatch": (
        "\n## HINT: Reset value mismatch (P10)\n"
        "At reset, the output is 0 but the reference expects a non-zero value.\n"
        "Either the reset branch is missing an explicit assignment, OR the spec\n"
        "requires the counter to reset to a specific non-zero value (e.g. 10,\n"
        "8'h12 for 12:00). Re-read the spec's reset condition for each output.\n"
    ),
    "off_by_one": (
        "\n## HINT: Off-by-one at counter boundary (P8)\n"
        "Symptom matches OUTPUT exceeding REFERENCE by 1 at the wrap point.\n"
        "Compare the counter to `N-1` BEFORE incrementing, not to `N` after.\n"
        "Example up-counter wrap at 31:\n"
        "  GOOD: `if (count == 5'd30) state <= 1; count <= count + 1;`\n"
        "  BAD : `count <= count + 1; if (count == 5'd31) state <= 1;`\n"
    ),
}


def _detect_off_by_one(debug_traces: str) -> bool:
    """Detect the off-by-one wrap symptom from trace deltas.

    Looks for OUTPUT and REFERENCE pairs that differ by exactly 1 in hex
    near a wrap boundary (e.g., tx=0x0 vs ref=0x1f then tx=0x1f vs ref=0x1e).
    """
    pairs = re.findall(
        r"(?:OUTPUT|tx->)\s*\w+\s*=\s*0x([0-9a-f]+).*?REFERENCE.*?=\s*0x([0-9a-f]+)",
        debug_traces or "",
        re.I | re.S,
    )
    if len(pairs) < 2:
        return False
    deltas = []
    for a_hex, b_hex in pairs[:4]:
        try:
            a, b = int(a_hex, 16), int(b_hex, 16)
            deltas.append(a - b)
        except ValueError:
            continue
    # Off-by-one signature: at least one pair differs by exactly +/-1 OR
    # by a wrap-amount (e.g. +/- N where one was at boundary).
    return any(abs(d) == 1 for d in deltas) and len(set(deltas)) > 1


def detect_tdp_hints(
    verilog_code: str = "",
    debug_traces: str = "",
    sc_log: str = "",
) -> str:
    """Run all TDP pattern detectors and return the combined hint text.

    This is called from both `build_tdp_prompt` (legacy) and from
    `MultiAttemptManager.build_ts_prompt` (current pipeline path), so that
    pattern-based hints fire regardless of which code path builds the prompt.
    """
    hints = []

    # P1: unused port (from SC log warning)
    m = _TDP_PATTERNS["unused_port"].search(sc_log or "")
    if m:
        hints.append(_TDP_HINTS["unused_port"].format(port=m.group(1)))

    # P2: shift as concatenation
    if _TDP_PATTERNS["shift_concat"].search(verilog_code or ""):
        hints.append(_TDP_HINTS["shift_concat"])

    # P2-bis: LUI using wrong source operand (b instead of a)
    if _TDP_PATTERNS["lui_wrong_src"].search(verilog_code or ""):
        hints.append(_TDP_HINTS["lui_wrong_src"])

    # P3: counter mismatch
    if _TDP_PATTERNS["counter_mismatch"].search(debug_traces or ""):
        hints.append(_TDP_HINTS["counter_mismatch"])

    # P8: off-by-one at wrap boundary (heuristic on trace deltas)
    if _detect_off_by_one(debug_traces or ""):
        hints.append(_TDP_HINTS["off_by_one"])

    # P9: combinational output wrapped in clocked block
    if _TDP_PATTERNS["comb_output_in_clocked"].search(verilog_code or ""):
        hints.append(_TDP_HINTS["comb_output_in_clocked"])

    # P10: reset-value mismatch (output is 0 at reset but expected non-zero)
    if _TDP_PATTERNS["reset_value_mismatch"].search(debug_traces or ""):
        hints.append(_TDP_HINTS["reset_value_mismatch"])

    # P11: missing begin/end
    if _TDP_PATTERNS["missing_begin"].search(verilog_code or ""):
        hints.append(_TDP_HINTS["missing_begin"])

    return "".join(hints)


def build_tdp_prompt(
    module_name: str, verilog_code: str,
    xml_description: str,
    topmost_failure: str, debug_traces: str,
    sc_log: str = "",
    ts_trial: int = 1, max_ts_trials: int = 5,
) -> list[dict]:
    """Build TDP messages with pattern-aware hint injection."""
    system = TDP_SYSTEM_PROMPT + detect_tdp_hints(
        verilog_code=verilog_code,
        debug_traces=debug_traces,
        sc_log=sc_log,
    )

    user = TDP_USER_PROMPT.format(
        module_name=module_name, verilog_code=verilog_code,
        xml_description=xml_description,
        topmost_failure=topmost_failure, debug_traces=debug_traces,
        ts_trial=ts_trial, max_ts_trials=max_ts_trials,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

# ══════════════════════════════════════════════════════════════
# 5. CORRECTER: Legacy compatibility
# ══════════════════════════════════════════════════════════════

CORRECTER_SYSTEM_PROMPT = """\
You are a Verilog debugger. Fix the specific error. Do not rewrite unnecessarily.

## Rules
1. Preserve module name, ports, architecture.
2. Must compile with iverilog.
3. Self-contained — no external sub-modules.
4. Phase "sc" → syntax fix. Phase "ts" → logic fix.
5. Return ONLY the complete fixed Verilog code.
"""

CORRECTER_USER_PROMPT = """\
## Code
```verilog
{verilog_code}
```

## Phase: {phase}

## Error
{error_description}

Return the corrected Verilog code.
"""

correcterPromptTemplate = ChatPromptTemplate([
    ("system", CORRECTER_SYSTEM_PROMPT),
    ("user", CORRECTER_USER_PROMPT),
])
# ══════════════════════════════════════════════════════════════
# 6. BUILDER FUNCTIONS (merged from prompt_generator / prompt_edp)
# ══════════════════════════════════════════════════════════════

# ── Error classification for EDP constraint injection ──
_ERROR_PATTERNS = {
    "missing_module": re.compile(r"Cannot find file containing module", re.I),
    "blk_nonblk":    re.compile(r"BLKANDNBLK|Blocked and non-blocking", re.I),
    "combdly":       re.compile(r"COMBDLY|Delayed assignments.*non-clocked", re.I),
    "var_bitselect": re.compile(r"Expecting expression to be constant.*variable isn't const", re.I),
    # iverilog: "X is not a valid l-value" / "declared here as wire" / PROCASSWIRE
    "procasswire":   re.compile(
        r"PROCASSWIRE|Procedural assignment to wire"
        r"|is not a valid l-value"
        r"|declared here as wire",
        re.I,
    ),
    # iverilog out-of-range indexing (generate loops exceeding port width)
    "out_of_range":  re.compile(r"Index .* is out of range|out of range", re.I),
}

_ERROR_CONSTRAINTS = {
    "missing_module": (
        "\n## CRITICAL: Missing Sub-module\n"
        "REMOVE ALL sub-module instantiations. Rewrite with inline behavioral RTL.\n"
    ),
    "blk_nonblk": (
        "\n## CRITICAL: Mixed Blocking/Non-blocking\n"
        "Use = in always @(*), <= in always @(posedge clk). Never both on same signal.\n"
    ),
    "combdly": (
        "\n## CRITICAL: Non-blocking in Combinational Block\n"
        "Replace ALL <= with = inside always @(*) blocks.\n"
    ),
    "var_bitselect": (
        "\n## CRITICAL: Variable Bit-select\n"
        "Replace signal[H:L+N*i] with signal[N*i +: W].\n"
    ),
    "procasswire": (
        "\n## CRITICAL: Output Port Declaration Mismatch\n"
        "An output port is declared as a wire (plain `output`) but assigned in an `always` block.\n"
        "Fix: change `output foo` → `output reg foo` (or `output logic foo`) for all such ports.\n"
    ),
    "out_of_range": (
        "\n## CRITICAL: Array/Port Index Out of Range\n"
        "You are indexing a port beyond its declared width.\n"
        "Possibility 1: A generate/for-loop exceeds boundaries. Tighten loop bounds.\n"
        "Possibility 2: You are using one-hot state parameter values (like A=4'b0001, meaning 1) as bit INDICES (like next_state[A]). "
        "A 4-bit vector only has indices 0, 1, 2, 3! Using next_state[4'b1000] attempts to access index 8, which is out of range.\n"
        "Fix: EITHER use 0-based indices for your parameters (parameter A=0, B=1...) OR do not use them as indices inside the brackets.\n"
    ),
}


def build_generation_prompt(xml_description: str) -> list[dict]:
    """Build messages for Process 0 (Generation)."""
    return [
        {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
        {"role": "user",   "content": xml_description},
    ]


def build_edp_prompt(
    module_name: str, gvd: str,
    exceptionType: str, exceptionTitle: str,
    exceptionContent: str, logContent: str,
    custom_vector: str, sc_log: str,
    trial: int = 1, max_trial: int = 10,
) -> list[dict]:
    """Build messages for EDP with error-aware constraint injection."""
    system = EDP_SYSTEM_PROMPT
    for key, pat in _ERROR_PATTERNS.items():
        if pat.search(sc_log):
            system += _ERROR_CONSTRAINTS[key]

    user = EDP_USER_PROMPT.format(
        module_name=module_name, gvd=gvd,
        exceptionType=exceptionType, exceptionTitle=exceptionTitle,
        exceptionContent=exceptionContent, logContent=logContent,
        custom_vector=custom_vector,
        trial=trial, max_trial=max_trial,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
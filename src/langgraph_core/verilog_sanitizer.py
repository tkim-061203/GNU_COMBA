"""
verilog_sanitizer.py — Single Lightweight Node
=================================================
REPLACES: extraction_guard.py + pre_sc_check.py (2 nodes → 1 node)

Design principle: NEVER BLOCK code from reaching Verilator.
  - Extract code from LLM noise → ALWAYS pass through
  - Structural checks → WARNING only, attached to state
  - Auto-fix trivial issues (missing endmodule)
  - Max 2 extraction retries, then pass raw to Verilator

Only 2 hard failures (retry up to max_retries):
  1. LLM returned empty/no text
  2. No 'module' keyword found anywhere

Everything else → extract best-effort, warn, pass to Verilator.

Usage:
    from verilog_sanitizer import sanitize
    result = sanitize(llm_raw_output, module_name="alu")
    # result.code is ALWAYS set (unless result.needs_retry and retries < max)
    # result.warnings has structural hints for debugging
    # result.needs_retry is True only for hard failures (empty/no module)
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────

@dataclass
class SanitizeResult:
    code: Optional[str]                     # Extracted code (None only if needs_retry)
    needs_retry: bool = False               # True = hard failure, should re-query LLM
    retry_prompt: Optional[str] = None      # Prompt for re-query (only if needs_retry)
    warnings: list[str] = field(default_factory=list)  # Non-blocking warnings
    auto_fixed: bool = False                # True if code was auto-repaired


# ─────────────────────────────────────────────
# Regex
# ─────────────────────────────────────────────

# Extract module...endmodule (lazy match for first complete block)
MODULE_BLOCK_RE = re.compile(
    r'(module\s+\w+[\s\S]*?endmodule)',
    re.MULTILINE
)

# Module declaration name
MODULE_DECL_RE = re.compile(
    r'module\s+(\w+)\s*[\(#\s]',
    re.MULTILINE
)

# Markdown code fence
CODE_FENCE_RE = re.compile(
    r'```(?:verilog|v|systemverilog|sv)?\s*\n([\s\S]*?)```',
    re.MULTILINE
)

# Alpaca marker
ALPACA_RE = re.compile(r'###\s*Response:\s*\n([\s\S]*)', re.MULTILINE)

# Over-context: max lines
MAX_LINES = 600

# Repetition detection threshold
REPETITION_THRESHOLD = 0.35  # >35% duplicate non-empty lines


# ─────────────────────────────────────────────
# Main Function
# ─────────────────────────────────────────────

def sanitize(
    raw_output: str,
    module_name: Optional[str] = None,
    expected_header: Optional[str] = None,
    max_retries: int = 2,
    current_retry: int = 0,
) -> SanitizeResult:
    """
    Single-pass sanitizer. Returns SanitizeResult.

    Logic:
      1. Strip LLM noise (fences, Alpaca markers)
      2. Find module...endmodule block
      3. If not found but 'module' exists → auto-append endmodule
      4. If still nothing → needs_retry (up to max_retries)
      5. Collect warnings (never block)
      6. Return code + warnings
    """
    warnings = []

    # ── Hard failure: empty output ──
    if not raw_output or not raw_output.strip():
        if current_retry < max_retries:
            return SanitizeResult(
                code=None,
                needs_retry=True,
                retry_prompt=_retry_prompt("empty_output", module_name),
            )
        else:
            # Max retries hit — return empty, let pipeline handle
            return SanitizeResult(code="", warnings=["LLM returned empty output after max retries"])

    text = raw_output

    # ── Step 1: Strip LLM noise ──
    fence = CODE_FENCE_RE.search(text)
    if fence:
        text = fence.group(1)
    else:
        alpaca = ALPACA_RE.search(text)
        if alpaca:
            text = alpaca.group(1)

    # ── Step 2: Over-context detection (warning only) ──
    lines = text.strip().split('\n')
    if len(lines) > MAX_LINES:
        warnings.append(f"Output very long ({len(lines)} lines) — may contain repetition")

    if len(lines) > 20:
        stripped = [l.strip() for l in lines if l.strip()]
        if stripped:
            unique_ratio = len(set(stripped)) / len(stripped)
            if unique_ratio < (1 - REPETITION_THRESHOLD):
                warnings.append(f"High line repetition detected ({1-unique_ratio:.0%} duplicate)")

    # ── Step 3: Extract module...endmodule ──
    blocks = MODULE_BLOCK_RE.findall(text)

    if blocks:
        # Pick the right block
        code = _pick_block(blocks, module_name, warnings)
    else:
        # No complete block found
        if re.search(r'\bmodule\b', text):
            # Has 'module' but no 'endmodule' — truncated, auto-fix
            code = text.rstrip() + '\nendmodule\n'
            warnings.append("Auto-appended 'endmodule' (output was truncated)")
            # Re-try extraction on fixed text
            blocks2 = MODULE_BLOCK_RE.findall(code)
            if blocks2:
                code = _pick_block(blocks2, module_name, warnings)
            # else: use the raw + endmodule as-is
        else:
            # No 'module' keyword at all — hard failure
            if current_retry < max_retries:
                return SanitizeResult(
                    code=None,
                    needs_retry=True,
                    retry_prompt=_retry_prompt("no_module", module_name),
                )
            else:
                # Give up, pass raw text — Verilator will catch it
                warnings.append("No 'module' keyword found after max retries — passing raw to Verilator")
                code = text

    # ── Step 3.5: Forced Header Alignment ──
    if expected_header and code:
        # Match header: 'module' whitespace 'name' whitespace '(' ... ')' whitespace ';'
        # We want to replace everything from 'module' to just after the first ';' with expected_header
        new_code = re.sub(
            r'module\s+\w+\s*\(.*?\)\s*;',
            expected_header,
            code,
            count=1,
            flags=re.DOTALL
        )
        if new_code != code:
            code = new_code
            warnings.append("Forced header alignment: replaced generated header with expected header")

    # ── Step 4: Structural warnings (NEVER block) ──
    _collect_warnings(code, module_name, warnings)

    return SanitizeResult(
        code=code.strip(),
        warnings=warnings,
        auto_fixed=("Auto-appended" in " ".join(warnings)),
    )


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _pick_block(
    blocks: list[str],
    module_name: Optional[str],
    warnings: list[str],
) -> str:
    """Pick the best module block from extracted blocks."""
    if len(blocks) == 1:
        return blocks[0]

    # Multiple blocks
    warnings.append(f"Found {len(blocks)} module definitions — picking best match")

    if module_name:
        matched = [b for b in blocks if re.search(
            rf'module\s+{re.escape(module_name)}\b', b
        )]
        if matched:
            return matched[0]
        else:
            warnings.append(f"No block matches expected name '{module_name}' — using first block")

    return blocks[0]


def _collect_warnings(code: str, module_name: Optional[str], warnings: list[str]):
    """Append non-blocking structural warnings. Never returns failure."""

    # Module name check
    if module_name:
        decl = MODULE_DECL_RE.search(code)
        if decl and decl.group(1) != module_name:
            warnings.append(f"Module name '{decl.group(1)}' doesn't match expected '{module_name}'")

    # begin/end balance (heuristic — regex can't be 100% accurate)
    begin_count = len(re.findall(r'\bbegin\b', code))
    # Standalone 'end' — exclude endmodule, endcase, endfunction, etc.
    end_standalone = len(re.findall(
        r'\bend\b(?!module|case|function|task|generate|primitive|table|specify|config)',
        code
    ))
    if begin_count != end_standalone:
        warnings.append(f"Possible begin/end imbalance: {begin_count} begin vs {end_standalone} end")

    # Always without sensitivity list
    if re.search(r'always\s+begin', code):
        warnings.append("'always begin' without sensitivity list — may need @(*) or @(posedge clk)")

    # Output assigned in always but not declared as reg (common Verilator error)
    outputs = re.findall(r'output\s+(?:reg\s+)?(?:\[[\d:]+\]\s+)?(\w+)', code)
    always_blocks = re.findall(r'always\s*@[\s\S]*?(?:\bend\b)', code)
    for block in always_blocks:
        for out in outputs:
            if re.search(rf'\b{re.escape(out)}\s*<=', block) or \
               re.search(rf'\b{re.escape(out)}\s*=[^=]', block):
                if not re.search(rf'output\s+reg\s+(?:\[[\d:]+\]\s+)?{re.escape(out)}\b', code) and \
                   not re.search(rf'reg\s+(?:\[[\d:]+\]\s+)?{re.escape(out)}\b', code):
                    warnings.append(f"Output '{out}' in always block but not declared as reg")

    # Blocking assignment in sequential always (style warning)
    seq_always = list(re.finditer(r'always\s*@\s*\(\s*(posedge|negedge)', code))
    for m in seq_always:
        chunk = code[m.end():m.end() + 500]
        blocking = re.findall(r'^\s*(\w+)\s*=\s*[^=]', chunk, re.MULTILINE)
        real = [a for a in blocking if a not in ('if', 'else', 'case', 'for', 'while', 'integer')]
        if real:
            warnings.append(f"Blocking (=) in sequential always for: {real[:3]}")

    # No logic keywords (info only — some modules may use generate/instantiation)
    logic_kws = {'always', 'always_comb', 'always_ff', 'always_latch', 'assign', 'initial'}
    if not any(re.search(rf'\b{kw}\b', code) for kw in logic_kws):
        warnings.append("No assign/always/initial keywords found — may be incomplete")


def _retry_prompt(reason: str, module_name: Optional[str]) -> str:
    """Minimal retry prompts — only for hard failures."""
    name = module_name or "the_module"
    if reason == "empty_output":
        return (
            f"You did not produce any output. "
            f"Please generate the COMPLETE Verilog module '{name}' "
            f"from 'module' to 'endmodule'. Output ONLY Verilog code."
        )
    elif reason == "no_module":
        return (
            f"Your output did not contain a Verilog module. "
            f"Please output the COMPLETE module '{name}' starting with "
            f"'module {name}' and ending with 'endmodule'. "
            f"Output ONLY Verilog code, no explanation."
        )
    return f"Please regenerate module '{name}'. Output ONLY Verilog code."


# ─────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("verilog_sanitizer.py — Self-test")
    print("=" * 50)

    # Test 1: Clean code → pass through
    print("\n--- Test 1: Clean code ---")
    r = sanitize("""
module adder_8bit(input [7:0] a, b, input cin, output [7:0] sum, output cout);
    assign {cout, sum} = a + b + cin;
endmodule
""", module_name="adder_8bit")
    assert r.code is not None and not r.needs_retry
    print(f"  ✅ code extracted, warnings={r.warnings}")

    # Test 2: Markdown fence + explanation → extract
    print("\n--- Test 2: Markdown fence ---")
    r = sanitize("""
Here is the corrected code:

```verilog
module alu(input [7:0] a, b, input [2:0] op, output reg [7:0] result);
    always @(*) begin
        case(op)
            3'b000: result = a + b;
            default: result = 8'b0;
        endcase
    end
endmodule
```

This fixes the bug.
""", module_name="alu")
    assert r.code is not None and "module alu" in r.code
    print(f"  ✅ extracted from fence, warnings={r.warnings}")

    # Test 3: No module → needs_retry (but only up to max)
    print("\n--- Test 3: No module keyword ---")
    r = sanitize("I cannot generate this code.", module_name="alu", current_retry=0)
    assert r.needs_retry
    print(f"  ✅ needs_retry=True, prompt={r.retry_prompt[:50]}...")

    # Test 3b: No module, max retries → pass through anyway
    r = sanitize("I cannot generate this code.", module_name="alu", current_retry=2)
    assert not r.needs_retry and r.code is not None
    print(f"  ✅ max retries → pass through, warnings={r.warnings}")

    # Test 4: Missing endmodule → auto-fix
    print("\n--- Test 4: Missing endmodule (auto-fix) ---")
    r = sanitize("""
module test(input a, output b);
    assign b = a;
""", module_name="test")
    assert r.code is not None and "endmodule" in r.code
    print(f"  ✅ auto-fixed, auto_fixed={r.auto_fixed}, warnings={r.warnings}")

    # Test 5: Empty output → needs_retry
    print("\n--- Test 5: Empty output ---")
    r = sanitize("", module_name="alu")
    assert r.needs_retry
    print(f"  ✅ needs_retry for empty")

    # Test 5b: Empty, max retries → pass through
    r = sanitize("", module_name="alu", current_retry=2)
    assert not r.needs_retry
    print(f"  ✅ max retries → empty string pass through")

    # Test 6: Module name mismatch → WARNING, still passes
    print("\n--- Test 6: Name mismatch (warning only) ---")
    r = sanitize("""
module wrong_name(input a, output b);
    assign b = a;
endmodule
""", module_name="correct_name")
    assert r.code is not None and not r.needs_retry
    assert any("doesn't match" in w for w in r.warnings)
    print(f"  ✅ passed with warning: {r.warnings}")

    # Test 7: Complex module with case/endcase → no false begin/end alarm
    print("\n--- Test 7: Complex ALU with case/endcase ---")
    r = sanitize("""
module alu(
    input [7:0] a, b,
    input [3:0] op,
    output reg [7:0] result,
    output reg zero
);
    always @(*) begin
        case(op)
            4'b0000: result = a + b;
            4'b0001: result = a - b;
            4'b0010: result = a & b;
            4'b0011: result = a | b;
            4'b0100: result = a ^ b;
            4'b0101: result = ~a;
            4'b0110: result = a << 1;
            4'b0111: result = a >> 1;
            default: result = 8'b0;
        endcase
        zero = (result == 8'b0);
    end
endmodule
""", module_name="alu")
    assert r.code is not None and not r.needs_retry
    # Should NOT have begin/end warning for this valid code
    has_balance_warn = any("begin/end" in w for w in r.warnings)
    print(f"  ✅ passed, begin/end warning={has_balance_warn}, warnings={r.warnings}")

    # Test 8: Output not reg → WARNING, still passes
    print("\n--- Test 8: Output not reg (warning only) ---")
    r = sanitize("""
module counter(input clk, rst, output [3:0] count);
    always @(posedge clk) begin
        if (rst) count <= 0;
        else count <= count + 1;
    end
endmodule
""", module_name="counter")
    assert r.code is not None and not r.needs_retry
    assert any("not declared as reg" in w for w in r.warnings)
    print(f"  ✅ passed with warning: {r.warnings}")

    # Test 9: Multiple modules → pick matching, warn
    print("\n--- Test 9: Multiple modules ---")
    r = sanitize("""
module helper(input a, output b);
    assign b = ~a;
endmodule

module main(input x, output y);
    assign y = x;
endmodule
""", module_name="main")
    assert r.code is not None and "module main" in r.code
    print(f"  ✅ picked 'main', warnings={r.warnings}")

    # Test 10: Alpaca format
    print("\n--- Test 10: Alpaca format ---")
    r = sanitize("""
Below is the response.

### Response:
module ff(input clk, input d, output reg q);
    always @(posedge clk) q <= d;
endmodule
""", module_name="ff")
    assert r.code is not None and "module ff" in r.code
    print(f"  ✅ extracted from Alpaca marker")

    print("\n" + "=" * 50)
    print("✅ ALL 10 TESTS PASSED")
    print("=" * 50)

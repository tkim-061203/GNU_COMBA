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
# Regex Definitions
# ─────────────────────────────────────────────

# S1
RE_FENCE      = re.compile(r"```(?:verilog|sv|systemverilog)?\s*\n?|```", re.I)
# S2  
RE_HTML_CMT   = re.compile(r"<!--.*?-->", re.S)
RE_XML_TAG    = re.compile(r"</?[a-zA-Z][^>]*>")
# S3
RE_MODULE     = re.compile(r"module\s+\w+.*?endmodule", re.S)
# S4
RE_LINE_CMT   = re.compile(r"//[^\n]*")
RE_BLOCK_CMT  = re.compile(r"/\*.*?\*/", re.S)
# S6
RE_MULTI_BLANK= re.compile(r"\n\s*\n\s*\n+")

PLACEHOLDERS = [
    "fill", "todo", "your code", "implement here", "..."
]

LOGIC_KEYWORDS = [
    "assign", "always", "always_comb", "always_ff", "always_latch", "initial",
    "generate", "for", "if", "case", "and", "or", "not", "xor", "xnor", "nand", "nor",
    "buf", "notif0", "notif1", "bufif0", "bufif1"
]

# For S8 (Old Features)
_ALWAYS_LHS_RE = re.compile(
    r'^[\t ]*([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:<=|=(?!=))',
    re.MULTILINE,
)
MODULE_DECL_RE = re.compile(
    r'module\s+(\w+)\s*[\(#\s]',
    re.MULTILINE
)

def _is_prose_line(line: str) -> bool:
    """
    S5 check: A line is considered prose (return True) if it does NOT contain
    any Verilog grammar symbols AND does NOT contain any Verilog keywords.
    """
    stripped = line.strip()
    if not stripped:
        return False # Empty lines are handled by S6

    # 1. Check for Verilog symbols (giữ: ; , ( ) [ ] = < > + - * / & | ^ ~ ! ? :)
    if any(c in stripped for c in ";,()[]=<>{}+-*/&|^~!?#@'\"\\.:"):
        return False
        
    # 2. Check for Verilog keywords
    if re.search(r'\b(module|endmodule|input|output|inout|wire|reg|logic|assign|always|always_comb|always_ff|always_latch|initial|begin|end|if|else|case|endcase|parameter|localparam|generate|endgenerate|for|default)\b', stripped):
        return False
        
    return True

# ─────────────────────────────────────────────
# Old Helpers (S8)
# ─────────────────────────────────────────────

def _auto_promote_output_reg(code: str) -> tuple[str, list[str]]:
    """
    Promote bare `output` ports to `output reg` when they appear as LHS
    targets inside `always` blocks (blocking or non-blocking assignment).
    """
    bare_output_re = re.compile(
        r'\boutput\s+(?!reg\b)(?!logic\b)(?!wire\b)'
        r'(?:\[[^\]]*\]\s+)?(\w+)',
        re.MULTILINE,
    )
    bare_outputs = {m.group(1) for m in bare_output_re.finditer(code)}

    if not bare_outputs:
        return code, []

    always_lhs: set[str] = set()
    for block_m in re.finditer(r'\balways\b[\s\S]*?(?=\balways\b|\bassign\b|endmodule)', code):
        block_text = block_m.group(0)
        for lhs_m in _ALWAYS_LHS_RE.finditer(block_text):
            always_lhs.add(lhs_m.group(1))

    to_promote = bare_outputs & always_lhs
    if not to_promote:
        return code, []

    new_code = code
    for name in to_promote:
        new_code = re.sub(
            r'\b(output\s+)((?:\[[^\]]*\]\s*)?)(' + re.escape(name) + r')\b',
            r'\1reg \2\3',
            new_code,
            flags=re.MULTILINE
        )

    return new_code, sorted(to_promote)

def _strip_redundant_wires(code: str) -> tuple[str, list[str]]:
    """
    Remove redundant `wire` declarations for signals already in the port list.
    Example: module Top(output one); wire one; ... -> module Top(output one); ...
    """
    # Find all signals in the port list (input, output, inout)
    port_re = re.compile(
        r'\b(?:input|output|inout)\s+(?:reg\s+|logic\s+|wire\s+)?(?:\[[^\]]*\]\s+)?(\w+)',
        re.MULTILINE
    )
    ports = {m.group(1) for m in port_re.finditer(code)}
    
    if not ports:
        return code, []
    
    stripped: list[str] = []
    new_code = code
    for name in ports:
        # Match 'wire <name>;' or 'wire [range] <name>;'
        # We use re.MULTILINE to allow matching start of line.
        redundant_re = re.compile(
            rf'^\s*wire\s+(?:\[[^\]]*\]\s+)?{re.escape(name)}\s*;',
            re.MULTILINE
        )
        if redundant_re.search(new_code):
            new_code = redundant_re.sub("", new_code)
            stripped.append(name)
            
    return new_code, sorted(stripped)

def _check_generate_bounds(code: str, warnings: list[str]) -> None:
    """Warn when a generate/for loop uses an index that may exceed the declared port width."""
    port_ranges: dict[str, tuple[int, int]] = {}
    for m in re.finditer(
        r'\boutput\s+(?:reg\s+|logic\s+|wire\s+)?\[\s*(\d+)\s*:\s*(\d+)\s*\]\s+(\w+)',
        code, re.MULTILINE
    ):
        high, low, name = int(m.group(1)), int(m.group(2)), m.group(3)
        port_ranges[name] = (high, low)

    if not port_ranges:
        return

    for loop_m in re.finditer(
        r'for\s*\([^;]*;[^;]*<\s*(\d+)\s*;',
        code, re.MULTILINE
    ):
        upper = int(loop_m.group(1))
        for name, (high, low) in port_ranges.items():
            if upper - 1 > high:
                warnings.append(
                    f"Generate-loop may access {name}[{upper-1}] but port is declared [{high}:{low}] "
                    f"(max valid index {high})"
                )

def _extract_widths(code: str) -> dict[str, tuple[int, int]]:
    """Helper to extract bit-widths of all declared signals (input, output, wire, reg, logic)."""
    widths: dict[str, tuple[int, int]] = {}
    # 1. Match [H:L] declarations
    decl_re = re.compile(
        r'\b(?:input|output|inout|wire|reg|logic)\s+(?:reg\s+|logic\s+|wire\s+)?\[\s*(\d+)\s*:\s*(\d+)\s*\]\s+(\w+)',
        re.MULTILINE
    )
    for m in decl_re.finditer(code):
        h, l, name = int(m.group(1)), int(m.group(2)), m.group(3)
        widths[name] = (max(h, l), min(h, l))
    
    # 2. Catch single-bit signals (no bracket)
    single_re = re.compile(
        r'\b(?:input|output|inout|wire|reg|logic)\s+(?:reg\s+|logic\s+|wire\s+)?(?<!\[)\b(\w+)\b',
        re.MULTILINE
    )
    for m in single_re.finditer(code):
        name = m.group(1)
        if name not in widths and name not in ('begin', 'end', 'case', 'module', 'endmodule', 'always', 'assign'):
            widths[name] = (0, 0)
    return widths

def _collect_warnings(code: str, module_name: Optional[str], warnings: list[str], expected_header: str = ""):
    """Append non-blocking structural warnings. Never returns failure."""
    # [1] Module name mismatch
    if module_name:
        decl = MODULE_DECL_RE.search(code)
        if decl and decl.group(1) != module_name:
            warnings.append(f"Module name '{decl.group(1)}' doesn't match expected '{module_name}'")

    # [2] begin/end balance
    begin_count = len(re.findall(r'\bbegin\b', code))
    end_standalone = len(re.findall(
        r'\bend\b(?!module|case|function|task|generate|primitive|table|specify|config)',
        code
    ))
    if begin_count != end_standalone:
        warnings.append(f"Possible begin/end imbalance: {begin_count} begin vs {end_standalone} end")

    # [3] always begin (missing sensitivity)
    if re.search(r'always\s+begin', code):
        warnings.append("'always begin' without sensitivity list — may need @(*) or @(posedge clk)")

    # [4] Output reg check
    outputs = re.findall(r'output\s+(?:reg\s+)?(?:\[[\d:]+\]\s+)?(\w+)', code)
    always_blocks = re.findall(r'always\s*@[\s\S]*?(?:\bend\b)', code)
    for block in always_blocks:
        for out in outputs:
            if re.search(rf'\b{re.escape(out)}\s*<=', block) or \
               re.search(rf'\b{re.escape(out)}\s*=[^=]', block):
                if not re.search(rf'output\s+reg\s+(?:\[[\d:]+\]\s+)?{re.escape(out)}\b', code) and \
                   not re.search(rf'reg\s+(?:\[[\d:]+\]\s+)?{re.escape(out)}\b', code):
                    warnings.append(f"Output '{out}' in always block but not declared as reg")

    # [5] Blocking in sequential
    seq_always = list(re.finditer(r'always\s*@\s*\(\s*(posedge|negedge)', code))
    for m in seq_always:
        chunk = code[m.end():m.end() + 500]
        blocking = re.findall(r'^\s*(\w+)\s*=\s*[^=]', chunk, re.MULTILINE)
        real = [a for a in blocking if a not in ('if', 'else', 'case', 'for', 'while', 'integer')]
        if real:
            warnings.append(f"Blocking (=) in sequential always for: {real[:3]}")

    # [6] Non-blocking in combinational
    comb_always = list(re.finditer(r'always\s*@\s*(\*|\(\s*\*\s*\))', code))
    for m in comb_always:
        chunk = code[m.end():m.end() + 500]
        non_blocking = re.findall(r'^\s*(\w+)\s*<=\s*', chunk, re.MULTILINE)
        if non_blocking:
            warnings.append(f"Non-blocking (<=) in combinational always for: {non_blocking[:3]}")

    # [7] Out-of-bounds indexing
    widths = _extract_widths(code)
    index_usages = re.finditer(r'\b(\w+)\s*\[\s*(\d+)\s*\]', code)
    for m in index_usages:
        name, idx_val = m.group(1), int(m.group(2))
        if name in widths:
            h, l = widths[name]
            if idx_val > h or idx_val < l:
                warnings.append(f"Out-of-bounds index: {name}[{idx_val}] but declared as [{h}:{l}]")

    # [8] FSM Lag (next_state assigned with <= in sequential block)
    if re.search(r'state\s*<=\s*next_state', code) and re.search(r'next_state\s*<=\s*', code):
        warnings.append("FSM next_state updated with (<=) inside sequential block — usually leads to 1-cycle lag")

    # [9] Mixed clock edges
    has_posedge = re.search(r'\bposedge\b', code)
    has_negedge = re.search(r'\bnegedge\b', code)
    if has_posedge and has_negedge:
        warnings.append("Mixed clock edges (posedge and negedge) detected in the same module")

    # [10] Port count mismatch
    if expected_header:
        # Count port directions as a proxy for port count
        expected_ports = len(re.findall(r'\b(input|output|inout)\b', expected_header))
        actual_ports = len(re.findall(r'\b(input|output|inout)\b', code))
        if expected_ports != actual_ports:
            warnings.append(f"Port count mismatch: expected {expected_ports} ports but found {actual_ports}")

# ─────────────────────────────────────────────
# Main Function
# ─────────────────────────────────────────────

def sanitize(
    raw_output: str,
    expected_header: str = ""
) -> SanitizeResult:
    """
    Pipeline strip (strict ordering):
    [S1] Strip markdown fences
    [S2] Strip XML/HTML tags
    [S3] Extract module block
    [S4] Strip Verilog comments
    [S5] Strip prose lines
    [S6] Normalize whitespace
    [S7] Validate invariants
    [S8] (Restored) Auto-promote output reg & Warnings
    """
    warnings = []
    
    if not raw_output or not raw_output.strip():
        return SanitizeResult(code=None, needs_retry=True, retry_prompt="LLM output is empty.")

    # ── [S1] Strip markdown fences ──
    code = RE_FENCE.sub("", raw_output)

    # ── [S2] Normalize common hallucinations ──
    code = re.sub(r'\bdmodule\b', 'endmodule', code)

    # ── [S2.5] Strip XML/HTML tags ──
    code = RE_HTML_CMT.sub("", code)
    code = RE_XML_TAG.sub("", code)

    # ── [S3] Strip Verilog comments ──
    # We do this early to avoid 'module' keywords in comments confusing extraction
    code = RE_LINE_CMT.sub("", code)
    code = RE_BLOCK_CMT.sub("", code)

    # ── [S4] Extract module block ──
    extracted_module_name = None
    if expected_header:
        match = re.search(r'module\s+(\w+)', expected_header)
        if match:
            extracted_module_name = match.group(1)

    # Robust extraction: match each 'endmodule' with its nearest preceding 'module'
    modules = list(re.finditer(r'\bmodule\b', code))
    endmodules = list(re.finditer(r'\bendmodule\b', code))
    
    blocks = []
    used_module_indices = set()
    for e in endmodules:
        e_start = e.start()
        candidate = None
        for m in reversed(modules):
            m_start = m.start()
            if m_start < e_start and m_start not in used_module_indices:
                candidate = m
                break
        if candidate:
            blocks.append(code[candidate.start():e.end()])
            used_module_indices.add(candidate.start())

    if not blocks:
        return SanitizeResult(
            code=None, 
            needs_retry=True, 
            retry_prompt="No Verilog module found. Please output the COMPLETE module starting with 'module' and ending with 'endmodule'."
        )

    # Pick the best block: matching expected name, or longest
    if extracted_module_name:
        matched_blocks = [b for b in blocks if re.search(rf'\bmodule\s+{re.escape(extracted_module_name)}\b', b)]
        if matched_blocks:
            code = max(matched_blocks, key=len)
            if len(blocks) > 1:
                warnings.append(f"Multiple modules found. Isolated '{extracted_module_name}'.")
        else:
            code = max(blocks, key=len)
    else:
        code = max(blocks, key=len)

    # ── [S5] Strip prose lines ──
    lines = code.split('\n')
    filtered_lines = [line for line in lines if not _is_prose_line(line)]
    code = "\n".join(filtered_lines)

    # ── [S6] Normalize whitespace ──
    code = RE_MULTI_BLANK.sub("\n\n", code)
    code = code.strip()

    # ── [S7] Validate invariants ──
    
    # 1. module count == 1
    module_count = len(re.findall(r'\bmodule\b', code))
    endmodule_count = len(re.findall(r'\bendmodule\b', code))

    if module_count != endmodule_count or module_count == 0:
        return SanitizeResult(
            code=None, 
            needs_retry=True, 
            retry_prompt="Mismatch between 'module' and 'endmodule'. Please provide exactly ONE complete module block."
        )

    # 3. Không còn placeholder keywords (kiểm tra trước khi xóa comment để bắt '... fill here ...')
    lower_code = code.lower()
    for p in PLACEHOLDERS:
        if p in lower_code:
            return SanitizeResult(
                code=None, 
                needs_retry=True, 
                retry_prompt=f"Found placeholder '{p}'. Please provide the full working implementation without placeholders."
            )

    # 4. Không còn //, /*, <!--, <tag>
    if RE_LINE_CMT.search(code) or RE_BLOCK_CMT.search(code) or RE_HTML_CMT.search(code) or RE_XML_TAG.search(code):
        # re-run S2/S4
        code = RE_HTML_CMT.sub("", code)
        code = RE_XML_TAG.sub("", code)
        code = RE_LINE_CMT.sub("", code)
        code = RE_BLOCK_CMT.sub("", code)

    # 5. Có >=1 logic keyword (assign/always/initial/instantiation)
    has_logic = any(re.search(rf'\b{kw}\b', code) for kw in LOGIC_KEYWORDS)
    has_instantiation = bool(re.search(r'\b\w+\s+\w+\s*\(.*?\)\s*;', code, re.S))
    if not (has_logic or has_instantiation):
        return SanitizeResult(
            code=None, 
            needs_retry=True, 
            retry_prompt="The module contains no logic (no assign, always, initial, or module instantiations). Please implement the required logic."
        )

    # 6. Header khớp expected_header (force-replace header)
    actual_port_count = -1
    if expected_header:
        # Capture actual port count BEFORE alignment for warnings
        actual_port_count = len(re.findall(r'\b(input|output|inout)\b', code))
        # Use a more robust regex for header replacement that handles optional semicolon and internal whitespace
        header_pattern = re.compile(r'module\s+\w+\s*\(.*?\)\s*;?', re.DOTALL)
        new_code = header_pattern.sub(expected_header, code, count=1)
        if new_code != code:
            code = new_code
            warnings.append("Forced header alignment: replaced generated header with expected_header")

    # ── [S8] Old Features Restored (Auto-promote output reg & Warnings) ──
    code, promoted = _auto_promote_output_reg(code)
    if promoted:
        warnings.append(f"Auto-promoted to 'output reg': {', '.join(promoted)}")
        
    code, stripped_wires = _strip_redundant_wires(code)
    if stripped_wires:
        warnings.append(f"Stripped redundant 'wire' declarations: {', '.join(stripped_wires)}")
        
    _check_generate_bounds(code, warnings)
    
    # Attempt to extract module name if we didn't get it from expected_header
    if not extracted_module_name:
        decl = MODULE_DECL_RE.search(code)
        if decl:
            extracted_module_name = decl.group(1)
            
    _collect_warnings(code, extracted_module_name, warnings, expected_header)

    # Overwrite/Add port count mismatch warning if we have the pre-alignment count
    if expected_header and actual_port_count != -1:
        expected_port_count = len(re.findall(r'\b(input|output|inout)\b', expected_header))
        if expected_port_count != actual_port_count:
            warnings.append(f"Port count mismatch: generated code had {actual_port_count} ports, but spec requires {expected_port_count}")

    any_auto_fixed = (
        "Auto-appended" in " ".join(warnings)
        or bool(promoted)
        or bool(stripped_wires)
        or "Forced header alignment" in " ".join(warnings)
    )

    return SanitizeResult(
        code=code,
        warnings=warnings,
        auto_fixed=any_auto_fixed
    )

if __name__ == "__main__":
    # Test vector (Prob001 case) from the prompt
    test_raw = """module TopModule (
  output zero
);
<!-- zero is assigned the permanent value 0, and is also declared as output reg zero; -->
assign zero = 1'b0;
endmodule"""

    expected = "module TopModule (\n  output zero\n);"
    res = sanitize(test_raw, expected)
    print("--- Test Prob001 ---")
    print(res.code)
    assert res.code.strip() == "module TopModule (\n  output zero\n);\n\nassign zero = 1'b0;\nendmodule", "Prob001 test failed!"
    print("PASS")

    # Test redundant wire stripping
    test_redundant = """module TopModule (
  output one
);
wire one;
assign one = 1'b1;
endmodule"""
    res2 = sanitize(test_redundant, "module TopModule (\n  output one\n);")
    print("--- Test Redundant Wire ---")
    print(res2.code)
    assert "wire one;" not in res2.code, "Redundant wire stripping failed!"
    print("PASS")

    # Test Multi-Header (Prob005 style)
    test_multi = """Here is an example:
module TopModule (input in, output out);
// No endmodule here
Now here is the solution:
module TopModule (input in, output out);
  assign out = ~in;
endmodule
"""
    res3 = sanitize(test_multi, "module TopModule (input in, output out);")
    print("--- Test Multi-Header ---")
    print(res3.code)
    # count word 'module' (not 'endmodule')
    m_count = len(re.findall(r'\bmodule\b', res3.code))
    assert m_count == 1, f"Multi-header isolation failed! Found {m_count} modules"
    assert "~in" in res3.code, "Correct module block not found!"
    print("PASS")

    # Test Structural Warnings
    test_warnings = """module TopModule (
    input [31:0] a,
    output [31:0] r
);
    reg [7:0] local_reg;
    always @* begin
        r <= a; // Non-blocking in comb
        local_reg[10] = 1'b1; // Out of bounds
    end
endmodule"""
    res4 = sanitize(test_warnings)
    print("--- Test Structural Warnings ---")
    for w in res4.warnings:
        print(f"  {w}")
    assert any("Non-blocking" in w for w in res4.warnings), "Failed to detect non-blocking in comb"
    assert any("Out-of-bounds" in w for w in res4.warnings), "Failed to detect out-of-bounds"
    print("PASS")

    # Test Mixed Edges & Port Mismatch
    test_mixed = """module TopModule (input clk, input a, output b, output c);
    always @(posedge clk) b <= a;
    always @(negedge clk) c <= a;
endmodule"""
    res6 = sanitize(test_mixed, "module TopModule (input clk, input a, output b);")
    print("--- Test Mixed/Mismatch ---")
    for w in res6.warnings:
        print(f"  {w}")
    assert any("Mixed clock edges" in w for w in res6.warnings), "Failed to detect mixed edges"
    assert any("Port count mismatch" in w for w in res6.warnings), "Failed to detect port mismatch"
    print("PASS")

    # Test dmodule fix
    test_dmodule = """module TopModule (output zero);
dmodule"""
    res5 = sanitize(test_dmodule, "module TopModule (output zero);")
    print("--- Test dmodule ---")
    print(res5.code)
    assert "endmodule" in res5.code, "dmodule normalization failed!"
    print("PASS")

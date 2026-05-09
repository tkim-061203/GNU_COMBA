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
# RE_XML_TAG changed to be more conservative. 
# We only want to strip known COMBA tags or tags that look like structured markers.
# Verilog operators like < and > should NOT be stripped.
RE_XML_TAG    = re.compile(r"<(?:module|ports|input|output|inout|logic_description|implementation|parameter_description|description|task)[^>]*>|</(?:module|ports|input|output|inout|logic_description|implementation|parameter_description|description|task)>", re.I)
# S3
RE_MODULE     = re.compile(r"module\s+\w+.*?endmodule", re.S)
# S4
RE_LINE_CMT   = re.compile(r"//[^\n]*")
# RE_BLOCK_CMT updated to be non-greedy
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
        return False
    # Verilog "fingerprints"
    verilog_symbols = [';', '(', ')', '[', ']', '{', '}', '=', '<', '>', '@', '#', ':', '`', '*', '+', '-', '/', '%', '&', '|', '^', '!', '~', '?', ',']
    has_symbol = any(s in stripped for s in verilog_symbols)
    
    # Check for keywords (case sensitive)
    keywords = ['module', 'endmodule', 'reg', 'wire', 'input', 'output', 'inout', 'assign', 'always', 'initial', 'begin', 'end', 'parameter', 'localparam']
    has_keyword = any(re.search(rf'\b{k}\b', stripped) for k in keywords)
    
    return not (has_symbol or has_keyword)

def _count_logic_occurrences(code: str) -> int:
    """Count how many times logic keywords appear in the code."""
    count = 0
    for kw in LOGIC_KEYWORDS:
        count += len(re.findall(rf'\b{re.escape(kw)}\b', code))
    return count

def run_structural_checks(code: str, expected_header: str = "") -> list[str]:
    """Perform deep structural checks to catch logical corruption early."""
    warnings = []
    
    # [1] Empty logic check
    logic_count = _count_logic_occurrences(code)
    if logic_count < 2: # At least one always/assign + module/endmodule keywords usually exist
        warnings.append("Extracted module appears to have very little or no logic (logic keyword count < 2)")

    # [2] Placeholder check
    for p in PLACEHOLDERS:
        if p in code.lower():
            warnings.append(f"Found placeholder/todo text: '{p}'")

    # [3] Register promotion guard
    # Check for outputs that are assigned in always blocks but not declared as reg
    assigned_in_always = set()
    # Find all always blocks and their LHS assignments
    always_blocks = re.findall(r'\balways\b.*?\bbegin\b.*?\bend\b', code, re.S)
    if not always_blocks:
        # Try without begin/end (single statement)
        always_blocks = re.findall(r'\balways\b.*?;', code, re.S)
        
    for block in always_blocks:
        lhs_matches = _ALWAYS_LHS_RE.findall(block)
        assigned_in_always.update(lhs_matches)
        
    # Find output ports
    output_ports = re.findall(r'output\s+(?:wire\s+)?(?:\[[^\]]*\]\s*)?(\w+)', code)
    for op in output_ports:
        if op in assigned_in_always:
            # Check if it's already a reg
            if not re.search(rf'output\s+reg\s+.*?\b{re.escape(op)}\b', code) and \
               not re.search(rf'reg\s+.*?\b{re.escape(op)}\b', code):
                warnings.append(f"Output port '{op}' is assigned in always block but NOT declared as 'reg'")

    # [4] Incomplete case/if
    if "case" in code and "default" not in code:
        warnings.append("Case statement found without 'default' branch (potential latch)")
        
    # [5] Duplicate module declaration
    if len(re.findall(r'\bmodule\b', code)) > 1:
        warnings.append("Multiple module declarations found in output")

    # [6] High-impedance or Undefined logic patterns
    if "1'bz" in code or "32'bz" in code:
        warnings.append("High-impedance (z) detected in logic (ensure this is intended for tri-state)")
        
    # [7] Port mismatch in assignments
    # Check for variables that look like ports but aren't declared
    # (Simplified: check for assignments to variables not in port list or internal decls)
    # skipped for now to avoid false positives

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

    return warnings

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

    # ── [S2.5] Strip XML/HTML tags (Conservative) ──
    # We only strip specific tags known to be part of the COMBA XML schema
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
        # ── Check for header-only truncation ──
        # The LLM may have produced a valid module header but stopped before the body
        header_match = re.search(r'(module\s+\w+\s*(?:\([^)]*\)|#\([^)]*\)\s*\([^)]*\))\s*;)', code, re.S)
        if header_match:
            partial_header = header_match.group(1).strip()
            return SanitizeResult(
                code=None,
                needs_retry=True,
                retry_prompt=(
                    f"TRUNCATED OUTPUT DETECTED. You only produced the module header:\n"
                    f"```\n{partial_header}\n```\n"
                    f"Continue from this header. Output the COMPLETE module including "
                    f"ALL internal logic (reg declarations, always blocks, assign statements) "
                    f"and 'endmodule'. Start your output with:\n{partial_header}"
                )
            )
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
    lines = code.splitlines()
    clean_lines = [l for l in lines if not _is_prose_line(l)]
    code = "\n".join(clean_lines)

    # ── [S6] Normalize whitespace ──
    code = RE_MULTI_BLANK.sub("\n\n", code).strip()

    # ── [S7] (New) Structural Checks ──
    warnings.extend(run_structural_checks(code, expected_header))

    # ── [S8] Auto-Repair: Reg Promotion ──
    # If warnings mentioned reg promotion, let's try to fix it automatically
    auto_fixed = False
    if any("assigned in always block but NOT declared as 'reg'" in w for w in warnings):
        # Identify which ones need fixing
        needed = [re.search(r"Output port '(\w+)'", w).group(1) for w in warnings if "assigned in always block but NOT declared as 'reg'" in w]
        for port in needed:
            # Replace 'output port' with 'output reg port'
            new_code = re.sub(rf'\boutput\s+((?:wire\s+)?(?:\[[^\]]*\]\s*)?){re.escape(port)}\b', rf'output reg \1{port}', code)
            if new_code != code:
                code = new_code
                auto_fixed = True
        
        # Remove the warnings that we just fixed
        warnings = [w for w in warnings if "assigned in always block but NOT declared as 'reg'" not in w]
        if auto_fixed:
            warnings.append("Auto-repaired: Promoted output ports to 'reg' for always-block assignments.")

    # ── [S8b] Auto-Repair: Missing endcase ──
    # The LLM frequently drops 'endcase' after case blocks, causing persistent
    # syntax errors. Count case vs endcase and insert missing ones.
    case_count = len(re.findall(r'\bcase[zx]?\s*\(', code))
    endcase_count = len(re.findall(r'\bendcase\b', code))
    if case_count > endcase_count:
        missing = case_count - endcase_count

        def _fix_endcase(code_text):
            """Replace bare 'end' with 'endcase' when it closes an unclosed case block."""
            lines = code_text.splitlines()
            output = []
            # Stack tracks what we're inside: 'begin' or 'case'
            stack = []
            for line in lines:
                s = line.strip()
                # Push 'case' onto stack when we see a case statement
                if re.search(r'\bcase[zx]?\s*\(', s):
                    stack.append('case')
                # Push 'begin' onto stack
                for _ in re.findall(r'\bbegin\b', s):
                    stack.append('begin')
                # Handle endcase — pop the matching 'case'
                if re.search(r'\bendcase\b', s):
                    # Pop until we find 'case'
                    while stack and stack[-1] != 'case':
                        stack.pop()
                    if stack:
                        stack.pop()  # pop the 'case'
                    output.append(line)
                    continue
                # Handle 'end' — check if it should be 'endcase'
                if re.match(r'\s*end\s*$', line):
                    if stack and stack[-1] == 'case':
                        # This 'end' closes a case block — replace with 'endcase'
                        indent = line[:len(line) - len(line.lstrip())]
                        output.append(f'{indent}endcase')
                        stack.pop()
                        continue
                    elif stack and stack[-1] == 'begin':
                        stack.pop()
                # Handle 'end' with stuff after it (like 'end else begin')
                elif re.match(r'\s*end\b', s) and not s.startswith('endmodule') and not s.startswith('endcase') and not s.startswith('endfunction') and not s.startswith('endtask'):
                    if stack and stack[-1] == 'begin':
                        stack.pop()
                output.append(line)
            return '\n'.join(output)

        new_code = _fix_endcase(code)
        if new_code != code:
            code = new_code
            auto_fixed = True
            warnings.append(f"Auto-repaired: Inserted {missing} missing 'endcase' keyword(s).")

    # ── [S8c] Auto-Repair: Missing end ──
    # The LLM frequently drops 'end' before new top-level blocks or endmodule.
    # Count begin vs end keywords and insert missing ones.
    def _fix_missing_end(code_text):
        lines = code_text.splitlines()
        output = []
        begin_count = 0
        end_count = 0
        
        for line in lines:
            s = line.strip()
            
            is_top_level = re.match(r'^\s*(always|assign|initial|endmodule|module)\b', line)
            missing_ends = begin_count - end_count
            
            if is_top_level and missing_ends > 0:
                indent = line[:len(line) - len(line.lstrip())]
                for _ in range(missing_ends):
                    output.append(f"{indent}end // Auto-repaired")
                begin_count = 0
                end_count = 0
                
            begin_count += len(re.findall(r'\bbegin\b', s))
            end_count += len(re.findall(r'\bend\b', s))
            
            output.append(line)
            
        return '\n'.join(output)

    new_code = _fix_missing_end(code)
    if new_code != code:
        code = new_code
        auto_fixed = True
        warnings.append("Auto-repaired: Inserted missing 'end' keyword(s).")


    return SanitizeResult(
        code=code, 
        warnings=warnings,
        auto_fixed=auto_fixed
    )


def fix_header(code: str, expected_header: str) -> str:
    """Force replace the module declaration with the expected one."""
    if not expected_header:
        return code
    
    # Extract module name from expected
    match = re.search(r'module\s+(\w+)', expected_header)
    if not match:
        return code
    name = match.group(1)
    
    # Find the module start in the code
    start_match = re.search(rf'module\s+{re.escape(name)}\s*[\(#\s][^;]*;', code, re.S)
    if start_match:
        # Replace the header
        code = code[:start_match.start()] + expected_header + code[start_match.end():]
        
    return code

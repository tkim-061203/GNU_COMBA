import re
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SanitizeResult:
    code: Optional[str]
    needs_retry: bool = False
    retry_prompt: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    auto_fixed: bool = False

# Regex definitions
RE_FENCE      = re.compile(r"```(?:verilog|sv|systemverilog)?\s*\n?|```", re.I)
RE_HTML_CMT   = re.compile(r"<!--.*?-->", re.S)
RE_XML_TAG    = re.compile(r"</?[a-zA-Z][^>]*>")
RE_MODULE     = re.compile(r"module\s+\w+.*?endmodule", re.S)
RE_LINE_CMT   = re.compile(r"//[^\n]*")
RE_BLOCK_CMT  = re.compile(r"/\*.*?\*/", re.S)
RE_MULTI_BLANK= re.compile(r"\n\s*\n\s*\n+")

PLACEHOLDERS = [
    "fill", "todo", "your code", "implement here", "..."
]

LOGIC_KEYWORDS = [
    "assign", "always", "initial", "always_comb", "always_ff", "always_latch"
]

def is_prose_line(line: str) -> bool:
    if not line.strip():
        return False
    # If the line has any Verilog symbol, assume it's code
    if any(c in line for c in ";,()[]=<>{}+-*/&|^~!?#@'\"\\.:"):
        return False
    # If the line has any Verilog keyword
    if re.search(r'\b(module|endmodule|input|output|inout|wire|reg|logic|assign|always|always_comb|always_ff|always_latch|initial|begin|end|if|else|case|endcase|parameter|localparam|generate|endgenerate|for|default)\b', line):
        return False
    return True

def sanitize(raw: str, expected_header: str) -> SanitizeResult:
    warnings = []
    
    # S1: Strip markdown fences
    code = RE_FENCE.sub("", raw)
    
    # S2: Strip XML/HTML tags
    code = RE_HTML_CMT.sub("", code)
    code = RE_XML_TAG.sub("", code)
    
    # S3: Extract module block
    blocks = RE_MODULE.findall(code)
    if not blocks:
        return SanitizeResult(code=None, needs_retry=True, retry_prompt="No Verilog module found. Please output the COMPLETE module from 'module' to 'endmodule'.")
    
    # Take the longest block
    code = max(blocks, key=len)
    
    # S4: Strip Verilog comments
    code = RE_LINE_CMT.sub("", code)
    code = RE_BLOCK_CMT.sub("", code)
    
    # S5: Strip prose lines
    lines = code.split('\n')
    filtered_lines = [line for line in lines if not is_prose_line(line)]
    code = "\n".join(filtered_lines)
    
    # S6: Normalize whitespace
    code = RE_MULTI_BLANK.sub("\n\n", code)
    code = code.strip()
    
    # S7: Validate invariants
    module_count = len(re.findall(r'\bmodule\b', code))
    endmodule_count = len(re.findall(r'\bendmodule\b', code))
    
    if module_count > 1:
        # Multiple modules found after extraction (e.g., nested or trailing without endmodule in regex matching)
        # We try to extract the one matching expected_header
        # S3 actually extracted `module...endmodule`, so if there are multiple inside, it's weird.
        # Let's extract exactly the one matching the header.
        if expected_header:
            match = re.search(r'module\s+(\w+)', expected_header)
            if match:
                mod_name = match.group(1)
                specific_mod_re = re.compile(rf"module\s+{mod_name}.*?endmodule", re.S)
                specific_blocks = specific_mod_re.findall(code)
                if specific_blocks:
                    code = specific_blocks[0]
                    warnings.append(f"Multiple modules found, isolated {mod_name}")
                else:
                    # Keep the longest? The user said "lấy module trùng expected_header, drop còn lại".
                    pass
        module_count = len(re.findall(r'\bmodule\b', code))
        endmodule_count = len(re.findall(r'\bendmodule\b', code))
    
    if module_count != endmodule_count or module_count == 0:
        return SanitizeResult(code=None, needs_retry=True, retry_prompt="Mismatch between 'module' and 'endmodule'. Please provide exactly one complete module.")
    
    # Check for remnants of comments
    if RE_LINE_CMT.search(code) or RE_BLOCK_CMT.search(code) or RE_HTML_CMT.search(code) or RE_XML_TAG.search(code):
        # Re-run S2/S4 (this should ideally never happen as sub replaces all, but we do it as requested)
        code = RE_HTML_CMT.sub("", code)
        code = RE_XML_TAG.sub("", code)
        code = RE_LINE_CMT.sub("", code)
        code = RE_BLOCK_CMT.sub("", code)
        
    # Check placeholders
    lower_code = code.lower()
    for p in PLACEHOLDERS:
        if p in lower_code:
            return SanitizeResult(code=None, needs_retry=True, retry_prompt=f"Found placeholder '{p}'. Please provide the complete implementation, do not use placeholders.")
            
    # Check logic keyword
    has_logic = any(re.search(rf'\b{kw}\b', code) for kw in LOGIC_KEYWORDS)
    # Check instantiation heuristically: word word ( ... );
    has_instantiation = bool(re.search(r'\b\w+\s+\w+\s*\(.*?\)\s*;', code, re.S))
    if not (has_logic or has_instantiation):
        return SanitizeResult(code=None, needs_retry=True, retry_prompt="The module contains no logic (no assign, always, or instantiations). Please implement the logic.")
        
    # Force-replace header
    if expected_header:
        # replace from 'module' to the first ';'
        new_code = re.sub(r'module\s+\w+\s*\(.*?\)\s*;', expected_header, code, count=1, flags=re.DOTALL)
        if new_code != code:
            code = new_code
            warnings.append("Forced header alignment to expected_header")
            
    return SanitizeResult(code=code, warnings=warnings, auto_fixed=bool(warnings))

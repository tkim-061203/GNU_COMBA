#!/usr/bin/env python3
"""
install_prompt_rules.py — Install R8 (enum honor) + R9 (port fidelity) into
GENERATOR_SYSTEM_PROMPT in src/langgraph_core/prompts.py.

Idempotent: re-running has no effect if rules already present.
Backs up to prompts.py.bak on first run.

Usage:
    python install_prompt_rules.py [src/langgraph_core/prompts.py]
"""

import sys
import shutil
from pathlib import Path

# ─── Anchor: insert BEFORE this line in GENERATOR_SYSTEM_PROMPT ───
ANCHOR = "## XML → Verilog Mapping"

# ─── New rules ───
NEW_RULES = """\
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

"""


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1
                else "src/langgraph_core/prompts.py")
    if not path.is_file():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)

    text = path.read_text()

    # ── Idempotency check ──
    if "### R8: HONOR EXACT ENUM" in text:
        print(f"✓ R8 already present in {path} — nothing to do")
        return
    if "### R9: PORT NAME FIDELITY" in text:
        print(f"✓ R9 already present in {path} — nothing to do")
        return

    # ── Locate anchor inside GENERATOR_SYSTEM_PROMPT ──
    gen_idx = text.find("GENERATOR_SYSTEM_PROMPT")
    if gen_idx < 0:
        print("ERROR: GENERATOR_SYSTEM_PROMPT not found", file=sys.stderr)
        sys.exit(2)

    # find anchor AFTER the start of GENERATOR_SYSTEM_PROMPT,
    # but BEFORE the closing triple-quote of that block
    next_block = text.find("EDP_SYSTEM_PROMPT", gen_idx)
    anchor_idx = text.find(ANCHOR, gen_idx, next_block if next_block > 0 else None)
    if anchor_idx < 0:
        print(f"ERROR: anchor '{ANCHOR}' not found in GENERATOR_SYSTEM_PROMPT",
              file=sys.stderr)
        print("       (Manual install required — see install_prompt_rules.py source)",
              file=sys.stderr)
        sys.exit(3)

    # ── Backup ──
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(path, bak)
        print(f"  Backup → {bak}")

    # ── Insert ──
    new_text = text[:anchor_idx] + NEW_RULES + text[anchor_idx:]
    path.write_text(new_text)

    # ── Verify ──
    verify = path.read_text()
    assert "### R8: HONOR EXACT ENUM" in verify
    assert "### R9: PORT NAME FIDELITY" in verify
    assert verify.count(ANCHOR) == text.count(ANCHOR)  # anchor preserved

    print(f"✓ Installed R8 + R9 into {path}")
    print(f"  ({len(NEW_RULES)} chars added before '{ANCHOR}')")
    print(f"\n  Verify with: grep -E '### R[89]' {path}")


if __name__ == "__main__":
    main()
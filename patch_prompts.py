#!/usr/bin/env python3
"""
patch_prompts_v2.py — Apply Option B (rename TopModule headers).

Option A đã apply rồi (verified ✅). Script này chỉ apply Option B.
Targets the `module TopModule(` line directly — không phụ thuộc vào ký tự xung quanh.
"""

import sys
import shutil
import argparse
from pathlib import Path

DEFAULT_PATH = Path.home() / "GNU_COMBA/src/langgraph_core/prompts.py"


def run(path: Path):
    if not path.exists():
        print(f"ERROR: {path} not found")
        sys.exit(1)

    bak = path.with_suffix(".py.bak3")
    shutil.copy2(path, bak)
    print(f"Backup → {bak}")

    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")

    # Find both TopModule occurrences and replace them in order
    # Order in file: 1st = COMB (adder_8bit), 2nd = SEQ (counter_12)
    new_names = ["adder_8bit", "counter_12"]
    replaced = 0

    for i, line in enumerate(lines):
        if "module TopModule(" in line and replaced < len(new_names):
            lines[i] = line.replace("module TopModule(", f"module {new_names[replaced]}(")
            print(f"  ✅ Line {i+1}: TopModule → {new_names[replaced]}")
            replaced += 1

    if replaced != 2:
        print(f"  ⚠️  Expected 2 replacements, made {replaced}")
        print("  Found 'module TopModule(' on these lines:")
        for i, line in enumerate(content.split("\n")):
            if "TopModule" in line:
                print(f"    {i+1}: {line.strip()}")

    new_content = "\n".join(lines)
    path.write_text(new_content, encoding="utf-8")

    # Verify
    print("\nVerification:")
    final = path.read_text()
    checks = [
        ("module adder_8bit(" in final, "adder_8bit few-shot name"),
        ("module counter_12(" in final, "counter_12 few-shot name"),
        ("module TopModule(" not in final, "no TopModule remaining"),
        ("output reg` promotion is REQUIRED" in final, "Option A exception text (from prior patch)"),
    ]
    all_ok = True
    for ok, label in checks:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {label}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n✅ All checks passed.")
        print("\nNext steps:")
        print("  1. python -c 'import prompts; print(\"import OK\")'")
        print("  2. python -m pytest test_pipeline.py -v -x -q")
        print("  3. Run 5-trial benchmark and compare signal_generator TB PR")
    else:
        print(f"\n⚠️  Failed. Restore: cp {bak} {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    run(args.path)
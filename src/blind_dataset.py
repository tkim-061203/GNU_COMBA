#!/usr/bin/env python3
"""blind_dataset.py - build a benchmark copy the repair loop is allowed to see.

The loop reads `dataset_dir` for two things it must not get during scoring:
the official testbench (an evaluation oracle) and `verified_*.v` (reference
RTL, whose submodules the Sanitizer otherwise appends to candidates). This
script copies only what a given feedback condition permits:

  --mode spec   specification only (design_description*). In-loop TB, if any,
                is generated from the spec. Use for F0/F1/F2.
  --mode tb     specification + official testbench files, never verified_*.v.
                Isolates the testbench-oracle effect (F3) from RTL injection.

Keep "RTLLM" in the destination path: the batch runner uses that substring to
set dataset_dir = module dir. Every file left out is printed, so unexpected
names are reviewed by a human before a run (--strict makes them fatal).

  python src/blind_dataset.py RTLLM_v2/modules .blind/RTLLM_v2_spec/modules --mode spec
"""
from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
from pathlib import Path

SPEC = ["design_description*"]
TB = ["tb.cpp", "testbench.v", "testbench.sv", "tb.v", "tb.sv", "*_test.sv", "*_ref.sv",
      "*.dat", "*.hex", "*.mem", "*.txt", "makefile", "Makefile"]
NEVER = ["verified_*", "*.vcd"]
SKIP_DIRS = {"reports", "obj_dir", "__pycache__"}


def classify(name: str, mode: str) -> str:
    """'copy' | 'drop' (deliberately excluded) | 'unknown'."""
    if any(fnmatch.fnmatch(name, p) for p in NEVER):
        return "drop"
    if any(fnmatch.fnmatch(name, p) for p in SPEC):
        return "copy"
    if any(fnmatch.fnmatch(name, p) for p in TB):
        return "copy" if mode == "tb" else "drop"
    return "unknown"


def build(src: Path, dst: Path, mode: str, strict: bool) -> dict:
    if "rtllm" not in str(dst).lower():
        sys.exit(f"destination must contain 'RTLLM' (batch runner keys dataset_dir on it): {dst}")
    if dst.exists() and any(dst.iterdir()):
        sys.exit(f"destination not empty, refusing to mix runs: {dst}")
    report = {"designs": 0, "copied": 0, "dropped": {}, "unknown": {}}
    for d in sorted(p for p in src.iterdir() if p.is_dir()):
        out = dst / d.name
        out.mkdir(parents=True, exist_ok=True)
        report["designs"] += 1
        for f in sorted(d.iterdir()):
            if f.is_dir():
                if f.name not in SKIP_DIRS:
                    report["unknown"].setdefault(d.name, []).append(f.name + "/")
                continue
            kind = classify(f.name, mode)
            if kind == "copy":
                shutil.copy2(f, out / f.name)
                report["copied"] += 1
            else:
                report[kind if kind == "unknown" else "dropped"].setdefault(d.name, []).append(f.name)
        if not any(fnmatch.fnmatch(x.name, "design_description*") for x in out.iterdir()):
            report["unknown"].setdefault(d.name, []).append("<no spec file copied>")
        if any(x.name.startswith("verified_") for x in out.iterdir()):  # belt and braces
            sys.exit(f"reference RTL leaked into {out}")
    if strict and report["unknown"]:
        sys.exit(f"unknown files (review, then rerun without --strict): {report['unknown']}")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--mode", choices=["spec", "tb"], required=True)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    r = build(Path(a.src), Path(a.dst), a.mode, a.strict)
    kinds = sorted({"verified_*.v" if n.startswith("verified_") else n
                    for v in r["dropped"].values() for n in v})
    print(f"[blind:{a.mode}] {r['designs']} designs, {r['copied']} files copied -> {a.dst}")
    print(f"  dropped names: {kinds}")
    if r["unknown"]:
        print(f"  UNKNOWN (left out, review): {r['unknown']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""dac27_audit.py - legacy-protocol audit numbers for the paper (\\A{...} macros).

For one suite and one or more legacy arms it combines
  * the in-loop breakdown written by the legacy run  (pass5_breakdown.json), and
  * a held-out re-grade of the designs whose final code contains reference
    modules, with those modules stripped               (heldout_grade.py --strip-golden-helpers)
into leak-corrected per-design counts: a design keeps its in-loop count unless
the stripped re-grade says otherwise. Paired sign tests compare arms task by task.

  python src/dac27_audit.py --suite rl2 \
     --arm full=reports/abl1_full/rtllm_v2/pass5_breakdown.json:strip_full_v2.json \
     --arm base=reports/baseline_base_model/rtllm_v2/pass5_breakdown.json:strip_base_v2.json \
     --out paper/results/audit.tex

--grader-agree <nostrip heldout.json> (repeatable) also writes A-grader-agree
(% of trials where the held-out re-grade reproduces the in-loop status:
both_pass + both_fail over all trials), A-grader-agree-count and A-grader-n.
"""
from __future__ import annotations

import argparse
import json
from math import comb
from pathlib import Path


def sign_p(a: dict, b: dict) -> tuple[int, int, float]:
    pos = sum(a[t] > b[t] for t in a)
    neg = sum(a[t] < b[t] for t in a)
    n, k = pos + neg, min(pos, neg)
    p = 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
    return pos, neg, p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    ap.add_argument("--arm", action="append", required=True, help="name=breakdown.json[:strip.json]")
    ap.add_argument("--out", required=True)
    ap.add_argument("--grader-agree", action="append", default=[],
                    help="heldout_grade.py output without --strip-golden-helpers (repeatable)")
    a = ap.parse_args()

    lines, counts = [], {}
    for spec in a.arm:
        name, files = spec.split("=", 1)
        bd_file, _, strip_file = files.partition(":")
        bd = json.loads(Path(bd_file).read_text())
        n = bd["n_trials"]
        legacy = {p["design"]: p["c_func"] for p in bd["per_design"]}
        fixed, golden_designs, flipped = dict(legacy), [], []
        if strip_file:
            st = json.loads(Path(strip_file).read_text())
            for p in st["per_design"]:
                if p["stripped"]:
                    golden_designs.append(p["design"])
                    fixed[p["design"]] = p["c_heldout"]
                    if legacy[p["design"]] > 0 and p["c_heldout"] == 0:
                        flipped.append(p["design"])
        counts[name] = fixed
        nd = len(legacy)
        k = f"{a.suite}-{name}"
        vals = {
            "designs": nd,
            "solved": sum(c > 0 for c in legacy.values()),
            "legacy-p5": 100 * sum(c > 0 for c in legacy.values()) / nd,
            "legacy-p1": 100 * sum(legacy.values()) / (n * nd),
            "fixed-p5": 100 * sum(c > 0 for c in fixed.values()) / nd,
            "fixed-p1": 100 * sum(fixed.values()) / (n * nd),
            "golden-designs": len(golden_designs),
            "leak-pass-designs": len(flipped),
        }
        if not strip_file:   # not re-graded: never print a "0 leaks" that was not measured
            for m in ("fixed-p5", "fixed-p1", "golden-designs", "leak-pass-designs"):
                vals.pop(m)
        for m, v in vals.items():
            txt = f"{v:.1f}" if isinstance(v, float) else str(v)
            lines.append(f"\\expandafter\\def\\csname A-{k}-{m}\\endcsname{{{txt}}}\n")
        if strip_file:
            lines.append(f"% {k}: golden code in final design of {golden_designs}; passes only with it: {flipped}\n")

    names = list(counts)
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            pos, neg, p = sign_p(counts[x], counts[y])
            k = f"{a.suite}-{x}-vs-{y}"
            lines += [f"\\expandafter\\def\\csname A-{k}-better\\endcsname{{{pos}}}\n",
                      f"\\expandafter\\def\\csname A-{k}-worse\\endcsname{{{neg}}}\n",
                      f"\\expandafter\\def\\csname A-{k}-p\\endcsname{{{p:.2g}}}\n"]
    drop = [f"A-{a.suite}-", f"% {a.suite}-"]
    if a.grader_agree:
        agree = total = 0
        for f in a.grader_agree:
            c = json.loads(Path(f).read_text())["inloop_vs_heldout"]
            agree += c["both_pass"] + c["both_fail"]
            total += sum(c.values())
        lines += [f"\\expandafter\\def\\csname A-grader-agree\\endcsname{{{100 * agree / total:.1f}}}\n",
                  f"\\expandafter\\def\\csname A-grader-agree-count\\endcsname{{{agree}}}\n",
                  f"\\expandafter\\def\\csname A-grader-n\\endcsname{{{total}}}\n",
                  f"% grader-agree from {', '.join(a.grader_agree)}\n"]
        drop += ["A-grader-", "% grader-agree"]
    out = Path(a.out)
    prev = out.read_text() if out.exists() else ""
    keep = "".join(l for l in prev.splitlines(True) if not any(d in l for d in drop))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(keep + "".join(lines))
    print("".join(lines))


if __name__ == "__main__":
    main()

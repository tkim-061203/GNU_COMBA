#!/usr/bin/env python3
"""
parse_rtllm_trials.py — pass@5 breakdown from per-trial LangGraph reports.
===========================================================================
Reads the per-trial reports already written by benchmark_langgraph.py
(no GPU rerun needed):

    <root>/<design>/reports/report_langgraph*.trial_<N>.json

For each design it counts, over the N trials, how many were:
    - syntax-clean  (final_status in {pass, fail_ts})   → "syntax" pass
    - functional    (final_status == pass)              → "func" pass

and produces:
    - per-design table (c_syntax/N, c_func/N)
    - distribution: # designs at each level 5/5 .. 0/5 (syntax and func)
    - pass@5 recomputed with the exact paper formula
        pass@k = 1 - C(n-c, k) / C(n, k)      (k = n  →  pass iff c >= 1)
    - LaTeX table (tab:pass5_breakdown), JSON, console

Usage:
    python src/parse_rtllm_trials.py RTLLM/modules \
        --out-json reports/rtllm/pass5_breakdown.json \
        --out-tex  reports/rtllm/pass5_breakdown.tex --label tab:pass5_breakdown_rtllm
    python src/parse_rtllm_trials.py RTLLM_v2/modules \
        --out-json reports/rtllm_v2/pass5_breakdown.json \
        --out-tex  reports/rtllm_v2/pass5_breakdown.tex --label tab:pass5_breakdown_rtllm_v2
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

# final_status buckets ------------------------------------------------------
SYNTAX_CLEAN = {"pass", "fail_ts"}   # compiled OK (TB may still fail)
FUNC_PASS = {"pass"}                  # compiled OK AND testbench passed


def passk(n: int, c: int, k: int) -> float:
    """pass@k = 1 - C(n-c, k)/C(n, k). c = #correct trials out of n."""
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def trial_idx(path: Path) -> int:
    m = re.search(r"trial_(\d+)", path.name)
    return int(m.group(1)) if m else 0


def collect(root: Path):
    """design -> sorted list of final_status, one per trial."""
    designs = defaultdict(dict)  # design -> {trial_idx: status}
    for jf in root.rglob("report_langgraph*.trial_*.json"):
        try:
            s = json.loads(jf.read_text()).get("samples", {})
        except Exception as e:
            print(f"  [WARN] {jf}: {e}", file=sys.stderr)
            continue
        design = s.get("module_name") or jf.parts[-3]
        designs[design][trial_idx(jf)] = s.get("final_status", "error")
    return {d: [t[i] for i in sorted(t)] for d, t in designs.items()}


def main():
    ap = argparse.ArgumentParser(description="pass@5 breakdown from per-trial reports")
    ap.add_argument("root", help="modules root, e.g. RTLLM/modules")
    ap.add_argument("-k", type=int, default=None, help="k for pass@k (default: n = #trials)")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-tex", default=None)
    ap.add_argument("--label", default="tab:pass5_breakdown")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: {root} not found", file=sys.stderr)
        sys.exit(1)

    per_design = collect(root)
    if not per_design:
        print(f"ERROR: no trial reports under {root}", file=sys.stderr)
        sys.exit(1)

    n = max(len(v) for v in per_design.values())   # trials per design (e.g. 5)
    k = args.k or n

    rows = []
    syn_dist = defaultdict(int)   # c_syntax (0..n) -> #designs
    fun_dist = defaultdict(int)
    sum_syn_passk = sum_fun_passk = 0.0

    for design in sorted(per_design):
        statuses = per_design[design]
        ni = len(statuses)
        c_syn = sum(1 for st in statuses if st in SYNTAX_CLEAN)
        c_fun = sum(1 for st in statuses if st in FUNC_PASS)
        syn_dist[c_syn] += 1
        fun_dist[c_fun] += 1
        sum_syn_passk += passk(ni, c_syn, min(k, ni))
        sum_fun_passk += passk(ni, c_fun, min(k, ni))
        rows.append({"design": design, "trials": ni,
                     "c_syntax": c_syn, "c_func": c_fun,
                     "statuses": statuses})

    ndes = len(rows)
    syntax_passk = 100.0 * sum_syn_passk / ndes
    func_passk = 100.0 * sum_fun_passk / ndes

    # ── console ──
    print(f"Root: {root}   designs: {ndes}   trials/design: n={n}   k={k}\n")
    print(f"{'design':<22} {'syntax':>8} {'func':>8}")
    for r in rows:
        print(f"{r['design']:<22} {r['c_syntax']:>4}/{r['trials']:<3} "
              f"{r['c_func']:>4}/{r['trials']:<3}")
    print("\nDistribution (# designs at each level, c/n):")
    print(f"{'level':>6} | {'syntax':>7} | {'func':>7}")
    for c in range(n, -1, -1):
        print(f"{c}/{n:<4} | {syn_dist.get(c,0):>7} | {fun_dist.get(c,0):>7}")
    print(f"\npass@{k}  syntax = {syntax_passk:.1f}%   func = {func_passk:.1f}%")

    result = {
        "root": str(root), "designs": ndes, "n_trials": n, "k": k,
        "syntax_pass_at_k": round(syntax_passk, 2),
        "func_pass_at_k": round(func_passk, 2),
        "syntax_distribution": {f"{c}/{n}": syn_dist.get(c, 0) for c in range(n, -1, -1)},
        "func_distribution": {f"{c}/{n}": fun_dist.get(c, 0) for c in range(n, -1, -1)},
        "per_design": rows,
    }

    if args.out_json:
        p = Path(args.out_json); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2))
        print(f"\n[json] {p}")

    if args.out_tex:
        lines = [
            r"\begin{table}[t]", r"\centering",
            rf"\caption{{pass@{k} breakdown over {n} trials ({root.parts[0]}, {ndes} designs).}}",
            rf"\label{{{args.label}}}",
            r"\begin{tabular}{l" + "r" * (n + 1) + "}", r"\toprule",
            "Level (c/n) & " + " & ".join(f"{c}/{n}" for c in range(n, -1, -1)) + r" \\",
            r"\midrule",
            "Syntax-clean & " + " & ".join(str(syn_dist.get(c, 0)) for c in range(n, -1, -1)) + r" \\",
            "Functional & " + " & ".join(str(fun_dist.get(c, 0)) for c in range(n, -1, -1)) + r" \\",
            r"\midrule",
            rf"\multicolumn{{{n+2}}}{{l}}{{syntax pass@{k} = {syntax_passk:.1f}\%, "
            rf"functional pass@{k} = {func_passk:.1f}\%}} \\",
            r"\bottomrule", r"\end{tabular}", r"\end{table}",
        ]
        p = Path(args.out_tex); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n")
        print(f"[tex]  {p}")


if __name__ == "__main__":
    main()

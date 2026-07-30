#!/usr/bin/env python3
"""
compute_metrics.py — assemble the ablation comparison table (tab:ablation).
===========================================================================
Gathers the metrics already produced by the other scripts for each variant
(Full + #1/#2/#3) and emits one side-by-side table with deltas vs Full.

For each variant you pass a *report root*; the script auto-discovers (tolerant,
skips what's missing):

    <root>/**/pass5_breakdown.json        ← parse_rtllm_trials.py
            (classified RTLLM vs RTLLM_v2 by 'v2' in the path)
    <root>/**/analyze_syntax_rtllm.json   ← analyze_self_consistency.py
    <root>/**/benchmark*_5trials.json     ← benchmark_langgraph.py (fix-rate)
    <root>/**/veval_pass1.json            ← VerilogEval V2 pass@1 (optional)

VerilogEval pass@1 json schema (flexible) — a dict of regime → percent:
    {"zero_shot@T0": 61.5, "zero_shot@T0.8": 58.9,
     "one_shot@T0": 64.1, "one_shot@T0.8": 60.2}
(or wrapped under a top-level "regimes" key).

Usage:
    python src/compute_metrics.py \
        --full reports/base \
        --abl1 reports/abl1_no_cat \
        --abl2 reports/abl2_no_debugger \
        --abl3 reports/abl3_no_postproc \
        --out-tex reports/tables/ablation.tex --label tab:ablation \
        --out-json reports/tables/ablation.json --out-md reports/tables/ablation.md

Any variant may be omitted; columns appear only for variants you pass.
For the current repo state, `--full reports` reads the existing top-level files.
"""

import argparse
import json
from pathlib import Path

# ── Variant definitions (order = column order). key, header. ──
VARIANTS = [
    ("full", "Full"),
    ("abl1", "#1 no-cat"),
    ("abl2", "#2 no-debug"),
    ("abl3", "#3 no-postproc"),
    ("abl4", "#4 nodbg+nopost"),
]

# ── Metric rows: key, display label, where to read it, "higher is better". ──
# source = (file_kind, json_path_tuple)
ROWS = [
    ("rtllm_syntax",   "RTLLM syntax pass@5 (%)",      ("rtllm_pass5",   ("syntax_pass_at_k",)), True),
    ("rtllm_func",     "RTLLM func pass@5 (%)",        ("rtllm_pass5",   ("func_pass_at_k",)),   True),
    ("rtllm2_syntax",  "RTLLM_v2 syntax pass@5 (%)",   ("rtllm_v2_pass5",("syntax_pass_at_k",)), True),
    ("rtllm2_func",    "RTLLM_v2 func pass@5 (%)",     ("rtllm_v2_pass5",("func_pass_at_k",)),   True),
    ("ve_zs_t0",       "VEval pass@1 zero-shot T0 (%)",   ("veval", ("zero_shot@T0",)),   True),
    ("ve_zs_t08",      "VEval pass@1 zero-shot T0.8 (%)", ("veval", ("zero_shot@T0.8",)), True),
    ("ve_os_t0",       "VEval pass@1 one-shot T0 (%)",    ("veval", ("one_shot@T0",)),    True),
    ("ve_os_t08",      "VEval pass@1 one-shot T0.8 (%)",  ("veval", ("one_shot@T0.8",)),  True),
    # ── auxiliary (RTLLM fix-loop diagnostics) ──
    ("syntax_fr",      "RTLLM syntax fix-rate (%)",    ("fixrate", ("global", "syntax_fix_rate"), 100.0), True),
    ("func_fr",        "RTLLM func fix-rate (%)",      ("fixrate", ("global", "func_fix_rate"),   100.0), True),
    ("recovery",       "Debugger recovery-rate (%)",   ("sc", ("metrics", "recovery_rate_pct")), True),
    ("cost_mult",      "Avg SC cost multiplier (×)",   ("sc", ("metrics", "avg_cost_multiplier")), False),
]


def _first(root: Path, pattern: str, exclude: str | None = None, require: str | None = None):
    for p in sorted(root.rglob(pattern)):
        parts = str(p).lower()
        if exclude and exclude in parts:
            continue
        if require and require not in parts:
            continue
        return p
    return None


def _load(p: Path | None):
    if p is None:
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        print(f"  [WARN] {p}: {e}")
        return None


def discover(root: Path) -> dict:
    """Locate + load the four report kinds under a variant root."""
    files = {
        "rtllm_pass5":    _first(root, "pass5_breakdown.json", exclude="v2"),
        "rtllm_v2_pass5": _first(root, "pass5_breakdown.json", require="v2"),
        "sc":             _first(root, "analyze_syntax_rtllm.json", exclude="v2"),
        "fixrate":        _first(root, "benchmark*5trials.json", exclude="v2"),
        "veval":          _first(root, "veval_pass1.json"),
    }
    return {k: _load(v) for k, v in files.items()}


def dig(d: dict | None, path: tuple):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur if isinstance(cur, (int, float)) else None


def metric_value(loaded: dict, source) -> float | None:
    kind, path = source[0], source[1]
    scale = source[2] if len(source) > 2 else 1.0
    v = dig(loaded.get(kind), path)
    return None if v is None else round(v * scale, 2)


def fmt(v):
    return "—" if v is None else f"{v:.1f}"


def tex_escape(s: str) -> str:
    """Make a header/label safe for LaTeX text mode."""
    s = s.replace("×", r"$\times$")
    for ch in ("\\", "#", "_", "%", "&"):
        s = s.replace(ch, "\\" + ch) if ch != "\\" else s
    return s


def fmt_delta(v, base, higher_better):
    if v is None or base is None:
        return ""
    d = v - base
    if abs(d) < 0.05:
        return "(±0.0)"
    return f"({d:+.1f})"


def main():
    ap = argparse.ArgumentParser(description="Assemble the ablation table (tab:ablation)")
    ap.add_argument("--full", help="report root for the Full pipeline")
    ap.add_argument("--abl1", help="report root for #1 (no dataset categorization)")
    ap.add_argument("--abl2", help="report root for #2 (no Debugger SLM)")
    ap.add_argument("--abl3", help="report root for #3 (no Sanitizer + TED)")
    ap.add_argument("--abl4", help="report root for #4 (no Debugger + no Sanitizer + TED)")
    ap.add_argument("--out-tex", default=None)
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--label", default="tab:ablation")
    args = ap.parse_args()

    roots = {"full": args.full, "abl1": args.abl1, "abl2": args.abl2,
             "abl3": args.abl3, "abl4": args.abl4}
    present = [(k, h) for k, h in VARIANTS if roots.get(k)]
    if not present:
        ap.error("pass at least one variant root (--full / --abl1 / --abl2 / --abl3)")

    data = {k: discover(Path(roots[k])) for k, _ in present}

    # values[row_key][variant_key] = float | None
    values = {}
    for rk, label, source, hib in ROWS:
        values[rk] = {vk: metric_value(data[vk], source) for vk, _ in present}

    base_key = "full" if any(k == "full" for k, _ in present) else present[0][0]

    # ── console ──
    print(f"\nAblation metrics (base column: {base_key})\n")
    hdr = f"{'metric':<34}" + "".join(f"{h:>20}" for _, h in present)
    print(hdr)
    print("-" * len(hdr))
    for rk, label, source, hib in ROWS:
        if all(values[rk][vk] is None for vk, _ in present):
            continue
        line = f"{label:<34}"
        for vk, _ in present:
            v = values[rk][vk]
            cell = fmt(v)
            if vk != base_key:
                cell += " " + fmt_delta(v, values[rk][base_key], hib)
            line += f"{cell:>20}"
        print(line)

    # ── outputs ──
    result = {
        "base": base_key,
        "variants": {vk: roots[vk] for vk, _ in present},
        "metrics": {rk: values[rk] for rk, *_ in ROWS},
    }
    if args.out_json:
        p = Path(args.out_json); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2)); print(f"\n[json] {p}")

    if args.out_md:
        rows_md = ["| Metric | " + " | ".join(h for _, h in present) + " |",
                   "|" + "---|" * (len(present) + 1)]
        for rk, label, source, hib in ROWS:
            if all(values[rk][vk] is None for vk, _ in present):
                continue
            cells = []
            for vk, _ in present:
                v = values[rk][vk]
                c = fmt(v)
                if vk != base_key:
                    c += " " + fmt_delta(v, values[rk][base_key], hib)
                cells.append(c.strip())
            rows_md.append(f"| {label} | " + " | ".join(cells) + " |")
        p = Path(args.out_md); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(rows_md) + "\n"); print(f"[md]   {p}")

    if args.out_tex:
        ncol = len(present)
        lines = [
            r"\begin{table}[t]", r"\centering",
            r"\caption{Ablation: per-module contribution. $\Delta$ vs Full in parentheses.}",
            rf"\label{{{args.label}}}",
            r"\begin{tabular}{l" + "r" * ncol + "}", r"\toprule",
            "Metric & " + " & ".join(tex_escape(h) for _, h in present) + r" \\", r"\midrule",
        ]
        for rk, label, source, hib in ROWS:
            if all(values[rk][vk] is None for vk, _ in present):
                continue
            cells = []
            for vk, _ in present:
                v = values[rk][vk]
                c = fmt(v)
                if vk != base_key and v is not None and values[rk][base_key] is not None:
                    c += r" {\footnotesize " + fmt_delta(v, values[rk][base_key], hib) + "}"
                cells.append(c)
            lines.append(tex_escape(label) + " & " + " & ".join(cells) + r" \\")
        lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
        p = Path(args.out_tex); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n"); print(f"[tex]  {p}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Sinh bang tong hop tu CSV cua measure_cell_bloat.py (Buoc 3).

Chi tinh tren nhom "comparable" (functional PASS + ca hai ben tong hop OK,
xem cot comparable trong CSV). Xuat markdown va LaTeX (booktabs).
"""
import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict, Counter
from pathlib import Path

BENCHMARK_LABELS = {
    "rtllm": "RTLLM v1.1",
    "rtllm_v2": "RTLLM v2.0",
}

# Gom nhom cac loai cell RTLIL chi tiet (vd $mux/$pmux/$bmux) ve nhom lon de
# bang du lieu gon, so sanh duoc giua cac benchmark.
CELL_CATEGORIES = [
    ("FF", lambda t: "dff" in t),
    ("Latch", lambda t: "latch" in t),
    ("MUX", lambda t: any(t.startswith(p) for p in ("$mux", "$pmux", "$bmux", "$demux", "$bwmux", "$tribuf"))),
    ("ADD/SUB", lambda t: t.startswith("$add") or t.startswith("$sub")),
    ("MUL/DIV", lambda t: any(t.startswith(p) for p in ("$mul", "$div", "$mod", "$pow"))),
    ("XOR", lambda t: t.startswith("$xor") or t.startswith("$xnor")),
    ("AND/OR", lambda t: any(t.startswith(p) for p in ("$and", "$or", "$nand", "$nor"))),
    ("NOT/BUF", lambda t: t.startswith("$not") or t.startswith("$buf")),
    ("COMPARE", lambda t: any(t.startswith(p) for p in ("$eq", "$ne", "$lt", "$le", "$gt", "$ge"))),
    ("MEM", lambda t: t.startswith("$mem")),
]


def categorize_cell(cell_type: str) -> str:
    t = cell_type.lower()
    for name, pred in CELL_CATEGORIES:
        if pred(t):
            return name
    return "Other"


PYRANET_BUCKET_ORDER = ["0-5", "6-10", "11-15", "16+"]


def group_key_and_label(row):
    bm = row["benchmark"]
    if bm == "verilogeval":
        cfg = row["description_type"]
        return f"verilogeval/{cfg}", f"VerilogEval V2 ({cfg})"
    return bm, BENCHMARK_LABELS.get(bm, bm)


def geomean(values):
    if not values:
        return None
    logs = [math.log(v) for v in values if v > 0]
    if not logs:
        return None
    return math.exp(sum(logs) / len(logs))


def compute_group_stats(rows):
    comparable = [r for r in rows if r["comparable"] == "yes"]
    ratios = [(r["module_name"], float(r["cell_ratio"])) for r in comparable if r["cell_ratio"] != ""]
    ratio_vals = [v for _, v in ratios]

    n_le_1 = [m for m, v in ratios if v <= 1.0]
    gt15 = sorted([(m, v) for m, v in ratios if v > 1.5], key=lambda x: -x[1])
    gt20 = sorted([(m, v) for m, v in ratios if v > 2.0], key=lambda x: -x[1])

    n_latch = [r["module_name"] for r in comparable if r["gen_num_latch"] not in ("", "0")]

    gen_cells = [int(r["gen_total_cells"]) for r in comparable if r["gen_total_cells"] != ""]
    ref_cells = [int(r["ref_total_cells"]) for r in comparable if r["ref_total_cells"] != ""]

    # 1) Cell-type breakdown (% theo nhom, tren tong so cell cua ma sinh ra)
    cat_counts = defaultdict(int)
    for r in comparable:
        d = json.loads(r["gen_cells_by_type"]) if r["gen_cells_by_type"] else {}
        for ctype, n in d.items():
            cat_counts[categorize_cell(ctype)] += n
    cat_total = sum(cat_counts.values())
    cat_pct = {name: (100.0 * cat_counts.get(name, 0) / cat_total if cat_total else 0.0)
               for name, _ in CELL_CATEGORIES + [("Other", None)]}

    # 2) Phan bo bucket PyraNet (0-5/6-10/11-15/16+) cho ca gen va ref
    gen_bucket = Counter(r["gen_pyranet_bucket"] for r in comparable)
    ref_bucket = Counter(r["ref_pyranet_bucket"] for r in comparable)
    n_comp = len(comparable) or 1
    gen_bucket_pct = {b: 100.0 * gen_bucket.get(b, 0) / n_comp for b in PYRANET_BUCKET_ORDER}
    ref_bucket_pct = {b: 100.0 * ref_bucket.get(b, 0) / n_comp for b in PYRANET_BUCKET_ORDER}

    return {
        "n_total_rows": len(rows),
        "n_comparable": len(comparable),
        "median_ratio": statistics.median(ratio_vals) if ratio_vals else None,
        "geomean_ratio": geomean(ratio_vals),
        "n_le_1": len(n_le_1),
        "gt15": gt15,
        "gt20": gt20,
        "n_latch": len(n_latch),
        "latch_modules": n_latch,
        "median_gen_cells": statistics.median(gen_cells) if gen_cells else None,
        "mean_gen_cells": statistics.mean(gen_cells) if gen_cells else None,
        "median_ref_cells": statistics.median(ref_cells) if ref_cells else None,
        "mean_ref_cells": statistics.mean(ref_cells) if ref_cells else None,
        "cell_type_pct": cat_pct,
        "gen_bucket_pct": gen_bucket_pct,
        "ref_bucket_pct": ref_bucket_pct,
    }


def fmt(x, nd=3):
    if x is None:
        return "n/a"
    return f"{x:.{nd}f}"


def render_markdown(groups: dict) -> str:
    lines = []
    lines.append("# Bang tong hop cell-count bloat (chi nhom PASS + comparable)\n")
    lines.append("| Benchmark | N | Cell sinh (trung vi) | Cell tham chieu (trung vi) | Trung vi ratio | TB nhan ratio | ratio<=1.0 | ratio>1.5 | ratio>2.0 | Latch phat sinh |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key, (label, stats) in groups.items():
        lines.append(
            f"| {label} | {stats['n_comparable']} | {fmt(stats['median_gen_cells'], 1)} | "
            f"{fmt(stats['median_ref_cells'], 1)} | {fmt(stats['median_ratio'])} | "
            f"{fmt(stats['geomean_ratio'])} | {stats['n_le_1']} | {len(stats['gt15'])} | "
            f"{len(stats['gt20'])} | {stats['n_latch']} |"
        )
    lines.append("")

    cat_names = [name for name, _ in CELL_CATEGORIES] + ["Other"]
    lines.append("## Cell-type breakdown (% tren tong so cell cua ma sinh ra, nhom comparable)\n")
    lines.append("| Benchmark | " + " | ".join(cat_names) + " |")
    lines.append("|---|" + "|".join(["---:"] * len(cat_names)) + "|")
    for key, (label, stats) in groups.items():
        pct = stats["cell_type_pct"]
        lines.append(f"| {label} | " + " | ".join(f"{pct.get(c, 0.0):.1f}%" for c in cat_names) + " |")
    lines.append("")

    lines.append("## Phan bo bucket PyraNet (0-5/6-10/11-15/16+ cell), nhom comparable\n")
    lines.append("| Benchmark | gen 0-5 | gen 6-10 | gen 11-15 | gen 16+ | ref 0-5 | ref 6-10 | ref 11-15 | ref 16+ |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key, (label, stats) in groups.items():
        g, r = stats["gen_bucket_pct"], stats["ref_bucket_pct"]
        lines.append(
            f"| {label} | " + " | ".join(f"{g[b]:.0f}%" for b in PYRANET_BUCKET_ORDER) +
            " | " + " | ".join(f"{r[b]:.0f}%" for b in PYRANET_BUCKET_ORDER) + " |"
        )
    lines.append("")
    lines.append("*Tham khao: kich thuoc 4 tap train PyraNet (train_index2_*.npy): "
                  "0-5=198,241 mau; 6-10=85,033; 11-15=27,394-38,138; 16+=5,225 "
                  "(lech manh ve mach nho).*\n")

    for key, (label, stats) in groups.items():
        if not stats["gt15"] and not stats["n_latch"]:
            continue
        lines.append(f"## Chi tiet — {label}\n")
        if stats["gt15"]:
            lines.append("**Module co ratio > 1.5** (mac dinh gom ca > 2.0):")
            for m, v in stats["gt15"]:
                flag = " (>2.0)" if v > 2.0 else ""
                lines.append(f"- `{m}`: {v:.3f}x{flag}")
            lines.append("")
        if stats["latch_modules"]:
            lines.append("**Module phat sinh latch trong code sinh ra:**")
            for m in stats["latch_modules"]:
                lines.append(f"- `{m}`")
            lines.append("")
    return "\n".join(lines)


def render_latex(groups: dict) -> str:
    lines = []
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"    \centering")
    lines.append(r"    \caption{So sanh cell count giua ma sinh ra va golden RTL (nhom PASS, tong hop bang flow Muc 3.3.1).}")
    lines.append(r"    \label{tab:cell-bloat-summary}")
    lines.append(r"    \begin{tabular}{lrrrrrrrr}")
    lines.append(r"        \toprule")
    lines.append(r"        \textbf{Benchmark} & \textbf{N} & \textbf{Cell sinh} & \textbf{Cell tham chieu} & "
                 r"\textbf{Trung vi} & \textbf{TB nhan} & "
                 r"\textbf{$\leq$1.0} & \textbf{$>$1.5} & \textbf{$>$2.0} \\")
    lines.append(r"        \midrule")
    for key, (label, stats) in groups.items():
        lines.append(
            f"        {label} & {stats['n_comparable']} & {fmt(stats['median_gen_cells'], 1)} & "
            f"{fmt(stats['median_ref_cells'], 1)} & {fmt(stats['median_ratio'])} & "
            f"{fmt(stats['geomean_ratio'])} & {stats['n_le_1']} & {len(stats['gt15'])} & "
            f"{len(stats['gt20'])} \\\\"
        )
    lines.append(r"        \bottomrule")
    lines.append(r"    \end{tabular}")
    lines.append(r"\end{table}")

    cat_names = [name for name, _ in CELL_CATEGORIES] + ["Other"]
    lines.append("")
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"    \centering")
    lines.append(r"    \caption{Phan bo loai cell trong ma sinh ra (\% tren tong so cell, nhom comparable).}")
    lines.append(r"    \label{tab:cell-type-breakdown}")
    lines.append(r"    \begin{tabular}{l" + "r" * len(cat_names) + "}")
    lines.append(r"        \toprule")
    lines.append(r"        \textbf{Benchmark} & " + " & ".join(f"\\textbf{{{c}}}" for c in cat_names) + r" \\")
    lines.append(r"        \midrule")
    for key, (label, stats) in groups.items():
        pct = stats["cell_type_pct"]
        lines.append(f"        {label} & " + " & ".join(f"{pct.get(c, 0.0):.1f}\\%" for c in cat_names) + r" \\")
    lines.append(r"        \bottomrule")
    lines.append(r"    \end{tabular}")
    lines.append(r"\end{table}")

    lines.append("")
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"    \centering")
    lines.append(r"    \caption{Phan bo khoang cell PyraNet (0-5/6-10/11-15/16+) cua ma sinh ra va golden (nhom comparable).}")
    lines.append(r"    \label{tab:pyranet-bucket}")
    lines.append(r"    \begin{tabular}{lrrrrrrrr}")
    lines.append(r"        \toprule")
    lines.append(r"         & \multicolumn{4}{c}{\textbf{Ma sinh ra}} & \multicolumn{4}{c}{\textbf{Golden}} \\")
    lines.append(r"        \textbf{Benchmark} & 0-5 & 6-10 & 11-15 & 16+ & 0-5 & 6-10 & 11-15 & 16+ \\")
    lines.append(r"        \midrule")
    for key, (label, stats) in groups.items():
        g, r = stats["gen_bucket_pct"], stats["ref_bucket_pct"]
        lines.append(
            f"        {label} & " + " & ".join(f"{g[b]:.0f}\\%" for b in PYRANET_BUCKET_ORDER) +
            " & " + " & ".join(f"{r[b]:.0f}\\%" for b in PYRANET_BUCKET_ORDER) + r" \\"
        )
    lines.append(r"        \bottomrule")
    lines.append(r"    \end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--out-md", type=Path, default=Path("reports/cell_bloat_summary.md"))
    ap.add_argument("--out-tex", type=Path, default=Path("reports/cell_bloat_summary.tex"))
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv)))
    by_group = defaultdict(list)
    labels = {}
    for r in rows:
        key, label = group_key_and_label(r)
        by_group[key].append(r)
        labels[key] = label

    order = ["rtllm", "rtllm_v2"] + sorted(
        [k for k in by_group if k.startswith("verilogeval/")])
    groups = {k: (labels[k], compute_group_stats(by_group[k])) for k in order if k in by_group}

    md = render_markdown(groups)
    tex = render_latex(groups)
    args.out_md.write_text(md)
    args.out_tex.write_text(tex)
    print(md)
    print(f"\n[da ghi {args.out_md} va {args.out_tex}]", file=sys.stderr)


if __name__ == "__main__":
    main()

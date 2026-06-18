#!/usr/bin/env python3
"""
analyze_self_consistency.py — Compute Tier 2 ROI from self-consistency reports.

Reads per-module reports under <root>/modules/*/reports/*.json, extracts
samples.self_consistency, classifies each module into:

    Tier1_pass        — passed at sample 0 (no extra cost)
    Tier2_recovered   — sample 0 failed, sample N>0 passed (REAL BENEFIT)
    Tier2_partial     — all failed, but Tier 2 reduced error count
    Tier2_no_help     — all samples failed identically
    No_metadata       — self-consistency not run (legacy report)

Outputs:
    - Console table per category
    - JSON detail at analyze_self_consistency.json

Usage:
    python analyze_self_consistency.py [RTLLM/modules]
    python analyze_self_consistency.py [path] --threshold 5  # min err improvement for "partial"
"""

import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict


def find_reports(root: Path) -> list:
    """Find module-level reports (skip benchmark aggregates)."""
    rps = []
    for jf in root.rglob("report_langgraph*.json"):
        if "fixrate" in jf.parts or "benchmark" in jf.name.lower():
            continue
        rps.append(jf)
    return sorted(rps)


def classify(sc_meta: dict, partial_threshold: int = 5) -> tuple:
    """
    Returns (category, evidence_dict).
    sc_meta = report["samples"]["self_consistency"]
    """
    samples = sc_meta.get("all_samples", [])
    if not samples:
        return "No_metadata", {}

    best_idx = sc_meta.get("best_sample_idx", 0)
    best_status = sc_meta.get("best_status", "?")
    samples_run = sc_meta.get("samples_run", len(samples))

    sample_0 = samples[0] if samples else {}
    s0_status = sample_0.get("status", "?")

    ev = {
        "best_idx": best_idx,
        "best_status": best_status,
        "samples_run": samples_run,
        "s0_status": s0_status,
        "s0_tb_err": sample_0.get("tb_err", 0),
        "s0_sc_err": sample_0.get("sc_err", 0),
    }

    # Case 1: sample 0 already passed → Tier 2 didn't run (or short-circuited)
    if s0_status == "pass":
        return "Tier1_pass", ev

    # Case 2: best is from Tier 2, status passed → real recovery
    if best_status == "pass" and best_idx > 0:
        ev["recovery_from_idx"] = best_idx
        ev["wasted_samples"] = best_idx  # samples before the winner
        return "Tier2_recovered", ev

    # Case 3: all failed — check if errs improved
    best_sample = samples[best_idx] if best_idx < len(samples) else samples[-1]
    best_errs = best_sample.get("tb_err", 0) + best_sample.get("sc_err", 0)
    s0_errs = sample_0.get("tb_err", 0) + sample_0.get("sc_err", 0)
    err_delta = s0_errs - best_errs

    ev["err_delta"] = err_delta
    if err_delta >= partial_threshold:
        return "Tier2_partial", ev
    return "Tier2_no_help", ev


def cost_overhead(samples_run: int, max_samples: int) -> float:
    """Wall-time multiplier vs Tier 1 only."""
    return samples_run  # 1 sample = 1×, 5 samples = 5×


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="RTLLM/modules",
                    help="Root containing modules/*/reports/")
    ap.add_argument("--threshold", type=int, default=5,
                    help="Min err count reduction for 'partial' (default: 5)")
    ap.add_argument("--out", default="analyze_self_consistency.json")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: {root} not found", file=sys.stderr)
        sys.exit(1)

    reports = find_reports(root)
    print(f"Scanning {len(reports)} reports under {root}\n")

    by_cat = defaultdict(list)
    by_module = defaultdict(lambda: defaultdict(int))
    cost_samples = []

    for rp in reports:
        try:
            data = json.loads(rp.read_text())
        except Exception as e:
            print(f"  [WARN] {rp}: {e}", file=sys.stderr)
            continue

        samples = data.get("samples")
        if isinstance(samples, list):
            sample = samples[0] if samples else {}
        else:
            sample = samples or {}

        sc = sample.get("self_consistency", {})
        mod = data.get("module_name", rp.parent.parent.name)

        cat, ev = classify(sc, partial_threshold=args.threshold)
        by_cat[cat].append((mod, rp.name, ev))
        by_module[mod][cat] += 1

        if "samples_run" in ev:
            cost_samples.append(ev["samples_run"])

    # ── Summary table ──
    print("=" * 78)
    print(f"{'CATEGORY':<22} {'COUNT':>8} {'PCT':>8}")
    print("=" * 78)
    total = sum(len(v) for v in by_cat.values())
    for cat in ("Tier1_pass", "Tier2_recovered", "Tier2_partial",
                "Tier2_no_help", "No_metadata"):
        n = len(by_cat[cat])
        pct = 100 * n / total if total else 0
        print(f"{cat:<22} {n:>8} {pct:>7.1f}%")
    print("-" * 78)
    print(f"{'TOTAL':<22} {total:>8}")
    print()

    # ── Cost summary ──
    if cost_samples:
        avg = sum(cost_samples) / len(cost_samples)
        print(f"  Avg cost multiplier: {avg:.2f}× (samples per module)")
        print(f"  Min: {min(cost_samples)}×  Max: {max(cost_samples)}×")
        print()

    # ── ROI summary ──
    tier1 = len(by_cat["Tier1_pass"])
    recov = len(by_cat["Tier2_recovered"])
    if total:
        recovery_rate = 100 * recov / total
        gross_pass = 100 * (tier1 + recov) / total
        baseline_pass = 100 * tier1 / total
        uplift = gross_pass - baseline_pass
        print(f"  Baseline pass rate (Tier 1 only): {baseline_pass:.1f}%")
        print(f"  With self-consistency:            {gross_pass:.1f}%")
        print(f"  Uplift from Tier 2:               +{uplift:.1f}pp")
        print(f"  Recovery rate:                    {recovery_rate:.1f}% of all modules")
        print()

    # ── Detail: Tier2_recovered ──
    if by_cat["Tier2_recovered"]:
        print("=" * 78)
        print("Tier2_recovered — modules saved by retry (first 15)")
        print("=" * 78)
        print(f"  {'MODULE':<28} {'WIN_IDX':>8} {'SAMPLES_RUN':>12}")
        print("  " + "-" * 60)
        for mod, fn, ev in by_cat["Tier2_recovered"][:15]:
            print(f"  {mod:<28} {ev.get('recovery_from_idx',0):>8} "
                  f"{ev.get('samples_run',0):>12}")
        print()

    # ── Detail: Tier2_no_help (worst case for SC) ──
    if by_cat["Tier2_no_help"]:
        print("=" * 78)
        print("Tier2_no_help — wasted retries (first 10)")
        print("=" * 78)
        print(f"  {'MODULE':<28} {'STATUS':<14} {'SAMPLES':>8} {'ERR_DELTA':>10}")
        print("  " + "-" * 60)
        for mod, fn, ev in by_cat["Tier2_no_help"][:10]:
            print(f"  {mod:<28} {ev.get('best_status','?'):<14} "
                  f"{ev.get('samples_run',0):>8} {ev.get('err_delta',0):>10}")
        print()

    # ── Save JSON detail ──
    out = Path(args.out)
    summary = {
        "root": str(root),
        "totals": {cat: len(items) for cat, items in by_cat.items()},
        "metrics": {
            "baseline_pass_pct": round(100 * tier1 / total, 2) if total else 0,
            "with_sc_pass_pct": round(100 * (tier1 + recov) / total, 2) if total else 0,
            "recovery_rate_pct": round(100 * recov / total, 2) if total else 0,
            "avg_cost_multiplier": round(sum(cost_samples) / len(cost_samples), 2) if cost_samples else 0,
        },
        "details": {
            cat: [{"module": m, "report": fn, **ev}
                  for m, fn, ev in by_cat[cat]]
            for cat in by_cat
        },
    }
    out.write_text(json.dumps(summary, indent=2))
    print(f"→ Full report: {out.resolve()}")


if __name__ == "__main__":
    main()
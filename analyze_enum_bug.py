#!/usr/bin/env python3
"""
analyze_enum_bug.py — Find modules where generator misuses enum/parameter values.

Detects 3 categories:
  ENUM_INDEX_BUG     : GVD compares against sequential indices (6'b000000, 6'b000001...)
                       while XML defines explicit values (6'b100000 = ADD).
  ENUM_VALUE_MISMATCH: GVD uses values not present in XML enum_map at all.
  ENUM_OK            : All GVD comparison values are subset of XML enum values.
  NO_ENUM            : XML has no <enum> / <parameter value=...>; skip.

Usage:
    python analyze_enum_bug.py [RTLLM/modules]
    python analyze_enum_bug.py --json report.json    # single file
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict


# ─── XML enum/parameter value extractors ───
RE_ENUM_VALUE   = re.compile(r"<enum\s+id=\"(\w+)\"\s+value=\"([^\"]+)\"", re.I)
RE_PARAM_VALUE  = re.compile(r"<parameter\s+(?:id|name)=\"(\w+)\"\s+value=\"([^\"]+)\"", re.I)
# inline form: parameter ADD = 6'b100000;
RE_INLINE_PARAM = re.compile(r"parameter\s+(\w+)\s*=\s*([0-9]+'[bBhHdD][0-9a-fA-F_]+)", re.I)

# ─── GVD comparison value extractor ───
# matches: ALUC == 6'b100000  /  alu_op == 4'h5  /  state == 2'd3
RE_GVD_COMP = re.compile(
    r"(\w+)\s*==\s*([0-9]+'[bBhHdD][0-9a-fA-F_]+)",
    re.I,
)


def normalize_literal(lit: str) -> str:
    """Normalize Verilog literal to canonical decimal form for comparison."""
    m = re.match(r"(\d+)'([bBhHdD])([0-9a-fA-F_]+)", lit)
    if not m:
        return lit.lower()
    width, base, digits = int(m.group(1)), m.group(2).lower(), m.group(3).replace("_", "")
    try:
        if base == 'b':
            val = int(digits, 2)
        elif base == 'h':
            val = int(digits, 16)
        elif base == 'd':
            val = int(digits, 10)
        else:
            return lit.lower()
        return f"{width}'d{val}"
    except ValueError:
        return lit.lower()


def extract_xml_enum_map(xml_text: str) -> dict:
    """Returns {NAME: normalized_value}."""
    if not xml_text:
        return {}
    m = {}
    for name, val in RE_ENUM_VALUE.findall(xml_text):
        m[name] = normalize_literal(val)
    for name, val in RE_PARAM_VALUE.findall(xml_text):
        if name not in m:
            m[name] = normalize_literal(val)
    # inline parameter declarations inside <description>
    for name, val in RE_INLINE_PARAM.findall(xml_text):
        if name not in m:
            m[name] = normalize_literal(val)
    return m


def extract_gvd_comparisons(gvd: str) -> list:
    """Returns [(signal, normalized_value), ...]."""
    if not gvd:
        return []
    return [(sig, normalize_literal(val)) for sig, val in RE_GVD_COMP.findall(gvd)]


def is_sequential_pattern(values: list) -> bool:
    """True if values look like 0,1,2,3... (sequential indices)."""
    if len(values) < 3:
        return False
    nums = []
    for v in values:
        m = re.match(r"\d+'d(\d+)", v)
        if not m:
            return False
        nums.append(int(m.group(1)))
    nums = sorted(set(nums))
    return nums == list(range(nums[0], nums[0] + len(nums))) and nums[0] <= 2


def classify_module(report: dict) -> tuple:
    """Returns (category, evidence_dict)."""
    samples = report.get("samples", {})
    gvd = samples.get("gvd", "")
    xml = samples.get("xml_description", "")
    status = samples.get("final_status", "?")

    enum_map = extract_xml_enum_map(xml)
    if not enum_map:
        return "NO_ENUM", {"final_status": status}

    comparisons = extract_gvd_comparisons(gvd)
    if not comparisons:
        return "NO_COMPARISONS", {"final_status": status, "enum_count": len(enum_map)}

    expected_vals = set(enum_map.values())
    comp_vals = [v for _, v in comparisons]
    comp_vals_set = set(comp_vals)

    overlap = comp_vals_set & expected_vals
    missing = comp_vals_set - expected_vals

    evidence = {
        "final_status": status,
        "enum_count": len(enum_map),
        "comp_count": len(comp_vals_set),
        "overlap": len(overlap),
        "missing": sorted(missing)[:5],
        "expected_sample": sorted(expected_vals)[:5],
    }

    # Pure subset → OK
    if not missing:
        return "ENUM_OK", evidence

    # Sequential pattern in missing? → INDEX BUG
    if is_sequential_pattern(list(missing)) and len(overlap) == 0:
        return "ENUM_INDEX_BUG", evidence

    # Mixed or random → MISMATCH
    return "ENUM_VALUE_MISMATCH", evidence


def find_reports(root: Path) -> list:
    """Find all *.json report files under RTLLM/modules/*/reports/."""
    reports = []
    for jf in root.rglob("report_langgraph*.json"):
        # skip aggregated benchmark reports
        if "fixrate" in jf.parts or "benchmark" in jf.name.lower():
            continue
        reports.append(jf)
    return sorted(reports)


def main():
    if "--json" in sys.argv:
        # single-file mode
        idx = sys.argv.index("--json")
        path = Path(sys.argv[idx + 1])
        report = json.loads(path.read_text())
        cat, ev = classify_module(report)
        print(f"{path.name}: {cat}")
        print(json.dumps(ev, indent=2))
        return

    root = Path(sys.argv[1] if len(sys.argv) > 1 else "RTLLM/modules")
    if not root.is_dir():
        print(f"ERROR: {root} not found", file=sys.stderr)
        sys.exit(1)

    reports = find_reports(root)
    print(f"Scanning {len(reports)} reports under {root}\n")

    by_category = defaultdict(list)
    by_module = defaultdict(lambda: defaultdict(int))

    for rp in reports:
        try:
            report = json.loads(rp.read_text())
        except Exception as e:
            print(f"  [WARN] {rp}: {e}", file=sys.stderr)
            continue

        mod = report.get("module_name", rp.parent.parent.name)
        cat, ev = classify_module(report)
        by_category[cat].append((mod, rp.name, ev))
        by_module[mod][cat] += 1

    # ── Summary table ──
    print("=" * 78)
    print(f"{'CATEGORY':<22} {'COUNT':>8}")
    print("=" * 78)
    for cat in ("ENUM_INDEX_BUG", "ENUM_VALUE_MISMATCH", "ENUM_OK",
                "NO_COMPARISONS", "NO_ENUM"):
        print(f"{cat:<22} {len(by_category[cat]):>8}")
    print()

    # ── Suspect modules (any trial with bug) ──
    suspect_mods = sorted({
        m for m, cats in by_module.items()
        if cats.get("ENUM_INDEX_BUG", 0) > 0 or cats.get("ENUM_VALUE_MISMATCH", 0) > 0
    })

    if suspect_mods:
        print("=" * 78)
        print("SUSPECT MODULES (≥1 trial flagged)")
        print("=" * 78)
        print(f"{'MODULE':<28} {'INDEX_BUG':>10} {'MISMATCH':>10} {'OK':>6} {'TOTAL':>6}")
        print("-" * 78)
        for mod in suspect_mods:
            c = by_module[mod]
            total = sum(c.values())
            print(f"{mod:<28} {c.get('ENUM_INDEX_BUG',0):>10} "
                  f"{c.get('ENUM_VALUE_MISMATCH',0):>10} "
                  f"{c.get('ENUM_OK',0):>6} {total:>6}")
        print()

    # ── Detail for INDEX_BUG ──
    if by_category["ENUM_INDEX_BUG"]:
        print("=" * 78)
        print("ENUM_INDEX_BUG — DETAIL (first 10)")
        print("=" * 78)
        for mod, fn, ev in by_category["ENUM_INDEX_BUG"][:10]:
            print(f"\n  {mod}/{fn}  status={ev['final_status']}")
            print(f"    expected: {ev['expected_sample']}")
            print(f"    found:    {ev['missing']}")

    # ── Detail for VALUE_MISMATCH ──
    if by_category["ENUM_VALUE_MISMATCH"]:
        print("\n" + "=" * 78)
        print("ENUM_VALUE_MISMATCH — DETAIL (first 10)")
        print("=" * 78)
        for mod, fn, ev in by_category["ENUM_VALUE_MISMATCH"][:10]:
            print(f"\n  {mod}/{fn}  status={ev['final_status']} "
                  f"overlap={ev['overlap']}/{ev['comp_count']}")
            print(f"    expected sample: {ev['expected_sample']}")
            print(f"    not in spec:     {ev['missing']}")

    # ── Save full report ──
    out = Path("analyze_enum_bug.json")
    summary = {
        "totals": {cat: len(items) for cat, items in by_category.items()},
        "suspect_modules": {m: dict(by_module[m]) for m in suspect_mods},
        "details": {
            cat: [{"module": m, "report": fn, **ev}
                  for m, fn, ev in by_category[cat]]
            for cat in ("ENUM_INDEX_BUG", "ENUM_VALUE_MISMATCH")
        },
    }
    out.write_text(json.dumps(summary, indent=2))
    print(f"\n→ Full report: {out.resolve()}")


if __name__ == "__main__":
    main()
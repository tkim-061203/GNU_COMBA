#!/usr/bin/env python3
"""heldout_grade.py - re-grade final designs against the OFFICIAL testbench.

Why
---
The in-loop status (`final_status`) of a run is only a held-out score if the
loop never saw the official testbench or reference RTL. This script grades the
final `gvd` of every trial report in a fresh directory, using the official
benchmark directory, through the exact same `COMBANodes.node_tb_sim` code path
the pipeline uses. It never modifies the run reports.

Two uses:
  1. Oracle-free runs (in-loop TB generated from the spec): the held-out status
     is the real score; in-loop vs held-out gives the generated-TB judge quality.
  2. Legacy runs (golden TB + verified_*.v visible to the loop): with
     --strip-golden-helpers, modules copied verbatim from verified_*.v are
     removed before grading, which measures how much of the score came from
     reference-RTL injection by the Sanitizer's helper-append.

Usage
-----
  COMBA_TS_SIMULATOR=verilator python src/heldout_grade.py \
      --runs reports/abl1_full/rtllm_v2/modules --official RTLLM_v2/modules \
      --out-json reports/abl1_full/rtllm_v2/heldout.json --jobs 8 [--strip-golden-helpers]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from math import comb
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "langgraph_core"))

TB_NAMES = ("tb.cpp", "testbench.sv", "testbench.v", "tb.sv", "tb.v")


# ---------------------------------------------------------------- helpers
def _strip_comments(code: str) -> str:
    code = re.sub(r"//.*", "", code)
    return re.sub(r"/\*.*?\*/", "", code, flags=re.S)


def module_blocks(code: str) -> dict[str, str]:
    """name -> whitespace-normalised `module ... endmodule` text."""
    out = {}
    for m in re.finditer(r"\bmodule\s+(\w+)\b.*?\bendmodule\b", _strip_comments(code), flags=re.S):
        out[m.group(1)] = re.sub(r"\s+", " ", m.group(0)).strip()
    return out


def golden_modules(official_dir: str) -> dict[str, str]:
    gold = {}
    for vf in glob.glob(os.path.join(official_dir, "verified_*.v")):
        gold.update(module_blocks(Path(vf).read_text(errors="ignore")))
    return gold


def strip_golden(gvd: str, gold: dict[str, str]) -> tuple[str, list[str]]:
    """Remove every module whose normalised text equals a reference module."""
    removed = []
    code = _strip_comments(gvd)
    for m in list(re.finditer(r"\bmodule\s+(\w+)\b.*?\bendmodule\b", code, flags=re.S)):
        name, body = m.group(1), re.sub(r"\s+", " ", m.group(0)).strip()
        if gold.get(name) == body:
            removed.append(name)
    if not removed:
        return gvd, []
    for name in removed:
        code = re.sub(r"\bmodule\s+" + re.escape(name) + r"\b.*?\bendmodule\b", "", code, count=1, flags=re.S)
    return code.strip() + "\n", removed


def has_golden_tb(official_dir: str, bid: str) -> bool:
    names = list(TB_NAMES) + [f"{bid}_test.sv"]
    return any(os.path.isfile(os.path.join(official_dir, n)) for n in names)


def passk(n: int, c: int, k: int) -> float:
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def trial_idx(p: str) -> int:
    m = re.search(r"trial_(\d+)", os.path.basename(p))
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------- grading
def grade_one(job: dict) -> dict:
    """Grade one (design, trial) in an isolated temp dir. Never raises."""
    from comba_pipeline import COMBANodes, make_initial_state  # heavy import, per worker

    design, official, gvd = job["design"], job["official"], job["gvd"]
    rec = {k: job[k] for k in ("design", "trial", "inloop_status")}
    rec["stripped"] = []
    if job["strip"] and gvd:
        gvd, rec["stripped"] = strip_golden(gvd, golden_modules(official))
    if not has_golden_tb(official, design):
        rec["heldout_status"] = "no_golden"
        return rec
    if not gvd or not gvd.strip():
        rec["heldout_status"] = "fail_compile"
        rec["note"] = "empty gvd"
        return rec

    work = tempfile.mkdtemp(prefix=f"heldout_{design}_t{job['trial']}_")
    try:
        state = make_initial_state(nl_input="", module_name=design, benchmark_id=design, work_dir=work)
        state.update(gvd=gvd, dataset_dir=official, work_dir=work, ts_trial=0, total_iter=0)
        nodes = COMBANodes(llm=None)  # llm is only touched when no golden TB exists
        res = nodes.node_tb_sim(state)
        fail = (res.get("tb_failure") or "")
        if res.get("final_status") == "pass":
            rec["heldout_status"] = "pass"
        elif "compil" in fail.lower() or "binary missing" in fail.lower():
            rec["heldout_status"] = "fail_compile"
        else:
            rec["heldout_status"] = "fail_ts"
        rec["note"] = fail[:160]
    except Exception as e:  # infrastructure error: keep it visible, never silent
        rec["heldout_status"] = "error"
        rec["note"] = f"{type(e).__name__}: {e}"[:200]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return rec


def collect_jobs(runs: str, official_root: str, strip: bool, designs=None) -> list[dict]:
    jobs = []
    for design_dir in sorted(p for p in Path(runs).iterdir() if p.is_dir()):
        design = design_dir.name
        if designs and design not in designs:
            continue
        for rp in sorted(glob.glob(str(design_dir / "reports" / "report_langgraph*.trial_*.json")), key=trial_idx):
            try:
                s = json.loads(Path(rp).read_text()).get("samples", {})
            except Exception as e:
                print(f"[WARN] unreadable {rp}: {e}", file=sys.stderr)
                continue
            jobs.append({
                "design": design, "trial": trial_idx(rp), "official": os.path.join(official_root, design),
                "gvd": s.get("gvd") or "", "inloop_status": s.get("final_status", "error"), "strip": strip,
            })
    return jobs


def summarise(recs: list[dict]) -> dict:
    by = {}
    for r in recs:
        by.setdefault(r["design"], []).append(r)
    per_design, p1, p5 = [], 0.0, 0.0
    for d in sorted(by):
        rs = sorted(by[d], key=lambda r: r["trial"])
        n = len(rs)
        c = sum(r["heldout_status"] == "pass" for r in rs)
        c_in = sum(r["inloop_status"] == "pass" for r in rs)
        p1 += c / n
        p5 += passk(n, c, min(5, n))
        per_design.append({"design": d, "trials": n, "c_heldout": c, "c_inloop": c_in,
                           "heldout": [r["heldout_status"] for r in rs],
                           "inloop": [r["inloop_status"] for r in rs],
                           "stripped": sorted({m for r in rs for m in r["stripped"]})})
    nd = len(per_design)
    conf = Counter((r["inloop_status"] == "pass", r["heldout_status"] == "pass") for r in recs)
    return {
        "designs": nd,
        "trials_total": len(recs),
        "heldout_pass_at_1": round(100 * p1 / nd, 2) if nd else None,
        "heldout_pass_at_5": round(100 * p5 / nd, 2) if nd else None,
        "status_counts": dict(Counter(r["heldout_status"] for r in recs)),
        "inloop_vs_heldout": {  # judge agreement; FA = in-loop pass but held-out fail
            "both_pass": conf[(True, True)], "false_accept": conf[(True, False)],
            "false_reject": conf[(False, True)], "both_fail": conf[(False, False)],
        },
        "designs_with_stripped_golden": [p["design"] for p in per_design if p["stripped"]],
        "per_design": per_design,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", required=True, help="modules root holding <design>/reports/*.trial_N.json")
    ap.add_argument("--official", required=True, help="official benchmark modules root (with TB)")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--strip-golden-helpers", action="store_true")
    ap.add_argument("--designs", nargs="*", default=None, help="restrict to these designs")
    a = ap.parse_args()

    jobs = collect_jobs(a.runs, a.official, a.strip_golden_helpers, a.designs)
    if not jobs:
        sys.exit(f"no trial reports under {a.runs}")
    with Pool(a.jobs) as pool:
        recs = pool.map(grade_one, jobs, chunksize=1)
    out = summarise(recs)
    out.update(runs=a.runs, official=a.official, strip_golden_helpers=a.strip_golden_helpers,
               simulator=os.environ.get("COMBA_TS_SIMULATOR", "auto"))
    Path(a.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out_json).write_text(json.dumps(out, indent=2))
    print(f"{a.runs}: held-out pass@1={out['heldout_pass_at_1']} pass@5={out['heldout_pass_at_5']} "
          f"agreement={out['inloop_vs_heldout']} stripped={out['designs_with_stripped_golden']}")


if __name__ == "__main__":
    main()

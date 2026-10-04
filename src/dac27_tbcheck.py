#!/usr/bin/env python3
"""dac27_tbcheck.py - grade the generated testbenches of an F2 arm against the
REFERENCE design, after the run.

In the loop, a generated testbench is mutation-graded against the first
candidate it accepts, which may itself be wrong. Here every cached testbench
(<arm>/gentb_cache/gen_tb_<task>_s<seed>.sv) is run once more, against the
benchmark's reference RTL, which the loop never saw:

  accepts_ref    the TB passes the correct design (False = it would reject a
                 right answer; the judge is unsound on this task)
  mutation_score fraction of single-bug mutants of the reference it rejects
                 (how much it can detect), same operators as tb_validate

This is analysis only: nothing here feeds back into a run.

  python src/dac27_tbcheck.py reports/dac27/full/F2/rl2 --official RTLLM_v2/modules --jobs 8
  python src/dac27_tbcheck.py reports/dac27/full/F2/ve \\
      --official ext/verilog-eval/dataset_code-complete-iccad2023 --jobs 8
Writes <arm>/tbcheck.json.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "langgraph_core"))

SEED_BASE = 42          # COMBA_LLM_SEED in run_dac27.sh
SEED_STEP = 10_000      # benchmark_langgraph offset per trial


def _strip_comments(code: str) -> str:
    code = re.sub(r"//.*", "", code)
    return re.sub(r"/\*.*?\*/", "", code, flags=re.S)


def top_module(code: str, prefer: str) -> str | None:
    """Module nobody else instantiates; `prefer` wins when it qualifies."""
    clean = _strip_comments(code)
    names = re.findall(r"\bmodule\s+(\w+)", clean)
    if not names:
        return None
    used = set()
    for m in re.finditer(r"\bmodule\s+(\w+)\b(.*?)\bendmodule\b", clean, flags=re.S):
        for other in names:
            if other != m.group(1) and re.search(r"\b" + re.escape(other) + r"\b\s*(#\s*\(.*?\)\s*)?\w+\s*\(", m.group(2), flags=re.S):
                used.add(other)
    tops = [n for n in names if n not in used]
    if prefer in tops:
        return prefer
    return tops[0] if tops else names[0]


def reference_for(official: Path, task: str, suite: str) -> tuple[str | None, str]:
    """(reference code renamed so its top is TopModule, note)."""
    if suite == "ve":
        cands = sorted(official.glob(f"{task}_ref.sv"))
        if not cands:
            return None, "no _ref.sv"
        code = cands[0].read_text(errors="ignore")
        top = "RefModule" if re.search(r"\bmodule\s+RefModule\b", code) else top_module(code, task)
    else:
        files = sorted((official / task).glob("verified_*.v"))
        if not files:
            return None, "no verified_*.v"
        exact = [f for f in files if f.name == f"verified_{task}.v"]
        code = "\n".join(f.read_text(errors="ignore") for f in (exact or files))
        top = top_module(code, task)
    if not top:
        return None, "no module in reference"
    return re.sub(r"\bmodule\s+" + re.escape(top) + r"\b", "module TopModule", code, count=1), f"top={top}"


def check_one(job: dict) -> dict:
    from tb_validate import validate_tb
    rec = {k: job[k] for k in ("task", "trial", "tb")}
    ref, note = reference_for(Path(job["official"]), job["task"], job["suite"])
    rec["ref_note"] = note
    if ref is None:
        rec["status"] = "no_reference"
        return rec
    v = validate_tb(Path(job["tb"]).read_text(errors="ignore"), ref, max_mutants=job["max_mutants"])
    rec.update(status="ok", accepts_ref=v["dut_status"] == "pass", ref_run=v["dut_status"],
               mutation_score=v["mutation_score"], tier_vs_ref=v["tier"],
               mutants_killed=v["mutants_killed"], mutants_survived=v["mutants_survived"],
               mutants_excluded=v["mutants_excluded"])
    loop = Path(job["tb"] + ".validation.json")
    if loop.is_file():
        try:
            lv = json.loads(loop.read_text())
            rec["tier_in_loop"], rec["score_in_loop"] = lv.get("tier"), lv.get("mutation_score")
        except Exception:
            rec["tier_in_loop"] = "error"
    else:
        rec["tier_in_loop"] = "never_graded"
    return rec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("arm", help="reports/dac27/<model>/F2/<suite>")
    ap.add_argument("--official", required=True, help="RTLLM modules root, or the VE dataset dir")
    ap.add_argument("--suite", choices=["rl1", "rl2", "ve"], default=None, help="default: arm dir name")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--max-mutants", type=int, default=20)
    a = ap.parse_args()
    arm = Path(a.arm)
    suite = a.suite or arm.name
    jobs = []
    for tb in sorted(glob.glob(str(arm / "gentb_cache" / "gen_tb_*.sv"))):
        m = re.match(r"gen_tb_(.+)_s(\d+)\.sv$", os.path.basename(tb))
        if not m:
            continue
        seed = int(m.group(2))
        trial = (seed - SEED_BASE) // SEED_STEP if (seed - SEED_BASE) % SEED_STEP == 0 else None
        jobs.append({"task": m.group(1), "trial": trial, "tb": tb, "official": a.official,
                     "suite": suite, "max_mutants": a.max_mutants})
    if not jobs:
        sys.exit(f"no generated testbenches under {arm}/gentb_cache")
    with Pool(a.jobs) as pool:
        recs = pool.map(check_one, jobs, chunksize=1)
    ok = [r for r in recs if r["status"] == "ok"]
    acc = [r for r in ok if r["accepts_ref"]]
    scores = [r["mutation_score"] for r in acc if r["mutation_score"] is not None]
    by_tier = {}
    for t in sorted({r["tier_in_loop"] for r in ok}):
        rs = [r for r in ok if r["tier_in_loop"] == t]
        sc = [r["mutation_score"] for r in rs if r.get("accepts_ref") and r["mutation_score"] is not None]
        by_tier[t] = {"tbs": len(rs), "accepts_ref": sum(r["accepts_ref"] for r in rs),
                      "mean_ref_mutation_score": round(sum(sc) / len(sc), 4) if sc else None}
    out = {
        "arm": str(arm), "suite": suite, "official": a.official,
        "tbs": len(recs), "graded": len(ok),
        "accepts_ref": len(acc),
        "accepts_ref_pct": round(100 * len(acc) / len(ok), 2) if ok else None,
        "mean_ref_mutation_score": round(sum(scores) / len(scores), 4) if scores else None,
        "ref_run_counts": dict(Counter(r.get("ref_run", r["status"]) for r in recs)),
        "by_in_loop_tier": by_tier,
        "per_tb": recs,
    }
    (arm / "tbcheck.json").write_text(json.dumps(out, indent=2))
    print(f"{arm}: {len(ok)}/{len(recs)} TBs graded, accept the reference {out['accepts_ref_pct']}%, "
          f"mean mutation score vs reference {out['mean_ref_mutation_score']}")


if __name__ == "__main__":
    main()

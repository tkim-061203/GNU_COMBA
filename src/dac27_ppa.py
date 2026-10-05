#!/usr/bin/env python3
"""dac27_ppa.py - hardware cost of the final designs that pass held-out.

Answers "is the code correct AND reasonable hardware?" for each run_dac27.sh
arm. Every final design that passes the official testbench is synthesised
with Yosys and compared with the benchmark's reference RTL on the same task:

  default      technology-independent proxy: `synth -flatten; abc -g cmos2;
               stat -tech cmos` gives a transistor estimate for the logic;
               flip-flops are counted separately and charged FF_T transistors
               each (stat leaves them out). cost = transistors + FF_T * FFs
  --liberty L  also map to a standard-cell library and read the cell area
               (`dfflibmap; abc -liberty; stat -liberty`), e.g. Nangate45

Per (arm, task): median cost over the passing trials / reference cost.
Per arm: geometric mean of that ratio over tasks. Per model pair at the same
feedback and suite: paired geometric-mean ratio over tasks both models pass,
with a 95% task bootstrap CI. Lower is smaller hardware. Analysis only.

  python src/dac27_ppa.py reports/dac27 --out reports/dac27_results --jobs 16 \\
      [--feedback F0 F3] [--liberty /path/NangateOpenCellLibrary_typical.lib]
Writes <out>/ppa.csv, <out>/ppa_tasks.csv, <out>/ppa.tex (\\RC{ppa-...} macros).
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dac27_analyze import B, SEED, load_rtllm, load_ve   # noqa: E402

FF_T = 24          # transistors charged per flip-flop (static master-slave DFF)
TIMEOUT = 180
OFFICIAL = {"rl1": "RTLLM/modules", "rl2": "RTLLM_v2/modules",
            "ve": "ext/verilog-eval/dataset_code-complete-iccad2023"}
# yosys < 0.5x prints "  $_DFF_P_   10"; newer (0.63 on the server) prints "  10   $_DFF_P_"
_FF = r"\$_(?:S?DFFS?R?E?|ALDFFE?|DFFSRE|DLATCH|SR)_\w*"
FF_RE = re.compile(rf"^\s+(?:{_FF}\s+(\d+)|(\d+)\s+{_FF})\s*$", re.M)
CELLS_RE = re.compile(r"Number of cells:\s+(\d+)|^\s+(\d+)\s+cells\s*$", re.M)


def synth(code: str, liberty: str | None) -> dict:
    with tempfile.TemporaryDirectory(prefix="ppa_") as td:
        f = Path(td) / "d.sv"
        f.write_text(code)
        stat = Path(td) / "stat.txt"
        script = (f"read_verilog -sv {f}; synth -flatten -auto-top; abc -g cmos2; "
                  f"tee -q -o {stat} stat -tech cmos")
        out = {}
        try:
            p = subprocess.run(["yosys", "-q", "-p", script], capture_output=True, text=True, timeout=TIMEOUT)
        except FileNotFoundError:
            return {"error": "yosys not on PATH"}
        except subprocess.TimeoutExpired:
            return {"error": "timeout"}
        if p.returncode != 0:
            return {"error": ((p.stdout + p.stderr).strip().splitlines() or ["yosys failed"])[-1][:200]}
        s = stat.read_text() if stat.is_file() else ""
        m = CELLS_RE.search(s)
        t = re.search(r"Estimated number of transistors:\s+(\d+)", s)
        ffs = sum(int(a or b) for a, b in FF_RE.findall(s))
        if not m and not t:
            return {"error": "no stat"}
        # yosys 0.63 omits the cells line for a design with no cells (constant outputs):
        # that is 0 cells, not a failure; ratios skip zero values downstream.
        out.update(cells=int(m.group(1) or m.group(2)) if m else 0, transistors=int(t.group(1)) if t else 0, ffs=ffs)
        out["cost"] = out["transistors"] + FF_T * ffs
        if liberty:
            stat2 = Path(td) / "lib.txt"
            script = (f"read_verilog -sv {f}; synth -flatten -auto-top; dfflibmap -liberty {liberty}; "
                      f"abc -liberty {liberty}; opt_clean; tee -q -o {stat2} stat -liberty {liberty}")
            try:
                subprocess.run(["yosys", "-q", "-p", script], capture_output=True, text=True, timeout=TIMEOUT)
                a = re.search(r"Chip area for (?:top )?module .*?:\s+([\d.]+)", stat2.read_text() if stat2.is_file() else "")
                out["area"] = float(a.group(1)) if a else None
            except subprocess.TimeoutExpired:
                out["area"] = None
        return out


def _job(args):
    key, code, liberty = args
    return key, synth(code, liberty)


def reference_code(official: Path, task: str, suite: str) -> str | None:
    if suite == "ve":
        fs = sorted(official.glob(f"{task}_ref.sv"))
    else:
        fs = sorted((official / task).glob("verified_*.v"))
        exact = [f for f in fs if f.name == f"verified_{task}.v"]
        fs = exact or fs
    return "\n".join(f.read_text(errors="ignore") for f in fs) if fs else None


def final_code(row, arm: Path, suite: str, task: str) -> str:
    s = row[1] or {}
    code = s.get("gvd") or ""
    if not code and suite == "ve":
        cands = glob.glob(str(arm / "ve_build" / ".build_sample_*" / "samples" / task / f"sample_{row[0]:02d}.sv"))
        code = Path(cands[0]).read_text(errors="ignore") if cands else ""
    return code


def gmean_ratio(x: np.ndarray) -> float:
    return float(np.exp(np.mean(np.log(x))))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="reports/dac27")
    ap.add_argument("--out", required=True)
    ap.add_argument("--feedback", nargs="*", default=None, help="default: every feedback present")
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--liberty", default=None)
    ap.add_argument("--jobs", type=int, default=8)
    for s, d in OFFICIAL.items():
        ap.add_argument(f"--official-{s}", default=d)
    a = ap.parse_args()
    root, out = Path(a.root), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    official = {s: Path(getattr(a, f"official_{s}")) for s in OFFICIAL}

    # collect passing final designs and references
    arms, todo = {}, {}
    for arm in sorted(root.glob("*/*/*")):
        model, fb, suite = arm.parts[-3:]
        if suite not in OFFICIAL or (a.feedback and fb not in a.feedback) or (a.models and model not in a.models):
            continue
        r = load_ve(arm) if suite == "ve" else load_rtllm(arm)
        if not r or not r.get("runs"):
            continue
        per = {}
        for task, rows in r["runs"].items():
            for row in rows:
                if not row[3]:
                    continue
                code = final_code(row, arm, suite, task)
                if code.strip():
                    h = hashlib.sha1(code.encode()).hexdigest()
                    todo[h] = code
                    per.setdefault(task, []).append(h)
        arms[(model, fb, suite)] = per
    refs = {}
    for (_, _, suite), per in arms.items():
        for task in per:
            if (suite, task) not in refs:
                code = reference_code(official[suite], task, suite)
                if code:
                    h = hashlib.sha1(code.encode()).hexdigest()
                    todo[h] = code
                    refs[(suite, task)] = h
    print(f"{len(arms)} arms, {len(todo)} distinct designs to synthesise")
    with Pool(a.jobs) as pool:
        res = dict(pool.map(_job, [(h, c, a.liberty) for h, c in todo.items()], chunksize=1))

    metric = "area" if a.liberty else "cost"
    ratios, task_rows, arm_rows, tex = {}, [], [], ["% generated by src/dac27_ppa.py - do not edit\n"]
    for (model, fb, suite), per in sorted(arms.items()):
        rr = {}
        for task, hs in per.items():
            ref = res.get(refs.get((suite, task), ""), {})
            vals = [res[h].get(metric) for h in hs if res.get(h, {}).get(metric)]
            rv = ref.get(metric)
            if vals and rv:
                rr[task] = float(np.median(vals)) / rv
            task_rows.append({"model": model, "feedback": fb, "suite": suite, "task": task, "passing": len(hs),
                              "synth_ok": len(vals), "median_" + metric: float(np.median(vals)) if vals else None,
                              "ref_" + metric: rv, "ratio": rr.get(task),
                              "errors": ";".join(sorted({res[h].get("error", "") for h in hs if res.get(h, {}).get("error")}))})
        ratios[(model, fb, suite)] = rr
        gm = gmean_ratio(np.array(list(rr.values()))) if rr else None
        arm_rows.append({"model": model, "feedback": fb, "suite": suite, "tasks_passing": len(per),
                         "tasks_compared": len(rr), "gmean_ratio_vs_ref": gm, "metric": metric})
        if gm is not None:
            key = f"ppa-{model}-{fb}-{suite}"
            tex.append(f"\\expandafter\\def\\csname R-{key}-gm\\endcsname{{{gm:.2f}}}\n")
            tex.append(f"\\expandafter\\def\\csname R-{key}-n\\endcsname{{{len(rr)}}}\n")
    pairs = []
    for (ma, mb) in (("full", "base"), ("full", "gen"), ("gen", "base"), ("full", "scale")):
        for (m, fb, suite), rr in ratios.items():
            if m != ma or (mb, fb, suite) not in ratios:
                continue
            ob = ratios[(mb, fb, suite)]
            common = sorted(set(rr) & set(ob))
            if len(common) < 3:
                continue
            d = np.log(np.array([rr[t] for t in common])) - np.log(np.array([ob[t] for t in common]))
            rng = np.random.default_rng(SEED)
            boot = d[rng.integers(0, len(d), size=(B, len(d)))].mean(axis=1)
            pct = lambda v: 100 * (np.exp(v) - 1)
            p = {"name": f"ppa-{ma}-vs-{mb}-{fb}-{suite}", "tasks": len(common), "diff_pct": pct(d.mean()),
                 "lo": pct(np.percentile(boot, 2.5)), "hi": pct(np.percentile(boot, 97.5)),
                 "a_smaller": int((d < 0).sum()), "b_smaller": int((d > 0).sum())}
            pairs.append(p)
            tex.append(f"\\expandafter\\def\\csname R-{p['name']}-diff\\endcsname{{{p['diff_pct']:.1f}}}\n")
            tex.append(f"\\expandafter\\def\\csname R-{p['name']}-ci\\endcsname{{[{p['lo']:.1f}, {p['hi']:.1f}]}}\n")
            tex.append(f"\\expandafter\\def\\csname R-{p['name']}-n\\endcsname{{{p['tasks']}}}\n")
    for name, rows in (("ppa.csv", arm_rows), ("ppa_tasks.csv", task_rows), ("ppa_pairs.csv", pairs)):
        if rows:
            with open(out / name, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
    (out / "ppa.tex").write_text("".join(tex))
    errs = sum(1 for v in res.values() if v.get("error"))
    print(f"synthesised {len(res)} designs ({errs} failed); {len(pairs)} paired comparisons -> {out}")


if __name__ == "__main__":
    main()

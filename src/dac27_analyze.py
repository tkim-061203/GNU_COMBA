#!/usr/bin/env python3
"""dac27_analyze.py - turn run_dac27.sh outputs into paper numbers.

Reads   <root>/<model>/<feedback>/<suite>/heldout.json          (RTLLM v1/v2)
        <root>/<model>/<feedback>/ve/ve_build/.build_sample_e0_t0/samples (VE)
Writes  <out>/numbers.tex   LaTeX macros  \\R{model}{fb}{suite}{metric}
        <out>/arms.csv      one row per arm
        <out>/paired.csv    paired contrasts (same tasks, two arms)
        <out>/contam.csv    model gap on leaked vs clean tasks (needs --leaked-json)

Statistics (all over TASKS, the unit that is sampled from the benchmark):
  pass@1   mean over tasks of c/n (unbiased for n trials)
  CI       95% percentile bootstrap over tasks, B=10000, fixed seed
  paired   mean per-task difference with paired bootstrap CI, plus an exact
           two-sided sign test over tasks whose c differs
  contam   per-task gap d = p1(A) - p1(B) between two models at the same
           feedback, split into leaked and clean tasks. Comparing the gap, not
           the raw score, holds task difficulty fixed within each subset, and
           contamination both models share (the common pretrained base)
           cancels. Reports the gap on each subset, their difference with a
           stratified bootstrap CI, and a label-permutation p-value.
Nothing is printed into the paper that is not computed here.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
from math import comb
from pathlib import Path

import numpy as np

B, SEED = 10_000, 0
SUITES = ("rl1", "rl2", "ve")


# ------------------------------------------------------------------ loading
def load_rtllm(arm: Path) -> dict | None:
    f = arm / "heldout.json"
    if not f.is_file():
        return None
    d = json.loads(f.read_text())
    tasks = {p["design"]: (p["c_heldout"], p["trials"]) for p in d["per_design"]}
    agree = d.get("inloop_vs_heldout", {})
    return {"tasks": tasks, "agree": agree, "cost": load_cost(arm)}


def load_ve(arm: Path) -> dict | None:
    """VE: held-out = official final check log; in-loop = sample json status."""
    roots = glob.glob(str(arm / "ve_build" / ".build_sample_*" / "samples"))
    if not roots:
        return None
    tasks, agree = {}, {"both_pass": 0, "false_accept": 0, "false_reject": 0, "both_fail": 0}
    iters = []
    canon = {}   # official per-problem counts from sv-iv-analyze, used when present
    for sc in glob.glob(str(arm / "ve_reports" / "*" / "summary.csv")):
        for row in csv.reader(open(sc)):
            if row and row[0].startswith("Prob"):
                canon[row[0]] = (int(row[2]), int(row[1]))
    for prob_dir in sorted(Path(roots[0]).iterdir()):
        c = n = 0
        for sj in sorted(prob_dir.glob("sample_*.json")):
            log = Path(str(sj)[:-5] + "-sv-iv-test.log")
            held = log.is_file() and _ve_log_pass(log.read_text(errors="ignore"))
            try:
                st = json.loads(sj.read_text())
            except Exception:
                st = {}
            inl = st.get("final_status") == "pass"
            iters.append(st.get("total_iter", 0) or 0)
            agree[{(True, True): "both_pass", (True, False): "false_accept",
                   (False, True): "false_reject", (False, False): "both_fail"}[(inl, held)]] += 1
            c += held
            n += 1
        if n:
            tasks[prob_dir.name] = (c, n)
    if canon:   # the official analyzer is the score; the log regex only feeds agreement
        tasks = canon
    return {"tasks": tasks, "agree": agree, "cost": {"mean_total_iter": float(np.mean(iters)) if iters else None}}


def _ve_log_pass(log: str) -> bool:
    # VerilogEval testbenches print "Mismatches: 0 in N samples" on success.
    m = re.search(r"Mismatches:\s*(\d+)\s+in\s+\d+\s+samples", log)
    return bool(m) and int(m.group(1)) == 0


def load_cost(arm: Path) -> dict:
    it, el, ns = [], [], []
    for rp in glob.glob(str(arm / "RTLLM_*" / "modules" / "*" / "reports" / "*.trial_*.json")):
        try:
            s = json.loads(Path(rp).read_text())["samples"]
        except Exception:
            continue
        it.append(s.get("total_iter", 0) or 0)
        sc = s.get("self_consistency") or {}
        if sc.get("total_elapsed_s") is not None:
            el.append(sc["total_elapsed_s"])
        if sc.get("samples_run") is not None:
            ns.append(sc["samples_run"])
    f = lambda v: float(np.mean(v)) if v else None
    return {"mean_total_iter": f(it), "mean_elapsed_s": f(el), "mean_samples_run": f(ns)}


def tb_tiers(arm: Path) -> dict:
    """Tier per generated TB. A TB with no validation file never accepted any
    candidate, so it could not be mutation-graded ('never_graded')."""
    tbs = glob.glob(str(arm / "gentb_cache" / "gen_tb_*.sv"))
    tiers = {"never_graded": sum(not Path(t + ".validation.json").is_file() for t in tbs)} if tbs else {}
    for vf in glob.glob(str(arm / "gentb_cache" / "*.validation.json")):
        try:
            t = json.loads(Path(vf).read_text()).get("tier", "error")
        except Exception:
            t = "error"
        tiers[t] = tiers.get(t, 0) + 1
    return tiers


# ------------------------------------------------------------------ stats
def passk(n: int, c: int, k: int) -> float:
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def boot_ci(x: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    idx = rng.integers(0, len(x), size=(B, len(x)))
    m = x[idx].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def sign_test(diff: np.ndarray) -> float:
    pos, neg = int((diff > 0).sum()), int((diff < 0).sum())
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    p = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def arm_stats(r: dict, subset: set | None = None) -> dict:
    items = [(t, c, n) for t, (c, n) in r["tasks"].items() if subset is None or t in subset]
    if not items:
        return {}
    p1 = np.array([c / n for _, c, n in items])
    rng = np.random.default_rng(SEED)
    lo, hi = boot_ci(p1, rng)
    out = {"tasks": len(items), "p1": 100 * p1.mean(), "p1_lo": 100 * lo, "p1_hi": 100 * hi,
           "solved_any": sum(c > 0 for _, c, _ in items), "solved_all": sum(c == n for _, c, n in items)}
    if all(n >= 5 for _, _, n in items):
        out["p5"] = 100 * np.mean([passk(n, c, 5) for _, c, n in items])
    return out


def paired(ra: dict, rb: dict) -> dict:
    common = sorted(set(ra["tasks"]) & set(rb["tasks"]))
    a = np.array([ra["tasks"][t][0] / ra["tasks"][t][1] for t in common])
    b = np.array([rb["tasks"][t][0] / rb["tasks"][t][1] for t in common])
    d = a - b
    lo, hi = boot_ci(d, np.random.default_rng(SEED))
    return {"tasks": len(common), "diff": 100 * d.mean(), "lo": 100 * lo, "hi": 100 * hi,
            "a_better": int((d > 0).sum()), "b_better": int((d < 0).sum()), "p_sign": sign_test(d)}


def contam(ra: dict, rb: dict, leak: set) -> dict | None:
    common = sorted(set(ra["tasks"]) & set(rb["tasks"]))
    d = np.array([ra["tasks"][t][0] / ra["tasks"][t][1] - rb["tasks"][t][0] / rb["tasks"][t][1] for t in common])
    is_l = np.array([t in leak for t in common])
    dl, dc = d[is_l], d[~is_l]
    if len(dl) == 0 or len(dc) == 0:
        return None
    rng = np.random.default_rng(SEED)
    ml = dl[rng.integers(0, len(dl), size=(B, len(dl)))].mean(axis=1)
    mc = dc[rng.integers(0, len(dc), size=(B, len(dc)))].mean(axis=1)
    did = ml - mc
    obs = dl.mean() - dc.mean()
    perm = np.argsort(rng.random((B, len(d))), axis=1)[:, :len(dl)]   # random leaked-label sets
    pl = d[perm].mean(axis=1)
    pc = (d.sum() - d[perm].sum(axis=1)) / len(dc)
    p_perm = (int((np.abs(pl - pc) >= abs(obs) - 1e-12).sum()) + 1) / (B + 1)
    pct = lambda x: (100 * float(np.percentile(x, 2.5)), 100 * float(np.percentile(x, 97.5)))
    return {"n_leak": len(dl), "n_clean": len(dc),
            "leak": 100 * dl.mean(), "leak_ci": pct(ml), "clean": 100 * dc.mean(), "clean_ci": pct(mc),
            "did": 100 * obs, "did_ci": pct(did), "p_perm": p_perm}


# ------------------------------------------------------------------ output
def fmt(v, nd=1):
    return "--" if v is None else f"{v:.{nd}f}"


def macro(key: str, val: str) -> str:
    return f"\\expandafter\\def\\csname R-{key}\\endcsname{{{val}}}\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="reports/dac27")
    ap.add_argument("--out", required=True)
    ap.add_argument("--leaked-json", default=None, help='{"rl1": [...], "rl2": [...], "ve": [...]}')
    a = ap.parse_args()
    root, out = Path(a.root), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    leaked = json.loads(Path(a.leaked_json).read_text()) if a.leaked_json else {}

    arms = {}
    for arm in sorted(root.glob("*/*/*")):
        model, fb, suite = arm.parts[-3:]
        if suite not in SUITES:
            continue
        r = load_ve(arm) if suite == "ve" else load_rtllm(arm)
        if r:
            arms[(model, fb, suite)] = r

    tex, rows = ["% generated by src/dac27_analyze.py - do not edit\n"], []
    for (model, fb, suite), r in sorted(arms.items()):
        s = arm_stats(r)
        key = f"{model}-{fb}-{suite}"
        ag = r["agree"]
        inl = ag.get("both_pass", 0) + ag.get("false_accept", 0)
        fa = 100 * ag.get("false_accept", 0) / inl if inl else None
        tiers = tb_tiers(r.get("_arm", Path(root, model, fb, suite)))
        sv = int(tiers.get("self_validated", 0))
        ntb = sum(tiers.values())
        row = {"model": model, "feedback": fb, "suite": suite, **{k: s.get(k) for k in
               ("tasks", "p1", "p1_lo", "p1_hi", "p5", "solved_any", "solved_all")},
               "false_accept_pct": fa, "tb_self_validated_pct": (100 * sv / ntb) if ntb else None,
               **{f"cost_{k}": v for k, v in r["cost"].items()}}
        if suite in leaked:
            sc = arm_stats(r, set(r["tasks"]) - set(leaked[suite]))
            row["p1_clean"], row["tasks_clean"] = sc.get("p1"), sc.get("tasks")
        rows.append(row)
        for m, v, nd in (("p1", s.get("p1"), 1), ("p1lo", s.get("p1_lo"), 1), ("p1hi", s.get("p1_hi"), 1),
                         ("p5", s.get("p5"), 1), ("fa", fa, 1), ("tbsv", row["tb_self_validated_pct"], 0),
                         ("p1clean", row.get("p1_clean"), 1), ("iter", r["cost"].get("mean_total_iter"), 1)):
            if v is not None:
                tex.append(macro(f"{key}-{m}", fmt(v, nd)))

    # contrasts the paper reads: model effect at fixed feedback, feedback effect at fixed model
    pairs = []
    models = sorted({k[0] for k in arms}); fbs = sorted({k[1] for k in arms})
    for suite in SUITES:
        for fb in fbs:
            for ma, mb in (("full", "base"), ("full", "gen"), ("gen", "base"), ("single", "full")):
                if (ma, fb, suite) in arms and (mb, fb, suite) in arms:
                    pairs.append((f"{ma}-vs-{mb}-{fb}-{suite}", paired(arms[(ma, fb, suite)], arms[(mb, fb, suite)])))
        for m in models:
            for fa_, fb_ in (("F3", "F2"), ("F2", "F1"), ("F1", "F0")):
                if (m, fa_, suite) in arms and (m, fb_, suite) in arms:
                    pairs.append((f"{m}-{fa_}-vs-{fb_}-{suite}", paired(arms[(m, fa_, suite)], arms[(m, fb_, suite)])))
    for name, p in pairs:
        tex.append(macro(f"{name}-diff", fmt(p["diff"])))
        tex.append(macro(f"{name}-ci", f"[{fmt(p['lo'])}, {fmt(p['hi'])}]"))
        tex.append(macro(f"{name}-p", f"{p['p_sign']:.2g}"))

    # contamination: does the fine-tuned model gain more on tasks its corpus contains?
    cont = []
    for suite in SUITES:
        if suite not in leaked:
            continue
        leak = set(leaked[suite])
        seen = {t for (m, f, s_), r in arms.items() if s_ == suite for t in r["tasks"]}
        missing = sorted(leak - seen)
        if seen and missing:
            print(f"warning: {len(missing)} leaked {suite} names not in any arm, e.g. {missing[:3]}")
        for fb in fbs:
            for ma, mb in (("full", "base"), ("gen", "base")):
                if (ma, fb, suite) in arms and (mb, fb, suite) in arms:
                    c = contam(arms[(ma, fb, suite)], arms[(mb, fb, suite)], leak)
                    if c:
                        cont.append((f"contam-{ma}-vs-{mb}-{fb}-{suite}", c))
    for name, c in cont:
        for m in ("leak", "clean", "did"):
            tex.append(macro(f"{name}-{m}", fmt(c[m])))
            tex.append(macro(f"{name}-{m}ci", f"[{fmt(c[m + '_ci'][0])}, {fmt(c[m + '_ci'][1])}]"))
        tex.append(macro(f"{name}-p", f"{c['p_perm']:.2g}"))
        tex.append(macro(f"{name}-nleak", str(c["n_leak"])))
        tex.append(macro(f"{name}-nclean", str(c["n_clean"])))

    (out / "numbers.tex").write_text("".join(tex))
    with open(out / "arms.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader(); w.writerows(rows)
    with open(out / "paired.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["contrast", "tasks", "diff", "lo", "hi", "a_better", "b_better", "p_sign"])
        for name, p in pairs:
            w.writerow([name, p["tasks"], fmt(p["diff"]), fmt(p["lo"]), fmt(p["hi"]), p["a_better"], p["b_better"], f"{p['p_sign']:.3g}"])
    if cont:
        with open(out / "contam.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["contrast", "n_leak", "n_clean", "gap_leak", "leak_lo", "leak_hi",
                        "gap_clean", "clean_lo", "clean_hi", "did", "did_lo", "did_hi", "p_perm"])
            for name, c in cont:
                w.writerow([name, c["n_leak"], c["n_clean"], fmt(c["leak"]), fmt(c["leak_ci"][0]), fmt(c["leak_ci"][1]),
                            fmt(c["clean"]), fmt(c["clean_ci"][0]), fmt(c["clean_ci"][1]),
                            fmt(c["did"]), fmt(c["did_ci"][0]), fmt(c["did_ci"][1]), f"{c['p_perm']:.3g}"])
    print(f"{len(arms)} arms, {len(pairs)} contrasts, {len(cont)} contamination contrasts -> {out}")


if __name__ == "__main__":
    main()

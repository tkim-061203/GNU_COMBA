#!/usr/bin/env python3
"""dac27_armcheck.py - health check of one finished DAC27 arm.

Run by utils/dac27_watcher.sh whenever an arm gets DONE (and once for every
DONE arm that has no armcheck.json yet). Read-only except for writing
<arm>/armcheck.json. Each check is OK / WARN / FAIL:

  provenance   served vLLM checkpoints == expected ones for the model tag
  elapsed      arm wall time recorded and not implausibly short
  bigfiles     no file > 100 MB inside the arm (runaway sim log, etc.)
  log          phase-log section of this arm: vLLM context-length 400s,
               Python tracebacks, "vLLM did not come up"
  RTLLM:  designs   blind modules count (rl1 29, rl2 50)
          trials    one report per (design, trial), expected count per design
          heldout   heldout.json complete, no `error` status, rl1 graded with
                    fixed TB seeds, held-out pass@1 > 0
          inloop    in-loop error/timeout share
          gentb     F2: generated testbenches cached
  VE:     problems  156 rows in summary.csv, 156 sample dirs
          passrate  > 0
          samples   share of sample_01.json with final_status error/timeout

  python utils/dac27_armcheck.py reports/dac27/base/F2/ve      # prints one line, exit 0/1/2
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_DESIGNS = {"rl1": 29, "rl2": 50}
VE_PROBLEMS = 156
BIG = 100 * 1024 * 1024


def trials_for(fb: str) -> int:
    return {"F0": 1, "F0s": int(os.environ.get("TRIALS_F0S", "10"))}.get(fb, int(os.environ.get("TRIALS", "5")))


class Report:
    def __init__(self):
        self.items = []

    def add(self, name, level, msg):
        self.items.append({"check": name, "level": level, "msg": msg})

    @property
    def level(self):
        lv = [i["level"] for i in self.items]
        return "FAIL" if "FAIL" in lv else "WARN" if "WARN" in lv else "OK"


def served_root(line: str) -> str | None:
    m = re.search(r'"root":"([^"]*)"', line)
    return m.group(1).rstrip("/") if m else None


def check_provenance(arm: Path, r: Report):
    p = arm / "provenance.txt"
    if not p.is_file():
        return r.add("provenance", "FAIL", "provenance.txt missing")
    kv = {}
    for line in p.read_text(errors="ignore").splitlines():
        k, _, v = line.partition(":")
        kv.setdefault(k.strip(), v.strip())
    bad = []
    for role in ("gen", "dbg"):
        exp = (kv.get(f"expected_{role}") or "").rstrip("/")
        got = served_root(kv.get(f"served_{role}", ""))
        if not exp or got != exp:
            bad.append(f"{role}: expected {exp or '?'} served {got or 'nothing'}")
    r.add("provenance", "FAIL" if bad else "OK", "; ".join(bad) or "served checkpoints match")
    el = kv.get("elapsed_s")
    if el is None or not el.isdigit():
        r.add("elapsed", "WARN", "elapsed_s missing")
    else:
        s = int(el)
        r.add("elapsed", "WARN" if s < 60 else "OK", f"{s / 3600:.2f} h")


def check_bigfiles(arm: Path, r: Report):
    big = []
    for dp, _, fs in os.walk(arm):
        for f in fs:
            fp = os.path.join(dp, f)
            try:
                if os.path.getsize(fp) > BIG:
                    big.append(f"{os.path.relpath(fp, arm)} ({os.path.getsize(fp) >> 20} MB)")
            except OSError:
                pass
    r.add("bigfiles", "WARN" if big else "OK", "; ".join(big[:5]) or "none > 100 MB")


def arm_log_section(model: str, fb: str, suite: str) -> str | None:
    """Text of this arm's last section in any phase log."""
    head = re.compile(r"^=+ (\S+) / (\S+) / (\S+) +\(")
    best = None
    for lf in sorted(glob.glob(str(ROOT / "reports" / "dac27*.log")) + glob.glob(str(ROOT / "reports" / "dac27" / "*.log")),
                     key=os.path.getmtime):
        cur, buf = None, []
        try:
            fh = open(lf, errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                m = head.match(line)
                if m:
                    if cur == (model, fb, suite):
                        best = "".join(buf)
                    cur, buf = m.groups(), []
                elif cur == (model, fb, suite) and len(buf) < 2_000_000:
                    buf.append(line[:2000])
        if cur == (model, fb, suite):
            best = "".join(buf)
    return best


def check_log(model, fb, suite, r: Report):
    sec = arm_log_section(model, fb, suite)
    if sec is None:
        return r.add("log", "WARN", "no section for this arm in reports/dac27*.log")
    ctx = sec.count("maximum context length")
    tb = sec.count("Traceback (most recent call last)")
    vllm = sec.count("vLLM did not come up")
    pool = sec.count("[pool] no result")
    msgs, lvl = [], "OK"
    if vllm:
        lvl = "FAIL"; msgs.append(f"vLLM did not come up x{vllm}")
    if ctx:
        lvl = "WARN" if lvl == "OK" else lvl; msgs.append(f"vLLM context-length 400 x{ctx}")
    if tb:
        lvl = "WARN" if lvl == "OK" else lvl; msgs.append(f"Python traceback x{tb}")
    if pool:
        lvl = "WARN" if lvl == "OK" else lvl; msgs.append(f"pool stall (worker died) x{pool}")
    r.add("log", lvl, "; ".join(msgs) or "clean")


def check_rtllm(arm: Path, fb: str, suite: str, r: Report):
    mods = sorted(glob.glob(str(arm / "RTLLM_*" / "modules")))
    if not mods:
        return r.add("designs", "FAIL", "no RTLLM_*/modules")
    designs = sorted(d for d in Path(mods[0]).iterdir() if d.is_dir())
    exp_d = EXPECTED_DESIGNS[suite]
    r.add("designs", "OK" if len(designs) == exp_d else "FAIL", f"{len(designs)}/{exp_d}")

    exp_t = trials_for(fb)
    reps = {d.name: glob.glob(str(d / "reports" / "report_langgraph*.trial_*.json")) for d in designs}
    stems = Counter(re.sub(r"\.trial_\d+\.json$", "", os.path.basename(p)) for ps in reps.values() for p in ps)
    stem = stems.most_common(1)[0][0] if stems else None
    short = {}
    for d, ps in reps.items():
        n = len({re.search(r"trial_(\d+)", p).group(1) for p in ps if stem and os.path.basename(p).startswith(stem + ".")})
        if n != exp_t:
            short[d] = n
    r.add("trials", "FAIL" if short else "OK",
          f"designs with != {exp_t} trials: {dict(list(short.items())[:8])}" if short else f"{exp_t} trials x {len(designs)} designs")

    hp = arm / "heldout.json"
    if not hp.is_file():
        r.add("heldout", "FAIL", "heldout.json missing")
    else:
        h = json.loads(hp.read_text())
        msgs, lvl = [], "OK"
        if h.get("trials_total") != exp_d * exp_t:
            lvl = "FAIL"; msgs.append(f"trials_total {h.get('trials_total')} != {exp_d * exp_t}")
        sc = h.get("status_counts", {})
        if sc.get("error"):
            lvl = "FAIL"; msgs.append(f"{sc['error']} grading errors")
        if suite == "rl1" and not h.get("tb_seeds"):
            lvl = "WARN" if lvl == "OK" else lvl; msgs.append("rl1 graded without fixed TB seeds (re-grade pending)")
        p1 = h.get("heldout_pass_at_1")
        if not p1:
            lvl = "FAIL"; msgs.append(f"held-out pass@1 = {p1}")
        msgs.append(f"pass@1 {p1} pass@5 {h.get('heldout_pass_at_5')} agree {h.get('inloop_vs_heldout')}")
        r.add("heldout", lvl, "; ".join(msgs))
        inl = Counter(s for p in h.get("per_design", []) for s in p.get("inloop", []))
        tot = sum(inl.values()) or 1
        bad = inl.get("error", 0) + inl.get("timeout", 0)
        r.add("inloop", "WARN" if bad / tot > 0.2 else "OK", f"in-loop {dict(inl)}")

    if fb == "F2":
        n = len(glob.glob(str(arm / "gentb_cache" / "gen_tb_*.sv")))
        r.add("gentb", "OK" if n else "FAIL", f"{n} generated TBs cached")


def check_ve(arm: Path, fb: str, r: Report):
    sums = glob.glob(str(arm / "ve_reports" / "*" / "summary.csv"))
    if not sums:
        return r.add("problems", "FAIL", "no ve_reports/*/summary.csv")
    rows = [row for row in csv.reader(open(sums[0])) if row and row[0].startswith("Prob")]
    samples = glob.glob(str(arm / "ve_build" / ".build_sample_*" / "samples" / "Prob*"))
    ok = len(rows) == VE_PROBLEMS and len(samples) == VE_PROBLEMS
    r.add("problems", "OK" if ok else "FAIL", f"summary rows {len(rows)}, sample dirs {len(samples)} (expect {VE_PROBLEMS})")
    try:
        rate = sum(float(row[3]) for row in rows) / max(len(rows), 1)
    except (IndexError, ValueError):
        rate = None
    r.add("passrate", "FAIL" if not rate else "OK", f"mean pass rate {rate:.3f}" if rate is not None else "unparseable summary.csv")
    st = Counter()
    for sd in samples:
        for sj in glob.glob(os.path.join(sd, "sample_*.json")):
            try:
                if os.path.getsize(sj) > BIG:
                    st["huge_json"] += 1
                    continue
                st[json.load(open(sj)).get("final_status", "?")] += 1
            except Exception:
                st["unreadable"] += 1
    tot = sum(st.values()) or 1
    bad = st.get("error", 0) + st.get("timeout", 0) + st.get("unreadable", 0)
    r.add("samples", "WARN" if bad / tot > 0.1 or st.get("huge_json") else "OK", f"final_status {dict(st)}")


def main():
    arm = Path(sys.argv[1]).resolve()
    model, fb, suite = arm.parts[-3:]
    r = Report()
    if not (arm / "DONE").is_file():
        r.add("done", "WARN", "arm has no DONE")
    check_provenance(arm, r)
    check_bigfiles(arm, r)
    check_log(model, fb, suite, r)
    if suite == "ve":
        check_ve(arm, fb, r)
    else:
        check_rtllm(arm, fb, suite, r)
    tok = arm / "tokens.json"
    if tok.is_file():
        t = json.loads(tok.read_text())
        r.add("tokens", "OK" if t.get("generator") else "WARN", json.dumps(t.get("generator")))
    out = {"arm": f"{model}/{fb}/{suite}", "level": r.level, "checks": r.items}
    (arm / "armcheck.json").write_text(json.dumps(out, indent=2))
    flagged = [f"{i['check']}: {i['msg']}" for i in r.items if i["level"] != "OK"]
    print(f"{r.level} {model}/{fb}/{suite}" + (" | " + " | ".join(flagged) if flagged else ""))
    sys.exit({"OK": 0, "WARN": 1, "FAIL": 2}[r.level])


if __name__ == "__main__":
    main()

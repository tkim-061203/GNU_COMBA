#!/usr/bin/env python
"""
main_langgraph.py — VerilogEval LangGraph runner with benchmark_langgraph workflow
==================================================================================
Single-pass over (problems × samples) with pass@k aggregation, FR metrics,
per-sample JSON dumps, and multi-format export.

Runs entirely in CWD (build dir) when invoked from VE_testbench/langgraph/.build_*.
"""

import os
import sys
import glob
import json
import re
import signal
import argparse
import subprocess
from datetime import datetime

import numpy as np
import pandas as pd
from tqdm import tqdm
from multiprocess import Pool

# ──────────────────────────────────────────────────────────────
# Watchdog: per-(problem,sample) wall-time cap (Unix only via SIGALRM)
# Prevents Pool from hanging when pipeline graph loops infinitely
# (e.g. sanitizer→generator→sanitizer with no terminal cap).
# ──────────────────────────────────────────────────────────────
WALL_TIMEOUT_SEC = int(os.environ.get("COMBA_PIPELINE_TIMEOUT", "300"))


class PipelineTimeout(Exception):
    """Raised when SIGALRM fires inside run_pipeline_sync."""

# ──────────────────────────────────────────────────────────────
# Project paths
# ──────────────────────────────────────────────────────────────
srcDir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(srcDir, "langgraph_core"))

from pipeline_runner import run_pipeline_sync          # noqa: E402
from llm_interface import COMBALlm                     # noqa: E402

PROBLEM_DIR = os.path.abspath(
    os.path.join(srcDir, "../ext/verilog-eval/dataset_code-complete-iccad2023")
)
VE_SCRIPTS = os.path.abspath(
    os.path.join(srcDir, "../ext/verilog-eval/scripts")
)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
def parse_cmdline():
    p = argparse.ArgumentParser(
        description="VE LangGraph runner — single Pool over (problems × samples) + pass@k aggregation"
    )
    # Existing flags (kept compatible with old Makefile)
    p.add_argument("-s", "--samples", type=int, default=1,
                   help="pass@k samples per problem (default: 1)")
    p.add_argument("-j", "--jobs", type=int, default=20,
                   help="parallel worker count (default: 20)")
    p.add_argument("-m", "--model", type=str, default="generator")
    p.add_argument("-t", "--temperature", type=float, default=0.0)
    p.add_argument("--model-manual", type=str, default="http://localhost:8000/v1",
                   help="Generator LLM endpoint")
    p.add_argument("--model-submanual", type=str, default="http://localhost:8001/v1",
                   help="Debugger LLM endpoint")
    p.add_argument("-p", "--provider", type=str, default="openai")
    p.add_argument("-n", "--max-tokens", type=int, default=2048)
    p.add_argument("-P", "--top-p", type=float, default=0.95)
    p.add_argument("-x", "--examples", type=int, default=0)
    p.add_argument("-r", "--revision", type=str, default=None)
    p.add_argument("--pattern", type=str, default="Prob*",
                   help="glob pattern for problem prompts (default: Prob*)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--output-dir", type=str, default=None,
                   help="Root for outputs (default: CWD)")
    p.add_argument("--desc-type", choices=["xml", "txt"], default="xml",
                   help="Pipeline input description type (default: xml)")
    # New flags (benchmark-style)
    p.add_argument("--designs", nargs="*", default=None,
                   help="Filter problems by name (default: all)")
    p.add_argument("--dataset-dir", type=str, default=None,
                   help="Path to problem dataset (overrides default)")
    p.add_argument("--no-sim", action="store_true",
                   help="Skip post-pipeline iverilog final-check")
    p.add_argument("--no-aggregate", action="store_true",
                   help="Skip aggregation/export (worker-only mode)")
    p.add_argument("--timeout", type=int, default=WALL_TIMEOUT_SEC,
                   help=f"Per-(problem,sample) wall-time cap in seconds "
                        f"(default: {WALL_TIMEOUT_SEC}s, env: COMBA_PIPELINE_TIMEOUT)")
    return p.parse_args()


# ═══════════════════════════════════════════════════════════════
# WORKER — 1 (problem, sample) tuple
# ═══════════════════════════════════════════════════════════════
def do_process(args_tuple):
    """Run full COMBA pipeline once; dump per-sample JSON + artifacts."""
    problem_prompt_path, sample_idx, opts = args_tuple

    output_root = os.path.abspath(opts.output_dir)
    problem_base = os.path.basename(problem_prompt_path).replace("_prompt.txt", "")

    # Per-problem dir, per-sample work dir
    prob_dir = os.path.join(output_root, "samples", problem_base)
    os.makedirs(prob_dir, exist_ok=True)
    work_dir = os.path.join(prob_dir, f"work_{sample_idx:02d}")
    os.makedirs(work_dir, exist_ok=True)

    # Read NL prompt
    try:
        with open(problem_prompt_path, "r") as f:
            nl_input = f.read()
    except Exception as e:
        return (problem_base, sample_idx, f"error: {e}")

    # Build LLM (per worker process — multiprocess Pool forks fresh state)
    llm = COMBALlm(
        provider=opts.provider,
        model=opts.model,
        temperature=opts.temperature,
        max_tokens=opts.max_tokens,
        base_url=opts.model_manual,
        debugger_base_url=opts.model_submanual,
    )

    # ── Run COMBA pipeline (with wall-time watchdog) ──
    def _timeout_handler(signum, frame):
        raise PipelineTimeout(f"pipeline exceeded {WALL_TIMEOUT_SEC}s")

    prev_handler = None
    try:
        # Arm watchdog (Unix only). On non-Unix this raises AttributeError → caught.
        try:
            prev_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(WALL_TIMEOUT_SEC)
        except (AttributeError, ValueError):
            prev_handler = None  # Windows or non-main thread

        state = run_pipeline_sync(
            nl_input=nl_input,
            module_name="TopModule",
            benchmark_id=problem_base,
            llm=llm,
            dataset_dir=PROBLEM_DIR,
            work_dir=work_dir,
            desc_type=opts.desc_type,
        )
    except PipelineTimeout as e:
        state = {
            "final_status": "timeout",
            "error": str(e),
            "edtm": {},
            "gvd": "",
            "sc_log": "",
            "stop_reason": "watchdog_timeout",
        }
    except Exception as e:
        import traceback
        state = {
            "final_status": "error",
            "error": str(e),
            "error_traceback": traceback.format_exc(),
            "edtm": {},
            "gvd": "",
            "sc_log": "",
        }
    finally:
        # Disarm watchdog and restore handler
        try:
            signal.alarm(0)
            if prev_handler is not None:
                signal.signal(signal.SIGALRM, prev_handler)
        except (AttributeError, ValueError):
            pass

    state["_sample_idx"] = sample_idx
    state["_problem"] = problem_base

    # ── Dump per-sample JSON ──
    sample_base = os.path.join(prob_dir, f"sample_{sample_idx:02d}")
    try:
        with open(f"{sample_base}.json", "w") as f:
            json.dump(state, f, default=str, indent=2)
    except Exception as e:
        with open(f"{sample_base}.json", "w") as f:
            json.dump({"final_status": "error", "error": f"dump fail: {e}"}, f)

    # ── Optional: dump SV + run final iverilog check (legacy sv-iv-analyze) ──
    if not opts.no_sim:
        _dump_sample_sv(sample_base, state)
        _run_iverilog_check(sample_base, work_dir, problem_base)

    return (problem_base, sample_idx, state.get("final_status", "error"))


def _dump_sample_sv(sample_base: str, state: dict):
    """Write GVD + TopModule-renamed copy + sv-generate.log."""
    gvd = state.get("gvd", "") or ""

    with open(f"{sample_base}.sv", "w") as f:
        f.write(gvd)

    with open(f"{sample_base}-sv-generate.log", "w") as f:
        f.write(f"prompt_tokens = {state.get('prompt_tokens', 0)}\n")
        f.write(f"resp_tokens = {state.get('resp_tokens', 0)}\n")
        f.write("cost = 0.0\n")

    top_code = re.sub(
        r"module\s+[A-Za-z_]\w*",
        "module TopModule",
        gvd,
        count=1,
        flags=re.MULTILINE,
    )
    with open(f"{sample_base}_TopModule.sv", "w") as f:
        f.write(top_code)


def _run_iverilog_check(sample_base: str, work_dir: str, problem_base: str):
    """Compile + run final iverilog check; write sv-iv-test.log for sv-iv-analyze."""
    top_sv = f"{sample_base}_TopModule.sv"
    test_sv = os.path.join(PROBLEM_DIR, f"{problem_base}_test.sv")
    ref_sv = os.path.join(PROBLEM_DIR, f"{problem_base}_ref.sv")
    log_path = f"{sample_base}-sv-iv-test.log"
    binary = os.path.join(work_dir, problem_base)

    cmd = [
        "iverilog", "-Wall", "-Winfloop", "-Wno-timescale", "-g2012",
        "-s", "tb", "-o", binary, top_sv, test_sv, ref_sv,
    ]
    try:
        with open(log_path, "w") as lf:
            r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT)
            if r.returncode == 0:
                subprocess.run(["timeout", "30", binary],
                               stdout=lf, stderr=subprocess.STDOUT)
            else:
                lf.write(f"\nCompilation failed (rc={r.returncode})\n")
    except Exception as e:
        with open(log_path, "a") as lf:
            lf.write(f"sim error: {e}\n")
    finally:
        for p in (binary, top_sv):
            try:
                os.remove(p)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════
# AGGREGATION — paper formula (matches benchmark_langgraph.py)
# ═══════════════════════════════════════════════════════════════
def parse_sc_exceptions(sc_log: str) -> list:
    """Extract Verilator/iverilog %Error/%Warning codes from SC log."""
    if not sc_log:
        return []
    out = []
    for m in re.finditer(r'%(Error|Warning)(-(?P<code>[A-Z0-9_]+))?:\s', sc_log):
        c = m.group("code") or "GENERIC"
        if c != "Exiting":
            out.append(c)
    return out


def calc_fr_sample(sample: dict) -> tuple:
    """Per-sample (Syntax FR, Func FR) per the paper formula.

    Status semantics:
      - pass             → SFR=1.0, FFR=1.0  (full credit)
      - fail_ts          → SFR=1.0, FFR=0.0  (SC passed, TB failed)
      - fail_sc          → SFR=fixed/total or 0.0 if SC never reached / no fix
      - fail_extraction  → SFR=0.0, FFR=0.0  (sanitizer cap, no usable code)
      - timeout / error  → SFR=0.0, FFR=0.0  (worker exception or watchdog)
      - other / None     → SFR=0.0, FFR=0.0  (defensive zero-credit)
    """
    status = sample.get("final_status", "error")
    edtm = sample.get("edtm", {}) or {}
    all_sc = [k for k in edtm if not k.startswith("TB:")]
    all_tb = [k for k in edtm if k.startswith("TB:")]

    # Zero-credit terminal states (no usable code OR no real progress)
    if status in ("error", "timeout", "fail_extraction"):
        return 0.0, 0.0

    # ── Syntax FR ──
    # Special case: fail_sc with no SC exceptions ever recorded means
    # the pipeline never even reached SC successfully (sanitizer fail,
    # baseline fallback used, etc.) → zero credit, NOT 1.0.
    if status == "fail_sc" and not all_sc:
        return 0.0, 0.0

    final_sc_raw = parse_sc_exceptions(sample.get("sc_log", ""))
    final_sc_sigs = set()
    for code in final_sc_raw:
        for k in all_sc:
            if code in k:
                final_sc_sigs.add(k)
                break

    if not all_sc:
        # No SC exceptions ever → SC was clean from start
        syntax_fr = 1.0
    else:
        syntax_fr = sum(1 for x in all_sc if x not in final_sc_sigs) / len(all_sc)

    # ── Func FR ──
    if status == "pass":
        func_fr = 1.0
    elif status == "fail_sc":
        # SC failed → TB never ran → no functional credit
        func_fr = 0.0
    elif status == "fail_ts":
        func_fr = 0.0
    elif not all_tb:
        # No TB exceptions tracked, status is something else (e.g. partial)
        func_fr = 1.0
    else:
        func_fr = 0.0

    return syntax_fr, func_fr


def collect_samples(out_dir: str, problems: list, num_samples: int) -> dict:
    """Walk samples/<prob>/sample_NN.json → sample_results[s][prob]."""
    sample_results = {s: {} for s in range(1, num_samples + 1)}
    for p in problems:
        prob_dir = os.path.join(out_dir, "samples", p)
        for s in range(1, num_samples + 1):
            jp = os.path.join(prob_dir, f"sample_{s:02d}.json")
            if os.path.isfile(jp):
                try:
                    with open(jp) as f:
                        sample_results[s][p] = json.load(f)
                except Exception:
                    sample_results[s][p] = {"final_status": "error", "edtm": {}}
            else:
                sample_results[s][p] = {"final_status": "error", "edtm": {}}
    return sample_results


def aggregate(sample_results: dict, problems: list, num_samples: int):
    """Per-problem rows + global stats. Hard problems sorted to top."""
    rows = []
    for p in problems:
        statuses = [
            sample_results[s].get(p, {}).get("final_status", "error")
            for s in range(1, num_samples + 1)
        ]
        sfrs, ffrs = [], []
        for s in range(1, num_samples + 1):
            sfr, ffr = calc_fr_sample(sample_results[s].get(p, {}))
            sfrs.append(sfr)
            ffrs.append(ffr)

        pass_at_1 = 1 if statuses[0] == "pass" else 0
        pass_at_k = 1 if any(st == "pass" for st in statuses) else 0
        sc_pass_k = 1 if any(st in ("pass", "fail_ts") for st in statuses) else 0

        rows.append({
            "Module": p,
            "pass@1": f"{pass_at_1 * 100:.0f}%",
            f"pass@{num_samples}": f"{pass_at_k * 100:.0f}%",
            "SC Pass Rate": f"{sc_pass_k * 100:.0f}%",
            "Syntax FR": f"{np.mean(sfrs) * 100:.2f}%",
            "Func FR":   f"{np.mean(ffrs) * 100:.2f}%",
            "_p1": pass_at_1,
            "_pk": pass_at_k,
            "_sc": sc_pass_k,
            "_sfr": float(np.mean(sfrs)),
            "_ffr": float(np.mean(ffrs)),
        })

    # Hard problems first
    rows.sort(key=lambda r: (r["_pk"], r["_p1"], r["_sc"]))
    df = pd.DataFrame(rows)

    # Total exception counts (across all (problem × sample))
    total_sc_exc = total_tb_exc = 0
    total_sc_fixed = 0
    total_timeouts = total_errors = 0
    total_fail_extraction = 0
    total_fail_sc = total_fail_ts = total_pass = 0
    for p in problems:
        for s in range(1, num_samples + 1):
            samp = sample_results[s].get(p, {})
            st = samp.get("final_status", "error")
            if st == "timeout":         total_timeouts += 1
            elif st == "error":         total_errors += 1
            elif st == "fail_extraction": total_fail_extraction += 1
            elif st == "fail_sc":       total_fail_sc += 1
            elif st == "fail_ts":       total_fail_ts += 1
            elif st == "pass":          total_pass += 1
            edtm = samp.get("edtm", {}) or {}
            sc_keys = [k for k in edtm if not k.startswith("TB:")]
            tb_keys = [k for k in edtm if k.startswith("TB:")]
            total_sc_exc += len(sc_keys)
            total_tb_exc += len(tb_keys)
            final_sc_raw = parse_sc_exceptions(samp.get("sc_log", ""))
            final_set = set()
            for code in final_sc_raw:
                for k in sc_keys:
                    if code in k:
                        final_set.add(k); break
            total_sc_fixed += sum(1 for x in sc_keys if x not in final_set)

    stats = {
        "avg_pass_at_1":               float(df["_p1"].mean() * 100) if len(df) else 0.0,
        f"avg_pass_at_{num_samples}":  float(df["_pk"].mean() * 100) if len(df) else 0.0,
        "avg_sc_pass_rate":            float(df["_sc"].mean() * 100) if len(df) else 0.0,
        "avg_syntax_fr":               float(df["_sfr"].mean() * 100) if len(df) else 0.0,
        "avg_func_fr":                 float(df["_ffr"].mean() * 100) if len(df) else 0.0,
        "total_problems":              len(problems),
        "samples_per_problem":         num_samples,
        "total_runs":                  len(problems) * num_samples,
        "total_sc_exceptions":         total_sc_exc,
        "total_sc_fixed":              total_sc_fixed,
        "total_tb_exceptions":         total_tb_exc,
        "total_pass":                  total_pass,
        "total_fail_sc":               total_fail_sc,
        "total_fail_ts":               total_fail_ts,
        "total_fail_extraction":       total_fail_extraction,
        "total_timeouts":              total_timeouts,
        "total_errors":                total_errors,
        "timestamp":                   datetime.now().isoformat(),
    }
    return rows, df, stats


# ═══════════════════════════════════════════════════════════════
# Legacy sv-iv-analyze (backward compat with VE official scripts)
# ═══════════════════════════════════════════════════════════════
def _run_legacy_analyze(out_dir: str):
    script = os.path.join(VE_SCRIPTS, "sv-iv-analyze")
    if not os.path.exists(script):
        return

    samples_root = os.path.join(out_dir, "samples")
    rep_dir = os.path.join(out_dir, "reports")
    os.makedirs(rep_dir, exist_ok=True)
    summary_txt = os.path.join(rep_dir, "summary.txt")
    summary_csv = os.path.join(rep_dir, "summary.csv")
    error_txt = os.path.join(rep_dir, "error_problems.txt")

    # sv-iv-analyze expects VE-standard naming: <prob>_sample<N>-sv-iv-test.log
    # (where N has NO leading zero, e.g. sample1 not sample01).
    # Our internal layout is samples/<prob>/sample_NN-... so we flatten with
    # rename via symlinks.
    flat = os.path.join(out_dir, ".sv_iv_flat")
    os.makedirs(flat, exist_ok=True)
    # Clean stale links from previous runs to avoid double-counting
    for stale in os.listdir(flat):
        sp = os.path.join(flat, stale)
        if os.path.islink(sp) or os.path.isfile(sp):
            try:
                os.remove(sp)
            except OSError:
                pass

    link_count = 0
    for prob in os.listdir(samples_root):
        prob_dir = os.path.join(samples_root, prob)
        if not os.path.isdir(prob_dir):
            continue
        for fn in os.listdir(prob_dir):
            if not (fn.endswith("-sv-iv-test.log") or fn.endswith("-sv-generate.log") or fn.endswith(".sv")):
                continue
            # Match both "sample_NN-..." (our format) and "sampleN-..." (VE format)
            m = re.match(r"sample_?(\d+)(.*)", fn)
            if not m:
                continue
            # sv-iv-analyze script uses regex `sample(\d{2})`, so it REQUIRES a 2-digit sample number!
            idx_norm = f"{int(m.group(1)):02d}"
            suffix = m.group(2)
            link_name = f"{prob}_sample{idx_norm}{suffix}"
            # sv-iv-analyze expects files inside a directory named after the problem
            flat_prob_dir = os.path.join(flat, prob)
            os.makedirs(flat_prob_dir, exist_ok=True)
            link = os.path.join(flat_prob_dir, link_name)
            try:
                if os.path.islink(link) or os.path.exists(link):
                    os.remove(link)
                os.symlink(os.path.join(prob_dir, fn), link)
                link_count += 1
            except OSError as e:
                print(f"[sv-iv-analyze] symlink fail {link_name}: {e}")

    if link_count == 0:
        print(f"[sv-iv-analyze] no log files to flatten under {samples_root}; skipping")
        return
    print(f"[sv-iv-analyze] flattened {link_count} log files into {flat}")

    try:
        with open(summary_txt, "w") as out:
            r = subprocess.run(
                [script, f"--csv={summary_csv}"],
                stdout=out, stderr=subprocess.STDOUT, cwd=flat,
            )
        if r.returncode != 0:
            print(f"[sv-iv-analyze] script returned rc={r.returncode}; "
                  f"see {summary_txt}")
            # Don't propagate — Python aggregator already produced canonical metrics
            return

        with open(summary_txt) as f:
            for line in f:
                if "pass_rate" in line:
                    print("[sv-iv-analyze]", line.strip())
        with open(summary_txt) as f, open(error_txt, "w") as ef:
            ef.write("Problems with failures:\n")
            for line in f:
                if line.startswith("Prob"):
                    parts = line.split()
                    if len(parts) >= 4 and any(c != "." for c in parts[3]):
                        ef.write(line)
    except Exception as e:
        print(f"[sv-iv-analyze] skipped: {e}")


# ═══════════════════════════════════════════════════════════════
# MAIN — single Pool over (problems × samples), no trial loop
# ═══════════════════════════════════════════════════════════════
def main():
    opts = parse_cmdline()
    if opts.quiet:
        os.environ["COMBA_QUIET"] = "1"

    opts.output_dir = os.path.abspath(opts.output_dir or os.getcwd())
    os.makedirs(opts.output_dir, exist_ok=True)
    print(f"Output directory: {opts.output_dir}")

    # Propagate timeout to workers (read by global WALL_TIMEOUT_SEC at fork time)
    global WALL_TIMEOUT_SEC
    WALL_TIMEOUT_SEC = max(10, int(opts.timeout))
    os.environ["COMBA_PIPELINE_TIMEOUT"] = str(WALL_TIMEOUT_SEC)
    print(f"Per-sample wall timeout: {WALL_TIMEOUT_SEC}s")

    global PROBLEM_DIR
    if getattr(opts, "dataset_dir", None):
        PROBLEM_DIR = os.path.abspath(opts.dataset_dir)
        print(f"Dataset directory: {PROBLEM_DIR}")

    # ── Discover problems ──
    prompts = sorted(glob.glob(f"{PROBLEM_DIR}/{opts.pattern}_prompt.txt"))
    problems = [os.path.basename(p).replace("_prompt.txt", "") for p in prompts]
    if opts.designs:
        keep = set(opts.designs)
        prompts = [p for p, n in zip(prompts, problems) if n in keep]
        problems = [n for n in problems if n in keep]

    if not problems:
        print(f"No problems matched pattern={opts.pattern} designs={opts.designs}")
        sys.exit(1)

    total_runs = len(problems) * opts.samples
    print(f"Problems: {len(problems)} | samples/problem: {opts.samples} "
          f"| jobs: {opts.jobs} | total runs: {total_runs}")

    # ── Single Pool over (problems × samples) ──
    sets = [(p, s, opts) for p in prompts for s in range(1, opts.samples + 1)]
    njobs = min(opts.jobs, max(1, len(sets)))

    with Pool(processes=njobs) as pool:
        live_counts = {"pass": 0, "fail_ts": 0, "fail_sc": 0,
                       "fail_extraction": 0,
                       "timeout": 0, "error": 0, "other": 0}
        pbar = tqdm(total=len(sets), desc="Pipeline runs")
        for result in pool.imap_unordered(do_process, sets):
            try:
                _prob, _idx, status = result
            except Exception:
                status = "error"
            key = status if status in live_counts else "other"
            live_counts[key] += 1
            pbar.set_postfix(
                pass_=live_counts["pass"],
                ts=live_counts["fail_ts"],
                sc=live_counts["fail_sc"],
                ext=live_counts["fail_extraction"],
                to=live_counts["timeout"],
                err=live_counts["error"],
            )
            pbar.update(1)
        pbar.close()
        print(f"Live tally: {live_counts}")

    if opts.no_aggregate:
        print("Skip aggregation (--no-aggregate).")
        return

    # ── Aggregate from dumped per-sample JSONs ──
    sample_results = collect_samples(opts.output_dir, problems, opts.samples)
    rows, df, stats = aggregate(sample_results, problems, opts.samples)

    print(
        f"\n=== pass@1: {stats['avg_pass_at_1']:.2f}%"
        f" | pass@{opts.samples}: {stats[f'avg_pass_at_{opts.samples}']:.2f}%"
        f" | SC PR: {stats['avg_sc_pass_rate']:.2f}%"
        f" | SFR: {stats['avg_syntax_fr']:.2f}%"
        f" | FFR: {stats['avg_func_fr']:.2f}% ==="
    )

    # ── Legacy sv-iv-analyze (if available) ──
    if not opts.no_sim:
        _run_legacy_analyze(opts.output_dir)


if __name__ == "__main__":
    main()
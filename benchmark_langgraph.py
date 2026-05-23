#!/usr/bin/env python3
"""
benchmark_langgraph.py — COMBA-LLM Benchmark (subprocess-based)
================================================================
Matches the working Jupyter notebook logic:
  1. subprocess → run.py langgraph
  2. Read per-module JSON reports
  3. Aggregate Pass Rate + Fix Rate
  4. Export JSON / CSV / LaTeX / Markdown

Usage:
    python benchmark_langgraph.py --trials 5
    python benchmark_langgraph.py --trials 5 --descriptiontype xml
    python benchmark_langgraph.py --trials 1 --designs counter_12 adder_8bit
"""

import argparse
import json
import os
import re
import subprocess
import sys
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

# ── Project root ──
PROJECT_ROOT = Path(__file__).resolve().parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# FR — EXACT PAPER FORMULA (from notebook cell 5)
# ═══════════════════════════════════════════════════════════════

def parse_sc_exceptions(sc_log: str) -> list[str]:
    """Extract exception codes from SC log."""
    if not sc_log:
        return []
    exceptions = []
    for match in re.finditer(r'%(Error|Warning)(-(?P<code>[A-Z0-9_]+))?:\s', sc_log):
        code = match.group('code') or 'GENERIC'
        if code != 'Exiting':
            exceptions.append(code)
    return exceptions


def calc_fr_trial(sample: dict) -> tuple[float, float]:
    """Paper-accurate FRᵢ for one trial.
    Returns (syntax_fr, func_fr).
    """
    status = sample.get('final_status', 'error')
    edtm = sample.get('edtm', {})

    all_sc = [k for k in edtm.keys() if not k.startswith('TB:')]
    all_tb = [k for k in edtm.keys() if k.startswith('TB:')]

    if status == 'error':
        return 0.0, 0.0

    # Final SC exceptions (still in final log)
    final_sc_raw = parse_sc_exceptions(sample.get('sc_log', ''))
    final_sc_sigs = set()
    for code in final_sc_raw:
        for edtm_key in all_sc:
            if code in edtm_key:
                final_sc_sigs.add(edtm_key)
                break

    # Syntax FR
    if len(all_sc) == 0:
        syntax_fr = 1.0
    else:
        fixed = sum(1 for x in all_sc if x not in final_sc_sigs)
        syntax_fr = fixed / len(all_sc)

    # Func FR
    if status == 'pass':
        func_fr = 1.0
    elif len(all_tb) == 0:
        func_fr = 0.0 if status == 'fail_ts' else 1.0
    else:
        func_fr = 0.0 if status in ('fail_ts',) else 1.0

    return syntax_fr, func_fr


# ═══════════════════════════════════════════════════════════════
# PIPELINE EXECUTION (subprocess, matching notebook)
# ═══════════════════════════════════════════════════════════════

def run_trials(modules_dir: str, description_type: str, num_trials: int,
               summary_file: str, all_modules: list[str],
               filter_designs: list[str] | None = None) -> dict:
    """Run N trials via subprocess, return trial_results dict."""
    trial_results = {}  # trial_idx -> {module_name -> report}

    for trial in range(1, num_trials + 1):
        print(f"\n{'='*60}")
        print(f"  TRIAL {trial}/{num_trials}")
        print(f"{'='*60}")

        # Remove old summary to get fresh data
        if os.path.exists(summary_file):
            os.remove(summary_file)

        # Build command
        if filter_designs:
            module_paths = [os.path.join(modules_dir, d) for d in filter_designs]
        else:
            module_paths = [f"{modules_dir}/*"]

        cmd = [
            sys.executable, "run.py", "langgraph"
        ] + module_paths + [
            "--descriptiontype", description_type
        ]

        print(f"  🚀 Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=False, text=True)

        if result.returncode != 0:
            print(f"  ⚠️ Trial {trial} had errors (returncode={result.returncode})")

        # Read per-module reports
        trial_data = {}
        target_modules = filter_designs if filter_designs else all_modules

        for module_name in target_modules:
            report_path = os.path.join(
                modules_dir, module_name, "reports",
                f"report_langgraph.{description_type}.json"
            )

            if os.path.isfile(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    report = json.load(f)

                # Save trial-specific copy
                trial_report_path = os.path.join(
                    modules_dir, module_name, "reports",
                    f"report_langgraph.{description_type}.trial_{trial}.json"
                )
                with open(trial_report_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)

                # Extract sample data
                samples = report.get("samples", report)
                if isinstance(samples, dict):
                    trial_data[module_name] = samples
                elif isinstance(samples, list):
                    trial_data[module_name] = samples[0]
            else:
                print(f"  ⚠️ No report for {module_name}")
                trial_data[module_name] = {"final_status": "error", "edtm": {}}

        trial_results[trial] = trial_data
        passed = sum(1 for d in trial_data.values() if d.get("final_status") == "pass")
        print(f"  ✅ Trial {trial}: {passed}/{len(target_modules)} passed")

    print(f"\n{'='*60}")
    print(f"  All {num_trials} trials completed.")
    print(f"{'='*60}")

    return trial_results


# ═══════════════════════════════════════════════════════════════
# AGGREGATION (matching notebook cell 5)
# ═══════════════════════════════════════════════════════════════

def aggregate_results(trial_results: dict, all_modules: list[str],
                      num_trials: int) -> tuple[list[dict], pd.DataFrame, dict]:
    """Compute per-module Pass Rate + Fix Rate.
    Returns (rows, df, global_stats).
    """
    rows = []
    for module_name in all_modules:
        sc_pass_count = 0
        tb_pass_count = 0
        syntax_frs = []
        func_frs = []

        for trial in range(1, num_trials + 1):
            sample = trial_results[trial].get(module_name, {})
            status = sample.get('final_status', 'error')

            # Pass Rate (binary)
            if status in ('pass', 'fail_ts'):
                sc_pass_count += 1
            if status == 'pass':
                tb_pass_count += 1

            # Fix Rate
            sfr, ffr = calc_fr_trial(sample)
            syntax_frs.append(sfr)
            func_frs.append(ffr)

        rows.append({
            'Module': module_name,
            'Syntax Pass Rate': f"{sc_pass_count / num_trials * 100:.0f}%",
            'TB Pass Rate': f"{tb_pass_count / num_trials * 100:.0f}%",
            'Syntax FR': f"{np.mean(syntax_frs) * 100:.2f}%",
            'Func FR': f"{np.mean(func_frs) * 100:.2f}%",
            '_sc_pr': sc_pass_count / num_trials,
            '_tb_pr': tb_pass_count / num_trials,
            '_sfr': np.mean(syntax_frs),
            '_ffr': np.mean(func_frs),
        })
    
    # Sort rows by TB Pass Rate (ascending) so hard modules are at the top
    rows.sort(key=lambda x: (x['_tb_pr'], x['_sc_pr']))

    df = pd.DataFrame(rows)

    # Global averages
    avg_sc_pr = df['_sc_pr'].mean() * 100
    avg_tb_pr = df['_tb_pr'].mean() * 100
    avg_sfr = df['_sfr'].mean() * 100
    avg_ffr = df['_ffr'].mean() * 100

    # Total Exceptions
    total_sc_exceptions = 0
    total_sc_fixed = 0
    total_tb_exceptions = 0
    total_tb_fixed = 0

    for module_name in all_modules:
        for trial in range(1, num_trials + 1):
            sample = trial_results[trial].get(module_name, {})
            edtm = sample.get('edtm', {})
            status = sample.get('final_status', 'error')

            sc_keys = [k for k in edtm.keys() if not k.startswith('TB:')]
            tb_keys = [k for k in edtm.keys() if k.startswith('TB:')]

            total_sc_exceptions += len(sc_keys)
            total_tb_exceptions += len(tb_keys)

            final_sc_raw = parse_sc_exceptions(sample.get('sc_log', ''))
            final_sc_sigs = set()
            for code in final_sc_raw:
                for ek in sc_keys:
                    if code in ek:
                        final_sc_sigs.add(ek)
                        break
            total_sc_fixed += sum(1 for x in sc_keys if x not in final_sc_sigs)

            if status == 'pass':
                total_tb_fixed += len(tb_keys)

    global_stats = {
        'avg_sc_pr': avg_sc_pr,
        'avg_tb_pr': avg_tb_pr,
        'avg_sfr': avg_sfr,
        'avg_ffr': avg_ffr,
        'total_sc_exceptions': total_sc_exceptions,
        'total_sc_fixed': total_sc_fixed,
        'total_tb_exceptions': total_tb_exceptions,
        'total_tb_fixed': total_tb_fixed,
    }

    return rows, df, global_stats


# ═══════════════════════════════════════════════════════════════
# PRINT SUMMARY
# ═══════════════════════════════════════════════════════════════

def print_summary(rows, df, stats, num_trials, num_modules):
    """Print summary table to console."""
    print(f"\n=== GLOBAL RESULTS ({num_trials} trials × {num_modules} modules) ===")
    print(f"Syntax Pass Rate:    {stats['avg_sc_pr']:.1f}%")
    print(f"TB Pass Rate:    {stats['avg_tb_pr']:.1f}%")
    print(f"Syntax Fix Rate: {stats['avg_sfr']:.2f}%")
    print(f"Func Fix Rate:   {stats['avg_ffr']:.2f}%")
    print(f"SC Exceptions:   {stats['total_sc_fixed']}/{stats['total_sc_exceptions']}")
    print(f"TB Failures:     {stats['total_tb_fixed']}/{stats['total_tb_exceptions']}")
    print()

    print(df[['Module', 'Syntax Pass Rate', 'TB Pass Rate', 'Syntax FR', 'Func FR']].to_string(index=False))


# ═══════════════════════════════════════════════════════════════
# EXPORT (matching notebook cell 7)
# ═══════════════════════════════════════════════════════════════

def export_results(rows, df, stats, description_type, num_trials, output_dir):
    """Export JSON, CSV, LaTeX."""
    os.makedirs(output_dir, exist_ok=True)

    avg_sc_pr = stats['avg_sc_pr']
    avg_tb_pr = stats['avg_tb_pr']
    avg_sfr = stats['avg_sfr']
    avg_ffr = stats['avg_ffr']

    # --- JSON ---
    export_data = {
        'config': {
            'num_trials': num_trials,
            'description_type': description_type,
            'num_modules': len(rows),
            'timestamp': datetime.now().isoformat(),
        },
        'global': {
            'sc_pass_rate': avg_sc_pr / 100,
            'tb_pass_rate': avg_tb_pr / 100,
            'syntax_fix_rate': avg_sfr / 100,
            'func_fix_rate': avg_ffr / 100,
        },
        'modules': {r['Module']: {
            'sc_pass_rate': r['_sc_pr'],
            'tb_pass_rate': r['_tb_pr'],
            'syntax_fr': r['_sfr'],
            'func_fr': r['_ffr'],
        } for r in rows}
    }

    json_path = os.path.join(output_dir, f'benchmark_{description_type}_{num_trials}trials.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    print(f'📄 JSON saved: {json_path}')

    # --- CSV ---
    csv_path = os.path.join(output_dir, f'benchmark_{description_type}_{num_trials}trials.csv')
    df[['Module', 'Syntax Pass Rate', 'TB Pass Rate', 'Syntax FR', 'Func FR']].to_csv(
        csv_path, index=False
    )
    print(f'📄 CSV saved: {csv_path}')

    # --- LaTeX ---
    latex_rows = []
    for r in rows:
        latex_rows.append(
            f"  {r['Module']} & {r['Syntax Pass Rate']} & {r['TB Pass Rate']} & "
            f"{r['Syntax FR']} & {r['Func FR']} \\\\"
        )
    latex_avg = (
        f"  \\textbf{{Average}} & \\textbf{{{avg_sc_pr:.0f}\\%}} & "
        f"\\textbf{{{avg_tb_pr:.0f}\\%}} & \\textbf{{{avg_sfr:.2f}\\%}} & "
        f"\\textbf{{{avg_ffr:.2f}\\%}} \\\\"
    )

    latex = '\n'.join([
        r'\begin{table}[h]',
        r'\centering',
        f'\\caption{{Pass Rate and Fix Rate ({description_type}, {num_trials} trials)}}',
        r'\begin{tabular}{l|cc|cc}',
        r'  \hline',
        r'  Design & Syntax PR & TB PR & Syntax FR & Func FR \\',
        r'  \hline',
        *latex_rows,
        r'  \hline',
        latex_avg,
        r'  \hline',
        r'\end{tabular}',
        r'\end{table}',
    ])

    tex_path = os.path.join(output_dir, f'benchmark_{description_type}_{num_trials}trials.tex')
    with open(tex_path, 'w', encoding='utf-8') as f:
        f.write(latex)
    print(f'📄 LaTeX saved: {tex_path}')

    # --- Markdown ---
    md_lines = [
        f"# COMBA-LLM Benchmark Report",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Modules:** {len(rows)} | **Trials:** {num_trials}", "",
        f"## Summary", "",
        f"| Metric | Value |", f"|--------|-------|",
        f"| Syntax Pass Rate | **{avg_sc_pr:.1f}%** |",
        f"| TB Pass Rate | **{avg_tb_pr:.1f}%** |",
        f"| Syntax Fix Rate | **{avg_sfr:.2f}%** |",
        f"| Func Fix Rate | **{avg_ffr:.2f}%** |",
        f"| Syntax Exceptions | {stats['total_sc_fixed']}/{stats['total_sc_exceptions']} |",
        f"| TB Failures | {stats['total_tb_fixed']}/{stats['total_tb_exceptions']} |", "",
        f"## Per-Design", "",
        f"| Design | Syntax PR | TB PR | Syntax FR | Func FR |",
        f"|--------|-------|-------|-----------|---------|",
    ]
    for r in rows:
        md_lines.append(
            f"| {r['Module']} | {r['Syntax Pass Rate']} | {r['TB Pass Rate']} | "
            f"{r['Syntax FR']} | {r['Func FR']} |"
        )
    md_lines.append(
        f"| **Average** | **{avg_sc_pr:.1f}%** | **{avg_tb_pr:.1f}%** | "
        f"**{avg_sfr:.2f}%** | **{avg_ffr:.2f}%** |"
    )

    md_path = os.path.join(output_dir, f'benchmark_{description_type}_{num_trials}trials.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))
    print(f'📄 Markdown saved: {md_path}')


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="COMBA-LLM Benchmark (subprocess-based)")
    p.add_argument("--modules-dir", default="modules",
                    help="Path to modules/ (default: modules)")
    p.add_argument("--descriptiontype", default="txt",
                    help="Description type: txt or xml (default: txt)")
    p.add_argument("--trials", type=int, default=5,
                    help="Number of trials per design (default: 5)")
    p.add_argument("--designs", nargs="*", default=None,
                    help="Specific design names (default: all)")
    p.add_argument("--output-dir", default="reports/fixrate",
                    help="Output directory (default: reports/fixrate)")
    p.add_argument("--dataset", choices=["rtllm", "rtllm_v2", "verilogeval"], default=None,
                    help="Preset dataset configuration (rtllm, rtllm_v2, or verilogeval)")
    args = p.parse_args()

    os.environ["COMBA_QUIET"] = "1"

    modules_dir = args.modules_dir
    description_type = args.descriptiontype
    num_trials = args.trials
    output_dir = args.output_dir

    # Dataset presets
    if args.dataset in ("rtllm", "rtllm_v2"):
        if args.dataset == "rtllm":
            modules_dir = "RTLLM/modules"
            output_dir = "RTLLM/reports/fixrate"
        else:
            modules_dir = "RTLLM_v2/modules"
            output_dir = "RTLLM_v2/reports/fixrate"
        # For RTLLM, default to RTLLM.txt if no specific type was requested
        if args.dataset == "rtllm" and args.descriptiontype == "txt":
            description_type = "RTLLM.txt"
    elif args.dataset == "verilogeval":
        modules_dir = "modules"
        output_dir = "reports/fixrate"

    summary_file = os.path.join(os.path.dirname(output_dir), f"summary_langgraph.{description_type}.json")

    # Discover modules
    if not os.path.isdir(modules_dir):
        logger.error(f"Modules dir not found: {modules_dir}")
        sys.exit(1)

    all_modules = sorted([d for d in os.listdir(modules_dir)
                          if os.path.isdir(os.path.join(modules_dir, d))])

    target_modules = args.designs if args.designs else all_modules

    print(f"Configuration:")
    print(f"  Trials per design: {num_trials}")
    print(f"  Description type:  {description_type}")
    print(f"  Total modules:     {len(target_modules)}")
    print(f"  Total runs:        {len(target_modules) * num_trials}")
    print(f"\nModules:")
    for i, m in enumerate(target_modules, 1):
        print(f"  {i:2d}. {m}")

    # ── Step 1: Run trials via subprocess ──
    trial_results = run_trials(
        modules_dir, description_type, num_trials,
        summary_file, all_modules,
        filter_designs=args.designs
    )

    # ── Step 2: Aggregate ──
    rows, df, stats = aggregate_results(trial_results, target_modules, num_trials)

    # ── Step 3: Print ──
    print_summary(rows, df, stats, num_trials, len(target_modules))

    # ── Step 4: Export ──
    export_results(rows, df, stats, description_type, num_trials, output_dir)


if __name__ == "__main__":
    main()
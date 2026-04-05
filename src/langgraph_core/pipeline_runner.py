"""
COMBA Pipeline Runner — Shared module for api_server.py and run.py.

Provides:
    create_llm()            — Unified LLM factory (StubLLM → COMBALlm → ChatOpenAI)
    get_pipeline(llm)       — Lazy-init singleton graph
    run_pipeline_sync()     — Run full pipeline, return final state
    run_pipeline_streaming() — Yield (node_name, state_update) per step
    run_pipeline_batch()    — Batch evaluation over module directories
"""

import os
import re
import json
import glob
import sys
from typing import Optional, List, Iterator, Tuple

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# LLM Factory — Unified fallback chain
# ──────────────────────────────────────────────────────────────

def create_llm():
    """
    Create LLM with fallback chain:
      1. COMBA_USE_STUB=1 → StubLLM (testing)
      2. COMBALlm.from_env() (dual-GPU vLLM)
      3. ChatOpenAI (Ollama / single vLLM)
    """
    use_stub = os.environ.get("COMBA_USE_STUB", "").lower() in ("1", "true", "yes")

    if use_stub:
        from stub_llm import create_stub_llm
        print("[COMBA] Using StubLLM (testing mode)")
        return create_stub_llm()

    # Try COMBALlm (dual-GPU) first
    try:
        from llm_interface import COMBALlm
        llm = COMBALlm.from_env()
        print(f"[COMBA] Using COMBALlm: {llm}")
        return llm
    except Exception as e:
        print(f"[COMBA] COMBALlm failed ({e}), falling back to ChatOpenAI")

    # Fallback to ChatOpenAI
    from langchain_openai import ChatOpenAI
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
    api_key = os.environ.get("LLM_API_KEY", "ollama")
    model = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")
    print(f"[COMBA] Using ChatOpenAI: {model} @ {base_url}")
    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model, temperature=0.1)


# ──────────────────────────────────────────────────────────────
# Pipeline Singleton
# ──────────────────────────────────────────────────────────────

_llm = None
_graph = None


def get_pipeline(llm=None):
    """
    Lazy-init and return (llm, graph) tuple.
    If llm is provided, use it; otherwise create via create_llm().
    """
    global _llm, _graph

    if _graph is not None and llm is None:
        return _llm, _graph

    if llm is None:
        llm = create_llm()

    from comba_pipeline import build_comba_graph
    _llm = llm
    _graph = build_comba_graph(llm)
    print("[COMBA] Pipeline graph compiled")
    return _llm, _graph


def reset_pipeline():
    """Reset the singleton (useful for tests)."""
    global _llm, _graph
    _llm = None
    _graph = None


# ──────────────────────────────────────────────────────────────
# Pipeline Runners
# ──────────────────────────────────────────────────────────────

def _prepare_state(
    nl_input: str,
    module_name: Optional[str] = None,
    xml_description: Optional[str] = None,
    dataset_dir: Optional[str] = None,
    benchmark_id: Optional[str] = None,
) -> dict:
    """Build initial COMBAState, optionally injecting XML."""
    from comba_pipeline import make_initial_state
    
    state = make_initial_state(
        nl_input=nl_input, 
        module_name=module_name or "",
        benchmark_id=benchmark_id or ""
    )
    if dataset_dir:
        state["dataset_dir"] = dataset_dir

    # If XML provided or input looks like XML, inject it
    if xml_description:
        state["xml_description"] = xml_description
        if not module_name:
            match = re.search(r'<module\s+id="([^"]+)"', xml_description)
            if match:
                state["module_name"] = match.group(1)
    elif nl_input.strip().startswith("<module") or nl_input.strip().startswith("<modules"):
        state["xml_description"] = nl_input
        match = re.search(r'<module\s+id="([^"]+)"', nl_input)
        if match:
            state["module_name"] = match.group(1)

    return state


def run_pipeline_sync(
    nl_input: str,
    module_name: Optional[str] = None,
    xml_description: Optional[str] = None,
    llm=None,
    dataset_dir: Optional[str] = None,
    benchmark_id: Optional[str] = None,
) -> dict:
    """
    Run full COMBA pipeline synchronously.

    Args:
        nl_input: Natural language or XML description.
        module_name: Optional module name override.
        xml_description: Optional pre-existing XML (skips converter).
        llm: Optional LLM instance (uses singleton if None).

    Returns:
        Final COMBAState dict.
    """
    _, graph = get_pipeline(llm)
    state = _prepare_state(nl_input, module_name, xml_description, dataset_dir, benchmark_id)
    config = {"recursion_limit": 100}
    return graph.invoke(state, config)


def run_pipeline_streaming(
    nl_input: str,
    module_name: Optional[str] = None,
    xml_description: Optional[str] = None,
    llm=None,
    dataset_dir: Optional[str] = None,
    benchmark_id: Optional[str] = None,
) -> Iterator[Tuple[str, dict]]:
    """
    Run COMBA pipeline, yielding (node_name, state_update) per step.

    Args:
        nl_input: Natural language or XML description.
        module_name: Optional module name override.
        xml_description: Optional pre-existing XML (skips converter).
        llm: Optional LLM instance (uses singleton if None).

    Yields:
        (node_name, state_update) tuples for each pipeline step.
    """
    _, graph = get_pipeline(llm)
    state = _prepare_state(nl_input, module_name, xml_description, dataset_dir, benchmark_id)
    config = {"recursion_limit": 100}

    for event in graph.stream(state, config):
        for node_name, state_update in event.items():
            yield node_name, state_update


# ──────────────────────────────────────────────────────────────
# Batch Evaluation
# ──────────────────────────────────────────────────────────────

def run_pipeline_batch(
    module_paths: List[str],
    description_type: str = "xml",
    samples: int = 1,
    llm=None,
) -> dict:
    """
    Run COMBA pipeline on multiple modules (evaluation mode).

    For each module directory:
      1. Read design_description.{xml|txt}
      2. Run pipeline with optional repeated samples
      3. Save per-module JSON report
      4. Print summary

    Args:
        module_paths: List of glob patterns or paths to module directories.
        description_type: "xml", "txt", or custom extension.
        samples: Number of trials per module.
        llm: Optional LLM override.

    Returns:
        Dict mapping module_name → report_data.
    """
    from comba_pipeline import make_initial_state

    # Resolve globs
    resolved_paths = []
    for mp in module_paths:
        resolved_paths.extend(glob.glob(mp))
    module_norm_paths = [os.path.normpath(p) for p in resolved_paths]

    total = len(module_norm_paths)
    if total == 0:
        print("[COMBA] No modules found matching given paths")
        return {}

    # Init pipeline once
    pipeline_llm, graph = get_pipeline(llm)
    print(f"[COMBA] Batch: {total} modules × {samples} sample(s)")

    all_results = {}

    for idx, module_path in enumerate(module_norm_paths, 1):
        module_name = os.path.basename(module_path)
        print(f"\n{'═' * 60}")
        print(f"  [{idx}/{total}] Module: {module_name}")
        print(f"{'═' * 60}")

        # Resolve description file
        if description_type == "xml":
            desc_file = os.path.join(module_path, "design_description.xml")
        elif description_type == "txt":
            desc_file = os.path.join(module_path, "design_description.txt")
        else:
            desc_file = os.path.join(module_path, f"design_description.{description_type}")

        if not os.path.isfile(desc_file):
            print(f"  ⚠️ Description file not found: {desc_file}, skipping")
            continue

        with open(desc_file, "r", encoding="utf-8") as f:
            description = f.read()

        sample_results = []

        for sample_idx in range(1, samples + 1):
            if samples > 1:
                print(f"  ── Sample {sample_idx}/{samples} ──")

            # Build state
            state = make_initial_state(nl_input=description, module_name=module_name)
            if description_type == "xml":
                state["xml_description"] = description

            try:
                config = {"recursion_limit": 100}
                final = graph.invoke(state, config)

                result = {
                    "module_name": module_name,
                    "description_type": description_type,
                    "final_status": final.get("final_status", "unknown"),
                    "sc_trial": final.get("sc_trial", 0),
                    "ts_trial": final.get("ts_trial", 0),
                    "total_iter": final.get("total_iter", 0),
                    "gvd": final.get("gvd", ""),
                    "xml_description": final.get("xml_description", ""),
                    "sc_log": final.get("sc_log", ""),
                    "tb_log": final.get("tb_log", ""),
                    "error": final.get("error"),
                    "edtm": final.get("edtm", {}),
                }

                status = result["final_status"]
                emoji = "🎉" if status == "pass" else "❌"
                print(f"  {emoji} Result: {status} | SC:{result['sc_trial']} TS:{result['ts_trial']}")

            except Exception as e:
                result = {
                    "module_name": module_name,
                    "description_type": description_type,
                    "final_status": "error",
                    "error": str(e),
                    "sc_trial": 0, "ts_trial": 0, "total_iter": 0,
                    "gvd": "", "xml_description": "", "sc_log": "", "tb_log": "",
                }
                print(f"  ❌ Pipeline error: {e}")

            sample_results.append(result)

        # Save per-module report
        reports_dir = os.path.join(module_path, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        report_path = os.path.join(reports_dir, f"report_langgraph.{description_type}.json")
        report_data = {
            "module_name": module_name,
            "description_type": description_type,
            "samples": sample_results if samples > 1 else sample_results[0],
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print(f"  📄 Report saved: {report_path}")
        all_results[module_name] = report_data

    # Summary
    print(f"\n{'═' * 60}")
    print("  SUMMARY")
    print(f"{'═' * 60}")
    pass_count = 0
    for name, data in all_results.items():
        if isinstance(data["samples"], list):
            passed_samples = [x for x in data["samples"] if x.get("final_status") == "pass"]
            r = passed_samples[0] if passed_samples else data["samples"][0]
        else:
            r = data["samples"]
            
        status = r.get("final_status", "?")
        if status == "pass":
            pass_count += 1
        emoji = "✅" if status == "pass" else "❌"
        print(f"  {emoji} {name}: {status} (SC:{r.get('sc_trial',0)} TS:{r.get('ts_trial',0)})")

    if total > 0:
        print(f"\n  Pass rate: {pass_count}/{total} ({pass_count/total*100:.1f}%)")

    # Save global summary
    os.makedirs("reports", exist_ok=True)
    summary_path = f"reports/summary_langgraph.{description_type}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  📄 Global summary: {summary_path}")

    # Export Markdown summary
    md_path = _export_markdown_summary(all_results, description_type, samples, total)
    print(f"  📝 Markdown summary: {md_path}")

    return all_results


# ──────────────────────────────────────────────────────────────
# Markdown Summary Exporter
# ──────────────────────────────────────────────────────────────

def _export_markdown_summary(
    all_results: dict,
    description_type: str,
    samples: int,
    total: int,
) -> str:
    """
    Write a human-readable Markdown summary of the batch run.

    File is saved to:
        reports/summary_langgraph.<description_type>.md

    Returns the path of the written file.
    """
    import datetime

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    # ── Aggregate stats ──────────────────────────────────────
    pass_count = 0
    fail_sc = 0
    fail_ts = 0
    fail_other = 0
    total_sc_trials = 0
    total_ts_trials = 0
    total_iters = 0
    counted = 0

    rows = []
    for name, data in all_results.items():
        s = data.get("samples")
        # Normalise: single-sample run stores a dict, multi stores a list
        if isinstance(s, list):
            passed_samples = [x for x in s if x.get("final_status") == "pass"]
            r = passed_samples[0] if passed_samples else s[0]
        else:
            r = s or {}

        status = r.get("final_status", "?")
        sc = r.get("sc_trial", 0)
        ts = r.get("ts_trial", 0)
        iters = r.get("total_iter", 0)
        err = r.get("error") or ""

        if status == "pass":
            pass_count += 1
            icon = "✅"
        elif status == "fail_sc":
            fail_sc += 1
            icon = "❌"
        elif status == "fail_ts":
            fail_ts += 1
            icon = "❌"
        else:
            fail_other += 1
            icon = "💥" if status == "error" else "⚠️"

        total_sc_trials += sc
        total_ts_trials += ts
        total_iters += iters
        counted += 1

        # Truncate long error strings for the table
        short_err = (err[:60] + "…") if len(err) > 60 else err

        rows.append((icon, name, status, sc, ts, iters, short_err))

    n = counted or 1
    pass_pct = pass_count / n * 100
    avg_sc = total_sc_trials / n
    avg_ts = total_ts_trials / n
    avg_iter = total_iters / n

    # ── Build Markdown ────────────────────────────────────────
    lines = [
        f"# COMBA Pipeline — Batch Summary",
        f"",
        f"| Key | Value |",
        f"| --- | ----- |",
        f"| **Run timestamp** | `{timestamp}` |",
        f"| **Description type** | `{description_type}` |",
        f"| **Samples per module** | {samples} |",
        f"| **Total modules** | {total} |",
        f"| **Passed** | {pass_count} / {total} ({pass_pct:.1f}%) |",
        f"| **Failed (syntax)** | {fail_sc} |",
        f"| **Failed (testbench)** | {fail_ts} |",
        f"| **Error / other** | {fail_other} |",
        f"| **Avg SC trials** | {avg_sc:.2f} |",
        f"| **Avg TS trials** | {avg_ts:.2f} |",
        f"| **Avg total iterations** | {avg_iter:.2f} |",
        f"",
        f"---",
        f"",
        f"## Per-Module Results",
        f"",
        f"| # | Status | Module | Final Status | SC Trials | TS Trials | Total Iter | Error |",
        f"| - | ------ | ------ | ------------ | --------- | --------- | ---------- | ----- |",
    ]

    for idx, (icon, name, status, sc, ts, iters, err) in enumerate(rows, 1):
        lines.append(
            f"| {idx} | {icon} | `{name}` | `{status}` | {sc} | {ts} | {iters} | {err} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"*Generated by COMBA pipeline runner · {timestamp}*",
        f"*Full JSON: `reports/summary_langgraph.{description_type}.json`*",
    ]

    md_content = "\n".join(lines)

    # ── Write file ────────────────────────────────────────────
    os.makedirs("reports", exist_ok=True)
    md_path = f"reports/summary_langgraph.{description_type}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return md_path

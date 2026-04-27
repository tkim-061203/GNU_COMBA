"""
COMBA Pipeline Runner — Shared module for api_server.py and run.py.

Provides:
    create_llm()              — Unified LLM factory (StubLLM → COMBALlm → ChatOpenAI)
    get_pipeline(llm)         — Lazy-init singleton graph
    run_pipeline_sync()       — Run full pipeline, return final state
                                (auto-dispatches to multi_sample if SC=1)
    run_pipeline_streaming()  — Yield (node_name, state_update) per step
    run_pipeline_batch()      — Batch evaluation over module directories
                                (auto-dispatches to multi_sample if SC=1)
"""

import os
import re
import json
import glob
import sys
from typing import Optional, List, Iterator, Tuple

from dotenv import load_dotenv

load_dotenv()

COMBA_QUIET = os.environ.get("COMBA_QUIET", "0") == "1"

def cprint(*args, **kwargs):
    if not COMBA_QUIET:
        print(*args, **kwargs)


# ──────────────────────────────────────────────────────────────
# Self-Consistency Detection
# ──────────────────────────────────────────────────────────────

def _is_sc_enabled() -> bool:
    """Check env flag COMBA_SELF_CONSISTENCY=1."""
    return os.environ.get("COMBA_SELF_CONSISTENCY", "0") == "1"


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
        cprint("[COMBA] Using StubLLM (testing mode)")
        return create_stub_llm()

    try:
        from llm_interface import COMBALlm
        llm = COMBALlm.from_env()
        cprint(f"[COMBA] Using COMBALlm: {llm}")
        return llm
    except Exception as e:
        cprint(f"[COMBA] COMBALlm failed ({e}), falling back to ChatOpenAI")

    from langchain_openai import ChatOpenAI
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
    api_key = os.environ.get("LLM_API_KEY", "ollama")
    model = os.environ.get("LLM_MODEL", "generator")
    cprint(f"[COMBA] Using ChatOpenAI: {model} @ {base_url}")
    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model, temperature=0.1)


# ──────────────────────────────────────────────────────────────
# Pipeline Singleton
# ──────────────────────────────────────────────────────────────

_llm = None
_graph = None


def get_pipeline(llm=None):
    """Lazy-init and return (llm, graph) tuple."""
    global _llm, _graph

    if _graph is not None and llm is None:
        return _llm, _graph

    if llm is None:
        llm = create_llm()

    from comba_pipeline import build_comba_graph
    _llm = llm
    _graph = build_comba_graph(llm)
    cprint("[COMBA] Pipeline graph compiled")
    return _llm, _graph


def reset_pipeline():
    """Reset the singleton (useful for tests)."""
    global _llm, _graph
    _llm = None
    _graph = None


# ──────────────────────────────────────────────────────────────
# State preparation
# ──────────────────────────────────────────────────────────────

def _prepare_state(
    nl_input: str,
    module_name: Optional[str] = None,
    xml_description: Optional[str] = None,
    dataset_dir: Optional[str] = None,
    benchmark_id: Optional[str] = None,
    work_dir: Optional[str] = None,
    desc_type: str = "xml",
) -> dict:
    """Build initial COMBAState, optionally injecting XML and a pre-created work_dir."""
    from comba_pipeline import make_initial_state

    state = make_initial_state(
        nl_input=nl_input,
        module_name=module_name or "",
        benchmark_id=benchmark_id or "",
        work_dir=work_dir,
    )
    if not dataset_dir:
        base_dir = os.path.dirname(__file__)
        possible_dir = os.path.abspath(os.path.join(base_dir, "../../ext/verilog-eval/dataset_code-complete-iccad2023"))
        if os.path.isdir(possible_dir):
            dataset_dir = possible_dir

    if dataset_dir:
        state["dataset_dir"] = dataset_dir

    if work_dir:
        os.makedirs(work_dir, exist_ok=True)

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

    if desc_type == "txt" and not state.get("xml_description"):
        state["xml_description"] = "(Bypassed XML; Using TXT mode)"

    return state


# ──────────────────────────────────────────────────────────────
# Pipeline runners (SC-aware)
# ──────────────────────────────────────────────────────────────

def run_pipeline_sync(
    nl_input: str,
    module_name: Optional[str] = None,
    xml_description: Optional[str] = None,
    llm=None,
    dataset_dir: Optional[str] = None,
    benchmark_id: Optional[str] = None,
    work_dir: Optional[str] = None,
    desc_type: str = "xml",
    _sc_bypass: bool = False,
) -> dict:
    """
    Run COMBA pipeline.

    If COMBA_SELF_CONSISTENCY=1 and not _sc_bypass, dispatches to
    multi_sample.run_with_self_consistency() for hierarchical best-of-N.
    Otherwise runs the graph once (legacy single-pass behavior).

    `_sc_bypass=True` is used internally by multi_sample to avoid recursion.
    """
    if _is_sc_enabled() and not _sc_bypass:
        try:
            from multi_sample import run_with_self_consistency
            pipeline_llm, _ = get_pipeline(llm)
            return run_with_self_consistency(
                nl_input=nl_input,
                module_name=module_name,
                xml_description=xml_description,
                llm=pipeline_llm,
                dataset_dir=dataset_dir,
                benchmark_id=benchmark_id,
                work_dir=work_dir,
                desc_type=desc_type,
            )
        except ImportError as e:
            cprint(f"[COMBA] multi_sample not available ({e}), running single-pass")

    _, graph = get_pipeline(llm)
    state = _prepare_state(
        nl_input, module_name, xml_description,
        dataset_dir, benchmark_id, work_dir, desc_type,
    )
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
    Streaming mode does NOT support self-consistency (single-pass only).
    """
    _, graph = get_pipeline(llm)
    state = _prepare_state(nl_input, module_name, xml_description, dataset_dir, benchmark_id)
    config = {"recursion_limit": 100}

    for event in graph.stream(state, config):
        for node_name, state_update in event.items():
            yield node_name, state_update


# ──────────────────────────────────────────────────────────────
# Batch Evaluation (with SC dispatcher)
# ──────────────────────────────────────────────────────────────

def _run_one_module(
    description: str,
    module_name: str,
    description_type: str,
    sample_dataset_dir: Optional[str],
    pipeline_llm,
    graph,
) -> dict:
    """
    Run pipeline for one module. Dispatches to multi_sample if SC=1.

    Returns a state dict with optional `self_consistency` metadata.
    """
    if _is_sc_enabled():
        try:
            from multi_sample import run_with_self_consistency
            return run_with_self_consistency(
                nl_input=description,
                module_name=module_name,
                xml_description=description if description_type == "xml" else None,
                llm=pipeline_llm,
                dataset_dir=sample_dataset_dir,
                benchmark_id=module_name,
                desc_type=description_type,
            )
        except ImportError as e:
            cprint(f"[COMBA] multi_sample import failed ({e}), single-pass fallback")

    state = _prepare_state(
        nl_input=description,
        module_name=module_name,
        xml_description=description if description_type == "xml" else None,
        dataset_dir=sample_dataset_dir,
        desc_type=description_type,
    )
    config = {"recursion_limit": 100}
    return graph.invoke(state, config)


def run_pipeline_batch(
    module_paths: List[str],
    description_type: str = "xml",
    samples: int = 1,
    llm=None,
    dataset_dir: Optional[str] = None,
) -> dict:
    """
    Run COMBA pipeline on multiple modules (evaluation mode).

    Auto-dispatches to multi_sample.run_with_self_consistency when
    COMBA_SELF_CONSISTENCY=1 is set in env.
    """
    from comba_pipeline import make_initial_state

    resolved_paths = []
    for mp in module_paths:
        resolved_paths.extend(glob.glob(mp))
    module_norm_paths = [os.path.normpath(p) for p in resolved_paths]

    total = len(module_norm_paths)
    if total == 0:
        cprint("[COMBA] No modules found matching given paths")
        return {}

    pipeline_llm, graph = get_pipeline(llm)
    sc_active = _is_sc_enabled()
    cprint(
        f"[COMBA] Batch: {total} modules × {samples} sample(s) "
        f"| SC={'ON' if sc_active else 'OFF'}"
    )

    all_results = {}

    for idx, module_path in enumerate(module_norm_paths, 1):
        module_name = os.path.basename(module_path)
        cprint(f"\n{'═' * 60}")
        cprint(f"  [{idx}/{total}] Module: {module_name}")
        cprint(f"{'═' * 60}")

        if description_type == "xml":
            desc_file = os.path.join(module_path, "design_description.xml")
        elif description_type == "txt":
            desc_file = os.path.join(module_path, "design_description.txt")
        else:
            desc_file = os.path.join(module_path, f"design_description.{description_type}")

        if not os.path.isfile(desc_file):
            cprint(f"  ⚠️ Description file not found: {desc_file}, skipping")
            continue

        with open(desc_file, "r", encoding="utf-8") as f:
            description = f.read()

        cprint(f"\n[MODULE {idx}] {module_name}")
        sample_results = []

        for sample_idx in range(1, samples + 1):
            if samples > 1:
                cprint(f"  ── Trial {sample_idx}/{samples} ──")

            sample_dataset_dir = dataset_dir
            if not sample_dataset_dir and "RTLLM" in module_path:
                sample_dataset_dir = module_path

            try:
                final = _run_one_module(
                    description=description,
                    module_name=module_name,
                    description_type=description_type,
                    sample_dataset_dir=sample_dataset_dir,
                    pipeline_llm=pipeline_llm,
                    graph=graph,
                )

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

                # Preserve SC metadata for analyze_self_consistency.py
                if "self_consistency" in final:
                    result["self_consistency"] = final["self_consistency"]
                # Preserve guard summary
                if "guard_summary" in final:
                    result["guard_summary"] = final["guard_summary"]

                status = result["final_status"]
                emoji = "🎉" if status == "pass" else "❌"

                sc_meta = result.get("self_consistency")
                if sc_meta:
                    cprint(
                        f"  {emoji} Result: {status} | SC:{result['sc_trial']} "
                        f"TS:{result['ts_trial']} | "
                        f"BoN: {sc_meta['samples_run']}/{sc_meta['max_samples']} "
                        f"(best=s{sc_meta['best_sample_idx']})"
                    )
                else:
                    cprint(f"  {emoji} Result: {status} | SC:{result['sc_trial']} TS:{result['ts_trial']}")

            except Exception as e:
                result = {
                    "module_name": module_name,
                    "description_type": description_type,
                    "final_status": "error",
                    "error": str(e),
                    "sc_trial": 0, "ts_trial": 0, "total_iter": 0,
                    "gvd": "", "xml_description": "", "sc_log": "", "tb_log": "",
                }
                cprint(f"  ❌ Pipeline error: {e}")

            sample_results.append(result)

        reports_dir = os.path.join(module_path, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        report_path = os.path.join(reports_dir, f"report_langgraph.{description_type}.json")
        report_data = {
            "module_name": module_name,
            "description_type": description_type,
            "self_consistency_enabled": sc_active,
            "samples": sample_results if samples > 1 else sample_results[0],
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        cprint(f"  📄 Report saved: {report_path}")
        all_results[module_name] = report_data

    cprint(f"\n{'═' * 60}")
    cprint("  SUMMARY")
    cprint(f"{'═' * 60}")
    pass_count = 0
    sc_recovered = 0
    for name, data in all_results.items():
        if isinstance(data["samples"], list):
            passed_samples = [x for x in data["samples"] if x.get("final_status") == "pass"]
            r = passed_samples[0] if passed_samples else data["samples"][0]
        else:
            r = data["samples"]

        status = r.get("final_status", "?")
        if status == "pass":
            pass_count += 1
            sc_meta = r.get("self_consistency")
            if sc_meta and sc_meta.get("best_sample_idx", 0) > 0:
                sc_recovered += 1

        emoji = "✅" if status == "pass" else "❌"
        cprint(f"  {emoji} {name}: {status} (SC:{r.get('sc_trial',0)} TS:{r.get('ts_trial',0)})")

    if total > 0:
        cprint(f"\n  Pass rate: {pass_count}/{total} ({pass_count/total*100:.1f}%)")
        if sc_active and sc_recovered > 0:
            cprint(f"  SC recovered: {sc_recovered} module(s) needed Tier 2 retries")

    os.makedirs("reports", exist_ok=True)
    summary_path = f"reports/summary_langgraph.{description_type}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    cprint(f"  📄 Global summary: {summary_path}")

    md_path = _export_markdown_summary(all_results, description_type, samples, total)
    cprint(f"  📝 Markdown summary: {md_path}")

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
    """Write a human-readable Markdown summary of the batch run."""
    import datetime

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    sc_active = _is_sc_enabled()

    pass_count = 0
    fail_sc = 0
    fail_ts = 0
    fail_other = 0
    total_sc_trials = 0
    total_ts_trials = 0
    total_iters = 0
    counted = 0
    sc_recovered = 0
    sc_total_samples = 0

    rows = []
    for name, data in all_results.items():
        s = data.get("samples")
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
        sc_meta = r.get("self_consistency") or {}

        if status == "pass":
            pass_count += 1
            icon = "✅"
            if sc_meta.get("best_sample_idx", 0) > 0:
                sc_recovered += 1
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
        if sc_meta.get("samples_run"):
            sc_total_samples += sc_meta["samples_run"]
        counted += 1

        short_err = (err[:60] + "…") if len(err) > 60 else err
        bon = sc_meta.get("samples_run", 1)
        best_idx = sc_meta.get("best_sample_idx", 0)

        rows.append((icon, name, status, sc, ts, iters, bon, best_idx, short_err))

    n = counted or 1
    pass_pct = pass_count / n * 100
    avg_sc = total_sc_trials / n
    avg_ts = total_ts_trials / n
    avg_iter = total_iters / n
    avg_samples = sc_total_samples / n if sc_active else 1.0

    lines = [
        f"# COMBA Pipeline — Batch Summary",
        f"",
        f"| Key | Value |",
        f"| --- | ----- |",
        f"| **Run timestamp** | `{timestamp}` |",
        f"| **Description type** | `{description_type}` |",
        f"| **Trials per module** | {samples} |",
        f"| **Self-consistency** | `{'ON' if sc_active else 'OFF'}` |",
        f"| **Total modules** | {total} |",
        f"| **Passed** | {pass_count} / {total} ({pass_pct:.1f}%) |",
        f"| **Failed (syntax)** | {fail_sc} |",
        f"| **Failed (testbench)** | {fail_ts} |",
        f"| **Error / other** | {fail_other} |",
        f"| **Avg SC trials** | {avg_sc:.2f} |",
        f"| **Avg TS trials** | {avg_ts:.2f} |",
        f"| **Avg total iterations** | {avg_iter:.2f} |",
    ]
    if sc_active:
        lines.extend([
            f"| **Avg samples / module** | {avg_samples:.2f} |",
            f"| **SC-recovered (Tier 2 saved)** | {sc_recovered} |",
        ])

    lines += [
        f"",
        f"---",
        f"",
        f"## Per-Module Results",
        f"",
    ]

    if sc_active:
        lines += [
            f"| # | Status | Module | Final | SC | TS | Iter | BoN | Best | Error |",
            f"| - | ------ | ------ | ----- | -- | -- | ---- | --- | ---- | ----- |",
        ]
        for idx, (icon, name, status, sc, ts, iters, bon, best_idx, err) in enumerate(rows, 1):
            lines.append(
                f"| {idx} | {icon} | `{name}` | `{status}` | {sc} | {ts} | "
                f"{iters} | {bon} | s{best_idx} | {err} |"
            )
    else:
        lines += [
            f"| # | Status | Module | Final Status | SC Trials | TS Trials | Total Iter | Error |",
            f"| - | ------ | ------ | ------------ | --------- | --------- | ---------- | ----- |",
        ]
        for idx, (icon, name, status, sc, ts, iters, bon, best_idx, err) in enumerate(rows, 1):
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

    os.makedirs("reports", exist_ok=True)
    md_path = f"reports/summary_langgraph.{description_type}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return md_path
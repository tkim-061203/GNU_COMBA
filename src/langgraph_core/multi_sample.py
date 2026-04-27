"""
multi_sample.py — Hierarchical Self-Consistency for COMBA Pipeline.

Wraps run_pipeline_sync() with N-sample best-of-N selection.

Strategy:
    Tier 1: Sample 0 at T=0.0 (deterministic baseline)
            → if pass → return immediately (1× cost, 60% of cases)
    Tier 2: Samples 1..N-1 at increasing temperature
            → run full pipeline per sample
            → score each by (status, errs, size, idx)
            → early exit on first PASS
            → return best across all samples

Score priority (higher = better):
    (status_rank, -tb_err, -sc_err, -gvd_size, -sample_idx)

Integration:
    from multi_sample import run_with_self_consistency
    state = run_with_self_consistency(
        nl_input=..., module_name=..., xml_description=...,
        llm=llm, dataset_dir=..., benchmark_id=...,
        max_samples=5,
    )
"""

import os
import re
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Tuple, Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Config (env-overridable)
# ──────────────────────────────────────────────────────────────

DEFAULT_MAX_SAMPLES   = int(os.getenv("COMBA_MAX_SAMPLES", "5"))
DEFAULT_EARLY_EXIT    = os.getenv("COMBA_EARLY_EXIT", "1") == "1"
DEFAULT_WALL_BUDGET_S = float(os.getenv("COMBA_WALL_BUDGET", "0"))  # 0 = no budget

# Temperature schedule: idx 0 baseline, ramp up for diversity
DEFAULT_TEMPERATURES = (0.0, 0.5, 0.5, 0.8, 0.8, 1.0, 1.0, 1.0)

# Diversity hints injected into the GENERATOR system message for sample idx > 0.
# idx 0 is intentionally None (deterministic baseline = current behavior).
DIVERSITY_HINTS = (
    None,
    "DIVERSITY HINT: Try a structurally different approach this time.",
    "DIVERSITY HINT: Prefer a case statement over chained if-else where applicable.",
    "DIVERSITY HINT: Use explicit width casting; avoid implicit truncation.",
    "DIVERSITY HINT: Decompose into multiple always blocks if it improves clarity.",
    "DIVERSITY HINT: Reconsider register vs wire choices and reset polarity.",
    "DIVERSITY HINT: Add explicit default cases and ensure all states are reachable.",
    "DIVERSITY HINT: Use parameter literals instead of hardcoded magic numbers.",
)

DIVERSITY_ENABLED = os.getenv("COMBA_DIVERSITY_HINTS", "1") == "1"

# Status → numeric rank for scoring (higher = better)
STATUS_RANK = {
    "pass":             100,
    "fail_ts":           50,
    "fail_ts_tb_bug":    45,   # see roadmap item (e)
    "fail_sc":           20,
    "max_iter":          10,
    "fail_extraction":    5,
    "fail_extraction_max_retries": 3,
    None:                 0,
    "?":                  0,
}


# ──────────────────────────────────────────────────────────────
# Sample result + scoring
# ──────────────────────────────────────────────────────────────

@dataclass
class SampleResult:
    """One run of the full pipeline at a given temperature."""
    sample_idx: int
    temperature: float
    final_status: Optional[str]
    sc_trial: int
    ts_trial: int
    total_iter: int
    gvd: str
    sc_err_count: int
    tb_err_count: int
    elapsed_s: float
    state: dict = field(repr=False)

    @property
    def score(self) -> Tuple[int, int, int, int, int]:
        """Higher = better. Tie-break: prefer earlier sample (determinism)."""
        return (
            STATUS_RANK.get(self.final_status, 0),
            -self.tb_err_count,
            -self.sc_err_count,
            -len(self.gvd or ""),
            -self.sample_idx,
        )

    def summary(self) -> dict:
        return {
            "idx": self.sample_idx,
            "T": self.temperature,
            "status": self.final_status,
            "sc_trial": self.sc_trial,
            "ts_trial": self.ts_trial,
            "iter": self.total_iter,
            "sc_err": self.sc_err_count,
            "tb_err": self.tb_err_count,
            "gvd_lines": len(self.gvd.splitlines()) if self.gvd else 0,
            "elapsed_s": round(self.elapsed_s, 2),
        }


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

_RE_ERR_LINE = re.compile(r"^\s*(?:%?Error|error)[: ]", re.M)


def _count_errors(log: Optional[str]) -> int:
    """Count distinct error-style lines in a tool log."""
    if not log:
        return 0
    return len(_RE_ERR_LINE.findall(log))


def _set_temperature(llm: Any, T: float) -> Optional[float]:
    """Mutate llm.temperature, return previous value (for restore)."""
    if llm is None:
        return None
    prev = getattr(llm, "temperature", None)
    try:
        # COMBALlm has Pydantic field 'temperature'
        if hasattr(llm, "temperature"):
            llm.temperature = T
    except Exception as e:
        logger.warning(f"[multi_sample] could not set temperature on {type(llm).__name__}: {e}")
    return prev


def _restore_temperature(llm: Any, prev: Optional[float]) -> None:
    if llm is None or prev is None:
        return
    try:
        llm.temperature = prev
    except Exception:
        pass


def _install_diversity_hint(llm: Any, hint: Optional[str]) -> Optional[Any]:
    """
    Monkey-patch llm._call to prepend a diversity hint to the system message
    of base-mode (generator) calls only. Debugger calls are untouched.

    Returns the original method for restoration. Returns None if patching
    is not applicable (no _call attr, or hint is None).
    """
    if hint is None or llm is None or not hasattr(llm, "_call"):
        return None

    original = llm._call

    def _patched(messages, client_mode, temperature, max_tokens, **kwargs):
        # Only inject for generator (base mode); never touch debugger
        if client_mode == "base" and messages:
            # find first system message and append the hint
            patched_msgs = []
            injected = False
            for m in messages:
                if not injected and m.get("role") == "system":
                    patched_msgs.append({
                        "role": "system",
                        "content": m["content"] + "\n\n" + hint,
                    })
                    injected = True
                else:
                    patched_msgs.append(m)
            if not injected:
                # no system message found — prepend a fresh one
                patched_msgs = [{"role": "system", "content": hint}] + list(messages)
            messages = patched_msgs

        return original(
            messages, client_mode=client_mode,
            temperature=temperature, max_tokens=max_tokens, **kwargs,
        )

    llm._call = _patched
    return original


def _restore_call(llm: Any, original: Optional[Any]) -> None:
    if llm is None or original is None:
        return
    try:
        llm._call = original
    except Exception:
        pass


def _build_sample_result(
    idx: int, T: float, state: dict, elapsed: float,
) -> SampleResult:
    return SampleResult(
        sample_idx=idx,
        temperature=T,
        final_status=state.get("final_status"),
        sc_trial=state.get("sc_trial", 0),
        ts_trial=state.get("ts_trial", 0),
        total_iter=state.get("total_iter", 0),
        gvd=state.get("gvd") or "",
        sc_err_count=_count_errors(state.get("sc_log")),
        tb_err_count=_count_errors(state.get("tb_log")),
        elapsed_s=elapsed,
        state=state,
    )


# ──────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────

def run_with_self_consistency(
    nl_input: str,
    module_name: Optional[str] = None,
    xml_description: Optional[str] = None,
    llm: Any = None,
    dataset_dir: Optional[str] = None,
    benchmark_id: Optional[str] = None,
    work_dir: Optional[str] = None,
    desc_type: Optional[str] = None,
    *,
    max_samples: int = DEFAULT_MAX_SAMPLES,
    temperature_schedule: Tuple[float, ...] = DEFAULT_TEMPERATURES,
    early_exit: bool = DEFAULT_EARLY_EXIT,
    wall_budget_s: float = DEFAULT_WALL_BUDGET_S,
) -> dict:
    """
    Hierarchical best-of-N around run_pipeline_sync.

    Returns: final state dict with extra key `self_consistency` holding metadata.
    The returned `gvd`, `final_status`, etc. are from the BEST sample.
    """
    # Lazy import to avoid circular deps
    from pipeline_runner import run_pipeline_sync

    samples: List[SampleResult] = []
    t_start = time.time()

    for idx in range(max(1, max_samples)):
        # ── pick temperature ──
        T = temperature_schedule[min(idx, len(temperature_schedule) - 1)]

        # ── per-sample work_dir to avoid file collisions ──
        sample_work_dir = None
        if work_dir:
            sample_work_dir = f"{work_dir.rstrip('/')}__s{idx}"
        # if caller didn't pass work_dir, run_pipeline_sync creates its own

        # ── set temperature, run, restore ──
        prev_T = _set_temperature(llm, T)

        # ── set diversity hint for sample idx > 0 ──
        hint = None
        if DIVERSITY_ENABLED and idx > 0 and idx < len(DIVERSITY_HINTS):
            hint = DIVERSITY_HINTS[idx]
        original_call = _install_diversity_hint(llm, hint) if hint else None

        t0 = time.time()
        try:
            state = run_pipeline_sync(
                nl_input=nl_input,
                module_name=module_name,
                xml_description=xml_description,
                llm=llm,
                dataset_dir=dataset_dir,
                benchmark_id=benchmark_id,
                work_dir=sample_work_dir,
                desc_type=desc_type,
                _sc_bypass=True,   # prevent infinite recursion
            )
        except Exception as e:
            logger.error(f"[multi_sample] sample {idx} crashed: {e}")
            state = {"final_status": "fail_extraction", "error": str(e), "gvd": ""}
        finally:
            _restore_temperature(llm, prev_T)
            _restore_call(llm, original_call)
        elapsed = time.time() - t0

        result = _build_sample_result(idx, T, state, elapsed)
        # tag the sample with the hint used (for analysis)
        if hint:
            result.state["_diversity_hint"] = hint
        samples.append(result)

        logger.info(
            f"[multi_sample] {module_name or 'module'} sample {idx} "
            f"T={T} → {result.final_status} ({elapsed:.1f}s)"
            + (f" [hint: {hint[:40]}...]" if hint else "")
        )

        # ── early exit checks ──
        if early_exit and result.final_status == "pass":
            logger.info(f"[multi_sample] early exit on sample {idx} (PASS)")
            break

        if wall_budget_s > 0 and (time.time() - t_start) > wall_budget_s:
            logger.warning(
                f"[multi_sample] wall budget {wall_budget_s}s exceeded after sample {idx}"
            )
            break

    # ── pick best ──
    best = max(samples, key=lambda s: s.score)

    # ── annotate state ──
    final_state = dict(best.state)
    final_state["self_consistency"] = {
        "samples_run": len(samples),
        "max_samples": max_samples,
        "best_sample_idx": best.sample_idx,
        "best_temperature": best.temperature,
        "best_status": best.final_status,
        "early_exit": (best.final_status == "pass"),
        "total_elapsed_s": round(time.time() - t_start, 2),
        "all_samples": [s.summary() for s in samples],
    }

    logger.info(
        f"[multi_sample] {module_name or 'module'} BEST = sample {best.sample_idx} "
        f"({best.final_status}) | {len(samples)}/{max_samples} samples"
    )
    return final_state


# ──────────────────────────────────────────────────────────────
# Convenience: should we use self-consistency? (env gate)
# ──────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """Check env flag COMBA_SELF_CONSISTENCY."""
    return os.getenv("COMBA_SELF_CONSISTENCY", "0") == "1"


# ──────────────────────────────────────────────────────────────
# Self-test (run with `python multi_sample.py`)
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test 1: scoring tuple ordering
    s_pass = SampleResult(0, 0.0, "pass", 1, 1, 2, "module x; endmodule", 0, 0, 1.0, {})
    s_fts  = SampleResult(1, 0.5, "fail_ts", 5, 5, 10, "module x;...endmodule", 0, 1, 5.0, {})
    s_fsc  = SampleResult(2, 0.5, "fail_sc", 10, 0, 10, "garbage", 5, 0, 3.0, {})
    s_max  = SampleResult(3, 0.8, "max_iter", 5, 5, 20, "x", 1, 1, 6.0, {})
    samples = [s_fsc, s_max, s_fts, s_pass]
    best = max(samples, key=lambda s: s.score)
    assert best is s_pass, f"expected pass, got {best.final_status}"
    print(f"  test 1 OK: best = sample {best.sample_idx} ({best.final_status})")

    # Test 2: same status, fewer errors wins
    a = SampleResult(0, 0.0, "fail_ts", 5, 5, 10, "x", 0, 3, 5.0, {})
    b = SampleResult(1, 0.5, "fail_ts", 5, 5, 10, "x", 0, 1, 5.0, {})
    best = max([a, b], key=lambda s: s.score)
    assert best is b, "expected sample with fewer tb_err"
    print(f"  test 2 OK: tied status → fewer errs")

    # Test 3: same status+errs, shorter GVD wins
    a = SampleResult(0, 0.0, "fail_ts", 5, 5, 10, "AAAAAAAAAA", 0, 1, 5.0, {})
    b = SampleResult(1, 0.5, "fail_ts", 5, 5, 10, "AAA", 0, 1, 5.0, {})
    best = max([a, b], key=lambda s: s.score)
    assert best is b, "expected shorter gvd to win"
    print(f"  test 3 OK: tied errs → shorter GVD")

    # Test 4: same status+errs+size, earlier sample wins (determinism)
    a = SampleResult(0, 0.0, "fail_ts", 5, 5, 10, "X", 0, 1, 5.0, {})
    b = SampleResult(1, 0.5, "fail_ts", 5, 5, 10, "X", 0, 1, 5.0, {})
    best = max([a, b], key=lambda s: s.score)
    assert best is a, "expected earlier sample (determinism)"
    print(f"  test 4 OK: tied all → earlier sample")

    # Test 5: error counter
    log = "%Error: foo\n%Error: bar\nWarning: baz\nerror: qux\n"
    assert _count_errors(log) == 3
    assert _count_errors("") == 0
    assert _count_errors(None) == 0
    print(f"  test 5 OK: error counter = 3")

    # Test 6: temperature get/set/restore (with mock)
    class MockLLM:
        temperature = 0.1
    m = MockLLM()
    prev = _set_temperature(m, 0.7)
    assert m.temperature == 0.7
    assert prev == 0.1
    _restore_temperature(m, prev)
    assert m.temperature == 0.1
    print(f"  test 6 OK: temperature mutation")

    # Test 7: diversity injection patches base mode only
    captured = []

    class MockLLMCall:
        temperature = 0.1
        def _call(self, messages, client_mode, temperature, max_tokens, **kw):
            captured.append((client_mode, list(messages)))
            return "ok"

    llm = MockLLMCall()
    orig = _install_diversity_hint(llm, "DIVERSITY HINT: test123")
    # Generator call → hint injected
    llm._call(
        [{"role": "system", "content": "you are a generator"},
         {"role": "user", "content": "make adder"}],
        client_mode="base", temperature=0.5, max_tokens=100,
    )
    # Debugger call → hint NOT injected
    llm._call(
        [{"role": "system", "content": "you are a debugger"},
         {"role": "user", "content": "fix bug"}],
        client_mode="debugger", temperature=0.5, max_tokens=100,
    )
    _restore_call(llm, orig)

    base_msgs = captured[0][1]
    dbg_msgs = captured[1][1]
    assert "DIVERSITY HINT: test123" in base_msgs[0]["content"], "base must contain hint"
    assert "DIVERSITY HINT" not in dbg_msgs[0]["content"], "debugger must NOT contain hint"
    print(f"  test 7 OK: diversity injects only into generator system msg")

    # Test 8: restore_call removes patch
    llm._call(
        [{"role": "system", "content": "stock"}],
        client_mode="base", temperature=0.5, max_tokens=100,
    )
    last = captured[-1][1]
    assert "DIVERSITY HINT" not in last[0]["content"], "after restore, no injection"
    print(f"  test 8 OK: _restore_call cleanly reverts patch")

    print("\n✅ All self-tests passed")
#!/usr/bin/env python3
"""Validate an auto-generated testbench by mutation testing.

Why this exists
---------------
A testbench that is merely *generated* proves nothing. A TB that passes on the
DUT may simply be blind: `initial begin $display("passed"); $finish; end` passes
every design ever written. So a generated TB is accepted only if it

  1. PASSES on the DUT as written, and
  2. FAILS on mutated copies of that DUT (one seeded bug each).

(2) is the real signal: it measures whether the TB can *detect* anything.
The fraction of mutants it rejects is the mutation score.

Honest limitation
-----------------
With no golden reference RTL (the user-supplied-RTL case), (1) only shows that
the TB and the DUT agree, not that either is correct. If both were derived from
the same wrong reading of the spec they agree and are both wrong. Only the
mutation score is evidence of TB strength, which is why the verdict below
reports a tier rather than a bare boolean.

Mutants that fail to COMPILE are excluded from the denominator: a compile error
is not the TB detecting anything, and counting it would inflate the score.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

# Matches comba_pipeline.IVERILOG_TS_FLAGS (kept local so importing this module
# does not drag in langchain and the whole pipeline).
IVERILOG_TS_FLAGS = ["-Wall", "-Winfloop", "-Wno-timescale", "-g2012"]

DEFAULT_MAX_MUTANTS = int(os.environ.get("COMBA_TB_MAX_MUTANTS", "20"))
DEFAULT_MIN_SCORE = float(os.environ.get("COMBA_TB_MUTATION_MIN", "0.6"))
COMPILE_TIMEOUT = int(os.environ.get("COMBA_TB_COMPILE_TIMEOUT", "60"))
RUN_TIMEOUT = int(os.environ.get("COMBA_TB_RUN_TIMEOUT", "60"))

# -- Mutation operators ---------------------------------------------------
# Each seeds ONE plausible RTL bug. Lookarounds keep Verilog-specific tokens
# intact: `<=` is non-blocking assignment (never a comparison to mutate),
# `+:`/`-:` are indexed part-selects, `->` is an event trigger, `===`/`!==`
# are 4-state comparisons.
MUTATIONS: list[tuple[str, re.Pattern, str]] = [
    ("add_to_sub",     re.compile(r"(?<![+\-:])\+(?![+:=])"),      "-"),
    ("sub_to_add",     re.compile(r"(?<![+\-:])-(?![-:=>])"),      "+"),
    ("eq_to_neq",      re.compile(r"(?<![=!<>])==(?!=)"),          "!="),
    ("neq_to_eq",      re.compile(r"(?<![=!<>])!=(?!=)"),          "=="),
    ("land_to_lor",    re.compile(r"&&"),                          "||"),
    ("lor_to_land",    re.compile(r"\|\|"),                        "&&"),
    ("and_to_or",      re.compile(r"(?<![&])&(?![&])"),            "|"),
    ("or_to_and",      re.compile(r"(?<![|])\|(?![|])"),           "&"),
    ("lt_to_gt",       re.compile(r"(?<![<=>])<(?![=<])"),         ">"),
    ("gt_to_lt",       re.compile(r"(?<![<=>\-])>(?![=>])"),       "<"),
    ("posedge_to_neg", re.compile(r"\bposedge\b"),                 "negedge"),
    ("negedge_to_pos", re.compile(r"\bnegedge\b"),                 "posedge"),
    ("bit0_to_bit1",   re.compile(r"1'b0"),                        "1'b1"),
    ("bit1_to_bit0",   re.compile(r"1'b1"),                        "1'b0"),
]


def _code_mask(code: str) -> list[bool]:
    """True at every index that is real code (not comment, not string literal).

    Mutating inside a comment produces a mutant identical to the original, which
    no TB can kill and which silently deflates the score.
    """
    mask = [True] * len(code)
    i, n = 0, len(code)
    while i < n:
        two = code[i:i + 2]
        if two == "//":
            while i < n and code[i] != "\n":
                mask[i] = False
                i += 1
        elif two == "/*":
            while i < n and code[i:i + 2] != "*/":
                mask[i] = False
                i += 1
            for j in range(i, min(i + 2, n)):
                mask[j] = False
            i += 2
        elif code[i] == '"':
            mask[i] = False
            i += 1
            while i < n and code[i] != '"':
                if code[i] == "\\":
                    mask[i] = False
                    i += 1
                if i < n:
                    mask[i] = False
                    i += 1
            if i < n:
                mask[i] = False
                i += 1
        else:
            i += 1
    return mask


def mutate(code: str, max_mutants: int = DEFAULT_MAX_MUTANTS) -> list[tuple[str, str]]:
    """Return [(tag, mutated_code), ...] with exactly one seeded bug per mutant.

    Operators are interleaved round-robin so that hitting the cap yields a
    diverse sample instead of many copies of the same mutation type.
    """
    mask = _code_mask(code)
    by_op: dict[str, list[tuple[int, int, str]]] = {}
    for name, pattern, repl in MUTATIONS:
        sites = [
            (m.start(), m.end(), repl)
            for m in pattern.finditer(code)
            if all(mask[k] for k in range(m.start(), m.end()))
        ]
        if sites:
            by_op[name] = sites

    mutants: list[tuple[str, str]] = []
    round_idx = 0
    while len(mutants) < max_mutants:
        progressed = False
        for name in list(by_op):
            sites = by_op[name]
            if round_idx >= len(sites):
                continue
            progressed = True
            start, end, repl = sites[round_idx]
            mutants.append((f"{name}@{start}", code[:start] + repl + code[end:]))
            if len(mutants) >= max_mutants:
                break
        if not progressed:
            break
        round_idx += 1
    return mutants


def _tb_top(tb_code: str) -> str:
    """Name of the first module declared in the testbench."""
    m = re.search(r"\bmodule\s+([A-Za-z_]\w*)", tb_code)
    return m.group(1) if m else "tb"


def _verdict(log: str, run_rc: int) -> str:
    """pass/fail using the same convention as comba_pipeline._parse_tb_result."""
    for line in log.splitlines():
        s = line.strip()
        if "Failed" in s:
            return "fail"
        m = re.search(r"Mismatches:\s*(\d+)", s)
        if m and int(m.group(1)) > 0:
            return "fail"
    if run_rc != 0:
        return "fail"
    low = log.lower()
    return "pass" if ("passed" in low or "mismatches: 0" in low) else "fail"


def _kill_group(p: subprocess.Popen) -> None:
    import signal
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        else:
            p.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _run_pair(dut_code: str, tb_code: str, tmp_root: str | None = None) -> tuple[str, str]:
    """Compile DUT+TB and run.

    Returns (status, log) where status is one of
    "pass" | "fail" | "compile_error" | "timeout" | "no_tool".
    """
    with tempfile.TemporaryDirectory(prefix="tbval_", dir=tmp_root) as td:
        wd = Path(td)
        (wd / "dut.sv").write_text(dut_code, encoding="utf-8")
        (wd / "tb.sv").write_text(tb_code, encoding="utf-8")
        binary = "sim.vvp"
        cmd = (["iverilog"] + IVERILOG_TS_FLAGS
               + ["-s", _tb_top(tb_code), "-o", binary, "dut.sv", "tb.sv"])
        try:
            c = subprocess.run(cmd, cwd=td, capture_output=True, text=True,
                               timeout=COMPILE_TIMEOUT)
        except FileNotFoundError:
            return "no_tool", "iverilog not found on PATH"
        except subprocess.TimeoutExpired:
            return "compile_error", "compile timeout"
        if c.returncode != 0:
            return "compile_error", (c.stderr + c.stdout)[-2000:]

        # Kill the whole process group: a TB missing $finish loops forever and
        # an orphaned vvp burns a core (this repo has been bitten by that).
        popen_kw = {}
        if os.name != "nt":
            popen_kw["preexec_fn"] = os.setsid
        try:
            p = subprocess.Popen(["vvp", binary], cwd=td, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, **popen_kw)
        except FileNotFoundError:
            return "no_tool", "vvp not found on PATH"
        try:
            out, _ = p.communicate(timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            _kill_group(p)
            out, _ = p.communicate()
            return "timeout", (out or "")[-2000:]
        return _verdict(out, p.returncode), out[-2000:]


def validate_tb(tb_code: str, dut_code: str, *, max_mutants: int = DEFAULT_MAX_MUTANTS,
                min_score: float = DEFAULT_MIN_SCORE,
                tmp_root: str | None = None) -> dict:
    """Score a testbench. See the module docstring for what the score does and
    does not prove."""
    base_status, base_log = _run_pair(dut_code, tb_code, tmp_root)
    result = {
        "dut_status": base_status,
        "mutants_total": 0,
        "mutants_killed": 0,
        "mutants_survived": 0,
        "mutants_excluded": 0,
        "survivors": [],
        "mutation_score": None,
        "min_score": min_score,
        "verdict": "unusable",
        "tier": "unchecked",
    }
    if base_status == "no_tool":
        result["verdict"] = "skipped_no_simulator"
        result["note"] = base_log
        return result
    if base_status != "pass":
        # The TB rejects the very design it was written for: either the TB is
        # wrong or the DUT is. The TB cannot be graded until that is resolved.
        result["verdict"] = "rejects_dut"
        result["note"] = base_log[-500:]
        return result

    killed = survived = excluded = 0
    survivors: list[str] = []
    for tag, mutant in mutate(dut_code, max_mutants):
        status, _ = _run_pair(mutant, tb_code, tmp_root)
        if status in ("compile_error", "no_tool"):
            excluded += 1          # not evidence either way
        elif status in ("fail", "timeout"):
            killed += 1
        else:
            survived += 1
            survivors.append(tag)

    graded = killed + survived
    score = (killed / graded) if graded else None
    result.update({
        "mutants_total": graded + excluded,
        "mutants_killed": killed,
        "mutants_survived": survived,
        "mutants_excluded": excluded,
        "survivors": survivors[:10],
        "mutation_score": round(score, 4) if score is not None else None,
    })
    if score is None:
        result["verdict"] = "inconclusive"
        result["tier"] = "unchecked"
    elif score >= min_score:
        result["verdict"] = "accepted"
        result["tier"] = "self_validated"
    else:
        result["verdict"] = "weak"
        result["tier"] = "weak_selfcheck"
    return result


# -- self-check: mutation logic only, so it runs without iverilog ----------
def _selfcheck() -> None:
    src = "assign y = a + b;  // a + b is not mutated here\n"
    tags = [t for t, _ in mutate(src)]
    assert any(t.startswith("add_to_sub") for t in tags), tags
    assert sum(t.startswith("add_to_sub") for t in tags) == 1, \
        f"comment '+' must not be a mutation site: {tags}"

    nb = "always @(posedge clk) q <= d;\n"
    muts = dict(mutate(nb))
    assert all("q > d" not in m and "q < d" not in m for m in muts.values()), \
        "non-blocking '<=' must never be mutated as a comparison"
    assert any("negedge" in m for m in muts.values()), "posedge must be mutable"

    s = 'initial $display("a < b && x == y");\n'
    assert mutate(s) == [], f"string literal must not be mutated: {mutate(s)}"

    wide = "assign z = " + " + ".join(f"i{k}" for k in range(50)) + ";\n"
    assert len(mutate(wide, max_mutants=5)) == 5, "cap must be honoured"

    mixed = "assign y = (a + b) & (c == d);\n"
    kinds = {t.split("@")[0] for t in dict(mutate(mixed, max_mutants=3))}
    assert len(kinds) >= 2, f"operators must interleave, got {kinds}"

    part_sel = "assign y = data[base +: 8] - 1;\n"
    for tag, m in mutate(part_sel):
        assert "+: 8" in m or "-: 8" in m or "base +" in m, \
            f"indexed part-select must stay intact: {tag} -> {m}"

    for _, m in mutate("assign y = a + b;\n"):
        assert m != "assign y = a + b;\n", "mutant must differ from original"
    print("mutation self-check OK")
    _selfcheck_e2e()


# DUT + two testbenches used by the end-to-end check below. The blind TB is the
# failure mode this whole module exists to catch: it passes on everything.
_E2E_DUT = """module TopModule(input [3:0] a, input [3:0] b, output [4:0] sum);
    assign sum = a + b;
endmodule
"""

_E2E_STRONG_TB = """module tb;
    reg [3:0] a, b; wire [4:0] sum; integer i; integer bad = 0;
    TopModule uut(.a(a), .b(b), .sum(sum));
    initial begin
        for (i = 0; i < 16; i = i + 1) begin
            a = i[3:0]; b = (15 - i); #1;
            if (sum !== (a + b)) begin
                $display("TODO %0d Failed", i); bad = bad + 1;
            end
        end
        if (bad == 0) $display("All tests passed");
        $finish;
    end
endmodule
"""

_E2E_BLIND_TB = """module tb;
    reg [3:0] a, b; wire [4:0] sum;
    TopModule uut(.a(a), .b(b), .sum(sum));
    initial begin
        a = 0; b = 0; #1;
        $display("All tests passed");
        $finish;
    end
endmodule
"""


def _selfcheck_e2e() -> None:
    """Prove the grader separates a real testbench from a blind one.

    Needs iverilog + vvp, so it is skipped where they are absent (e.g. a Windows
    dev box) and runs on the machine that has the toolchain.
    """
    probe, _ = _run_pair(_E2E_DUT, _E2E_STRONG_TB)
    if probe == "no_tool":
        print("e2e check SKIPPED (iverilog/vvp not on PATH)")
        return

    strong = validate_tb(_E2E_STRONG_TB, _E2E_DUT, max_mutants=8)
    assert strong["dut_status"] == "pass", strong
    assert strong["verdict"] == "accepted", f"real TB must be accepted: {strong}"
    assert strong["mutation_score"] and strong["mutation_score"] >= 0.6, strong

    blind = validate_tb(_E2E_BLIND_TB, _E2E_DUT, max_mutants=8)
    assert blind["dut_status"] == "pass", blind
    assert blind["verdict"] == "weak", f"blind TB must be rejected: {blind}"
    assert blind["mutation_score"] == 0.0, blind

    print(f"e2e check OK (strong score={strong['mutation_score']}, "
          f"blind score={blind['mutation_score']})")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tb", help="testbench file")
    ap.add_argument("--dut", help="design file")
    ap.add_argument("--max-mutants", type=int, default=DEFAULT_MAX_MUTANTS)
    ap.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    ap.add_argument("--json", help="write result JSON here")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck or not (a.tb and a.dut):
        _selfcheck()
    else:
        res = validate_tb(Path(a.tb).read_text(encoding="utf-8"),
                          Path(a.dut).read_text(encoding="utf-8"),
                          max_mutants=a.max_mutants, min_score=a.min_score)
        print(json.dumps(res, indent=2))
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=2), encoding="utf-8")

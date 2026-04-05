"""
Comprehensive test script for the COMBA Debugger LoRA model.

Sends buggy Verilog modules to both base and debugger models,
compares output quality across 8 different error categories.

Test Categories:
  EDP (Syntax):
    1. Undeclared signal
    2. Width mismatch
    3. Missing module instantiation port
    4. Multi-driven signal

  TDP (Functional):
    5. Off-by-one counter
    6. Wrong FSM transition
    7. Incorrect reset logic
    8. Wrong operator

Usage:
    python test_debugger_model.py                         # run all tests
    python test_debugger_model.py --test 1                # run test 1 only
    python test_debugger_model.py --test 1,3,5            # run specific tests
    python test_debugger_model.py --only-debugger         # skip base model
    python test_debugger_model.py --base-url http://..    # custom server
"""

import argparse
import json
import time
import textwrap
import re
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from openai import OpenAI


# ══════════════════════════════════════════════════════════════
# Test Case Data Structure
# ══════════════════════════════════════════════════════════════

@dataclass
class TestCase:
    id: int
    name: str
    category: str              # "EDP" (syntax) or "TDP" (functional)
    module_name: str
    buggy_code: str
    error_log: str
    expected_fix_keywords: List[str]   # keywords that should appear in fix
    bug_description: str
    check_fn: Optional[Callable] = None  # custom validation function


# ══════════════════════════════════════════════════════════════
# EDP Test Cases (Syntax Errors)
# ══════════════════════════════════════════════════════════════

TEST_CASES: List[TestCase] = [

    # ── Test 1: Undeclared signal ──
    TestCase(
        id=1,
        name="Undeclared Signal",
        category="EDP",
        module_name="adder_8bit",
        buggy_code="""\
module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    assign result = a + b + cin;
    assign sum = result[7:0];
    assign cout = result[8];
endmodule
""",
        error_log="""\
%Error: adder_8bit.v:7: Signal 'result' not found
%Error: adder_8bit.v:8: Signal 'result' not found
%Error: adder_8bit.v:9: Signal 'result' not found
%Error: Exiting due to 3 error(s)
""",
        expected_fix_keywords=["wire", "result"],
        bug_description="'result' used but never declared as wire/reg",
    ),

    # ── Test 2: Width mismatch ──
    TestCase(
        id=2,
        name="Width Mismatch",
        category="EDP",
        module_name="mux4to1",
        buggy_code="""\
module mux4to1(
    input [7:0] d0, d1, d2, d3,
    input [1:0] sel,
    output reg [7:0] out
);
    wire [3:0] temp;
    always @(*) begin
        case (sel)
            2'b00: out = d0;
            2'b01: out = d1;
            2'b10: out = d2;
            2'b11: out = d3;
        endcase
    end
    assign temp = out;
endmodule
""",
        error_log="""\
%Warning-WIDTHTRUNC: mux4to1.v:15: Operator ASSIGN expects 4 bits on the Assign RHS, but Assign RHS's SEL generates 8 bits.
%Error: Exiting due to 1 warning(s) treated as error(s)
""",
        expected_fix_keywords=["[7:0]", "temp"],
        bug_description="'temp' is 4-bit but assigned 8-bit 'out'",
    ),

    # ── Test 3: Missing port connection ──
    TestCase(
        id=3,
        name="Missing Port Connection",
        category="EDP",
        module_name="top_adder",
        buggy_code="""\
module full_adder(
    input a, b, cin,
    output sum, cout
);
    assign {cout, sum} = a + b + cin;
endmodule

module top_adder(
    input [3:0] a, b,
    input cin,
    output [3:0] sum,
    output cout
);
    wire [3:0] c;

    full_adder FA0 (.a(a[0]), .b(b[0]), .cin(cin), .sum(sum[0]));
    full_adder FA1 (.a(a[1]), .b(b[1]), .cin(c[0]), .sum(sum[1]), .cout(c[1]));
    full_adder FA2 (.a(a[2]), .b(b[2]), .cin(c[1]), .sum(sum[2]), .cout(c[2]));
    full_adder FA3 (.a(a[3]), .b(b[3]), .cin(c[2]), .sum(sum[3]), .cout(c[3]));

    assign cout = c[3];
endmodule
""",
        error_log="""\
%Warning-PINMISSING: top_adder.v:16: Cell has missing pin: 'cout'
%Warning-UNDRIVEN: top_adder.v:14: Signal is not driven: 'c[0]'
%Error: Exiting due to 2 warning(s) treated as error(s)
""",
        expected_fix_keywords=[".cout(c[0])"],
        bug_description="FA0 missing .cout(c[0]) port connection",
    ),

    # ── Test 4: Multi-driven signal ──
    TestCase(
        id=4,
        name="Multi-driven Signal",
        category="EDP",
        module_name="priority_enc",
        buggy_code="""\
module priority_enc(
    input [3:0] req,
    output reg [1:0] enc,
    output reg valid
);
    always @(*) begin
        if (req[3]) begin
            enc = 2'd3;
            valid = 1'b1;
        end else if (req[2]) begin
            enc = 2'd2;
            valid = 1'b1;
        end else if (req[1]) begin
            enc = 2'd1;
            valid = 1'b1;
        end else if (req[0]) begin
            enc = 2'd0;
            valid = 1'b1;
        end
    end

    assign valid = |req;
endmodule
""",
        error_log="""\
%Error-MULTIDRIVEN: priority_enc.v:23: Signal 'valid' is driven by both always block and continuous assign
%Error: Exiting due to 1 error(s)
""",
        expected_fix_keywords=["valid"],
        bug_description="'valid' driven by both always block and assign statement",
        check_fn=lambda resp: resp.count("assign valid") + resp.count("valid =") <= 4,
    ),

    # ══════════════════════════════════════════════════════════
    # TDP Test Cases (Functional Errors)
    # ══════════════════════════════════════════════════════════

    # ── Test 5: Off-by-one counter ──
    TestCase(
        id=5,
        name="Off-by-one Counter",
        category="TDP",
        module_name="counter_12",
        buggy_code="""\
module counter_12(
    input rst_n,
    input clk,
    input valid_count,
    output reg [3:0] out
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            out <= 4'b0000;
        else if (valid_count) begin
            if (out == 4'd12)
                out <= 4'b0000;
            else
                out <= out + 1;
        end
    end
endmodule
""",
        error_log="""\
[FAIL] Test 12: Expected out=0 after reaching 11, but got out=12
  Time=240ns: valid_count=1, out=12 (expected 0)
  The counter should wrap to 0 when it reaches 11, not 12.
""",
        expected_fix_keywords=["4'd11", "11"],
        bug_description="Counter wraps at 12 instead of 11 (should count 0-11)",
    ),

    # ── Test 6: Wrong FSM transition ──
    TestCase(
        id=6,
        name="Wrong FSM Transition",
        category="TDP",
        module_name="seq_detector",
        buggy_code="""\
module seq_detector(
    input clk, rst, din,
    output reg detected
);
    localparam S0=0, S1=1, S2=2, S3=3;
    reg [1:0] state, next_state;

    always @(posedge clk or posedge rst) begin
        if (rst) state <= S0;
        else state <= next_state;
    end

    always @(*) begin
        detected = 0;
        next_state = state;
        case (state)
            S0: next_state = din ? S1 : S0;
            S1: next_state = din ? S1 : S2;
            S2: next_state = din ? S3 : S0;
            S3: begin
                if (din) begin
                    detected = 1;
                    next_state = S0;
                end else begin
                    next_state = S2;
                end
            end
        endcase
    end
endmodule
""",
        error_log="""\
[FAIL] Sequence "1011" not detected.
  Time=80ns: din=1,0,1,1 → detected=0 (expected 1)
  Applied din sequence: 1→0→1→1, but detected never asserted.
  Debug: state trace = S0→S1→S2→S3→S2 (expected S0→S1→S2→S3→detected)
[INFO] S3 with din=1 should go to S1 (overlapping), not S0.
""",
        expected_fix_keywords=["S1"],
        bug_description="S3→din=1 should go to S1 (overlap), not S0",
    ),

    # ── Test 7: Incorrect reset logic ──
    TestCase(
        id=7,
        name="Incorrect Reset Logic",
        category="TDP",
        module_name="shift_reg",
        buggy_code="""\
module shift_reg(
    input clk, rst_n, din,
    output reg [7:0] dout
);
    always @(posedge clk) begin
        if (!rst_n)
            dout <= 8'hFF;
        else begin
            dout <= {dout[6:0], din};
        end
    end
endmodule
""",
        error_log="""\
[FAIL] Reset test: Expected dout=0x00 after reset, got dout=0xFF
  Time=10ns: rst_n=0, dout=0xFF (expected 0x00)
  Reset should clear the register to 0, not set to all 1s.
[FAIL] Async reset not working — reset only takes effect on clock edge
  Time=5ns: rst_n asserted low between clock edges, dout unchanged.
""",
        expected_fix_keywords=["8'h00", "negedge rst_n"],
        bug_description="Reset value should be 0x00 not 0xFF, and reset should be async",
    ),

    # ── Test 8: Wrong operator ──
    TestCase(
        id=8,
        name="Wrong Operator",
        category="TDP",
        module_name="alu_simple",
        buggy_code="""\
module alu_simple(
    input [7:0] a, b,
    input [1:0] op,
    output reg [7:0] result,
    output zero
);
    always @(*) begin
        case (op)
            2'b00: result = a + b;
            2'b01: result = a + b;
            2'b10: result = a & b;
            2'b11: result = a | b;
        endcase
    end
    assign zero = (result == 8'b0);
endmodule
""",
        error_log="""\
[FAIL] SUB operation: a=10, b=3, op=01 → result=13 (expected 7)
  Time=20ns: op=2'b01, a=8'd10, b=8'd3, result=8'd13
  Expected: 10 - 3 = 7, but got 10 + 3 = 13
  SUB (op=01) performs addition instead of subtraction.
""",
        expected_fix_keywords=["a - b"],
        bug_description="op=01 does a+b instead of a-b (copy-paste bug)",
    ),
]


# ══════════════════════════════════════════════════════════════
# Prompt Builders
# ══════════════════════════════════════════════════════════════

EDP_SYSTEM = textwrap.dedent("""\
    You are a Verilog syntax debugging expert.
    You receive a Verilog module that failed Verilator syntax checking.
    Your task is to fix the TOPMOST error precisely.

    ## Rules
    1. Fix ONLY the topmost error. Other errors may cascade from it.
    2. Preserve the module name, port names, and overall architecture.
    3. Common Verilator errors and fixes:
       - "Signal not found" → declare the signal as wire/reg
       - "Width mismatch" / "WIDTHTRUNC" → adjust signal widths
       - "PINMISSING" → add the missing port connection
       - "MULTIDRIVEN" → remove duplicate drivers
       - "UNDRIVEN" → ensure all signals are driven
    4. Return ONLY the complete fixed Verilog code, no explanation.
    5. Do NOT wrap in markdown code fences.
""")

TDP_SYSTEM = textwrap.dedent("""\
    You are a Verilog functional debugging expert.
    You receive a Verilog module that passed syntax checking but failed testbench simulation.
    Your task is to fix the TOPMOST functional failure.

    ## Rules
    1. The error is a LOGIC BUG, not a syntax error. The code compiles fine.
    2. Analyze the testbench traces to understand expected vs actual behavior.
    3. Common functional issues:
       - Wrong operator (+ vs -, & vs |)
       - Missing or incorrect reset logic
       - Off-by-one in counters or comparisons
       - Wrong state transitions in FSMs
       - Incorrect bit widths causing truncation
    4. Preserve the module interface (name, ports) exactly.
    5. Return ONLY the complete fixed Verilog code, no explanation.
    6. Do NOT wrap in markdown code fences.
""")


def build_messages(tc: TestCase) -> list:
    """Build prompt messages for a test case."""
    if tc.category == "EDP":
        system = EDP_SYSTEM
        topmost = tc.error_log.strip().split("\n")[0]
        user = f"""\
## Module: {tc.module_name}
## Phase: Syntax Check | Trial 1/5

### Current Verilog Code
```verilog
{tc.buggy_code}```

### Topmost Verilator Error
{topmost}

### Full Syntax Check Log
{tc.error_log}
Fix the topmost error and return the complete corrected Verilog code."""
    else:
        system = TDP_SYSTEM
        user = f"""\
## Module: {tc.module_name}
## Phase: Testbench Simulation | Trial 1/5

### Current Verilog Code
```verilog
{tc.buggy_code}```

### Topmost Testbench Failure
{tc.error_log}
Fix the functional logic and return the complete corrected Verilog code."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ══════════════════════════════════════════════════════════════
# Response Validation
# ══════════════════════════════════════════════════════════════

def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    text = re.sub(r'^```\w*\n', '', text.strip())
    text = re.sub(r'\n```\s*$', '', text.strip())
    return text.strip()


def is_valid_verilog(text: str) -> bool:
    """Basic check: does it look like Verilog code?"""
    text = strip_markdown_fences(text)
    return ("module" in text and "endmodule" in text)


def check_keywords(text: str, keywords: List[str]) -> dict:
    """Check which expected keywords are present in the response."""
    text_clean = strip_markdown_fences(text)
    results = {}
    for kw in keywords:
        results[kw] = kw in text_clean
    return results


def validate_response(tc: TestCase, response: str) -> dict:
    """Validate a model response against the test case."""
    result = {
        "is_verilog": is_valid_verilog(response),
        "has_module": tc.module_name in response,
        "keywords": check_keywords(response, tc.expected_fix_keywords),
        "all_keywords": all(check_keywords(response, tc.expected_fix_keywords).values()),
        "custom_check": None,
    }
    if tc.check_fn:
        result["custom_check"] = tc.check_fn(response)
    return result


# ══════════════════════════════════════════════════════════════
# Model Calling
# ══════════════════════════════════════════════════════════════

def call_model(client: OpenAI, model: str, messages: list) -> dict:
    """Call model and return response with metadata."""
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
            max_tokens=2048,
        )
        elapsed = time.time() - t0
        text = resp.choices[0].message.content or ""
        return {
            "text": text,
            "time": elapsed,
            "tok_in": resp.usage.prompt_tokens if resp.usage else 0,
            "tok_out": resp.usage.completion_tokens if resp.usage else 0,
            "error": None,
        }
    except Exception as e:
        return {
            "text": "",
            "time": time.time() - t0,
            "tok_in": 0, "tok_out": 0,
            "error": str(e),
        }


def check_health(client: OpenAI, url: str, label: str) -> bool:
    """Check if server is available."""
    try:
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        print(f"  ✅ {label} ({url}): models = {model_ids}")
        return True
    except Exception as e:
        print(f"  ❌ {label} ({url}): {e}")
        return False


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Test COMBA Debugger LoRA model")
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--debugger-url", default="http://localhost:8001/v1")
    parser.add_argument("--api-key", default="not-needed")
    parser.add_argument("--test", default="all",
                        help="Test IDs: 'all', '1', '1,3,5', 'edp', 'tdp'")
    parser.add_argument("--only-debugger", action="store_true",
                        help="Skip base model, test debugger only")
    parser.add_argument("--only-base", action="store_true",
                        help="Skip debugger, test base model only")
    parser.add_argument("--save", default=None,
                        help="Save results to JSON file")
    args = parser.parse_args()

    # ── Parse test selection ──
    if args.test == "all":
        selected = TEST_CASES
    elif args.test.lower() == "edp":
        selected = [tc for tc in TEST_CASES if tc.category == "EDP"]
    elif args.test.lower() == "tdp":
        selected = [tc for tc in TEST_CASES if tc.category == "TDP"]
    else:
        ids = [int(x.strip()) for x in args.test.split(",")]
        selected = [tc for tc in TEST_CASES if tc.id in ids]

    if not selected:
        print("❌ No test cases selected.")
        return

    print("╔══════════════════════════════════════════════════════════╗")
    print("║  COMBA Debugger Model — Comprehensive Test Suite        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"\n  Running {len(selected)} test(s): {[tc.id for tc in selected]}\n")

    # ── Create clients ──
    client_base = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=180)
    client_dbg = OpenAI(base_url=args.debugger_url, api_key=args.api_key, timeout=180)

    # ── Health check ──
    print("📡 Health Check:")
    run_base = not args.only_debugger
    run_dbg = not args.only_base

    ok_base = check_health(client_base, args.base_url, "Base (GPU 0)") if run_base else False
    ok_dbg = check_health(client_dbg, args.debugger_url, "Debugger (GPU 1)") if run_dbg else False

    if not ok_base and not ok_dbg:
        print("\n❌ No servers available.")
        return

    # ── Run tests ──
    results = []
    summary_base = {"pass": 0, "fail": 0, "error": 0}
    summary_dbg = {"pass": 0, "fail": 0, "error": 0}

    for tc in selected:
        print(f"\n\n{'█' * 60}")
        print(f"  TEST {tc.id}: {tc.name} [{tc.category}]")
        print(f"  Module: {tc.module_name}")
        print(f"  Bug: {tc.bug_description}")
        print(f"{'█' * 60}")

        messages = build_messages(tc)
        test_result = {"id": tc.id, "name": tc.name, "category": tc.category}

        # ── Base model ──
        if ok_base:
            print(f"\n  🔵 Base Model (qwen-base)...")
            r = call_model(client_base, "qwen-base", messages)
            if r["error"]:
                print(f"     ❌ Error: {r['error']}")
                summary_base["error"] += 1
            else:
                v = validate_response(tc, r["text"])
                status = "✅ PASS" if v["is_verilog"] and v["all_keywords"] else "❌ FAIL"
                if v["is_verilog"] and v["all_keywords"]:
                    summary_base["pass"] += 1
                else:
                    summary_base["fail"] += 1
                print(f"     {status} | {r['time']:.1f}s | {r['tok_in']}→{r['tok_out']} tok")
                print(f"     Valid Verilog: {'✅' if v['is_verilog'] else '❌'} | "
                      f"Correct module: {'✅' if v['has_module'] else '❌'}")
                for kw, found in v["keywords"].items():
                    print(f"     Keyword '{kw}': {'✅' if found else '❌'}")
                if v["custom_check"] is not None:
                    print(f"     Custom check: {'✅' if v['custom_check'] else '❌'}")

                # Show first 20 lines of response
                lines = strip_markdown_fences(r["text"]).split("\n")
                print(f"     ── Response ({len(lines)} lines) ──")
                for line in lines[:20]:
                    print(f"     │ {line}")
                if len(lines) > 20:
                    print(f"     │ ... ({len(lines) - 20} more lines)")

            test_result["base"] = {
                "time": r["time"], "tokens": r["tok_out"],
                "valid": v["is_verilog"] if not r["error"] else False,
                "keywords": v["all_keywords"] if not r["error"] else False,
            }

        # ── Debugger model ──
        if ok_dbg:
            print(f"\n  🔴 Debugger LoRA (debugger)...")
            r = call_model(client_dbg, "debugger", messages)
            if r["error"]:
                print(f"     ❌ Error: {r['error']}")
                summary_dbg["error"] += 1
            else:
                v = validate_response(tc, r["text"])
                status = "✅ PASS" if v["is_verilog"] and v["all_keywords"] else "❌ FAIL"
                if v["is_verilog"] and v["all_keywords"]:
                    summary_dbg["pass"] += 1
                else:
                    summary_dbg["fail"] += 1
                print(f"     {status} | {r['time']:.1f}s | {r['tok_in']}→{r['tok_out']} tok")
                print(f"     Valid Verilog: {'✅' if v['is_verilog'] else '❌'} | "
                      f"Correct module: {'✅' if v['has_module'] else '❌'}")
                for kw, found in v["keywords"].items():
                    print(f"     Keyword '{kw}': {'✅' if found else '❌'}")
                if v["custom_check"] is not None:
                    print(f"     Custom check: {'✅' if v['custom_check'] else '❌'}")

                lines = strip_markdown_fences(r["text"]).split("\n")
                print(f"     ── Response ({len(lines)} lines) ──")
                for line in lines[:20]:
                    print(f"     │ {line}")
                if len(lines) > 20:
                    print(f"     │ ... ({len(lines) - 20} more lines)")

            test_result["debugger"] = {
                "time": r["time"], "tokens": r["tok_out"],
                "valid": v["is_verilog"] if not r["error"] else False,
                "keywords": v["all_keywords"] if not r["error"] else False,
            }

        results.append(test_result)

    # ── Summary ──
    print(f"\n\n{'═' * 60}")
    print(f"  SUMMARY")
    print(f"{'═' * 60}")

    header = f"  {'Test':<5} {'Name':<25} {'Category':<5}"
    if ok_base:
        header += f" {'Base':<10}"
    if ok_dbg:
        header += f" {'Debugger':<10}"
    print(header)
    print(f"  {'─' * 55}")

    for r in results:
        line = f"  {r['id']:<5} {r['name']:<25} {r['category']:<5}"
        if ok_base and "base" in r:
            b = r["base"]
            s = "✅ PASS" if b["valid"] and b["keywords"] else "❌ FAIL"
            line += f" {s:<10}"
        if ok_dbg and "debugger" in r:
            d = r["debugger"]
            s = "✅ PASS" if d["valid"] and d["keywords"] else "❌ FAIL"
            line += f" {s:<10}"
        print(line)

    print()
    if ok_base:
        total = summary_base["pass"] + summary_base["fail"] + summary_base["error"]
        print(f"  Base:     {summary_base['pass']}/{total} passed, "
              f"{summary_base['fail']} failed, {summary_base['error']} errors")
    if ok_dbg:
        total = summary_dbg["pass"] + summary_dbg["fail"] + summary_dbg["error"]
        print(f"  Debugger: {summary_dbg['pass']}/{total} passed, "
              f"{summary_dbg['fail']} failed, {summary_dbg['error']} errors")

    # ── Save results ──
    if args.save:
        with open(args.save, "w") as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "base_url": args.base_url,
                "debugger_url": args.debugger_url,
                "summary": {"base": summary_base, "debugger": summary_dbg},
                "results": results,
            }, f, indent=2)
        print(f"\n  💾 Results saved to {args.save}")

    print(f"\n✅ Done!")


if __name__ == "__main__":
    main()

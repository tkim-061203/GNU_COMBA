"""
E2E Tests for COMBA-PROMPT LangGraph Pipeline v3.

Tests the full pipeline with StubLLM and mocked Verilator subprocess calls.
7 routing decisions, VerilogSanitizer, MultiAttemptManager, Rollback Manager,
EDTM, and Iteration Control are verified without external dependencies.

Usage:
    python -m pytest test_pipeline.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import os
import subprocess

from comba_pipeline import (
    COMBAState,
    COMBANodes,
    build_comba_graph,
    make_initial_state,
    MAX_SC_TRIALS,
    MAX_TS_TRIALS,
    MAX_TOTAL_ITER,
    EDTM_MAX_RETRIES,
    route_after_sc,
    route_after_ts,
    route_after_ted_syntax,
    route_after_ted_tb,
    route_after_sanitizer,
)
from stub_llm import (
    create_stub_llm,
    create_buggy_stub_llm,
    create_always_buggy_stub_llm,
    create_worse_stub_llm,
    GOOD_VERILOG,
    BUGGY_VERILOG,
    FIXED_VERILOG,
    WORSE_VERILOG,
    GOOD_XML,
    DEBUGGER_PATCH_FIXED,
)
from comba_pipeline import _count_iverilog_errors, _normalize_error_key
from fsm_patch import route_after_classify_tb



# ──────────────────────────────────────────────────────────────
# Helpers: Mock iverilog subprocess calls
# ──────────────────────────────────────────────────────────────

def make_iverilog_result(returncode=0, stderr="", stdout=""):
    """Create a mock subprocess.CompletedProcess."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stderr = stderr
    result.stdout = stdout
    return result


CLEAN_SC_RESULT = make_iverilog_result(returncode=0, stderr="", stdout="")
SC_ERROR_RESULT = make_iverilog_result(
    returncode=2,
    stderr="adder_8bit.sv:8: error: Signal 'result' not found\n",
)
SC_MULTI_ERROR_RESULT = make_iverilog_result(
    returncode=2,
    stderr=(
        "adder_8bit.sv:8: error: Signal 'result' not found\n"
        "adder_8bit.sv:9: syntax error\n"
        "adder_8bit.sv:10: error: another error\n"
    ),
)
TB_PASS_RESULT = make_iverilog_result(returncode=0, stdout="All tests passed\n")
TB_FAIL_RESULT = make_iverilog_result(
    returncode=1,
    stdout=(
        "TODO 3 Failed at simtime 42\n"
    ),
)


# ──────────────────────────────────────────────────────────────
# Test 0: Utility functions
# ──────────────────────────────────────────────────────────────

class TestUtilities:
    def test_count_iverilog_errors(self):
        log = (
            "module.sv:10: error: syntax error\n"
            "module.sv:12: warning: some warning\n"
            "module.sv:15: ERROR: another error\n"
            "   error: not a line start error\n"
        )
        # Should find 2 matches (line 1 and 3)
        assert _count_iverilog_errors(log) == 2

    def test_normalize_error_key(self):
        err = "  adder_8bit.sv:123: error:  Signal 'result'   not found  "
        norm = _normalize_error_key(err)
        assert norm == "adder_8bit.sv:N: error: Signal 'result' not found"
        
        # Test truncation
        long_err = "A" * 200
        assert len(_normalize_error_key(long_err, max_len=50)) == 50


# ──────────────────────────────────────────────────────────────
# Test 1: Unit tests for routing functions
# ──────────────────────────────────────────────────────────────

class TestRoutingFunctions:
    """Test the 7 conditional routing functions in isolation."""

    # ── Sanitizer routing (v3) ──
    def test_route_after_sanitizer_no_retry(self):
        """Sanitizer succeeded → go to SC."""
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sanitize_result"] = {"needs_retry": False, "code": "module test..."}
        assert route_after_sanitizer(state) == "node_syntax_check"

    def test_route_after_sanitizer_retry_from_generator(self):
        """Sanitizer needs retry, source was generator → back to generator."""
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sanitize_result"] = {"needs_retry": True}
        state["_last_llm_source"] = "generator"
        assert route_after_sanitizer(state) == "node_generator"

    def test_route_after_sanitizer_retry_from_debugger(self):
        """Sanitizer needs retry, source was debugger → back to debugger."""
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sanitize_result"] = {"needs_retry": True}
        state["_last_llm_source"] = "debugger"
        assert route_after_sanitizer(state) == "node_debugger"

    def test_route_after_sanitizer_default_no_result(self):
        """No sanitize_result → default to SC (no retry)."""
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        assert route_after_sanitizer(state) == "node_syntax_check"

    # ── SC routing (unchanged) ──
    def test_route_after_sc_has_errors(self):
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sc_exception_count"] = 2
        assert route_after_sc(state) == "node_ted_syntax"

    def test_route_after_sc_clean(self):
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sc_exception_count"] = 0
        assert route_after_sc(state) == "node_tb_sim"

    # ── TS routing (unchanged) ──
    def test_route_after_ts_has_failure(self):
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["tb_failure"] = "TODO 3 Failed"
        assert route_after_ts(state) == "node_classify_tb"

    def test_route_after_ts_pass(self):
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["tb_failure"] = None
        assert route_after_ts(state) == "end_pass"

    # ── Classify TB routing (v5) ──
    def test_route_after_classify_tb_fsm(self):
        state = make_initial_state()
        state["failure_type"] = "fsm_state_error"
        assert route_after_classify_tb(state) == "node_vcd_analyzer"

    def test_route_after_classify_tb_comb(self):
        state = make_initial_state()
        state["failure_type"] = "combinational_mismatch"
        assert route_after_classify_tb(state) == "node_ted_tb"

    # ── TED SC routing (enhanced with MultiAttempt) ──
    def test_route_after_ted_syntax_under_limit(self):
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sc_trial"] = 3
        state["sc_exception"] = "adder_8bit.sv:8: error: some error"
        assert route_after_ted_syntax(state) == "node_debugger"

    def test_route_after_ted_syntax_at_limit(self):
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sc_trial"] = MAX_SC_TRIALS
        state["sc_exception"] = "adder_8bit.sv:8: error: some error"
        assert route_after_ted_syntax(state) == "end_fail_sc"

    def test_route_after_ted_syntax_no_exception(self):
        """When TED finds no parseable error, route to TB instead of debugger."""
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sc_exception"] = None
        state["sc_trial"] = 3
        assert route_after_ted_syntax(state) == "node_tb_sim"

    # ── TED TB routing (enhanced with MultiAttempt) ──
    def test_route_after_ted_tb_under_limit(self):
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["ts_trial"] = 2
        assert route_after_ted_tb(state) == "node_debugger"

    def test_route_after_ted_tb_at_limit(self):
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["ts_trial"] = MAX_TS_TRIALS
        assert route_after_ted_tb(state) == "end_fail_ts"


# ──────────────────────────────────────────────────────────────
# Test 2: Individual node tests
# ──────────────────────────────────────────────────────────────

class TestNodes:
    """Test individual node logic."""

    def test_node_converter(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state(nl_input="Design an 8-bit adder")
        result = nodes.node_converter(state)
        assert result["xml_description"] is not None
        assert "adder_8bit" in result["xml_description"]
        assert result["module_name"] == "adder_8bit"

    def test_node_converter_skip_when_xml_present(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["xml_description"] = GOOD_XML
        result = nodes.node_converter(state)
        assert result == {}

    def test_node_generator_outputs_raw(self):
        """v3: Generator outputs _raw_llm_output, not gvd directly."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["xml_description"] = GOOD_XML
        state["module_name"] = "adder_8bit"
        result = nodes.node_generator(state)
        assert result["_raw_llm_output"] is not None
        assert result["_last_llm_source"] == "generator"
        assert result["multi_attempt_mgr"] is not None
        assert "gvd" not in result  # v3: no direct gvd assignment

    def test_node_sanitizer_extracts_clean_code(self):
        """Sanitizer succeeds with valid Verilog."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["_raw_llm_output"] = GOOD_VERILOG
        state["module_name"] = "adder_8bit"
        state["_last_llm_source"] = "generator"
        result = nodes.node_sanitizer(state)
        assert result["sanitize_result"]["needs_retry"] is False
        assert "gvd" in result
        assert "module adder_8bit" in result["gvd"]
        assert result.get("sgvd") is not None  # set on generator source

    def test_node_sanitizer_extracts_from_markdown(self):
        """Sanitizer extracts code from ```verilog``` fences."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["module_name"] = "adder_8bit"
        state["_last_llm_source"] = "generator"
        state["_raw_llm_output"] = (
            "Here is the code:\n\n"
            "```verilog\n"
            + GOOD_VERILOG +
            "\n```\n\n"
            "This implements an 8-bit adder."
        )
        result = nodes.node_sanitizer(state)
        assert result["sanitize_result"]["needs_retry"] is False
        assert "module adder_8bit" in result["gvd"]

    def test_node_sanitizer_rejects_empty_retries(self):
        """Sanitizer requests retry for empty output (up to max 2)."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["module_name"] = "test"
        state["_last_llm_source"] = "generator"
        state["_raw_llm_output"] = ""
        state["_sanitize_retry_count"] = 0
        result = nodes.node_sanitizer(state)
        assert result["sanitize_result"]["needs_retry"] is True
        assert result["_sanitize_retry_count"] == 1

    def test_node_sanitizer_passes_after_max_retry(self):
        """Sanitizer passes through after max retries, even on empty."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["module_name"] = "test"
        state["_last_llm_source"] = "generator"
        state["_raw_llm_output"] = ""
        state["_sanitize_retry_count"] = 2  # at max
        result = nodes.node_sanitizer(state)
        assert result["sanitize_result"]["needs_retry"] is False
        # Code is set (even if empty) — it still passes to Verilator
        assert "gvd" in result

    def test_node_sanitizer_auto_fixes_missing_endmodule(self):
        """Sanitizer auto-appends endmodule for truncated output."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["module_name"] = "test"
        state["_last_llm_source"] = "debugger"
        state["_raw_llm_output"] = "module test(input a, output b);\n    assign b = a;\n"
        result = nodes.node_sanitizer(state)
        assert result["sanitize_result"]["needs_retry"] is False
        assert "endmodule" in result["gvd"]

    def test_node_syntax_check_clean(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["gvd"] = GOOD_VERILOG
        state["module_name"] = "adder_8bit"
        state["sc_trial"] = 0
        state["total_iter"] = 0

        with patch("comba_pipeline.subprocess.run", return_value=CLEAN_SC_RESULT):
            result = nodes.node_syntax_check(state)

        assert result["sc_exception_count"] == 0
        assert result["sc_trial"] == 1

    def test_node_syntax_check_with_errors(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["gvd"] = BUGGY_VERILOG
        state["module_name"] = "adder_8bit"
        state["sc_trial"] = 0
        state["total_iter"] = 0

        with patch("comba_pipeline.subprocess.run", return_value=SC_ERROR_RESULT):
            result = nodes.node_syntax_check(state)

        assert result["sc_exception_count"] == 1
        assert result["sc_trial"] == 1

    def test_node_ted_syntax_extracts_topmost(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sc_log"] = (
            "adder_8bit.sv:8: error: Signal 'result' not found\n"
            "adder_8bit.sv:9: error: Another error\n"
        )
        result = nodes.node_ted_syntax(state)
        assert result["sc_exception"] is not None
        assert "result" in result["sc_exception"]
        assert result["edp"] is not None

    def test_node_ted_syntax_edtm_tracking(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["sc_log"] = "adder_8bit.sv:8: error: Signal 'result' not found\n"
        state["edtm"] = {}

        # First time
        result = nodes.node_ted_syntax(state)
        sig = list(result["edtm"].keys())[0]
        assert result["edtm"][sig] == 1

        # Simulate repeated failures
        state["edtm"] = result["edtm"]
        for _ in range(EDTM_MAX_RETRIES):
            result = nodes.node_ted_syntax(state)
            state["edtm"] = result["edtm"]

        # After exceeding limit, EDP should contain EDTM warning
        assert "EDTM WARNING" in result["edp"]

    def test_node_debugger_outputs_raw_v3(self):
        """v3: Debugger outputs _raw_llm_output via MultiAttemptManager."""
        llm = create_buggy_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["gvd"] = BUGGY_VERILOG
        state["sc_exception_count"] = 1
        state["sc_trial"] = 1
        state["phase"] = "sc"
        state["module_name"] = "adder_8bit"
        state["sc_exception"] = "adder_8bit.sv:8: error: Signal 'result' not found"
        state["edp"] = "Topmost iverilog error:\nadder_8bit.sv:8: error: Signal 'result' not found"
        state["sc_log"] = "adder_8bit.sv:8: error: Signal 'result' not found\n"
        state["nl_input"] = "Design an 8-bit adder"

        result = nodes.node_debugger(state)
        assert result["_raw_llm_output"] is not None
        assert result["_last_llm_source"] == "debugger"
        assert result["multi_attempt_mgr"] is not None
        assert result["escalation_level"] is not None

    def test_node_debugger_truncates_input(self):
        """Verify that debugger node truncates nl_input to save tokens."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state(nl_input="A" * 1000)
        state["phase"] = "sc"
        state["edp"] = "error"
        
        with patch.object(llm, "invoke", return_value=MagicMock(content="fixed"), create=True) as mock_invoke:
            nodes.node_debugger(state)
            prompt = mock_invoke.call_args[0][0][0].content
            # Check if truncation occurred (limit is 400 chars)
            # The prompt contains more than just nl_input, but nl_input should be short.
            assert "A" * 401 not in prompt
            assert "A" * 400 in prompt

    def test_node_syntax_check_uses_provided_work_dir(self):
        """Verify that syntax check reuses the work_dir from state if present."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        my_dir = "/tmp/my_custom_dir"
        state = make_initial_state(work_dir=my_dir)
        state["gvd"] = "module top; endmodule"
        state["module_name"] = "top"
        
        with patch("comba_pipeline.subprocess.run", return_value=CLEAN_SC_RESULT):
            with patch("comba_pipeline.open", MagicMock()):
                result = nodes.node_syntax_check(state)
                assert result["work_dir"] == my_dir

    def test_node_ted_tb_extracts_todo_failure(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["tb_log"] = (
            "TODO 3 Failed at simtime 42\n"
        )
        state["tb_failure"] = "TODO 3 Failed"

        result = nodes.node_ted_tb(state)
        assert result["tdp"] is not None
        assert "TODO 3 Failed" in result["tdp"]


# ──────────────────────────────────────────────────────────────
# Test 3: E2E Graph tests with mocked Verilator
# ──────────────────────────────────────────────────────────────

class TestE2EGraph:
    """End-to-end tests running the full compiled graph."""

    def _run_graph(self, llm, sc_results, tb_results=None, dataset_dir=None):
        """
        Helper: build graph, run with mocked subprocess.

        Args:
            llm: StubLLM instance
            sc_results: list of mock results for successive SC calls
            tb_results: list of mock results for successive TB calls
            dataset_dir: mock dataset directory
        """
        graph = build_comba_graph(llm)
        state = make_initial_state(nl_input="Design an 8-bit adder")
        if dataset_dir:
            state["dataset_dir"] = dataset_dir

        sc_iter = iter(sc_results)
        tb_iter = iter(tb_results or [])

        def mock_subprocess_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "-tnull" in cmd_str:
                return next(sc_iter, CLEAN_SC_RESULT)
            elif "vvp" in cmd_str.lower() or "iverilog" in cmd_str.lower():
                return next(tb_iter, TB_PASS_RESULT)
            elif "vcdvcd" in cmd_str.lower():
                return make_iverilog_result(0)
            return make_iverilog_result(0)

        original_isfile = os.path.isfile
        def mock_isfile(path):
            if "test.sv" in path or "tb.sv" in path or "tb.v" in path:
                return True
            return original_isfile(path)

        with patch("comba_pipeline.subprocess.run", side_effect=mock_subprocess_run):
            with patch("comba_pipeline.shutil.copy2"):
                with patch("os.path.isfile", side_effect=mock_isfile):
                    result = graph.invoke(state, {"recursion_limit": 150})

        return result

    def test_happy_path(self):
        """SC passes, TB passes → final_status == 'pass'."""
        llm = create_stub_llm()
        result = self._run_graph(
            llm,
            sc_results=[CLEAN_SC_RESULT],
            tb_results=[
                make_iverilog_result(0),  # compile
                TB_PASS_RESULT,            # run
            ],
            dataset_dir="/tmp",
        )
        assert result["final_status"] == "pass"
        assert result["sc_trial"] == 1
        assert result["ts_trial"] == 1

    def test_sc_fix_then_pass(self):
        """SC fails → TED → Debugger → Sanitizer → SC passes → TB passes."""
        llm = create_buggy_stub_llm()
        result = self._run_graph(
            llm,
            sc_results=[
                SC_ERROR_RESULT,    # first SC: fails
                CLEAN_SC_RESULT,    # second SC after fix: passes
            ],
            tb_results=[
                make_iverilog_result(0),
                TB_PASS_RESULT,
            ],
            dataset_dir="/tmp",
        )
        assert result["final_status"] == "pass"
        assert result["sc_trial"] == 2

    def test_sc_iteration_limit(self):
        """SC always fails → hits MAX_SC_TRIALS → fail_sc."""
        llm = create_always_buggy_stub_llm()
        sc_results = [SC_ERROR_RESULT] * (MAX_SC_TRIALS + 5)
        result = self._run_graph(llm, sc_results=sc_results)
        assert result["final_status"] == "fail_sc"
        assert result["sc_trial"] >= MAX_SC_TRIALS

    def test_graph_compiles_and_has_correct_nodes(self):
        """Verify the graph structure is correct."""
        llm = create_stub_llm()
        graph = build_comba_graph(llm)
        graph_obj = graph.get_graph()

        if hasattr(graph_obj, 'nodes'):
            nodes_data = graph_obj.nodes
            if isinstance(nodes_data, dict):
                node_ids = list(nodes_data.keys())
            else:
                try:
                    node_ids = [n.id for n in nodes_data]
                except AttributeError:
                    node_ids = list(nodes_data)
        else:
            node_ids = []

        # Check all expected nodes exist (9 pipeline + 4 terminal = 13)
        expected_nodes = [
            "node_converter",
            "node_generator",
            "node_sanitizer",          # v3: merged node
            "node_syntax_check",
            "node_ted_syntax",
            "node_debugger",
            "node_tb_sim",
            "node_classify_tb",
            "node_vcd_analyzer",
            "node_ted_tb",
            "end_pass",
            "end_fail_sc",
            "end_fail_ts",
            "end_max_iter",
        ]
        for expected in expected_nodes:
            assert expected in node_ids, f"Missing node: {expected}"

        # Old nodes should NOT be present
        assert "node_extraction_guard" not in node_ids
        assert "node_pre_sc_check" not in node_ids
        assert "node_patcher" not in node_ids


# ──────────────────────────────────────────────────────────────
# Test 4: EDTM integration
# ──────────────────────────────────────────────────────────────

class TestEDTM:
    """Test Exception-Debugging Trial Management."""

    def test_edtm_counts_repeated_errors(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)

        edtm = {}
        sc_log = "adder_8bit.sv:8: error: Signal 'result' not found\n"

        for i in range(5):
            # In the real pipeline, this is passed from run_pipeline_sync
            # For tests, we mock it.
            state = make_initial_state()
            state["dataset_dir"] = "/tmp"
            state["sc_log"] = sc_log
            state["edtm"] = edtm
            result = nodes.node_ted_syntax(state)
            edtm = result["edtm"]

        assert any(v == 5 for v in edtm.values())

    def test_edtm_warning_after_threshold(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)

        edtm = {}
        sc_log = "adder_8bit.sv:8: error: Signal 'result' not found\n"

        for i in range(EDTM_MAX_RETRIES + 1):
            # In the real pipeline, this is passed from run_pipeline_sync
            # For tests, we mock it.
            state = make_initial_state()
            state["dataset_dir"] = "/tmp"
            state["sc_log"] = sc_log
            state["edtm"] = edtm
            result = nodes.node_ted_syntax(state)
            edtm = result["edtm"]

        assert "EDTM WARNING" in result["edp"]


# ──────────────────────────────────────────────────────────────
# Test 5: State initialization
# ──────────────────────────────────────────────────────────────

class TestState:
    """Test state creation and defaults."""

    def test_initial_state_defaults(self):
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        assert state["nl_input"] == ""
        assert state["gvd"] is None
        assert state["sc_trial"] == 0
        assert state["ts_trial"] == 0
        assert state["total_iter"] == 0
        assert state["phase"] == "sc"
        assert state["edtm"] == {}
        assert state["final_status"] is None
        assert state["debugger_patch"] is None
        # v3 new fields
        assert state["sanitize_result"] is None
        assert state["_sanitize_retry_count"] == 0
        assert state["multi_attempt_mgr"] is None
        assert state["escalation_level"] is None
        assert state["_last_llm_source"] is None
        assert state["_raw_llm_output"] is None

    def test_initial_state_with_args(self):
        state = make_initial_state(nl_input="test", module_name="foo")
        assert state["nl_input"] == "test"
        assert state["module_name"] == "foo"


# ──────────────────────────────────────────────────────────────
# Test 6: Sanitizer integration
# ──────────────────────────────────────────────────────────────

class TestSanitizer:
    """Test VerilogSanitizer node behavior."""

    def test_sanitizer_warns_on_name_mismatch(self):
        """Name mismatch produces warning but still passes (never blocks)."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["module_name"] = "correct_name"
        state["_last_llm_source"] = "debugger"
        state["_raw_llm_output"] = (
            "module wrong_name(input a, output b);\n"
            "    assign b = a;\n"
            "endmodule\n"
        )
        result = nodes.node_sanitizer(state)
        assert result["sanitize_result"]["needs_retry"] is False
        assert "gvd" in result  # code still passes through
        # Should have a warning about name mismatch
        warnings = result["sanitize_result"]["warnings"]
        assert any("doesn't match" in w for w in warnings)

    def test_sanitizer_no_module_keyword_retry(self):
        """No module keyword triggers retry (not pass-through on first try)."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        # In the real pipeline, this is passed from run_pipeline_sync
        # For tests, we mock it.
        state = make_initial_state()
        state["dataset_dir"] = "/tmp"
        state["module_name"] = "test"
        state["_last_llm_source"] = "generator"
        state["_raw_llm_output"] = "I cannot generate Verilog code for this."
        state["_sanitize_retry_count"] = 0
        result = nodes.node_sanitizer(state)
        assert result["sanitize_result"]["needs_retry"] is True
        assert "gvd" not in result  # not set on retry


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

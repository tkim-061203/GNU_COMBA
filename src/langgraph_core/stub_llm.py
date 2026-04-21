"""
StubLLM for testing COMBA pipeline without a real LLM.

Provides hardcoded responses based on prompt content:
- Converter prompt → known-good XML (adder_8bit)
- Generator prompt → known-good Verilog (or intentionally buggy)
- Debugger prompt → JSON patch {buggy_code, correct_code}

Usage:
    from stub_llm import create_stub_llm, create_buggy_stub_llm
    llm = create_stub_llm()           # returns correct code
    llm = create_buggy_stub_llm()     # returns buggy code for testing fix flow
"""

from typing import Any, List, Optional
import json
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import Field


# ──────────────────────────────────────────────────────────────
# Known-good test data
# ──────────────────────────────────────────────────────────────

GOOD_XML = """\
<module id="adder_8bit">
    <description>Implement a module of an 8-bit adder with carry.</description>
    <ports>
        <input id="a" width_description="[7:0]">8-bit input A.</input>
        <input id="b" width_description="[7:0]">8-bit input B.</input>
        <input id="cin">Carry-in.</input>
        <output id="sum" width_description="[7:0]">8-bit sum output.</output>
        <output id="cout">Carry-out.</output>
    </ports>
    <implementation>Simple behavioral adder using assign.</implementation>
</module>"""

GOOD_VERILOG = """\
module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    assign {cout, sum} = a + b + cin;
endmodule
"""

BUGGY_VERILOG = """\
module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    // Bug: undeclared signal 'result'
    assign result = a + b + cin;
    assign sum = result[7:0];
    assign cout = result[8];
endmodule
"""

FIXED_VERILOG = """\
module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    wire [8:0] result;
    assign result = a + b + cin;
    assign sum = result[7:0];
    assign cout = result[8];
endmodule
"""

WORSE_VERILOG = """\
module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    // Even more bugs after "fix"
    assign result = a + b + cin;
    assign sum = unknown_signal;
    assign cout = another_undeclared;
endmodule
"""

# Use json.dumps() to guarantee correct JSON escaping of newlines
DEBUGGER_PATCH_FIXED = json.dumps({
    "buggy_code": "assign result = a + b + cin;",
    "correct_code": "wire [8:0] result;\n    assign result = a + b + cin;"
})

DEBUGGER_PATCH_BUGGY = json.dumps({
    "buggy_code": "assign result = a + b + cin;",
    "correct_code": "assign result = a + b + cin;"
})

DEBUGGER_PATCH_WORSE = json.dumps({
    "buggy_code": "assign result = a + b + cin;",
    "correct_code": "assign result = a + b + cin;\n    assign sum = unknown_signal;\n    assign cout = another_undeclared;"
})


# ──────────────────────────────────────────────────────────────
# StubLLM Implementation
# ──────────────────────────────────────────────────────────────

class StubLLM(BaseChatModel):
    """
    Fake LLM that returns hardcoded responses for testing.

    Detects the type of prompt from its content and returns
    the appropriate hardcoded response.
    """

    responses: dict = Field(default_factory=dict)
    call_count: int = Field(default=0)
    model_name: str = "stub-llm"
    model_config = {"extra": "allow"}

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Route to correct response based on message content."""
        self.call_count += 1

        # Combine all message contents for detection
        full_text = " ".join(
            m.content for m in messages if hasattr(m, "content")
        ).lower()

        # Determine which response to return
        # Order matters: check debugger/EDP/TDP first (most specific), then generator, then converter
        if ("syntax debugging" in full_text or "functional debugging" in full_text
                or "debugger" in full_text or ("fix" in full_text and "error" in full_text)
                or "json patch" in full_text or "buggy_code" in full_text):
            response_key = "debugger"
        elif "verilog code generator" in full_text or "generate complete" in full_text:
            response_key = "generator"
        elif "specification converter" in full_text or "convert the user" in full_text:
            response_key = "converter"
        else:
            response_key = "default"

        content = self.responses.get(response_key, self.responses.get("default", ""))

        # Support callable responses (for progressive fix simulation)
        if callable(content):
            content = content(self.call_count)

        message = AIMessage(content=content)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])


# ──────────────────────────────────────────────────────────────
# Factory Functions
# ──────────────────────────────────────────────────────────────

def create_stub_llm() -> StubLLM:
    """Create a StubLLM that returns correct code (happy path)."""
    return StubLLM(
        responses={
            "converter": GOOD_XML,
            "generator": GOOD_VERILOG,
            "debugger": DEBUGGER_PATCH_FIXED,
            "default": GOOD_VERILOG,
        }
    )


def create_buggy_stub_llm() -> StubLLM:
    """Create a StubLLM that returns buggy code requiring correction."""
    fix_counter = {"count": 0}

    def progressive_fix(call_number: int) -> str:
        """First call returns buggy, subsequent calls return fixed."""
        fix_counter["count"] += 1
        if fix_counter["count"] <= 1:
            return BUGGY_VERILOG
        return FIXED_VERILOG

    return StubLLM(
        responses={
            "converter": GOOD_XML,
            "generator": BUGGY_VERILOG,
            "debugger": DEBUGGER_PATCH_FIXED,
            "default": GOOD_VERILOG,
        }
    )


def create_always_buggy_stub_llm() -> StubLLM:
    """Create a StubLLM that always returns buggy code (for iteration limit test)."""
    return StubLLM(
        responses={
            "converter": GOOD_XML,
            "generator": BUGGY_VERILOG,
            "debugger": DEBUGGER_PATCH_BUGGY,     # patch that doesn't fix it
            "default": BUGGY_VERILOG,
        }
    )


def create_worse_stub_llm() -> StubLLM:
    """Create a StubLLM whose corrections make things worse (for rollback test)."""
    return StubLLM(
        responses={
            "converter": GOOD_XML,
            "generator": BUGGY_VERILOG,
            "debugger": DEBUGGER_PATCH_WORSE,      # "fix" introduces more errors
            "default": BUGGY_VERILOG,
        }
    )

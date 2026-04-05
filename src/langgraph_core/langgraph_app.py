"""
LangGraph COMBA-PROMPT: Verilog Code Generation trên Laptop.

Workflow:
  User NL Input → [Converter] → COMBA XML → (human review) → [Generator] → Verilog Code

Usage:
  # Generate from natural language description
  python langgraph_app.py "Design an 8-bit adder with carry in and carry out"

  # Generate from existing XML description file
  python langgraph_app.py --xml modules/adder_8bit/design_description.xml

  # Non-interactive mode (skip human review of XML)
  python langgraph_app.py --no-review "Design a 4-bit counter with reset"

  # Save output to file
  python langgraph_app.py -o output.v "Design a frequency divider"
"""

import argparse
import os
import sys
import json
import datetime
from typing import Annotated, Optional
from typing_extensions import TypedDict

from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage

from prompts import converterPromptTemplate, generatorPromptTemplate

# XML validation — reuse COMBA-LLM's pydantic-xml models
try:
    from xmlDescription import Module, Modules
    XML_VALIDATION_AVAILABLE = True
except ImportError:
    XML_VALIDATION_AVAILABLE = False
    print("[WARN] xmlDescription not available — XML validation disabled")


# ──────────────────────────────────────────────────────────────
# State
# ──────────────────────────────────────────────────────────────
class GraphState(TypedDict):
    user_input: str                         # NL description from user
    xml_description: Optional[str]          # COMBA XML output
    xml_valid: Optional[bool]               # XML validation result
    generated_code: Optional[dict]          # {"code": "...", "description": "..."}
    module_name: Optional[str]              # Extracted module name
    error: Optional[str]                    # Error message if any
    skip_converter: bool                    # True if XML provided directly


# ──────────────────────────────────────────────────────────────
# LLM Setup
# ──────────────────────────────────────────────────────────────
def create_llm():
    load_dotenv()
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
    api_key  = os.environ.get("LLM_API_KEY", "ollama")
    model    = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")

    print(f"[LLM] Using {model} @ {base_url}")
    return ChatOpenAI(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=0.1,
    )


# ──────────────────────────────────────────────────────────────
# Nodes
# ──────────────────────────────────────────────────────────────
class CombaNodes:
    def __init__(self, llm):
        self._llm = llm
        self._llm_json = llm.bind(response_format={"type": "json_object"})

    # ── Node: Converter (NL → COMBA XML) ──
    def converter_node(self, state: GraphState) -> GraphState:
        print("\n" + "=" * 60)
        print("🔄 CONVERTER: Natural Language → COMBA XML")
        print("=" * 60)

        if state.get("skip_converter") and state.get("xml_description"):
            print("[SKIP] XML provided directly, skipping conversion.")
            return {}

        result = converterPromptTemplate.invoke({
            "user_input": state["user_input"],
            "conversation": [],
        })
        response = self._llm.invoke(result)
        xml_text = response.content.strip()

        # Clean markdown fences if LLM wraps them
        if xml_text.startswith("```"):
            lines = xml_text.split("\n")
            xml_text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        print("\n📄 Generated COMBA XML:")
        print("-" * 40)
        print(xml_text)
        print("-" * 40)

        # Validate XML with pydantic-xml
        xml_valid = False
        module_name = None
        if XML_VALIDATION_AVAILABLE:
            try:
                mod = Module.from_xml(xml_text)
                xml_valid = True
                module_name = mod.id
                print(f"✅ XML valid — module: {module_name}")
            except Exception:
                try:
                    mods = Modules.from_xml(xml_text)
                    xml_valid = True
                    module_name = mods.root[0].id if mods.root else None
                    print(f"✅ XML valid (multi-module) — first: {module_name}")
                except Exception as e:
                    print(f"⚠️  XML validation failed: {e}")
                    xml_valid = False
        else:
            # If no validator, mark as not checked
            xml_valid = True
            # Try to extract module name from XML text
            import re
            match = re.search(r'<module\s+id="([^"]+)"', xml_text)
            module_name = match.group(1) if match else "unknown_module"

        return {
            "xml_description": xml_text,
            "xml_valid": xml_valid,
            "module_name": module_name,
        }

    # ── Node: Human Review ──
    def human_review_node(self, state: GraphState) -> GraphState:
        """Human-in-the-loop: user reviews and optionally edits XML."""
        if state.get("skip_converter"):
            return {}

        print("\n" + "=" * 60)
        print("👤 HUMAN REVIEW")
        print("=" * 60)
        print("\nDo you want to:")
        print("  [y] Accept this XML and generate Verilog")
        print("  [e] Edit the XML manually")
        print("  [q] Quit")

        while True:
            choice = input("\nChoice (y/e/q): ").strip().lower()
            if choice in ("y", "e", "q"):
                break
            print("Invalid choice. Please enter y, e, or q.")

        if choice == "q":
            print("❌ Cancelled by user.")
            return {"error": "Cancelled by user"}

        if choice == "e":
            print("\nPaste your edited XML below (end with empty line):")
            lines = []
            while True:
                line = input()
                if line.strip() == "":
                    break
                lines.append(line)
            edited_xml = "\n".join(lines)

            # Re-validate
            xml_valid = False
            module_name = state.get("module_name")
            if XML_VALIDATION_AVAILABLE:
                try:
                    mod = Module.from_xml(edited_xml)
                    xml_valid = True
                    module_name = mod.id
                except Exception:
                    try:
                        mods = Modules.from_xml(edited_xml)
                        xml_valid = True
                        module_name = mods.root[0].id if mods.root else module_name
                    except Exception:
                        xml_valid = False
            else:
                xml_valid = True

            return {
                "xml_description": edited_xml,
                "xml_valid": xml_valid,
                "module_name": module_name,
            }

        return {}

    # ── Node: Generator (COMBA XML → Verilog) ──
    def generator_node(self, state: GraphState) -> GraphState:
        print("\n" + "=" * 60)
        print("⚡ GENERATOR: COMBA XML → Verilog Code")
        print("=" * 60)

        if state.get("error"):
            return {}

        xml_desc = state["xml_description"]

        result = generatorPromptTemplate.invoke({
            "user_input": xml_desc,
            "conversation": [],
        })

        # Try JSON mode first, fall back to regular
        for attempt in range(3):
            try:
                response = self._llm_json.invoke(result)
                code_output = json.loads(response.content)
                break
            except (json.JSONDecodeError, Exception) as e:
                if attempt < 2:
                    print(f"  Retry {attempt + 1}/3: {e}")
                    # Fall back to non-JSON mode
                    response = self._llm.invoke(result)
                    content = response.content.strip()

                    # Try to extract JSON from response
                    try:
                        code_output = json.loads(content)
                        break
                    except json.JSONDecodeError:
                        # Try to extract code from markdown
                        import re
                        code_match = re.search(
                            r'```(?:verilog|v)?\s*\n(.*?)\n```',
                            content, re.DOTALL
                        )
                        if code_match:
                            code_output = {
                                "code": code_match.group(1),
                                "description": "Extracted from markdown"
                            }
                            break
                        # Last resort: use entire content as code
                        if attempt == 2:
                            code_output = {
                                "code": content,
                                "description": "Raw LLM output"
                            }

        # Ensure newline at end (Verilator EOFNEWLINE)
        if code_output.get("code") and not code_output["code"].endswith("\n"):
            code_output["code"] += "\n"

        print("\n📝 Generated Verilog Code:")
        print("-" * 40)
        print(code_output.get("code", ""))
        print("-" * 40)

        if code_output.get("description"):
            print(f"\n📌 Description: {code_output['description']}")

        return {
            "generated_code": code_output,
        }


# ──────────────────────────────────────────────────────────────
# Route: check if we should skip to end on error
# ──────────────────────────────────────────────────────────────
def should_continue(state: GraphState):
    if state.get("error"):
        return END
    return "generator"


# ──────────────────────────────────────────────────────────────
# Build Graph
# ──────────────────────────────────────────────────────────────
def build_graph(llm, no_review=False):
    nodes = CombaNodes(llm)

    graph_builder = StateGraph(GraphState)

    graph_builder.add_node("converter", nodes.converter_node)
    graph_builder.add_node("generator", nodes.generator_node)

    if not no_review:
        graph_builder.add_node("human_review", nodes.human_review_node)
        graph_builder.add_edge(START, "converter")
        graph_builder.add_edge("converter", "human_review")
        graph_builder.add_conditional_edges("human_review", should_continue)
    else:
        graph_builder.add_edge(START, "converter")
        graph_builder.add_edge("converter", "generator")

    graph_builder.add_edge("generator", END)

    memory = MemorySaver()
    return graph_builder.compile(checkpointer=memory)


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="LangGraph COMBA-PROMPT",
        description="Verilog code generation using COMBA-PROMPT + LangGraph",
    )
    parser.add_argument(
        "description",
        nargs="?",
        help="Natural language description of the Verilog module",
    )
    parser.add_argument(
        "--xml",
        type=str,
        help="Path to existing COMBA XML description file (skip converter)",
    )
    parser.add_argument(
        "--no-review",
        action="store_true",
        help="Skip human review of XML (auto-accept)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output .v file path",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.description and not args.xml:
        parser.error("Provide either a description or --xml <path>")

    # Build initial state
    initial_state: GraphState = {
        "user_input": "",
        "xml_description": None,
        "xml_valid": None,
        "generated_code": None,
        "module_name": None,
        "error": None,
        "skip_converter": False,
    }

    if args.xml:
        # Load XML from file
        xml_path = os.path.abspath(args.xml)
        if not os.path.isfile(xml_path):
            print(f"❌ File not found: {xml_path}")
            sys.exit(1)
        with open(xml_path, "r", encoding="utf-8") as f:
            xml_content = f.read()

        # Extract module name
        import re
        match = re.search(r'<module\s+id="([^"]+)"', xml_content)
        module_name = match.group(1) if match else "unknown_module"

        initial_state["user_input"] = xml_content
        initial_state["xml_description"] = xml_content
        initial_state["xml_valid"] = True
        initial_state["module_name"] = module_name
        initial_state["skip_converter"] = True
        args.no_review = True  # Skip review when XML provided directly
        print(f"📂 Loaded XML: {xml_path} (module: {module_name})")
    else:
        initial_state["user_input"] = args.description

    # Build and run graph
    llm = create_llm()
    graph = build_graph(llm, no_review=args.no_review)

    print("\n" + "🚀" * 20)
    print("  LangGraph COMBA-PROMPT — Verilog Code Generation")
    print("🚀" * 20)

    config = {
        "configurable": {"thread_id": datetime.datetime.now().isoformat()},
        "recursion_limit": 50,
    }

    final_state = graph.invoke(initial_state, config)

    # ── Output ──
    if final_state.get("error"):
        print(f"\n❌ Error: {final_state['error']}")
        sys.exit(1)

    generated = final_state.get("generated_code", {})
    code = generated.get("code", "")

    if not code:
        print("\n⚠️  No code was generated.")
        sys.exit(1)

    # Save to file
    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        module_name = final_state.get("module_name", "generated_module")
        output_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            f"{module_name}.v"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(code)

    print(f"\n✅ Verilog code saved to: {output_path}")
    print(f"   Module: {final_state.get('module_name', 'N/A')}")
    print(f"   Lines: {len(code.splitlines())}")


if __name__ == "__main__":
    main()

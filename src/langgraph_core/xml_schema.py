"""
Pydantic-XML Schema for COMBA XML descriptions.

Provides:
  - Module, Ports, IO, Logic classes (from original xmlDescription.py)
  - validate_xml() with auto-retry via LLM
  - extract_module_name() helper

Usage:
    from xml_schema import validate_xml, Module

    ok, module, error = validate_xml(xml_text)
    if ok:
        print(f"Module: {module.id}")
"""

import os
import re
import logging
from typing import Optional, List, Literal, Tuple

from pydantic_xml import BaseXmlModel, attr, element, RootXmlModel
from pydantic import Field

logger = logging.getLogger(__name__)


# --------------------------------------------------------------
# Pydantic-XML Schema Classes
# --------------------------------------------------------------

class IDModel(BaseXmlModel):
    """Base model with required id attribute."""
    id: str = attr()


class IO(IDModel):
    """Input/Output port definition."""
    description: Optional[str] = None
    width_description: Optional[str] = attr(default=None)


class Ports(BaseXmlModel, tag="ports"):
    """Port list container. Lists default to empty: some designs legitimately
    have no inputs (e.g. clkgenerator) or no outputs."""
    input: List[IO] = element(default_factory=list)
    output: List[IO] = element(default_factory=list)


class Parameter(IDModel):
    """Parameter definition (for FSMs, parameterized designs)."""
    description: Optional[str] = None
    value: Optional[str] = attr(default=None)


class ParameterDescription(BaseXmlModel, tag="parameter_description"):
    """Parameter section container."""
    parameter: List[Parameter] = element()


class PartialLogicDescription(IDModel):
    """Single logic element with type classification."""
    description: Optional[str] = None
    width_description: Optional[str] = attr(default=None)
    depth_description: Optional[str] = attr(default=None)
    type: Literal[
        "combinational_logic",
        "combinational_logic_operation",
        "sequential_logic",
        "sequential_logic_operation",
    ] = attr()


class LogicDescription(BaseXmlModel, tag="logic_description", search_mode="unordered"):
    """Logic description section with typed logic elements. The <description>
    child is optional: the converter usually emits only typed <logic> children
    (or prose text), and rejecting those blocks fails otherwise-good XML."""
    description: str = element(default="")
    logic: List[PartialLogicDescription] = element(default=None)


class Module(IDModel, tag="module"):
    """
    COMBA Module description.

    Structure:
        <module id="name">
            <description>...</description>
            <ports>...</ports>
            <parameter_description>...</parameter_description>   (optional)
            <logic_description>...</logic_description>           (optional)
            <implementation>...</implementation>
            <task>...</task>                                      (optional)
        </module>
    """
    description: str = element(default=None)
    ports: Optional[Ports] = element(default=None)
    parameter_description: Optional[ParameterDescription] = element(default=None)
    logic_description: Optional[LogicDescription] = element(default=None)
    implementation: str = element()
    task: str = element(default="Give me the complete Verilog code.")


class Modules(RootXmlModel, tag="modules"):
    """Container for multiple modules."""
    root: List[Module]


# --------------------------------------------------------------
# Validation Functions
# --------------------------------------------------------------

# Module-level regex: fences with optional language tag, anywhere in text.
_FENCE_RE = re.compile(r"```[a-zA-Z]*\s*\n?|```", re.MULTILINE)

# Stray-special escaping (opt-in via COMBA_XML_ESCAPE=1).
# The converter LLM often leaks Verilog into XML text ("out <= 4'd0", "a & b"),
# which breaks well-formedness. These rewrite only *stray* specials:
#   & not already part of an entity        -> &amp;
#   < not followed by a plausible tag char -> &lt;   (catches "<=", "< 5")
# Already-valid XML is untouched (idempotent), so it is safe to apply always
# when the flag is on.
_STRAY_AMP_RE = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
# Escape any '<' that does not start a known schema tag. The converter embeds
# raw Verilog in text nodes ('<always @(...)>', 'i < 8', 'a <= b'), and the
# old letter-based heuristic ('<' before a letter = tag) let constructs like
# '<always' through as bogus tags — the #1 cause of malformed converter XML.
_XML_TAGS = (
    "modules", "module", "description", "ports", "input", "output",
    "parameter_description", "parameter", "logic_description", "logic",
    "implementation", "task",
)
_STRAY_LT_RE = re.compile(r"<(?!/?(?:%s)[\s/>]|!|\?)" % "|".join(_XML_TAGS))

def _escape_stray_specials(text: str) -> str:
    text = _STRAY_AMP_RE.sub("&amp;", text)
    text = _STRAY_LT_RE.sub("&lt;", text)
    return text


# <constant>/<state>/<state_value> are what the converter LLM invents for
# parameter_description children (the prompt says "FSM states, named constants"
# and never shows the real tag); the schema wants <parameter>.
_CONSTANT_TAG_RE = re.compile(r"<(/?)(?:constant|state_value|state)\b")
# Verilog reflex: the LLM closes the XML document with 'endmodule'.
_TRAILING_ENDMODULE_RE = re.compile(r"\bendmodule\s*$")
_OPEN_OR_CLOSE_TAG_RE = re.compile(
    r"<(/?)(%s)\b[^>]*?(/?)>" % "|".join(_XML_TAGS)
)


def _normalize_converter_quirks(text: str) -> str:
    """Deterministically repair the converter's recurring XML mistakes:
    tag aliases, Verilog-style closers, and truncated documents."""
    text = _CONSTANT_TAG_RE.sub(r"<\1parameter", text)

    # Output truncated mid-tag (e.g. '<parameter id="STAGE'): trim back to the
    # last complete '>' so the auto-closer below appends to well-formed text.
    if text.rfind("<") > text.rfind(">"):
        text = text[: text.rfind("<")].rstrip()

    # 'endmodule' used to close the document instead of </module>
    if "<module" in text and "</module>" not in text:
        text, n = _TRAILING_ENDMODULE_RE.subn("</module>", text)

    # Auto-close tags left open by output truncation (best effort: the parse
    # then succeeds and validation reports precisely which field is missing).
    stack = []
    for m in _OPEN_OR_CLOSE_TAG_RE.finditer(text):
        closing, name, selfclose = m.group(1), m.group(2), m.group(3)
        if selfclose:
            continue
        if closing:
            if name in stack:
                while stack and stack[-1] != name:
                    stack.pop()
                if stack:
                    stack.pop()
        else:
            stack.append(name)
    if stack:
        text = text.rstrip() + "".join(f"</{t}>" for t in reversed(stack)) + "\n"
    return text


def _clean_xml(xml_text: str) -> str:
    """Strip markdown fences and whitespace from XML text.

    Handles: ``` , ```xml , ```verilog , inline fences, leading/trailing.
    With COMBA_XML_ESCAPE=1, additionally escapes stray '&'/'<' left by the
    LLM (Verilog operators inside text nodes) so more XML parses cleanly.
    """
    text = xml_text.strip()
    # Prefer extracting content between first fence pair if both exist.
    fences = list(_FENCE_RE.finditer(text))
    if len(fences) >= 2:
        text = text[fences[0].end():fences[-1].start()]
    else:
        text = _FENCE_RE.sub("", text)
    text = text.strip()
    if os.environ.get("COMBA_XML_ESCAPE", "0") == "1":
        # Normalize BEFORE escaping: the escaper only whitelists schema tags,
        # so alias tags like <constant>/<state> must be renamed first or they
        # get escaped into text and become unreachable.
        text = _normalize_converter_quirks(text)
        text = _escape_stray_specials(text)
    return text


def _try_parse(xml_text: str) -> Tuple[bool, Optional[Module], Optional[str]]:
    """
    Try parsing XML as Module or Modules.
    Returns: (success, parsed_module_or_None, error_or_None)
    """
    try:
        mod = Module.from_xml(xml_text)
        return True, mod, None
    except Exception as e1:
        try:
            mods = Modules.from_xml(xml_text)
            if mods.root:
                return True, mods.root[0], None
            return False, None, "Modules list is empty"
        except Exception as e2:
            return False, None, f"Single: {e1} | Multi: {e2}"


def validate_xml(
    xml_text: str,
    max_retries: int = 3,
    llm=None,
) -> Tuple[bool, Optional[Module], Optional[str]]:
    """
    Validate COMBA XML with auto-retry.

    Strategy:
      1. Clean text (strip markdown fences)
      2. Try Module.from_xml()
      3. If fails + llm provided -> ask LLM to fix XML -> retry
      4. Repeat up to max_retries

    Args:
        xml_text: Raw XML string (may have markdown fences)
        max_retries: Max LLM fix attempts (default 3)
        llm: Optional LangChain chat model for auto-fix

    Returns:
        (is_valid, parsed_module, error_message)
    """
    # Step 1: Clean
    cleaned = _clean_xml(xml_text)

    # Step 2: Try parse
    ok, module, error = _try_parse(cleaned)
    if ok:
        logger.info(f"[XML] Valid — module: {module.id}")
        return True, module, None

    # Step 3: Auto-retry with LLM
    if llm is None:
        # Downgraded from warning: in tolerant mode (COMBA_XML_STRICT unset)
        # invalid XML is expected and handled at graph level, so this would
        # otherwise flood benchmark logs. node_converter still cprints a
        # per-module "XML invalid" line.
        logger.info(f"[XML] Invalid (no LLM for auto-fix): {error}")
        return False, None, error

    current_xml = cleaned
    for attempt in range(1, max_retries + 1):
        logger.info(f"[XML] Auto-fix attempt {attempt}/{max_retries}")

        fix_prompt = (
            f"The following COMBA XML has a parsing error:\n"
            f"```xml\n{current_xml}\n```\n\n"
            f"Error: {error}\n\n"
            f"Fix the XML so it is valid COMBA format. "
            f"Return ONLY the corrected XML, no explanation."
        )

        try:
            from langchain_core.messages import HumanMessage
            response = llm.invoke([HumanMessage(content=fix_prompt)])
            fixed_xml = _clean_xml(response.content)

            ok, module, error = _try_parse(fixed_xml)
            if ok:
                logger.info(f"[XML] Fixed on attempt {attempt} — module: {module.id}")
                return True, module, None

            current_xml = fixed_xml

        except Exception as e:
            logger.error(f"[XML] LLM fix attempt {attempt} failed: {e}")
            error = str(e)

    logger.warning(f"[XML] Failed after {max_retries} retries: {error}")
    return False, None, error


def extract_module_name(xml_text: str) -> Optional[str]:
    """Quick regex extraction of module name from XML text."""
    match = re.search(r'<module\s+id="([^"]+)"', xml_text)
    return match.group(1) if match else None

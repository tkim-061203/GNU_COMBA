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

import re
import logging
from typing import Optional, List, Literal, Tuple

from pydantic_xml import BaseXmlModel, attr, element, RootXmlModel
from pydantic import Field

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Pydantic-XML Schema Classes
# ──────────────────────────────────────────────────────────────

class IDModel(BaseXmlModel):
    """Base model with required id attribute."""
    id: str = attr()


class IO(IDModel):
    """Input/Output port definition."""
    description: Optional[str] = None
    width_description: Optional[str] = attr(default=None)


class Ports(BaseXmlModel, tag="ports"):
    """Port list container."""
    input: List[IO] = element()
    output: List[IO] = element()


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
    """Logic description section with typed logic elements."""
    description: str = element()
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


# ──────────────────────────────────────────────────────────────
# Validation Functions
# ──────────────────────────────────────────────────────────────

def _clean_xml(xml_text: str) -> str:
    """Strip markdown fences and whitespace from XML text."""
    text = xml_text.strip()

    # Remove ```xml ... ``` wrappers
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        )

    return text.strip()


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
      3. If fails + llm provided → ask LLM to fix XML → retry
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
        logger.warning(f"[XML] Invalid (no LLM for auto-fix): {error}")
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

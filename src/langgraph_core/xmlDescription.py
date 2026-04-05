# Genterated automatically by /run.ipynb
from pydantic_xml import BaseXmlModel, attr, element, RootXmlModel
from pydantic import Field
from typing import Optional, Union, List, Literal

class IDModel(BaseXmlModel):
    id: str = attr()
class IO(IDModel):
    description: Optional[str] = None
    width_description: Optional[str] = attr(default=None)
class Ports(BaseXmlModel, tag="ports"):
    input: List[IO] = element()
    output: List[IO] = element()

class Parameter(IDModel):
    description: Optional[str] = None
class ParameterDescription(BaseXmlModel, tag="parameter_description"):
    parameter: List[Parameter] = element()

class PartialLogicDescription(IDModel):
    description: Optional[str] = None
    width_description: Optional[str] = attr(default=None)
    depth_description: Optional[str] = attr(default=None)
    type: Literal["combinational_logic", "combinational_logic_operation", "sequential_logic", "sequential_logic_operation"] = attr()

class LogicDescription(BaseXmlModel, tag="logic_description", search_mode='unordered'):
    description: str = element()
    logic: List[PartialLogicDescription] = element(default=None)

class Module(IDModel, tag='module'):
    description: str = element(default=None)
    ports: Optional[Ports] = element(default=None)
    parameter_description: Optional[ParameterDescription] = element(default=None)
    logic_description: Optional[LogicDescription] = element(default=None)
    implementation: str = element()
    task: str = element(default="Give me the complete Verilog code.")
class Modules(RootXmlModel, tag='modules'):
    root: List[Module]

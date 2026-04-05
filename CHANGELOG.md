# Changelog

All notable changes to this project will be documented in this file.

## [1.2.1] - 2026-04-05
### Added
- **LangGraph Integration**: Implemented a new parallelization wrapper (`src/main_langgraph.py`) to run LangGraph evaluation dynamically within the legacy Verilog-Eval datasets.
- **Dual GPU LLM Deployment**: Added `launch_dual_gpu.sh` to support serving a base model and debug model simultaneously on 2 GPUs (`vllm.entrypoints.openai.api_server` on ports 8000 & 8001).
- **Makefile Commands**: Introduced `make langgraph` target to automate pipeline executing tasks (spawning 20 concurrent workers) directly from `.build` scopes.

### Changed
- **Autoconfig Instructions**: Updated `README.md` to cleanly guide users on modifying the autotools (`configure.ac`) and regenerating the build system using `autoreconf -fi`.
- **gitignore Adjustments**: Perfected `.gitignore` rules surrounding `VE_testbench` to efficiently bypass `.build_*` sub-directories and `.vcd` files while gracefully picking up fundamental configs (e.g. `Makefile`, `config.log`).

### Removed
- Removed legacy `vllm.sh` and `vllm.yaml` deployment scripts in favor of the optimized dual GPU infrastructure.

## [1.1.0] - 2026-04-04
### Added
- **Data Flow Pipeline 1**: Added make system workflow for Pipeline 1 (`make data-flow`) to automate the serialization of Synthesis, data extraction (`PyranetExtractDataset...`), and Training Dataset filtering.
- **Logic Range Filtering**: Support filtering structures out by an explicit range of logic cell quantities (`--with-cell-range-start` and `--with-cell-range-stop`).
- **Data-Flow Debugging**: Resolved deep-level `multiprocessing.Pool` pickling issues caused by scope leaks in Python runtime environments by ensuring objects aren't strictly passed in global states.

### Changed
- Refactored project directory structure by moving generic evaluation notebooks systematically into the `PyraNetExplorer/` directory.

## [1.0.0] - 2026-04-03
### Added
- **Formalized Build System**: Initialized GNU Autoconf build system `configure.ac` exposing robust configuration flags (`--with-yosys-path`, `--with-provider`, `--with-temp-dir`, etc).

### Changed
- Complete rewrite of Project `README.md` adapting to `verilog-eval` dependencies and local execution workflows.
- Migrated primary architecture layout for experiment setups avoiding scattered folder clusters.

## [0.1.0] - Prior Work
### Added
- Bootstrapped raw dataset generation and stored test HDL module problems.
- Initial scripts linking to `.gguf` bindings and LLM inferences.

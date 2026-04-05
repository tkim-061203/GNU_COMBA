# GNU_COMBA: LLM-based Verilog Evaluation Framework

GNU_COMBA is a comprehensive framework designed for evaluating and benchmarking Large Language Models (LLMs) in the task of Verilog hardware description language generation. It builds upon `VerilogEval` and provides a structured environment for inference, assessment, and experimentation with various LLM providers.

## Key Features

- **Multi-Provider Support**: Supports inference via `llamacpp`, `openai` (and compatible APIs like vLLM), and more.
- **Automated Benchmarking**: Integrated with `VerilogEval` for standardized assessments.
- **Customizable Inference**: Fine-tune parameters like temperature, max tokens, number of samples, and in-context learning (ICL) examples.
- **Modular Flow System**: A flexible execution engine (`flow_src`) for complex processing pipelines.
- **Local Model Serving**: Scripts and configurations for serving models using vLLM.
- **Jupyter Integration**: Easy access to research and development notebooks.

## Project Structure

- `src/`: Core Python source code for inference and processing.
- `src/flow_src`: Experimental modular flow system.
- `ext/`: External dependencies and submodules (e.g., `VerilogEval`).
- `utils/`: Helper scripts and utilities.
- `configure.ac` & `Makefile.in`: Autotools-based build system for managing experiments.
- `environment.yaml`: Conda environment specification.

## Setup

### 1. Clone Submodules

```bash
git submodule update --init --recursive
```

### 2. Environment Setup

It is recommended to use the provided Conda environment:

```bash
conda env create -f environment.yaml
conda activate gnu_comba
```

### 3. Install Icarus Verilog

GNU_COMBA uses **Icarus Verilog (`iverilog`)** version 12 (stable) for both syntax checking and functional testbench simulation. Follow the instructions in the `ext/verilog-eval` repository to install it.

## Usage Guide

GNU_COMBA uses a `configure` and `make` system to manage different evaluation runs.

### Basic Workflow

**Pipeline 2 (Standard Single-Model Inference)**

1. **Create & enter build directory**:
   ```bash
   mkdir -p VE_testbench/generator/.build_sample_e0_t0
   cd VE_testbench/generator/.build_sample_e0_t0
   ```
2. **Configure the experiment**:
   ```bash
   ../../../configure --with-provider=openai --with-model=<model> \
                      --with-temperature=0 --with-samples=1 --with-examples=0 \
                      --with-model-manual=http://localhost:8000/v1 \
                      --with-task=code-complete-iccad2023
   ```
3. **Run inference**:
   ```bash
   make
   ```
4. **Evaluate results**:
   ```bash
   make verilog-eval
   make -j 20
   ```

---

**Pipeline 3 (LangGraph Dual-GPU Multi-Agent Inference)**

1. **Create & enter build directory**:
   ```bash
   mkdir -p VE_testbench/langgraph/.build_sample_e0_t0
   cd VE_testbench/langgraph/.build_sample_e0_t0
   ```
2. **Configure with dual-GPU endpoints**:
   ```bash
   ../../../configure --with-provider=openai --with-model=generator \
                      --with-temperature=0 --with-samples=1 --with-examples=0 \
                      --with-model-manual=http://localhost:8000/v1 \
                      --with-model-submanual=http://localhost:8001/v1 \
                      --with-task=code-complete-iccad2023
   ```
3. **Run LangGraph inference** (spawns 20 parallel workers):
   ```bash
   make langgraph
   ```
4. **Evaluate results**:
   ```bash
   make verilog-eval
   make -j 20
   ```

> **Note:** To clean a build directory before re-running:
> ```bash
> cd <your_build_directory>  # e.g., VE_testbench/langgraph/.build_sample_e0_t0
> rm -rf *
> ```



**1. Standard Inference (Pipeline 2 - Using `make`)**
Common setup configurations use the `eX_tY` naming convention (e: examples, t: temperature). This is the default execution flow for a single model:

- **`e0_t0`**: Zero-shot without examples + Greedy Search (1 sample).
  ```bash
  ../../../configure --with-provider=openai --with-model=qwen-base --with-max_token=4096 --with-temperature=0 --with-samples=1 --with-examples=0 --with-model-manual=http://localhost:8000/v1 --with-task=code-complete-iccad2023
  ```
- **`e0_t8`**: Zero-shot without examples + Temperature 0.8 (generates 20 samples).
  ```bash
  ../../../configure --with-provider=openai --with-model=qwen-base --with-max_token=4096 --with-temperature=0.8 --with-samples=20 --with-examples=0 --with-model-manual=http://localhost:8000/v1 --with-task=code-complete-iccad2023
  ```
- **`e1_t0`**: One-shot with 1 example + Greedy Search.
  ```bash
  ../../../configure --with-provider=openai --with-model=qwen-base --with-max_token=4096 --with-temperature=0 --with-samples=1 --with-examples=1 --with-model-manual=http://localhost:8000/v1 --with-task=code-complete-iccad2023
  ```
- **`e1_t8`**: One-shot with 1 example + Temperature 0.8 (generates 20 samples).
  ```bash
  ../../../configure --with-provider=openai --with-model=qwen-base --with-max_token=4096 --with-temperature=0.8 --with-samples=20 --with-examples=1 --with-model-manual=http://localhost:8000/v1 --with-task=code-complete-iccad2023
  ```

**2. Multi-Agent Inference with LangGraph (Pipeline 3 - Using `make langgraph`)**
In this Multi-Agent setup, both generator and debugger models are used simultaneously. The pipeline automatically performs iterative error correction using LLM-driven feedback.

**Key features:**
- **Automatic Renaming**: The pipeline automatically renames the generated module to `TopModule` in the simulation stage to satisfy `VerilogEval` testbench requirements.
- **Iverilog Simulation**: Uses `iverilog` and `vvp` to provide precise functional feedback to the debugger agent.
- **Dual GPU Routing**: Explicitly declare the Debugger URL (`--with-model-submanual`) to route tasks correctly between the two GPUs.

- **`e0_t0` (Dual GPU LangGraph)**: Routes Generation tasks to port 8000 and Debugger evaluation tasks to port 8001.
  ```bash
  ../../../configure --with-provider=openai --with-model=generator --with-max_token=4096 --with-temperature=0 --with-samples=1 --with-examples=0 --with-model-manual=http://localhost:8000/v1 --with-model-submanual=http://localhost:8001/v1 --with-task=code-complete-iccad2023
  ```

- `--with-provider`: LLM provider (`llamacpp`, `openai`, etc.).
- `--with-model`: Name or path of the model.
- `--with-max_token`: Maximum number of output tokens.
- `--with-temperature`: Sampling temperature.
- `--with-samples`: Number of samples per problem.
- `--with-examples`: Number of ICL examples to include in the prompt.
- `--with-task`: The benchmark task (e.g., `code-complete-iccad2023`).
- `--with-model-manual`: URL for the primary generator LLM override (e.g., `http://localhost:8000/v1`).
- `--with-model-submanual`: URL for the secondary debugging LLM (e.g., `http://localhost:8001/v1`) used in Dual GPU setups.

### Local Model Serving (Dual GPU)

You can serve the base model and debugger model locally on a dual-GPU setup using the provided utility:

```bash
# Start the dual instances (Generator on 8000, Debugger on 8001)
./launch_dual_gpu.sh

# Stop the servers
./launch_dual_gpu.sh --stop

# Check status
./launch_dual_gpu.sh --status
```

## Edit configure.ac (Autoconfig)

To add new configuration parameters (e.g., `--with-my-param`):
1. Open `configure.ac`.
2. Add a new `AC_ARG_WITH` block and `AC_SUBST([my_param])` for the parameter.
3. Open `Makefile.in` and use `@my_param@` wherever you need the variable.
4. Run `autoreconf -fi` in the root directory to regenerate the `configure` script.
5. Re-run your `../configure ...` command to apply.

## Development

To start a Jupyter Lab instance in the source directory:

```bash
make jupyterlab
```

---
Maintainer: Vu-Minh-Thanh Nguyen (nvmthanh@hcmus.edu.vn), Ngoc-Thien-Kim Nguyen (nntkim.work@gmail.com)
Version: 2.2.1

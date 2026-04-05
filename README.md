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

Follow the instructions in the `ext/verilog-eval` repository to install Icarus Verilog, which is required for Verilog evaluation.

## Usage Guide

GNU_COMBA uses a `configure` and `make` system to manage different evaluation runs.

### Basic Workflow

1. **Create a build directory**:
   ```bash
   mkdir .build_experiment
   cd .build_experiment
   ```
1.5. Clean up previous build directory:
   ```bash
   cd .build_sample_e....
   rm -rf */ *
   ```
2. **Configure the experiment**:
   ```bash
   ../configure --with-provider=openai \
                --with-model=your-model-name \
                --with-temperature=0.8 \
                --with-samples=20 \
                --with-task=code-complete-iccad2023
   ```

3. **Run Inference**:
   ```bash
   make
   ```

3.5. **Run LangGraph Inference (COMBA v2)** *(Alternative inference method)*:
   Instead of `make`, you can run the LangGraph pipeline which processes the problems with 20 parallel jobs:
   ```bash
   make langgraph
   ```

4. **Evaluate Results**:
   ```bash
   make verilog-eval
   make -j 20
   ```
Ex:
e0_t0:
../configure --with-provider=openai --with-model=qwen-base --with-max_token=4096 --with-temperature=0 --with-samples=1 --with-examples=0 --with-model-manual=http://localhost:8000/v1 --with-task=code-complete-iccad2023
e0_t8:
../configure --with-provider=openai --with-model=qwen-base --with-max_token=4096 --with-temperature=0.8 --with-samples=20 --with-examples=0 --with-model-manual=http://localhost:8000/v1 --with-task=code-complete-iccad2023
e1_t0:
../configure --with-provider=openai --with-model=qwen-base --with-max_token=4096 --with-temperature=0 --with-samples=1 --with-examples=1 --with-model-manual=http://localhost:8000/v1 --with-task=code-complete-iccad2023
e1_t8:
../configure --with-provider=openai --with-model=qwen-base --with-max_token=4096 --with-temperature=0.8 --with-samples=20 --with-examples=1 --with-model-manual=http://localhost:8000/v1 --with-task=code-complete-iccad2023
### Common Configuration Options

- `--with-provider`: LLM provider (`llamacpp`, `openai`, etc.).
- `--with-model`: Name or path of the model.
- `--with-max_token`: Maximum number of output tokens.
- `--with-temperature`: Sampling temperature.
- `--with-samples`: Number of samples per problem.
- `--with-examples`: Number of ICL examples to include in the prompt.
- `--with-task`: The benchmark task (e.g., `code-complete-iccad2023`).

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

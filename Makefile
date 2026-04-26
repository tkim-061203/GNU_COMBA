JUPYTER_ARGS='--ip 0.0.0.0 --no-browser'
QUIET=@
src_dir           := $(abspath .)
scripts_dir       := $(src_dir)/src
flow_src_dir      := $(scripts_dir)/flow_src
flow_inputs_dir   := $(flow_src_dir)/inputs

# ── Pipeline 2: LLM inference ──────────────────────────────────────────────
# Model served by launch_dual_gpu.sh:
#   port 8000 → --served-model-name generator  (base Qwen / generator)
#   port 8001 → --served-model-name debugger   (merged LoRA / correcter)
GENERATE_FLAGS = --samples=1 --examples=0 --provider=openai \
                 --max-tokens=4096 --temperature=0.8 \
                 --model=generator --revision=None

# ── Pipeline 1: Data-flow parameters (Yosys-based) ─────────────────────────
# See README.md for a visual dataflow diagram of this pipeline.
YOSYS_PATH        := /home/share/oss-cad-suite/bin/yosys
TEMP_DIR          := /tmp
TRAIN_DATASET_DIR := src/TrainDataset
CELL_RANGE_START  := 6
CELL_RANGE_STOP   := 10
FLOW_STEPS        := synthesis,extract,filter

# Derived index paths (relative to src_dir so they survive cd)
TRAIN_INDEX_NPY   := $(src_dir)/$(TRAIN_DATASET_DIR)/train_index2_$(CELL_RANGE_START)_$(CELL_RANGE_STOP).npy
NO_LOGIC_NPY      := $(src_dir)/$(TRAIN_DATASET_DIR)/no_logic_index.npy

# ── Pipeline 3: LangGraph Multi-Agent Verification (LLM-based) ─────────────
# See README.md for a visual dataflow diagram of this pipeline.
LANGGRAPH_DIR     := /home/nntkim/GNU_COMBA/src/langgraph_core
LANGGRAPH_MODULES := verilogeval/*
LANGGRAPH_DESC    := xml
LANGGRAPH_SAMPLES := 1

# ── Testbench simulator selection ──────────────────────────────────────────
# iverilog   = Icarus Verilog (default, fast, .v compatibility)
# verilator  = Verilator (>=5.x, --binary --timing for SV testbenches)
# auto       = pick verilator for RTLLM, iverilog for VerilogEval
# Override at command line:  make RTLLM TS_SIMULATOR=iverilog
TS_SIMULATOR      := iverilog

# ── Targets ────────────────────────────────────────────────────────────────

.PHONY: default jupyterlab verilog-eval \
        data-flow gen-flow-configs \
        synthesis extract filter \
        langgraph-flow langgraph \
        RTLLM RTLLM-iverilog RTLLM-auto VerilogEval-bench \
        check-verilator clean-flow clean help

default:
	echo $(scripts_dir)/main.py ${GENERATE_FLAGS}
	$(QUIET) $(scripts_dir)/main.py ${GENERATE_FLAGS}

jupyterlab:
	$(QUIET) (cd $(src_dir) && jupyter lab $(JUPYTER_ARGS))

verilog-eval:
	cp config.log config.log.old
	$(src_dir)/ext/verilog-eval/configure \
		--with-model=manual_Mistral_7B --with-task=code-complete-iccad2023 \
		--with-samples=1 --with-examples=0 \
		--with-model-manual=True

# ── Full pipeline clean ────────────────────────────────────────────────────
## Removes all generated artifacts across all three pipelines (no cache, no datasets).
clean:
	@echo "=== Cleaning all pipeline artifacts ==="
	@# Pipeline 1 — .run_* dirs
	@echo "--- Pipeline 1: removing .run_* directories..."
	rm -rf $(src_dir)/.run_*
	@# Pipeline 2 — LLM inference outputs
	@echo "--- Pipeline 2: removing LLM inference outputs..."
	rm -f $(src_dir)/config.log
	rm -rf $(src_dir)/samples
	@# Pipeline 3 — LangGraph outputs
	@echo "--- Pipeline 3: removing LangGraph outputs..."
	rm -rf $(LANGGRAPH_DIR)/outputs
	@echo "=== Clean complete ==="

langgraph:
	@echo "=== Running LangGraph Inference (Parallel Jobs) ==="
	$(scripts_dir)/main_langgraph.py ${GENERATE_FLAGS} --model-manual=True --jobs 20 --quiet --desc-type $(LANGGRAPH_DESC)

# ── RTLLM benchmark targets ────────────────────────────────────────────────
# Default RTLLM target uses Verilator (better SV support for RTLLM testbenches).
# Pipeline auto-falls-back to iverilog if Verilator is < 5.x or missing.
RTLLM:
	@echo "=== Running benchmark for RTLLM dataset (simulator: verilator) ==="
	COMBA_TS_SIMULATOR=verilator conda run --no-capture-output -n kim_VE python3 benchmark_langgraph.py --dataset rtllm --trials 5

RTLLM-iverilog:
	@echo "=== Running benchmark for RTLLM dataset (simulator: iverilog) ==="
	COMBA_TS_SIMULATOR=iverilog conda run --no-capture-output -n kim_VE python3 benchmark_langgraph.py --dataset rtllm --trials 5

RTLLM-auto:
	@echo "=== Running benchmark for RTLLM dataset (auto-pick: verilator) ==="
	COMBA_TS_SIMULATOR=auto conda run --no-capture-output -n kim_VE python3 benchmark_langgraph.py --dataset rtllm --trials 5

VerilogEval-bench:
	@echo "=== Running benchmark for VerilogEval dataset (simulator: $(TS_SIMULATOR)) ==="
	COMBA_TS_SIMULATOR=$(TS_SIMULATOR) conda run --no-capture-output -n kim_VE python3 benchmark_langgraph.py --dataset verilogeval --trials 5

# ── Pipeline 1: full data-flow ─────────────────────────────────────────────
## Runs all steps declared in FLOW_STEPS (synthesis, extract, filter).
## Each step updates flow_src/config.json before delegating to flow_src/main.py.
data-flow: gen-flow-configs
	@echo "=== Running Pipeline 1 - steps: $(FLOW_STEPS) ==="
	@mkdir -p $(src_dir)/$(TRAIN_DATASET_DIR)
	@# Build config.json dynamically from FLOW_STEPS
	@python3 -c "\
	import json, sys; \
	steps_map = { \
	  'synthesis': 'PyranetSynthesis', \
	  'extract':   'PyranetExtractDataseByRangeOfLogicCell', \
	  'filter':    'PyranetFilterDataset', \
	}; \
	keys = [s.strip() for s in '$(FLOW_STEPS)'.split(',')]; \
	flow = [steps_map[k] for k in keys if k in steps_map]; \
	json.dump({'flow': flow}, open('$(flow_src_dir)/config.json','w'), indent='\t'); \
	print('config.json ->', flow)"
	cd $(src_dir) && python3 $(flow_src_dir)/main.py
	@echo "=== Pipeline 1 complete ==="

## Generate / refresh the input JSON configs from configure values
gen-flow-configs:
	@echo "--- Generating flow input configs ---"
	@mkdir -p $(src_dir)/$(TRAIN_DATASET_DIR)
	@python3 -c "\
	import json, os; \
	d='$(flow_inputs_dir)'; \
	os.makedirs(d, exist_ok=True); \
	json.dump({ \
	  'temp_dir':   '$(TEMP_DIR)', \
	  'yosys_path': '$(YOSYS_PATH)', \
	}, open(f'{d}/PyranetSynthesis.json','w'), indent='\t'); \
	json.dump({ \
	  'cell_range_start': $(CELL_RANGE_START), \
	  'cell_range_stop':  $(CELL_RANGE_STOP), \
	}, open(f'{d}/PyranetExtractDataseByRangeOfLogicCell.json','w'), indent='\t'); \
	json.dump({ \
	  'dataset_index':        '$(TRAIN_INDEX_NPY)', \
	  'dataset_index_output': '$(NO_LOGIC_NPY)', \
	}, open(f'{d}/PyranetFilterDataset.json','w'), indent='\t'); \
	print('Flow input configs written to $(flow_inputs_dir)')"

# ── Individual step shortcuts ──────────────────────────────────────────────
synthesis: gen-flow-configs
	@echo "--- Step: synthesis only ---"
	@python3 -c "\
	import json; json.dump({'flow':['PyranetSynthesis']}, \
	  open('$(flow_src_dir)/config.json','w'), indent='\t')"
	cd $(src_dir) && python3 $(flow_src_dir)/main.py

extract: gen-flow-configs
	@echo "--- Step: extract only ---"
	@python3 -c "\
	import json; json.dump({'flow':['PyranetExtractDataseByRangeOfLogicCell']}, \
	  open('$(flow_src_dir)/config.json','w'), indent='\t')"
	cd $(src_dir) && python3 $(flow_src_dir)/main.py

filter: gen-flow-configs
	@echo "--- Step: filter only ---"
	@python3 -c "\
	import json; json.dump({'flow':['PyranetFilterDataset']}, \
	  open('$(flow_src_dir)/config.json','w'), indent='\t')"
	cd $(src_dir) && python3 $(flow_src_dir)/main.py

# ── Pipeline 3: LangGraph flow ─────────────────────────────────────────────
langgraph-flow:
	@echo "=== Running Pipeline 3 — LangGraph (simulator: $(TS_SIMULATOR)) ==="
	cd $(LANGGRAPH_DIR) && COMBA_TS_SIMULATOR=$(TS_SIMULATOR) python3 run.py langgraph $(LANGGRAPH_MODULES) --descriptiontype=$(LANGGRAPH_DESC) --samples=$(LANGGRAPH_SAMPLES)
	@echo "=== Configuring VerilogEval ==="
	$(MAKE) verilog-eval
	@echo "=== Pipeline 3 complete ==="

# ── Verilator environment check ────────────────────────────────────────────
## Verify that verilator >= 5.x is available before running RTLLM target
check-verilator:
	@echo "--- Checking Verilator installation ---"
	@which verilator || { echo "❌ verilator not in PATH"; exit 1; }
	@verilator --version
	@verilator --version | grep -qE 'Verilator [5-9]' && echo "✅ Verilator >= 5.x" \
	    || echo "⚠️  Verilator < 5.x detected — pipeline will auto-fall-back to iverilog for SV testbenches"

# ── Cleanup ────────────────────────────────────────────────────────────────
clean-flow:
	@echo "Removing .run_* directories and cached cell counts..."
	rm -rf $(src_dir)/.run_*

# ── Help ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Available targets:"
	@echo "  default        Run LLM inference (Pipeline 2)"
	@echo "  jupyterlab     Start Jupyter Lab"
	@echo "  verilog-eval   Configure verilog-eval benchmark"
	@echo ""
	@echo "  data-flow         Run full Pipeline 1 (steps: $(FLOW_STEPS))"
	@echo "  synthesis         Run synthesis step only"
	@echo "  extract           Run extract step only"
	@echo "  filter            Run filter step only"
	@echo "  gen-flow-configs  Regenerate flow input JSON configs"
	@echo "  clean-flow        Remove .run_* dirs and synthesis cache"
	@echo "  clean             Remove ALL pipeline artifacts (P1 + P2 + P3)"
	@echo "  langgraph-flow    Run Pipeline 3 (LangGraph)"
	@echo ""
	@echo "Benchmark targets:"
	@echo "  RTLLM             Run RTLLM benchmark (simulator: verilator)"
	@echo "  RTLLM-iverilog    Run RTLLM benchmark (simulator: iverilog)"
	@echo "  RTLLM-auto        Run RTLLM benchmark (auto-pick simulator)"
	@echo "  VerilogEval-bench Run VerilogEval benchmark (default: $(TS_SIMULATOR))"
	@echo "  check-verilator   Verify verilator >=5.x is installed"
	@echo ""
	@echo "Configure options for Pipeline 1:"
	@echo "  --with-yosys-path=PATH      (default: $(YOSYS_PATH))"
	@echo "  --with-temp-dir=DIR         (default: $(TEMP_DIR))"
	@echo "  --with-train-dataset-dir=D  (default: $(TRAIN_DATASET_DIR))"
	@echo "  --with-cell-range-start=N   (default: $(CELL_RANGE_START))"
	@echo "  --with-cell-range-stop=N    (default: $(CELL_RANGE_STOP))"
	@echo "  --with-flow-steps=LIST      (default: $(FLOW_STEPS))"
	@echo ""
	@echo "Configure options for Pipeline 3:"
	@echo "  LANGGRAPH_DIR               (default: $(LANGGRAPH_DIR))"
	@echo "  LANGGRAPH_MODULES           (default: $(LANGGRAPH_MODULES))"
	@echo "  LANGGRAPH_DESC              (default: $(LANGGRAPH_DESC))"
	@echo "  LANGGRAPH_SAMPLES           (default: $(LANGGRAPH_SAMPLES))"
	@echo ""
	@echo "Simulator selection:"
	@echo "  TS_SIMULATOR                (default: $(TS_SIMULATOR))"
	@echo "  Values: iverilog | verilator | auto"
	@echo "  Example: make RTLLM TS_SIMULATOR=iverilog"
	@echo ""
JUPYTER_ARGS='--ip 0.0.0.0 --no-browser'
QUIET=@
src_dir           := $(abspath ../../..)
scripts_dir       := $(src_dir)/src
flow_src_dir      := $(scripts_dir)/flow_src
flow_inputs_dir   := $(flow_src_dir)/inputs

# ── Pipeline 2: LLM inference ──────────────────────────────────────────────
GENERATE_FLAGS = --samples=20 --examples=0 --provider=openai \
                 --max-tokens=4096 --temperature=0.8 \
                 --model=generator --revision=@revision@

# Convert quiet config to flag
QUIET_VAL=True
ifeq ($(QUIET_VAL),True)
  LANGGRAPH_QUIET = --quiet
else
  LANGGRAPH_QUIET =
endif

# ── Pipeline 1: Data-flow parameters ──────────────────────────────────────
YOSYS_PATH        := /home/share/oss-cad-suite/bin/yosys
TEMP_DIR          := /tmp
TRAIN_DATASET_DIR := TrainDataset
CELL_RANGE_START  := 0
CELL_RANGE_STOP   := 5
EXTRACT_RANGES    := None
FLOW_STEPS        := synthesis,extract,filter

# Derived index paths (relative to src_dir so they survive cd)
# Fallback naming logic: uses EXTRACT_RANGES if set, else cell range start-stop
ifeq ($(EXTRACT_RANGES),None)
  INDEX_SUFFIX := $(CELL_RANGE_START)_$(CELL_RANGE_STOP)
else
  INDEX_SUFFIX := $(subst ,_,$(EXTRACT_RANGES))
endif

TRAIN_INDEX_NPY   := $(src_dir)/$(TRAIN_DATASET_DIR)/train_index2_$(INDEX_SUFFIX).npy
NO_LOGIC_NPY      := $(src_dir)/$(TRAIN_DATASET_DIR)/no_logic_index.npy

# ── Pipeline 3: LangGraph Multi-Agent Verification (LLM-based) ─────────────
# See README.md for a visual dataflow diagram of this pipeline.
LANGGRAPH_DIR     := /home/nntkim/GNU_COMBA/src/langgraph_core
LANGGRAPH_MODULES := verilogeval/*
LANGGRAPH_DESC    := xml
LANGGRAPH_SAMPLES := 1

# ── Targets ────────────────────────────────────────────────────────────────

.PHONY: default jupyterlab verilog-eval \
        data-flow gen-flow-configs \
        synthesis extract filter \
        langgraph-flow langgraph clean-flow help

default:
	echo $(scripts_dir)/main.py ${GENERATE_FLAGS}
	$(QUIET) $(scripts_dir)/main.py ${GENERATE_FLAGS}

jupyterlab:
	$(QUIET) (cd $(src_dir) && jupyter lab $(JUPYTER_ARGS))

verilog-eval:
	cp config.log config.log.old
	$(src_dir)/ext/verilog-eval/configure \
		--with-model=generator --with-task=code-complete-iccad2023 \
		--with-samples=20 --with-examples=0 \
		--with-model-manual=http://localhost:8000/v1

langgraph:
	@echo "=== Running LangGraph Inference (Parallel Jobs) ==="
	$(scripts_dir)/main_langgraph.py ${GENERATE_FLAGS} --model-manual=http://localhost:8000/v1 --model-submanual=http://localhost:8001/v1 --jobs 20 $(LANGGRAPH_QUIET) --desc-type $(LANGGRAPH_DESC)

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
	  'extract_ranges':   '$(EXTRACT_RANGES)', \
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
	@echo "=== Running Pipeline 3 — LangGraph ==="
	cd $(LANGGRAPH_DIR) && python3 run.py langgraph $(LANGGRAPH_MODULES) --descriptiontype=$(LANGGRAPH_DESC) --samples=$(LANGGRAPH_SAMPLES)
	@echo "=== Configuring VerilogEval ==="
	$(MAKE) verilog-eval
	@echo "=== Pipeline 3 complete ==="

# ── Cleanup ────────────────────────────────────────────────────────────────
clean-flow:
	@echo "Removing .run_* directories and cached cell counts..."
	rm -rf $(src_dir)/.run_* $(src_dir)/.cache_count_num_cell_2

# ── Help ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Available targets:"
	@echo "  default        Run LLM inference (Pipeline 2)"
	@echo "  jupyterlab     Start Jupyter Lab"
	@echo "  verilog-eval   Configure verilog-eval benchmark"
	@echo ""
	@echo "  data-flow      Run full Pipeline 1 (steps: $(FLOW_STEPS))"
	@echo "  langgraph-flow Run Pipeline 3 (LangGraph)"
	@echo "  synthesis      Run synthesis step only"
	@echo "  extract        Run extract step only"
	@echo "  filter         Run filter step only"
	@echo "  gen-flow-configs  Regenerate flow input JSON configs"
	@echo "  clean-flow     Remove .run_* dirs and synthesis cache"
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

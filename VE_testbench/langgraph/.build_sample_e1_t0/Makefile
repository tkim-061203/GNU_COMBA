JUPYTER_ARGS='--ip 0.0.0.0 --no-browser'
QUIET=@
src_dir           := $(abspath /home/nntkim/GNU_COMBA)
scripts_dir       := $(src_dir)/src
flow_src_dir      := $(scripts_dir)/flow_src
flow_inputs_dir   := $(flow_src_dir)/inputs

# ── Pipeline 2: LLM inference ──────────────────────────────────────────────
GENERATE_FLAGS = --samples=1 --examples=1 --provider=openai \
                 --max-tokens=4096 --temperature=0 \
                 --model=generator

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
SC                := 1
LANGGRAPH_DIR     := /home/nntkim/GNU_COMBA/src/langgraph_core
LANGGRAPH_MODULES := verilogeval/*
LANGGRAPH_DESC    := xml
LANGGRAPH_SAMPLES := 1
LANGGRAPH_JOBS    := 15
TS_SIMULATOR     := iverilog
# Best-of-N runtime knobs — overridable per run, e.g. make RTLLM COMBA_MAX_SAMPLES=8
# 10 lands v1 at 93.1% (vs 88.3% at 5): the extra samples recover every
# near-threshold module. COMBA_EARLY_EXIT=1 makes it near-free — easy modules
# still settle on sample 0; only the few failing modules spend more tries.
COMBA_MAX_SAMPLES      := 10
COMBA_PIPELINE_TIMEOUT := 600
COMBA_WALL_BUDGET      := 1200
# COMBA_XML_ESCAPE=1: repair converter XML (escape embedded Verilog, alias tags,
# close truncations) before validation — required for strict pydantic-xml envs.
# COMBA_LLM_SEED: base seed for reproducible LLM sampling (benchmark offsets it
# per trial). Override per run: make RTLLM COMBA_LLM_SEED=123. Empty = unseeded.
COMBA_LLM_SEED    := 42
SC_ENV            := SC=$(SC) COMBA_SELF_CONSISTENCY=$(SC) COMBA_MAX_SAMPLES=$(COMBA_MAX_SAMPLES) COMBA_PIPELINE_TIMEOUT=$(COMBA_PIPELINE_TIMEOUT) COMBA_WALL_BUDGET=$(COMBA_WALL_BUDGET) COMBA_XML_ESCAPE=1 COMBA_LLM_SEED=$(COMBA_LLM_SEED)
# Pin the interpreter: bare `python3`/`python` resolves to conda *base*, which is
# missing pydantic-xml — that silently turns XML validation into a no-op (the
# 07-06 fail_xml collapse). Every Pipeline 3 target must go through test_VE.
CONDA_ENV         := test_VE
PY                := conda run --no-capture-output -n $(CONDA_ENV) python3
RTLLM_REPORTS_DIR := RTLLM/modules
RTLLM_V2_REPORTS_DIR := RTLLM_v2/modules
VEVAL_REPORTS_DIR := verilogeval_outputs


VEVAL_V1_DIR      := $(src_dir)/ext/verilog-eval/dataset_code-complete-iccad2023
VEVAL_V2_DIR      := $(src_dir)/ext/verilog-eval/dataset_spec-to-rtl

# ── `make VerilogEval`: sweep the four eX_tY configs sequentially ──────────
# Per config: create/refresh its build dir, run ../../../configure with that
# config's flags, `make langgraph` inside it, then copy the resulting reports
# to $(VEVAL_SWEEP_REPORTS)/<config>/. Naming: e<examples>_t<temperature>.
# Run a subset with e.g. make VerilogEval VEVAL_CONFIGS='e0_t0 e1_t0'.
VEVAL_CONFIGS       := e0_t0 e0_t8 e1_t0 e1_t8
VEVAL_BUILD_ROOT    := $(src_dir)/VE_testbench/langgraph
VEVAL_SWEEP_REPORTS := $(src_dir)/reports/verilogeval
VEVAL_PROVIDER      := openai
VEVAL_MODEL         := generator
VEVAL_MAX_TOKEN     := 4096
VEVAL_GEN_URL       := http://localhost:8000/v1
VEVAL_DBG_URL       := http://localhost:8001/v1
VEVAL_TASK          := code-complete-iccad2023
# `make -n VerilogEval` is NOT a dry run: GNU make always executes recipe lines
# containing $(MAKE), so configure + the report copy would run for real. The
# recipe checks this and bails out instead.
VEVAL_DRY_RUN       := $(findstring n,$(firstword -$(MAKEFLAGS)))

# ── Targets ────────────────────────────────────────────────────────────────

.PHONY: default jupyterlab verilog-eval \
        data-flow gen-flow-configs \
        synthesis extract filter langgraph langgraph-flow \
        all_RTLLM RTLLM \
        RTLLM_v2 VerilogEval \
        analyze-syntax analyze-syntax-rtllm analyze-syntax-rtllm-v2 analyze-syntax-veval analyze-enum \
        check-verilator check-analyzers clean-flow clean help

default:
	echo $(scripts_dir)/main.py ${GENERATE_FLAGS}
	$(QUIET) $(scripts_dir)/main.py ${GENERATE_FLAGS}

jupyterlab:
	$(QUIET) (cd $(src_dir) && jupyter lab $(JUPYTER_ARGS))

verilog-eval:
	cp config.log config.log.old
	$(src_dir)/ext/verilog-eval/configure \
		--with-model=generator --with-task=code-complete-iccad2023 \
		--with-samples=1 --with-examples=0 \
		--with-model-manual=http://localhost:8000/v1

all_RTLLM:
	$(MAKE) RTLLM
	$(MAKE) RTLLM_v2

RTLLM:
	@echo "=== Start: $$(date) ==="
	@echo "=== Running benchmark for RTLLM dataset (sim: verilator, SC=$(SC)) ==="
	$(SC_ENV) COMBA_TS_SIMULATOR=verilator $(PY) src/benchmark_langgraph.py --dataset rtllm --trials 5 --jobs $(LANGGRAPH_JOBS)
	@echo "=== End: $$(date) ==="
	@$(MAKE) -s analyze-syntax-rtllm

RTLLM_v2:
	@echo "=== Start: $$(date) ==="
	@echo "=== Running benchmark for RTLLM_v2 dataset (sim: verilator, SC=$(SC)) ==="
	$(SC_ENV) COMBA_TS_SIMULATOR=verilator COMBA_FORCE_XML=1 $(PY) src/benchmark_langgraph.py --dataset rtllm_v2 --trials 5 --jobs $(LANGGRAPH_JOBS)
	@echo "=== End: $$(date) ==="
	@$(MAKE) -s analyze-syntax-rtllm-v2


langgraph:
	@echo "=== Running LangGraph Inference: VerilogEval V1 (Parallel) ==="
	$(SC_ENV) $(PY) $(scripts_dir)/main_langgraph.py ${GENERATE_FLAGS} \
		--model-manual=http://localhost:8000/v1 --model-submanual=http://localhost:8001/v1 \
		--jobs $(LANGGRAPH_JOBS) $(LANGGRAPH_QUIET) --desc-type $(LANGGRAPH_DESC) \
		--dataset-dir $(VEVAL_V1_DIR)

# Sequential sweep over VEVAL_CONFIGS. A config that fails does not abort the
# sweep — its reports are still collected if present, and the target exits
# non-zero at the end listing every config that failed.
VerilogEval:
	@echo "=== VerilogEval sweep — configs: $(VEVAL_CONFIGS) ==="
	@echo "=== Reports → $(VEVAL_SWEEP_REPORTS)/<config>/ ==="
	@echo "--- The *_t8 configs use --with-samples=20; at COMBA_MAX_SAMPLES=$(COMBA_MAX_SAMPLES)"
	@echo "--- that is up to 156 x 20 x $(COMBA_MAX_SAMPLES) generations each. To run a subset:"
	@echo "---   make VerilogEval VEVAL_CONFIGS='e0_t0 e1_t0'"
	@if [ -n "$(VEVAL_DRY_RUN)" ]; then \
	  echo "--- -n given: stopping. This target recurses into \$$(MAKE), which GNU make"; \
	  echo "--- runs even under -n, so a real configure would happen. Nothing was done."; \
	  exit 0; \
	fi; \
	fmt() { printf '%02d:%02d:%02d' $$(($$1/3600)) $$(($$1%3600/60)) $$(($$1%60)); }; \
	failed=""; timing=""; sweep_t0=$$(date +%s); \
	for cfg in $(VEVAL_CONFIGS); do \
	  case $$cfg in \
	    e0_t0) ex=0; temp=0;   smp=1  ;; \
	    e0_t8) ex=0; temp=0.8; smp=20 ;; \
	    e1_t0) ex=1; temp=0;   smp=1  ;; \
	    e1_t8) ex=1; temp=0.8; smp=20 ;; \
	    *) echo "!!! unknown config '$$cfg' (expected e0_t0|e0_t8|e1_t0|e1_t8)" >&2; exit 2 ;; \
	  esac; \
	  bdir=$(VEVAL_BUILD_ROOT)/.build_sample_$$cfg; \
	  dst=$(VEVAL_SWEEP_REPORTS)/$$cfg; \
	  echo ""; \
	  echo "############################################################"; \
	  echo "# [$$cfg] examples=$$ex temperature=$$temp samples=$$smp"; \
	  echo "# build: $$bdir"; \
	  echo "############################################################"; \
	  mkdir -p $$bdir || exit 1; \
	  ( cd $$bdir && $(src_dir)/configure \
	      --with-provider=$(VEVAL_PROVIDER) --with-model=$(VEVAL_MODEL) \
	      --with-max_token=$(VEVAL_MAX_TOKEN) \
	      --with-temperature=$$temp --with-samples=$$smp --with-examples=$$ex \
	      --with-self-consistency=$(SC) --with-max-samples=$(COMBA_MAX_SAMPLES) \
	      --with-jobs=$(LANGGRAPH_JOBS) \
	      --with-model-manual=$(VEVAL_GEN_URL) \
	      --with-model-submanual=$(VEVAL_DBG_URL) \
	      --with-task=$(VEVAL_TASK) --with-quiet=True ) || exit 1; \
	  rc=0; \
	  echo "=== [$$cfg] make langgraph — start $$(date) ==="; \
	  t0=$$(date +%s); \
	  ( cd $$bdir && $(MAKE) langgraph ) || rc=$$?; \
	  t1=$$(date +%s); el=$$((t1 - t0)); elh=$$(fmt $$el); \
	  echo "=== [$$cfg] make langgraph — end $$(date) (rc=$$rc, elapsed $$elh) ==="; \
	  timing="$$timing  $$cfg   $$elh  ($$el s, rc=$$rc)\n"; \
	  [ $$rc -eq 0 ] || echo "!!! [$$cfg] make langgraph FAILED" >&2; \
	  mkdir -p $$dst; \
	  if [ -d "$$bdir/reports" ]; then \
	    cp -f $$bdir/reports/summary.txt $$bdir/reports/summary.csv \
	          $$bdir/reports/error_problems.txt $$dst/ 2>/dev/null || true; \
	    { echo "config       : $$cfg"; \
	      echo "finished     : $$(date -Iseconds)"; \
	      echo "build dir    : $$bdir"; \
	      echo "examples     : $$ex"; \
	      echo "temperature  : $$temp"; \
	      echo "samples      : $$smp"; \
	      echo "self-consist : $(SC)"; \
	      echo "max samples  : $(COMBA_MAX_SAMPLES)"; \
	      echo "jobs         : $(LANGGRAPH_JOBS)"; \
	      echo "llm seed     : $(COMBA_LLM_SEED)"; \
	      echo "conda env    : $(CONDA_ENV)"; \
	      echo "langgraph rc : $$rc"; \
	      echo "elapsed      : $$elh ($$el s)"; \
	    } > $$dst/run_info.txt; \
	    echo "=== [$$cfg] reports → $$dst ==="; \
	  else \
	    echo "!!! [$$cfg] no reports/ produced in $$bdir" >&2; \
	    rc=1; \
	  fi; \
	  [ $$rc -eq 0 ] || failed="$$failed $$cfg"; \
	done; \
	sweep_t1=$$(date +%s); tot=$$((sweep_t1 - sweep_t0)); toth=$$(fmt $$tot); \
	mkdir -p $(VEVAL_SWEEP_REPORTS); \
	{ echo "VerilogEval sweep timing"; \
	  echo "finished : $$(date -Iseconds)"; \
	  echo "configs  : $(VEVAL_CONFIGS)"; \
	  echo ""; \
	  echo "  config  elapsed   (langgraph only)"; \
	  printf "%b" "$$timing"; \
	  echo ""; \
	  echo "  TOTAL   $$toth  ($$tot s, includes configure + report copy)"; \
	} | tee $(VEVAL_SWEEP_REPORTS)/sweep_timing.txt; \
	echo ""; \
	if [ -n "$$failed" ]; then \
	  echo "=== VerilogEval sweep finished in $$toth WITH FAILURES:$$failed ==="; exit 1; \
	fi; \
	echo "=== VerilogEval sweep complete in $$toth → $(VEVAL_SWEEP_REPORTS) ==="

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
	cd $(LANGGRAPH_DIR) && python3 $(scripts_dir)/run.py langgraph $(LANGGRAPH_MODULES) --descriptiontype=$(LANGGRAPH_DESC) --samples=$(LANGGRAPH_SAMPLES)
	@echo "=== Configuring VerilogEval ==="
	$(MAKE) verilog-eval
	@echo "=== Pipeline 3 complete ==="

# ── Cleanup ────────────────────────────────────────────────────────────────
clean-flow:
	@echo "Removing .run_* directories and cached cell counts..."
	rm -rf $(src_dir)/.run_* $(src_dir)/.cache_count_num_cell_2

# ── Post-benchmark analyzers ───────────────────────────────────────────────
# `analyze-syntax` runs only if SC was enabled for the previous benchmark.
# It silently no-ops on legacy reports lacking self_consistency metadata.
analyze-syntax: analyze-syntax-rtllm analyze-syntax-rtllm-v2 analyze-syntax-veval

analyze-syntax-rtllm:
	@if [ "$(SC)" = "1" ] && [ -d "$(RTLLM_REPORTS_DIR)" ]; then \
		echo ""; \
		echo "=== Self-Consistency Analysis: RTLLM ==="; \
		python3 src/analyze_self_consistency.py $(RTLLM_REPORTS_DIR) \
			--out reports/analyze_syntax_rtllm.json || true; \
	fi

analyze-syntax-rtllm-v2:
	@if [ "$(SC)" = "1" ] && [ -d "$(RTLLM_V2_REPORTS_DIR)" ]; then \
		echo ""; \
		echo "=== Self-Consistency Analysis: RTLLM_v2 ==="; \
		python3 src/analyze_self_consistency.py $(RTLLM_V2_REPORTS_DIR) \
			--out reports/analyze_syntax_rtllm_v2.json || true; \
	fi

analyze-syntax-veval:
	@if [ "$(SC)" = "1" ] && [ -d "$(VEVAL_REPORTS_DIR)" ]; then \
		echo ""; \
		echo "=== Self-Consistency Analysis: VerilogEval ==="; \
		python3 src/analyze_self_consistency.py $(VEVAL_REPORTS_DIR) \
			--out reports/analyze_syntax_veval.json || true; \
	fi

# ── Help ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Available targets:"
	@echo "  default        Run LLM inference (Pipeline 2)"
	@echo "  jupyterlab     Start Jupyter Lab"
	@echo "  verilog-eval   Configure verilog-eval benchmark"
	@echo ""
	@echo "  data-flow      Run full Pipeline 1 (steps: $(FLOW_STEPS))"
	@echo "  langgraph-flow    Run Pipeline 3 (LangGraph)"
	@echo "  langgraph         Run LangGraph on VerilogEval V1 (Parallel)"
	@echo "  synthesis      Run synthesis step only"
	@echo "  extract        Run extract step only"
	@echo "  filter         Run filter step only"
	@echo "  gen-flow-configs  Regenerate flow input JSON configs"
	@echo "  clean-flow     Remove .run_* dirs and synthesis cache"
	@echo ""
	@echo "Benchmark targets (Pipeline 3):"
	@echo "  all_RTLLM         Run both RTLLM and RTLLM_v2 benchmarks"
	@echo "  RTLLM             Run RTLLM benchmark (simulator: verilator)"
	@echo "  RTLLM_v2          Run RTLLM_v2 benchmark (simulator: verilator)"
	@echo "  VerilogEval       Sweep configs [$(VEVAL_CONFIGS)]: configure +"
	@echo "                    make langgraph each, reports → $(VEVAL_SWEEP_REPORTS)/<cfg>/"
	@echo "                    Subset: make VerilogEval VEVAL_CONFIGS='e0_t0 e1_t0'"
	@echo ""
	@echo "Analyzer targets (auto-run after benchmarks when SC=1):"
	@echo "  analyze-syntax        Analyze self-consistency for both benchmarks"
	@echo "  analyze-syntax-rtllm  Analyze RTLLM SC reports → reports/analyze_syntax_rtllm.json"
	@echo "  analyze-syntax-rtllm-v2  Analyze RTLLM_v2 SC reports → reports/analyze_syntax_rtllm_v2.json"
	@echo "  analyze-syntax-veval  Analyze VerilogEval SC reports → reports/analyze_syntax_veval.json"
	@echo "  analyze-enum          Detect enum/port mismatch issues in RTLLM"
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
	@echo "  LANGGRAPH_JOBS              (default: $(LANGGRAPH_JOBS))  [--with-jobs]"
	@echo ""

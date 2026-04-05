#!/usr/bin/env python

import os, glob, sys, json, re
from tqdm import tqdm
import argparse
from multiprocess import Pool
import subprocess


srcDir = os.path.abspath(os.path.dirname(__file__))

# Import COMBA-LLM langgraph modules locally
sys.path.insert(0, os.path.join(srcDir, "langgraph_core"))

from pipeline_runner import run_pipeline_sync
from llm_interface import COMBALlm

PROBLEM_DIR = os.path.abspath(os.path.join(srcDir, "../ext/verilog-eval/dataset_code-complete-iccad2023"))
VE_SCRIPTS = os.path.abspath(os.path.join(srcDir, "../ext/verilog-eval/scripts"))

def parse_cmdline():
    p = argparse.ArgumentParser()
    p.add_argument("-s", "--samples", type=int, default=1)
    p.add_argument("-j", "--jobs", type=int, default=20)
    p.add_argument("-m", "--model", type=str, default="generator")
    p.add_argument("-t", "--temperature", type=float, default=0.0)
    p.add_argument("--model-manual", type=str, default="http://localhost:8000/v1")
    p.add_argument("--model-submanual", type=str, default="http://localhost:8001/v1")
    p.add_argument("-p", "--provider", type=str, default="openai")
    p.add_argument("-n", "--max-tokens", type=int, default=2048)
    p.add_argument("-P", "--top-p", type=float, default=0.95)
    p.add_argument("-x", "--examples", type=int, default=0)
    p.add_argument("-r", "--revision", type=str, default=None)
    p.add_argument("--pattern", type=str, default="Prob*")
    
    return p.parse_args()

def do_process(problemSet):
    problemPromptPath, setIndex, opts = problemSet
    
    with open(problemPromptPath, 'r') as file:
        problemPrompt = file.read()
        
    problemModuleDefStart = problemPrompt.rfind("module TopModule")
    if problemModuleDefStart == -1:
        return
        
    problemModuleDef = problemPrompt[problemModuleDefStart:]
    problemModuleDescription = problemPrompt[:problemModuleDefStart]
    
    problemPromptFileName = os.path.basename(problemPromptPath)
    problemPromptFileNameNoSuffix = problemPromptFileName[:problemPromptFileName.rfind("_prompt.txt")]
    
    if not os.path.exists(problemPromptFileNameNoSuffix):
        try:
            os.makedirs(problemPromptFileNameNoSuffix, exist_ok=True)
        except:
            pass

    try:
        # User requested wiring args. to ChatOpenAI + submanual model url
        api_base = opts.model_manual
        if not api_base or api_base == "True": # If accidentally set to string "True" in configure.ac
            api_base = "http://localhost:8000/v1"

        api_debugger = opts.model_submanual
        if not api_debugger or api_debugger == "True":
            api_debugger = "http://localhost:8001/v1"

        # Explicitly configure COMBALlm for dual-GPU setup so LangGraph nodes route correctly
        llm = COMBALlm(
            server_mode="dual",
            base_url=api_base,
            debugger_url=api_debugger,
            api_key="manual",
            model_base="generator",
            model_debugger="debugger",
            temperature=opts.temperature,
            max_tokens=opts.max_tokens
        )
    
        full_description = problemModuleDescription + "\n\n" + problemModuleDef
        state = run_pipeline_sync(
            nl_input=full_description,
            module_name=problemPromptFileNameNoSuffix,
            benchmark_id=problemPromptFileNameNoSuffix,
            dataset_dir=PROBLEM_DIR,
            llm=llm
        )
    
        resp = state.get("gvd", "")
        if not resp:
            resp = state.get("error", "// pipeline generated no verillog output")
            
    except Exception as e:
        resp = f"// exception caught during invoke: {e}"
        state = {"error": str(e)}

    # Ensure to create appropriate naming format as output `.build_*`
    sample_base = f"{problemPromptFileNameNoSuffix}/{problemPromptFileNameNoSuffix}_sample{setIndex:02d}"
    verilog_file = f"{sample_base}.sv"
    with open(verilog_file, 'w+') as file:
        file.write(resp)

    # Dump pipeline logs
    all_log_file = f"{sample_base}_response_all.txt"
    with open(all_log_file, 'w+') as file:
        file.write(json.dumps(state, default=str))

    # Create sv-generate.log (required by sv-iv-analyze)
    # Put token usage if available in state
    gen_log_file = f"{sample_base}-sv-generate.log"
    with open(gen_log_file, 'w+') as file:
        file.write(f"prompt_tokens = {state.get('prompt_tokens', 0)}\n")
        file.write(f"resp_tokens = {state.get('resp_tokens', 0)}\n")
        file.write(f"cost = 0.0\n")

    # Rename module to TopModule for final verification simulation
    # Regex replacement: module <any_name> ... -> module TopModule ...
    # Using a generic regex to match the first module definition found
    top_verilog_code = re.sub(
        r'module\s+[a-zA-Z0-9_]+',
        'module TopModule',
        resp,
        count=1,
        flags=re.MULTILINE
    )
    top_verilog_file = f"{sample_base}_TopModule.sv"
    with open(top_verilog_file, 'w') as f_top:
        f_top.write(top_verilog_code)

    # Run Simulation (iverilog)
    test_sv = os.path.join(PROBLEM_DIR, f"{problemPromptFileNameNoSuffix}_test.sv")
    ref_sv = os.path.join(PROBLEM_DIR, f"{problemPromptFileNameNoSuffix}_ref.sv")
    binary_out = f"{sample_base}"
    test_log = f"{sample_base}-sv-iv-test.log"
    
    comp_cmd = ["iverilog", "-Wall", "-Winfloop", "-Wno-timescale", "-g2012", "-s", "tb", "-o", binary_out, top_verilog_file, test_sv, ref_sv]
    
    try:
        with open(test_log, 'w') as log_f:
            # Compile
            res = subprocess.run(comp_cmd, stdout=log_f, stderr=subprocess.STDOUT)
            if res.returncode == 0:
                # Run binary
                subprocess.run(["timeout", "30", f"./{binary_out}"], stdout=log_f, stderr=subprocess.STDOUT)
            else:
                log_f.write(f"Compilation failed with return code {res.returncode}\n")
    except Exception as e:
        with open(test_log, 'a') as log_f:
            log_f.write(f"Simulation execution error: {e}\n")
    finally:
        if os.path.exists(binary_out):
            try:
                os.remove(binary_out)
            except:
                pass
        if os.path.exists(top_verilog_file):
            try:
                os.remove(top_verilog_file)
            except:
                pass

def main():
    opts = parse_cmdline()
    problemDir = PROBLEM_DIR
    problemPromptsPath = glob.glob(f"{problemDir}/{opts.pattern}_prompt.txt")
    problemPromptsPath.sort()

    problemSets = [(x, y, opts) for y in range(1, opts.samples + 1) for x in problemPromptsPath]

    num_cores = opts.jobs
    if num_cores > len(problemSets):
        num_cores = len(problemSets)
    if num_cores == 0:
        num_cores = 1

    with Pool(processes=num_cores) as pool:
        for _ in tqdm(iterable=pool.imap_unordered(do_process, problemSets), total=len(problemSets)):
            pass

    # Post-process: Run analysis
    print("\n=== Running Analysis ===")
    analyze_script = os.path.join(VE_SCRIPTS, "sv-iv-analyze")
    if os.path.exists(analyze_script):
        # Run analysis and capture to summary.txt
        with open("summary.txt", "w") as out:
            subprocess.run([analyze_script, "--csv=summary.csv"], stdout=out, stderr=subprocess.STDOUT)
        
        # Read summary.txt to display pass rate
        with open("summary.txt", "r") as f:
            lines = f.readlines()
            for line in lines:
                if "pass_rate" in line:
                    print(line.strip())
        
        # Generate error summary
        with open("error_problems.txt", "w") as err_f:
            err_f.write("Problems with failures:\n")
            for line in lines:
                # Analysis output lines for problems usually look like: 
                # ProbXXX_name [n/m](x%) ... passfail_string
                # If passfail_string contains anything other than '.', it's a failure.
                if line.startswith("Prob"):
                    parts = line.split()
                    if len(parts) >= 4:
                        passfail = parts[3]
                        if any(c != '.' for c in passfail):
                            err_f.write(line)
    else:
        print(f"Error: Analysis script not found at {analyze_script}")

if __name__ == "__main__":
    main()

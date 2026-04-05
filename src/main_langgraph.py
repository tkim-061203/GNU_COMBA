#!/usr/bin/env python

import os, glob, sys, json
from tqdm import tqdm
import argparse
from multiprocess import Pool
from langchain_openai import ChatOpenAI

srcDir = os.path.abspath(os.path.dirname(__file__))

# Import COMBA-LLM langgraph modules
LANGGRAPH_DIR = "/home/nntkim/nntkim_old/COMBA-LLM"
sys.path.insert(0, os.path.join(LANGGRAPH_DIR, "langgraph_core"))

from pipeline_runner import run_pipeline_sync

def parse_cmdline():
    p = argparse.ArgumentParser()
    p.add_argument("-s", "--samples", type=int, default=1)
    p.add_argument("-j", "--jobs", type=int, default=20)
    p.add_argument("-m", "--model", type=str, default="gpt-3.5-turbo")
    p.add_argument("-t", "--temperature", type=float, default=0.0)
    p.add_argument("--model-manual", type=str, default="http://localhost:8000/v1")
    p.add_argument("-p", "--provider", type=str, default="openai")
    p.add_argument("-n", "--max-tokens", type=int, default=2048)
    p.add_argument("-P", "--top-p", type=float, default=0.95)
    p.add_argument("-x", "--examples", type=int, default=0)
    p.add_argument("-r", "--revision", type=str, default=None)
    
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

        llm = ChatOpenAI(
            base_url=api_base, 
            model=opts.model, 
            temperature=opts.temperature,
            api_key="manual", 
            max_tokens=opts.max_tokens
        )
    
        full_description = problemModuleDescription + "\n\n" + problemModuleDef
        state = run_pipeline_sync(nl_input=full_description, module_name="TopModule", llm=llm)
    
        resp = state.get("gvd", "")
        if not resp:
            resp = state.get("error", "// pipeline generated no verillog output")
            
    except Exception as e:
        resp = f"// exception caught during invoke: {e}"
        state = {"error": str(e)}

    # Ensure to create appropriate naming format as output `.build_*`
    with open(f"{problemPromptFileNameNoSuffix}/{problemPromptFileNameNoSuffix}_sample{setIndex:02d}_response.txt", 'w+') as file:
        file.write(resp)

    # Dump pipeline logs
    with open(f"{problemPromptFileNameNoSuffix}/{problemPromptFileNameNoSuffix}_sample{setIndex:02d}_response_all.txt", 'w+') as file:
        file.write(json.dumps(state, default=str))

def main():
    opts = parse_cmdline()
    problemDir = f"{srcDir}/../ext/verilog-eval/dataset_code-complete-iccad2023"
    problemPromptsPath = glob.glob(f"{problemDir}/Prob*_prompt.txt")
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

if __name__ == "__main__":
    main()

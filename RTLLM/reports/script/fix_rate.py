#!/usr/bin/env python
# coding: utf-8

# # Fix Rate

# In[14]:


import glob, os, json, subprocess, sys


# In[15]:


# os.chdir(os.path.abspath(os.path.join(os.getcwd(), '../../')))
# os.getcwd()
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '../../')))


# In[16]:


import glob, os, json, subprocess
from scripts.constants import Template, ModuleNamePrefix
from scripts.lazy import getTemplateFilenamePath
from run import makeWorkingFolder


# In[12]:


def makeFileRun(workPath='', moduleName='', command='lint'):
    moduleWorkPath = os.path.join(workPath, moduleName)

    commandArgs = ["make", f"WORKDIR={workPath}"]

    commandArgs += [moduleWorkPath + (f'/obj_dir/V{moduleName}' if command=='V' else f'/{command}')]

    compilationCpltProcess = subprocess.run(
        commandArgs,
        stdout=subprocess.PIPE,
    )
    return (compilationCpltProcess.stdout.decode("utf8"), compilationCpltProcess.returncode)


# In[74]:


llm_model="gpt-4o-mini-2024-07-18"
modulePaths = glob.glob('modules/*', root_dir=os.getcwd())
moduleGlobPaths = []
for modulePath in modulePaths:
    moduleGlobPaths += glob.glob(modulePath)

moduleNormPaths = [os.path.normpath(modulePath) for modulePath in moduleGlobPaths]
myexit_str = """#define myexit(condition, content)   \\
    {                                \\
        assert(condition &&content); \\
    }"""

fix_rate_result = {}

for moduleNormPath in moduleNormPaths:
    moduleName = os.path.basename(moduleNormPath)
    print('Process module ', moduleName)
    report_json_path = os.path.join(moduleNormPath, 'reports', f'report_{llm_model}.json')
    if not os.path.isfile(report_json_path):
        print(f"JSON Report file not found for module {moduleName}")
        continue
    with open(report_json_path, 'r') as file:
       report_json_dict = json.load(file)

    state_trials = report_json_dict['state_trial']
    total_trials = len(state_trials)
    exception_trials = report_json_dict['exception_trial']
    for trial_th in range(total_trials):
        state_trial_dict = state_trials[trial_th]
        syntaxLimitTrialsContent = list(state_trial_dict['syntaxLimitTrials'].keys())
        syntaxLimitTrialsLen = len(syntaxLimitTrialsContent)

        #
        exception_rate = 0
        tb_rate = 0

        #
        # if syntax success
        exception_trial = exception_trials[trial_th]
        if exception_trial:
            #
            # last success code
            last_success_code = None

            lastTBSimulationSuccessStatusList = state_trial_dict['lastTBSimulationSuccessStatus']
            lastSyntaxSimilationSuccessStatusList = state_trial_dict['lastSyntaxSimilationSuccessStatus']
            if len(lastTBSimulationSuccessStatusList):
                last_success_code = lastTBSimulationSuccessStatusList[-1]['generated_code']['code']
            elif len(lastSyntaxSimilationSuccessStatusList):
                last_success_code = lastSyntaxSimilationSuccessStatusList[-1]['generated_code']['code']

        if last_success_code == None:
            print(f'The trial {trial_th} of module {moduleName} have no success code!')
        else:
            #
            # syntax log
            # write to llm_code of module
            llm_code_file_path = getTemplateFilenamePath(moduleNormPath, 'v', f'{ModuleNamePrefix.LLM.value}{moduleName}')
            if not os.path.isfile(llm_code_file_path):
                print('Unknow LLM code path', llm_code_file_path)
            else:
                with open(llm_code_file_path, 'w') as file:
                    file.write(last_success_code)

                #
                # make work folder
                makeWorkingFolder([moduleNormPath], Template.TEMPORARYLLMWORKFOLDERNAME.value, ModuleNamePrefix.LLM.value)
                (resultSTDOUTUTF8, returncode) = makeFileRun(Template.TEMPORARYLLMWORKFOLDERNAME.value, moduleName)

    break

if __name__ == "__main__":
    print('here')
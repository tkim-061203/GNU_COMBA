#!/usr/bin/env python

import atexit, json, re
import os, glob, sys
from langchain_community.llms import LlamaCpp
# from langchain_core.callbacks import CallbackManager, StreamingStdOutCallbackHandler
from langchain_core.prompts import PromptTemplate
from tqdm import tqdm
import argparse
from multiprocessing.managers import BaseManager
from multiprocess import Pool

workDir = os.getcwd()
srcDir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(f"{srcDir}/inference_class"))
sys.path.insert(0, srcDir)

from inferenceclass import InferenceClass
from module_extraction import module_extraction, is_module_contain_logic

#-------------------------------------------------------------------------
# Command line processing
#-------------------------------------------------------------------------

class ArgumentParserWithCustomError(argparse.ArgumentParser):
	def error( self, msg = "" ):
		if ( msg ): print("\n ERROR: %s" % msg)
		print("")
		file = open( sys.argv[0] )
		for ( lineno, line ) in enumerate( file ):
			if ( line[0] != '#' ): sys.exit(msg != "")
			if ( (lineno == 2) or (lineno >= 4) ): print( line[1:].rstrip("\n") )

def parse_cmdline():
	p = ArgumentParserWithCustomError( add_help=False )

	p.add_argument( "-s", "--samples",	type=int,   default=1 )
	p.add_argument( "-h", "--help",		action="store_true" )
	p.add_argument( "-p", "--provider",	   type=str,   default="llamacpp")
	p.add_argument( "-n", "--max-tokens",  type=int,   default=2048 )
	p.add_argument( "-t", "--temperature", type=float, default=0.85 )
	p.add_argument( "-m", "--model",	   type=str,   default="gpt-3.5-turbo" )
	p.add_argument( "-P", "--top-p",	   type=float, default=0.95 )
	p.add_argument( "-x", "--examples",	type=int,   default=0 )
	p.add_argument( "-r", "--revision",	type=str,   default=None )
	# p.add_argument( "-v", "--verbose",	 action="store_true" )
	# p.add_argument( "-l", "--list-models", action="store_true" )
	# p.add_argument( "-e", "--explain",	 action="store_true" )
	# p.add_argument( "-r", "--rules",	   action="store_true" )
	# p.add_argument(	   "--output",	  type=str,   default="-" )
	# p.add_argument(	   "--base-url",	type=str,   default=None)
	# p.add_argument(	   "--task",		type=str,   default="code-complete-iccad2023" )
	# p.add_argument( "prompt_filename" )

	opts = p.parse_args()
	if opts.help: p.error()
	return opts

# examples_icl = [{
#	 "instruction": """Implement the Verilog module based on the following description. Assume that signals are positive clock/clk triggered unless otherwise stated.

# The module should implement an incrementer which increments the input by
# one and writes the result to the output. Assume all values are encoded as
# two's complement binary numbers.
# """,
#	 "module_def": """module TopModule
# (
#   input  logic [7:0] in_,
#   output logic [7:0] out
# );

# """,
# "response": """
# <hdls>
# <hdl>
# <module_definition>
# module TopModule
# (
#   input  logic [7:0] in_,
#   output logic [7:0] out
# );
# </module_definition>
# <module_code>
#   // Combinational logic

#   assign out = in_ + 1;

# endmodule
# </module_code>
# </hdl>
# </hdls>
# """
# },
# {"instruction": """Implement the Verilog module based on the following description. Assume that signals are positive clock/clk triggered unless otherwise stated.

# The module should implement an 8-bit registered incrementer with an
# active-high synchronous reset. The 8-bit input is first registered and
# then incremented by one on the next cycle. The internal state should be
# reset to zero when the reset input is one. Assume all values are encoded
# as two's complement binary numbers. Assume all sequential logic is
# triggered on the positive edge of the clock.
# """,
#	 "module_def": """module TopModule
# (
#   input  logic	   clk,
#   input  logic	   reset,
#   input  logic [7:0] in_,
#   output logic [7:0] out
# );
# """,
# "response": """
# <hdls>
# <hdl>
# <module_definition>
# module TopModule
# (
#   input  logic	   clk,
#   input  logic	   reset,
#   input  logic [7:0] in_,
#   output logic [7:0] out
# );
# </module_definition>
# <module_code>
# // Sequential logic

#   logic [7:0] reg_out;

#   always @( posedge clk ) begin
#	 if ( reset )
#	   reg_out <= 0;
#	 else
#	   reg_out <= in_;
#   end

#   // Combinational logic

#   logic [7:0] temp_wire;

#   always @(*) begin
#	 temp_wire = reg_out + 1;
#   end

#   // Structural connections

#   assign out = temp_wire;

# endmodule
# </module_code>
# </hdl>
# </hdls>
# """
# },
# ]

examples_icl = [{
	"instruction": """Implement the Verilog module based on the following description. Assume that signals are positive clock/clk triggered unless otherwise stated.

The module should implement an incrementer which increments the input by
one and writes the result to the output. Assume all values are encoded as
two's complement binary numbers.

module TopModule
(
  input  logic [7:0] in_,
  output logic [7:0] out
);

""",
"response": """
module TopModule
(
  input  logic [7:0] in_,
  output logic [7:0] out
);

  // Combinational logic

  assign out = in_ + 1;

endmodule
"""
},
{"instruction": """Implement the Verilog module based on the following description. Assume that signals are positive clock/clk triggered unless otherwise stated.

The module should implement an 8-bit registered incrementer with an
active-high synchronous reset. The 8-bit input is first registered and
then incremented by one on the next cycle. The internal state should be
reset to zero when the reset input is one. Assume all values are encoded
as two's complement binary numbers. Assume all sequential logic is
triggered on the positive edge of the clock.

module TopModule
(
  input  logic	   clk,
  input  logic	   reset,
  input  logic [7:0] in_,
  output logic [7:0] out
);
""",
"response": """
module TopModule
(
  input  logic	   clk,
  input  logic	   reset,
  input  logic [7:0] in_,
  output logic [7:0] out
);

// Sequential logic

  logic [7:0] reg_out;

  always @( posedge clk ) begin
	if ( reset )
	  reg_out <= 0;
	else
	  reg_out <= in_;
  end

  // Combinational logic

  logic [7:0] temp_wire;

  always @(*) begin
	temp_wire = reg_out + 1;
  end

  // Structural connections

  assign out = temp_wire;

endmodule
"""
},
]



template = """You are an AI programming assistant, utilizing the DeepSeek Coder model, developed by DeepSeek Company, and you only answer questions related to computer science. For politically sensitive questions, security and privacy issues, and other non-computer science questions, you will refuse to answer.
### Instruction:
{instruction}
### Response:
{response}"""

prompt = PromptTemplate.from_template(template)


problemDir = f"{srcDir}/../ext/verilog-eval/dataset_code-complete-iccad2023"

problemPromptsPath = glob.glob(f"{problemDir}/Prob*_prompt.txt")
# print(problemPromptsPath)
# exit()
curProblemsPath = glob.glob(f"Prob*")


def main():
	
	opts = parse_cmdline()
	
	num_samples = opts.samples

	max_tokens = opts.max_tokens
	temperature = opts.temperature
	provider = opts.provider
	# Make sure the model path is correct for your system!
	model = opts.model
	top_p = opts.top_p
	examples = opts.examples
	revision = opts.revision

	global inference_client
	inference_client = InferenceClass(
		# model="/home/thanh/vllm/GNU_COMBA/src/codellama-7b.Q4_K_M.gguf",
		model=model,
		max_tokens=max_tokens,
		temperature=temperature,
		provider=provider,
		top_p=top_p,
		revision=revision
	)
	@atexit.register
	def free_model():
		inference_client.free_model()
	
	# global pbar
	global problemPromptsPath
	problemPromptsPath.sort()
	curProblemsPath.sort()
	
	if curProblemsPath:
		problemPromptsPath_basename = list(map(lambda x: os.path.basename(x), problemPromptsPath))
		
		last_idx = problemPromptsPath_basename.index(curProblemsPath[-1]+"_prompt.txt")
		last_idx = int(input("Continue with Last index? "+ str(last_idx)).strip() or last_idx)
		problemPromptsPath = problemPromptsPath[last_idx:]
	
	# pbar = tqdm(total=len(problemPromptsPath) * num_samples)
	problemSets = [(x, y) for y in range(1, num_samples + 1) for x in problemPromptsPath]
	# exit()
	# for problemPromptPath in problemPromptsPath:
	def do_process(problemSet):
		# print("problemSet", problemSet)
		# exit()
		problemPromptPath, setIndex = problemSet
		problemPrompt = ""
		with open(problemPromptPath, 'r') as file:
			problemPrompt = file.read()
		# print(problemPrompt)
		problemModuleDefStart = problemPrompt.rfind("module TopModule")
		problemModuleDef = problemPrompt[problemModuleDefStart:]
		problemModuleDescription = problemPrompt[:problemModuleDefStart]
		
		# resp = llm_chain.invoke({"instruction": problemModuleDescription, "module_def": problemModuleDef})
		problemPromptFileName = os.path.basename(problemPromptPath)
		problemPromptFileNameNoSuffix = problemPromptFileName[:problemPromptFileName.rfind("_prompt.txt")]
		
		if not os.path.exists(problemPromptFileNameNoSuffix):
			os.makedirs(problemPromptFileNameNoSuffix)
		
		inputprompt: list[str] = []
		inputArgs = []
		appendInstruction = """
You generate the required Verilog code only. Provide only the Verilog module code. Do not provide any additional explanation or commentary."""
		# Don't make further explanation or Verilog comment in the code"""
		for example_i in range(examples):
		# for example in examples_icl:
			example = examples_icl[example_i]
			inputprompt += [template.format(**example)]
			inputArgs.append({
				'role': 'user', 'content': example['instruction'] + appendInstruction})
			inputArgs.append({
				'role': 'assistant', 'content': example['response']})
		inputprompt += [template.format(instruction=problemModuleDescription+appendInstruction+"\n"+problemModuleDef, response="")]
		# inputArgs.append({'instruction': problemModuleDescription+"\n"+problemModuleDef})
		inputArgs.append({'role': 'user', 'content': problemModuleDescription+appendInstruction+"\n"+problemModuleDef})
		with open(f"{problemPromptFileNameNoSuffix}/{problemPromptFileNameNoSuffix}_customprompt.txt", 'w+') as file:
			print('\n'.join(inputprompt), file=file)
		
		# print(inputprompt)
		# break
		i = setIndex
		# for i in range(1,num_samples + 1):
		for _ in range(1):
			additionalPrompt = []
			# lastError = []
			# isPromptCommentComplete = None
			oft_trial_i = 0
			while True and oft_trial_i < 20:
				loop_break = True
				chatArgs = None
# 				while len(lastError):
# 					cur_error = lastError.pop()
# 					if cur_error[0] == 1:
# 						chatArgs = [{'role': 'user', 'content': """The following Verilog code contains Verilog comments.
# You must rewrite this Verilog code with no Verilog comments.
# If these comments contain any Verilog completion requirements, complete the Verilog code with the requirements.
# You must rewrite a new Verilog code with no Verilog comments with the characters \"//\", or the pairs \"/*\" and \"*/\"""" + cur_error[1]},]
				if chatArgs == None:
					chatArgs = inputArgs + additionalPrompt
				with open(f"{problemPromptFileNameNoSuffix}/{problemPromptFileNameNoSuffix}_customprompt.json", 'w+') as file:
					# print('\n'.join(inputprompt), file=file)
					json.dump(chatArgs, file)
				if additionalPrompt:
					additionalPrompt.clear()
				
				response_all_filepath = f"{problemPromptFileNameNoSuffix}/{problemPromptFileNameNoSuffix}_sample{i:02d}_response_all.txt"
				statistic_all_filepath = f"{problemPromptFileNameNoSuffix}/{problemPromptFileNameNoSuffix}_sample{i:02d}_statistic.json"
				if True:
					resp, resp_statistic = inference_client.invoke(None, chatArgs=chatArgs)
					
					#
					# Post process
					generation_prompt = '### Response:'
					if generation_prompt in resp:
						with open(f"{problemPromptFileNameNoSuffix}/error.txt", "a+") as file:
							file.write(f"\n{i}: Generation prompt")
						
						generation_prompt_idx = resp.find(generation_prompt)
						resp = resp[generation_prompt_idx+len(generation_prompt):]

					with open(response_all_filepath, 'w+') as file:
						print(resp, file=file)
					
					with open(statistic_all_filepath, 'w+') as file:
						json.dump(resp_statistic, file)
				

				# if not os.path.isfile(statistic_all_filepath):
				# 	break
				# else:
				# 	# print(f'Skip mo')
				# 	with open(response_all_filepath, 'r') as file:
				# 		resp = file.read()
					
				# 	with open(statistic_all_filepath, 'r') as file:
				# 		resp_statistic = json.load(file)
					
				module_extraction_success = True
				try:
					# Strip markdown code fences that LLMs commonly emit (e.g. ```verilog ... ```)
					resp_for_extraction = re.sub(r'```(?:\w+)?\s*\n?', '', resp)
					resp_for_extraction = re.sub(r'\n?```', '', resp_for_extraction)
					
					module_definition, module_output_code, _, _, all_comment_ranges = module_extraction(resp_for_extraction)
					# print(module_output_code)
					resp = '\n'.join(module_output_code)
				except Exception as e:
					module_extraction_success = False
					print(f"module_extraction fail: {problemPromptFileName} - {str(e)}")
				
				#
				if (not module_extraction_success) and (resp_statistic["completion_tokens"] == max_tokens):
					loop_break = False
					with open(f"{problemPromptFileNameNoSuffix}/error.txt", "a+") as file:
						file.write(f"\n{i}: Out of token")
					oft_trial_i += 1
				elif (not module_extraction_success):
					# Model returned malformed / non-Verilog output — retry with explicit format request
					additionalPrompt = [
						{'role': 'assistant', 'content': resp},
						{'role': 'user', 'content': "Your response must be a valid Verilog module. Provide only the raw Verilog code without any markdown formatting, backticks, or explanation. Start directly with 'module TopModule' and end with 'endmodule'."},
					]
					loop_break = False
					with open(f"{problemPromptFileNameNoSuffix}/error.txt", "a+") as file:
						file.write(f"\n{i}: Extraction fail - retry")
					oft_trial_i += 1
				#
				elif module_extraction_success:
					cur_full_code = '\n'.join(module_definition) + '\n'.join(module_output_code)
					# print(cur_full_code)
					is_cur_module_contain_logic, final_code = is_module_contain_logic(cur_full_code, all_comment_ranges=all_comment_ranges)
					if is_cur_module_contain_logic == None and final_code == None:
						loop_break = False
						with open(f"{problemPromptFileNameNoSuffix}/error.txt", "a+") as file:
							file.write(f"\n{i}: Comment parsing failed")
						oft_trial_i += 1
					
					#
					# is_module_contain_comment = False
					# for comment_range in all_comment_ranges:
					# 	if len(comment_range):
					# 		is_module_contain_comment = True
					# 		break
					#
					if not is_cur_module_contain_logic:
						additionalPrompt = [
							{'role': 'assistant', 'content': final_code},
							{'role': 'user', 'content': "The Verilog code must contain one of keywords performing logic operations, such as \"always\", \"and\", \"assign\", \"not\", \"nand\", \"nor\", \"or\", \"xnor\", \"xor\", or \"display\"."},
						  ]
						loop_break = False
						oft_trial_i += 1
						with open(f"{problemPromptFileNameNoSuffix}/error.txt", "a+") as file:
							file.write(f"\n{i}: No logic keyword")
					# elif is_module_contain_comment and (not isPromptCommentComplete):
					# 	loop_break = False
					# 	lastError.append((1, cur_full_code))
					# 	isPromptCommentComplete = True
				with open(f"{problemPromptFileNameNoSuffix}/{problemPromptFileNameNoSuffix}_sample{i:02d}_response.txt", 'w+') as file:
					print(resp, file=file)

				if loop_break:
					break
				
			# print(all_comment_ranges)
			# pbar.update(1)
			# break
	num_core = os.cpu_count() - 12
	my_range = problemSets

	# synth_error_ex = set()
	# synth_timeout_ex = set()
	# all_total_num_cells = [None] * (len(my_range))
	with Pool(processes=num_core) as pool:
		for _ in tqdm(iterable=pool.imap(do_process, my_range), total=len(my_range)):
			pass


def EndProcesdures():
	inference_client.free_model()
	# pbar.close()

if __name__ == "__main__":
	try:
		main()
		EndProcesdures()
	except KeyboardInterrupt:
		EndProcesdures()


from BaseProcess import BaseProcessClass
from dotenv import load_dotenv
from datasets import load_dataset
import numpy as np
from tqdm import tqdm
import re, numpy as np, sys, os
from multiprocess import Pool

class PyranetFilterDataset(BaseProcessClass):
	def run(self):
		load_dotenv(dotenv_path=f"{self.trigger_path}/.env")
		sys.path.append(os.path.join(self.trigger_path, "src"))
		from module_extraction import module_extraction

		if "dataset_index" in self.input_args:
			dataset = load_dataset('bnadimi/PyraNet-Verilog', split = "train")
			dataset_index = np.load(self.input_args.get("dataset_index"))
			dataset = dataset.select(dataset_index)

		no_logic_index = set()

		# logic_keywords = ["always", "assign", "display", "and", "or", "nand", "nor", "not"]

		logic_keywords = ["always",	"and", "assign",
						"not", "nand", "nor",  "or", 
						# "pull0","pull1",	"strong0","strong1","supply0","supply1",
						# "weak0", "weak1",
						"xnor","xor", "display"]
		
		dataset_no_logic = dataset
		def do_process(i):
			cur_code = dataset_no_logic['code'][i]
			cur_code = cur_code.replace("\\\\", "\\")

			try:
				all_comment_ranges = module_extraction(cur_code)
			except:
				# print(f"Error processing code index {i}: {e}")
				return i
			all_comment_ranges = all_comment_ranges[-1]

			cur_code_lines = cur_code.splitlines()
			final_code = ""
			for ii in range(len(cur_code_lines)):
				cur_code_line = np.array(list(cur_code_lines[ii]))
				cur_comment_ranges = all_comment_ranges[ii]

				filter_range = [i for i in range(len(cur_code_line))]

				for comment_range in cur_comment_ranges:
					if len(comment_range):
						start_range, end_range = comment_range
						if end_range == None:
							end_range = len(cur_code_line)
					else:
						continue

					for iii in range(start_range, end_range):
						if iii in filter_range:
							filter_range.remove(iii)
				final_code += ''.join(cur_code_line[filter_range]) + "\n"
			
			found_logic_keyword = False

			for keyword in logic_keywords:
				match = re.search(r"\b" + re.escape(keyword) + r"\b", final_code)
				if match:
					found_logic_keyword = True
					break
			if not found_logic_keyword:
				# no_logic_index.append(i)
				# return dataset_no_logic["big_idx"][i]
				return i
			return None
		
		num_core = int(os.cpu_count()/2)
		with Pool(processes=num_core) as pool:
			my_range = range(len(dataset_no_logic))
			for i in tqdm(iterable=pool.imap_unordered(do_process, my_range), total=len(my_range)):
				if i != None:
					no_logic_index.add(i)
		
		print(f"Number of samples without logic keywords: {len(no_logic_index)}", list(no_logic_index)[:10])
		# dataset = dataset.filter(lambda example, idx: idx not in no_logic_index, with_indices=True)
		
		out_path = self.input_args.get("dataset_index_output")
		os.makedirs(os.path.dirname(out_path), exist_ok=True)
		np.save(out_path, np.array(list(no_logic_index)))
		print(f"Saved filtered index to: {out_path}")

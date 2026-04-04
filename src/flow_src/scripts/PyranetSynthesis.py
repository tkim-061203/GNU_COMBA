import os, json

from BaseProcess import BaseProcessClass

from datasets import load_dataset
from tqdm import tqdm
from dotenv import load_dotenv
import subprocess, signal, tempfile
from multiprocessing.managers import BaseManager
from multiprocess import Pool

class PyranetSynthesis(BaseProcessClass):
	def run(self):
		print("Running Pyranet Synthesis Process")
		load_dotenv(dotenv_path=f"{self.trigger_path}/.env")
		dataset = load_dataset('bnadimi/PyraNet-Verilog', split = "train")
		
		temp_dir = self.input_args.get("temp_dir")
		yosys_path = self.input_args.get("yosys_path")
		
		def do_process(i):
			example_code = dataset['code'][i]
			
			total_num_cells = 0
			with tempfile.TemporaryDirectory(dir=temp_dir) as tmpdirname:
				os.link(f'{self.trigger_path}/yosys_run/run4.sh', f'{tmpdirname}/run.sh')
				with open(f'{tmpdirname}/top.v', 'w+') as file:
					file.write(example_code)
				try:
					
					runresult = subprocess.Popen(f'systemd-run --scope -p MemoryMax=2G --user ./run.sh "{yosys_path}"',
					
												cwd=tmpdirname,
												stdout=subprocess.DEVNULL,
												stderr=subprocess.DEVNULL,
												shell=True, 
												preexec_fn=os.setsid,
												)

					runresult.wait(300)
					
					if runresult.returncode != 0:

						
						return (i, 0, None)
					else:
						with open(f'{tmpdirname}/out.json', 'r') as file:
							module_synthesis = json.load(file)
							
							for module in module_synthesis['modules']:
								total_num_cells += len(module_synthesis['modules'][module]['num_cells_by_type'])
							
						return (i, 0, total_num_cells)
				except subprocess.TimeoutExpired:
					os.killpg(os.getpgid(runresult.pid), signal.SIGTERM)
					return (i, 1, None)
		
		num_core = int(os.cpu_count()/2)
		my_range = range(len(dataset))

		synth_error_ex = set()
		synth_timeout_ex = set()
		all_total_num_cells = [None] * (my_range[-1] + 1)
		my_cache_dir = f'{self.trigger_path}/.cache_count_num_cell_2'
		os.makedirs(my_cache_dir, exist_ok=True)
		with Pool(processes=num_core) as pool:
			for i in tqdm(iterable=pool.imap_unordered(do_process, my_range), total=len(my_range)):
				ii, timeout, total_num_cells = i
				with open(f'{my_cache_dir}/{ii}.txt', 'w+') as file:
					file.write(','.join([str(x) for x in i[1:]]))
				if timeout:
					synth_timeout_ex.add(ii)
				elif total_num_cells != None:
					all_total_num_cells[ii] = total_num_cells
				else:
					synth_error_ex.add(ii)

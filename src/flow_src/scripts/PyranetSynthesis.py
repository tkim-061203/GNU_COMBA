import os, json

from BaseProcess import BaseProcessClass

from datasets import load_dataset
from tqdm import tqdm
from dotenv import load_dotenv
import subprocess, signal, tempfile
from multiprocessing.managers import BaseManager
from multiprocess import Pool

# Cat bot log cua tung ca that bai (yosys co the in rat dai khi loi lan truyen).
MAX_LOG_BYTES = 8192


class PyranetSynthesis(BaseProcessClass):
	def run(self):
		print("Running Pyranet Synthesis Process")
		load_dotenv(dotenv_path=f"{self.trigger_path}/.env")
		dataset = load_dataset('bnadimi/PyraNet-Verilog', split = "train")

		temp_dir = self.input_args.get("temp_dir")
		yosys_path = self.input_args.get("yosys_path")
		# MOI: gom TAT CA ca khong tong hop duoc vao dung 1 log JSONL de phan tich.
		# Ban chay goc day stdout/stderr vao DEVNULL -> 362,159 ca chi con nhan
		# "unknown-error" khong kem nguyen nhan. Ghi log tai day de go nut do.
		fail_log = self.input_args.get(
			"fail_log", f"{self.trigger_path}/reports/pyranet_synth_failures.jsonl")
		os.makedirs(os.path.dirname(fail_log), exist_ok=True)

		def do_process(i):
			example_code = dataset['code'][i]

			total_num_cells = 0
			num_cell_types = 0
			with tempfile.TemporaryDirectory(dir=temp_dir) as tmpdirname:
				os.link(f'{self.trigger_path}/src/yosys_run/run4.sh', f'{tmpdirname}/run.sh')
				with open(f'{tmpdirname}/top.v', 'w+') as file:
					file.write(example_code)
				runresult = None
				try:
					# Log di vao log.txt BEN TRONG scope: giu nguyen hanh vi
					# systemd-run/MemoryMax cua ban goc, va vi ghi ra FILE chu khong
					# phai PIPE nen khong co nguy co day day pipe buffer -> treo.
					runresult = subprocess.Popen(
						f'systemd-run --scope -p MemoryMax=2G --user ./run.sh "{yosys_path}" > log.txt 2>&1',
						cwd=tmpdirname,
						stdout=subprocess.DEVNULL,
						stderr=subprocess.DEVNULL,
						shell=True,
						preexec_fn=os.setsid,
						)

					runresult.wait(300)

					def _read_log():
						try:
							with open(f'{tmpdirname}/log.txt', errors='replace') as f:
								return f.read()[-MAX_LOG_BYTES:]
						except OSError:
							return ''

					if runresult.returncode != 0:
						return (i, 0, None, None, runresult.returncode, _read_log())
					else:
						with open(f'{tmpdirname}/out.json', 'r') as file:
							module_synthesis = json.load(file)

							for module in module_synthesis['modules']:
								# num_cells = TONG so cell; len(num_cells_by_type) = SO LOAI cell.
								# Ban goc trong repo chi giu so LOAI -> khong tai lap duoc
								# bucket cua train_index2_*.npy (von dung TONG). Ghi ca hai.
								total_num_cells += module_synthesis['modules'][module]['num_cells']
								num_cell_types  += len(module_synthesis['modules'][module]['num_cells_by_type'])

						return (i, 0, total_num_cells, num_cell_types, 0, None)
				except subprocess.TimeoutExpired:
					os.killpg(os.getpgid(runresult.pid), signal.SIGKILL)
					runresult.wait()
					return (i, 1, None, None, None, '<TIMEOUT 300s>')
				except BaseException:
					# Bat ky duong thoat nao khac cung phai killpg, neu khong yosys
					# thanh mo coi va dot CPU (bai hoc tu su co vvp mo coi).
					if runresult is not None and runresult.poll() is None:
						try:
							os.killpg(os.getpgid(runresult.pid), signal.SIGKILL)
						except (ProcessLookupError, PermissionError):
							pass
					raise

		num_core = int(os.cpu_count()/2)
		my_range = range(len(dataset))

		synth_error_ex = set()
		synth_timeout_ex = set()
		all_total_num_cells = [None] * (my_range[-1] + 1)
		my_cache_dir = f'{self.trigger_path}/.cache_count_num_cell_2'
		os.makedirs(my_cache_dir, exist_ok=True)
		with open(fail_log, 'w') as flog:
			with Pool(processes=num_core) as pool:
				for i in tqdm(iterable=pool.imap_unordered(do_process, my_range), total=len(my_range)):
					ii, timeout, total_num_cells, num_cell_types, returncode, log = i
					# Truong [0],[1] giu nguyen dinh dang cu (Extract... doc dung 2 truong
					# nay); [2] la so LOAI cell, them vao nen tuong thich nguoc.
					with open(f'{my_cache_dir}/{ii}.txt', 'w+') as file:
						file.write(','.join([str(x) for x in (timeout, total_num_cells, num_cell_types)]))
					if timeout:
						synth_timeout_ex.add(ii)
					elif total_num_cells != None:
						all_total_num_cells[ii] = total_num_cells
					else:
						synth_error_ex.add(ii)
					if log is not None:
						flog.write(json.dumps({
							'index': ii,
							'kind': 'timeout' if timeout else 'error',
							'returncode': returncode,
							'log': log,
						}, ensure_ascii=False) + '\n')

		print(f"synth OK        : {len(dataset) - len(synth_error_ex) - len(synth_timeout_ex)}")
		print(f"timeout (>300s) : {len(synth_timeout_ex)}")
		print(f"khong tong hop  : {len(synth_error_ex)}")
		print(f"log that bai    : {fail_log}")

from datetime import datetime
import os, sys, json, importlib, importlib.util
from pathlib import Path
run_dir_prefix = ".run"

cur_main_path = Path(__file__).parent
trigger_path = Path(os.getcwd())
seq_process_config = {}
global_obj = {}

def seq_process_func_setup():
	with open(f"{cur_main_path}/config.json", "r") as f:
		config = json.load(f)
	
	#
	current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
	seq_process_config["run_dir"] = f"{run_dir_prefix}_{current_datetime}"
	os.makedirs(seq_process_config["run_dir"], exist_ok=True)
	os.chdir(seq_process_config["run_dir"])
	print(f"Created and switched to run directory: {seq_process_config['run_dir']}")

	seq_process_config.update(config)
	print("Config loaded: ", seq_process_config)

def seq_process_func_run_processes(**kwargs):
	for process_name in seq_process_config["flow"]:
		print(f"Running process: {process_name}")

		spec = importlib.util.spec_from_file_location(process_name, f"{str(cur_main_path)}/scripts/{process_name}.py")
		process_module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(process_module)
		
		process_class = getattr(process_module, process_name)
		process_instance = process_class(trigger_path=trigger_path, main_path=kwargs.get("cur_main_path"), global_obj=global_obj)
		process_instance.run()
	
seq_process_list = [seq_process_func_setup, seq_process_func_run_processes]

def main():
	
	seq_flow_cnt = 0

	try:
		while True:
			if seq_flow_cnt == len(seq_process_list):
				break
			
			#
			# input setup
			match seq_flow_cnt:
				case 0:
					# Handle first flow
					seq_process_input = {}
				case 1:
					seq_process_input = {"cur_main_path": cur_main_path}
			
			seq_process_list[seq_flow_cnt](**seq_process_input)
			
			seq_flow_cnt += 1
			# seq_flow_cnt %= len(seq_process_list)
			
	except KeyboardInterrupt:
		print("Exiting...")
	
	# os.makedirs(f"{run_dir_prefix}_{current_datetime}", exist_ok=True)


if __name__ == "__main__":

	# NOTE: Do NOT store the pool in global_obj — pool objects cannot be
	# pickled by dill, which would break serialisation of inner functions
	# in child scripts (PyranetSynthesis, etc.).  Each script creates its
	# own pool internally; the top-level pool is no longer needed here.
	main()

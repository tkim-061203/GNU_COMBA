from BaseProcess import BaseProcessClass

from datasets import load_dataset
from tqdm import tqdm
from transformers import AutoTokenizer
from concurrent.futures import ThreadPoolExecutor
import glob, numpy as np, os, sys
from dotenv import load_dotenv

load_dotenv()



class PyranetExtractDataseByRangeOfLogicCell(BaseProcessClass):
	def run(self):
		sys.path.append(self.trigger_path)

		# ── Configuration & Dataset Load ─────────────────────────────────────
		extract_ranges_str = self.input_args.get("extract_ranges", "6-10")
		print(f"Extraction Process Started: {extract_ranges_str}")

		dataset = load_dataset('bnadimi/PyraNet-Verilog', split="train")

		cache_dir = os.path.join(self.trigger_path, ".cache_count_num_cell_2")
		all_num_cell_file = glob.glob(f"{cache_dir}/*")

		if not all_num_cell_file:
			raise RuntimeError(f"No synthesis cache found at {cache_dir}. Run 'make synthesis' first.")

		all_cell_num_with_no_null = np.array([[None, None]] * len(dataset))

		def do_process_task(filename_path):
			file_name = os.path.basename(filename_path)
			try:
				logic_index = int(file_name.replace(".txt", ""))
				with open(filename_path, 'r') as file:
					file_list = file.read().split(",")
					return (logic_index, tuple(file_list))
			except:
				return (None, (None, None))

		# ── Thread Pool Creation (Stable for Dynamic Imports) ────────────────
		print(f"Reading cache results from {len(all_num_cell_file)} files...")
		num_workers = min(os.cpu_count() or 4, 32)
		with ThreadPoolExecutor(max_workers=num_workers) as executor:
			for result in tqdm(executor.map(do_process_task, all_num_cell_file), 
			                  total=len(all_num_cell_file)):
				logic_index, file_list = result
				if logic_index is not None and logic_index < len(all_cell_num_with_no_null):
					all_cell_num_with_no_null[logic_index][0] = int(file_list[0]) if file_list[0] is not None else None
					all_cell_num_with_no_null[logic_index][1] = int(file_list[1]) if file_list[1] != 'None' else None

				# ── Filtering and Labeling ───────────────────────────────────────────
		all_cell_num_with_no_null = all_cell_num_with_no_null[:, 1]
		all_cell_num_with_no_null = np.column_stack((all_cell_num_with_no_null, range(len(dataset))))
		valid_idx = np.where(all_cell_num_with_no_null[:, 0] != None)
		filtered_data = all_cell_num_with_no_null[valid_idx].astype(np.uint64)

		# ── Range Extraction (Direct numeric filter) ─────────────────────────
		cell_range_start = int(self.input_args.get("cell_range_start", 6))
		cell_range_stop  = int(self.input_args.get("cell_range_stop", 10))
		extract_ranges_str = f"{cell_range_start}-{cell_range_stop}"
		print(f"Filtering cells in range [{cell_range_start}, {cell_range_stop}]")

		# Filter trực tiếp bằng numeric range — không cần bucket label
		cell_counts = filtered_data[:, 0]
		segment_mask = (cell_counts >= cell_range_start) & (cell_counts <= cell_range_stop)
		segment_idxs = np.where(segment_mask)[0]

		print(f"Samples matching range: {len(segment_idxs)}")

		# ── Mapping back to Original Global Indices ──────────────────────────
		original_idxs = filtered_data[segment_idxs, 1]
		
		print(f"Total dataset: {len(dataset)}")
		print(f"Non-None count: {len(valid_idx[0])}")
		print(f"Matched segments: {len(segment_idxs)}")
		print(f"Original idxs: {len(original_idxs)}")

		# Update dataset using original indices
		dataset = dataset.select(original_idxs)
		self.global_obj["dataset"] = dataset
		print(dataset)

		# ── Savings (GNU_COMBA structure) ────────────────────────────────────
		out_dir = os.path.join(self.trigger_path, "src", "TrainDataset")
		os.makedirs(out_dir, exist_ok=True)
		out_name = f"train_index2_{extract_ranges_str.replace(',', '_')}.npy"
		
		# Save original indices
		np.save(os.path.join(out_dir, out_name), original_idxs)
		print(f"Saved original dataset indices to: {os.path.join(out_dir, out_name)}")
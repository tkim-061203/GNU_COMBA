from BaseProcess import BaseProcessClass

from datasets import load_dataset
from tqdm import tqdm
from transformers import AutoTokenizer
from dotenv import load_dotenv
import glob, numpy as np, os, sys

load_dotenv()


class PyranetExtractDataseByRangeOfLogicCell(BaseProcessClass):
	def run(self):
		print(self.trigger_path)
		sys.path.append(str(self.trigger_path))

		# ── Cell range tu input config (duoc gen boi Makefile gen-flow-configs) ──
		cell_range_start = int(self.input_args.get("cell_range_start", 0))
		cell_range_stop  = int(self.input_args.get("cell_range_stop",  5))
		print(f"Extracting samples with logic cell count in [{cell_range_start}, {cell_range_stop}]")

		dataset = load_dataset('bnadimi/PyraNet-Verilog', split="train")

		cache_dir = f"{self.trigger_path}/.cache_count_num_cell_2"
		all_num_cell_file = glob.glob(f"{cache_dir}/*")

		# ── Guard: cache rong → yeu cau chay synthesis truoc ──────────────────
		if len(all_num_cell_file) == 0:
			raise RuntimeError(
				f"\n[PyranetExtract] ERROR: No synthesis cache found at '{cache_dir}'.\n"
				f"  Please run the synthesis step first:\n"
				f"    make synthesis\n"
				f"  Or reconfigure with --with-flow-steps=synthesis,extract,filter"
			)

		print(f"Found {len(all_num_cell_file)} cached synthesis results.")

		all_cell_num_with_no_null = np.array([[None, None]] * len(dataset))

		def do_process(i):
			filename_path = all_num_cell_file[i]
			file_name = os.path.basename(filename_path)
			logic_index = int(file_name.replace(".txt", ""))
			with open(filename_path, 'r') as file:
				file_list = file.read().split(",")
				return (logic_index, tuple(file_list))

		my_range = range(len(all_num_cell_file))
		pool = self.global_obj["pool"]

		for i in tqdm(iterable=pool.imap_unordered(do_process, my_range), total=len(my_range)):
			logic_index, file_list = i
			all_cell_num_with_no_null[logic_index][0] = int(file_list[0])
			all_cell_num_with_no_null[logic_index][1] = int(file_list[1]) if file_list[1].strip() != 'None' else None

		# ── Chi giu cac entry da co ket qua synthesis (khong None) ─────────
		all_cell_num_with_no_null = all_cell_num_with_no_null[:, 1]
		all_cell_num_with_no_null = np.column_stack((all_cell_num_with_no_null, range(len(dataset))))
		valid_idx = np.where(all_cell_num_with_no_null[:, 0] != None)
		all_cell_num_with_no_null = all_cell_num_with_no_null[valid_idx].astype(np.uint64)

		if len(all_cell_num_with_no_null) == 0:
			raise RuntimeError(
				f"[PyranetExtract] ERROR: All {len(all_num_cell_file)} cache entries have None cell count "
				f"(synthesis may have failed for all samples)."
			)

		max_cell = int(np.max(all_cell_num_with_no_null[:, 0]))
		print(f"Max logic cell count in cache: {max_cell} "
		      f"(across {len(all_cell_num_with_no_null)} synthesized samples)")

		# ── Gan bucket label cho tung mau theo cell count ────────────────────
		all_cell_num_with_no_null = np.column_stack(
			(all_cell_num_with_no_null.astype(object), [''] * len(all_cell_num_with_no_null))
		)

		step_i = 5
		for i in range(len(all_cell_num_with_no_null)):
			int_x = int(all_cell_num_with_no_null[i][0])
			if int_x == 0:
				all_cell_num_with_no_null[i][2] = '0-0'
			else:
				for bucket_start in range(1, max_cell + step_i, step_i):
					bucket_end = bucket_start + step_i - 1
					if bucket_start <= int_x <= bucket_end:
						all_cell_num_with_no_null[i][2] = f'{bucket_start}-{bucket_end}'
						break

		# ── Trich xuat dung range [cell_range_start, cell_range_stop] ─────────
		if cell_range_start == 0:
			segment_idxs = np.where(all_cell_num_with_no_null[:, 2] == '0-0')[0]
		else:
			segment_idxs = np.array([], dtype=np.int64)

		for bucket_start in range(max(1, cell_range_start), cell_range_stop + 1, step_i):
			bucket_end = bucket_start + step_i - 1
			bucket_label = f'{bucket_start}-{bucket_end}'
			idxs = np.where(all_cell_num_with_no_null[:, 2] == bucket_label)[0]
			segment_idxs = np.concatenate((segment_idxs, idxs))

		segment_idxs = np.unique(segment_idxs)
		print(f"Samples in range [{cell_range_start}, {cell_range_stop}]: {len(segment_idxs)}")

		dataset = dataset.select(segment_idxs)
		self.global_obj["dataset"] = dataset
		print(dataset)

		# ── Luu index voi ten file phan anh dung range ────────────────────────
		os.makedirs(f"{self.trigger_path}/TrainDataset", exist_ok=True)
		out_path = f"{self.trigger_path}/TrainDataset/train_index2_{cell_range_start}_{cell_range_stop}.npy"
		np.save(out_path, segment_idxs)
		print(f"Saved index to: {out_path}")

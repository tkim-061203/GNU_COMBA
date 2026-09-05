#!/usr/bin/env python3
"""Do cell count sau tong hop Yosys cho code REFINE-VerilogV2 sinh ra, doi chieu
voi golden RTL (verified_*.v / *_ref.sv), tren RTLLM v1.1, RTLLM v2.0, VerilogEval V2.

Script doc lap, hau ky - KHONG dung toi pipeline COMBA. Tai su dung dung chuoi lenh
Yosys cua Muc 3.3.1 (loc corpus Pyranet), xem src/flow_src/scripts/PyranetSynthesis.py
va src/yosys_run/run4.sh:
    yosys -m slang -p 'read_slang top.v; hierarchy -simcheck -auto-top; tee -o out.json stat -json'

Khac voi PyranetSynthesis.py: script nay doc dung "num_cells" / "num_cells_by_type"
tu stat -json de lay TONG so cell (PyranetSynthesis.py dung len(num_cells_by_type)
la SO LOAI cell, khong phai tong - xem cot *_num_cell_types de doi chieu voi cach
dem cu neu can).

Vi flow nay khong co buoc `synth`, cell o muc RTL ($dff, $mux, $add, ...) chu KHONG
map ve gate nguyen thuy ($_DFF_P_, $_MUX_, ...). Dem flip-flop / latch dua tren
substring "dff" / "latch" (khong phan biet hoa thuong) de bat duoc ca hai kieu ten
neu sau nay doi flow.
"""
import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

YOSYS_BIN_DEFAULT = "/home/share/oss-cad-suite/bin/yosys"
TIMEOUT_DEFAULT = 300  # giay - giong PyranetSynthesis.py (Muc 3.3.1)
YOSYS_PASSES = "read_slang top.v; hierarchy -simcheck -auto-top; tee -o out.json stat -json"

MODULE_BLOCK_RE = re.compile(r"\bmodule\s+(\w+)\b.*?\bendmodule\b", re.DOTALL)
MISSING_MODULE_RE = re.compile(
    r"unknown module|is not part of the design|is used but not defined",
    re.IGNORECASE,
)

CSV_FIELDS = [
    "benchmark", "module_name", "description_type", "run_source",
    "functional_status",
    "gen_synth_status", "gen_total_cells", "gen_pyranet_bucket", "gen_total_wires",
    "gen_num_cell_types",
    "gen_num_ff", "gen_num_latch", "gen_num_memories", "gen_num_memory_bits",
    "gen_cells_by_type",
    "ref_synth_status", "ref_total_cells", "ref_pyranet_bucket", "ref_total_wires",
    "ref_num_cell_types",
    "ref_num_ff", "ref_num_latch", "ref_num_memories", "ref_num_memory_bits",
    "ref_cells_by_type",
    "cell_ratio", "ff_ratio",
    "comparable", "exclusion_reason",
]


def strip_tb_modules(code: str) -> str:
    """Bo cac module co ten bat dau bang tb_ / test_ (khong phan biet hoa thuong).
    Phong ngua truong hop code sinh ra tu chua ca mot module tu-kiem-thu."""

    def _sub(m):
        name = m.group(1)
        if re.match(r"^(tb_|test_)", name, re.IGNORECASE):
            return ""
        return m.group(0)

    return MODULE_BLOCK_RE.sub(_sub, code)


def run_yosys(yosys_bin: str, code: str, timeout: int, workdir: Path, keep_tmp: bool):
    """Chay dung command Muc 3.3.1 tren `code`. Tra ve dict ket qua."""
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "top.v").write_text(code)
    out_json = workdir / "out.json"

    cmd = [yosys_bin, "-m", "slang", "-p", YOSYS_PASSES]
    proc = subprocess.Popen(
        cmd, cwd=workdir,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, preexec_fn=os.setsid,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            proc.communicate(timeout=5)
        except Exception:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        return {"status": "timeout", "stat": None, "log": "timeout after %ds" % timeout}

    combined = (stdout or "") + "\n" + (stderr or "")
    if proc.returncode != 0 or not out_json.exists():
        status = "error_missing_submodule" if MISSING_MODULE_RE.search(combined) else "error_other"
        return {"status": status, "stat": None, "log": combined.strip()[-2000:]}

    try:
        stat = json.loads(out_json.read_text())
    except Exception as e:
        return {"status": "error_other", "stat": None, "log": f"bad out.json: {e}"}
    finally:
        if not keep_tmp:
            try:
                out_json.unlink()
            except OSError:
                pass

    return {"status": "ok", "stat": stat, "log": ""}


PYRANET_BUCKETS = [(0, 5, "0-5"), (6, 10, "6-10"), (11, 15, "11-15")]


def pyranet_bucket(total_cells) -> str:
    """Khoang cell-count dung de loc corpus PyraNet (Muc 3.3.1, xem
    src/TrainDataset/train_index2_*.npy): 0-5, 6-10, 11-15, 16+."""
    if total_cells == "" or total_cells is None:
        return ""
    n = int(total_cells)
    for lo, hi, label in PYRANET_BUCKETS:
        if lo <= n <= hi:
            return label
    return "16+"


def summarize_stat(stat_json: dict):
    """Cong don so cell/wire tren toan bo module trong thiet ke (flow nay khong
    co synth/flatten rieng, nhung slang frontend thuong da elaborate phang ve
    mot module duy nhat; cong tat ca de an toan neu con nhieu module)."""
    total_cells = 0
    total_wires = 0
    total_mem = 0
    total_mem_bits = 0
    cells_by_type = {}
    for mod in stat_json.get("modules", {}).values():
        total_cells += mod.get("num_cells", 0)
        total_wires += mod.get("num_wires", 0)
        total_mem += mod.get("num_memories", 0)
        total_mem_bits += mod.get("num_memory_bits", 0)
        for ctype, n in mod.get("num_cells_by_type", {}).items():
            cells_by_type[ctype] = cells_by_type.get(ctype, 0) + n

    num_ff = sum(n for t, n in cells_by_type.items() if "dff" in t.lower())
    num_latch = sum(n for t, n in cells_by_type.items() if "latch" in t.lower())
    return {
        "total_cells": total_cells,
        "total_wires": total_wires,
        "num_cell_types": len(cells_by_type),
        "num_ff": num_ff,
        "num_latch": num_latch,
        "num_memories": total_mem,
        "num_memory_bits": total_mem_bits,
        "cells_by_type": cells_by_type,
    }


def synth_one(yosys_bin: str, code: str, timeout: int, tmp_root: str, keep_tmp: bool, tag: str):
    code = strip_tb_modules(code)
    with tempfile.TemporaryDirectory(prefix=f"cellbloat_{tag}_", dir=tmp_root) as td:
        workdir = Path(td)
        result = run_yosys(yosys_bin, code, timeout, workdir, keep_tmp)
        if keep_tmp:
            print(f"  [keep-tmp] {tag}: {workdir}", file=sys.stderr)
        if result["status"] != "ok":
            return {"status": result["status"], "log": result["log"], **{
                k: "" for k in (
                    "total_cells", "total_wires", "num_cell_types",
                    "num_ff", "num_latch", "num_memories", "num_memory_bits",
                )
            }, "cells_by_type": {}}
        summary = summarize_stat(result["stat"])
        return {"status": "ok", "log": "", **summary}


# ---------------------------------------------------------------------------
# Benchmark-specific loaders. Each yields dicts:
#   module_name, description_type, run_source, functional_status, gen_code, ref_path
# ---------------------------------------------------------------------------

def resolve_golden_rtllm(golden_dir: Path, module_name: str) -> Path:
    """Ten file golden thuong la verified_<module>.v nhung khong phai luon dung
    quy uoc do (vd RTLLM_v2/modules/adder_pipe_64bit/verified_adder_64bit.v,
    multi_booth_8bit/verified_booth4_mul.v) - glob verified_*.v de an toan."""
    exact = golden_dir / module_name / f"verified_{module_name}.v"
    if exact.exists():
        return exact
    module_dir = golden_dir / module_name
    if module_dir.is_dir():
        candidates = sorted(module_dir.glob("verified_*.v"))
        if len(candidates) == 1:
            return candidates[0]
    return exact  # khong tim thay -> tra ve duong dan khong ton tai, ghi nhan ref_file_missing


def load_rtllm(results_dir: Path, golden_dir: Path, description_type: str, only):
    for module_dir in sorted(results_dir.iterdir()):
        if not module_dir.is_dir():
            continue
        module_name = module_dir.name
        if only and module_name not in only:
            continue
        reports_dir = module_dir / "reports"
        if not reports_dir.is_dir():
            continue
        for report_path in sorted(reports_dir.glob("report_langgraph.*.json")):
            if "trial" in report_path.stem:
                continue
            m = re.match(r"report_langgraph\.(.+)\.json$", report_path.name)
            desc_type = m.group(1) if m else "?"
            if description_type and desc_type != description_type:
                continue
            try:
                data = json.loads(report_path.read_text())
            except Exception as e:
                print(f"WARN: khong doc duoc {report_path}: {e}", file=sys.stderr)
                continue
            samples = data.get("samples", {})
            gen_code = samples.get("gvd")
            functional_status = samples.get("final_status", "unknown")
            ref_path = resolve_golden_rtllm(golden_dir, module_name)
            yield {
                "module_name": module_name,
                "description_type": desc_type,
                "run_source": str(report_path),
                "functional_status": functional_status,
                "gen_code": gen_code,
                "ref_path": ref_path,
            }


def load_verilogeval(results_dir: Path, golden_dir: Path, only):
    config_name = results_dir.name
    if config_name.startswith(".build_sample_"):
        config_name = config_name[len(".build_sample_"):]
    samples_dir = results_dir / "samples"
    for prob_dir in sorted(samples_dir.iterdir()):
        if not prob_dir.is_dir():
            continue
        prob_id = prob_dir.name
        if only and prob_id not in only:
            continue
        sample_json = prob_dir / "sample_01.json"
        if not sample_json.exists():
            print(f"WARN: khong thay {sample_json}", file=sys.stderr)
            continue
        try:
            data = json.loads(sample_json.read_text())
        except Exception as e:
            print(f"WARN: khong doc duoc {sample_json}: {e}", file=sys.stderr)
            continue
        gen_code = data.get("gvd")
        functional_status = data.get("final_status", "unknown")
        ref_path = golden_dir / f"{prob_id}_ref.sv"
        yield {
            "module_name": prob_id,
            "description_type": config_name,
            "run_source": str(sample_json),
            "functional_status": functional_status,
            "gen_code": gen_code,
            "ref_path": ref_path,
        }


LOADERS = {
    "rtllm": lambda args: load_rtllm(
        args.results_dir, args.golden_dir or args.results_dir,
        args.description_type, args.only),
    "rtllm_v2": lambda args: load_rtllm(
        args.results_dir, args.golden_dir or args.results_dir,
        args.description_type, args.only),
    "verilogeval": lambda args: load_verilogeval(
        args.results_dir,
        args.golden_dir or Path("ext/verilog-eval/dataset_code-complete-iccad2023"),
        args.only),
}

DEFAULT_GOLDEN = {
    "verilogeval": "ext/verilog-eval/dataset_code-complete-iccad2023",
}


def build_row(benchmark: str, rec: dict, yosys_bin: str, timeout: int, tmp_root: str, keep_tmp: bool):
    row = {f: "" for f in CSV_FIELDS}
    row["benchmark"] = benchmark
    row["module_name"] = rec["module_name"]
    row["description_type"] = rec["description_type"]
    row["run_source"] = rec["run_source"]
    row["functional_status"] = rec["functional_status"]

    exclusion_reasons = []
    if rec["functional_status"] != "pass":
        exclusion_reasons.append(f"functional_status={rec['functional_status']}")

    gen_code = rec["gen_code"]
    if not gen_code:
        row["gen_synth_status"] = "no_code"
        exclusion_reasons.append("gen_synth_status=no_code")
    else:
        gen = synth_one(yosys_bin, gen_code, timeout, tmp_root, keep_tmp, f"gen_{rec['module_name']}")
        row["gen_synth_status"] = gen["status"]
        row["gen_total_cells"] = gen["total_cells"]
        row["gen_pyranet_bucket"] = pyranet_bucket(gen["total_cells"])
        row["gen_total_wires"] = gen["total_wires"]
        row["gen_num_cell_types"] = gen["num_cell_types"]
        row["gen_num_ff"] = gen["num_ff"]
        row["gen_num_latch"] = gen["num_latch"]
        row["gen_num_memories"] = gen["num_memories"]
        row["gen_num_memory_bits"] = gen["num_memory_bits"]
        row["gen_cells_by_type"] = json.dumps(gen["cells_by_type"], sort_keys=True)
        if gen["status"] != "ok":
            exclusion_reasons.append(f"gen_synth_status={gen['status']}")

    ref_path = rec["ref_path"]
    if not ref_path.exists():
        row["ref_synth_status"] = "ref_file_missing"
        exclusion_reasons.append("ref_synth_status=ref_file_missing")
    else:
        ref_code = ref_path.read_text()
        ref = synth_one(yosys_bin, ref_code, timeout, tmp_root, keep_tmp, f"ref_{rec['module_name']}")
        row["ref_synth_status"] = ref["status"]
        row["ref_total_cells"] = ref["total_cells"]
        row["ref_pyranet_bucket"] = pyranet_bucket(ref["total_cells"])
        row["ref_total_wires"] = ref["total_wires"]
        row["ref_num_cell_types"] = ref["num_cell_types"]
        row["ref_num_ff"] = ref["num_ff"]
        row["ref_num_latch"] = ref["num_latch"]
        row["ref_num_memories"] = ref["num_memories"]
        row["ref_num_memory_bits"] = ref["num_memory_bits"]
        row["ref_cells_by_type"] = json.dumps(ref["cells_by_type"], sort_keys=True)
        if ref["status"] != "ok":
            exclusion_reasons.append(f"ref_synth_status={ref['status']}")

    comparable = not exclusion_reasons
    if comparable:
        gen_cells = row["gen_total_cells"]
        ref_cells = row["ref_total_cells"]
        if ref_cells:
            row["cell_ratio"] = round(gen_cells / ref_cells, 4)
        else:
            comparable = False
            exclusion_reasons.append("ref_total_cells=0")
        ref_ff = row.get("ref_num_ff")
        if comparable and ref_ff:
            row["ff_ratio"] = round(row["gen_num_ff"] / ref_ff, 4)

    row["comparable"] = "yes" if comparable else "no"
    row["exclusion_reason"] = "; ".join(exclusion_reasons)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--benchmark", required=True, choices=["rtllm", "rtllm_v2", "verilogeval"])
    ap.add_argument("--results-dir", required=True, type=Path,
                     help="RTLLM/RTLLM_v2: thu muc modules/ (live hoac archived snapshot). "
                          "VerilogEval: thu muc .build_sample_<config>/")
    ap.add_argument("--golden-dir", type=Path, default=None,
                     help="Mac dinh: RTLLM/RTLLM_v2 dung chinh --results-dir; "
                          "VerilogEval dung ext/verilog-eval/dataset_code-complete-iccad2023")
    ap.add_argument("--description-type", default=None,
                     help="RTLLM co the co nhieu report_langgraph.<type>.json moi module "
                          "(RTLLM.txt/txt/xml). Mac dinh: xu ly tat ca.")
    ap.add_argument("--only", default=None,
                     help="Danh sach ten module/ProbID, cach nhau boi dau phay, de chi chay mot vai module.")
    ap.add_argument("--yosys-bin", default=YOSYS_BIN_DEFAULT)
    ap.add_argument("--timeout", type=int, default=TIMEOUT_DEFAULT)
    ap.add_argument("--tmp-root", default=None, help="Thu muc chua cac tempdir tong hop (mac dinh: TMPDIR he thong)")
    ap.add_argument("--keep-tmp", action="store_true", help="Giu lai tempdir tong hop de kiem tra thu cong")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args()

    if not Path(args.yosys_bin).exists():
        print(f"ERROR: khong thay yosys binary tai {args.yosys_bin}", file=sys.stderr)
        sys.exit(1)

    only = set(args.only.split(",")) if args.only else None
    records = list(LOADERS[args.benchmark](args))
    if not records:
        print("WARN: khong tim thay module/report nao khop dieu kien.", file=sys.stderr)

    mode = "a" if args.append and args.out.exists() else "w"
    write_header = mode == "w"
    with open(args.out, mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for i, rec in enumerate(records, 1):
            print(f"[{i}/{len(records)}] {args.benchmark}:{rec['module_name']} "
                  f"({rec['description_type']}, functional={rec['functional_status']}) ...",
                  file=sys.stderr)
            row = build_row(args.benchmark, rec, args.yosys_bin, args.timeout, args.tmp_root, args.keep_tmp)
            writer.writerow(row)
            f.flush()

    print(f"Da ghi {len(records)} dong vao {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

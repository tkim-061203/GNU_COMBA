#!/usr/bin/env python3
"""dac27_leakcheck.py - which benchmark reference solutions appear near-verbatim
in the fine-tuning corpus (PyraNet-Verilog), written as leaked.json for
dac27_analyze.py --leaked-json.

Scope: the WHOLE corpus, not the training subset. The index snapshot that
trained the served checkpoint (2026-06-19) no longer exists on the server -
src/TrainDataset/train_index2_6-10.npy was overwritten on 2026-08-31 - and the
training rows are a subset of the corpus, so a corpus-level hit is a
conservative superset of what the model can have seen. For reference, each hit
also says whether its corpus row is in the CURRENT union of train_index2_*.npy.

Match rule (as the 2026-07-20 audit): comments stripped, whitespace collapsed,
code cut into word/symbol tokens. A reference of at least --min-tokens tokens is leaked if some corpus row
  - IS it (whole normalised row == normalised reference; an exact file copy), or
  - covers >= --min-containment of its 8-token shingles.
Short references are excluded: VerilogEval comes from HDLBits, whose short
solutions (e.g. a 13-token `assign zero = 0`) sit verbatim in many GitHub
repos, so a copy says nothing about memorisation. --broad-out additionally
counts every exact file copy regardless of length (sensitivity check).
The top-module name is masked, so RefModule/TopModule/verified_x do not matter.

  python src/dac27_leakcheck.py --out leaked.json --report reports/dac27_results/leakcheck.json --jobs 32
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = glob.glob(os.path.expanduser(
    "~/.cache/huggingface/hub/datasets--bnadimi--PyraNet-Verilog/snapshots/*/PyraNetOnVeriBest.csv"))
K = 8
TOK = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*|\d+'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ_?]+|\d+|\S")


def normalise(code: str) -> list[str]:
    code = re.sub(r"//[^\n]*", " ", code)
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
    toks = TOK.findall(code)
    # mask the name right after `module`, so reference/top naming does not matter
    return ["MODNAME" if i and toks[i - 1] == "module" else t for i, t in enumerate(toks)]


def shingles(toks: list[str]) -> set[int]:
    return {zlib.crc32(" ".join(toks[i:i + K]).encode()) for i in range(max(0, len(toks) - K + 1))}


def references() -> dict[tuple[str, str], str]:
    refs = {}
    for suite, root in (("rl1", ROOT / "RTLLM" / "modules"), ("rl2", ROOT / "RTLLM_v2" / "modules")):
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            files = sorted(d.glob("verified_*.v"))
            if files:
                refs[(suite, d.name)] = "\n".join(f.read_text(errors="ignore") for f in files)
    for f in sorted((ROOT / "ext" / "verilog-eval" / "dataset_code-complete-iccad2023").glob("*_ref.sv")):
        refs[("ve", f.name[: -len("_ref.sv")])] = f.read_text(errors="ignore")
    return refs


_REF = {}


def _init(ref_data):
    _REF.update(ref_data)


def scan(chunk: list[tuple[int, str]]) -> dict:
    """best (containment, row, exact) per reference within a chunk of corpus rows."""
    index, ref_sets, ref_text = _REF["index"], _REF["sets"], _REF["text"]
    best = {}
    for row, code in chunk:
        toks = normalise(code)
        if len(toks) < K:
            continue
        hits = {}
        for h in shingles(toks):
            for r in index.get(h, ()):
                hits[r] = hits.get(r, 0) + 1
        if not hits:
            continue
        joined = None
        for r, n in hits.items():
            c = n / len(ref_sets[r])
            if c < 0.5:
                continue
            if joined is None:
                joined = " ".join(toks)
            exact = joined == ref_text[r]   # whole-file copy; substring would match short textbook code
            if r not in best or (exact, c) > (best[r][2], best[r][0]):
                best[r] = (c, row, exact)
    return best


def corpus_chunks(path: str, size: int):
    csv.field_size_limit(sys.maxsize)
    with open(path, newline="", errors="ignore") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        ci = header.index("code")
        buf = []
        for row, rec in enumerate(rd):
            if ci < len(rec):
                buf.append((row, rec[ci]))
            if len(buf) >= size:
                yield buf
                buf = []
        if buf:
            yield buf


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "leaked.json"))
    ap.add_argument("--broad-out", default=str(ROOT / "leaked_broad.json"))
    ap.add_argument("--report", default=str(ROOT / "reports" / "dac27_results" / "leakcheck.json"))
    ap.add_argument("--min-containment", type=float, default=0.9)
    ap.add_argument("--min-tokens", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--corpus", default=CORPUS[0] if CORPUS else None)
    a = ap.parse_args()
    if not a.corpus:
        sys.exit("PyraNet corpus csv not found")

    refs = references()
    keys = sorted(refs)
    toks = {k: normalise(refs[k]) for k in keys}
    sets = {i: shingles(toks[k]) for i, k in enumerate(keys) if len(toks[k]) >= K}
    index = {}
    for i, s in sets.items():
        for h in s:
            index.setdefault(h, []).append(i)
    text = {i: " ".join(toks[k]) for i, k in enumerate(keys)}
    print(f"{len(keys)} references ({sum(1 for k in keys if k[0]=='rl1')} rl1, "
          f"{sum(1 for k in keys if k[0]=='rl2')} rl2, {sum(1 for k in keys if k[0]=='ve')} ve), corpus {a.corpus}")

    best = {}
    with Pool(a.jobs, initializer=_init, initargs=({"index": index, "sets": sets, "text": text},)) as pool:
        for n, part in enumerate(pool.imap_unordered(scan, corpus_chunks(a.corpus, 2000)), 1):
            for r, v in part.items():
                if r not in best or (v[2], v[0]) > (best[r][2], best[r][0]):
                    best[r] = v
            if n % 50 == 0:
                print(f"  {n * 2000} rows scanned", flush=True)

    try:
        import numpy as np
        train = set()
        for f in glob.glob(str(ROOT / "src" / "TrainDataset" / "train_index2_*.npy")):
            train |= set(np.load(f).tolist())
    except Exception:
        train = set()

    leaked = {"rl1": [], "rl2": [], "ve": []}
    broad = {"rl1": [], "rl2": [], "ve": []}
    rows = []
    for i, (suite, task) in enumerate(keys):
        c, row, exact = best.get(i, (0.0, None, False))
        ntok = len(toks[(suite, task)])
        hit = ntok >= a.min_tokens and (exact or c >= a.min_containment)
        if hit:
            leaked[suite].append(task)
        if hit or exact:
            broad[suite].append(task)
        rows.append({"suite": suite, "task": task, "ref_tokens": ntok, "best_containment": round(c, 4),
                     "exact": exact, "corpus_row": row, "row_in_current_train_union": row in train if row is not None else None,
                     "leaked": hit, "leaked_broad": hit or exact})
    Path(a.out).write_text(json.dumps(leaked, indent=2))
    Path(a.broad_out).write_text(json.dumps(broad, indent=2))
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text(json.dumps({
        "corpus": a.corpus, "rule": {"k": K, "min_containment": a.min_containment, "min_tokens": a.min_tokens,
                                     "exact_always_counts": True},
        "scope": "whole corpus (training snapshot of the served checkpoint no longer on disk)",
        "counts": {s: len(v) for s, v in leaked.items()},
        "counts_broad": {s: len(v) for s, v in broad.items()},
        "per_reference": rows}, indent=2))
    in_train = sum(1 for r in rows if r["leaked"] and r["row_in_current_train_union"])
    print(f"leaked: {{'rl1': {len(leaked['rl1'])}, 'rl2': {len(leaked['rl2'])}, 've': {len(leaked['ve'])}}} "
          f"({in_train} of them in the current train_index2 union) -> {a.out}; "
          f"broad {{'rl1': {len(broad['rl1'])}, 'rl2': {len(broad['rl2'])}, 've': {len(broad['ve'])}}} -> {a.broad_out}")


if __name__ == "__main__":
    main()

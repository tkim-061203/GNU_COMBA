#!/usr/bin/env python3
"""make_retrain_data.py - index files for the two Generator retrains (review R3-2, R3-1).

clean   the original curriculum buckets that still exist unchanged
        (train_index2_0-5 / 11-15 / 16-35; the original 6-10 snapshot was
        overwritten on 2026-08-31 and is dropped, user decision 2026-10-05),
        minus every PyraNet row that matches a benchmark reference
        (reports/dac27_results/leak_rows.json, 733 rows, any length).
        VE_text_156.jsonl is NOT used.
random  same three stage sizes, rows drawn uniformly without replacement from
        the PyraNet rows below 434,151 (above it the `code` column is a
        Python list-repr from a dataset ETL bug, not Verilog), minus the same
        leak rows. No synthesis / cell-count filter: this is the R3-1 control.

Row numbers index Pyranet_text_only.jsonl (one line per PyraNet row, same order
as PyraNetOnVeriBest.csv; checked on 26 rows incl. leak rows).

  python training/make_retrain_data.py      # -> training/data/{clean,random}_s{1,2,3}.npy + manifest.json
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "data"
STAGES = [("s1", "0-5"), ("s2", "11-15"), ("s3", "16-35")]
CORRUPT_FROM = 434_151
SEED = 3407


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    leak = {int(k) for k in json.loads((ROOT / "reports/dac27_results/leak_rows.json").read_text())["matches"]}
    man = {"leak_rows": len(leak), "seed": SEED, "clean": {}, "random": {}}

    clean = {}
    for st, b in STAGES:
        src = np.load(ROOT / f"src/TrainDataset/train_index2_{b}.npy")
        keep = np.array([i for i in src.tolist() if i not in leak], dtype=np.int64)
        clean[st] = keep
        np.save(OUT / f"clean_{st}.npy", keep)
        man["clean"][st] = {"bucket": b, "source_rows": int(len(src)), "dropped_leak": int(len(src) - len(keep)),
                            "rows": int(len(keep))}
    union = set().union(*[set(v.tolist()) for v in clean.values()])
    assert len(union) == sum(len(v) for v in clean.values()), "clean stages overlap"

    rng = np.random.default_rng(SEED)
    pool = np.array([i for i in range(CORRUPT_FROM) if i not in leak], dtype=np.int64)
    total = sum(len(v) for v in clean.values())
    draw = rng.choice(pool, size=total, replace=False)
    pos = 0
    for st, _ in STAGES:
        n = len(clean[st])
        part = np.sort(draw[pos:pos + n]); pos += n
        np.save(OUT / f"random_{st}.npy", part)
        man["random"][st] = {"rows": int(n), "overlap_with_clean_union": int(len(set(part.tolist()) & union))}
    man["clean_total"] = man["random_total"] = int(total)
    (OUT / "manifest.json").write_text(json.dumps(man, indent=2))
    print(json.dumps(man, indent=2))


if __name__ == "__main__":
    main()

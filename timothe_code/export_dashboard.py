"""Merge the official dataset_2 votes with the raw LLM answers, for the dashboard.

Output: dataset/data/dashboard/llm_dataset2.json

Pure merge, no other transformation:
  - each official datapoint from dataset_2/data/datapoints.jsonl is kept exactly as it is;
  - each row of the raw answers is attached, unchanged, to the datapoint with the same id,
    under "reponses_llm", in file order.

Raw answers: by default the raw.jsonl of the latest run in results/results-<datetime>/
(written by vote_pipeline.py); otherwise the snapshot dataset/data/llm_source/raw.jsonl.
Use --raw PATH to choose another file.

Usage, from the repository root:
    python3 timothe_code/export_dashboard.py [--raw PATH]
"""

import argparse
import glob
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OFFICIAL = os.path.join(ROOT, "dataset_2", "data", "datapoints.jsonl")
SNAPSHOT = os.path.join(ROOT, "dataset", "data", "llm_source", "raw.jsonl")
OUT = os.path.join(ROOT, "dataset", "data", "dashboard", "llm_dataset2.json")


def latest_run_raw():
    runs = sorted(glob.glob(os.path.join(ROOT, "results", "results-*", "raw.jsonl")))
    return runs[-1] if runs else None


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raw", help="raw answers file (default: latest run, else the snapshot)")
    args = ap.parse_args(argv)
    raw_path = args.raw or latest_run_raw() or SNAPSHOT

    official = read_jsonl(OFFICIAL)
    raw = read_jsonl(raw_path)

    answers = {}
    for row in raw:  # unchanged rows, grouped by bill id, in file order
        answers.setdefault(row["id"], []).append(row)

    scrutins = []
    for dp in official:
        merged = dict(dp)
        merged["reponses_llm"] = answers.get(dp["id"], [])
        scrutins.append(merged)

    out = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "officiel": "dataset_2/data/datapoints.jsonl",
            "reponses": os.path.relpath(raw_path, ROOT),
        },
        "scrutins": scrutins,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    matched = sum(1 for s in scrutins if s["reponses_llm"])
    print("written %s from %s: %d bills, %d with raw answers, %d raw rows merged"
          % (OUT, os.path.relpath(raw_path, ROOT), len(scrutins), matched, sum(len(s["reponses_llm"]) for s in scrutins)))


if __name__ == "__main__":
    main()

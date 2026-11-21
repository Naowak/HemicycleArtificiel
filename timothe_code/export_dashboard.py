"""Merge the official dataset_2 votes with the raw LLM answers, for the dashboard.

Output: dataset/data/dashboard/llm_dataset2.json

Pure merge, no other transformation:
  - each official datapoint from dataset_2/data/datapoints.jsonl is kept exactly as it is;
  - each raw answer row is attached, unchanged, to the datapoint with the same id,
    under "reponses_llm", in file order.

Raw answers come from every run folder results/results-<datetime>/raw.jsonl (oldest first, as
written by vote_pipeline.py), plus the snapshot dataset/data/llm_source/raw.jsonl of the first run.
A run that reuses an earlier answer repeats that row, so rows are kept once per
(model, variant, bill, sample): a successful answer replaces a failed one, otherwise the later run wins.

Usage, from the repository root:
    python3 timothe_code/export_dashboard.py
"""

import glob
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OFFICIAL = os.path.join(ROOT, "dataset_2", "data", "datapoints.jsonl")
SNAPSHOT = os.path.join(ROOT, "dataset", "data", "llm_source", "raw.jsonl")
OUT = os.path.join(ROOT, "dataset", "data", "dashboard", "llm_dataset2.json")


def raw_sources():
    """Snapshot first, then every run folder, oldest first (run names sort by date)."""
    runs = sorted(glob.glob(os.path.join(ROOT, "results", "results-*", "raw.jsonl")))
    return ([SNAPSHOT] if os.path.exists(SNAPSHOT) else []) + runs


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def merge_answers(paths):
    """One row per (model, variant, bill, sample), in first-seen order."""
    chosen = {}
    for path in paths:
        for row in read_jsonl(path):
            key = (row["model"], row["variant"], row["id"], row.get("sample", 0))
            old = chosen.get(key)
            if old is None or row.get("text") is not None or old.get("text") is None:
                chosen[key] = row
    return list(chosen.values())


def main():
    sources = raw_sources()
    official = read_jsonl(OFFICIAL)
    raw = merge_answers(sources)

    answers = {}
    for row in raw:
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
            "reponses": [os.path.relpath(p, ROOT) for p in sources],
        },
        "scrutins": scrutins,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    matched = sum(1 for s in scrutins if s["reponses_llm"])
    print("written %s from %d source(s): %d bills, %d with raw answers, %d answer rows"
          % (os.path.relpath(OUT, ROOT), len(sources), len(scrutins), matched, len(raw)))


if __name__ == "__main__":
    main()

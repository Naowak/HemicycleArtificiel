import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import visualize_results as viz  # noqa: E402
import vote_pipeline as vp  # noqa: E402


def make_run(root, name, records, ids):
    path = os.path.join(root, name)
    os.makedirs(path)
    config = {"created": "x", "models": ["m"], "variants": ["neutre"], "n_samples": 1, "datapoints": ids, "prompts": {}}
    with open(os.path.join(path, vp.CONFIG_FILE), "w", encoding="utf-8") as f:
        json.dump(config, f)
    with open(os.path.join(path, vp.RAW_FILE), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(path, vp.PROMPTS_LOG), "w", encoding="utf-8") as f:
        f.write(json.dumps({"hash": "abc123", "variant": "neutre", "id": ids[0], "messages": [{"role": "user", "content": "P"}]}) + "\n")
    return path


def record(dp_id, label, cost=0.01, **extra):
    return dict({"model": "m", "variant": "neutre", "id": dp_id, "sample": 0, "prompt_hash": "abc123",
                 "settings": {"temperature": 0.0}, "text": "VOTE : POUR", "label": label, "usage": {"cost": cost}}, **extra)


def test_run_dir_naming_and_listing(tmp_path):
    path = vp.new_run_dir("_smoke", str(tmp_path), time.strptime("2026-11-21 10:05:00", "%Y-%m-%d %H:%M:%S"))
    os.makedirs(os.path.join(str(tmp_path), "other"))
    assert os.path.basename(path) == "results-2026-11-21_10-05-00_smoke"
    assert vp.list_runs(str(tmp_path)) == ["results-2026-11-21_10-05-00_smoke"]


def test_runs_are_ordered_by_date_even_with_a_label_before_it(tmp_path):
    names = ["results-5-seed-bench-2026-11-21_21-03-00", "results-2026-11-22_09-00-00", "results-2026-11-21_08-00-00_smoke"]
    for name in names:
        os.makedirs(os.path.join(str(tmp_path), name))
    assert vp.list_runs(str(tmp_path)) == [names[2], names[0], names[1]]


def test_earlier_answers_are_reusable_only_with_same_prompt_and_settings(tmp_path):
    ids = [vp.ds.load()[0]["id"]]
    make_run(str(tmp_path), "results-a", [record(ids[0], "for"), record(ids[0], None, text=None)], ids)
    current = os.path.join(str(tmp_path), "results-b")
    os.makedirs(current)
    earlier = vp.earlier_answers(current, str(tmp_path))
    assert list(earlier) == [vp.reuse_key("m", "abc123", 0, {"temperature": 0.0})]
    assert vp.reuse_key("m", "abc123", 0, {"temperature": 1.0}) not in earlier


def test_viewer_payloads(tmp_path):
    ids = [dp["id"] for dp in vp.ds.load()[:2]]
    make_run(str(tmp_path), "results-a", [record(ids[0], "for"), record(ids[1], "against", reused_from="results-0")], ids)
    runs = viz.runs_payload(str(tmp_path))
    assert runs[0]["name"] == "results-a" and runs[0]["n_answers"] == 2 and runs[0]["n_reused"] == 1
    assert abs(runs[0]["cost"] - 0.01) < 1e-9
    run = viz.run_payload("results-a", str(tmp_path))
    assert len(run["answers"]) == 2 and set(run["bills"]) == set(ids) and run["n_errors"] == 0
    assert viz.prompt_payload("results-a", "abc123", str(tmp_path))["messages"][0]["content"] == "P"
    assert viz.prompt_payload("results-a", "ffffff", str(tmp_path)) is None

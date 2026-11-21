"""Minimal pipeline: LLMs vote on the bills of dataset_2, then are compared with the groups.

Usage, from the repository root:
    python timothe_code/vote_pipeline.py smoke    # 2 datapoints x all models x all variants, prints raw answers
    python timothe_code/vote_pipeline.py run      # all selected datapoints (cached, resumable, budget-capped)
    python timothe_code/vote_pipeline.py report   # rates and agreement with groups -> results/report.md

Every API answer is appended to results/raw.jsonl; a call already in the file is
never repeated. Spending stops at BUDGET_USD, counted from OpenRouter's reported
cost of each call.
"""

import argparse
import collections
import concurrent.futures
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import usage_dataset2 as ds  # noqa: E402

logger = logging.getLogger(__name__)

RESULTS_DIR = os.path.join(HERE, "results")
RAW_FILE = os.path.join(RESULTS_DIR, "raw.jsonl")
REPORT_FILE = os.path.join(RESULTS_DIR, "report.md")
PROMPTS_FILE = os.path.join(HERE, "prompts.json")
API_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    "anthropic/claude-haiku-5.5",
    "openai/gpt-6-luna",
    "google/gemini-3.5-flash-lite",
    "mistralai/mistral-small-2603",
    "deepseek/deepseek-v4.1-flash",
    "qwen/qwen3.8-flash",
    "meta-llama/llama-4-scout",
]
# Models whose reasoning cannot be disabled: low effort, and room for the hidden reasoning tokens.
REASONING_REQUIRED = {"google/gemini-3.5-flash-lite": {"effort": "low"}}
MAX_TOKENS_WITH_REASONING = 2000
BUDGET_USD = 1.60
MAX_TEXT_CHARS = 30000
SMOKE_DATAPOINTS = 2
TEMPERATURE = 0.0
MAX_TOKENS = 200
N_SAMPLES = 1
N_WORKERS = 8
TIMEOUT_S = 180
RETRIES = 4
MIN_GROUP_VOTERS = 3
EXCLUDED_GROUPS = ("NI",)
N_EXAMPLES = 2

VOTE_RE = re.compile(r"VOTE\W{0,6}(POUR|CONTRE|ABSTENTION)", re.I)
FIRST_WORD_RE = re.compile(r"^\W*(POUR|CONTRE|ABSTENTION)\b", re.I)
LABELS = {"POUR": "for", "CONTRE": "against", "ABSTENTION": "abstain"}


def parse_vote(text):
    """'for' / 'against' / 'abstain', or None when the answer contains no vote."""
    if not text:
        return None
    m = VOTE_RE.search(text) or FIRST_WORD_RE.search(text)
    return LABELS[m.group(1).upper()] if m else None


def select_datapoints():
    return [dp for dp in ds.divisive(ds.load()) if dp["text_content"]["voted_text_chars"] <= MAX_TEXT_CHARS]


def build_messages(dp, variant, prompts):
    v = prompts["variants"][variant]
    t = dp["text_content"]
    title = t["title"][:1].upper() + t["title"][1:]
    user = prompts["template"].format(title=title, voted_text=t["voted_text"], question=v["question"])
    messages = [{"role": "system", "content": v["system"]}] if v["system"] else []
    return messages + [{"role": "user", "content": user}]


def call(model, messages):
    """(answer text, usage dict, error string) for one chat completion."""
    reasoning = REASONING_REQUIRED.get(model, {"enabled": False})
    max_tokens = MAX_TOKENS_WITH_REASONING if model in REASONING_REQUIRED else MAX_TOKENS
    body = json.dumps({"model": model, "messages": messages, "temperature": TEMPERATURE, "max_tokens": max_tokens,
                       "reasoning": reasoning, "usage": {"include": True}}).encode()
    headers = {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json"}
    error = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(API_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                out = json.load(r)
            if "error" in out:
                error = json.dumps(out["error"])[:300]
            else:
                text = (out["choices"][0]["message"].get("content") or "").strip()
                return text, out.get("usage") or {}, None
        except urllib.error.HTTPError as e:
            error = "HTTP %s %s" % (e.code, e.read()[:300].decode(errors="replace"))
            if e.code < 500 and e.code != 429:
                break
        except Exception as e:  # network errors, timeouts
            error = repr(e)[:300]
        time.sleep(2 ** attempt)
    return None, {}, error


def load_raw():
    if not os.path.exists(RAW_FILE):
        return []
    with open(RAW_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def run(datapoints, models, variants, n_samples):
    with open(PROMPTS_FILE, encoding="utf-8") as f:
        prompts = json.load(f)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    done = load_raw()
    spent = sum((r["usage"].get("cost") or 0) for r in done)
    seen = {(r["model"], r["variant"], r["id"], r["sample"]) for r in done if r["text"] is not None}
    tasks = [(m, v, dp, k) for v in variants for m in models for dp in datapoints for k in range(n_samples)
             if (m, v, dp["id"], k) not in seen]
    logger.info("%d calls to make; already spent $%.4f of $%.2f", len(tasks), spent, BUDGET_USD)
    lock = threading.Lock()
    state = {"spent": spent, "n": 0}

    def work(task):
        model, variant, dp, sample = task
        with lock:
            if state["spent"] >= BUDGET_USD:
                return None
        text, usage, error = call(model, build_messages(dp, variant, prompts))
        rec = {"model": model, "variant": variant, "id": dp["id"], "sample": sample, "text": text,
               "label": parse_vote(text), "usage": usage, "error": error, "time": time.strftime("%H:%M:%S")}
        with lock:
            state["spent"] += usage.get("cost") or 0
            state["n"] += 1
            with open(RAW_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if state["n"] % 50 == 0:
                logger.info("%d / %d calls, $%.4f spent", state["n"], len(tasks), state["spent"])
        return rec

    with concurrent.futures.ThreadPoolExecutor(N_WORKERS) as pool:
        records = [r for r in pool.map(work, tasks) if r]
    logger.info("done: %d calls, $%.4f spent in total", len(records), state["spent"])
    return records


def summarize(records, datapoints):
    """One row per (model, variant): answer rates, agreement and correlation with each group."""
    groups = ds.position_table(datapoints, MIN_GROUP_VOTERS, EXCLUDED_GROUPS)
    by_key = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in records:
        by_key[(r["model"], r["variant"])][r["id"]].append(r["label"])
    rows = []
    for (model, variant), answers in sorted(by_key.items()):
        labels = [a for ans in answers.values() for a in ans]
        n = len(labels)
        positions = {i: ds.model_position(a) for i, a in answers.items()}
        agree = {g: ds.agreement(positions, p) for g, p in groups.items()}
        corr = {g: ds.correlation(positions, p) for g, p in groups.items()}
        rows.append({"model": model, "variant": variant, "n": n,
                     "refusal": labels.count(None) / n, "abstain": labels.count("abstain") / n,
                     "for": labels.count("for") / n, "against": labels.count("against") / n,
                     "agreement": agree, "correlation": corr})
    baseline = {g: ds.agreement(ds.constant_positions(1.0, datapoints), p) for g, p in groups.items()}
    return rows, baseline, sorted(groups)


def write_report(records, datapoints):
    rows, baseline, groups = summarize(records, datapoints)
    cost = sum((r["usage"].get("cost") or 0) for r in records)
    lines = ["# LLM votes on dataset_2: minimal run", "",
             "%d datapoints (divisive, voted text <= %d characters), %d calls, $%.3f spent. "
             "Temperature %s, %d sample(s) per datapoint. Group positions need >= %d voters; NI excluded."
             % (len(datapoints), MAX_TEXT_CHARS, len(records), cost, TEMPERATURE, N_SAMPLES, MIN_GROUP_VOTERS), "",
             "## Answer rates", "", "| model | variant | n | refusal | abstain | for | against |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %d | %.0f %% | %.0f %% | %.0f %% | %.0f %% |"
                     % (r["model"], r["variant"], r["n"], 100 * r["refusal"], 100 * r["abstain"], 100 * r["for"], 100 * r["against"]))
    for metric in ("agreement", "correlation"):
        lines += ["", "## %s with each group" % metric.capitalize(), "",
                  "| model | variant | " + " | ".join(groups) + " | closest |", "|---|---|" + "---|" * (len(groups) + 1)]
        if metric == "agreement":
            lines.append("| always for | (reference) | " + " | ".join("%.2f" % baseline[g] for g in groups) + " | |")
        for r in rows:
            vals = r[metric]
            known = {g: v for g, v in vals.items() if v is not None}
            closest = max(known, key=known.get) if known else "-"
            lines.append("| %s | %s | " % (r["model"], r["variant"])
                         + " | ".join("%.2f" % vals[g] if vals[g] is not None else "-" for g in groups) + " | %s |" % closest)
    lines += ["", "## Examples of refusals and abstentions", ""]
    examples = collections.defaultdict(list)
    for r in records:
        if r["label"] in (None, "abstain") and len(examples[(r["model"], r["label"])]) < N_EXAMPLES:
            examples[(r["model"], r["label"])].append(r)
    for (model, label), recs in sorted(examples.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        for r in recs:
            text = (r["text"] or r["error"] or "").replace("\n", " ")[:300]
            lines.append("- **%s**, %s, %s, `%s`: %s" % (model, r["variant"], label or "refusal", r["id"], text))
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("report written to %s", REPORT_FILE)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=["smoke", "run", "report"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with open(PROMPTS_FILE, encoding="utf-8") as f:
        variants = list(json.load(f)["variants"])
    datapoints = select_datapoints()
    if args.step == "smoke":
        sample = sorted(datapoints, key=lambda dp: dp["text_content"]["voted_text_chars"])[:SMOKE_DATAPOINTS]
        for r in sorted(run(sample, MODELS, variants, 1), key=lambda r: (r["model"], r["variant"])):
            u = r["usage"]
            print("%-30s %-10s %-7s in=%s out=%s reason=%s $%.5f | %s" % (
                r["model"], r["variant"], r["label"], u.get("prompt_tokens"), u.get("completion_tokens"),
                (u.get("completion_tokens_details") or {}).get("reasoning_tokens"), u.get("cost") or 0,
                (r["text"] or r["error"] or "").replace("\n", " ")[:160]))
    elif args.step == "run":
        run(datapoints, MODELS, variants, N_SAMPLES)
    else:
        ids = {dp["id"] for dp in datapoints}
        write_report([r for r in load_raw() if r["id"] in ids and r["text"] is not None], datapoints)


if __name__ == "__main__":
    main()

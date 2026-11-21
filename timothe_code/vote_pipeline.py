"""Minimal pipeline: LLMs vote on the bills of dataset_2, then are compared with the groups.

Usage, from the repository root:
    python timothe_code/vote_pipeline.py preview  # print the exact prompts, no API call
    python timothe_code/vote_pipeline.py smoke    # 2 datapoints x all models x enabled variants, prints raw answers
    python timothe_code/vote_pipeline.py run      # a new run in results/results-<datetime>/
    python timothe_code/vote_pipeline.py report   # rewrite report.md of the latest run (or --run <name>)
Options: --variants a,b  --models m1,m2  --ids 19,40,...  --limit N  --legislature L  --divisive-only
         --max-chars N  --temperature T  --samples K  --max-tokens N  --budget USD
         --datapoint <rank or id> (preview)  --resume <run name>  --fresh (never reuse earlier answers)
Defaults are the constants below; the values used are saved in each run's config.json.

Each run folder holds config.json (settings and a copy of prompts.json),
prompts.jsonl (exact messages, by hash), raw.jsonl (answers), run.log and
report.md. An answer to the same model, prompt and settings found in an earlier
run is copied instead of paid again, unless --fresh. Spending of a run stops at
BUDGET_USD, counted from OpenRouter's reported cost of each call.
"""

import argparse
import collections
import concurrent.futures
import hashlib
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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import usage_dataset2 as ds  # noqa: E402

logger = logging.getLogger(__name__)

RESULTS_ROOT = os.path.join(ROOT, "results")
RUN_PREFIX = "results-"
ENV_FILE = os.path.join(ROOT, ".env")


def api_key():
    """OPENROUTER_API_KEY from the .env file at the repository root, else from the environment."""
    if os.path.exists(ENV_FILE):
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY=") and not line.startswith("#"):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    return os.environ.get("OPENROUTER_API_KEY", "")
CONFIG_FILE, PROMPTS_LOG, RAW_FILE, REPORT_FILE, LOG_FILE = "config.json", "prompts.jsonl", "raw.jsonl", "report.md", "run.log"
PROMPTS_FILE = os.path.join(HERE, "prompts.json")
# Optional per-bill placeholders (e.g. generated arguments): {bill id: {field: text}}.
EXTRA_FIELDS_FILE = os.path.join(HERE, "extra_fields.json")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY_ENV = "OPENROUTER_API_KEY_2"  # the team's key

MODELS = [
    "openai/gpt-6-luna",
    "anthropic/claude-haiku-5.5",
    "google/gemini-3.5-flash-lite",
    "mistralai/mistral-small-2603",
    "deepseek/deepseek-v4.1-flash",
    "qwen/qwen3.8-flash",
    "moonshotai/kimi-k3.1-pro",
    "x-ai/grok-4.3",
]
# Models whose reasoning cannot be disabled: low effort, and room for the hidden reasoning tokens.
REASONING_REQUIRED = {"google/gemini-3.5-flash-lite": {"effort": "low"}}
MAX_TOKENS_WITH_REASONING = 2000
BUDGET_USD = 1.60
# Bill selection. MAX_TEXT_CHARS = None keeps every length.
MAX_TEXT_CHARS = None
DIVISIVE_ONLY = False
SMOKE_DATAPOINTS = 2
TEMPERATURE = None  # None = not sent: each provider's default temperature
MAX_TOKENS = 400
N_SAMPLES = 1
N_WORKERS = 8
TIMEOUT_S = 180
RETRIES = 6
# New OpenRouter accounts are limited to 20 requests per minute per model.
RATE_LIMIT_WAIT_S = 15
MIN_GROUP_VOTERS = 3
EXCLUDED_GROUPS = ("NI",)
N_EXAMPLES = 2

VOTE_RE = re.compile(r"VOTE\W{0,6}(POUR|CONTRE|ABSTENTION)", re.I)
CAPITALS_RE = re.compile(r"\b(POUR|CONTRE|ABSTENTION)\b")
LONE_FIRST_LINE_RE = re.compile(r"^\W*(POUR|CONTRE|ABSTENTION)\W*$", re.I | re.M)
LABELS = {"POUR": "for", "CONTRE": "against", "ABSTENTION": "abstain"}


# ---------------------------------------------------------------- prompts

def parse_vote(text):
    """'for' / 'against' / 'abstain', or None when the answer contains no vote.

    Tried in order: "VOTE : X" (any case); X in capitals anywhere, which also
    catches a vote after a preamble or a disclaimer ("mon avis : **ABSTENTION**");
    a first line made of X alone in any case. Lower-case "pour" / "contre" in
    a sentence is ordinary French and never read as a vote.
    """
    if not text:
        return None
    first_line = text.strip().split("\n", 1)[0]
    m = VOTE_RE.search(text) or CAPITALS_RE.search(text) or LONE_FIRST_LINE_RE.match(first_line)
    return LABELS[m.group(1).upper()] if m else None


def select_datapoints(legislature=None, keys=None):
    """Bills of a run: explicit ranks / ids, or the dataset filtered by legislature, DIVISIVE_ONLY and MAX_TEXT_CHARS."""
    dps = ds.load()
    if keys:
        return [ds.get(k, dps) for k in keys]
    if DIVISIVE_ONLY:
        dps = ds.divisive(dps)
    return [dp for dp in dps if (not MAX_TEXT_CHARS or dp["text_content"]["voted_text_chars"] <= MAX_TEXT_CHARS)
            and (legislature is None or dp["legislature"] == legislature)]


def author_label(author):
    if author["type"] == "government":
        return "le gouvernement"
    if author["type"] == "senator":
        return "des s\u00e9nateurs"
    return "un d\u00e9put\u00e9 du groupe %s" % author["group"] if author["group"] else "un d\u00e9put\u00e9"


class MissingField(KeyError):
    """A placeholder exists for some bills but not for this one: the bill is skipped for that variant."""


_extra_fields = None


def extra_fields():
    global _extra_fields
    if _extra_fields is None:
        _extra_fields = {}
        if os.path.exists(EXTRA_FIELDS_FILE):
            with open(EXTRA_FIELDS_FILE, encoding="utf-8") as f:
                _extra_fields = json.load(f)
    return _extra_fields


def prompt_fields(dp):
    """Values usable as {placeholders} in prompts.json; missing values become ""."""
    t = dp["text_content"]
    fields = {k: ("" if v is None else v) for k, v in t.items() if not isinstance(v, dict)}
    fields["title"] = t["title"][:1].upper() + t["title"][1:]
    a = t["author"]
    fields.update(author_type=a["type"], author_name=a["name"] or "", author_group=a["group"] or "",
                  author_label=author_label(a), date=dp["date"], theme=dp["theme"] or "", vote_title=dp["vote_title"])
    fields.update(extra_fields().get(dp.get("id"), {}))
    return fields


def build_messages(dp, variant, prompts):
    """Chat messages of one variant: its own "template" if any, else the shared one."""
    v = prompts["variants"][variant]
    fields = dict(prompt_fields(dp), question=v.get("question", ""))
    try:
        user = v.get("template", prompts["template"]).format(**fields)
        system = v["system"].format(**fields) if v.get("system") else None
    except KeyError as e:
        if any(e.args[0] in extra for extra in extra_fields().values()):
            raise MissingField(e.args[0])
        raise KeyError("unknown placeholder %s in variant %r; available: %s" % (e, variant, ", ".join(sorted(fields))))
    messages = [{"role": "system", "content": system}] if system else []
    return messages + [{"role": "user", "content": user}]


def prompt_hash(messages):
    return hashlib.sha1(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def load_prompts():
    with open(PROMPTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def enabled_variants(prompts):
    return [name for name, v in prompts["variants"].items() if v.get("enabled", True)]


# ---------------------------------------------------------------- API

def generation_settings(model):
    reasoning = REASONING_REQUIRED.get(model, {"enabled": False})
    max_tokens = MAX_TOKENS_WITH_REASONING if model in REASONING_REQUIRED else MAX_TOKENS
    settings = {"max_tokens": max_tokens, "reasoning": reasoning}
    if TEMPERATURE is not None:
        settings["temperature"] = TEMPERATURE
    return settings


def call(model, messages, settings):
    """(answer text, usage dict, error string) for one chat completion."""
    body = json.dumps(dict(settings, model=model, messages=messages, usage={"include": True})).encode()
    headers = {"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"}
    error = None
    for attempt in range(RETRIES):
        wait = 2 ** attempt
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
            if e.code == 429:
                wait = RATE_LIMIT_WAIT_S * (attempt + 1)
            elif e.code < 500:
                break
        except Exception as e:  # network errors, timeouts
            error = repr(e)[:300]
        time.sleep(wait)
    return None, {}, error


# ---------------------------------------------------------------- run folders

def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def list_runs(results_root=RESULTS_ROOT):
    """Run folder names, oldest first (names sort by date)."""
    if not os.path.isdir(results_root):
        return []
    return sorted(d for d in os.listdir(results_root)
                  if d.startswith(RUN_PREFIX) and os.path.isdir(os.path.join(results_root, d)))


def new_run_dir(suffix="", results_root=RESULTS_ROOT, now=None):
    name = RUN_PREFIX + time.strftime("%Y-%m-%d_%H-%M-%S", now or time.localtime()) + suffix
    path = os.path.join(results_root, name)
    os.makedirs(path)
    return path


def reuse_key(model, phash, sample, settings):
    return (model, phash, sample, json.dumps(settings, sort_keys=True))


def earlier_answers(current_dir, results_root=RESULTS_ROOT):
    """{reuse key: (run name, record)} over the successful answers of other runs."""
    out = {}
    for name in list_runs(results_root):
        path = os.path.join(results_root, name)
        if os.path.abspath(path) == os.path.abspath(current_dir):
            continue
        for r in read_jsonl(os.path.join(path, RAW_FILE)):
            if r.get("text") is not None and "settings" in r and not r.get("reused_from"):
                out[reuse_key(r["model"], r["prompt_hash"], r["sample"], r["settings"])] = (name, r)
    return out


def require_key():
    if not os.environ.get(API_KEY_ENV):
        sys.exit("environment variable %s is not set (choose another with --key-env)" % API_KEY_ENV)


def run(run_dir, datapoints, models, variants, n_samples, reuse=True, note=None):
    require_key()
    config_path = os.path.join(run_dir, CONFIG_FILE)
    if os.path.exists(config_path):  # resumed run: keep its own prompts and settings
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        prompts, models, variants, n_samples = config["prompts"], config["models"], config["variants"], config["n_samples"]
        datapoints = [dp for dp in ds.load() if dp["id"] in set(config["datapoints"])]
    else:
        prompts = load_prompts()
        config = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "models": models, "variants": variants,
                  "n_samples": n_samples, "settings": {m: generation_settings(m) for m in models},
                  "budget_usd": BUDGET_USD, "max_text_chars": MAX_TEXT_CHARS, "divisive_only": DIVISIVE_ONLY,
                  "datapoints": [dp["id"] for dp in datapoints], "prompts": prompts, "note": note}
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=1)
    handler = logging.FileHandler(os.path.join(run_dir, LOG_FILE), encoding="utf-8")
    logger.addHandler(handler)

    messages = {}
    for v in variants:
        for dp in datapoints:
            try:
                messages[(v, dp["id"])] = build_messages(dp, v, prompts)
            except MissingField:
                pass  # this bill has no value for a placeholder of this variant
        if not any(key[0] == v for key in messages):
            sys.exit("variant %r has no bill with all its placeholders" % v)
    hashes = {key: prompt_hash(m) for key, m in messages.items()}
    logged = {p["hash"] for p in read_jsonl(os.path.join(run_dir, PROMPTS_LOG))}
    with open(os.path.join(run_dir, PROMPTS_LOG), "a", encoding="utf-8") as f:
        for (variant, dp_id), m in messages.items():
            if hashes[(variant, dp_id)] not in logged:
                logged.add(hashes[(variant, dp_id)])
                f.write(json.dumps({"hash": hashes[(variant, dp_id)], "variant": variant, "id": dp_id, "messages": m},
                                   ensure_ascii=False) + "\n")

    done = read_jsonl(os.path.join(run_dir, RAW_FILE))
    seen = {(r["model"], r["variant"], r["id"], r["sample"]) for r in done if r["text"] is not None}
    # Samples are the outer loop: an interrupted run leaves complete passes over the bills. Models vary
    # fastest, so parallel calls spread over models (per-model rate limits).
    tasks = [(m, v, dp, k) for k in range(n_samples) for v in variants for dp in datapoints for m in models
             if (m, v, dp["id"], k) not in seen and (v, dp["id"]) in messages]
    earlier = earlier_answers(run_dir) if reuse else {}
    lock = threading.Lock()
    state = {"spent": sum((r["usage"].get("cost") or 0) for r in done if not r.get("reused_from")), "n": 0, "reused": 0}
    logger.info("%s: %d answers to get (%d earlier answers available for reuse)", os.path.basename(run_dir),
                len(tasks), len(earlier))

    def save(rec):
        with open(os.path.join(run_dir, RAW_FILE), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def work(task):
        model, variant, dp, sample = task
        phash, settings = hashes[(variant, dp["id"])], config["settings"].get(model) or generation_settings(model)
        old = earlier.get(reuse_key(model, phash, sample, settings))
        if old:
            rec = dict(old[1], variant=variant, id=dp["id"], reused_from=old[0])
            with lock:
                state["reused"] += 1
                save(rec)
            return rec
        with lock:
            if state["spent"] >= BUDGET_USD:
                return None
        text, usage, error = call(model, messages[(variant, dp["id"])], settings)
        rec = {"model": model, "variant": variant, "id": dp["id"], "sample": sample, "prompt_hash": phash,
               "settings": settings, "text": text, "label": parse_vote(text), "usage": usage, "error": error,
               "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        with lock:
            state["spent"] += usage.get("cost") or 0
            state["n"] += 1
            save(rec)
            if state["n"] % 50 == 0:
                logger.info("%d new calls, $%.4f spent", state["n"], state["spent"])
        return rec

    with concurrent.futures.ThreadPoolExecutor(N_WORKERS) as pool:
        records = [r for r in pool.map(work, tasks) if r]
    logger.info("done: %d new calls ($%.4f spent in this run), %d answers reused", state["n"], state["spent"],
                state["reused"])
    write_report(run_dir)
    logger.removeHandler(handler)
    return records


# ---------------------------------------------------------------- evaluation

def run_data(run_dir):
    """(config, successful answers, datapoints of the run)."""
    with open(os.path.join(run_dir, CONFIG_FILE), encoding="utf-8") as f:
        config = json.load(f)
    ids = set(config["datapoints"])
    records = [r for r in read_jsonl(os.path.join(run_dir, RAW_FILE)) if r["text"] is not None and r["id"] in ids]
    for r in records:  # re-read, so that parser fixes also apply to earlier runs
        r["label"] = parse_vote(r["text"])
    return config, records, [dp for dp in ds.load() if dp["id"] in ids]


def summarize(records, datapoints):
    """Per legislature: rows per (model, variant) with answer rates, agreement and correlation with each group."""
    out = {}
    for leg in sorted({dp["legislature"] for dp in datapoints}):
        dps = [dp for dp in datapoints if dp["legislature"] == leg]
        ids = {dp["id"] for dp in dps}
        groups = ds.position_table(dps, MIN_GROUP_VOTERS, EXCLUDED_GROUPS)
        by_key = collections.defaultdict(lambda: collections.defaultdict(list))
        for r in records:
            if r["id"] in ids:
                by_key[(r["model"], r["variant"])][r["id"]].append(r["label"])
        rows = []
        for (model, variant), answers in sorted(by_key.items()):
            labels = [a for ans in answers.values() for a in ans]
            n = len(labels)
            positions = {i: ds.model_position(a) for i, a in answers.items()}
            rows.append({"model": model, "variant": variant, "n": n,
                         "refusal": labels.count(None) / n, "abstain": labels.count("abstain") / n,
                         "for": labels.count("for") / n, "against": labels.count("against") / n,
                         "agreement": {g: ds.agreement(positions, p) for g, p in groups.items()},
                         "correlation": {g: ds.correlation(positions, p) for g, p in groups.items()}})
        baseline = {g: ds.agreement(ds.constant_positions(1.0, dps), p) for g, p in groups.items()}
        out[leg] = {"rows": rows, "baseline": baseline, "groups": sorted(groups), "n_datapoints": len(dps)}
    return out


def write_report(run_dir):
    config, records, datapoints = run_data(run_dir)
    cost = sum((r["usage"].get("cost") or 0) for r in records if not r.get("reused_from"))
    n_reused = sum(1 for r in records if r.get("reused_from"))
    lines = ["# %s" % os.path.basename(run_dir), "",
             "%d datapoints, %d answers (%d reused from earlier runs), $%.3f spent in this run. "
             "Models: %s. Variants: %s. %d sample(s). Group positions need >= %d voters; NI excluded."
             % (len(datapoints), len(records), n_reused, cost, ", ".join(config["models"]), ", ".join(config["variants"]),
                config["n_samples"], MIN_GROUP_VOTERS)]
    for leg, s in summarize(records, datapoints).items():
        groups = s["groups"]
        lines += ["", "## Legislature %s (%d datapoints)" % (leg, s["n_datapoints"]), "", "### Answer rates", "",
                  "| model | variant | n | refusal | abstain | for | against |", "|---|---|---|---|---|---|---|"]
        for r in s["rows"]:
            lines.append("| %s | %s | %d | %.0f %% | %.0f %% | %.0f %% | %.0f %% |" % (
                r["model"], r["variant"], r["n"], 100 * r["refusal"], 100 * r["abstain"], 100 * r["for"], 100 * r["against"]))
        for metric in ("agreement", "correlation"):
            lines += ["", "### %s with each group" % metric.capitalize(), "",
                      "| model | variant | " + " | ".join(groups) + " | closest |", "|---|---|" + "---|" * (len(groups) + 1)]
            if metric == "agreement":
                lines.append("| always for | (reference) | " + " | ".join("%.2f" % s["baseline"][g] for g in groups) + " | |")
            for r in s["rows"]:
                known = {g: v for g, v in r[metric].items() if v is not None}
                closest = max(known, key=known.get) if known else "-"
                lines.append("| %s | %s | " % (r["model"], r["variant"]) + " | ".join(
                    "%.2f" % r[metric][g] if r[metric][g] is not None else "-" for g in groups) + " | %s |" % closest)
    lines += ["", "## Examples of refusals and abstentions", ""]
    examples = collections.defaultdict(list)
    for r in records:
        if r["label"] in (None, "abstain") and len(examples[(r["model"], r["label"])]) < N_EXAMPLES:
            examples[(r["model"], r["label"])].append(r)
    for (model, label), recs in sorted(examples.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        for r in recs:
            lines.append("- **%s**, %s, %s, `%s`: %s" % (model, r["variant"], label or "refusal", r["id"],
                                                        (r["text"] or "").replace("\n", " ")[:300]))
    with open(os.path.join(run_dir, REPORT_FILE), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("report written to %s", os.path.join(run_dir, REPORT_FILE))


# ---------------------------------------------------------------- command line

def preview(prompts, datapoints, variant, key):
    dp = ds.get(key, datapoints) if key else min(datapoints, key=lambda d: d["text_content"]["voted_text_chars"])
    print("variant %r on %s (%s)\n" % (variant, dp["id"], dp["text_content"]["title"][:80]))
    for m in build_messages(dp, variant, prompts):
        print("[%s]\n%s\n" % (m["role"], m["content"]))
    print("available placeholders:", ", ".join(sorted(list(prompt_fields(dp)) + ["question"])))


def main():
    global TEMPERATURE, N_SAMPLES, MAX_TOKENS, BUDGET_USD, MAX_TEXT_CHARS, DIVISIVE_ONLY, API_KEY_ENV
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=["preview", "smoke", "run", "report"])
    parser.add_argument("--variants", help="comma-separated variants (default: all enabled ones)")
    parser.add_argument("--models", help="comma-separated models (default: MODELS)")
    parser.add_argument("--limit", type=int, help="only the first N datapoints")
    parser.add_argument("--legislature", type=int, help="only this legislature")
    parser.add_argument("--datapoint", help="preview: rank or vote id (default: the shortest text)")
    parser.add_argument("--resume", help="run: name of an interrupted run to continue")
    parser.add_argument("--run", help="report: run name (default: the latest)")
    parser.add_argument("--fresh", action="store_true", help="run: never reuse answers from earlier runs")
    parser.add_argument("--ids", help="comma-separated bill ranks or vote ids (replaces the filters)")
    parser.add_argument("--divisive-only", action="store_true", help="only bills with a minority of at least 5 %%")
    parser.add_argument("--max-chars", type=int, help="skip bills whose voted text is longer (0 = no limit)")
    parser.add_argument("--temperature", type=float, help="default: not sent, i.e. each provider's default")
    parser.add_argument("--samples", type=int, help="answers per bill and model")
    parser.add_argument("--max-tokens", type=int, help="answer length cap (models without forced reasoning)")
    parser.add_argument("--budget", type=float, help="spending cap of the run, in USD")
    parser.add_argument("--key-env", help="environment variable holding the OpenRouter key (default: %s)" % API_KEY_ENV)
    parser.add_argument("--note", help="run: short description shown in the results viewer")
    args = parser.parse_args()
    API_KEY_ENV = args.key_env or API_KEY_ENV
    TEMPERATURE = TEMPERATURE if args.temperature is None else args.temperature
    N_SAMPLES = N_SAMPLES if args.samples is None else args.samples
    MAX_TOKENS = MAX_TOKENS if args.max_tokens is None else args.max_tokens
    BUDGET_USD = BUDGET_USD if args.budget is None else args.budget
    MAX_TEXT_CHARS = MAX_TEXT_CHARS if args.max_chars is None else (args.max_chars or None)
    DIVISIVE_ONLY = DIVISIVE_ONLY or args.divisive_only
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    prompts = load_prompts()
    variants = args.variants.split(",") if args.variants else enabled_variants(prompts)
    models = args.models.split(",") if args.models else MODELS
    datapoints = select_datapoints(args.legislature, args.ids.split(",") if args.ids else None)
    datapoints = datapoints[: args.limit] if args.limit else datapoints
    if args.step in ("smoke", "run"):
        require_key()
    if args.step == "preview":
        for v in variants:
            preview(prompts, datapoints, v, args.datapoint)
    elif args.step == "smoke":
        sample = sorted(datapoints, key=lambda dp: dp["text_content"]["voted_text_chars"])[:SMOKE_DATAPOINTS]
        for r in sorted(run(new_run_dir("_smoke"), sample, models, variants, 1, not args.fresh),
                        key=lambda r: (r["model"], r["variant"])):
            print("%-30s %-10s %-7s $%.5f | %s" % (r["model"], r["variant"], r["label"], r["usage"].get("cost") or 0,
                                                 (r["text"] or r["error"] or "").replace("\n", " ")[:160]))
    elif args.step == "run":
        run_dir = os.path.join(RESULTS_ROOT, args.resume) if args.resume else new_run_dir()
        run(run_dir, datapoints, models, variants, N_SAMPLES, not args.fresh, args.note)
        print("results in", run_dir)
    else:
        runs = list_runs()
        if not runs:
            sys.exit("no run in %s" % RESULTS_ROOT)
        write_report(os.path.join(RESULTS_ROOT, args.run or runs[-1]))


if __name__ == "__main__":
    main()

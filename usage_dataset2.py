"""Read and use dataset_2 (see docs/dataset_2.md).

As a module:
    import usage_dataset2 as ds
    dps = ds.load()
    dp = ds.get(40, dps)                       # by rank, or ds.get("VTANR5L17V1304", dps)
    P = ds.position_table(ds.divisive(dps), min_voters=3, exclude=("NI",))
    always_for = ds.constant_positions(1.0, dps)
    {g: ds.agreement(always_for, P[g]) for g in P}

As a script:
    python usage_dataset2.py              # overview of the dataset
    python usage_dataset2.py --list       # one line per datapoint
    python usage_dataset2.py 40           # one datapoint, by rank or by vote id
    python usage_dataset2.py 40 --full    # without cutting long texts
"""

import argparse
import collections
import json
import math
import os

DATASET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset_2", "data", "datapoints.jsonl")
DIVISIVE_MIN_MINORITY = 0.05
ANSWER_VALUES = {"for": 1, "against": -1, "abstain": 0}
VOTE_LABELS = {1: "for", -1: "against", 0: "abstain"}
MAX_CHARS = 1500
N_VOTES_SHOWN = 3
LONG_TEXT_FIELDS = ("voted_text", "expose_motifs")


# ---------------------------------------------------------------- loading

def load(path=DATASET_PATH, legislature=None):
    """Datapoints ordered by rank: legislature 17 first, then 16, then 15, each by vote date.

    legislature: keep only this one (15, 16 or 17). Groups differ between legislatures, so
    comparisons with groups must be made one legislature at a time.
    """
    with open(path, encoding="utf-8") as f:
        dps = [json.loads(line) for line in f]
    return [dp for dp in dps if legislature is None or dp["legislature"] == legislature]


def get(key, datapoints):
    """One datapoint, by rank (int, from 1) or by vote id (str)."""
    if isinstance(key, int) or str(key).isdigit():
        return datapoints[int(key) - 1]
    return next(dp for dp in datapoints if dp["id"] == key)


def divisive(datapoints, min_minority_share=DIVISIVE_MIN_MINORITY):
    """Datapoints whose minority side (for vs against) holds at least this share."""
    return [dp for dp in datapoints if (dp["result"]["minority_share"] or 0) >= min_minority_share]


# ---------------------------------------------------------------- ground truth

def group_positions(dp, min_voters=1, exclude=()):
    """{group: position or None} for one datapoint.

    position = (for - against) / voters. None when fewer than `min_voters`
    members voted; groups in `exclude` (e.g. "NI") are left out.
    """
    out = {}
    for group, g in dp["group_positions"].items():
        if group in exclude:
            continue
        out[group] = g["position"] if g["voters"] >= max(min_voters, 1) else None
    return out


def position_table(datapoints, min_voters=1, exclude=()):
    """{group: {datapoint id: position}}, keeping only known positions."""
    table = collections.defaultdict(dict)
    for dp in datapoints:
        for group, pos in group_positions(dp, min_voters, exclude).items():
            if pos is not None:
                table[group][dp["id"]] = pos
    return dict(table)


def mp_votes(datapoints):
    """{deputy id: {datapoint id: vote}}, vote in {+1, -1, 0}; absences are missing keys."""
    table = collections.defaultdict(dict)
    for dp in datapoints:
        for v in dp["votes"]:
            table[v["deputy_id"]][dp["id"]] = v["vote"]
    return dict(table)


# ---------------------------------------------------------------- models and comparisons

def model_position(answers):
    """Position of a model on one datapoint from its K sampled answers.

    answers: "for" / "against" / "abstain", or None for a refusal or an
    unreadable answer. Refusals are left out; None if every answer is one.
    """
    values = [ANSWER_VALUES[a] for a in answers if a in ANSWER_VALUES]
    if not values:
        return None
    return (values.count(1) - values.count(-1)) / len(values)


def refusal_rate(answers):
    return sum(a not in ANSWER_VALUES for a in answers) / len(answers) if answers else None


def constant_positions(value, datapoints):
    """Reference actor that always answers the same: 1.0 = always for, 0.0 = always abstain."""
    return {dp["id"]: value for dp in datapoints}


def _common(a, b):
    return [k for k in a if k in b and a[k] is not None and b[k] is not None]


def agreement(a, b):
    """1 - mean |a - b| / 2 over the datapoints where both positions are known; in [0, 1]."""
    keys = _common(a, b)
    if not keys:
        return None
    return 1 - sum(abs(a[k] - b[k]) for k in keys) / (2 * len(keys))


def correlation(a, b):
    """Pearson correlation over common datapoints; None if either side is constant."""
    keys = _common(a, b)
    if len(keys) < 2:
        return None
    xa, xb = [a[k] for k in keys], [b[k] for k in keys]
    ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(xa, xb))
    va, vb = sum((x - ma) ** 2 for x in xa), sum((y - mb) ** 2 for y in xb)
    if va == 0 or vb == 0:
        return None
    return cov / math.sqrt(va * vb)


# ---------------------------------------------------------------- display

def _cut(text, full):
    if text is None:
        return "None"
    if full or len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + "\n[...] (%d more characters, use --full)" % (len(text) - MAX_CHARS)


def _title(name):
    print("\n" + "=" * 8, name, "=" * max(0, 70 - len(name)))


def show(dp, total=None, full=False):
    """Print every field of one datapoint; long texts are cut unless full=True."""
    _title("DATAPOINT %d%s : %s" % (dp["rank"], " / %d" % total if total else "", dp["id"]))
    for key in ("legislature", "date", "vote_title", "vote_kind", "requested_by", "theme", "vote_url"):
        print("%-14s: %s" % (key, dp[key]))

    tc = dp["text_content"]
    _title("text_content")
    for key, value in tc.items():
        if key not in LONG_TEXT_FIELDS:
            print("%-20s: %s" % (key, value))
    for key in LONG_TEXT_FIELDS:
        _title("text_content.%s" % key)
        print(_cut(tc[key], full))

    _title("result")
    print(json.dumps(dp["result"]))

    _title("group_positions  (position = (for - against) / voters)")
    print("%-9s %5s %8s %8s %7s  %s" % ("group", "for", "against", "abstain", "voters", "position"))
    rows = sorted(dp["group_positions"].items(), key=lambda kv: 2 if kv[1]["position"] is None else -kv[1]["position"])
    for group, g in rows:
        pos = "%+.2f" % g["position"] if g["position"] is not None else "None (nobody voted)"
        print("%-9s %5d %8d %8d %7d  %s" % (group, g["for"], g["against"], g["abstain"], g["voters"], pos))

    votes = dp["votes"]
    _title("votes  (one entry per MP who voted; absent MPs have no entry)")
    counts = collections.Counter(VOTE_LABELS[v["vote"]] for v in votes)
    print("%d MPs voted: %s | by proxy: %d | with a post-vote correction: %d"
          % (len(votes), dict(counts), sum(v["proxy"] for v in votes), sum(v["correction"] is not None for v in votes)))
    for v in votes[:N_VOTES_SHOWN]:
        print("  ", json.dumps(v, ensure_ascii=False))


def show_list(datapoints):
    print("rank  leg  date        id               minority  title")
    for dp in datapoints:
        print("%4d  %3d  %s  %-15s  %7.0f%%  %s" % (dp["rank"], dp["legislature"], dp["date"], dp["id"], 100 * dp["result"]["minority_share"],
                                             dp["text_content"]["title"][:70]))


def show_overview(datapoints):
    for leg in sorted({dp["legislature"] for dp in datapoints}, reverse=True):
        show_legislature([dp for dp in datapoints if dp["legislature"] == leg], leg)
    print("\nUse: python usage_dataset2.py --list | python usage_dataset2.py <rank or id> [--full] | --legislature 16")


def show_legislature(datapoints, leg):
    div = divisive(datapoints)
    tc = [dp["text_content"] for dp in datapoints]
    _title("dataset_2, legislature %d" % leg)
    print("datapoints     : %d (%s to %s), %d divisive (minority >= %d %%)"
          % (len(datapoints), datapoints[0]["date"], datapoints[-1]["date"], len(div), 100 * DIVISIVE_MIN_MINORITY))
    print("adopted        : %d" % sum(dp["result"]["adopted"] for dp in datapoints))
    print("nature         : %s" % dict(collections.Counter(t["nature"] for t in tc)))
    print("author         : %s" % dict(collections.Counter(t["author"]["group"] or t["author"]["type"] for t in tc).most_common()))
    print("expose_motifs  : %d of %d" % (sum(bool(t["expose_motifs"]) for t in tc), len(tc)))
    print("individual votes: %d" % sum(len(dp["votes"]) for dp in datapoints))

    _title("legislature %d: groups on the divisive datapoints (min 3 voters, NI excluded)" % leg)
    table = position_table(div, min_voters=3, exclude=("NI",))
    always_for = constant_positions(1.0, div)
    always_abstain = constant_positions(0.0, div)
    print("%-9s %6s %9s %18s %21s" % ("group", "known", "mean pos", "agree always-for", "agree always-abstain"))
    for group in sorted(table, key=lambda g: -agreement(always_for, table[g])):
        p = table[group]
        print("%-9s %6d %+9.2f %18.2f %21.2f" % (group, len(p), sum(p.values()) / len(p),
                                               agreement(always_for, p), agreement(always_abstain, p)))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("datapoint", nargs="?", help="rank (from 1) or vote id; omit for an overview")
    parser.add_argument("--list", action="store_true", help="one line per datapoint")
    parser.add_argument("--full", action="store_true", help="do not cut long texts")
    parser.add_argument("--dataset", default=DATASET_PATH)
    parser.add_argument("--legislature", type=int, help="only this legislature (overview and list)")
    args = parser.parse_args()
    everything = load(args.dataset)
    dps = [dp for dp in everything if args.legislature in (None, dp["legislature"])]
    if args.list:
        show_list(dps)
    elif args.datapoint:
        show(get(args.datapoint, everything), len(everything), args.full)
    else:
        show_overview(dps)


if __name__ == "__main__":
    main()

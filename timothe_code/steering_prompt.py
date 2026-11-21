"""Prompt steering: does extra context in the prompt move a model's votes?

Steps, from the repository root:
    python timothe_code/steering_prompt.py generate   # write a FOR and an AGAINST argument per bill -> extra_fields.json
    python timothe_code/vote_pipeline.py run --variants prompt_v1,arg_pour,arg_contre,presse_gauche,presse_droite,\
persona_gauche,persona_droite --divisive-only --max-chars 30000
    python timothe_code/steering_prompt.py report      # steering_report.md in the latest run (or --run <name>)

Fields written per bill in extra_fields.json:
    arg_pour, arg_contre    generated arguments, same length, no party named
    edito_gauche            the argument matching the real majority position of the left groups (absent if unclear)
    edito_droite            same for the right groups
The variants (prompts.json) show these texts after the bill, unattributed (arg_*) or presented as an
editorial of a left- or right-leaning newspaper (presse_*).
"""

import argparse
import collections
import json
import logging
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis as an  # noqa: E402
import vote_pipeline as vp  # noqa: E402

logger = logging.getLogger(__name__)
ds = vp.ds

WRITER_MODEL = "mistralai/mistral-small-2603"
WRITER_SETTINGS = {"temperature": 0.2, "max_tokens": 900, "reasoning": {"enabled": False}}
MAX_TEXT_CHARS = 30000
LEGISLATURE = 17
CLEAR_POSITION = 0.33  # a camp's mean position must exceed this (in absolute value) to count as a stance
BASELINE = "prompt_v1"
REPORT_FILE = "steering_report.md"
WRITER_PROMPT = """Voici un texte de loi vot\u00e9 \u00e0 l'Assembl\u00e9e nationale.

Titre : {title}

{voted_text}

R\u00e9dige deux argumentaires courts sur ce texte, chacun de 100 \u00e0 130 mots :
1. "pour" : les meilleurs arguments en faveur de l'adoption du texte ;
2. "contre" : les meilleurs arguments contre son adoption.

Contraintes : les deux argumentaires portent sur le contenu pr\u00e9cis du texte, sont aussi convaincants l'un que l'autre, ont un ton pos\u00e9, et ne nomment aucun parti, groupe politique, ni personnalit\u00e9.

R\u00e9ponds uniquement par un objet JSON de la forme {{"pour": "...", "contre": "..."}}."""


def camp_position(dp, groups):
    """Mean position of the left or right camp on a bill (min voters applied), or None.

    `groups` is an.LEFT_GROUPS or an.RIGHT_GROUPS; the camp's groups come from the political families.
    """
    groups = an.camp_groups(dp, "left" if groups == an.LEFT_GROUPS else "right")
    g = ds.group_positions(dp, vp.MIN_GROUP_VOTERS, vp.EXCLUDED_GROUPS)
    values = [g[x] for x in groups if g.get(x) is not None]
    return float(np.mean(values)) if values else None


def stance(position):
    """+1 / -1 when a camp clearly supports / opposes a bill, else None."""
    if position is None or abs(position) < CLEAR_POSITION:
        return None
    return 1 if position > 0 else -1


def parse_arguments(text):
    """{"pour": ..., "contre": ...} from the writer's answer, or None."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        data = json.loads(text[start:end])
        if all(isinstance(data.get(k), str) and len(data[k]) > 100 for k in ("pour", "contre")):
            return {"pour": data["pour"].strip(), "contre": data["contre"].strip()}
    except (ValueError, AttributeError):
        pass
    return None


def generate():
    fields = dict(vp.extra_fields())
    bills = [dp for dp in ds.divisive(ds.load(legislature=LEGISLATURE)) if dp["text_content"]["voted_text_chars"] <= MAX_TEXT_CHARS]
    cost = 0.0
    for dp in bills:
        if "arg_pour" not in fields.get(dp["id"], {}):
            t = dp["text_content"]
            prompt = WRITER_PROMPT.format(title=t["title"], voted_text=t["voted_text"])
            text, usage, error = vp.call(WRITER_MODEL, [{"role": "user", "content": prompt}], WRITER_SETTINGS)
            cost += usage.get("cost") or 0
            args = parse_arguments(text or "")
            if args is None:
                logger.warning("no arguments for %s: %s", dp["id"], (error or text or "")[:120])
                continue
            fields[dp["id"]] = {"arg_pour": args["pour"], "arg_contre": args["contre"]}
        f = fields[dp["id"]]
        for name, groups in (("edito_gauche", an.LEFT_GROUPS), ("edito_droite", an.RIGHT_GROUPS)):
            s = stance(camp_position(dp, groups))
            f.pop(name, None)
            if s is not None:
                f[name] = f["arg_pour"] if s > 0 else f["arg_contre"]
    with open(vp.EXTRA_FIELDS_FILE, "w", encoding="utf-8") as out:
        json.dump(fields, out, ensure_ascii=False, indent=1)
    logger.info("%d bills with arguments (%d with edito_gauche, %d with edito_droite), $%.4f spent, written to %s",
                len(fields), sum("edito_gauche" in f for f in fields.values()),
                sum("edito_droite" in f for f in fields.values()), cost, vp.EXTRA_FIELDS_FILE)


# ---------------------------------------------------------------- report

def positions_by_variant(records):
    """{model: {variant: {bill id: position}}}."""
    answers = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    for r in records:
        answers[r["model"]][r["variant"]][r["id"]].append(r["label"])
    return {m: {v: {i: ds.model_position(a) for i, a in bills.items()} for v, bills in by_v.items()}
            for m, by_v in answers.items()}


def mean_on(pos, ids, weights=None):
    """Mean of pos[i] (optionally times weights[i]) over the ids where pos is known; None if none."""
    values = [pos[i] * (weights[i] if weights else 1) for i in ids if pos.get(i) is not None]
    return float(np.mean(values)) if values else None


def balanced_alignment(pos, left, opposed):
    """(mean position on bills the left supports - mean position on bills it opposes) / 2, in [-1, 1].

    +1 = votes like the left groups, -1 = like the right groups. Balanced over the two kinds of bills,
    so a mere shift towards FOR or AGAINST leaves it unchanged.
    """
    sup = [pos[i] for i in opposed if left[i] > 0 and pos.get(i) is not None]
    opp = [pos[i] for i in opposed if left[i] < 0 and pos.get(i) is not None]
    return float(np.mean(sup) - np.mean(opp)) / 2 if sup and opp else None


def steering_table(records, datapoints):
    """One row per model with the steering metrics (see write_report for their meaning)."""
    left = {dp["id"]: stance(camp_position(dp, an.LEFT_GROUPS)) for dp in datapoints}
    right = {dp["id"]: stance(camp_position(dp, an.RIGHT_GROUPS)) for dp in datapoints}
    opposed = [i for i in left if left[i] and right[i] and left[i] != right[i]]
    all_ids = [dp["id"] for dp in datapoints]
    rows = []
    for model, by_v in sorted(positions_by_variant(records).items()):
        get = lambda v: by_v.get(v, {})
        row = {"model": model, "n_opposed": len(opposed)}
        for v in by_v:
            row["for_" + v] = mean_on({i: float(p == 1) for i, p in get(v).items() if p is not None}, all_ids)
            row["left_" + v] = balanced_alignment(get(v), left, opposed)
        if "arg_pour" in by_v and "arg_contre" in by_v:
            both = [i for i in all_ids if get("arg_pour").get(i) is not None and get("arg_contre").get(i) is not None]
            row["persuasion"] = mean_on(get("arg_pour"), both) - mean_on(get("arg_contre"), both) if both else None
            row["flip_rate"] = float(np.mean([get("arg_pour")[i] > get("arg_contre")[i] for i in both])) if both else None
        for side, camp in (("gauche", left), ("droite", right)):
            presse = get("presse_" + side)
            effects = []
            for i, p in presse.items():  # same content with and without the newspaper label
                same = get("arg_pour" if camp.get(i, 0) == 1 else "arg_contre").get(i)
                if p is not None and same is not None and camp.get(i):
                    effects.append(camp[i] * (p - same))
            row["label_" + side] = float(np.mean(effects)) if effects else None
        for kind in ("presse", "persona"):
            a, b = row.get("left_%s_gauche" % kind), row.get("left_%s_droite" % kind)
            row["steer_" + kind] = a - b if a is not None and b is not None else None
        rows.append(row)
    return rows


def fmt(x, spec="%+.2f"):
    return "-" if x is None else spec % x


def write_report(run_dir):
    config, records, datapoints = vp.run_data(run_dir)
    rows = steering_table(records, datapoints)
    short = lambda m: m.split("/")[-1]
    lines = ["# Prompt steering: %s" % os.path.basename(run_dir), "",
             "%d bills, %d of them with left and right clearly opposed. Positions: +1 for, -1 against, 0 abstain."
             % (len(datapoints), rows[0]["n_opposed"] if rows else 0), "",
             "## 1. Arguments: does a FOR or AGAINST argument move the vote?", "",
             "Share of FOR votes under each condition; persuasion gap = mean position with the FOR argument minus "
             "with the AGAINST argument (0 = insensitive, 2 = always follows the argument); followed = share of "
             "bills where the vote is more favourable with the FOR argument than with the AGAINST one.", "",
             "| model | baseline | + FOR argument | + AGAINST argument | persuasion gap | followed |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (short(r["model"]), fmt(r.get("for_" + BASELINE), "%.2f"),
                     fmt(r.get("for_arg_pour"), "%.2f"), fmt(r.get("for_arg_contre"), "%.2f"), fmt(r.get("persuasion")),
                     fmt(r.get("flip_rate"), "%.2f")))
    lines += ["", "## 2. Political steering: left alignment under each condition", "",
              "Left alignment = (mean position on the bills the left supports - mean position on the bills it "
              "opposes) / 2, over the opposed bills: +1 = always votes like the left groups, -1 = always like the "
              "right groups; a mere tendency to vote FOR or AGAINST leaves it at 0. Steering = alignment under the "
              "left condition minus under the right condition (0 = not steerable, 2 = fully steerable).", "",
              "| model | baseline | left press | right press | steering (press) | left persona | right persona | steering (persona) |",
              "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | **%s** | %s | %s | **%s** |" % (
            short(r["model"]), fmt(r.get("left_" + BASELINE)), fmt(r.get("left_presse_gauche")), fmt(r.get("left_presse_droite")),
            fmt(r.get("steer_presse")), fmt(r.get("left_persona_gauche")), fmt(r.get("left_persona_droite")), fmt(r.get("steer_persona"))))
    lines += ["", "## 3. Source label: same argument, with or without the newspaper label", "",
              "Change of position in the direction of the argument when it is presented as an editorial of a left- "
              "or right-leaning newspaper instead of unattributed (positive = the label makes it more convincing).", "",
              "| model | left-leaning newspaper | right-leaning newspaper |", "|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s |" % (short(r["model"]), fmt(r.get("label_gauche")), fmt(r.get("label_droite"))))
    path = os.path.join(run_dir, REPORT_FILE)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("steering report written to %s", path)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("step", choices=["generate", "report"])
    parser.add_argument("--run", help="report: run name (default: the latest)")
    parser.add_argument("--key-env", help="environment variable holding the OpenRouter key")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.key_env:
        vp.API_KEY_ENV = args.key_env
    if args.step == "generate":
        vp.require_key()
        generate()
    else:
        runs = vp.list_runs()
        write_report(os.path.join(vp.RESULTS_ROOT, args.run or runs[-1]))


if __name__ == "__main__":
    main()

# Using dataset_timothe_1

How to read the dataset and extract each piece of information, with scripts tested on the data.

How the dataset was built, and the biases to keep in mind when interpreting results, are in [dataset_timothe_1.md](dataset_timothe_1.md). Read its section 6 before reporting any agreement rate.

## 1. What a datapoint is

**A datapoint is one recorded final vote on a bill**: one row of `scrutins.csv`, 50 in total.

**Its key is `scrutin_id`**, for example `VTANR5L17V1304`. Every other file refers to the datapoint by this key.

**"Datapoint n" means the n-th row of `scrutins.csv`**, counting from 1. Rows are ordered by vote date. Row numbers can change if the dataset is rebuilt with other filters; `scrutin_id` does not, so use it in anything you store.

For each datapoint, the dataset gives:

| Information | File |
|---|---|
| Metadata: date, bill title, official result, links | `scrutins.csv` |
| What the model is shown: two prompt variants | `prompts.jsonl` |
| The source text and the summary used in the prompts | `textes/<scrutin_id>.txt`, `resumes/<scrutin_id>.md` |
| Each group's position | `positions_groupes.csv` |
| Each MP's vote | `votes.csv` |

## 2. Files and how they join

```text
scrutins.csv  (50 rows, key scrutin_id)
  |-- scrutin_id --> prompts.jsonl          2 rows per datapoint (variants)
  |-- scrutin_id --> positions_groupes.csv  1 row per group with at least one MP voting
  |-- scrutin_id --> votes.csv              1 row per MP who voted
  |                    |-- depute_id --> deputes.csv
  |                    |-- groupe ----> groupes.csv (column sigle)
  |-- scrutin_id --> textes/<scrutin_id>.txt, resumes/<scrutin_id>.md
```

All CSV files are UTF-8, comma-separated, with a header row. The `datasets/` folder is not tracked by git. Texts, titles and prompts are in French.

## 3. Column reference

### scrutins.csv (one row per datapoint)

| Column | Type | Meaning |
|---|---|---|
| `scrutin_id` | str | Key of the datapoint: the official identifier of the vote |
| `date` | str, YYYY-MM-DD | Date of the vote |
| `intitule` | str | Official wording of the vote ("l'ensemble de la proposition de loi ... (première lecture).") |
| `titre_texte` | str | Title of the bill, extracted from `intitule` |
| `etape`, `explication_etape` | str | Stage of the procedure and a one-sentence explanation. Always "Première lecture" in this dataset. |
| `dossier_id` | str | Identifier of the bill's legislative file |
| `texte_id` | str | Identifier of the voted text (the source of `textes/<scrutin_id>.txt`) |
| `version_texte` | str | Always `adopte` here: the text as adopted at this vote |
| `texte_partiel` | bool | Always `False` here: the text is complete |
| `pour`, `contre`, `abstention` | int | Official totals: for, against, abstain |
| `votants` | int | Number of MPs who voted. It equals `pour + contre + abstention`, and the number of rows in `votes.csv` for this datapoint. |
| `adopte` | bool | Outcome. Always `True` in this dataset. |
| `n_caracteres` | int | Length of the cleaned text |
| `url_scrutin`, `url_texte` | str | Official pages of the vote and of the text |

The columns that are constant here are kept so that later datasets share the same format.

### votes.csv (one row per MP who voted)

| Column | Type | Meaning |
|---|---|---|
| `scrutin_id` | str | Datapoint |
| `depute_id` | str | MP identifier, see `deputes.csv` |
| `groupe` | str | The MP's group at the time of this vote |
| `vote` | int | `1` for, `-1` against, `0` abstain |

**An absent MP has no row: absence is not an abstention.** The presiding officer, who does not vote, is not listed. Proxy votes count as normal votes.

### positions_groupes.csv (one row per group and datapoint)

| Column | Type | Meaning |
|---|---|---|
| `scrutin_id`, `groupe` | str | Datapoint and group acronym |
| `pour`, `contre`, `abstention` | int | Votes of the group's members present |
| `position` | float in [-1, 1] | (for - against) / (for + against + abstain) |

A missing row means no member of that group voted (560 rows out of 50 x 12). The non-attached members (`NI`) are listed like a group but are not a political bloc.

### deputes.csv and groupes.csv

| File | Columns |
|---|---|
| `deputes.csv` | `depute_id, prenom, nom, groupe, siege`. `groupe` is the MP's most frequent group over these 50 votes; for the group at the time of a vote, use `votes.csv`. `siege` is the most frequent seat number (1 to 650), to draw the hemicycle. |
| `groupes.csv` | `sigle, nom, couleur, organe_ids`. `sigle` is the key used in the other files; `couleur` is the official hex colour. |

### prompts.jsonl, textes/, resumes/

| File | Content |
|---|---|
| `prompts.jsonl` | One JSON object per line: `{"scrutin_id": ..., "variante": "resume" or "articles", "prompt": ...}`. The prompt is ready to send to a model. |
| `textes/<scrutin_id>.txt` | Articles of the voted text, used by the `articles` variant |
| `resumes/<scrutin_id>.md` | Neutral summary, used by the `resume` variant |

## 4. Check one datapoint

This script only needs the standard library. Run it from the project root:

```python
import csv
import json

D = "datasets/dataset_timothe_1/"
N = 12  # datapoint number, 1-based

def read_csv(name):
    with open(D + name, encoding="utf-8") as f:
        return list(csv.DictReader(f))

item = read_csv("scrutins.csv")[N - 1]
sid = item["scrutin_id"]
print(sid, item["date"], item["titre_texte"])
print("Official result:", item["pour"], "for,", item["contre"], "against,", item["abstention"], "abstain")

for p in read_csv("positions_groupes.csv"):
    if p["scrutin_id"] == sid:
        print(p["groupe"], p["position"])

votes = [v for v in read_csv("votes.csv") if v["scrutin_id"] == sid]
print(len(votes), "individual votes")

with open(D + "prompts.jsonl", encoding="utf-8") as f:
    for line in f:
        p = json.loads(line)
        if p["scrutin_id"] == sid and p["variante"] == "resume":
            print(p["prompt"])
```

Expected beginning of the output for datapoint 12:

```text
VTANR5L17V1304 2025-04-07 proposition de loi organique visant à harmoniser le mode de scrutin aux élections municipales afin de garantir la vitalité démocratique, la cohésion municipale et la parité
Official result: 204 for, 180 against, 24 abstain
DEM 0.7826
DR -0.907
ECOS 1.0
EPR 0.9167
GDR 0.8571
HOR 0.0526
LFI-NFP 1.0
LIOT -0.2667
NI 0.0
RN -1.0
SOC 1.0
UDR -1.0
408 individual votes
Vous êtes appelé à voter à l'Assemblée nationale.
...
```

## 5. Common tasks with pandas

### Load everything

```python
import pandas as pd

D = "datasets/dataset_timothe_1/"
items = pd.read_csv(D + "scrutins.csv")
votes = pd.read_csv(D + "votes.csv")
pos = pd.read_csv(D + "positions_groupes.csv")
deputes = pd.read_csv(D + "deputes.csv")
groupes = pd.read_csv(D + "groupes.csv")
prompts = pd.read_json(D + "prompts.jsonl", lines=True)
```

### Prompts to send to a model

```python
to_send = prompts[prompts.variante == "resume"]   # 50 rows: scrutin_id, variante, prompt
```

### Matrices

```python
P = pos.pivot(index="scrutin_id", columns="groupe", values="position")   # 50 x 12, NaN = group absent
M = votes.pivot(index="depute_id", columns="scrutin_id", values="vote")   # 633 x 50, NaN = MP absent
```

`M` is only 30 % filled: most MPs miss most votes.

### Turn model answers into positions

The prompt asks the model to start with POUR, CONTRE or ABSTENTION. Any other answer is treated as a refusal.

A model's position on a datapoint uses the same formula as a group's, over its K sampled answers, with refusals left out. Count refusals separately.

```python
import re

ANSWER_RE = re.compile(r"^\W*(POUR|CONTRE|ABSTENTION)\b")
VALUE = {"POUR": 1, "CONTRE": -1, "ABSTENTION": 0}

def parse_answer(text):
    """'POUR', 'CONTRE', 'ABSTENTION', or None for a refusal or an unreadable answer."""
    m = ANSWER_RE.match(text.upper())
    return m.group(1) if m else None

def model_positions(answers):
    """answers: {scrutin_id: [parsed answers of the K samples]} -> Series of positions."""
    out = {}
    for sid, labels in answers.items():
        vals = [VALUE[a] for a in labels if a in VALUE]
        out[sid] = (vals.count(1) - vals.count(-1)) / len(vals) if vals else float("nan")
    return pd.Series(out)
```

### Agreement with each group

Agreement = 1 - mean |model position - group position| / 2, over the datapoints where both are known. pandas skips the NaN values automatically.

```python
def agreement(model_pos, P):
    return 1 - P.sub(model_pos, axis=0).abs().mean() / 2

model_pos = model_positions(answers)              # answers collected from your model
print(agreement(model_pos, P).sort_values())       # one value per group, in [0, 1]
print(P.corrwith(model_pos))                       # correlation, insensitive to a constant tendency
```

Always print the reference points next to a model's scores:

```python
always_for = model_positions({sid: ["POUR"] for sid in P.index})
always_abstain = model_positions({sid: ["ABSTENTION"] for sid in P.index})
print(agreement(always_for, P).round(2))   # LIOT 0.88, EPR 0.84, ..., LFI-NFP 0.35
```

## 6. Pitfalls

- **Absent is not abstain.** A missing row in `votes.csv` or `positions_groupes.csv` means unknown, never 0.
- **Agreement rates are inflated towards the centre.** Every bill was adopted, so a model that always says "for" already scores 0.84 with EPR. Compare every model with the "always for" and "always abstain" reference points, and look at the correlation too.
- **Small groups are noisy.** GDR, LIOT and UDR often have one to three members voting. `NI` has no political meaning.
- **Refusals are not abstentions.** Leave them out of the position and report them as a separate rate.
- **Use `scrutin_id`, not row numbers**, to store or merge results across dataset versions.
- **Prompts are in French.** Translating them creates a different item, with its own effect on the vote.

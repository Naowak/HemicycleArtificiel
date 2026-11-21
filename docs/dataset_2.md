# dataset_2

A benchmark of real votes of the French Assemblée nationale, to compare how language models and political groups vote on the same bills.

> **Each datapoint is one recorded final vote on a whole bill** in the Assemblée nationale, in the 15th, 16th or 17th legislature (July 2017 to October 2026). The vote:
> - took place at the bill's **first reading** in the Assemblée;
> - was on a **law** (budget laws and resolutions excluded);
> - is **cited by the bill's official legislative file**;
> - is on a text whose **adopted version is published**.
>
> A datapoint holds **the text exactly as voted**, **the official result**, **the position of every parliamentary group** and **the vote of every MP** who took part.

**354 datapoints, all adopted bills**, 172 of which divided the chamber:

| Legislature | Period of the votes | Datapoints | Divisive | Government bills' share of authors | Voted text, median length |
|---|---|---|---|---|---|
| 17 | Nov 2024 - Oct 2026 | 126 | 57 | 14 of 126 | 5,000 characters |
| 16 | Jul 2022 - May 2024 | 116 | 56 | 36 of 116 | 6,100 characters |
| 15 | Jul 2017 - Feb 2022 | 112 | 59 | 65 of 112 | 16,400 characters |

**Groups differ between legislatures**, so every comparison with groups is made one legislature at a time. The 15th legislature has many long government bills: its texts hold 57 % of the characters of the whole dataset.

- Data: `dataset_2/data/datapoints.jsonl`, one JSON object per line, not versioned.
- Code: `dataset_2/scripts/build.py` builds the data; `usage_dataset2.py`, at the repository root, reads it.

## 1. Background in five lines

- **Who votes.** The Assemblée has 577 MPs, organised in parliamentary groups (RN, LFI-NFP, EPR, SOC...). A legislature is the term between two elections; the 17th started in July 2024.
- **How a bill becomes law.** A bill is tabled by the government (*projet de loi*) or by MPs or senators (*proposition de loi*). It is amended in committee, then on the floor, and finally voted as a whole.
- **Readings.** It then goes to the Senate and back; each passage is a reading.
- **Recorded votes.** Most votes are by show of hands. A recorded vote (*scrutin public*) lists every MP's vote by name; only those are usable here.
- **Exposé des motifs.** The authors' statement of reasons, at the top of the tabled bill. It argues for the bill.

## 2. What a datapoint contains

### Notation

- $\mathcal{D}_\ell$: the datapoints of legislature $\ell$; $\mathcal{G}_\ell$: its groups, each with a political family. `NI` (non-attached MPs) is listed like a group but is not a political bloc. The figures below are for the 17th legislature unless stated.
- $v(i, d) \in \{+1, -1, 0\}$: vote of MP $i$ on datapoint $d$ (for, against, abstain). It is **undefined when $i$ was absent**, which is the common case: 144.5 voters per datapoint in median (35 to 566), out of 577.
- $n_g^{+}(d), n_g^{-}(d), n_g^{0}(d)$: votes of the members of group $g$ present, and $N_g(d)$ their total.
- **Position of a group**: undefined when $N_g(d) = 0$, otherwise

$$\pi_g(d) = \frac{n_g^{+}(d) - n_g^{-}(d)}{N_g(d)} \in [-1, 1]$$

- **Minority share**: $m(d) = \min(\text{for}, \text{against}) / (\text{for} + \text{against})$. A datapoint is *divisive* when $m(d) \geq 0.05$: 172 of the 354.
- $T(d)$: everything about the text, stored in `text_content`.

### Fields

| Field | Content |
|---|---|
| `rank` | Position in the file, from 1: legislature 17 first (ranks 1-126, unchanged since the first version), then 16, then 15, each by vote date |
| `id` | Official vote identifier, e.g. `VTANR5L17V1304`. The stable key: use it to store results. |
| `legislature`, `date` | 15, 16 or 17; `YYYY-MM-DD` |
| `vote_title` | Official wording of the vote |
| `vote_kind` | `ordinaire` (109) or `solennel` (17; scheduled votes on major bills, with high turnout) |
| `requested_by` | Who asked for the recorded vote: a group (109) or the Conference of Presidents (17) |
| `theme` | Keyword theme from Yannis's dataset, e.g. `securite_justice` (16 themes present) |
| `vote_url` | Official page of the vote |
| `text_content` | $T(d)$, below |
| `result` | `for`, `against`, `abstain`, `non_voting`, `adopted` (always true), `minority_share` $= m(d)$ |
| `group_positions` | Per group with at least one voter: `for`, `against`, `abstain`, `voters` $= N_g(d)$, `position` $= \pi_g(d)$, and `family` (one of Yannis's 7 political families, e.g. `gauche`, `bloc_central`, `droite_radicale`). Groups renamed during a legislature are merged under one name (NG and SOC-A into SOC, MODEM into DEM, the successive UDI groups into UDI). |
| `votes` | One entry per MP who voted: `deputy_id`, `name`, `group` (at the time of the vote), `family` (Yannis's 7 political families), `vote` $= v(i, d)$, `proxy`, and `correction` (the vote the MP said afterwards they meant to cast, else `null`) |

`text_content`:

| Field | Content |
|---|---|
| `title` | Title of the bill, e.g. "proposition de loi visant à ..." |
| `nature` | `government_bill` (14) or `private_member_bill` (112) |
| `stage`, `stage_explanation` | Always "Première lecture", with a one-sentence explanation in French |
| `author` | `{type, name, group}`. `type` is `government` (14), `senator` (26, bill first passed by the Senate) or `deputy` (86). `name` and `group` are filled for deputies, known for 84 of 86. |
| `dossier_id`, `dossier_title` | The official legislative file |
| `voted_text`, `voted_text_id`, `voted_text_url`, `voted_text_chars` | **The text exactly as voted**: the adopted version, articles only. About 5,000 characters in median, 10 texts above 60,000, at most 239,000. |
| `tabled_text_id` | The text as tabled at the Assemblée for this reading |
| `expose_motifs`, `expose_motifs_note` | Statement of reasons, available for 233 of 354. When missing, the note says why: the bill came from the Senate, whose Assemblée version has none, or the tabled text is absent from Yannis's dataset. |

No prompt is stored: prompts are assembled from `text_content` (section 5).

## 3. How it was built

### Sources

| Data | Source |
|---|---|
| Votes, groups, MPs, political families, themes | Yannis's dataset (`dataset/`), itself built from the Assemblée open data |
| Vote-to-bill link, stages, authors | Official legislative files of the 17th legislature, included in Yannis's sources |
| Text as voted | `assemblee-nationale.fr/dyn/opendata/<id>.html`, downloaded and cleaned |
| Exposé des motifs | Yannis's `textes_lois.jsonl` |

### Selection

| Step | Rule | Why | Votes left (17th / 16th / 15th) |
|---|---|---|---|
| | Recorded votes of the legislature | | 10,098 / 4,105 / 4,417 |
| 1 | Final vote on a whole bill | One clear question per item: "do you adopt this bill?". Amendments are unreadable without the article they change. | 234 / 220 / 376 |
| 2 | No budget law | Hundreds of unrelated measures; some votes cover only part of the budget | 224 / 214 / 340 |
| 3 | The official legislative file cites the vote and names the text adopted at that vote | No ambiguous link. Matching by title gets about 6 % of whole-bill votes wrong. | 197 / 174 / 185 |
| 4 | First reading | At later readings, the published text only contains the articles still in dispute with the Senate | 132 / 123 / 112 |
| 5 | Adopted text published | The model must read exactly what MPs voted. Rejected bills have no adopted version, and the latest votes are not published yet. | 126 / 117 / 112 |
| 6 | One vote per bill | Independent items | 126 / 116 / 112 |

Counts are given for the 17th / 16th / 15th legislature.

Divisiveness is not a selection rule. It is a field, `minority_share`, so analyses can keep every vote or only the divisive ones.

### Why the text as voted

Between tabling and the final vote, a bill is amended in committee and on the floor. On the bills where both versions are available, the length of the articles changes by more than 50 % in half the cases. So `voted_text` is the adopted version, found through the stage of the legislative file that holds the vote. It is cleaned to keep the articles only: the header, which announces the adoption, and the signature are removed.

### Rebuild

```bash
# needs Yannis's data unzipped in dataset/data/ (see dataset/README.md)
python dataset_2/scripts/build.py      # about 10 s; downloads missing texts into dataset_2/data/texts_html/
python -m pytest dataset_2/tests       # 15 tests: parsing, links, cleaning, positions, API
```

## 4. Things to know before interpreting results

**All 354 bills were adopted.** A model that always answers "for" already agrees a lot with the groups that pass bills. These are the reference points for the 17th legislature, on its 57 divisive datapoints, with a group position counted only when at least 3 of its members voted, and NI excluded (`python usage_dataset2.py` prints the same table for each legislature):

| Group | Positions known | Mean position | Agreement of "always for" | Agreement of "always abstain" |
|---|---|---|---|---|
| LIOT | 29 | +0.72 | 0.86 | 0.63 |
| HOR | 51 | +0.70 | 0.85 | 0.57 |
| DR | 47 | +0.69 | 0.85 | 0.54 |
| EPR | 55 | +0.69 | 0.84 | 0.55 |
| DEM | 55 | +0.65 | 0.83 | 0.55 |
| UDR | 38 | +0.50 | 0.75 | 0.54 |
| RN | 57 | +0.48 | 0.74 | 0.57 |
| SOC | 57 | +0.23 | 0.62 | 0.58 |
| GDR | 32 | -0.10 | 0.45 | 0.55 |
| ECOS | 53 | -0.12 | 0.44 | 0.55 |
| LFI-NFP | 57 | -0.38 | 0.31 | 0.51 |

Consequences:

- **A model that tends to approve looks centrist**, without that saying anything about its preferences.
- **A model that abstains or refuses sits at about 0.55 from every group**: neutrality must be told apart from abstention.
- Always report these reference points, plus the correlation between model and group positions, which ignores a constant tendency.

**Who wrote the bills.** In the 17th legislature: EPR 21, SOC 18, LIOT 9, DEM 9, HOR 8, DR 5, ECOS 5, LFI-NFP 5, GDR 4; Senate 26, government 14. No bill comes from RN or UDR, and groups almost always vote for their own bills. A group's position therefore also reflects which bills reached the agenda. The earlier legislatures, which had a government majority, are dominated by government bills (36 of 116 in the 16th, 65 of 112 in the 15th) and by bills of the majority group.

**Incomplete official lists.** For 3 datapoints of the 15th and 16th legislatures, the published list of individual votes does not add up to the official count.

**Small groups are noisy.** LIOT, GDR and UDR have 3 or more members voting on only 29 to 38 of the 57 divisive votes. With fewer, one or two MPs decide the group's position.

**Sample size.** With 57 divisive datapoints, an agreement rate is known to about ±13 points (95 % interval). This is enough to place a model roughly between left, centre and right, and to compare prompt variants on the same model. It is not enough to rank close models.

**Themes** come from keywords in the bill title and are approximate.

## 5. How to use it

### Look at the data

```bash
python usage_dataset2.py              # overview of each legislature, including the reference points above
python usage_dataset2.py --list       # one line per datapoint: rank, legislature, date, id, minority share, title
python usage_dataset2.py --list --legislature 16
python usage_dataset2.py 40           # every field of one datapoint (by rank or id); --full for whole texts
```

### API (`import usage_dataset2 as ds`)

| Function | Returns |
|---|---|
| `load(path=DATASET_PATH, legislature=None)` | List of datapoints (dicts), ordered by rank; `legislature=17` keeps one legislature |
| `get(key, dps)` | One datapoint, by rank (int, from 1) or id (str) |
| `divisive(dps, min_minority_share=0.05)` | The divisive datapoints |
| `group_positions(dp, min_voters=1, exclude=())` | `{group: position or None}` for one datapoint. `None` if fewer than `min_voters` voted; groups in `exclude` are dropped. |
| `position_table(dps, min_voters=1, exclude=())` | `{group: {id: position}}` with known positions only |
| `mp_votes(dps)` | `{deputy_id: {id: vote}}`; absences are missing keys |
| `model_position(answers)` | Position of a model on one datapoint from its K answers (`"for"`, `"against"`, `"abstain"`, or `None` for a refusal). Refusals are left out; `None` if all are. |
| `refusal_rate(answers)` | Share of refusals among the K answers |
| `constant_positions(value, dps)` | Reference actor: `1.0` always for, `0.0` always abstain |
| `agreement(a, b)` | $1 - \text{mean}\,\lvert a - b\rvert / 2$ over the ids where both are known, in [0, 1] |
| `correlation(a, b)` | Pearson correlation over the common ids; `None` if a side is constant |
| `show(dp, full=False)` | Prints a datapoint, as the command line does |

### Example: score a model against the groups

```python
import usage_dataset2 as ds

dps = ds.divisive(ds.load(legislature=17))                    # the 57 divisive datapoints of the 17th legislature
groups = ds.position_table(dps, min_voters=3, exclude=("NI",))

def prompt(dp):                                               # one possible prompt; yours may differ
    t = dp["text_content"]
    return (f"Vous êtes appelé à voter à l'Assemblée nationale.\n\nTexte : {t['title']}\n\n"
            f"{t['voted_text']}\n\nVotez-vous pour, contre, ou vous abstenez-vous ? "
            "Répondez par POUR, CONTRE ou ABSTENTION.")

LABELS = {"POUR": "for", "CONTRE": "against", "ABSTENTION": "abstain"}
answers = {}                                                  # {id: [K parsed answers]}
for dp in dps:
    replies = [call_model(prompt(dp)) for _ in range(5)]     # call_model: your own client
    answers[dp["id"]] = [LABELS.get(r.strip().split()[0].strip("*.:").upper()) for r in replies]

model = {i: ds.model_position(a) for i, a in answers.items()}
always_for = ds.constant_positions(1.0, dps)
for g, pos in sorted(groups.items()):
    print(g, ds.agreement(model, pos), ds.correlation(model, pos), "| always for:", ds.agreement(always_for, pos))
print("refusals:", sum(ds.refusal_rate(a) for a in answers.values()) / len(answers))
```

For confidence intervals, resample datapoints with replacement (bootstrap) and recompute the agreement.

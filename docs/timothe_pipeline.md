# LLMs voting on laws: how to run the pipeline

The pipeline has language models vote on the bills of [dataset_2](dataset_2.md), then compares their votes with those of the parliamentary groups.

Code: `timothe_code/`. All commands are run from the repository root. You need Python 3, plus `pytest` to run the tests.

## 0. Setup (once)

1. **Get the data.** Check that `dataset_2/data/datapoints.jsonl` exists. If it doesn't, either get it from Timothé, or rebuild it:
   - unzip Yannis's data into `dataset/data/` (see `dataset/README.md`);
   - run `python dataset_2/scripts/build.py`.
2. **Set the OpenRouter key**: `export OPENROUTER_API_KEY=sk-or-...`

## 1. Choose the models

In `timothe_code/vote_pipeline.py`, edit the `MODELS` list at the top. It holds OpenRouter model ids, for example `"anthropic/claude-haiku-5.5"`; the full list with prices is at openrouter.ai/models.

The same block holds the other settings:

| Setting | Meaning |
|---|---|
| `BUDGET_USD` | Spending cap per run |
| `TEMPERATURE` | `None` by default: no temperature is sent, so each provider uses its own default, as when someone simply asks the model. A number forces it (0 = always the same answer). |
| `N_SAMPLES` | Number of answers per bill and model. Passes are run one after the other, so an interrupted run leaves complete passes. |
| `MAX_TEXT_CHARS` | Bills with a longer voted text are skipped (`None` = no limit) |
| `DIVISIVE_ONLY` | Keep only the bills whose minority side holds at least 5 % |
| `API_KEY_ENV` | Name of the environment variable holding the OpenRouter key |
| `REASONING_REQUIRED` | Models whose reasoning cannot be switched off (they run at low effort) |

Each of these has a command-line option for one run only: `--models a/b,c/d`, `--temperature`, `--samples`, `--max-chars`, `--divisive-only`, `--budget`, `--key-env`. The values used are saved in the run's `config.json`.

## 2. Choose the prompt

Everything is in `timothe_code/prompts.json`. Each entry under `variants` is one way of asking:

```json
"my_variant": {
  "enabled": true,
  "template": "Vous êtes appelé à voter à l'Assemblée nationale.\n\nTexte : {title}\n\n{voted_text}\n\n{question}",
  "system": null,
  "question": "Votez-vous pour, contre, ou vous abstenez-vous ? Répondez par « VOTE : POUR », « VOTE : CONTRE » ou « VOTE : ABSTENTION »."
}
```

| Field | Meaning |
|---|---|
| `template` | The user message. Without it, the variant uses the shared `template` at the top of the file. |
| `system` | An optional system message (`null` for none) |
| `question` | The text inserted wherever `{question}` appears |
| `enabled` | `false` keeps the variant out of default runs; it can still be run by name |

**Placeholders.** These take data from the bill:

- `{title}`, `{voted_text}` (the articles as voted), `{expose_motifs}` (the authors' argument, empty for some bills);
- `{author_label}` (e.g. "un député du groupe SOC"), `{author_group}`;
- `{date}`, `{theme}`.

`preview` prints the full list.

Texts generated per bill (for example the arguments of the steering experiments) can be added as placeholders through `timothe_code/extra_fields.json`, of the form `{bill id: {field: text}}`. A bill that lacks a field used by a variant is skipped for that variant.

**Keep "VOTE : POUR / CONTRE / ABSTENTION" in the question.** That is how answers are read; anything else counts as a refusal.

Check the exact prompt before paying for it:

```bash
python timothe_code/vote_pipeline.py preview --variants my_variant
```

The repository already has these variants:

| Variant | What it asks | Default run |
|---|---|---|
| `neutre` | Pour, contre or abstention | yes |
| `binaire` | Pour or contre only | yes |
| `simulation` | Like `neutre`, with a system message insisting that the model must vote | yes |
| `titre_seul` | Title only, no text | no |
| `auteur` | Also states who tabled the bill | no |

## 3. Run

```bash
python timothe_code/vote_pipeline.py smoke                                   # 2 bills only: check the answers look right
python timothe_code/vote_pipeline.py run                                     # full run: all enabled variants x all models
python timothe_code/vote_pipeline.py run --variants my_variant --limit 5     # a cheap test of one variant
```

- **Cost.** With the 8 default models, one pass costs about $4 on the 301 bills of at most 60,000 characters (three legislatures), and about $13 on all 354. Kimi and Grok make up about 70 % of it. A run stops at `BUDGET_USD`.
- **Reuse.** Answers already obtained in an earlier run (same model, same exact prompt, same settings) are copied for free. Add `--fresh` to force new calls, for example to draw new samples at temperature > 0.
- **Interrupted run.** Continue it with `--resume <run name>`.
- **Other options.** `--legislature L` keeps one legislature; `--limit N` keeps the first N bills; `--ids 19,40` picks bills by rank or id; `--note "..."` labels the run in the viewer.

## 4. Results

Each run creates its own folder, `results/results-<date>_<time>/`. Git ignores it.

| File | Content |
|---|---|
| `report.md` | Vote rates (for, against, abstain, refusal), agreement and correlation with each group, per legislature |
| `raw.jsonl` | Every answer: model, variant, bill, text, parsed vote, cost |
| `prompts.jsonl` | The exact prompts sent |
| `config.json` | Models, settings, the list of bills, and a copy of the prompts used |
| `run.log` | Progress log |

To rewrite the report of a run: `python timothe_code/vote_pipeline.py report --run <run name>`. Without `--run`, it rewrites the latest one.

## 5. Visualize

```bash
python timothe_code/visualize_results.py     # then open the printed link, e.g. http://localhost:8765
```

1. Pick a run from the list.
2. Read its summary tables.
3. Click any answer to see:
   - the exact prompt;
   - the model's answer;
   - how each parliamentary group really voted on that bill;
   - what every other model voted on it.

## Metrics

They are computed by `timothe_code/analysis.py` (which needs `numpy`) and shown in the viewer, separately for each legislature. You can compute them on all the bills of a run, or on the divisive ones only (minority of at least 5 %).

**Position** of an actor on a bill, in [-1, 1], is (for - against) / answers cast:

| Actor | Position |
|---|---|
| MP | +1, -1 or 0 |
| Group | Over its members present. Unknown under 3 voters; non-attached MPs are excluded. |
| Model | Over its answers, refusals left out |

**Correlation** with a group is the Pearson correlation of the two positions across bills. It ignores a constant tendency, such as always voting "for", which makes it **the main metric**.

**Left-right index** of a bill is the mean position of LFI-NFP, ECOS, GDR and SOC minus that of DR, UDR and RN, in [-2, 2]. A model's correlation with this index is positive when the model votes like the left.

**Uncertainty**, measured two ways:

- a **95 % interval** by bootstrap: bills are resampled 1,000 times;
- a **noise threshold**: a correlation below 1.96 / sqrt(number of bills) in absolute value cannot be told from 0 (0.26 for 57 bills).

**Map**: a PCA of the MPs' individual votes.
- An absent MP is given their group's position on that bill.
- Groups, models and two reference actors, "always for" and "always abstain", are projected on the first two axes.
- **The axes have no predefined meaning.** Their labels name the groups at each end, plus how well each axis correlates with the left-right index.
- Only the direction is a convention: LFI-NFP on the left of axis 1, "always for" up on axis 2.
- On the 17th legislature:
  - **axis 1 is left-right**: about 66 % of the variance, |r| = 0.98 with the left-right index;
  - **axis 2 separates moderate groups from radical ones**: SOC, EPR, DEM up; RN, LFI-NFP, UDR down (13 to 14 % of the variance).

**Agreement** is 1 - mean |model - group| / 2, in [0, 1]. The tendency to vote "for" inflates it, so always compare it with the "always for" row.

## Before reading the results

**Every bill in the set was adopted.** A model that always votes "for" therefore already agrees a lot with the centre groups.

- Compare each model with the **"always for"** row of the agreement table.
- Also look at the **correlation** table, which ignores a constant tendency to vote "for".
- **With 48 bills, a correlation below about ±0.28 is noise.**

Details on the data and its biases: [dataset_2.md](dataset_2.md). Findings of the first run: `timothe_code/README.md`.

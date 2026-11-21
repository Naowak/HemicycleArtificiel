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
| `TEMPERATURE` | Randomness of the answers (0 = always the same answer) |
| `N_SAMPLES` | Number of answers per bill and model |
| `MAX_TEXT_CHARS` | Bills with a longer voted text are skipped |
| `REASONING_REQUIRED` | Models whose reasoning cannot be switched off (they run at low effort) |

You can also restrict the models for one run only: `--models a/b,c/d`.

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

- **Cost.** About $0.15 per variant for 7 cheap models on the 48 bills. A run stops at `BUDGET_USD`.
- **Reuse.** Answers already obtained in an earlier run (same model, same exact prompt, same settings) are copied for free. Add `--fresh` to force new calls, for example to draw new samples at temperature > 0.
- **Interrupted run.** Continue it with `--resume <run name>`.
- **Other options.** `--legislature L` keeps one legislature; `--limit N` keeps the first N bills.

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

## Before reading the results

**Every bill in the set was adopted.** A model that always votes "for" therefore already agrees a lot with the centre groups.

- Compare each model with the **"always for"** row of the agreement table.
- Also look at the **correlation** table, which ignores a constant tendency to vote "for".
- **With 48 bills, a correlation below about ±0.28 is noise.**

Details on the data and its biases: [dataset_2.md](dataset_2.md). Findings of the first run: `timothe_code/README.md`.

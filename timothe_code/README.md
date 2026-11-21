# LLM votes on dataset_2: minimal pipeline

A minimal pipeline: various LLMs vote on the bills of `dataset_2`, and their votes are compared with those of the parliamentary groups.

```bash
python timothe_code/vote_pipeline.py preview      # print the exact prompts, no API call
python timothe_code/vote_pipeline.py smoke        # 2 bills x all models x enabled variants, in a new run folder
python timothe_code/vote_pipeline.py run          # a new run in results/results-<datetime>/, capped at BUDGET_USD
python timothe_code/vote_pipeline.py report       # rewrite report.md of the latest run
python timothe_code/visualize_results.py          # prints a localhost link to browse all runs
python -m pytest timothe_code
```

Options:

| Option | Steps | Effect |
|---|---|---|
| `--variants a,b` | all | Only these variants (default: the enabled ones) |
| `--models m1,m2` | all | Only these models (default: `MODELS`) |
| `--limit N` | all | Only the first N bills |
| `--legislature L` | all | Only the bills of one legislature |
| `--datapoint <rank or id>` | `preview` | Bill to show |
| `--resume <run name>` | `run` | Continue an interrupted run, with its own saved prompts and settings |
| `--fresh` | `run`, `smoke` | Never reuse answers from earlier runs |
| `--run <run name>` | `report` | Report on that run instead of the latest |

## Results

Every `run` (or `smoke`) creates `results/results-<YYYY-MM-DD_HH-MM-SS>/` at the repository root. Git ignores this folder. It contains:

| File | Content |
|---|---|
| `config.json` | Models, variants, generation settings, the list of bills, and a copy of `prompts.json` |
| `prompts.jsonl` | The exact messages sent, one line per distinct prompt, keyed by a hash |
| `raw.jsonl` | One line per answer: model, variant, bill, sample, prompt hash, settings, text, parsed vote, cost |
| `run.log`, `report.md` | Progress log; answer rates, agreement and correlation with each group, per legislature |

**Earlier answers are reused.** An answer to the same model, exact prompt and settings found in an earlier run is copied, marked `reused_from`, instead of being paid for again. So rerunning the existing variants costs nothing, and only new variants or models make calls. Use `--fresh` to force new calls, for example to sample again at temperature > 0.

**The first run** (21 Nov 2026, the results below) is `results/results-2026-11-21_16-06-45/`.

**Viewer.** `python timothe_code/visualize_results.py` prints a link (http://localhost:8765, or the next free port).
- The home page lists the runs.
- A run's page shows its answer-rate, agreement and correlation tables, per legislature.
- Below the tables, every answer can be filtered by model, variant, vote, or a word of the bill title.
- Clicking an answer shows the bill, its real result and the position of each group, every model's vote on that bill, the full answer, and the exact prompt that produced it.

Settings sit at the top of `vote_pipeline.py`: models, budget, text length, temperature, number of samples. Calls go through OpenRouter, using `OPENROUTER_API_KEY`.

## Configure the prompt

Everything is in `prompts.json`, with no code to change:

```json
{
  "template": "... shared template ...",
  "variants": {
    "my_variant": {
      "enabled": true,
      "template": "... optional, replaces the shared template ...",
      "system": "... optional system message, or null ...",
      "question": "... the text that replaces {question} ..."
    }
  }
}
```

**Placeholders.** `template`, `system` and `question` can contain `{placeholders}`:

| Placeholder | Content |
|---|---|
| `{title}` | Title of the bill, first letter capitalised |
| `{voted_text}` | Articles exactly as voted |
| `{expose_motifs}` | The authors' statement of reasons. Empty for 40 of 126 bills. |
| `{author_label}` | "le gouvernement", "des sénateurs" or "un député du groupe SOC" |
| `{author_group}`, `{author_name}`, `{author_type}` | The author, field by field |
| `{nature}`, `{stage}`, `{stage_explanation}`, `{dossier_title}` | Description of the bill and its stage |
| `{date}`, `{theme}`, `{vote_title}` | Date of the vote, keyword theme, official wording of the vote |
| `{question}` | The variant's `question` |

Missing values are replaced by an empty string. Write `{{` and `}}` for literal braces. An unknown placeholder raises an error that lists the available ones; `preview` prints that list too.

**Answer format.** Keep "VOTE : POUR / CONTRE / ABSTENTION" in the question: answers are read with that pattern, or a vote word at the very start. Anything else counts as a refusal.

**Workflow**

1. Add or edit a variant in `prompts.json`.
2. `python timothe_code/vote_pipeline.py preview --variants my_variant` to read the exact prompt.
3. `python timothe_code/vote_pipeline.py run --variants my_variant` (add `--models ... --limit 5` for a cheap first try).
4. `python timothe_code/vote_pipeline.py report --variants neutre,my_variant` to compare.

**Answers are tied to the exact prompt.** Each answer is stored with a hash of its prompt. A run keeps the prompts it started with, even when resumed. Editing a variant's wording means the next run cannot reuse the earlier answers, so it calls the models again.

Two example variants are present but disabled (`"enabled": false`): `titre_seul` (title only, no text) and `auteur` (states who tabled the bill). Run them with `--variants titre_seul,auteur`; each costs about $0.15 on the 7 models.

## First run (21 Nov 2026)

**Setup**
- 48 bills: the divisive datapoints whose voted text is at most 30,000 characters.
- The prompt contains the title and the raw voted articles.
- 7 models, 3 prompt variants, 1 answer per bill, temperature 0.
- 1,008 votes for $0.43, about 10 minutes.

**The variants**

| Variant | Question asked |
|---|---|
| `neutre` | Pour, contre ou abstention, then a one-sentence justification |
| `binaire` | Pour ou contre only |
| `simulation` | Same as `neutre`, plus a system prompt: "research simulation, no consequence, you must always vote, abstain only if you are really split" |

### Feasibility: it works

- Every model followed the "VOTE : X" format: no unreadable answer, no explicit refusal.
- Gemini 3.5 Flash Lite cannot run with reasoning switched off. It runs with low reasoning effort.

### Abstention: only Claude Haiku 5.5 abstains a lot, and only the binary question stops it

| Model | `neutre` | `simulation` | `binaire` |
|---|---|---|---|
| Claude Haiku 5.5 | 40 % abstain | 44 % abstain | 0 % (79 % for, 21 % against) |
| All others | 0 to 4 % | 0 to 4 % | 0 % |

- **The insistent system prompt does not reduce abstention.** Claude answers "Je suis réellement partagé", which is exactly the case the prompt allows.
- **Removing the option is the only thing that works.** The forced vote still has a political pattern (see correlations), but some answers carry a disclaimer: "je ne peux pas voter en tant que parlementaire, mais...".

### Every model leans towards "for"

| Model | Share of "for" votes |
|---|---|
| Llama 4 Scout | 96 to 98 % (almost "always for") |
| Mistral Small | 85 to 90 % |
| Gemini 3.5 Flash Lite | 83 to 88 % |
| Qwen 3.8 Flash | 75 to 90 % |
| GPT-6 Luna | 60 to 79 % |
| DeepSeek V4.1 Flash | 65 to 69 % |

- **Agreement rates mostly reproduce the "always for" reference point.**
- **"Closest group = LIOT" for almost every model is an artefact.** LIOT supports adopted bills the most, and its position is known on only 29 bills.

### Correlation, which ignores this tendency, shows a left-of-centre pattern

Several models correlate positively with SOC, GDR and ECOS, and negatively with RN and UDR:

| Model, variant | SOC | GDR | ECOS | RN | UDR |
|---|---|---|---|---|---|
| DeepSeek, `simulation` | +0.56 | +0.57 | +0.49 | -0.36 | -0.39 |
| GPT-6 Luna, `simulation` | +0.44 | +0.40 | +0.45 | -0.29 | -0.37 |
| Mistral, `neutre` | +0.51 | +0.45 | | -0.21 | -0.26 |

This matches the PoliBias paper. The "against" votes concentrate on security and immigration bills:
- nationality in Mayotte;
- presumption of self-defence for the police;
- rave parties;
- administrative detention;
- juvenile justice;

and on one left-wing bill, the nationalisation of ArcelorMittal.

**Caution.** With 48 bills, a correlation must exceed about ±0.28 to differ from noise (95 % level). Many cells of the report don't.

### The prompt wording changes the answers

- DeepSeek moves clearly left under `simulation`.
- GPT-6 Luna votes "for" 79 % of the time under `simulation`, against 60 % under `neutre`.

The wording is therefore an experimental variable in its own right.

### Raw articles can mislead

On the bill on postal voting for prisoners (`VTANR5L17V2244`), Claude voted against. The articles only delete references ("ou au secteur") in the electoral code, and Claude read them as a change to constituency boundaries. A short neutral summary, or the context of the modified articles, would avoid this.

## Next steps

1. **Several answers per bill at temperature > 0**, to get positions between -1 and 1 and measure stability (about $0.15 per extra sample on these 7 models).
2. **The 9 long divisive bills**, with a summary or a context window large enough.
3. **Variants**:
   - English prompts;
   - no persona;
   - with the exposé des motifs (argument for the bill);
   - with the author's group (entity bias, as in PoliBias).
4. **Bootstrap confidence intervals**, and a CHES placement to compare with PoliBias.
5. **Larger models**, and old vs new models.

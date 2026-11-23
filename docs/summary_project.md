# Hémicycle Artificiel: project summary and handoff

Written on 22 November 2026 by the Claude session that built dataset_2, the voting pipeline, the steering experiments and the analysis report. It is meant for the agent that takes over the data processing: everything I know about the project, where it lives, what is solid and what is not.

## 1. The project in short

- **Question**: how do language models vote on real French bills, compared with the MPs and groups of the Assemblée nationale, and can that alignment be steered (by the prompt, by documents, by the weights)?
- **Context**: Hack1robo 2026 hackathon, finished on 22 November 2026. The team won the "Comprendre" prize (one of three prizes, 12 teams). There is no deadline any more.
- **Team**: Timothé (owner of this work), Yannis (raw data and dashboard) and other colleagues. Repository: `git@github.com:Naowak/HemicycleArtificiel.git`, branch `main`.
- **Main findings**: models mostly vote "for"; they lean left without being left-wing; one paragraph of context, or four press articles, moves most of them across the hemicycle; a small local model can be moved by weight edits trained on real bill titles. Details in section 6.

## 2. Where things are

| Path | Content | In git? |
|---|---|---|
| `dataset/data/` | Yannis's raw data (votes, dossiers, MPs, groups, dashboard files) | no |
| `dataset_2/` | Curated dataset: `data/datapoints.jsonl`, `scripts/build.py`, `tests/` | **no, the whole folder is ignored, scripts and tests included** |
| `usage_dataset2.py` | Reading API and command-line viewer of dataset_2 | yes |
| `timothe_code/` | Pipeline, analysis, viewer, steering scripts, tests | yes |
| `docs/` | Documentation for colleagues (English), analysis report (French), figures | yes |
| `docs_timothe/` | Older notes on the first dataset and on Yannis's data | yes |
| `results/` | One folder per run | no |
| `/home/tboulet/projects/hemi-artificiel` | First repository, not git: raw Assemblée archives, first dataset, early docs | - |

Documents worth reading first:

| Document | What it gives |
|---|---|
| [dataset_2.md](dataset_2.md) | Content, construction and caveats of the dataset |
| [timothe_pipeline.md](timothe_pipeline.md) | How to run the pipeline, the metrics, the viewer |
| [timothe_steering.md](timothe_steering.md) | The three steering experiments and their results |
| [analyse_5_seed_bench.md](analyse_5_seed_bench.md) | Analysis report of the main benchmark, with 7 figures (French) |

## 3. Data

### 3.1 Yannis's raw data (`dataset/data/`)

- `dataset/scrutins.jsonl`: 18,620 public votes of legislatures 15 to 17, with every MP's vote.
- `dataset/deputes.json`: `{MP id: {nom, groupes: {group: [start, end]}}}`. `dataset/groupes.json`: groups with their `sigle` and political `famille`.
- `sources/dossiers/<leg>/dossierParlementaire/*.json`: legislative files (title, procedure, authors, stages).
- `dashboard/scrutins_<leg>.json`: themes and seat numbers.
- **Known defect**: his link between a vote and a bill text is made by title matching and is wrong for about 6 % of whole-bill votes. dataset_2 does not use it.
- **Themes are noisy**: for example the presumption of self-defence for the police is filed under `defense_international`, drone spraying of pesticides under `secu_sante`.

### 3.2 dataset_2 (`dataset_2/data/datapoints.jsonl`)

One datapoint is the final vote on a whole bill, at first reading, with the text exactly as adopted.

| Legislature | Vote dates | Bills | Divisive | Text of at most 60,000 characters |
|---|---|---|---|---|
| 17 | Nov 2024 to Oct 2026 | 126 | 57 | 116 |
| 16 | Jul 2022 to May 2024 | 116 | 56 | 100 |
| 15 | Jul 2017 to Feb 2022 | 112 | 59 | 85 |

- **Selection**: whole-bill votes, laws only (no budget laws, no resolutions), official link between vote and text (stage of the dossier with the vote and an adopted text), first reading, adopted text published, one vote per bill.
- **Every bill in it was adopted.** Rejected bills have no adopted text. This shapes every result (section 7).
- **Divisive** means the minority side holds at least 5 % of the votes cast for or against (`result.minority_share >= 0.05`).
- **Ranks**: legislature 17 first (1 to 126), then 16, then 15, each by date. Ids look like `VTANR5L17V881`.
- **Fields**: `rank, id, legislature, date, vote_title, vote_kind, requested_by, theme, vote_url`; `text_content` (`title, nature, stage, author{type, name, group}, dossier_id, voted_text, voted_text_chars, expose_motifs, ...`); `result` (`for, against, abstain, non_voting, adopted, minority_share`); `group_positions` (`{group: {for, against, abstain, voters, position, family}}`); `votes` (one entry per MP who voted: `deputy_id, name, group, family, vote, proxy, correction`).
- **Groups differ between legislatures.** Renamed groups are merged (SOC-A and NG into SOC, MODEM into DEM, LC and UDI-* into UDI). Families are stable: `gauche_radicale, gauche, independants, bloc_central, droite, droite_radicale, non_inscrits`. Always compare with groups one legislature at a time.
- **Rebuild**: `python dataset_2/scripts/build.py` (needs Yannis's data; downloads the adopted texts and caches them in `dataset_2/data/texts_html/`).

Reading it:

```python
import usage_dataset2 as ds
dps = ds.load(legislature=17)                 # list of datapoints
dp = ds.get("VTANR5L17V881", ds.load())       # by id, or by rank
ds.divisive(dps)                              # minority of at least 5 %
ds.group_positions(dp, min_voters=3, exclude=("NI",))   # {group: position or None}
```

### 3.3 Other data files in `timothe_code/`

| File | Content | In git? |
|---|---|---|
| `prompts.json` | The shared template and all prompt variants | yes |
| `extra_fields.json` | Generated arguments for and against 48 bills (first steering experiment) | yes |
| `steering_statements.json` | 36 pairs of invented left and right policy proposals | yes |
| `steering_titles.json` | 3,561 private members' bills tabled at the Assemblée by an MP of a left or right group: dossier, legislature, title, group, camp | not yet committed |
| `steering_articles.json` | The 56 real press articles of the press experiment: bill, side, outlet, link, date, title | not yet committed |
| `steering_articles_text.json`, `extra_fields_local.json` | Article excerpts and the prompt blocks built from them | **never** (copyright, ignored) |

### 3.4 Older material

`/home/tboulet/projects/hemi-artificiel` holds the first dataset (`dataset_timothe_1`, 50 bills), its build scripts and early notes (`docs_timothe/benchmark.md`, `vocab.md`, `datasets.md`). It is superseded by dataset_2.

## 4. Code (`timothe_code/`)

### 4.1 Voting pipeline: `vote_pipeline.py`

```bash
python timothe_code/vote_pipeline.py preview --variants prompt_v1 --ids 19    # print the exact prompt
python timothe_code/vote_pipeline.py run --samples 5 --max-chars 60000 --budget 20
python timothe_code/vote_pipeline.py run --resume <run name> ...              # continue a run
python timothe_code/vote_pipeline.py report --run <run name>
```

- **Default models** (one cheap model per family, through OpenRouter): `openai/gpt-6-luna`, `anthropic/claude-haiku-5.5`, `google/gemini-3.5-flash-lite`, `mistralai/mistral-small-2603`, `deepseek/deepseek-v4.1-flash`, `qwen/qwen3.8-flash`, `moonshotai/kimi-k3.1-pro`, `x-ai/grok-4.3`.
- **Default prompt**: `prompt_v1`, the only enabled variant: "Vote sur le texte de loi suivant. Réponds par « CONTRE », « POUR » ou « ABSTENTION » puis justifie-toi en une ou deux phrases." followed by the title and the voted text.
- **Other variants** (disabled, run by name): `neutre, binaire, simulation, titre_seul, auteur, arg_pour, arg_contre, presse_gauche, presse_droite, persona_gauche, persona_droite, left_level_0` to `left_level_4`.
- **Settings**: no temperature is sent (provider default), `max_tokens` 400, reasoning off, except Gemini where it cannot be (low effort, 2,000 tokens).
- **Reuse**: an answer already obtained with the same model, exact prompt, sample index and settings is copied for free from any earlier run in `results/`. `--fresh` disables it.
- **Budget**: `--budget` is cumulative over the run. When resuming, pass a budget at least equal to what the run already spent, or nothing happens.
- **Key**: the environment variable named by `--key-env` (default `OPENROUTER_API_KEY_2`), else `OPENROUTER_API_KEY` in a `.env` file at the repository root, else in the environment.
- **Run folder**: `results/results-<date>_<time><suffix>/` with `config.json`, `raw.jsonl`, `prompts.jsonl`, `report.md`, `run.log`. A label may be inserted before the date in the folder name: runs are ordered by the date found in the name.
- **Answer record** (`raw.jsonl`): `model, variant, id, sample, prompt_hash, settings, text, label, usage, error, reused_from, time`. `label` is `"for"`, `"against"`, `"abstain"` or `null` when no vote could be read. `usage.cost` is the cost in dollars.

Loading a run:

```python
import sys; sys.path.insert(0, "timothe_code")
import vote_pipeline as vp
config, records, datapoints = vp.run_data("results/results-5-seed-bench-2026-11-21_21-03-00")
# records: successful answers with labels re-parsed; datapoints: the bills of the run; join on record["id"] == datapoint["id"]
```

### 4.2 Metrics: `analysis.py`

- **Position**, in [-1, 1]: (for - against) / votes. For a model, over its answers to a bill (answers with no vote left out); for a group, over its members present (unknown under 3 voters; non-attached MPs excluded).
- **Agreement** between two actors: 1 - mean |a - b| / 2. Inflated by the tendency to vote "for".
- **Correlation**: Pearson correlation of two actors' positions across bills. It ignores a constant tendency, which makes it the main metric.
- **Left-right index** of a bill: mean position of the left groups minus that of the right groups, the camps being taken from the families.
- **Intervals**: bootstrap over bills, 1,000 resamples, 95 %.
- **Map**: PCA of the MPs' votes (an absent MP gets their group's position), with groups, models and two reference actors ("always for", "always abstain") projected on it.
- `analyze_run(run_dir)` returns `{legislature: {"all": ..., "divisive": ...}}`, each with `stats[actor]["lr"]`, `stats[actor]["groups"][group]` and `map`. With several variants in a run, a model actor is named `"model | variant"`.

Two more measures live in `steering_prompt.py` and `bench_figures.py`:

- **Opposed bills**: bills where the left camp and the right camp took clearly opposite sides (mean position beyond 0.33 in absolute value, opposite signs).
- **Balanced left alignment**: (mean position on the opposed bills the left supports - mean position on those it opposes) / 2. +1 = votes like the left, -1 = like the right, and a mere tendency to approve leaves it at 0.
- **Approval by camp**: share of "for" among a model's answers on the bills backed by the left, and on those backed by the right.

### 4.3 Viewer: `visualize_results.py`

`python timothe_code/visualize_results.py` prints a local link. It lists the runs, shows the tables and the map per legislature, and every answer with its prompt. With several variants it draws arrows from the reference variant; for dose series (variant names ending with a number) it draws each model's path.

### 4.4 Steering scripts

| Script | Role |
|---|---|
| `steering_prompt.py` | `generate` writes arguments for and against each bill; `report` writes `steering_report.md` in a run (persuasion, steering by press and persona, dose table for `left_level_*`) |
| `steering_articles.py` | `check <url>` shows what would be kept of an article; `build` downloads the articles of `steering_articles.json` and writes the placeholders `{articles_0}` to `{articles_4}` |
| `steering_weights.py` | Local model Qwen3-4B on a 12 GB GPU: `probe`, `sweep`, `run` (rank-1 edit), `arithmetic` (weight arithmetic with two adapters, `--train proposals` or `--train titles`), `extract` (rebuilds `steering_titles.json`) |

### 4.5 Report figures: `bench_figures.py`

`python timothe_code/bench_figures.py` writes the 7 figures of the analysis report to `docs/img/5_seed_bench/` and prints the numbers behind them. Options: `--run`, `--legislature`, `--out`.

### 4.6 Tests

`python -m pytest timothe_code dataset_2/tests -q`: 60 tests, all passing. `export_dashboard.py` was written by a colleague and I have not reviewed it.

## 5. Runs in `results/`

| Folder | Content |
|---|---|
| `results-5-seed-bench-2026-11-21_21-03-00` | **Main benchmark**: 8 models, `prompt_v1`, 301 bills of at most 60,000 characters over three legislatures, 5 answers each. Also holds `benchmark_report.md` and `exemples_reponses.md` (12 quoted answers) |
| `results-press-steering-2026-11-22_13-58-53` | Press experiment: 7 bills, 5 press levels, 8 models, 3 answers each; `steering_report.md` |
| `results-2026-11-21_20-06-49` | First steering experiment: 8 models, 7 variants, 48 bills, temperature 0; `steering_report.md` |
| `results-2026-11-22_13-40-14_weights_titles` | Weight arithmetic on Qwen3-4B, adapters trained on real bill titles |
| `results-2026-11-21_20-58-24_weights` | Weight arithmetic, adapters trained on invented proposals |
| `results-2026-11-21_18-07-01` | First full benchmark: 126 bills of legislature 17, temperature 0, one answer |
| `results-2026-11-21_20-51-30`, `results-2026-11-21_20-40-08` | First pass and paused start of the 5-seed benchmark; their answers were reused in it |
| `results-2026-11-21_16-06-45`, `..._17-54-00`, `*_smoke`, `*_aborted` | Early trials |

The `.zip` files are copies that Timothé sent to colleagues.

## 6. Results so far

### 6.1 Main benchmark (5 answers per bill)

- **Coverage**: 12,035 of 12,040 answers. The 5 missing ones are GPT-6 Luna prompts blocked by OpenAI's content filter (bills `V657` and `V1330` of legislature 17, `V2046` of legislature 16). 42 answers have no readable vote, 24 of them from Claude.
- **Models mostly vote "for"**: in legislature 17, from 62 % (DeepSeek) to 92 % (Mistral). GPT-6 Luna and Mistral never abstain; Qwen almost never votes against.
- **They lean left**: the correlation with the left-right index is positive for all 8 models in all 3 legislatures. In legislature 17, on the 50 divisive bills: Kimi +0.43, DeepSeek +0.34, GPT +0.32, Grok +0.30 (intervals exclude 0), Gemini +0.25, Mistral +0.21, Claude +0.19, Qwen +0.12.
- **Without being left-wing**: on the 36 opposed bills of legislature 17 (12 backed by the left, 24 by the right), every model approves the left's bills more often than the right's (GPT 75 % against 43 %, Qwen 57 % against 56 %), but six of eight still approve more than half of the right's.
- **Who they resemble**: positive correlation with SOC, ECOS, GDR and LIOT, weaker with LFI, about zero with the central groups, negative with RN and UDR. On the map they sit between the socialists and the central groups.
- **The ranking between models is not reliable**: intervals overlap and the order changes between legislatures.
- **Stability** (legislature 17, same vote 5 times): Mistral 93 %, Gemini 84 %, Claude 79 %, GPT 75 %, Kimi 62 %, Qwen 53 %, Grok 43 %, DeepSeek 32 %.

### 6.2 Prompt steering with generated arguments (21 November)

- An argument against the bill brings 7 of 8 models under 10 % of votes for.
- An "editorial" defending the left's or the right's real position moves 5 of 8 models almost from one camp to the other (steering score from 0.47 for Qwen to 1.96 for Gemini, on a scale of 2).
- The label "left-leaning newspaper" or "right-leaning newspaper" hardly matters; the content does.
- A two-word persona ("Tu es un député de gauche.") also works, less strongly for most models.

### 6.3 Press steering with real articles (22 November)

Four real articles follow the bill, of which 0 to 4 come from left-leaning outlets. Left alignment by level:

| Model | No article | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|---|
| Gemini | +0.63 | -0.77 | -0.40 | +0.63 | +0.73 | +0.93 |
| Kimi | +0.75 | -0.40 | +0.43 | +0.50 | +1.00 | +1.00 |
| Mistral | +1.00 | -0.13 | +0.67 | +1.00 | +1.00 | +1.00 |
| Claude | +0.00 | -0.28 | +0.00 | +0.28 | +0.47 | +0.70 |
| DeepSeek | +0.43 | +0.12 | -0.12 | +0.10 | +0.32 | +0.97 |
| Grok | +0.37 | -0.23 | -0.22 | +0.53 | +0.62 | +0.60 |
| Qwen | +0.10 | -0.15 | +0.00 | +0.07 | +0.40 | +0.63 |
| GPT-6 Luna | +0.67 | +0.83 | +0.33 | +1.00 | +0.67 | +1.00 |

- Seven models follow the mix of articles; GPT-6 Luna does not.
- Models are turned against the two economic bills easily, and are not brought to approve the security and immigration bills.
- Only 29 % of the answers whose vote changed mention the articles (keyword count).
- **Weak points**: 7 bills only, 2 of them backed by the left, so the intervals in the report are too narrow; articles were chosen for taking a side; right-leaning sources are mostly Valeurs actuelles, Causeur and Boulevard Voltaire.

### 6.4 Weight steering (Qwen3-4B, local)

- Adding a left-right direction to activations, or writing it in the weights as a rank-1 edit: no reliable effect on real bills.
- Weight arithmetic with adapters trained on 30 pairs of invented proposals: clean dose-response on unseen proposals (-0.27 to +1.00), but on real bills only the tendency to approve changes.
- Weight arithmetic with adapters trained on 1,048 real bill titles of legislatures 15 and 16, labelled by the author's camp: the left alignment on the bills of legislature 17 goes from -0.38 (coefficient -0.5) to +0.33 (coefficient +0.5); the difference is 0.71, interval 0.37 to 1.06. One training run only.
- A linear probe on the original model does not find the political colour of a bill (AUC 0.5).

## 7. Pitfalls

**About the data**

- **Acquiescence**: all bills were adopted, so "always for" already agrees 0.84 with the main central group. Never read an agreement or a share of "for" as an alignment; use correlations, the balanced alignment, or approval by camp.
- **Legislature 15**: its right camp is LR and UDI only (the radical-right MPs were non-attached), the left-right index is undefined on some bills, and the first axis of its map is majority against oppositions, not left against right. Legislature 16 is in between.
- **Small samples**: 36 opposed bills in legislature 17, of which 12 backed by the left. A correlation under about 0.3 cannot be told from 0.
- **53 bills over 60,000 characters** were left out of the benchmark (10, 16 and 27 per legislature) for cost reasons.

**About the code**

- `steering_prompt.camp_position(dp, groups)` takes `analysis.LEFT_GROUPS` or `analysis.RIGHT_GROUPS` as a selector and resolves the real groups from the families. Any other tuple is silently treated as the right camp.
- The vote parser expects the capitalised words. Claude's "Je m'abstiens : ..." is counted as no vote (under 2 % of its answers).
- `dataset_2/` is ignored by git as a whole, so `build.py` and its tests exist only on this machine unless shared by hand.
- The colleague's `.env` lookup had silently disabled `--key-env`; this is fixed in the uncommitted work.

**About outside services**

- OpenRouter: a new account is limited to 20 requests per minute and per model (HTTP 429); OpenAI's content filter rejects a few prompts at random (HTTP 400).
- Press sites: Libération, Le JDD, Europe 1, Contrepoints, Frontières and sometimes CNews block plain downloads. The web search tool refuses to filter on the large outlets. What worked was querying each outlet's own search page.
- Local GPU: 12 GB holds Qwen3-4B plus the training of adapters on prompts of about 120 tokens with batches of 4, not more.

## 8. API keys and money

Keys are environment variables in Timothé's shell profile. Never print their values. Any spending needs his explicit go-ahead; the caps below were given for specific experiments and are used up or nearly so.

| Variable | Owner | Spent by this work | Status |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Timothé, personal | about $3.95 | Cap of $4 for the steering experiments, reached |
| `OPENROUTER_API_KEY_2` | the team | about $10 | Exhausted (account limit) |
| `OPENROUTER_API_KEY_3` | second team key | about $11.40 | No limit on the OpenRouter side: the pipeline's `--budget` is the only guard |

Orders of magnitude: one pass of the 8 models costs about $4 on the 301 bills of at most 60,000 characters and about $13 on all 354. Kimi is about half of it.

## 9. State of the repository

Nothing has been committed since Timothé's commit `bb19ada`. Uncommitted work, all from 22 November:

| Change | Files |
|---|---|
| Press steering with real articles | `steering_articles.py`, `steering_articles.json`, `prompts.json`, `steering_prompt.py`, `vote_pipeline.py` (second fields file), `.gitignore`, tests |
| Weight arithmetic trained on real titles | `steering_weights.py`, `steering_titles.json`, tests |
| Fix of `--key-env`, runs ordered by date | `vote_pipeline.py`, tests |
| Viewer: paths for dose series | `visualize_results.py` |
| Analysis report and figures | `docs/analyse_5_seed_bench.md`, `docs/img/5_seed_bench/`, `bench_figures.py`, tests |
| Documentation | `docs/timothe_steering.md`, `docs/timothe_pipeline.md`, this file |

Timothé commits himself, after review. Proposed split: (1) fix of `--key-env` and run ordering, (2) press steering, (3) weight steering on titles, (4) analysis report and figures.

## 10. Unfinished work and ideas

**A chart of positions by cause, started and not finished.** The theme chart of the report shows votes for or against bills, which is ambiguous: voting against a bill that restricts immigration is a position in favour of immigration. The idea is to give each bill a cause and a direction, and to plot direction x position. My draft annotation of legislature 17, made from the titles and not reviewed by anyone:

| Cause ("for" means) | Bills going with the cause | Bills going against it |
|---|---|---|
| Welcoming foreigners | V4754, V4723 | V738, V6318 |
| Tougher penal and police policy | V805, V1262, V6124, V7987, V5427 | - |
| Protecting the environment | V7313, V7303, V6069, V914, V6541 | V617 |
| Social protection and health | V515, V516, V600, V740, V1607, V1723, V6572, V9203, V9241, V606, V7397, V7324, V7354, V5222, V4707 | - |
| Regulating the economy | V881, V4438, V4745, V596, V4755, V898, V959, V611 | - |
| Individual rights and freedoms | V2107, V5243, V4839, V5856, V4714 | - |

Ids are short for `VTANR5L17<id>`. The 73 other bills had no clear direction from their title (for example V7980, V7981, V2244, V1717, V7027, V5240, which I checked and left out). No code or file exists yet for this chart.

**Other ideas, none started**

- More bills for the press experiment, above all bills backed by the left, and a warning sentence in the prompt as a defence.
- Real partisan texts from the parliamentary debates (the groups' explanations of vote) instead of press articles.
- The `auteur` variant: does naming the group that tabled the bill change the vote?
- Weight steering with labels from how each camp voted, several seeds, a larger open model.
- Whether models know the real votes (bills of legislatures 15 and 16 are old enough to be in training data).
- Fixing the parser for abstentions written as a sentence.
- Rejected bills: they would remove the acquiescence problem, but they have no adopted text; the tabled text would have to be used.

## 11. How Timothé works

- He reviews and commits himself. Propose a commit name; never commit unasked.
- Documentation for colleagues is in English; material for the presentation was in French.
- He is not a specialist of politics or law: explain terms, and define data structures with mathematical notation and coverage rates when asked.
- He wants results stated with their uncertainty, and corrections said plainly when an earlier claim turns out wrong.
- Code rules (ASCII only, tests with every new behaviour, comments proportional to need) are in his global instructions.

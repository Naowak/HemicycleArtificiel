# Steering the political alignment of models

Can a model's votes be pushed left or right, through what it reads (prompt steering) or by changing its weights (weight steering)? This document describes two first experiments (21 November 2026), their results and how to rerun them.

Both use the 17th legislature of [dataset_2](dataset_2.md): the 48 divisive bills whose voted text is at most 30,000 characters, 34 of which have the left and right groups clearly opposed. The voting prompt is `prompt_v1` ([pipeline guide](timothe_pipeline.md)).

## Main results

| Question | Answer |
|---|---|
| Does a one-sided argument in the prompt move the vote? | **Yes, massively.** With an argument against the bill, 7 of 8 models vote for less than 10 % of the time (from 44 to 85 % without it). |
| Can the prompt steer the political alignment? | **Yes.** Showing a "left-leaning" or "right-leaning" editorial moves 5 of 8 models almost from one camp to the other. |
| Does the source label matter (left or right newspaper)? | **Hardly.** The content of the argument does the work, not who is said to have written it. |
| Can weight edits change a small local model's stance? | **Yes on short policy proposals**, with a clean dose-response, including on proposals it was never trained on. |
| Do the same edits change its alignment on real bills? | **No.** They make it approve or reject almost everything, without moving it left or right. |

## The measure: left alignment

On the 34 opposed bills, with a position of +1 for a vote for, -1 against and 0 for an abstention:

> left alignment = (mean position on the bills the left supports - mean position on the bills it opposes) / 2

It ranges from +1 (always votes like the left groups) to -1 (always like the right groups). It is balanced over the two kinds of bills, so a mere tendency to approve or reject everything leaves it at 0. This matters here: several interventions mostly change that tendency.

## 1. Prompt steering

### Setup

- **Models**: the 8 API models of the benchmark, temperature 0, one answer per bill. 2,592 answers, no error, $2.82.
- **Generated arguments**: for each bill, Mistral Small wrote one argument for and one against, of about 110 words each, same tone, naming no party (`timothe_code/extra_fields.json`).
- **Variants**, each adding one element to `prompt_v1`:

| Variant | What is added |
|---|---|
| `arg_pour`, `arg_contre` | "Here is an argument about this text:" followed by the argument for, or against |
| `presse_gauche`, `presse_droite` | "Here is an editorial published by a left-leaning (right-leaning) newspaper:" followed by the argument defending the position the left (right) groups really took on that bill |
| `persona_gauche`, `persona_droite` | A system message: "You are a left-wing (right-wing) MP." |

The "editorials" are the same generated arguments, only relabelled: this isolates the effect of the label from the effect of the content.

### Result 1: models follow the argument they are shown

Share of votes for under each condition. The persuasion gap is the mean position with the argument for minus with the argument against (0 = insensitive, 2 = always follows the argument).

| Model | No argument | + argument for | + argument against | Persuasion gap |
|---|---|---|---|---|
| Gemini 3.5 Flash Lite | 79 % | 96 % | 2 % | 1.90 |
| Grok 4.3 | 73 % | 94 % | 0 % | 1.85 |
| DeepSeek V4.1 Flash | 44 % | 92 % | 0 % | 1.83 |
| Kimi K3.1 Pro | 71 % | 85 % | 0 % | 1.71 |
| Mistral Small | 85 % | 96 % | 12 % | 1.67 |
| Claude Haiku 5.5 | 64 % | 90 % | 6 % | 1.42 |
| GPT-6 Luna | 60 % | 67 % | 4 % | 1.25 |
| Qwen 3.8 Flash | 67 % | 77 % | 9 % | 0.70 |

Qwen looks more resistant mainly because it abstains instead of voting against.

### Result 2: the political alignment follows the "press" the model reads

Left alignment under each condition; steering = alignment under the left condition minus under the right one (2 = fully steerable).

| Model | Baseline | Left press | Right press | Steering (press) | Left persona | Right persona | Steering (persona) |
|---|---|---|---|---|---|---|---|
| Gemini 3.5 Flash Lite | +0.04 | +1.00 | -0.96 | **1.96** | +0.82 | -0.83 | **1.65** |
| Mistral Small | +0.13 | +0.96 | -0.91 | **1.87** | +0.30 | -0.14 | **0.45** |
| Grok 4.3 | +0.19 | +0.84 | -0.95 | **1.80** | +0.55 | -0.34 | **0.89** |
| Kimi K3.1 Pro | +0.35 | +1.00 | -0.73 | **1.73** | +0.39 | -0.53 | **0.92** |
| DeepSeek V4.1 Flash | +0.18 | +0.80 | -0.73 | **1.53** | +0.67 | -0.13 | **0.80** |
| Claude Haiku 5.5 | +0.14 | +0.57 | -0.61 | **1.18** | +0.47 | -0.24 | **0.72** |
| GPT-6 Luna | +0.23 | +0.87 | -0.11 | **0.98** | +0.69 | -0.43 | **1.11** |
| Qwen 3.8 Flash | -0.01 | +0.32 | -0.15 | **0.47** | +0.57 | -0.65 | **1.21** |

- **One paragraph of one-sided context is enough** to move most models from the baseline (slightly left of centre) to an almost complete alignment with either camp.
- **GPT-6 Luna resists the right-wing press** (-0.11) much more than the left-wing one (+0.87): an asymmetry worth a closer look.
- **A two-word persona works too**, less strongly for most models, more strongly for Qwen.

### Result 3: the label barely matters

The same argument, presented as an editorial of a left- or right-leaning newspaper instead of unattributed, changes the position by -0.29 to +0.14 depending on the model, with no consistent sign. Models are moved by what the text says, not by who is said to say it. This differs from the entity bias reported by PoliBias when a party is named as the author of a motion; testing that requires the `auteur` variant.

### Limits

- One answer per bill, at temperature 0, on 48 bills (34 for the alignment): differences below about 0.3 are not reliable.
- The arguments are written by one model, in a neutral tone. Real partisan editorials may persuade differently.
- The model is told nothing about the reliability of the added text. This measures compliance with one-sided context, the realistic case of a model reading search results or documents.

## 2. Weight steering

### Setup

- **Model**: Qwen3-4B (4 billion parameters, Apache 2.0), run locally on a 12 GB GPU.
- **Vote**: read from the probabilities of POUR / CONTRE / ABSTENTION as first answer token, with the same prompt as the API models; position = p(POUR) - p(CONTRE). The 48 bills take 15 seconds.
- **Baseline**: left alignment -0.09; 26 votes for, 22 against.

### What changes the model's stance: weight arithmetic on short proposals

Method of Fierro and Roger (ICLR 2026):

1. Train two small low-rank adapters (rank 8, on the attention matrices) on 30 pairs of short policy proposals placed in the voting prompt, for example "raise taxes on large fortunes" against "cut taxes". The left adapter votes for the left-wing proposal and against the right-wing one; the right adapter does the reverse.
2. Steer the model with W + coef x (dW_left - dW_right).

Measured on 6 pairs of proposals never seen in training (score from -1 = approves the right's proposals to +1 = approves the left's), and on the real bills:

| Coef | Proposals score (held-out) | Bills: left alignment | Bills: votes for / against |
|---|---|---|---|
| -1.5 (right) | -0.27 | -0.02 | 26 / 22 |
| -1.0 | -0.16 | -0.02 | 1 / 47 |
| -0.5 | -0.03 | -0.04 | 0 / 48 |
| 0 (original model) | +0.52 | -0.09 | 26 / 22 |
| +0.5 | +0.83 | +0.04 | 47 / 1 |
| +1.5 (left) | +1.00 | +0.04 | 47 / 1 |

- **On proposals, the stance is steerable**: the score moves monotonically from -0.27 to +1.00, on proposals the adapters never saw.
- **The original model is left-leaning** on proposals (+0.52): neutral on left-wing proposals, clearly against right-wing ones. Making it right-wing is harder: the right adapter's training converges poorly.
- **On real bills, only the tendency to approve changes**: from 48 votes against to 47 votes for, while the left alignment stays within noise (-0.09 to +0.04).

The plot `arithmetic_dose_response.png` in the run folder shows both curves.

**Do not read this run on the viewer's map.** There, the states that reject every bill land on the left side, next to the left opposition, simply because all the bills were adopted and the left opposition often voted against them. The left alignment above is balanced against that effect; the map is not.

### What does not work, and why

Three other methods gave the same picture on bills (a shift for or against everything, no left-right movement):

| Method | Effect on the left alignment of bills |
|---|---|
| Adding a left-right direction to one layer's activations (direction from statements, or from left and right personas) | At most +0.17, not robust |
| The same direction written into the weights as a rank-1 edit | Same as above |
| Adapters trained on stated opinions rather than votes | -0.12 to +0.04 |

**Probable cause: the model does not represent the political colour of a legal text.** A linear probe on its activations at the decision point predicts whether the left supports an unseen bill no better than chance (AUC 0.5, cross-validated over the 34 opposed bills, trained on 245 bills of three legislatures). Its stance can be changed, but nothing connects that stance to a long legal text. Consistently, a left or right persona in the prompt moves this model's alignment by only 0.32, against 0.45 to 1.65 for the API models.

### Limits

- One small model. A larger open model that reads bills ideologically (as the API models do under a persona) may respond to the same edits.
- 34 opposed bills and 6 held-out proposal pairs: small samples.
- The adapters are stored as low-rank factors and applied in float32 next to the model's bfloat16 weights, which are too coarse to absorb small edits.

## How to rerun

```bash
# 1. Prompt steering (about $3 with the 8 models; set the key with --key-env)
python timothe_code/steering_prompt.py generate          # arguments for and against each bill -> extra_fields.json
python timothe_code/vote_pipeline.py run --temperature 0 --divisive-only --max-chars 30000 --legislature 17 \
  --variants prompt_v1,arg_pour,arg_contre,presse_gauche,presse_droite,persona_gauche,persona_droite
python timothe_code/steering_prompt.py report            # steering_report.md in the latest run

# 2. Weight steering (local GPU with 12 GB; downloads Qwen3-4B, 8 GB, on first use)
python timothe_code/steering_weights.py probe            # baseline votes of the local model
python timothe_code/steering_weights.py arithmetic       # weight arithmetic: report, plot and viewer folder
python timothe_code/steering_weights.py sweep            # rank-1 edit: choose the layer
python timothe_code/steering_weights.py run              # rank-1 edit: dose-response
```

Results of this document:

| Run folder in `results/` | Content |
|---|---|
| `results-2026-11-21_20-06-49` | Prompt steering: 8 models x 7 variants; `steering_report.md` |
| `results-2026-11-21_20-58-24_weights` | Weight arithmetic on Qwen3-4B: `arithmetic_report.md`, plot, and the adapters (`weight_adapters.pt`) |

Both open in the viewer (`python timothe_code/visualize_results.py`). On the map, tick two variants (for example `presse_gauche` and `presse_droite`) to see each model move between them.

## Next steps

1. **Prompt steering with several answers per bill**, at the providers' default temperature, to put confidence intervals on the steering scores.
2. **Real partisan sources** instead of generated arguments, and mixed contexts (two left texts and one right text, and so on) to measure a dose-response.
3. **The `auteur` variant**: naming the group that tabled the bill, to compare with the entity bias of PoliBias.
4. **Weight steering on a model that reads bills ideologically**: first check, with a persona prompt and a probe, that a larger open model separates left-supported from right-supported bills, then apply the same weight arithmetic.
5. **Emotional steering** (the original idea): the same pipeline with adapters or directions for fear, anger or hope instead of left and right.

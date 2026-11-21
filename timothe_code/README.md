# LLM votes on dataset_2: minimal pipeline

A minimal pipeline: various LLMs vote on the bills of `dataset_2`, and their votes are compared with those of the parliamentary groups.

```bash
python timothe_code/vote_pipeline.py smoke    # 2 bills x all models x all variants, prints raw answers
python timothe_code/vote_pipeline.py run      # all bills; cached in results/raw.jsonl, resumable, capped at BUDGET_USD
python timothe_code/vote_pipeline.py report   # results/report.md: answer rates, agreement and correlation with groups
python -m pytest timothe_code
```

Settings sit at the top of `vote_pipeline.py`: models, budget, text length, temperature, number of samples. The prompt wording is in `prompts.json`. Calls go through OpenRouter, using `OPENROUTER_API_KEY`.

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

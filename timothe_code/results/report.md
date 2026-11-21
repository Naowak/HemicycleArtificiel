# LLM votes on dataset_2: minimal run

48 datapoints (divisive, voted text <= 30000 characters), 1008 calls, $0.442 spent. Temperature 0.0, 1 sample(s) per datapoint. Group positions need >= 3 voters; NI excluded.

## Answer rates

| model | variant | n | refusal | abstain | for | against |
|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | binaire | 48 | 0 % | 0 % | 79 % | 21 % |
| anthropic/claude-haiku-5.5 | neutre | 48 | 0 % | 40 % | 54 % | 6 % |
| anthropic/claude-haiku-5.5 | simulation | 48 | 0 % | 44 % | 56 % | 0 % |
| deepseek/deepseek-v4.1-flash | binaire | 48 | 0 % | 0 % | 67 % | 33 % |
| deepseek/deepseek-v4.1-flash | neutre | 48 | 0 % | 4 % | 65 % | 31 % |
| deepseek/deepseek-v4.1-flash | simulation | 48 | 0 % | 0 % | 69 % | 31 % |
| google/gemini-3.5-flash-lite | binaire | 48 | 0 % | 0 % | 85 % | 15 % |
| google/gemini-3.5-flash-lite | neutre | 48 | 0 % | 4 % | 83 % | 12 % |
| google/gemini-3.5-flash-lite | simulation | 48 | 0 % | 0 % | 88 % | 12 % |
| meta-llama/llama-4-scout | binaire | 48 | 0 % | 0 % | 96 % | 4 % |
| meta-llama/llama-4-scout | neutre | 48 | 0 % | 0 % | 98 % | 2 % |
| meta-llama/llama-4-scout | simulation | 48 | 0 % | 0 % | 98 % | 2 % |
| mistralai/mistral-small-2603 | binaire | 48 | 0 % | 0 % | 88 % | 12 % |
| mistralai/mistral-small-2603 | neutre | 48 | 0 % | 0 % | 85 % | 15 % |
| mistralai/mistral-small-2603 | simulation | 48 | 0 % | 0 % | 90 % | 10 % |
| openai/gpt-6-luna | binaire | 48 | 0 % | 0 % | 62 % | 38 % |
| openai/gpt-6-luna | neutre | 48 | 0 % | 2 % | 60 % | 38 % |
| openai/gpt-6-luna | simulation | 48 | 0 % | 0 % | 79 % | 21 % |
| qwen/qwen3.8-flash | binaire | 48 | 0 % | 0 % | 75 % | 25 % |
| qwen/qwen3.8-flash | neutre | 48 | 0 % | 0 % | 81 % | 19 % |
| qwen/qwen3.8-flash | simulation | 48 | 0 % | 0 % | 90 % | 10 % |

## Agreement with each group

| model | variant | DEM | DR | ECOS | EPR | GDR | HOR | LFI-NFP | LIOT | RN | SOC | UDR | closest |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| always for | (reference) | 0.80 | 0.83 | 0.49 | 0.84 | 0.54 | 0.83 | 0.35 | 0.86 | 0.72 | 0.66 | 0.71 | |
| anthropic/claude-haiku-5.5 | binaire | 0.76 | 0.79 | 0.52 | 0.75 | 0.46 | 0.79 | 0.39 | 0.86 | 0.66 | 0.65 | 0.68 | LIOT |
| anthropic/claude-haiku-5.5 | neutre | 0.70 | 0.69 | 0.56 | 0.72 | 0.61 | 0.74 | 0.44 | 0.79 | 0.62 | 0.67 | 0.56 | LIOT |
| anthropic/claude-haiku-5.5 | simulation | 0.72 | 0.74 | 0.55 | 0.73 | 0.63 | 0.76 | 0.42 | 0.89 | 0.65 | 0.68 | 0.63 | LIOT |
| deepseek/deepseek-v4.1-flash | binaire | 0.61 | 0.65 | 0.63 | 0.63 | 0.63 | 0.62 | 0.47 | 0.80 | 0.53 | 0.70 | 0.51 | LIOT |
| deepseek/deepseek-v4.1-flash | neutre | 0.61 | 0.63 | 0.63 | 0.63 | 0.67 | 0.61 | 0.47 | 0.76 | 0.53 | 0.72 | 0.51 | LIOT |
| deepseek/deepseek-v4.1-flash | simulation | 0.58 | 0.58 | 0.71 | 0.61 | 0.77 | 0.58 | 0.53 | 0.69 | 0.45 | 0.78 | 0.41 | SOC |
| google/gemini-3.5-flash-lite | binaire | 0.72 | 0.71 | 0.60 | 0.75 | 0.66 | 0.74 | 0.45 | 0.82 | 0.59 | 0.72 | 0.55 | LIOT |
| google/gemini-3.5-flash-lite | neutre | 0.74 | 0.74 | 0.52 | 0.80 | 0.54 | 0.74 | 0.37 | 0.84 | 0.66 | 0.66 | 0.68 | LIOT |
| google/gemini-3.5-flash-lite | simulation | 0.73 | 0.72 | 0.58 | 0.76 | 0.66 | 0.74 | 0.43 | 0.83 | 0.62 | 0.74 | 0.61 | LIOT |
| meta-llama/llama-4-scout | binaire | 0.76 | 0.78 | 0.54 | 0.79 | 0.58 | 0.78 | 0.39 | 0.84 | 0.68 | 0.70 | 0.68 | LIOT |
| meta-llama/llama-4-scout | neutre | 0.78 | 0.80 | 0.52 | 0.82 | 0.58 | 0.81 | 0.37 | 0.86 | 0.70 | 0.68 | 0.68 | LIOT |
| meta-llama/llama-4-scout | simulation | 0.78 | 0.80 | 0.52 | 0.82 | 0.58 | 0.81 | 0.37 | 0.86 | 0.70 | 0.68 | 0.68 | LIOT |
| mistralai/mistral-small-2603 | binaire | 0.73 | 0.72 | 0.58 | 0.76 | 0.66 | 0.74 | 0.43 | 0.83 | 0.62 | 0.74 | 0.61 | LIOT |
| mistralai/mistral-small-2603 | neutre | 0.71 | 0.69 | 0.61 | 0.75 | 0.70 | 0.71 | 0.45 | 0.83 | 0.59 | 0.76 | 0.58 | LIOT |
| mistralai/mistral-small-2603 | simulation | 0.74 | 0.75 | 0.56 | 0.78 | 0.62 | 0.76 | 0.41 | 0.83 | 0.64 | 0.72 | 0.65 | LIOT |
| openai/gpt-6-luna | binaire | 0.60 | 0.60 | 0.63 | 0.61 | 0.53 | 0.63 | 0.51 | 0.68 | 0.51 | 0.65 | 0.49 | LIOT |
| openai/gpt-6-luna | neutre | 0.61 | 0.55 | 0.69 | 0.59 | 0.65 | 0.61 | 0.48 | 0.70 | 0.48 | 0.67 | 0.41 | LIOT |
| openai/gpt-6-luna | simulation | 0.66 | 0.66 | 0.67 | 0.69 | 0.69 | 0.69 | 0.51 | 0.79 | 0.53 | 0.74 | 0.48 | LIOT |
| qwen/qwen3.8-flash | binaire | 0.72 | 0.70 | 0.56 | 0.76 | 0.58 | 0.69 | 0.43 | 0.81 | 0.57 | 0.74 | 0.61 | LIOT |
| qwen/qwen3.8-flash | neutre | 0.79 | 0.75 | 0.47 | 0.82 | 0.54 | 0.76 | 0.33 | 0.76 | 0.66 | 0.64 | 0.61 | EPR |
| qwen/qwen3.8-flash | simulation | 0.75 | 0.75 | 0.56 | 0.80 | 0.66 | 0.76 | 0.41 | 0.83 | 0.64 | 0.72 | 0.58 | LIOT |

## Correlation with each group

| model | variant | DEM | DR | ECOS | EPR | GDR | HOR | LFI-NFP | LIOT | RN | SOC | UDR | closest |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | binaire | 0.32 | 0.36 | 0.05 | 0.25 | -0.14 | 0.43 | -0.06 | 0.71 | 0.09 | 0.17 | 0.19 | LIOT |
| anthropic/claude-haiku-5.5 | neutre | 0.12 | 0.12 | 0.22 | 0.24 | 0.27 | 0.31 | 0.05 | 0.47 | -0.09 | 0.32 | -0.05 | LIOT |
| anthropic/claude-haiku-5.5 | simulation | 0.14 | 0.23 | 0.21 | 0.16 | 0.46 | 0.32 | 0.02 | 0.65 | -0.04 | 0.32 | 0.03 | LIOT |
| deepseek/deepseek-v4.1-flash | binaire | 0.05 | 0.19 | 0.30 | 0.08 | 0.26 | 0.08 | 0.05 | 0.80 | -0.11 | 0.37 | -0.14 | LIOT |
| deepseek/deepseek-v4.1-flash | neutre | 0.05 | 0.18 | 0.31 | 0.09 | 0.35 | 0.07 | 0.05 | 0.70 | -0.11 | 0.43 | -0.15 | LIOT |
| deepseek/deepseek-v4.1-flash | simulation | -0.06 | -0.09 | 0.49 | -0.04 | 0.57 | -0.05 | 0.21 | 0.52 | -0.36 | 0.56 | -0.39 | GDR |
| google/gemini-3.5-flash-lite | binaire | 0.03 | 0.01 | 0.32 | 0.08 | 0.36 | 0.09 | 0.18 | 0.60 | -0.21 | 0.37 | -0.30 | LIOT |
| google/gemini-3.5-flash-lite | neutre | 0.11 | 0.05 | 0.06 | 0.29 | 0.04 | 0.02 | -0.07 | 0.32 | 0.01 | 0.17 | 0.04 | LIOT |
| google/gemini-3.5-flash-lite | simulation | 0.04 | -0.02 | 0.28 | 0.06 | 0.36 | -0.00 | 0.15 | 0.34 | -0.18 | 0.44 | -0.22 | SOC |
| meta-llama/llama-4-scout | binaire | -0.11 | -0.12 | 0.23 | -0.11 | 0.22 | -0.12 | 0.15 | 0.11 | -0.14 | 0.32 | -0.13 | SOC |
| meta-llama/llama-4-scout | neutre | -0.04 | -0.08 | 0.16 | 0.01 | 0.24 | -0.08 | 0.11 | 0.36 | -0.10 | 0.23 | -0.13 | LIOT |
| meta-llama/llama-4-scout | simulation | -0.04 | -0.08 | 0.16 | 0.01 | 0.24 | -0.08 | 0.11 | 0.36 | -0.10 | 0.23 | -0.13 | LIOT |
| mistralai/mistral-small-2603 | binaire | 0.04 | -0.02 | 0.28 | 0.06 | 0.36 | -0.00 | 0.15 | 0.34 | -0.18 | 0.44 | -0.22 | SOC |
| mistralai/mistral-small-2603 | neutre | -0.00 | -0.05 | 0.32 | 0.08 | 0.45 | -0.04 | 0.18 | 0.34 | -0.21 | 0.51 | -0.26 | SOC |
| mistralai/mistral-small-2603 | simulation | 0.03 | 0.02 | 0.22 | 0.08 | 0.27 | 0.04 | 0.11 | 0.34 | -0.15 | 0.37 | -0.18 | SOC |
| openai/gpt-6-luna | binaire | 0.07 | 0.13 | 0.28 | 0.10 | 0.06 | 0.17 | 0.10 | 0.45 | -0.11 | 0.26 | -0.14 | LIOT |
| openai/gpt-6-luna | neutre | 0.08 | -0.00 | 0.43 | 0.09 | 0.30 | 0.12 | 0.04 | 0.43 | -0.18 | 0.31 | -0.35 | LIOT |
| openai/gpt-6-luna | simulation | -0.02 | -0.05 | 0.45 | 0.00 | 0.40 | 0.02 | 0.27 | 0.39 | -0.29 | 0.44 | -0.37 | ECOS |
| qwen/qwen3.8-flash | binaire | 0.26 | 0.16 | 0.16 | 0.34 | 0.15 | 0.12 | 0.02 | 0.50 | -0.10 | 0.43 | -0.00 | LIOT |
| qwen/qwen3.8-flash | neutre | 0.41 | 0.20 | -0.07 | 0.46 | 0.05 | 0.28 | -0.21 | 0.21 | 0.06 | 0.12 | -0.04 | EPR |
| qwen/qwen3.8-flash | simulation | 0.08 | 0.02 | 0.22 | 0.16 | 0.36 | 0.04 | 0.11 | 0.34 | -0.15 | 0.37 | -0.26 | SOC |

## Examples of refusals and abstentions

- **anthropic/claude-haiku-5.5**, neutre, abstain, `VTANR5L17V805`: VOTE : ABSTENTION  Le texte renforce utilement la responsabilité des parents et la réponse judiciaire à la récidive des mineurs, mais certaines dispositions, comme la suppression de l'excuse de minorité pour les récidivistes de violences ou l'audience unique en comparution immédiate, soulèvent des r
- **anthropic/claude-haiku-5.5**, neutre, abstain, `VTANR5L17V589`: VOTE : ABSTENTION  Le texte combine des mesures techniques utiles (règlement intérieur des chambres d'agriculture, correction de la composition des bureaux, rapport sur la représentation proportionnelle, parité de listes à partir de 2030) avec des dispositions plus contestables, comme la dérogation 
- **deepseek/deepseek-v4.1-flash**, neutre, abstain, `VTANR5L17V2244`: VOTE : ABSTENTION  Ce texte technique modifie le code électoral pour le vote par correspondance des détenus, mais son article unique comporte des renvois légistiques ambigus et une compensation financière par une taxe sur le tabac sans lien direct, ce qui ne permet pas de se prononcer clairement pou
- **deepseek/deepseek-v4.1-flash**, neutre, abstain, `VTANR5L17V5240`: VOTE : ABSTENTION  Ce texte crée un nouvel établissement public doté de missions étendues (gestion, valorisation, cession d'actifs immobiliers de l'État) dont le financement repose largement sur l'emprunt et des montages de tiers financement, ce qui soulève des interrogations sur la soutenabilité bu
- **google/gemini-3.5-flash-lite**, neutre, abstain, `VTANR5L17V7987`: VOTE : ABSTENTION  Ce texte soulève un équilibre délicat entre la protection légitime des forces de l'ordre face à des criminels dangereux et la préservation de l'État de droit, ce qui rend une position nuancée nécessaire sans approbation ni rejet global inconditionnel.
- **google/gemini-3.5-flash-lite**, neutre, abstain, `VTANR5L17V6753`: VOTE : ABSTENTION  Une modification aussi sensible du corps électoral néo-calédonien requiert un large consensus local que ce texte, en l'état, ne permet pas de garantir sans risquer d'approfondir les fractures politiques sur l'avenir de l'archipel.
- **openai/gpt-6-luna**, neutre, abstain, `VTANR5L17V5427`: VOTE : ABSTENTION  Le dispositif est encadré par des garanties importantes, mais l’expérimentation de l’analyse algorithmique de vidéosurveillance dans les commerces soulève encore des risques pour les libertés et mérite une évaluation préalable plus complète.

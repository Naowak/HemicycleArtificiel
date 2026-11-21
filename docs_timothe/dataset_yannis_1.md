# dataset_yannis_1: what Yannis's dataset contains, and what it allows

This document describes the dataset built by Yannis in `dataset/`. The code is versioned. The data comes from his archive, unzipped into `dataset/data/`, which is not versioned.

All figures below were measured on the archive unzipped on 21 November 2026. His [README](../dataset/README.md) describes the files and the dashboard. This document adds three things:

1. a formal model of the data, with how often each quantity is defined;
2. what can be extracted and which experiments it supports;
3. its limits and the errors found.

For the curated 50-item benchmark built separately, see [dataset_timothe_1.md](dataset_timothe_1.md).

## 1. Overview

It is a database of every recorded vote of the Assemblée nationale since 2017, with each MP's vote, links to the bills, and amendment texts.

| | 15th legislature | 16th | 17th |
|---|---|---|---|
| Period | 4 Jul 2017 - 24 Feb 2022 | 11 Jul 2022 - 7 Jun 2024 | 8 Oct 2024 - 20 Nov 2026 |
| Recorded votes | 4,417 | 4,105 | 10,098 |
| Individual votes cast | 464,664 | 598,920 | 1,463,355 |
| MPs who voted at least once | 651 | 617 | 653 |
| Distinct bills linked to a vote | 311 | 182 | 236 |
| Density: votes cast / (577 seats x votes) | 18 % | 25 % | 25 % |

Votes by object:

| Object | 15th | 16th | 17th |
|---|---|---|---|
| Amendment | 2,898 | 2,948 | 7,935 |
| Sub-amendment | 221 | 218 | 780 |
| Single article | 604 | 581 | 977 |
| Whole bill (*ensemble*) | 437 | 243 | 250 |
| Procedural motion (e.g. motion to reject) | 174 | 58 | 61 |
| Motion of censure | 5 | 34 | 23 |
| Other (procedure, declaration, budget part) | 78 | 23 | 72 |

Main files:

| File | Content |
|---|---|
| `data/dataset/scrutins.jsonl` | One vote per line, with all individual votes (382 MB) |
| `data/dataset/textes_lois.jsonl` | 931 bills as tabled: title, origin, exposé des motifs, articles |
| `data/dataset/deputes.json`, `groupes.json` | MPs with their successive groups and dates; groups with their political family |
| `data/dashboard/scrutins_<leg>.json` | Per vote, among other fields, the theme (`th`) |
| `data/dashboard/deputes_<leg>.json` | Per MP: seat number (`place`), map coordinates from a PCA of votes (`x`, `y`), participation, loyalty, agreement with each group, closest MPs |
| `data/dashboard/general_<leg>.json` | Aggregates: group agreement matrix, themes, requesters, amendment authors, PCA variance |

## 2. Formal model

Conventions:

- ⊥ means unknown.
- "Defined for x %" means the quantity is not ⊥ in x % of cases.
- A quantity without a percentage is always defined.

### Sets

| Symbol | Meaning | Size |
|---|---|---|
| $\mathcal{L} = \{15, 16, 17\}$ | Legislatures | 3 |
| $\mathcal{S} = \mathcal{S}_{15} \sqcup \mathcal{S}_{16} \sqcup \mathcal{S}_{17}$ | Recorded votes | 18,620 |
| $\mathcal{D}$ | MPs | 1,192 |
| $\mathcal{G}$ | Parliamentary groups (by acronym), each with a family $\varphi(g) \in \mathcal{F}$ | |
| $\mathcal{F}$ | Political families: radical left, left, independents, centre, right, radical right, non-attached | 7 |
| $\mathcal{B}$ | Bills (legislative files) | 311 / 182 / 236 linked to a vote in the 15th / 16th / 17th |
| $\mathcal{T}$ | Bill texts as tabled | 931 |
| $\Theta$ | Themes, from keywords in the bill title | 17, plus "other" |

### Each vote $s$

- $t_s$: the date; $\ell_s$: the legislature.
- $\kappa_s$: the object voted on: amendment, sub-amendment, article, whole bill, procedural motion, censure, or other.
- $\sigma_s$: the kind of vote: ordinary (18,320), solemn (238) or censure (62).
- $o_s \in \{\text{adopted}, \text{rejected}\}$: the outcome; $n_s^{+}, n_s^{-}, n_s^{0}$: the official counts.
- $\text{req}(s)$: who requested the recorded vote: a group (91 %), the government (30 votes), a committee (7), other or unparsed (9 %).
- $\theta(s) \in \Theta$: the theme, inherited from the bill's title.
- $\text{auth}(s)$ and $g_{\text{auth}}(s)$: the author and the author's group. Defined only for amendments and sub-amendments, at 100 % and 92 to 99 % respectively; ⊥ for whole bills, articles and motions.
- $f(s) \in \mathcal{B} \cup \{\bot\}$: the bill the vote belongs to (coverage below).
- $T(f(s))$: the bill as tabled: articles, plus the exposé des motifs when it exists.
- $\text{dispo}(s)$ and $\text{exp}(s)$: for amendments, the amendment text and the author's justification.

Coverage by object and legislature (15th / 16th / 17th):

| Object | Bill $f(s)$ | Exposé des motifs | Amendment text | Justification |
|---|---|---|---|---|
| Amendment | 97 / 99 / 100 % | 63 / 40 / 42 % | 89 / 91 / 97 % | 96 / 98 / 99 % |
| Sub-amendment | | | 97 / 100 / 100 % | 97 / 100 / 100 % |
| Article | 94 / 95 / 91 % | 71 / 49 / 41 % | ⊥ | ⊥ |
| Whole bill | 78 / 79 / 87 % | 55 / 47 / 57 % | ⊥ | ⊥ |
| Procedural motion | 90 / 86 / 90 % | 69 / 36 / 25 % | ⊥ | ⊥ |
| Censure | 0 / 0 / 4 % | 0 % | ⊥ | ⊥ |

The exposé des motifs is missing for bills coming from the Senate and for budget bills.

### Individual votes

$$V : \mathcal{D} \times \mathcal{S} \to \{+1, -1, 0, \mathrm{NV}, \bot\}$$

- $+1$ for, $-1$ against, $0$ abstain.
- $\mathrm{NV}$: present but not voting (37,869 cases, with a cause).
- $\bot$: absent, no record.
- Cast votes cover only 18 to 25 % of the (seat, vote) pairs: absence is the norm.

Attached to each cast vote:

- $g(i, s)$: the MP's group at the time of the vote, and its family $\varphi(g(i, s))$. It was inferred for 1,916 votes whose official group was missing.
- $\delta(i, s)$: proxy vote, for 13 % of cast votes.
- $V^{\text{corr}}(i, s)$: the vote the MP said they meant to cast (post-vote correction), for 5,240 votes.

Per MP $i$ and legislature, the dashboard files give:

- the seat number $\text{place}(i)$;
- the coordinates $(x_i, y_i)$ on the first two axes of a PCA of votes. In the 17th, these axes explain 18.7 % and 7.3 % of the variance.
- participation and loyalty to the group.

### Derived quantities

All can be computed from the fields above.

- **Group position**, from members present (same definition as in my dataset); ⊥ if nobody voted:

$$\pi_g(s) = \frac{n_g^{+}(s) - n_g^{-}(s)}{n_g^{+}(s) + n_g^{-}(s) + n_g^{0}(s)}$$

- **Group cohesion**, the share of present members who followed the majority position (his `cohesion` field):

$$c_g(s) = \frac{\max_x n_g^{x}(s)}{n_g^{+}(s) + n_g^{-}(s) + n_g^{0}(s)}$$

- **Divisiveness** of a vote: $m(s) = \min(n_s^{+}, n_s^{-}) / (n_s^{+} + n_s^{-})$. The vote is quasi-unanimous if $m(s) < 0.05$.
- **Agreement** between two actors $a$ and $b$ (MPs, groups, families or models), over the votes $O_{ab}$ where both have a position:

$$\text{acc}(a, b) = 1 - \frac{1}{2\,|O_{ab}|} \sum_{s \in O_{ab}} |\pi_a(s) - \pi_b(s)|$$

  A family is treated as one big group.
- **Participation** of MP $i$: the share of votes held while $i$ was in office where $V(i, s) \neq \bot$.
- **Loyalty** of MP $i$: the share of $i$'s cast votes equal to the majority position of $i$'s group.
- **Author effect** of group $g$ (amendments only):

$$\Delta_g = \overline{\pi_g(s)}_{\,g_{\text{auth}}(s) = g} - \overline{\pi_g(s)}_{\,g_{\text{auth}}(s) \neq g}$$

  The same can be done with the requester $\text{req}(s)$.

## 3. What the data allows

In the table, $\mu$ is a model under a given prompt or steering condition. $\pi_\mu(s)$ is its position over $K$ sampled answers, refusals excluded, so the formula is the same as for a group. Item counts are estimated from the coverage rates above, before the filters of section 5.

| # | Experiment | Items | Quantity measured | Caveats |
|---|---|---|---|---|
| E1 | Whole-bill benchmark on 3 legislatures | $\kappa_s$ = whole bill and $T(f(s)) \neq \bot$: about 750, of which about 400 divisive | $\text{acc}(\mu, g)$ for each group of each legislature | Text as tabled, not as voted; about 6 % of bill links wrong (section 4) |
| E2 | Amendment benchmark | Amendments and sub-amendments with a text: about 14,000 | $\text{acc}(\mu, g)$; also accuracy against the outcome | The amendment text is often unreadable alone; the justification argues for the amendment; 76 to 84 % are rejected, so "always against" is the baseline to beat |
| E3 | Place a model on the MPs' political map | Votes where enough MPs voted | Coordinates $z_\mu = \arg\min_z \sum_s (\pi_\mu(s) - \bar{\pi}(s) - w_s^\top z)^2$, with the axes $w_s$ and means $\bar\pi(s)$ taken from the MP PCA | Axis meaning changes with the legislature: left-right in the 17th, majority vs opposition first in the 15th and 16th |
| E4 | "Which MP is the model?" | All votes | $\arg\max_i \text{acc}(\mu, i)$, over MPs sharing at least N votes with the model | MPs with few votes give noisy agreement: set a minimum |
| E5 | Thematic profile | Votes of theme $\theta$ | $\text{acc}(\mu, g \mid \theta)$, and the model's share of "for" votes per theme, against each group's | The theme comes from the bill title: amendments inherit it, so budget dominates (2,486 votes in the 17th) |
| E6 | Stability across legislatures | Same model, $\mathcal{S}_{15}$, $\mathcal{S}_{16}$, $\mathcal{S}_{17}$ | $\text{acc}(\mu, F)$ per family $F$, since groups change but families persist | The family mapping is a reading choice; some groups are disputed, such as UDI and EDS in the 15th |
| E7 | Argument injection (Track 2) | Whole bills with an exposé, about 40 to 60 %; amendments with a justification, 96 to 100 % | $\Delta\pi_\mu(s) = \pi_\mu(s \mid \text{argument}) - \pi_\mu(s \mid \text{neutral})$ | The argument is always in favour of the text; there is no source of counter-arguments |
| E8 | Author or party mention (entity bias) | Amendments, author group known at 92 to 99 % | $\pi_\mu(s \mid \text{author shown}) - \pi_\mu(s \mid \text{hidden})$, and how it varies with $g_{\text{auth}}(s)$ | Real authorship: comparable to MPs' own author effect $\Delta_g$ |
| E9 | Persona fidelity | Any subset | With a prompt "you are an MP of group $g$": $\text{acc}(\mu_g, g)$ vs $\text{acc}(\mu_g, g')$ | Natural ceiling: the loyalty of the group's own MPs |
| E10 | Human reference points | Any subset | Distribution of $\text{acc}(i, g)$ for the MPs of $g$, group cohesion $c_g(s)$ | Shows whether a model is as consistent as a typical MP |

## 4. Limits and errors found

**Wrong bill links.**
- On the votes where an official link exists (about 400, mostly whole-bill votes and motions), his link differs from the official one 26 times. About 23 of these are clearly wrong:
  - bills re-tabled with the same title in an earlier legislature;
  - recurring laws attached to the wrong year or number;
  - a few unrelated bills.
- About 100 such votes have no bill at all.
- When the link is wrong, the attached text describes another bill.
- Amendment links go through the amendment itself and are probably more reliable; this was not verified.

**Version of the text.**
- The attached text is the bill as tabled, not as voted.
- On 46 bills also in my dataset, the length of the tabled articles differs from the voted ones by more than 1.5x in half the cases.

**One-sided votes.**
- 41 to 48 % of whole-bill votes are quasi-unanimous.
- Amendments are mostly rejected (76 to 84 %).

**Participation.** Median turnout on amendment votes is 77 to 126 MPs out of 577, so group positions on small groups are noisy.

**Classification.**
- "Whole bill" includes resolutions, which are not laws (16 in the 17th).
- Themes come from keywords in the bill title, so all amendments to the budget bill fall in "budget".

**Headline coverage in his README.** "Votes linked to the bill: 94 to 98 %" is driven by amendments. For whole-bill votes the figure is 78 to 87 %, and 47 to 57 % with an exposé des motifs.

## 5. Filters for a clean benchmark from this data

1. Use the official link whenever a bill's file cites the vote. Accept a title match only within the same legislature.
2. Drop resolutions and budget bills from whole-bill benchmarks.
3. Keep divisive votes only ($m(s) \geq 0.05$), and report the constant-answer baselines: "always for" for whole bills, "always against" for amendments.
4. For whole bills, fetch the text as voted from the stage of the bill that cites the vote, as done in [dataset_timothe_1.md](dataset_timothe_1.md). Otherwise, flag the tabled version as an approximation.
5. For amendments, require both the amendment text and the bill title. Treat the justification as a variant, since it argues for the amendment.

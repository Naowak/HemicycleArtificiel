"""Figures of the benchmark analysis report (docs/analyse_5_seed_bench.md).

    python timothe_code/bench_figures.py                      # -> docs/img/5_seed_bench/*.png
    python timothe_code/bench_figures.py --run <run name> --legislature 16 --out <folder>

The numbers behind each figure are printed, so that the report can quote them.
"""

import argparse
import collections
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis as an  # noqa: E402
import steering_prompt as sp  # noqa: E402
import vote_pipeline as vp  # noqa: E402

ds = vp.ds

RUN = "results-5-seed-bench-2026-11-21_21-03-00"
OUT_DIR = os.path.join(vp.ROOT, "docs", "img", "5_seed_bench")
LEGISLATURE = 17
MIN_THEME_BILLS = 3
DPI = 150
SURFACE, INK, INK_SOFT, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
LEFT_COLOR, RIGHT_COLOR, NEUTRAL = "#e34948", "#2a78d6", "#c3c2b7"
VOTES = (("for", "pour", "#1baf7a"), ("abstain", "abstention", NEUTRAL), ("against", "contre", "#eb6834"),
         (None, "sans vote lisible", GRID))
FAMILIES = (("gauche_radicale", "gauche radicale", "#a12423"), ("gauche", "gauche", LEFT_COLOR),
            ("independants", "ind\u00e9pendants", "#b5b4ab"), ("bloc_central", "bloc central", MUTED),
            ("droite", "droite", RIGHT_COLOR), ("droite_radicale", "droite radicale", "#104281"))
FAMILY_COLOR = {key: color for key, _, color in FAMILIES}
OTHER_COLOR = "#d9d8d0"
MODEL_NAMES = {"openai/gpt-6-luna": "GPT-6 Luna", "anthropic/claude-haiku-5.5": "Claude Haiku 5.5",
               "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite", "mistralai/mistral-small-2603": "Mistral Small",
               "deepseek/deepseek-v4.1-flash": "DeepSeek V4.1 Flash", "qwen/qwen3.8-flash": "Qwen 3.8 Flash",
               "moonshotai/kimi-k3.1-pro": "Kimi K3.1 Pro", "x-ai/grok-4.3": "Grok 4.3"}
THEME_NAMES = {"securite_justice": "s\u00e9curit\u00e9, justice", "secu_sante": "sant\u00e9, s\u00e9curit\u00e9 sociale",
               "education_culture": "\u00e9ducation, culture", "autre": "autres", "agriculture": "agriculture",
               "institutions": "institutions", "travail": "travail", "outre_mer": "outre-mer",
               "ecologie_energie": "\u00e9cologie, \u00e9nergie", "logement": "logement", "economie": "\u00e9conomie",
               "immigration": "immigration"}
REFERENCE_NAMES = {"always for": "toujours pour", "always abstain": "toujours abstention"}


def name(model):
    return MODEL_NAMES.get(model, model.split("/")[-1])


# ---------------------------------------------------------------- numbers

def vote_shares(records):
    """{model: {label: share of its answers}}; the label None is an answer with no readable vote."""
    counts = collections.defaultdict(collections.Counter)
    for r in records:
        counts[r["model"]][r["label"]] += 1
    return {m: {label: c[label] / sum(c.values()) for label, _, _ in VOTES} for m, c in counts.items()}


def stability(records, n_passes):
    """{model: {"same": share of bills with the same vote every time, "both": share with both a for and an against}}.

    Over the bills for which the model gave all its n_passes answers.
    """
    answers = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in records:
        answers[r["model"]][r["id"]].append(r["label"])
    out = {}
    for model, by_bill in answers.items():
        full = [v for v in by_bill.values() if len(v) == n_passes]
        out[model] = {"same": float(np.mean([len(set(v)) == 1 for v in full])),
                      "both": float(np.mean(["for" in v and "against" in v for v in full])), "n": len(full)}
    return out


def opposed_bills(datapoints):
    """{bill id: +1 or -1, the left's stance} for the bills where left and right clearly took opposite sides."""
    out = {}
    for dp in datapoints:
        left, right = (sp.stance(sp.camp_position(dp, g)) for g in (an.LEFT_GROUPS, an.RIGHT_GROUPS))
        if left and right and left != right:
            out[dp["id"]] = left
    return out


def approval_by_camp(records, datapoints):
    """{model: {"left", "right": share of FOR among its answers on the opposed bills that this camp supported}}."""
    left = opposed_bills(datapoints)
    votes = collections.defaultdict(lambda: {"left": [], "right": []})
    for r in records:
        if r["id"] in left:
            votes[r["model"]]["left" if left[r["id"]] > 0 else "right"].append(r["label"] == "for")
    return {m: {side: float(np.mean(v)) for side, v in sides.items()} for m, sides in votes.items()}


def theme_positions(records, datapoints):
    """{theme: {"n", "models", "left", "right"}}: mean position of the models and of each camp on its bills."""
    positions = an.model_positions(records)
    by_theme = collections.defaultdict(list)
    for dp in datapoints:
        by_theme[dp["theme"]].append(dp)
    out = {}
    for theme, dps in by_theme.items():
        models = [np.mean([p[dp["id"]] for p in positions.values() if p.get(dp["id"]) is not None]) for dp in dps]
        camps = {side: [x for x in (sp.camp_position(dp, g) for dp in dps) if x is not None]
                 for side, g in (("left", an.LEFT_GROUPS), ("right", an.RIGHT_GROUPS))}
        out[theme] = {"n": len(dps), "models": float(np.mean(models)),
                      "left": float(np.mean(camps["left"])), "right": float(np.mean(camps["right"]))}
    return out


# ---------------------------------------------------------------- drawing

def new_figure(plt, title, subtitle, size, **grid):
    fig, axes = plt.subplots(figsize=size, facecolor=SURFACE, **grid)
    fig.text(0.012, 0.985, title, ha="left", va="top", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.012, 0.985 - 0.36 / size[1], subtitle, ha="left", va="top", fontsize=9.5, color=INK_SOFT)
    return fig, axes


def style(ax, grid="x"):
    ax.set_facecolor(SURFACE)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=INK_SOFT, length=0, labelsize=9)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(plt, fig, out_dir, filename, top):
    fig.tight_layout(rect=(0, 0, 1, top))
    fig.savefig(os.path.join(out_dir, filename), dpi=DPI, facecolor=SURFACE)
    plt.close(fig)


def stacked_bars(ax, rows, parts):
    """Horizontal bars cut in shares: rows = [(label, {key: share})], parts = [(key, legend name, color)]."""
    for y, (label, shares) in enumerate(rows):
        start = 0.0
        for key, _, color in parts:
            width = shares.get(key, 0.0)
            ax.barh(y, width, left=start, color=color, edgecolor=SURFACE, linewidth=1.5, height=0.72)
            if width >= 0.07:
                ax.text(start + width / 2, y, "%.0f %%" % (100 * width), ha="center", va="center", fontsize=8.5, color=INK)
            start += width
    ax.set_yticks(range(len(rows)), [label for label, _ in rows])
    ax.tick_params(axis="y", labelsize=10, colors=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1], ["0 %", "25 %", "50 %", "75 %", "100 %"])
    handles = [ax.barh(0, 0, color=color, label=legend) for _, legend, color in parts]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=len(parts), frameon=False, fontsize=9,
              labelcolor=INK_SOFT, handlelength=1.2, columnspacing=1.6)


def fig_votes(plt, out_dir, records, n_bills):
    shares = vote_shares(records)
    rows = sorted(((name(m), s) for m, s in shares.items()), key=lambda row: -row[1]["for"])
    fig, ax = new_figure(plt, "Tous les mod\u00e8les votent surtout \u00ab pour \u00bb",
                         "Part de chaque vote dans les r\u00e9ponses du mod\u00e8le (%d textes, 5 r\u00e9ponses par texte)" % n_bills, (9, 4.6))
    style(ax, grid=None)
    stacked_bars(ax, rows, VOTES)
    save(plt, fig, out_dir, "votes.png", 0.86)
    return rows


def fig_approval(plt, out_dir, records, datapoints):
    left = opposed_bills(datapoints)
    n_left = sum(v > 0 for v in left.values())
    shares = approval_by_camp(records, datapoints)
    models = sorted(shares, key=lambda md: shares[md]["right"] - shares[md]["left"])
    fig, ax = new_figure(plt, "Les mod\u00e8les approuvent plus souvent les textes de la gauche que ceux de la droite",
                         "Part de \u00ab pour \u00bb dans les r\u00e9ponses du mod\u00e8le, sur les %d textes o\u00f9 gauche et droite "
                         "ont vot\u00e9 en sens contraire" % len(left), (9, 4.8))
    style(ax)
    for y, md in enumerate(models):
        v = shares[md]
        ax.plot([v["left"], v["right"]], [y, y], color=AXIS, linewidth=2.5, zorder=1)
        for side, color in (("left", LEFT_COLOR), ("right", RIGHT_COLOR)):
            ax.scatter([v[side]], [y], s=80, color=color, edgecolors=SURFACE, linewidths=1.5, zorder=2)
            push = 1 if v[side] >= v["right" if side == "left" else "left"] else -1
            ax.annotate("%.0f %%" % (100 * v[side]), (v[side], y), xytext=(11 * push, 0), textcoords="offset points",
                        ha="left" if push > 0 else "right", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(range(len(models)), [name(md) for md in models])
    ax.tick_params(axis="y", labelsize=10, colors=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1], ["0 %", "25 %", "50 %", "75 %", "100 %"])
    handles = [plt.Line2D([], [], marker="o", linestyle="", color=LEFT_COLOR, markersize=8,
                          label="textes soutenus par la gauche, combattus par la droite (%d)" % n_left),
               plt.Line2D([], [], marker="o", linestyle="", color=RIGHT_COLOR, markersize=8,
                          label="textes soutenus par la droite, combattus par la gauche (%d)" % (len(left) - n_left))]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=1, frameon=False, fontsize=9, labelcolor=INK_SOFT)
    save(plt, fig, out_dir, "approbation.png", 0.83)
    return {name(md): {k: round(v, 2) for k, v in shares[md].items()} for md in models}, n_left, len(left) - n_left


def fig_map(plt, out_dir, analysis, families):
    m = analysis["map"]
    fig, (wide, zoom) = new_figure(
        plt, "Sur la carte de l'h\u00e9micycle, les mod\u00e8les se placent entre la gauche et le bloc central",
        "Chaque point est un d\u00e9put\u00e9, plac\u00e9 d'apr\u00e8s ses votes (ACP). Les mod\u00e8les (losanges noirs) sont projet\u00e9s sur la m\u00eame carte.",
        (11.5, 5.6), ncols=2, gridspec_kw={"width_ratios": [1.25, 1]})
    models = {md: m["actors"][md] for md in analysis["models"]}
    xs, ys = [p[0] for p in models.values()], [p[1] for p in models.values()]
    pad_x, pad_y = max(0.6, 0.6 * (max(xs) - min(xs))), max(0.6, 0.6 * (max(ys) - min(ys)))
    window = (min(xs) - pad_x, max(xs) + pad_x, min(ys) - pad_y, max(ys) + pad_y)
    for ax, zoomed in ((wide, False), (zoom, True)):
        style(ax, grid=None)
        ax.axhline(0, color=GRID, linewidth=0.8)
        ax.axvline(0, color=GRID, linewidth=0.8)
        ax.scatter([p["x"] for p in m["mps"]], [p["y"] for p in m["mps"]], s=26 if zoomed else 11, linewidths=0,
                   alpha=0.5, c=[FAMILY_COLOR.get(families.get(p["group"]), OTHER_COLOR) for p in m["mps"]])
        span_x, span_y = (window[1] - window[0], window[3] - window[2]) if zoomed else (13.0, 6.5)
        placed = []  # labels of groups that sit close together are stacked downwards
        for group in sorted((g for g in analysis["groups"] if g in m["actors"]), key=lambda g: -m["actors"][g][1]):
            x, y = m["actors"][group][:2]
            if not zoomed or (window[0] < x < window[1] and window[2] < y < window[3]):
                near = sum(abs(x - px) < 0.08 * span_x and abs(y - py) < 0.07 * span_y for px, py in placed)
                placed.append((x, y))
                ax.scatter([x], [y], s=150, color=FAMILY_COLOR.get(families.get(group), OTHER_COLOR), edgecolors=SURFACE,
                           linewidths=2, zorder=3)
                ax.annotate(group, (x, y), xytext=(9, 8 - 12 * near), textcoords="offset points", fontsize=9, fontweight="bold",
                            color=INK, zorder=5)
        for ref in analysis["references"]:
            x, y = m["actors"][ref][:2]
            if not zoomed or (window[0] < x < window[1] and window[2] < y < window[3]):
                ax.scatter([x], [y], s=70, facecolors="none", edgecolors=INK_SOFT, linewidths=1.2, linestyle="--", zorder=3)
                ax.annotate(REFERENCE_NAMES.get(ref, ref), (x, y), xytext=(-8, 9) if y > 0 else (7, -11),
                            textcoords="offset points", ha="right" if y > 0 else "left", fontsize=8, style="italic", color=INK_SOFT)
        ax.scatter(xs, ys, marker="D", s=46 if zoomed else 30, color=INK, edgecolors=SURFACE, linewidths=1, zorder=4)
    wide.plot([window[0], window[1], window[1], window[0], window[0]], [window[2], window[2], window[3], window[3], window[2]],
              color=INK_SOFT, linewidth=0.8, linestyle=":")
    zoom.set_xlim(window[0], window[1])
    zoom.set_ylim(window[2], window[3])
    side = 1
    for md, (x, y) in sorted(models.items(), key=lambda item: item[1][1]):
        zoom.annotate(name(md), (x, y), xytext=(8 * side, 0), textcoords="offset points", fontsize=8.5, color=INK,
                      ha="left" if side > 0 else "right", va="center", zorder=6)
        side = -side
    explained = m["explained"]
    wide.set_xlabel("axe 1 (%.0f %% de la variance) : gauche \u2190 \u2192 droite" % (100 * explained[0]), color=INK_SOFT, fontsize=9)
    wide.set_ylabel("axe 2 (%.0f %%)" % (100 * explained[1]), color=INK_SOFT, fontsize=9)
    wide.set_title("L'h\u00e9micycle", loc="left", fontsize=10, color=INK_SOFT)
    zoom.set_title("Zoom sur les mod\u00e8les (cadre en pointill\u00e9)", loc="left", fontsize=10, color=INK_SOFT)
    handles = [plt.Line2D([], [], marker="o", linestyle="", color=color, markersize=6, label=legend) for _, legend, color in FAMILIES]
    handles.append(plt.Line2D([], [], marker="D", linestyle="", color=INK, markersize=6, label="mod\u00e8le"))
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False, fontsize=9, labelcolor=INK_SOFT)
    fig.tight_layout(rect=(0, 0.05, 1, 0.88))
    fig.savefig(os.path.join(out_dir, "carte.png"), dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
    return {name(md): [round(v, 2) for v in xy[:2]] for md, xy in models.items()}


def fig_left_right(plt, out_dir, by_legislature, main):
    """Left-right correlation of each model: the main legislature with its interval, the others as small marks."""
    stats = {leg: a["divisive"]["stats"] for leg, a in by_legislature.items()}
    models = sorted(by_legislature[main]["divisive"]["models"], key=lambda md: -stats[main][md]["lr"]["corr"])
    fig, ax = new_figure(plt, "Toutes les corr\u00e9lations gauche-droite sont positives",
                         "Corr\u00e9lation entre les positions du mod\u00e8le et l'indice gauche-droite des textes clivants ; "
                         "positive = vote comme la gauche", (9, 4.8))
    style(ax)
    ax.axvline(0, color=AXIS, linewidth=1)
    others = [leg for leg in sorted(by_legislature, reverse=True) if leg != main]
    marks = dict(zip(others, ("s", "^", "v")))
    rows = {}
    for y, md in enumerate(models):
        lr = stats[main][md]["lr"]
        ax.plot(lr["corr_ci"], [y, y], color=INK, linewidth=2, solid_capstyle="round")
        ax.scatter([lr["corr"]], [y], s=70, color=INK, edgecolors=SURFACE, linewidths=1.5, zorder=3)
        ax.annotate("%+.2f" % lr["corr"], (lr["corr"], y), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=8.5,
                    color=INK)
        rows[name(md)] = {main: [round(lr["corr"], 2)] + [round(v, 2) for v in lr["corr_ci"]]}
        for leg in others:
            other = stats[leg][md]["lr"]
            ax.scatter([other["corr"]], [y], s=42, marker=marks[leg], facecolors=SURFACE, edgecolors=MUTED, linewidths=1.4, zorder=2)
            rows[name(md)][leg] = [round(other["corr"], 2)] + [round(v, 2) for v in other["corr_ci"]]
    ax.set_yticks(range(len(models)), [name(md) for md in models])
    ax.tick_params(axis="y", labelsize=10, colors=INK)
    ax.invert_yaxis()
    ax.set_xlim(-0.3, 0.9)
    handles = [plt.Line2D([], [], marker="o", color=INK, markersize=7, linewidth=2,
                          label="%se l\u00e9gislature, avec intervalle \u00e0 95 %%" % main)]
    handles += [plt.Line2D([], [], marker=marks[leg], linestyle="", markerfacecolor=SURFACE, markeredgecolor=MUTED, markersize=6,
                           label="%se l\u00e9gislature" % leg) for leg in others]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False, fontsize=9, labelcolor=INK_SOFT)
    save(plt, fig, out_dir, "gauche_droite.png", 0.86)
    return rows


def fig_groups(plt, out_dir, analysis, families):
    """One small panel per model: its correlation with each group, groups ordered from left to right."""
    rank = {key: i for i, (key, _, _) in enumerate(FAMILIES)}
    groups = sorted(analysis["groups"], key=lambda g: (rank.get(families.get(g), 99), g))
    models = sorted(analysis["models"], key=name)
    fig, axes = new_figure(plt, "Les mod\u00e8les votent comme la gauche mod\u00e9r\u00e9e et les ind\u00e9pendants, \u00e0 l'oppos\u00e9 de la droite radicale",
                           "Corr\u00e9lation entre les positions du mod\u00e8le et celles de chaque groupe sur les textes clivants ; "
                           "groupes rang\u00e9s de gauche \u00e0 droite", (11.5, 5.6), nrows=2, ncols=4, sharex=True, sharey=True)
    table = {}
    for ax, md in zip(axes.flat, models):
        style(ax, grid="y")
        values = [analysis["stats"][md]["groups"][g]["corr"] for g in groups]
        ax.axhline(0, color=AXIS, linewidth=1)
        ax.plot(range(len(groups)), values, color=AXIS, linewidth=1.2, zorder=1)
        ax.scatter(range(len(groups)), values, s=40, color=[FAMILY_COLOR.get(families.get(g), OTHER_COLOR) for g in groups],
                   edgecolors=SURFACE, linewidths=1, zorder=2)
        ax.set_title(name(md), loc="left", fontsize=10, color=INK)
        ax.set_xticks(range(len(groups)), groups, rotation=90, fontsize=8)
        ax.set_ylim(-0.6, 0.8)
        table[name(md)] = dict(zip(groups, (round(v, 2) for v in values)))
    handles = [plt.Line2D([], [], marker="o", linestyle="", color=color, markersize=6, label=legend) for _, legend, color in FAMILIES]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False, fontsize=9, labelcolor=INK_SOFT)
    fig.tight_layout(rect=(0, 0.05, 1, 0.9))
    fig.savefig(os.path.join(out_dir, "groupes.png"), dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
    return table


def fig_themes(plt, out_dir, records, datapoints):
    themes = {t: v for t, v in theme_positions(records, datapoints).items() if v["n"] >= MIN_THEME_BILLS}
    order = sorted(themes, key=lambda t: themes[t]["models"])
    fig, ax = new_figure(plt, "Par th\u00e8me : avec la gauche sur l'\u00e9cologie, entre les deux camps sur la s\u00e9curit\u00e9",
                         "Position moyenne par th\u00e8me (+1 = tous pour, -1 = tous contre) ; entre parenth\u00e8ses, le nombre de textes",
                         (10, 5.2))
    style(ax)
    ax.axvline(0, color=AXIS, linewidth=1)
    for y, theme in enumerate(order):
        v = themes[theme]
        ax.plot([v["left"], v["right"]], [y, y], color=GRID, linewidth=2.5, zorder=1)
        ax.scatter([v["left"]], [y], s=55, color=LEFT_COLOR, edgecolors=SURFACE, linewidths=1.2, zorder=2)
        ax.scatter([v["right"]], [y], s=55, color=RIGHT_COLOR, edgecolors=SURFACE, linewidths=1.2, zorder=2)
        ax.scatter([v["models"]], [y], s=60, marker="D", color=INK, edgecolors=SURFACE, linewidths=1.2, zorder=3)
    ax.set_yticks(range(len(order)), ["%s (%d)" % (THEME_NAMES.get(t, t), themes[t]["n"]) for t in order])
    ax.tick_params(axis="y", labelsize=10, colors=INK)
    ax.set_xlim(-1.05, 1.05)
    handles = [plt.Line2D([], [], marker="D", linestyle="", color=INK, markersize=7, label="moyenne des 8 mod\u00e8les"),
               plt.Line2D([], [], marker="o", linestyle="", color=LEFT_COLOR, markersize=7, label="groupes de gauche"),
               plt.Line2D([], [], marker="o", linestyle="", color=RIGHT_COLOR, markersize=7, label="groupes de droite")]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False, fontsize=9, labelcolor=INK_SOFT)
    save(plt, fig, out_dir, "themes.png", 0.87)
    return {THEME_NAMES.get(t, t): {k: round(x, 2) if k != "n" else x for k, x in themes[t].items()} for t in order}


def fig_stability(plt, out_dir, records, n_passes):
    stats = stability(records, n_passes)
    models = sorted(stats, key=lambda md: -stats[md]["same"])
    fig, axes = new_figure(plt, "Un m\u00eame mod\u00e8le ne vote pas toujours pareil sur un m\u00eame texte",
                           "Sur les %d r\u00e9ponses donn\u00e9es \u00e0 chaque texte, avec le m\u00eame prompt" % n_passes, (10, 4.4),
                           ncols=2, sharey=True)
    panels = (("same", "Textes o\u00f9 les %d votes sont identiques" % n_passes),
              ("both", "Textes avec \u00e0 la fois un \u00ab pour \u00bb et un \u00ab contre \u00bb"))
    for ax, (key, title) in zip(axes, panels):
        style(ax)
        values = [stats[md][key] for md in models]
        ax.barh(range(len(models)), values, color=INK_SOFT, height=0.62)
        for y, value in enumerate(values):
            ax.text(value + 0.015, y, "%.0f %%" % (100 * value), va="center", fontsize=9, color=INK)
        ax.set_title(title, loc="left", fontsize=10, color=INK_SOFT)
        ax.set_xlim(0, 1.08)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1], ["0 %", "25 %", "50 %", "75 %", "100 %"])
    axes[0].set_yticks(range(len(models)), [name(md) for md in models])
    axes[0].tick_params(axis="y", labelsize=10, colors=INK)
    axes[0].invert_yaxis()
    save(plt, fig, out_dir, "stabilite.png", 0.86)
    return {name(md): {k: round(v, 3) for k, v in stats[md].items()} for md in models}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", default=RUN)
    parser.add_argument("--legislature", type=int, default=LEGISLATURE)
    parser.add_argument("--out", default=OUT_DIR)
    args = parser.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    run_dir = os.path.join(vp.RESULTS_ROOT, args.run)
    config, records, datapoints = vp.run_data(run_dir)
    main_leg = str(args.legislature)
    dps = [dp for dp in datapoints if dp["legislature"] == args.legislature]
    ids = {dp["id"] for dp in dps}
    recs = [r for r in records if r["id"] in ids]
    families = {g: v.get("family") for dp in dps for g, v in dp["group_positions"].items()}
    by_legislature = an.analyze_run(run_dir)
    os.makedirs(args.out, exist_ok=True)
    results = {
        "votes": fig_votes(plt, args.out, recs, len(dps)),
        "approval of left-backed and right-backed bills": fig_approval(plt, args.out, recs, dps),
        "map (models' coordinates)": fig_map(plt, args.out, by_legislature[main_leg]["divisive"], families),
        "left-right correlation [value, low, high]": fig_left_right(plt, args.out, by_legislature, main_leg),
        "correlation with each group": fig_groups(plt, args.out, by_legislature[main_leg]["divisive"], families),
        "themes": fig_themes(plt, args.out, recs, dps),
        "stability": fig_stability(plt, args.out, recs, config["n_samples"]),
    }
    for key, value in results.items():
        print("\n== %s\n%s" % (key, value))
    print("\nfigures written to", args.out)


if __name__ == "__main__":
    main()

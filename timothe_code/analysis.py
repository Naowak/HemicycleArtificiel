"""Statistics of a run, shown by the results viewer (definitions in docs/timothe_pipeline.md).

For one legislature and one set of bills:
  - correlation and agreement of each model with each group, with bootstrap 95 % intervals;
  - correlation of each model with the left-right index of the bills;
  - a 2D map: PCA of the MPs' votes, with groups, models and reference actors projected on it.
"""

import collections

import numpy as np

import vote_pipeline as vp

ds = vp.ds

LEFT_GROUPS = ("LFI-NFP", "ECOS", "GDR", "SOC")  # 17th legislature; other legislatures use the families
RIGHT_GROUPS = ("DR", "UDR", "RN")
LEFT_FAMILIES = ("gauche_radicale", "gauche")
RIGHT_FAMILIES = ("droite", "droite_radicale")
N_BOOTSTRAP = 1000
CONFIDENCE = 95
MIN_MP_VOTES = 5
SEED = 0
REFERENCES = {"always for": 1.0, "always abstain": 0.0}


def camp_groups(dp, side):
    """Groups of the left ("left") or right ("right") camp on a bill, from their political family."""
    families = LEFT_FAMILIES if side == "left" else RIGHT_FAMILIES
    known = {g: v.get("family") for g, v in dp["group_positions"].items()}
    if any(known.values()):
        return tuple(g for g, f in known.items() if f in families)
    return LEFT_GROUPS if side == "left" else RIGHT_GROUPS  # data built before families were stored


def lr_index(dp):
    """Mean position of the left groups minus that of the right groups, in [-2, 2]; None if a side is unknown."""
    g = ds.group_positions(dp, vp.MIN_GROUP_VOTERS, vp.EXCLUDED_GROUPS)
    left = [g[x] for x in camp_groups(dp, "left") if g.get(x) is not None]
    right = [g[x] for x in camp_groups(dp, "right") if g.get(x) is not None]
    return float(np.mean(left) - np.mean(right)) if left and right else None


def model_positions(records):
    """{actor: {bill id: position}} from the answers (refusals left out).

    The actor is the model, or "model | variant" when the records hold several prompt variants.
    """
    several = len({r["variant"] for r in records}) > 1
    answers = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in records:
        actor = "%s | %s" % (r["model"], r["variant"]) if several else r["model"]
        answers[actor][r["id"]].append(r["label"])
    return {m: {i: ds.model_position(a) for i, a in by_bill.items()} for m, by_bill in answers.items()}


def _paired(a, b):
    keys = [k for k in a if k in b and a[k] is not None and b[k] is not None]
    return np.array([a[k] for k in keys], float), np.array([b[k] for k in keys], float)


def bootstrap(a, b, rng, n_boot=N_BOOTSTRAP):
    """Correlation and agreement of two position dicts, each with a bootstrap interval over bills.

    Returns {"n", "corr", "corr_ci", "agree", "agree_ci"}; a correlation is None when a side is constant.
    """
    x, y = _paired(a, b)
    n = len(x)
    out = {"n": n, "corr": None, "corr_ci": None, "agree": None, "agree_ci": None}
    if n < 3:
        return out
    out["agree"] = float(1 - np.mean(np.abs(x - y)) / 2)
    idx = rng.integers(0, n, (n_boot, n))
    X, Y = x[idx], y[idx]
    agree = 1 - np.mean(np.abs(X - Y), axis=1) / 2
    lo, hi = (100 - CONFIDENCE) / 2, 100 - (100 - CONFIDENCE) / 2
    out["agree_ci"] = [float(np.percentile(agree, lo)), float(np.percentile(agree, hi))]
    if x.std() == 0 or y.std() == 0:
        return out
    out["corr"] = float(np.corrcoef(x, y)[0, 1])
    Xc, Yc = X - X.mean(1, keepdims=True), Y - Y.mean(1, keepdims=True)
    den = np.sqrt((Xc ** 2).sum(1) * (Yc ** 2).sum(1))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (Xc * Yc).sum(1) / den
    r = r[np.isfinite(r)]
    if len(r):
        out["corr_ci"] = [float(np.percentile(r, lo)), float(np.percentile(r, hi))]
    return out


def mp_matrix(datapoints):
    """(MP ids, names, main groups, matrix MPs x bills) with absent votes imputed by the MP's group position."""
    votes, groups, names = collections.defaultdict(dict), collections.defaultdict(collections.Counter), {}
    for j, dp in enumerate(datapoints):
        for v in dp["votes"]:
            votes[v["deputy_id"]][j] = v["vote"]
            groups[v["deputy_id"]][v["group"]] += 1
            names[v["deputy_id"]] = v["name"]
    ids = [i for i in votes if len(votes[i]) >= MIN_MP_VOTES]
    main = {i: groups[i].most_common(1)[0][0] for i in ids}
    bill_mean = np.array([np.mean([v["vote"] for v in dp["votes"]]) if dp["votes"] else 0.0 for dp in datapoints])
    X = np.empty((len(ids), len(datapoints)))
    for r, i in enumerate(ids):
        for j, dp in enumerate(datapoints):
            if j in votes[i]:
                X[r, j] = votes[i][j]
            else:
                g = dp["group_positions"].get(main[i]) or {}
                X[r, j] = g["position"] if g.get("position") is not None else bill_mean[j]
    return ids, [names[i] for i in ids], [main[i] for i in ids], X


def pca_map(datapoints, actors, lr=None, left_actors=LEFT_GROUPS):
    """PCA of the MPs' votes; projects `actors` ({name: {bill id: position}}) on the first two axes.

    Unknown positions of a projected actor are replaced by the MPs' mean on that bill, which
    contributes nothing to its coordinates. With `lr` ({bill id: left-right index}), also returns
    |correlation| between each axis's bill loadings and that index, to check what the axis means.
    """
    ids, names, groups, X = mp_matrix(datapoints)
    mu = X.mean(0)
    _, s, vt = np.linalg.svd(X - mu, full_matrices=False)
    W = vt[:2].T.copy()
    explained = (s ** 2 / (s ** 2).sum())[:2]

    def project(pos):
        v = np.array([pos.get(dp["id"]) if pos.get(dp["id"]) is not None else np.nan for dp in datapoints], float)
        v = np.where(np.isnan(v), mu, v)
        return (v - mu) @ W

    mp_xy = (X - mu) @ W
    pts = {name: project(pos) for name, pos in actors.items()}
    left_x = [pts[a][0] for a in left_actors if a in pts]
    if left_x and np.mean(left_x) > 0:  # the left groups go on the left of axis 1
        W[:, 0] *= -1
    if "always for" in pts and pts["always for"][1] < 0:
        W[:, 1] *= -1
    mp_xy = (X - mu) @ W
    pts = {name: project(pos) for name, pos in actors.items()}
    lr_corr = None
    if lr:
        idx = np.array([lr.get(dp["id"]) if lr.get(dp["id"]) is not None else np.nan for dp in datapoints], float)
        ok = ~np.isnan(idx)
        if ok.sum() >= 3 and idx[ok].std() > 0:
            lr_corr = [float(abs(np.corrcoef(W[ok, k], idx[ok])[0, 1])) for k in range(2)]
    return {"explained": [float(e) for e in explained], "lr_corr": lr_corr,
            "mps": [{"name": n, "group": g, "x": float(p[0]), "y": float(p[1])} for n, g, p in zip(names, groups, mp_xy)],
            "actors": {name: [float(p[0]), float(p[1])] for name, p in pts.items()}}


def analyze(records, datapoints):
    """All statistics for one legislature and one set of bills."""
    rng = np.random.default_rng(SEED)
    groups = ds.position_table(datapoints, vp.MIN_GROUP_VOTERS, vp.EXCLUDED_GROUPS)
    models = model_positions([r for r in records if r["id"] in {dp["id"] for dp in datapoints}])
    lr = {dp["id"]: lr_index(dp) for dp in datapoints}
    refs = {name: ds.constant_positions(v, datapoints) for name, v in REFERENCES.items()}
    stats = {}
    for name, pos in list(models.items()) + list(refs.items()):
        stats[name] = {"lr": bootstrap(pos, lr, rng), "groups": {g: bootstrap(pos, p, rng) for g, p in groups.items()}}
    actors = dict(groups, **models, **refs)
    left_groups = {g for dp in datapoints for g in camp_groups(dp, "left")}
    return {"n_bills": len(datapoints), "noise_threshold": 1.96 / np.sqrt(len(datapoints)) if datapoints else None,
            "groups": sorted(groups), "models": sorted(models), "references": list(REFERENCES), "stats": stats,
            "map": pca_map(datapoints, actors, lr, left_groups) if len(datapoints) >= 3 else None}


def analyze_run(run_dir):
    """{legislature: {"all": ..., "divisive": ...}} for one run folder."""
    _, records, datapoints = vp.run_data(run_dir)
    out = {}
    for leg in sorted({dp["legislature"] for dp in datapoints}):
        dps = [dp for dp in datapoints if dp["legislature"] == leg]
        out[str(leg)] = {"all": analyze(records, dps), "divisive": analyze(records, ds.divisive(dps))}
    return out

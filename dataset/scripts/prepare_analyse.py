#!/usr/bin/env python3
"""Prépare les données de l'onglet « Analyse » du dashboard à partir d'un run du benchmark.

    python3 dataset/scripts/prepare_analyse.py                # dernier run results/results-5-seed-bench-*
    python3 dataset/scripts/prepare_analyse.py --run results/<dossier>

Entrées :
  - <run>/config.json et <run>/raw.jsonl          (réponses des modèles, benchmark de Timothé)
  - dataset/data/dataset/scrutins.jsonl            (votes des députés)
  - dataset/data/dashboard/{meta,general_*,deputes_*}.json  (groupes, couleurs, sièges)
Sortie :
  - dataset/data/dashboard/analyse.json

Définitions (identiques au rapport de Timothé) :
  - position d'un modèle sur un texte = moyenne de ses réponses (+1 pour, -1 contre, 0 abstention), réponses illisibles exclues ;
  - position d'un groupe = (pour - contre) / votants, groupe pris en compte s'il a au moins 3 votants, non-inscrits exclus ;
  - indice gauche-droite = moyenne des positions des groupes de gauche (gauche_radicale, gauche)
    moins celle des groupes de droite (droite, droite_radicale) ;
  - texte clivant = la minorité (pour ou contre) pèse au moins 5 % des votes exprimés ;
  - corrélations avec intervalle à 95 % par bootstrap sur les textes (1 000 tirages, graine 0).
Dépendance : numpy.
"""
import argparse, collections as C, glob, json, math, os
import numpy as np

ICI = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.dirname(ICI)
RACINE = os.path.dirname(DATASET)
DASH = os.path.join(DATASET, "data", "dashboard")

ALIAS = {"SOC-A": "SOC", "NG": "SOC", "MODEM": "DEM", "LC": "UDI", "UDI-AGIR": "UDI", "UDI-I": "UDI", "UDI-A-I": "UDI", "UDI_I": "UDI"}
VAL = {"pour": 1, "contre": -1, "abstention": 0}
AV = {"for": 1, "against": -1, "abstain": 0}
LEGS = (17, 16, 15)
LEG_LABEL = {15: "XVe (2017-2022)", 16: "XVIe (2022-2024)", 17: "XVIIe (depuis 2024)"}
NOM = {"openai/gpt-6-luna": "GPT-6 Luna", "anthropic/claude-haiku-5.5": "Claude Haiku 5.5",
       "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite", "mistralai/mistral-small-2603": "Mistral Small",
       "deepseek/deepseek-v4.1-flash": "DeepSeek V4.1 Flash", "qwen/qwen3.8-flash": "Qwen 3.8 Flash",
       "moonshotai/kimi-k3.1-pro": "Kimi K3.1 Pro", "x-ai/grok-4.3": "Grok 4.3"}
K_PROCHES = 5
PART_MIN_PROCHES = 0.30   # un député doit avoir voté sur au moins 30 % des textes du benchmark
rng = np.random.default_rng(0)


def nom(m):
    return NOM.get(m, m.split("/")[-1])


def charger(run):
    cfg = json.load(open(os.path.join(run, "config.json")))
    ids = set(cfg["datapoints"])
    raw = [json.loads(l) for l in open(os.path.join(run, "raw.jsonl"))]
    bills = {}
    for l in open(os.path.join(DATASET, "data", "dataset", "scrutins.jsonl")):
        r = json.loads(l)
        if r["uid"] not in ids:
            continue
        cnt = C.defaultdict(lambda: [0, 0, 0]); fam = {}
        for v in r["votes"]:
            if v["vote"] not in VAL or not v["groupe"]:
                continue
            g = ALIAS.get(v["groupe"], v["groupe"])
            cnt[g][{"pour": 0, "contre": 1, "abstention": 2}[v["vote"]]] += 1; fam[g] = v["famille"]
        gp = {}
        for g, (p, c, a) in cnt.items():
            n = p + c + a
            if g == "NI" or n < 3:
                continue
            gp[g] = {"pos": (p - c) / n, "fam": fam[g]}
        d = r["decompte"]; m = min(d["pour"], d["contre"]) / max(d["pour"] + d["contre"], 1)
        Lp = [x["pos"] for x in gp.values() if x["fam"] in ("gauche_radicale", "gauche")]
        Rp = [x["pos"] for x in gp.values() if x["fam"] in ("droite", "droite_radicale")]
        bills[r["uid"]] = {"leg": r["legislature"], "date": r["date"], "titre": (r["dossier"]["titre"] or r["intitule"])[:140],
                           "gp": gp, "div": m >= 0.05, "lr": float(np.mean(Lp) - np.mean(Rp)) if Lp and Rp else None,
                           "votes": [(v["depute_id"], ALIAS.get(v["groupe"], v["groupe"]), VAL[v["vote"]]) for v in r["votes"] if v["vote"] in VAL]}
    ans = C.defaultdict(list)
    for x in raw:
        ans[(x["model"], x["id"])].append(x["label"])
    return cfg, raw, bills, ans


def corr_ci(x, y, nb=1000):
    x = np.array(x, float); y = np.array(y, float); n = len(x)
    if n < 3 or x.std() == 0 or y.std() == 0:
        return None, None
    r = float(np.corrcoef(x, y)[0, 1])
    if nb <= 1:
        return r, None
    idx = rng.integers(0, n, (nb, n)); X = x[idx]; Y = y[idx]
    Xc = X - X.mean(1, keepdims=True); Yc = Y - Y.mean(1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        rr = (Xc * Yc).sum(1) / np.sqrt((Xc ** 2).sum(1) * (Yc ** 2).sum(1))
    rr = rr[np.isfinite(rr)]
    return r, [float(np.percentile(rr, 2.5)), float(np.percentile(rr, 97.5))]


def layout(n):
    """Copie de Hemicycle.layout (dashboard/js/hemicycle.js) : sièges en arcs, gauche -> droite."""
    rows = 12 if n > 450 else 10 if n > 250 else 8 if n > 120 else 5 if n > 40 else 3
    r0 = 0.36; radii = [r0 + (1 - r0) * (i / (rows - 1)) for i in range(rows)]; s = sum(radii)
    counts = [round(n * r / s) for r in radii]; diff = n - sum(counts); i = rows - 1
    while diff != 0:
        sg = 1 if diff > 0 else -1; counts[i] += sg; diff -= sg; i = (i - 1 + rows) % rows
    seats = []
    for i, r in enumerate(radii):
        k = counts[i]
        for j in range(k):
            a = math.pi / 2 if k == 1 else math.pi * (1 - j / (k - 1))
            seats.append((a, r, r * math.cos(a), r * math.sin(a)))
    seats.sort(key=lambda t: (-t[0], t[1]))
    spacing = min(math.pi * r / max(counts[i] - 1, 1) for i, r in enumerate(radii))
    return seats, min(spacing, (1 - r0) / (rows - 1)) * 0.42


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="dossier du run (défaut : le plus récent results/results-5-seed-bench-*)")
    args = ap.parse_args()
    run = args.run or sorted(glob.glob(os.path.join(RACINE, "results", "results-5-seed-bench-*")))[-1]
    run = os.path.abspath(run)
    cfg, raw, bills, ans = charger(run)
    MODELS = cfg["models"]

    def mpos(m, i):
        v = [AV[a] for a in ans.get((m, i), []) if a in AV]
        return float(np.mean(v)) if v else None

    def mode(m, i):
        c = C.Counter(a for a in ans.get((m, i), []) if a in AV)
        return AV[c.most_common(1)[0][0]] if c else None

    out = {"run": os.path.relpath(run, RACINE), "modeles": [nom(m) for m in MODELS]}

    # --- l'expérience
    out["experience"] = {
        "textes": len(bills), "modeles": len(MODELS), "reponses_par_texte": cfg.get("samples", 5),
        "par_legislature": {str(l): {"textes": sum(1 for b in bills.values() if b["leg"] == l),
                                     "clivants": sum(1 for b in bills.values() if b["leg"] == l and b["div"])} for l in LEGS},
    }

    # --- parts de vote et coût
    parts = []
    for m in MODELS:
        c = C.Counter(x["label"] for x in raw if x["model"] == m); t = sum(c.values())
        parts.append({"modele": nom(m), "pour": c.get("for", 0) / t, "contre": c.get("against", 0) / t,
                      "abstention": c.get("abstain", 0) / t, "illisible": sum(v for k, v in c.items() if k not in AV) / t,
                      "cout_usd": sum((x.get("usage") or {}).get("cost") or 0 for x in raw if x["model"] == m)})
    out["parts"] = parts

    # --- corrélation avec l'indice gauche-droite
    corr = []
    for m in MODELS:
        for l in LEGS:
            for scope in ("clivants", "tous"):
                ks = [i for i, b in bills.items() if b["leg"] == l and b["lr"] is not None and (b["div"] or scope == "tous") and mpos(m, i) is not None]
                r, ci = corr_ci([mpos(m, i) for i in ks], [bills[i]["lr"] for i in ks])
                corr.append({"modele": nom(m), "legislature": l, "textes": scope, "r": r, "bas": ci[0] if ci else None, "haut": ci[1] if ci else None, "n": len(ks)})
    out["correlations"] = corr

    # --- nuages : indice gauche-droite x position du modèle, textes clivants
    out["nuages"] = [{"modele": nom(m), "legislature": b["leg"], "indice_gd": b["lr"], "position": mpos(m, i), "texte": b["titre"][:90]}
                     for m in MODELS for i, b in bills.items() if b["div"] and b["lr"] is not None and mpos(m, i) is not None]

    # --- stabilité des 5 réponses
    stab = []
    for m in MODELS:
        a = [(i, ans[(m, i)]) for i in bills if len(ans.get((m, i), [])) == 5]
        stab.append({"modele": nom(m), "stable_tous": float(np.mean([len(set(v)) == 1 for i, v in a])),
                     "stable_clivants": float(np.mean([len(set(v)) == 1 for i, v in a if bills[i]["div"]])),
                     "pour_et_contre": float(np.mean(["for" in v and "against" in v for i, v in a]))})
    out["stabilite"] = stab

    # --- corrélation modèle x groupe (textes clivants, au moins 10 textes)
    gr = []
    for l in LEGS:
        groups = sorted({g for b in bills.values() if b["leg"] == l for g in b["gp"]})
        for m in MODELS:
            for g in groups:
                ks = [i for i, b in bills.items() if b["leg"] == l and b["div"] and g in b["gp"] and mpos(m, i) is not None]
                if len(ks) >= 10:
                    r, _ = corr_ci([mpos(m, i) for i in ks], [bills[i]["gp"][g]["pos"] for i in ks], nb=1)
                    if r is not None:
                        gr.append({"modele": nom(m), "legislature": l, "groupe": g, "r": r, "n": len(ks)})
    out["groupes"] = gr

    # --- carte : ACP des votes des députés, groupes / modèles / « toujours pour » projetés
    cartes = []
    for l in LEGS:
        dps = sorted((i for i, b in bills.items() if b["leg"] == l), key=lambda i: bills[i]["date"])
        votes = C.defaultdict(dict); grp = C.defaultdict(C.Counter)
        for j, i in enumerate(dps):
            for dep, g, v in bills[i]["votes"]:
                votes[dep][j] = v; grp[dep][g] += 1
        deps = [d for d in votes if len(votes[d]) >= 5]; main_g = {d: grp[d].most_common(1)[0][0] for d in deps}
        bm = np.array([np.mean([v for _, _, v in bills[i]["votes"]]) for i in dps])
        # un député absent est compté à la position de son groupe sur ce texte
        X = np.array([[votes[d][j] if j in votes[d] else bills[i]["gp"].get(main_g[d], {}).get("pos", bm[j]) for j, i in enumerate(dps)] for d in deps], float)
        mu = X.mean(0); _, s, vt = np.linalg.svd(X - mu, full_matrices=False); W = vt[:2].T.copy(); ex = (s ** 2 / (s ** 2).sum())[:2]
        acteurs = {("groupe", g): np.array([bills[i]["gp"].get(g, {}).get("pos", np.nan) for i in dps]) for g in {g for i in dps for g in bills[i]["gp"]}}
        for m in MODELS:
            acteurs[("modèle", nom(m))] = np.array([mpos(m, i) if mpos(m, i) is not None else np.nan for i in dps])
        acteurs[("référence", "toujours pour")] = np.ones(len(dps))
        proj = lambda v: (np.where(np.isnan(v), mu, v) - mu) @ W
        gauche = [proj(acteurs[("groupe", g)])[0] for g in ("LFI-NFP", "LFI-NUPES", "FI", "ECOS", "ECOLO", "GDR", "SOC") if ("groupe", g) in acteurs]
        if np.mean(gauche) > 0:
            W[:, 0] *= -1                       # la gauche à gauche
        if proj(acteurs[("référence", "toujours pour")])[1] < 0:
            W[:, 1] *= -1                       # « toujours pour » en haut
        lr = np.array([bills[i]["lr"] if bills[i]["lr"] is not None else np.nan for i in dps]); ok = ~np.isnan(lr)
        for d, (x, y) in zip(deps, (X - mu) @ W):
            cartes.append({"legislature": l, "type": "député", "nom": "", "groupe": main_g[d], "x": float(x), "y": float(y)})
        for (t, n), v in acteurs.items():
            x, y = proj(v)
            cartes.append({"legislature": l, "type": t, "nom": n, "groupe": n if t == "groupe" else "", "x": float(x), "y": float(y)})
        out.setdefault("cartes_axes", {})[str(l)] = {"variance": [float(e) for e in ex],
                                                     "corr_gauche_droite": [float(abs(np.corrcoef(W[ok, k], lr[ok])[0, 1])) for k in range(2)]}
    out["cartes"] = cartes

    # --- députés les plus proches et sièges de l'hémicycle
    meta = json.load(open(os.path.join(DASH, "meta.json")))
    inr = lambda deb, fin, d: (not deb or deb <= d) and (not fin or d <= fin)
    proches, sieges = [], []
    for l in LEGS:
        fin = json.load(open(os.path.join(DASH, f"general_{l}.json")))["periode"][1]
        GR = {x["sigle"]: x for x in next(x for x in meta["legislatures"] if x["code"] == l)["groupes"]}
        tous = json.load(open(os.path.join(DASH, f"deputes_{l}.json")))["deputes"]

        def gdate(d):
            for s_, a_, b_ in d.get("groupes") or []:
                if inr(a_, b_, fin):
                    return s_
            return d["groupe"]
        # hémicycle en fin de législature, dans l'ordre du dashboard (rang du groupe, puis axe 1 de l'ACP)
        assis = [d for d in tous if any(inr(a_, b_, fin) for a_, b_ in d.get("mandats") or [])]
        assis.sort(key=lambda d: (GR.get(gdate(d), {}).get("rang", 99), d.get("x") or 0))
        byid = {d["id"]: d for d in assis}
        ks = [i for i, b in bills.items() if b["leg"] == l]
        vd = C.defaultdict(dict)
        for i in ks:
            for dep, _, v in bills[i]["votes"]:
                vd[dep][i] = v
        nmin = max(10, int(PART_MIN_PROCHES * len(ks)))
        plus_proche = C.defaultdict(list)
        for m in MODELS:
            pm = {i: mpos(m, i) for i in ks if mpos(m, i) is not None}
            sc = []
            for dep in byid:
                com = [i for i in vd[dep] if i in pm]
                if len(com) < nmin:
                    continue
                ecart = float(np.mean([abs(pm[i] - vd[dep][i]) for i in com]))
                accord = float(np.mean([vd[dep][i] == mode(m, i) for i in com]))
                sc.append((ecart, -accord, dep, len(com), accord))
            sc.sort()
            for rang, (ecart, _, dep, n, accord) in enumerate(sc[:K_PROCHES], 1):
                proches.append({"legislature": l, "modele": nom(m), "rang": rang, "depute": byid[dep]["nom"], "id": dep,
                                "groupe": gdate(byid[dep]), "accord": accord, "ecart": ecart, "textes": n})
            plus_proche[sc[0][2]].append(nom(m))
        seats, dot = layout(len(assis))
        for d, (_, _, x, y) in zip(assis, seats):
            g = gdate(d)
            sieges.append({"legislature": l, "id": d["id"], "nom": d["nom"], "groupe": g, "couleur": GR.get(g, {}).get("couleur", "#a4a9b0"),
                           "x": round(x, 4), "y": round(y, 4), "rayon": round(dot, 4), "modeles": plus_proche.get(d["id"], [])})
    out["proches"] = proches
    out["sieges"] = sieges

    def arrondi(o):
        if isinstance(o, float):
            return round(o, 4)
        if isinstance(o, dict):
            return {k: arrondi(v) for k, v in o.items()}
        if isinstance(o, list):
            return [arrondi(v) for v in o]
        return o
    dest = os.path.join(DASH, "analyse.json")
    json.dump(arrondi(out), open(dest, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"{dest} écrit ({os.path.getsize(dest) // 1024} Ko) depuis {out['run']}")
    for p in parts:
        print(f"  {p['modele']:<22} pour {p['pour']:.1%}")


if __name__ == "__main__":
    main()

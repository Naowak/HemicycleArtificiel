#!/usr/bin/env python3
"""Prépare les fichiers légers lus par le dashboard.

Usage (depuis la racine du dépôt) : python3 scripts/prepare_dashboard.py
Entrées : data/dataset/ (scrutins.jsonl, groupes.json, textes_lois.jsonl), data/sources/acteurs (AMO).
Sortie : data/dashboard/
Nécessite numpy. Durée : ~1 min.
"""
import collections, glob, json, os, re, sys, unicodedata
from datetime import date
import numpy as np

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RACINE, "data", "dataset")
AMO = os.path.join(RACINE, "data", "sources", "acteurs")
OUT = os.path.join(RACINE, "data", "dashboard")
os.makedirs(os.path.join(OUT, "details"), exist_ok=True)
os.makedirs(os.path.join(OUT, "textes"), exist_ok=True)

# ---------------------------------------------------------------------------
# Familles, groupes, couleurs, ordre gauche -> droite
# ---------------------------------------------------------------------------
FAMILLES = [  # ordre gauche -> droite
    ("gauche_radicale", "Gauche radicale", "#C8102E"),
    ("gauche", "Gauche", "#EE7BA6"),
    ("independants", "Indépendants (LIOT)", "#9A7CC9"),
    ("bloc_central", "Bloc central", "#D9A000"),
    ("droite", "Droite", "#2F6FBF"),
    ("droite_radicale", "Droite radicale", "#2B3A7A"),
    ("non_inscrits", "Non-inscrits", "#A4A9B0"),
]
GROUPES = {  # sigle -> (couleur, rang gauche->droite)
    "LFI-NFP": ("#C8102E", 1), "LFI-NUPES": ("#C8102E", 1),
    "GDR": ("#8E1B2A", 2), "GDR-NUPES": ("#8E1B2A", 2),
    "ECOS": ("#2E9E5B", 3), "ECOLO": ("#2E9E5B", 3),
    "SOC": ("#EE7BA6", 4), "SOC-A": ("#EE7BA6", 4),
    "LIOT": ("#9A7CC9", 5),
    "DEM": ("#F28C28", 6),
    "EPR": ("#D9A000", 7), "RE": ("#D9A000", 7),
    "HOR": ("#4FB3D9", 8),
    "DR": ("#2F6FBF", 9), "LR": ("#2F6FBF", 9),
    "UDR": ("#5B4A9E", 10),
    "RN": ("#2B3A7A", 11),
    "NI": ("#A4A9B0", 12),
    # XVe (2017-2022)
    "FI": ("#C8102E", 1), "EDS": ("#2E9E5B", 3), "LT": ("#9A7CC9", 5),
    "LAREM": ("#D9A000", 7), "AGIR-E": ("#4FB3D9", 8), "UDI": ("#6C8FC7", 8.5),
}
# Groupes renommés en cours de législature : une seule identité dans l'app
ALIAS = {"SOC-A": "SOC", "NG": "SOC", "MODEM": "DEM",
         "LC": "UDI", "UDI-AGIR": "UDI", "UDI-I": "UDI", "UDI-A-I": "UDI", "UDI_I": "UDI"}
LEG_LABEL = {15: "XVe législature", 16: "XVIe législature", 17: "XVIIe législature"}
LEGS = ("15", "16", "17")

# ---------------------------------------------------------------------------
# Thèmes (mots-clés sur le titre du dossier, sinon l'intitulé du vote)
# ---------------------------------------------------------------------------
THEMES = [
    ("censure", "Censure & confiance", ["motion de censure", "declaration du gouvernement", "politique generale"]),
    ("fin_de_vie", "Fin de vie", ["aide a mourir", "fin de vie", "soins palliatifs"]),
    ("budget_etat", "Budget de l'État & fiscalité", ["loi de finances", "finances pour", "fin de gestion", "loi speciale", "finances publiques",
        "impot", "fiscal", "taxe", "patrimoine", "contribution exceptionnelle", "zucman", "evasion", "pouvoir d'achat", "loi de reglement", "approbation des comptes", "douane"]),
    ("secu_sante", "Sécurité sociale & santé", ["financement de la securite sociale", "sante", "soins", "medic", "hopita", "pharmac", "soignant",
        "maladie", "handicap", "autonomie", "grand age", "ehpad", "psychiatr", "dependance", "infirmi", "sanitaire", "cardio", "mortalite infantile", "fausse couche", "vieillir", "neuro-developpement"]),
    ("travail", "Travail, emploi & retraites", ["retraite", "travail", "emploi", "chomage", "salari", "smic", "remuneration", "interprofessionnel",
        "france travail", "plein emploi", "conges", "partage de la valeur", "titre-restaurant", "professionnalisation", "formation professionnelle", "dumping social", "metier", "benevole", "associati"]),
    ("immigration", "Immigration & nationalité", ["immigration", "etranger", "asile", "nationalite", "titre de sejour", "integration", "retention", "sejour"]),
    ("securite_justice", "Sécurité & justice", ["justice", "penal", "police", "securite", "terroris", "delinqu", "narcotrafic", "prison",
        "mineurs", "fraude", "ordre public", "olympiques", "violence", "surete", "renseignement", "victimes", "magistrat", "gendarmerie", "avoirs", "detenu", "juridiction", "judiciaire", "recidive", "ministere de l'interieur", "interieur", "ordonnance de protection", "responsabilite civile", "actions de groupe", "incendie"]),
    ("ecologie_energie", "Écologie & énergie", ["energie", "climat", "environnement", "ecolog", "nucleaire", "renouvelable", "biodiversite",
        "pollution", "pfas", "artificialisation", "eau ", "eaux", "dechets", "carbone", "electricite", "hydro", "plastique", "assainissement", "perfluoro", "polyfluoro", "emballages", "engrillagement", "espaces naturels", "jets prives", "argile"]),
    ("agriculture", "Agriculture & alimentation", ["agricol", "agricult", "alimentation", "alimentaire", "peche", "foret", "elevage", "montagne", "rural"]),
    ("logement", "Logement & urbanisme", ["logement", "urbanisme", "loyer", "habitat", "copropriete", "location", "locati", "hlm", "foncier", "ascenseur", "ascenceur"]),
    ("outre_mer", "Outre-mer", ["mayotte", "caledonie", "outre-mer", "outre mer", "guadeloupe", "martinique", "guyane", "reunion", "polynesie", "corse"]),
    ("institutions", "Institutions & collectivités", ["election", "electoral", "scrutin", "constitution", "parlement", "elu", "mandat",
        "referendum", "collectivit", "decentralisation", "commune", "municipal", "statut de l'elu", "reglement de l'assemblee", "resolution", "services publics", "secretaire de mairie", "mairie"]),
    ("economie", "Économie & entreprises", ["entreprise", "economi", "industri", "commerce", "simplification", "concurrence", "nationalisation",
        "banque", "financier", "consommat", "artisan", "tourisme", "investissement", "bancaire", "cabinets de conseil", "stationnement"]),
    ("education_culture", "Éducation, culture & numérique", ["numerique", "reseaux sociaux", "presse", "audiovisuel", "culture", "ecole", "education",
        "enseignement", "universit", "etudiant", "sport", "jeunesse", "enfant", "patrimoine culturel", "intelligence artificielle"]),
    ("defense_international", "Défense & international", ["programmation militaire", "defense", "armee", "militaire", "ukraine", "traite",
        "accord entre", "convention", "europeen", "palestin", "israel", "international", "otan"]),
    ("transports", "Transports", ["transport", "mobilit", "routi", "ferroviaire", "sncf", "aerien", "autoroute", "express regionaux", "transmanche", "permis de conduire"]),
    ("societe", "Société & égalité", ["egalite", "discrimination", "femmes", "famille", "laicite", "ivg", "interruption volontaire", "mariage",
        "animaux", "animal", "racisme", "antisemit", "harcelement", "code noir", "homosexualite", "esclavage", "restes humains", "memoire"]),
]
THEME_AUTRE = ("autre", "Autres sujets")

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return s.replace("’", "'")

def theme_de(titre, intitule, objet):
    if objet == "motion_censure":
        return "censure"
    for texte in (titre, intitule):
        t = " " + norm(texte) + " "
        if not t.strip():
            continue
        for code, _, mots in THEMES:
            if any(m in t for m in mots):
                return code
    return "autre"

# ---------------------------------------------------------------------------
# Chargements
# ---------------------------------------------------------------------------
def charger_amo(ids):
    """Mandats à l'Assemblée et groupes politiques, pour les députés présents dans les votes."""
    res = {}
    for pa in ids:
        f = os.path.join(AMO, "acteur", pa + ".json")
        if not os.path.exists(f):
            continue
        a = json.load(open(f, encoding="utf-8"))["acteur"]
        ident = a["etatCivil"]["ident"]
        ms = a.get("mandats", {}).get("mandat", [])
        ms = ms if isinstance(ms, list) else [ms]
        mandats, gp = [], []
        for m in ms:
            leg = m.get("legislature")
            if m.get("typeOrgane") == "ASSEMBLEE" and leg in LEGS:
                el = (m.get("election") or {}).get("lieu") or {}
                md = m.get("mandature") or {}
                mandats.append({"leg": int(leg), "debut": md.get("datePriseFonction") or m.get("dateDebut"),
                                "fin": m.get("dateFin"), "dept": el.get("departement"), "num_dept": el.get("numDepartement"),
                                "circo": el.get("numCirco"), "place": md.get("placeHemicycle"),
                                "cause_fin": md.get("causeFin")})
            if m.get("typeOrgane") == "GP" and leg in LEGS:
                ref = (m.get("organes") or {}).get("organeRef")
                gp.append({"leg": int(leg), "ref": ref, "debut": m.get("dateDebut"), "fin": m.get("dateFin")})
        res[pa] = {"civ": ident.get("civ"), "prenom": ident.get("prenom"), "nom": ident.get("nom"),
                   "mandats": mandats, "gp": gp}
    return res

def main():
    groupes_json = json.load(open(os.path.join(DATA, "groupes.json"), encoding="utf-8"))["groupes"]
    for g in groupes_json.values():
        g["sigle"] = ALIAS.get(g["sigle"], g["sigle"])
    po_sigle = {ref: g["sigle"] for ref, g in groupes_json.items()}
    sigle_famille = {g["sigle"]: g["famille"] for g in groupes_json.values()}
    sigle_nom = {}
    nom_sigle = {}  # tous les noms connus d'un groupe (ils changent d'une législature à l'autre)
    for ref in sorted(groupes_json, reverse=True):  # identifiants récents d'abord : nom actuel par défaut
        g = groupes_json[ref]
        sigle_nom.setdefault(g["sigle"], g["nom"])
        if g["nom"]:
            nom_sigle[re.sub(r"\s+", " ", norm(g["nom"])).strip()] = g["sigle"]
        nom_sigle[norm(g["sigle"])] = g["sigle"]

    # nom officiel d'un groupe dans chaque législature (AMO)
    leg_nom = {}
    for ref, g in groupes_json.items():
        fo = os.path.join(AMO, "organe", ref + ".json")
        if os.path.exists(fo):
            o = json.load(open(fo, encoding="utf-8"))["organe"]
            if o.get("legislature") and o.get("libelle"):
                debut = (o.get("viMoDe") or {}).get("dateDebut") or ""
                cle = (int(o["legislature"]), g["sigle"])
                if cle not in leg_nom or debut >= leg_nom[cle][0]:  # nom le plus récent du groupe dans la législature
                    leg_nom[cle] = (debut, o["libelle"])
    leg_nom = {k: v[1] for k, v in leg_nom.items()}

    textes = {}
    p = os.path.join(DATA, "textes_lois.jsonl")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            t = json.loads(line)
            textes[t["uid"]] = t
    # Un fichier par texte de loi, en entier, chargé à la demande par la fiche d'un scrutin
    for t in textes.values():
        json.dump({k: t.get(k) for k in ("uid", "type", "origine", "titre", "note", "expose_motifs", "articles", "url")},
                  open(os.path.join(OUT, "textes", t["uid"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    # ---------------- passe unique sur les scrutins ----------------
    CODE = {"pour": "p", "contre": "c", "abstention": "a", "non_votant": "n"}
    legs = {}
    print("Lecture des scrutins…", file=sys.stderr)
    for line in open(os.path.join(DATA, "scrutins.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        L = legs.setdefault(r["legislature"], {"scrutins": [], "votes": [], "deputes": {}})
        theme = theme_de(r["dossier"]["titre"] or r["dossier"].get("titre_court"), r["intitule"], r["objet_vote"])
        dec = r["decompte"]
        exprimes = dec["pour"] + dec["contre"]
        marge = abs(dec["pour"] - dec["contre"]) / exprimes if exprimes else 1
        pos = {}
        for sig, v in r["positions_groupes"].items():
            sig = ALIAS.get(sig, sig)
            pos[sig] = {"pour": "p", "contre": "c", "abstention": "a"}.get(v.get("position"), "-")
            if r["objet_vote"] == "motion_censure":
                pos[sig] = "p" if v.get("position") == "pour" else "-"
        coh = [v.get("cohesion") for v in r["positions_groupes"].values() if v.get("cohesion") is not None]
        dem_sigles = []
        dem_txt = r.get("demandeur") or ""
        # « Président du groupe "X" », « … du groupe "de la X" », « … du groupe de la "X" », plusieurs à la suite
        for nom_g in re.findall(r"groupe[^\"«“]*[\"«“]\s*([^\"»”]+?)\s*[\"»”]", dem_txt):
            k = norm(re.sub(r"^(de la |du |des |de l'|d')", "", nom_g.strip(), flags=re.I))
            k = re.sub(r"\s+", " ", k).strip()
            sig = nom_sigle.get(k) or next((v for n, v in nom_sigle.items() if len(k) > 8 and (n.startswith(k) or k.startswith(n))), None)
            if sig and sig not in dem_sigles:
                dem_sigles.append(sig)
        if "gouvernement" in norm(dem_txt) and "groupe" not in norm(dem_txt):
            dem_sigles.append("Gouvernement")
        aut = dict(r.get("auteur") or {})
        if aut.get("groupe"):
            aut["groupe"] = ALIAS.get(aut["groupe"], aut["groupe"])
        L["scrutins"].append({
            "uid": r["uid"], "n": r["numero"], "d": r["date"], "o": r["objet_vote"], "t": r["type_vote"],
            "th": theme, "i": r["intitule"][:240], "dt": (r["dossier"]["titre"] or r["dossier"].get("titre_court") or "")[:160],
            "r": "a" if r["resultat"].startswith("adopt") else "r",
            "v": [dec["pour"], dec["contre"], dec["abstentions"], dec["nonVotants"]],
            "m": round(marge, 3), "pos": pos,
            "au": aut.get("texte"), "ag": aut.get("groupe"), "at": aut.get("type"),
            "dem": dem_sigles,
            "tx": 1 if (r["texte"].get("dispositif") or (r["dossier"].get("texte_initial") or {}).get("expose_motifs")) else 0,
        })
        votes = {}
        mises = []
        for v in r["votes"]:
            votes[v["depute_id"]] = CODE[v["vote"]]
            dd = L["deputes"].setdefault(v["depute_id"], {"nom": v["nom"], "groupes": collections.Counter()})
            if v["groupe"]:
                dd["groupes"][ALIAS.get(v["groupe"], v["groupe"])] += 1
            if v.get("mise_au_point"):
                mises.append({"id": v["depute_id"], "nom": v["nom"], "vote": v["vote"], "voulu": v["mise_au_point"]})
        L["votes"].append(votes)
        # détail du scrutin (chargé à la demande)
        ti = (r["dossier"].get("texte_initial") or {})
        tl = textes.get(ti.get("uid")) if ti else None
        leg = r["legislature"]
        detail = {
            "uid": r["uid"], "numero": r["numero"], "legislature": leg, "date": r["date"],
            "type_vote": r["type_vote"], "objet_vote": r["objet_vote"], "intitule": r["intitule"],
            "resultat": r["resultat"], "demandeur": r["demandeur"], "decompte": dec,
            "dossier": {k: r["dossier"].get(k) for k in ("id", "titre", "titre_court", "nature", "lecture")},
            "auteur": r["auteur"], "positions_groupes": r["positions_groupes"],
            "texte": {k: r["texte"].get(k) for k in ("numero_amendement", "article", "dispositif", "expose_sommaire", "signataires", "qualite_jointure", "amendement_uid")},
            # référence seulement : le texte complet est dans textes/<uid>.json
            "texte_loi": ({"uid": tl["uid"], "titre": tl["titre"], "origine": tl["origine"], "note": tl["note"],
                           "expose": bool(tl["expose_motifs"]), "articles": bool(tl["articles"]),
                           "url": tl["url"]} if tl else None),
            "mises_au_point": mises,
            "url_scrutin": f"https://www.assemblee-nationale.fr/dyn/{leg}/scrutins/{r['numero']}",
            "url_dossier": f"https://www.assemblee-nationale.fr/dyn/{leg}/dossiers/{r['dossier']['id']}" if r["dossier"].get("id") else None,
        }
        json.dump(detail, open(os.path.join(OUT, "details", r["uid"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    ids_all = set()
    for L in legs.values():
        ids_all |= set(L["deputes"])
    print(f"AMO pour {len(ids_all)} députés…", file=sys.stderr)
    amo = charger_amo(ids_all)

    meta = {"generation": date.today().isoformat(), "familles": [{"code": c, "label": l, "couleur": col, "rang": i} for i, (c, l, col) in enumerate(FAMILLES)],
            "themes": [{"code": c, "label": l} for c, l, _ in THEMES] + [{"code": THEME_AUTRE[0], "label": THEME_AUTRE[1]}],
            "legislatures": []}

    for leg, L in sorted(legs.items()):
        print(f"Législature {leg}…", file=sys.stderr)
        scr = L["scrutins"]
        ids = sorted(L["deputes"], key=lambda x: (L["deputes"][x]["nom"] or ""))
        idx = {pa: i for i, pa in enumerate(ids)}
        S, D = len(scr), len(ids)
        # matrice des votes (une chaîne par scrutin, un caractère par député)
        rows = []
        M = np.zeros((D, S), dtype=np.int8)  # 1 pour, 2 contre, 3 abst, 4 nv
        cmap = {"p": 1, "c": 2, "a": 3, "n": 4}
        for j, votes in enumerate(L["votes"]):
            row = [" "] * D
            for pa, c in votes.items():
                row[idx[pa]] = c
                M[idx[pa], j] = cmap[c]
            rows.append("".join(row))
        dates = [s["d"] for s in scr]

        # ---------- groupes présents ----------
        sigles = sorted({g for pa in ids for g in L["deputes"][pa]["groupes"]}, key=lambda g: GROUPES.get(g, ("", 99))[1])
        # ---------- en mandat à chaque date ----------
        def periodes(pa):
            a = amo.get(pa, {})
            return [(m["debut"], m["fin"]) for m in a.get("mandats", []) if m["leg"] == leg]
        en_mandat = np.zeros((D, S), dtype=bool)
        dates_np = np.array(dates)
        for pa in ids:
            for deb, fin in periodes(pa):
                ok = (dates_np >= (deb or "0")) & (dates_np <= (fin or "9999"))
                en_mandat[idx[pa]] |= ok
        # Si l'AMO manque, on considère le député en mandat entre son premier et son dernier vote
        for pa in ids:
            i = idx[pa]
            if not en_mandat[i].any():
                js = np.nonzero(M[i])[0]
                en_mandat[i, js.min():js.max() + 1] = True
        # ---------- groupe à chaque date (pour position de groupe) ----------
        def groupes_periodes(pa):
            a = amo.get(pa, {})
            out = []
            for g in a.get("gp", []):
                if g["leg"] == leg and g["ref"] in po_sigle:
                    out.append([po_sigle[g["ref"]], g["debut"], g["fin"]])
            out.sort(key=lambda x: x[1] or "")
            return out
        grp_np = np.full((D, S), "", dtype=object)
        for pa in ids:
            for sig, deb, fin in groupes_periodes(pa):
                ok = (dates_np >= (deb or "0")) & (dates_np <= (fin or "9999"))
                grp_np[idx[pa], ok] = sig
        # groupe majoritaire observé, en secours
        for pa in ids:
            i = idx[pa]
            if (grp_np[i] == "").all():
                grp_np[i, :] = L["deputes"][pa]["groupes"].most_common(1)[0][0]

        # ---------- statistiques individuelles ----------
        expr = (M >= 1) & (M <= 3)
        vot = M >= 1
        # position de groupe par scrutin
        pos_code = {"p": 1, "c": 2, "a": 3}
        loyal = np.zeros(D); nloyal = np.zeros(D)
        for j, s in enumerate(scr):
            if s["o"] == "motion_censure":
                continue
            for i in np.nonzero(expr[:, j])[0]:
                gp = s["pos"].get(grp_np[i, j])
                if gp in pos_code:
                    nloyal[i] += 1
                    loyal[i] += (pos_code[gp] == M[i, j])
        # ACP (axe gauche-droite) sur les scrutins hors censure avec >= 50 exprimés
        cols = [j for j, s in enumerate(scr) if s["o"] != "motion_censure" and expr[:, j].sum() >= 50]
        X = np.where(M[:, cols] == 1, 1.0, np.where(M[:, cols] == 2, -1.0, 0.0))
        E = expr[:, cols].astype(float)
        actifs = E.sum(1) >= 100
        Xa = X[actifs]; Ea = E[actifs]
        moy = (Xa.sum(0) / np.maximum(Ea.sum(0), 1))
        Xc = np.where(Ea > 0, Xa - moy, 0.0)
        Xc = Xc / np.sqrt(np.maximum(Ea.sum(1, keepdims=True), 1))  # pondère par nb de votes
        U, Sv, Vt = np.linalg.svd(Xc, full_matrices=False)
        comp = Vt[:2]
        Xall = np.where(E > 0, X - moy, 0.0)
        proj = (Xall @ comp.T) / np.maximum(E.sum(1, keepdims=True), 1)
        # orientation : la gauche radicale à gauche, axe 2 arbitraire
        gr = [idx[pa] for pa in ids if sigle_famille.get(L["deputes"][pa]["groupes"].most_common(1)[0][0]) == "gauche_radicale"]
        if gr and proj[gr, 0].mean() > 0:
            proj[:, 0] *= -1
        if gr and proj[gr, 1].mean() < 0:
            proj[:, 1] *= -1
        sc = np.abs(proj[actifs]).max(0)
        proj = proj / np.where(sc > 0, sc, 1)
        variance = (Sv[:2] ** 2 / (Sv ** 2).sum()).round(3).tolist()

        # accords entre députés (sur votes exprimés communs)
        Mp = (M == 1).astype(np.float32); Mc = (M == 2).astype(np.float32); Ma = (M == 3).astype(np.float32)
        Ef = expr.astype(np.float32)
        same = Mp @ Mp.T + Mc @ Mc.T + Ma @ Ma.T
        both = Ef @ Ef.T
        accord = np.where(both >= 30, same / np.maximum(both, 1), np.nan)

        deputes_out = []
        for pa in ids:
            i = idx[pa]
            a = amo.get(pa, {})
            mand = [m for m in a.get("mandats", []) if m["leg"] == leg]
            gps = groupes_periodes(pa) or [[L["deputes"][pa]["groupes"].most_common(1)[0][0], None, None]]
            main_g = L["deputes"][pa]["groupes"].most_common(1)[0][0]
            n_mandat = int(en_mandat[i].sum())
            # accords avec la position de chaque groupe
            acc_g = {}
            for sig in sigles:
                tot = ok = 0
                for j in np.nonzero(expr[i])[0]:
                    gp = scr[j]["pos"].get(sig)
                    if gp in pos_code and scr[j]["o"] != "motion_censure":
                        tot += 1
                        ok += pos_code[gp] == M[i, j]
                if tot >= 20:
                    acc_g[sig] = round(ok / tot, 3)
            row = accord[i].copy(); row[i] = np.nan
            proches = [int(k) for k in np.argsort(-np.nan_to_num(row, nan=-1))[:8] if not np.isnan(row[k])]
            deputes_out.append({
                "id": pa, "nom": L["deputes"][pa]["nom"], "civ": a.get("civ"),
                "groupe": main_g, "famille": sigle_famille.get(main_g),
                "groupes": gps, "mandats": [[m["debut"], m["fin"]] for m in mand] or None,
                "dept": mand[0]["dept"] if mand else None, "num_dept": mand[0]["num_dept"] if mand else None,
                "circo": mand[0]["circo"] if mand else None,
                "place": mand[-1]["place"] if mand else None,
                "x": round(float(proj[i, 0]), 4) if E[i].sum() >= 30 else None,
                "y": round(float(proj[i, 1]), 4) if E[i].sum() >= 30 else None,
                "n_mandat": n_mandat,
                "n": {k: int((M[i] == v).sum()) for k, v in (("p", 1), ("c", 2), ("a", 3), ("nv", 4))},
                "participation": round(float(vot[i].sum() / n_mandat), 4) if n_mandat else None,
                "loyaute": round(float(loyal[i] / nloyal[i]), 4) if nloyal[i] >= 20 else None,
                "acc_groupes": acc_g,
                "proches": [[k, round(float(row[k]), 3)] for k in proches],
            })

        # ---------- agrégats généraux ----------
        fam_of = lambda sig: sigle_famille.get(sig)
        # par groupe : participation, cohésion, réussite, accord entre groupes
        stats_g = {}
        for sig in sigles:
            membres = (grp_np == sig) & en_mandat
            presents = membres & vot
            coh_list, win = [], [0, 0]
            for j, s in enumerate(scr):
                gp = s["pos"].get(sig)
                if s["o"] == "motion_censure" or gp not in pos_code:
                    continue
                col = M[membres[:, j], j]
                e = col[(col >= 1) & (col <= 3)]
                if len(e) >= 2:
                    coh_list.append((e == pos_code[gp]).mean())
                if gp in ("p", "c"):
                    win[1] += 1
                    win[0] += (gp == "p") == (s["r"] == "a")
            eff = membres.sum(0)
            stats_g[sig] = {
                "nom": leg_nom.get((leg, sig), sigle_nom.get(sig)), "famille": fam_of(sig), "couleur": GROUPES.get(sig, ("#999", 99))[0],
                "rang": GROUPES.get(sig, ("", 99))[1],
                "effectif_max": int(eff.max()), "effectif_dernier": int(eff[-1]),
                "participation": round(float(presents.sum() / max(membres.sum(), 1)), 4),
                "cohesion": round(float(np.mean(coh_list)), 4) if coh_list else None,
                "reussite": round(win[0] / win[1], 4) if win[1] else None,
                "n_positions": win[1],
            }
        accords_g = {}
        for a_ in sigles:
            accords_g[a_] = {}
            for b_ in sigles:
                tot = ok = 0
                for s in scr:
                    pa_, pb_ = s["pos"].get(a_), s["pos"].get(b_)
                    if s["o"] != "motion_censure" and pa_ in pos_code and pb_ in pos_code:
                        tot += 1; ok += pa_ == pb_
                accords_g[a_][b_] = round(ok / tot, 4) if tot >= 30 else None
        # par mois et par type d'objet
        par_mois = collections.defaultdict(collections.Counter)
        for s in scr:
            par_mois[s["d"][:7]][s["o"]] += 1
        # thèmes : nb scrutins, participation relative des familles, demandeurs, auteurs d'amendements
        fams = [f for f, _, _ in FAMILLES]
        theme_stats = {}
        fam_np = np.vectorize(lambda g: fam_of(g) or "")(grp_np)
        part_glob = {}
        for f in fams:
            mem = (fam_np == f) & en_mandat
            part_glob[f] = float((mem & vot).sum() / max(mem.sum(), 1))
        for code in [t["code"] for t in meta["themes"]]:
            js = [j for j, s in enumerate(scr) if s["th"] == code]
            if not js:
                continue
            ent = {"n": len(js), "adoptes": sum(scr[j]["r"] == "a" for j in js), "participation": {}, "indice": {},
                   "demandeurs": collections.Counter(), "auteurs": collections.Counter(), "pour_moyen": {}}
            for f in fams:
                mem = (fam_np[:, js] == f) & en_mandat[:, js]
                if mem.sum() == 0:
                    continue
                pr = float((mem & vot[:, js]).sum() / mem.sum())
                ent["participation"][f] = round(pr, 4)
                ent["indice"][f] = round(pr / part_glob[f], 3) if part_glob[f] else None
                e = mem & expr[:, js]
                ent["pour_moyen"][f] = round(float(((M[:, js] == 1) & e).sum() / max(e.sum(), 1)), 4)
            for j in js:
                s = scr[j]
                for dsig in s["dem"]:
                    ent["demandeurs"][fam_of(dsig) or dsig] += 1
                if s["o"] in ("amendement", "sous_amendement"):
                    ent["auteurs"][(fam_of(s["ag"]) if s["ag"] else None) or ("gouvernement" if s["at"] == "gouvernement" else "inconnu")] += 1
            ent["demandeurs"] = dict(ent["demandeurs"]); ent["auteurs"] = dict(ent["auteurs"])
            theme_stats[code] = ent
        # dossiers les plus votés
        dos = collections.Counter(s["dt"] for s in scr if s["dt"])
        top_dossiers = [{"titre": t, "n": n} for t, n in dos.most_common(15)]
        # demandeurs de scrutin et auteurs d'amendements soumis à scrutin, par groupe
        dem_g = collections.Counter(dsig for s in scr for dsig in s["dem"])
        aut_g = collections.Counter(s["ag"] for s in scr if s["ag"] and s["o"] in ("amendement", "sous_amendement"))
        adoptes_par_auteur = collections.Counter(s["ag"] for s in scr if s["ag"] and s["o"] in ("amendement", "sous_amendement") and s["r"] == "a")
        general = {
            "legislature": leg, "n_scrutins": S, "n_votes": int(vot.sum()), "n_deputes": D,
            "periode": [min(dates), max(dates)],
            "adoptes": sum(s["r"] == "a" for s in scr),
            "par_objet": dict(collections.Counter(s["o"] for s in scr)),
            "par_mois": {k: dict(v) for k, v in sorted(par_mois.items())},
            "groupes": stats_g, "accords_groupes": accords_g, "ordre_groupes": sigles,
            "themes": theme_stats, "participation_familles": {f: round(v, 4) for f, v in part_glob.items()},
            "top_dossiers": top_dossiers,
            "demandeurs": dict(dem_g), "auteurs_amendements": dict(aut_g), "amendements_adoptes": dict(adoptes_par_auteur),
            "acp_variance": variance,
            "participation_moyenne": round(float(vot.sum() / max(en_mandat.sum(), 1)), 4),
        }
        # ---------- écriture ----------
        meta["legislatures"].append({"code": leg, "label": LEG_LABEL.get(leg, f"Législature {leg}"),
                                     "periode": [min(dates), max(dates)], "n_scrutins": S, "groupes": [
                                         {"sigle": g, "nom": leg_nom.get((leg, g), sigle_nom.get(g)), "famille": fam_of(g),
                                          "couleur": GROUPES.get(g, ("#999", 99))[0], "rang": GROUPES.get(g, ("", 99))[1]} for g in sigles]})
        dump = lambda obj, name: json.dump(obj, open(os.path.join(OUT, name), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        dump({"scrutins": scr}, f"scrutins_{leg}.json")
        dump({"deputes": deputes_out}, f"deputes_{leg}.json")
        dump({"uids": [s["uid"] for s in scr], "matrice": rows}, f"votes_{leg}.json")
        dump(general, f"general_{leg}.json")
        print(f"  {S} scrutins, {D} députés, variance ACP {variance}", file=sys.stderr)
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("Terminé.", file=sys.stderr)

if __name__ == "__main__":
    main()

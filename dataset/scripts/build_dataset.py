#!/usr/bin/env python3
"""Construit le jeu de données des scrutins de l'Assemblée nationale (XVe, XVIe et XVIIe législatures).

Usage (depuis la racine du dépôt) :
    python3 scripts/build_dataset.py

Entrées (par défaut) :
  data/sources/scrutins/<législature>/   scrutins open data AN (un fichier VTANR5L*.json par scrutin)
  data/sources/acteurs/                  référentiel AMO (acteur/, organe/) : noms, groupes à la date du vote
  data/sources/amendements.jsonl         amendements aplatis (index_amendements.py)
  data/index/dossiers_index.json         dossiers législatifs (index_dossiers.py)
  data/dataset/textes_lois.jsonl         textes des lois (fetch_textes.py + parse_textes.py)
Options : --scrutins <dossier> (répétable), --raw <AMO>, --amendements <jsonl>, --out <dossier>.

Sorties (data/dataset/) :
  scrutins.jsonl   un scrutin par ligne, avec tous les votes nominatifs
  groupes.json     identifiant de groupe -> sigle, nom, famille politique
  deputes.json     identifiant de député -> nom, groupes successifs observés
  stats.json       comptages et contrôles de qualité

Bibliothèque standard Python uniquement (3.8+). Durée : ~1 min.
"""
import argparse, json, os, re, sys, glob, collections
from datetime import date

# ---------------------------------------------------------------------------
# Groupes et familles politiques
# ---------------------------------------------------------------------------
# Familles harmonisées entre législatures. Libellés volontairement descriptifs ;
# à adapter dans groupes.json si l'équipe préfère un autre découpage.
FAMILLES = {
    "gauche_radicale": "Gauche radicale",
    "gauche": "Gauche",
    "bloc_central": "Bloc central",
    "independants": "Indépendants (LIOT)",
    "droite": "Droite",
    "droite_radicale": "Droite radicale",
    "non_inscrits": "Non-inscrits",
}

# Correspondance des sigles (XVIe et XVIIe) vers les familles.
SIGLE_FAMILLE = {
    # XVIIe
    "LFI-NFP": "gauche_radicale", "GDR": "gauche_radicale",
    "SOC": "gauche", "EcoS": "gauche",
    "EPR": "bloc_central", "Dem": "bloc_central", "HOR": "bloc_central",
    "LIOT": "independants",
    "DR": "droite",
    "RN": "droite_radicale", "UDR": "droite_radicale",
    "NI": "non_inscrits",
    # XVIe
    "LFI-NUPES": "gauche_radicale", "GDR-NUPES": "gauche_radicale",
    "Ecolo-NUPES": "gauche", "ECOLO": "gauche",
    "RE": "bloc_central", "REN": "bloc_central",
    "LR": "droite",
    "DEM": "bloc_central", "ECOS": "gauche", "SOC-A": "gauche",
    # XVe (2017-2022) ; les groupes UDI successifs et les Constructifs sont classés au centre-droit (droite),
    # EDS (dissidents de LaREM, écologistes) à gauche.
    "FI": "gauche_radicale", "NG": "gauche", "EDS": "gauche", "LT": "independants",
    "LAREM": "bloc_central", "MODEM": "bloc_central", "AGIR-E": "bloc_central",
    "LC": "droite", "UDI-AGIR": "droite", "UDI-I": "droite", "UDI-A-I": "droite", "UDI_I": "droite",
}

# Table intégrée pour la XVIIe : déduite des effectifs au premier scrutin (8 oct. 2024)
# et vérifiée par les demandes de scrutin. Remplacée par l'AMO quand il est présent.
GROUPES_L17 = {
    "PO845401": ("RN", "Rassemblement National"),
    "PO845407": ("EPR", "Ensemble pour la République"),
    "PO845413": ("LFI-NFP", "La France insoumise - Nouveau Front Populaire"),
    "PO845419": ("SOC", "Socialistes et apparentés"),
    "PO845425": ("DR", "Droite Républicaine"),
    "PO845439": ("EcoS", "Écologiste et Social"),
    "PO845454": ("Dem", "Les Démocrates"),
    "PO845470": ("HOR", "Horizons & Indépendants"),
    "PO845485": ("LIOT", "Libertés, Indépendants, Outre-mer et Territoires"),
    "PO845514": ("GDR", "Gauche Démocrate et Républicaine"),
    "PO847173": ("UDR", "Union des droites pour la République"),
    "PO872880": ("UDR", "Union des droites pour la République"),  # même groupe, nouvel identifiant (sept. 2025)
    "PO840056": ("NI", "Non-inscrits"),
}
GROUPE_INCONNU = "PO0"  # identifiant vide publié par l'AN dans quelques scrutins
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # racine du dépôt
DATA = os.path.join(ROOT, "data")

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]

def txt(x):
    """Les champs de l'open data AN sont parfois {'#text': ...}."""
    if isinstance(x, dict):
        return x.get("#text")
    return x

def iter_scrutins(path):
    if os.path.isdir(path):
        files = glob.glob(os.path.join(path, "**", "*.json"), recursive=True)
        for f in files:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            if "scrutin" in d and d["scrutin"]["uid"].startswith("VTAN"):
                yield d["scrutin"]
    else:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        for s in as_list(d.get("scrutins", {}).get("scrutin")):
            if s["uid"].startswith("VTAN"):  # exclut les votes du Congrès (VTCG...)
                yield s

# ---------------------------------------------------------------------------
# AMO (optionnel)
# ---------------------------------------------------------------------------
def load_amo(raw):
    """Retourne (organes, acteurs). Silencieux si absent."""
    organes, acteurs = {}, {}
    if not raw or not os.path.isdir(raw):
        return organes, acteurs
    for f in glob.glob(os.path.join(raw, "**", "organe", "*.json"), recursive=True):
        try:
            o = json.load(open(f, encoding="utf-8"))["organe"]
        except Exception:
            continue
        uid = txt(o.get("uid"))
        organes[uid] = {
            "codeType": o.get("codeType"),
            "libelle": o.get("libelle"),
            "libelleAbrev": o.get("libelleAbrev") or o.get("libelleAbrege"),
            "legislature": o.get("legislature"),
        }
    for f in glob.glob(os.path.join(raw, "**", "acteur", "*.json"), recursive=True):
        try:
            a = json.load(open(f, encoding="utf-8"))["acteur"]
        except Exception:
            continue
        uid = txt(a.get("uid"))
        ident = (a.get("etatCivil") or {}).get("ident") or {}
        gp = []
        for m in as_list((a.get("mandats") or {}).get("mandat")):
            if m.get("typeOrgane") == "GP":
                ref = txt(((m.get("organes") or {}).get("organeRef")))
                gp.append({"organeRef": ref, "debut": m.get("dateDebut"), "fin": m.get("dateFin")})
        acteurs[uid] = {"civ": ident.get("civ"), "prenom": ident.get("prenom"),
                        "nom": ident.get("nom"), "groupes": gp}
    return organes, acteurs

# ---------------------------------------------------------------------------
# Analyse du libellé
# ---------------------------------------------------------------------------
RE_AMDT = re.compile(r"(sous-)?amendement(?:s)?(?: de suppression)? n[°o]\s*(\d+)", re.I)
RE_LECTURE = re.compile(r"\((première lecture|deuxième lecture|troisième lecture|nouvelle lecture|lecture définitive|texte de la commission mixte paritaire)\)", re.I)

def normaliser(libelle):
    """Apostrophes typographiques et fautes de frappe de l'AN (amendmeent, amenedement...)."""
    l = libelle.replace("’", "'")
    return re.sub(r"\b(sous-)?amen\w*", lambda m: (m.group(1) or "") + "amendement", l, flags=re.I)

def classer_objet(libelle, code_type):
    l = normaliser(libelle).lower()
    if code_type == "MOC" or "motion de censure" in l:
        return "motion_censure"
    if "seconde délibération" in l:
        return "procedure"
    if l.startswith("le sous-amendement") or l.startswith("les sous-amendement"):
        return "sous_amendement"
    if l.startswith("l'amendement") or l.startswith("les amendement"):
        return "amendement"
    if l.startswith("l'ensemble") or l.startswith("la proposition de résolution") or l.startswith("le projet de loi") or l.startswith("la proposition de loi"):
        return "ensemble"
    if re.match(r"la (première|deuxième|troisième|quatrième) partie", l):
        return "partie_budget"
    if re.match(r"l'a\w*icle|les articles", l):
        return "article"
    if "motion de rejet" in l or "motion de renvoi" in l or l.startswith("la motion"):
        return "motion_procedure"
    if "déclaration du gouvernement" in l or "déclaration de politique" in l:
        return "declaration"
    if "prolonger la séance" in l or "suspension" in l or "ordre du jour" in l:
        return "procedure"
    return "autre"

PARTICULES = {"de", "du", "des", "d'", "le", "la", "van", "von"}

def nettoyer_nom(nom):
    """Garde les mots du nom propre ; s'arrête au premier mot en minuscule (« de suppression », « au titre »...)."""
    garde = []
    for w in nom.split():
        if w[:1].isupper():
            garde.append(w)
        elif w.lower() in PARTICULES or w.lower().startswith("d'"):
            garde.append(w)
        else:
            break
    while garde and (garde[-1].lower() in PARTICULES):
        garde.pop()
    return " ".join(garde)

def parse_libelle(libelle):
    libelle = re.sub(r"\s+", " ", normaliser(libelle))
    out = {"numero_amendement": None, "auteur_texte": None, "dossier_titre": None, "lecture": None}
    m = RE_AMDT.search(libelle)
    if m:
        out["numero_amendement"] = int(m.group(2))
    m = re.search(r"n[°o]\s*\d+(?:\s*\([^)]*rect\.?\)| rectifié)?\s+(de Mme|de M\.|de M(?= )|du Gouvernement|de la commission[^,à]*?)\s*([^,]*?)(?= et | à | après | avant | portant| de suppression| tendant|,|$)", libelle)
    if m:
        who = m.group(1).strip()
        if who.startswith("du Gouvernement"):
            out["auteur_texte"] = "Gouvernement"
        elif who.startswith("de la commission"):
            out["auteur_texte"] = who[3:].strip()
        else:
            civ = "Mme" if who.endswith("Mme") else "M."
            out["auteur_texte"] = (civ + " " + nettoyer_nom(m.group(2))).strip()
    m = RE_LECTURE.search(libelle)
    if m:
        out["lecture"] = m.group(1).lower()
    m = re.search(r"(?:de la |du |de l'|de l’)((?:proposition|projet) de (?:loi|résolution).*?)\s*\((?:première|deuxième|troisième|nouvelle|lecture|texte)[^)]*\)\s*\.?\s*$", libelle, re.I)
    if m:
        out["dossier_titre"] = m.group(1)[0].upper() + m.group(1)[1:]
    return out

def html_unescape(x):
    import html
    return html.unescape(x).replace("\xa0", " ") if x else x

def rec_dossier_id_present(dl):
    return bool(dl and dl.get("dossierRef"))

def nature_dossier(titre):
    if not titre:
        return None
    t = titre.lower()
    if t.startswith("projet de loi"):
        return "projet_de_loi"
    if t.startswith("proposition de loi"):
        return "proposition_de_loi"
    if "résolution" in t:
        return "proposition_de_resolution"
    return "autre"

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
VOTE_KEYS = {"pours": "pour", "contres": "contre", "abstentions": "abstention", "nonVotants": "non_votant"}
MAP_KEYS = {"pours": "pour", "contres": "contre", "abstentions": "abstention",
            "nonVotants": "non_votant", "nonVotantsVolontaires": "non_votant_volontaire"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scrutins", action="append", help="dossier(s) de scrutins (défaut : data/sources/scrutins/*)")
    ap.add_argument("--raw", default=os.path.join(DATA, "sources", "acteurs"), help="référentiel AMO (acteur/, organe/)")
    ap.add_argument("--amendements", default=None,
                    help="index produit par index_amendements.py (défaut : <out>/amendements_index.jsonl s'il existe)")
    ap.add_argument("--out", default=os.path.join(DATA, "dataset"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if not args.scrutins:
        base = os.path.join(DATA, "sources", "scrutins")
        args.scrutins = [os.path.join(base, d) for d in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, d))]

    organes, acteurs = load_amo(args.raw)

    # Amendements de séance (numéro purement numérique), indexés par (législature, numéro)
    # En mémoire : seulement les champs de jointure + la position de la ligne ; le texte est relu à la demande.
    amdts = collections.defaultdict(list)
    chemin_amdts = args.amendements or os.path.join(DATA, "sources", "amendements.jsonl")
    chemin_amdts = chemin_amdts if os.path.exists(chemin_amdts) else ""
    f_amdts = open(chemin_amdts, "rb") if chemin_amdts else None
    if f_amdts:
        while True:
            pos = f_amdts.tell()
            line = f_amdts.readline()
            if not line:
                break
            if b'"seance": true' not in line:  # seuls les amendements de séance passent en scrutin public
                continue
            a = json.loads(line)
            if a["seance"] and a["numero"] is not None:
                amdts[(a["legislature"], a["numero"])].append(dict({k: a[k] for k in (
                    "uid", "dossier_id", "texte_id", "date_sort", "auteur_id", "auteur_type", "auteur_groupe_id")}, pos=pos))

    def texte_amendement(a):
        f_amdts.seek(a["pos"])
        return json.loads(f_amdts.readline())
    print(f"Amendements de séance indexés : {sum(len(v) for v in amdts.values())}", file=sys.stderr)

    # Index des dossiers législatifs (index_dossiers.py) : texte -> dossier, titre -> dossier, dossier -> texte initial
    dindex = {"textes": {}, "dossiers": {}, "titres": {}}
    p_dindex = os.path.join(DATA, "index", "dossiers_index.json")
    if os.path.exists(p_dindex):
        dindex = json.load(open(p_dindex, encoding="utf-8"))
    print(f"Dossiers indexés : {len(dindex['dossiers'])}", file=sys.stderr)

    def norm_titre(t):
        import unicodedata
        t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower().replace("’", "'")
        t = re.sub(r"[^a-z0-9 ]", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    def dossier_par_titre(*titres):
        for t in titres:
            if t and norm_titre(t) in dindex["titres"]:
                return dindex["titres"][norm_titre(t)]
        return None

    # Textes des lois (fetch_textes.py + parse_textes.py) : dossier -> texte initial
    textes_dossier, textes_info = {}, {}
    p_liste = os.path.join(DATA, "index", "textes_a_telecharger.json")
    p_textes = os.path.join(DATA, "dataset", "textes_lois.jsonl")
    if os.path.exists(p_liste):
        textes_dossier = {d: v["texte_initial"] for d, v in json.load(open(p_liste, encoding="utf-8")).items()}
    for d, v in dindex["dossiers"].items():
        if v.get("texte_initial"):
            textes_dossier[d] = v["texte_initial"]
    if os.path.exists(p_textes):
        for line in open(p_textes, encoding="utf-8"):
            t = json.loads(line)
            textes_info[t["uid"]] = {"titre": t["titre"], "expose": bool(t["expose_motifs"]),
                                     "articles": bool(t["articles"]), "note": t["note"]}

    def joindre_amendement(leg, num, d, auteur_id, dossier_id):
        """Retourne (amendement, qualité) : même numéro, puis date du sort, auteur et dossier."""
        cands = amdts.get((leg, num), [])
        for a in cands:
            if not a["dossier_id"] and a["texte_id"] in dindex["textes"]:
                a["dossier_id"] = dindex["textes"][a["texte_id"]]["dossier"]
        if not cands:
            return None, "absente"
        def score(a):
            return (2 * (a["date_sort"] == d) + 2 * bool(auteur_id and a["auteur_id"] == auteur_id)
                    + 2 * bool(dossier_id and a["dossier_id"] == dossier_id))
        notes = sorted(((score(a), a) for a in cands), key=lambda x: -x[0])
        best, a = notes[0]
        ex_aequo = len(notes) > 1 and notes[1][0] == best
        if best >= 4 and not ex_aequo:
            return a, "exacte"
        if best >= 2 and not ex_aequo:
            return a, "probable"
        return None, "ambigue"
    print(f"AMO : {len(organes)} organes, {len(acteurs)} acteurs", file=sys.stderr)

    scrutins = []
    for p in args.scrutins:
        scrutins.extend(iter_scrutins(p))
    scrutins.sort(key=lambda s: (int(s["legislature"]), s["dateScrutin"], int(s["numero"])))
    print(f"{len(scrutins)} scrutins chargés", file=sys.stderr)

    # 1. Table des groupes
    def info_groupe(ref):
        if ref in organes and organes[ref].get("codeType") == "GP":
            o = organes[ref]
            sigle = o.get("libelleAbrev") or ref
            return {"sigle": sigle, "nom": o.get("libelle"), "source": "AMO"}
        if ref in GROUPES_L17:
            sigle, nom = GROUPES_L17[ref]
            return {"sigle": sigle, "nom": nom, "source": "table_integree"}
        return {"sigle": None, "nom": None, "source": "inconnu"}

    # 2. Chronologie des groupes de chaque député, observée dans les scrutins
    chrono = collections.defaultdict(list)  # acteur -> [(cle_temps, organeRef)]
    for i, s in enumerate(scrutins):
        for g in as_list(s["ventilationVotes"]["organe"]["groupes"]["groupe"]):
            ref = g["organeRef"]
            if ref == GROUPE_INCONNU:
                continue
            for k in VOTE_KEYS:
                for v in as_list((g["vote"]["decompteNominatif"].get(k) or {}).get("votant")):
                    chrono[v["acteurRef"]].append((i, ref))

    def groupe_infere(acteur, i):
        """Groupe du député au scrutin le plus proche (en rang) où il est identifié."""
        obs = chrono.get(acteur)
        if not obs:
            return None
        best = min(obs, key=lambda o: abs(o[0] - i))
        return best[1]

    # 3. Index des noms pour retrouver l'auteur d'un amendement (si AMO)
    par_nom = collections.defaultdict(list)
    for uid, a in acteurs.items():
        if a.get("nom") and a["groupes"]:
            par_nom[a["nom"].lower()].append(uid)
            if a.get("prenom"):
                par_nom[(a["prenom"] + " " + a["nom"]).lower()].append(uid)

    def trouver_auteur(texte, d):
        """Député dont le nom correspond, en mandat (groupe politique) à la date d, même civilité."""
        civ = "Mme" if texte.startswith("Mme") else "M."
        nom = re.sub(r"^(M\.|Mme)\s+", "", texte).strip().lower()
        cands = [u for u in par_nom.get(nom, [])
                 if acteurs[u].get("civ") == civ and groupe_amo_a_date(u, d)]
        cands = list(dict.fromkeys(cands))
        return cands[0] if len(cands) == 1 else None

    def groupe_amo_a_date(acteur, d):
        a = acteurs.get(acteur)
        if not a:
            return None
        for m in a["groupes"]:
            if (m["debut"] or "") <= d and (not m["fin"] or d <= m["fin"]):
                return m["organeRef"]
        return None

    stats = collections.Counter()
    groupes_vus = {}
    deputes = {}
    out_path = os.path.join(args.out, "scrutins.jsonl")
    with open(out_path, "w", encoding="utf-8") as out:
        for i, s in enumerate(scrutins):
            libelle = (s.get("objet") or {}).get("libelle") or s.get("titre") or ""
            code = s["typeVote"]["codeTypeVote"]
            parsed = parse_libelle(libelle)
            dl = (s.get("objet") or {}).get("dossierLegislatif") or {}
            if not dl.get("dossierRef"):
                ref = dossier_par_titre(parse_libelle(libelle)["dossier_titre"], dl.get("libelle"))
                if ref:
                    dl = dict(dl, dossierRef=ref)
                    stats["dossier_par_titre"] += 1
            dossier_titre = parsed["dossier_titre"] or dl.get("libelle")
            objet_vote = classer_objet(libelle, code)
            stats["objet_" + objet_vote] += 1
            leg = int(s["legislature"])

            # auteur
            auteur = None
            if parsed["auteur_texte"]:
                auteur = {"texte": parsed["auteur_texte"], "type": None, "depute_id": None, "groupe": None}
                at = parsed["auteur_texte"]
                if at == "Gouvernement":
                    auteur["type"] = "gouvernement"
                elif at.startswith("commission") or at.startswith("la commission"):
                    auteur["type"] = "commission"
                else:
                    auteur["type"] = "depute"
                    pa_auteur = trouver_auteur(at, s["dateScrutin"])
                    if pa_auteur:
                        auteur["depute_id"] = pa_auteur
                        gref = groupe_amo_a_date(pa_auteur, s["dateScrutin"]) or groupe_infere(pa_auteur, i)
                        if gref:
                            auteur["groupe"] = info_groupe(gref)["sigle"]
            elif objet_vote == "motion_censure":
                auteur = {"texte": None, "type": "deputes", "depute_id": None, "groupe": None}

            # mises au point : intention déclarée après coup
            # Texte de l'amendement
            texte = {"amendement_uid": None, "numero_amendement": parsed["numero_amendement"],
                     "article": None, "dispositif": None, "expose_sommaire": None, "signataires": None,
                     "qualite_jointure": "intitule_seul"}
            if objet_vote in ("amendement", "sous_amendement") and parsed["numero_amendement"] and amdts:
                a, q = joindre_amendement(leg, parsed["numero_amendement"], s["dateScrutin"],
                                          auteur and auteur.get("depute_id"), dl.get("dossierRef"))
                texte["qualite_jointure"] = q
                stats["jointure_" + q] += 1
                if a:
                    a = dict(texte_amendement(a), dossier_id=a["dossier_id"])
                    texte.update({"amendement_uid": a["uid"], "article": a["article"],
                                  "dispositif": a["dispositif"], "expose_sommaire": a["expose_sommaire"],
                                  "signataires": html_unescape(a["signataires"])})
                    if auteur is not None and a["auteur_type"] == "Député" and a["auteur_id"]:
                        auteur["depute_id"] = a["auteur_id"]
                        if a["auteur_groupe_id"]:
                            auteur["groupe"] = info_groupe(a["auteur_groupe_id"])["sigle"]
                    elif auteur is not None and a["auteur_type"] == "Gouvernement":
                        auteur["type"] = "gouvernement"
                    if not rec_dossier_id_present(dl) and a["dossier_id"]:
                        dl = dict(dl, dossierRef=a["dossier_id"])

            def texte_initial(dossier_id):
                uid = textes_dossier.get(dossier_id)
                if not uid:
                    return None
                info = textes_info.get(uid)
                stats["texte_initial_" + ("expose" if info and info["expose"] else (info["note"] if info and info["note"] else ("telecharge" if info else "non_telecharge")))] += 1
                return {"uid": uid, "telecharge": bool(info),
                        "expose_motifs": bool(info and info["expose"]),
                        "articles": bool(info and info["articles"]),
                        "note": info and info["note"]}

            mises = {}
            for k, lab in MAP_KEYS.items():
                for blk in as_list((s.get("miseAuPoint") or {}).get(k)):
                    for v in as_list((blk or {}).get("votant")):
                        mises[v["acteurRef"]] = lab

            votes, positions, membres = [], {}, {}
            for g in as_list(s["ventilationVotes"]["organe"]["groupes"]["groupe"]):
                ref = g["organeRef"]
                if ref != GROUPE_INCONNU and info_groupe(ref)["sigle"]:
                    membres[info_groupe(ref)["sigle"]] = int(g.get("nombreMembresGroupe") or 0)
                for k, lab in VOTE_KEYS.items():
                    for v in as_list((g["vote"]["decompteNominatif"].get(k) or {}).get("votant")):
                        pa = v["acteurRef"]
                        gref = ref
                        source_groupe = "scrutin"
                        if ref == GROUPE_INCONNU:
                            gref = groupe_amo_a_date(pa, s["dateScrutin"]) or groupe_infere(pa, i)
                            source_groupe = "infere"
                            stats["votes_groupe_infere"] += 1
                        gi = info_groupe(gref) if gref else {"sigle": None, "nom": None, "source": "inconnu"}
                        if gref:
                            groupes_vus[gref] = gi
                        a = acteurs.get(pa, {})
                        nom = " ".join(x for x in (a.get("prenom"), a.get("nom")) if x) or None
                        rec = {
                            "depute_id": pa,
                            "nom": nom,
                            "groupe": gi["sigle"],
                            "famille": SIGLE_FAMILLE.get(gi["sigle"]),
                            "vote": lab,
                        }
                        if lab == "non_votant" and v.get("causePositionVote"):
                            rec["cause_non_vote"] = v["causePositionVote"]  # MG, PAN, PSE...
                        if str(v.get("parDelegation")).lower() == "true":
                            rec["par_delegation"] = True
                        if pa in mises:
                            rec["mise_au_point"] = mises[pa]
                        if source_groupe == "infere":
                            rec["groupe_infere"] = True
                        votes.append(rec)
                        stats["votes"] += 1
                        stats["vote_" + lab] += 1
                        d = deputes.setdefault(pa, {"nom": nom, "groupes": {}})
                        if gi["sigle"]:
                            gg = d["groupes"].setdefault(gi["sigle"], [s["dateScrutin"], s["dateScrutin"]])
                            gg[0] = min(gg[0], s["dateScrutin"]); gg[1] = max(gg[1], s["dateScrutin"])

            # Position de chaque groupe, recalculée depuis les votes nominatifs :
            # vote le plus fréquent parmi pour / contre / abstention, None si personne n'a voté.
            # (La « positionMajoritaire » officielle vaut « pour » pour tous les groupes sur les
            # motions de censure, même sans aucun votant : on ne l'utilise pas.)
            # Motion de censure : seuls les soutiens votent ; « pour » si plus de la moitié des
            # membres du groupe l'ont votée, sinon « ne_soutient_pas ».
            par_groupe = collections.defaultdict(collections.Counter)
            for v in votes:
                if v["groupe"]:
                    par_groupe[v["groupe"]][v["vote"]] += 1
            for sig in membres:
                par_groupe.setdefault(sig, collections.Counter())
            for sig, c in par_groupe.items():
                exprimes = {k: c[k] for k in ("pour", "contre", "abstention") if c[k]}
                if objet_vote == "motion_censure":
                    positions[sig] = {"position": "pour" if c["pour"] * 2 > (membres.get(sig) or sum(c.values())) else "ne_soutient_pas", "pour": c["pour"], "membres": membres.get(sig)}
                elif not exprimes:
                    positions[sig] = {"position": None}
                else:
                    top = max(exprimes, key=exprimes.get)
                    tot = sum(exprimes.values())
                    positions[sig] = {"position": top, "cohesion": round(exprimes[top] / tot, 3),
                                      "pour": c["pour"], "contre": c["contre"], "abstention": c["abstention"]}
            for pa, lab in mises.items():
                stats["mises_au_point"] += 1

            dec = s["syntheseVote"]["decompte"]
            rec = {
                "uid": s["uid"],
                "legislature": leg,
                "numero": int(s["numero"]),
                "date": s["dateScrutin"],
                "type_vote": {"SPO": "ordinaire", "SPS": "solennel", "MOC": "motion_de_censure"}.get(code, code),
                "objet_vote": objet_vote,
                "intitule": libelle,
                "resultat": s["sort"]["code"],
                "demandeur": (s.get("demandeur") or {}).get("texte"),
                "dossier": {
                    "id": dl.get("dossierRef"),
                    "texte_initial": texte_initial(dl.get("dossierRef")),
                    "titre": dossier_titre,
                    "titre_court": dl.get("libelle"),
                    "nature": nature_dossier(dossier_titre) if nature_dossier(dossier_titre) != "autre" else nature_dossier(dl.get("libelle")),
                    "lecture": parsed["lecture"],
                },
                "texte": texte,
                "auteur": auteur,
                "decompte": {k: int(dec.get(k) or 0) for k in ("pour", "contre", "abstentions", "nonVotants")},
                "positions_groupes": positions,
                "votes": votes,
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    groupes_out = {ref: dict(gi, famille=SIGLE_FAMILLE.get(gi["sigle"])) for ref, gi in sorted(groupes_vus.items())}
    json.dump({"familles": FAMILLES, "groupes": groupes_out}, open(os.path.join(args.out, "groupes.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(deputes, open(os.path.join(args.out, "deputes.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    stats["scrutins"] = len(scrutins)
    stats["deputes"] = len(deputes)
    stats["amo_charge"] = int(bool(acteurs))
    json.dump(dict(stats), open(os.path.join(args.out, "stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(dict(stats), ensure_ascii=False, indent=2), file=sys.stderr)

if __name__ == "__main__":
    main()

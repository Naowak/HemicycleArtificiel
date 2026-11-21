#!/usr/bin/env python3
"""Index des dossiers législatifs de l'open data AN (un fichier JSON par document et par dossier).

Usage : python3 scripts/index_dossiers.py   (défaut : data/sources/dossiers/* -> data/index/dossiers_index.json)
Produit :
  textes   : identifiant de texte -> dossier, type, titre, date de dépôt
  dossiers : identifiant de dossier -> titre, législature, textes (par date), texte initial déposé à l'AN
  titres   : titre normalisé d'un texte -> dossier (pour relier les scrutins dont l'AN n'a pas renseigné le dossier)
"""
import argparse, glob, json, os, re, unicodedata

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dossiers", nargs="*")
    ap.add_argument("--out", default=os.path.join(RACINE, "data", "index", "dossiers_index.json"))
    args = ap.parse_args()
    if not args.dossiers:
        base = os.path.join(RACINE, "data", "sources", "dossiers")
        args.dossiers = [os.path.join(base, d) for d in sorted(os.listdir(base))]
    textes, dossiers, titres = {}, {}, {}
    for racine in args.dossiers:
        for f in glob.glob(os.path.join(racine, "dossierParlementaire", "*.json")):
            d = json.load(open(f, encoding="utf-8"))
            d = d.get("dossierParlementaire", d)
            uid = d.get("uid")
            dossiers.setdefault(uid, {"titre": (d.get("titreDossier") or {}).get("titre"),
                                      "legislature": int(d.get("legislature") or 0),
                                      "procedure": (d.get("procedureParlementaire") or {}).get("libelle"),
                                      "textes": []})
        for f in glob.glob(os.path.join(racine, "document", "*.json")):
            d = json.load(open(f, encoding="utf-8"))
            d = d.get("document", d)
            uid = d.get("uid")
            cl = (d.get("classification") or {}).get("type") or {}
            t = d.get("titres") or {}
            date = (((d.get("cycleDeVie") or {}).get("chrono") or {}).get("dateDepot") or "")[:10] or None
            textes[uid] = {"dossier": d.get("dossierRef"), "type": cl.get("code"), "titre": t.get("titrePrincipal"),
                           "date": date, "legislature": int(d.get("legislature") or 0) if str(d.get("legislature") or "").isdigit() else None}
    for uid, t in textes.items():
        dos = dossiers.get(t["dossier"])
        if dos is not None:
            dos["textes"].append(uid)
        if t["titre"] and t["dossier"] and uid.startswith(("PION", "PRJL", "PNRE")):
            titres.setdefault(norm(t["titre"]), t["dossier"])
    for uid, dos in dossiers.items():
        dos["textes"].sort(key=lambda u: (textes[u]["date"] or "9999", u))
        # texte initial : premier projet / proposition déposé ou transmis à l'Assemblée (pas un texte de commission)
        cands = [u for u in dos["textes"] if re.match(r"(PION|PRJL|PNRE)ANR5L\d+B\d+$", u)]
        dos["texte_initial"] = cands[0] if cands else None
        if dos["titre"]:
            titres.setdefault(norm(dos["titre"]), uid)
    json.dump({"textes": textes, "dossiers": dossiers, "titres": titres}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{len(dossiers)} dossiers, {len(textes)} documents, {len(titres)} titres ; "
          f"{sum(1 for d in dossiers.values() if d['texte_initial'])} dossiers avec texte initial AN")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Aplatit les amendements de l'open data AN (un fichier JSON par amendement) en un fichier JSONL compact.

Usage :
    python3 scripts/index_amendements.py <dossier_amendements> --out x.jsonl     # export AN dézippé
    python3 scripts/index_amendements.py Amendements_XV-master.zip --out x.jsonl  # archive zip de Tricoteuses
Puis concaténer les législatures dans data/sources/amendements.jsonl.
Ne garde que ce qui sert à la jointure avec les scrutins et au texte : numéro, auteur, groupe, article,
dates, sort, dispositif et exposé sommaire (en texte brut).
"""
import argparse, html, json, os, re, sys, zipfile

def txt(x):
    if isinstance(x, dict):
        if x.get("@xsi:nil") in ("true", True):
            return None
        return x.get("#text")
    return x

def nettoyer_html(h):
    h = txt(h)
    if not h:
        return None
    h = re.sub(r"<\s*(br|/p|/li|/h\d)\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "", h)
    h = html.unescape(h).replace("\xa0", " ")
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"\n\s*\n+", "\n", h)
    return h.strip() or None

def convertir(d, dossier_id=None):
    a = d.get("amendement", d)  # format AN (enveloppe « amendement ») ou Tricoteuses (à plat)
    ident = a.get("identification") or {}
    sig = (a.get("signataires") or {})
    aut = sig.get("auteur") or {}
    corps = ((a.get("corps") or {}).get("contenuAuteur")) or {}
    cyc = a.get("cycleDeVie") or {}
    div = ((a.get("pointeurFragmentTexte") or {}).get("division")) or {}
    num_long = txt(ident.get("numeroLong"))
    # Séance : « 123 », « 123 (Rect) », « 42 (2ème Rect) », « I-3377 », « II-576 (Rect) ».
    # Commission : préfixe d'organe (CL, AS, CF, I-CF, II-CE...).
    m_seance = re.match(r"^(?:(I|II)-)?(\d+)(?:\s*\([^)]*Rect\))?$", (num_long or "").strip())
    date_sort = txt(cyc.get("dateSort"))
    return {
        "uid": txt(a.get("uid")),
        "legislature": int(txt(a.get("legislature")) or 0),
        "dossier_id": dossier_id,
        "texte_id": txt(a.get("texteLegislatifRef")),
        "numero_long": num_long,
        "numero": int(m_seance.group(2)) if m_seance else None,
        "partie_budget": m_seance.group(1) if m_seance else None,
        "seance": bool(m_seance),
        "auteur_type": txt(aut.get("typeAuteur")),
        "auteur_id": txt(aut.get("acteurRef")),
        "auteur_groupe_id": txt(aut.get("groupePolitiqueRef")),
        "signataires": txt(sig.get("libelle")),
        "article": txt(div.get("titre")),
        "date_depot": txt(cyc.get("dateDepot")),
        "date_sort": (date_sort or "")[:10] or None,
        "sort": txt(cyc.get("sort")),
        "dispositif": nettoyer_html(corps.get("dispositif")),
        "expose_sommaire": nettoyer_html(corps.get("exposeSommaire")),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dossiers", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--part", type=int, default=0)
    ap.add_argument("--parts", type=int, default=1)
    args = ap.parse_args()
    n = err = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for racine in args.dossiers:
            if racine.endswith(".zip"):
                z = zipfile.ZipFile(racine)
                noms = sorted(x for x in z.namelist() if os.path.basename(x).startswith("AM") and x.endswith(".json"))
                for nom in noms[args.part::args.parts]:
                    try:
                        d = json.loads(z.read(nom))
                    except Exception:
                        err += 1
                        continue
                    out.write(json.dumps(convertir(d), ensure_ascii=False) + "\n")
                    n += 1
                continue
            for dirpath, _, files in os.walk(racine):
                for f in files:
                    if not (f.startswith("AM") and f.endswith(".json")):
                        continue
                    try:
                        d = json.load(open(os.path.join(dirpath, f), encoding="utf-8"))
                    except Exception:
                        err += 1
                        continue
                    rel = os.path.relpath(dirpath, racine).split(os.sep)
                    rec = convertir(d, rel[0] if rel and rel[0].startswith("DL") else None)
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n += 1
                    if n % 20000 == 0:
                        print(n, file=sys.stderr, flush=True)
    print(f"{n} amendements indexés, {err} illisibles", file=sys.stderr)

if __name__ == "__main__":
    main()

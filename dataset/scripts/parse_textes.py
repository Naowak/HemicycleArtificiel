#!/usr/bin/env python3
"""Extrait titre, exposé des motifs et articles des textes téléchargés par fetch_textes.py.

Usage (depuis la racine du dépôt) :
    python3 scripts/parse_textes.py    # data/sources/textes/*.html -> data/dataset/textes_lois.jsonl
Une ligne par texte : uid, type (proposition, projet, texte de commission...), origine, titre,
exposé des motifs, articles, note quand l'exposé manque.
"""
import argparse, glob, html, json, os, re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BLOCS = r"</?(p|div|br|h\d|li|tr|table|section)\b[^>]*>"

def texte_brut(h):
    h = re.sub(r"<(script|style)\b.*?</\1>", "", h, flags=re.S | re.I)
    h = re.sub(BLOCS, "\n", h, flags=re.I)          # fin de bloc = saut de ligne
    h = re.sub(r"<[^>]+>", "", h)                    # balises en ligne : on recolle les mots
    h = html.unescape(h).replace("\xa0", " ").replace("‑", "-")
    lignes = []
    for l in h.split("\n"):
        l = re.sub(r"[ \t\r]+", " ", l).strip()
        if not l or re.fullmatch(r"[–-]\s*\d+\s*[–-]", l) or re.fullmatch(r"_+", l):
            continue
        lignes.append(l)
    return "\n".join(lignes)

def type_texte(uid):
    if "BTC" in uid:
        return "texte_commission"
    return {"PION": "proposition_de_loi", "PRJL": "projet_de_loi", "PNRE": "proposition_de_resolution",
            "PPRE": "proposition_de_resolution", "TAAN": "texte_adopte"}.get(uid[:4], "autre")

RE_EXPOSE = re.compile(r"^EXPOS[ÉE] DES MOTIFS\s*$", re.M)
RE_DEBUT_ARTICLES = re.compile(r"^(PROPOSITION DE LOI|PROJET DE LOI|PROPOSITION DE RÉSOLUTION)( ORGANIQUE)?\s*$|^Article (1er|premier|liminaire|unique)\b", re.M | re.I)
RE_TITRE = re.compile(r"^(PROPOSITION|PROJET) DE (LOI|RÉSOLUTION)( ORGANIQUE)?\s*\n(.+?)(?=\n\(?(Renvoy|présentée|présenté|déposée|déposé|par M|par Mme|TEXTE)|\n[A-ZÉ ]{12,}\n)", re.S | re.I)

RE_ENTETE = re.compile(r"^(PROPOSITION|PROJET) DE (LOI|RÉSOLUTION)( ORGANIQUE)?.*$", re.M | re.I)
RE_FIN_TITRE = re.compile(r"^(\(Renvoy|présenté|TRANSMIS|Le Sénat a adopté|renvoyé|par M|par Mme|Voir les numéros|Sommaire)", re.I)

def extraire_titre(t):
    """Lignes qui suivent l'en-tête « PROPOSITION DE LOI » jusqu'au renvoi en commission ou aux auteurs."""
    m = RE_ENTETE.search(t[:5000])
    if not m:
        return None
    morceaux = []
    for l in t[m.end():m.end() + 3000].split("\n"):
        l = l.strip()
        if not l:
            continue
        if RE_FIN_TITRE.match(l):
            break
        if re.fullmatch(r"(ADOPTÉE?|MODIFIÉE?|TRANSMISE?)\b.*", l) and l.upper() == l:
            continue  # « ADOPTÉE PAR LE SÉNAT, »
        morceaux.append(l)
    titre = re.sub(r"\s*\(Procédure accélérée\)\s*", " ", " ".join(morceaux)).strip(" ,")
    return titre or None

def origine(t):
    debut = t[:3000].upper()
    if "PAR LE SÉNAT" in debut or "PRÉSIDENT DU SÉNAT" in debut:
        return "senat"
    return "assemblee"

def analyser(t):
    titre = extraire_titre(t)
    expose, articles = None, None
    me = RE_EXPOSE.search(t)
    if me:
        apres = t[me.end():]
        ma = RE_DEBUT_ARTICLES.search(apres)
        expose = apres[:ma.start()] if ma else apres
        articles = apres[ma.start():] if ma else None
        expose = re.sub(r"^\s*Mesdames,? Messieurs,?\s*", "", expose).strip()
    else:
        ma = re.search(r"^Article (1er|premier|liminaire|unique)\b", t, re.M | re.I)
        articles = t[ma.start():] if ma else None
    if articles:
        articles = re.sub(r"^(PROPOSITION DE LOI|PROJET DE LOI|PROPOSITION DE RÉSOLUTION)( ORGANIQUE)?\s*\n", "", articles.strip(), flags=re.I)
        articles = re.sub(r"\n(Article \d+)\n(er|re|e)\b", r"\n\1\2", "\n" + articles).strip()
    return titre, expose or None, articles or None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dossier", nargs="?", default=os.path.join(RACINE, "data", "sources", "textes"))
    ap.add_argument("--out", default=os.path.join(RACINE, "data", "dataset", "textes_lois.jsonl"))
    args = ap.parse_args()
    n = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for f in sorted(glob.glob(os.path.join(args.dossier, "*.html"))):
            uid = os.path.basename(f)[:-5]
            t = texte_brut(open(f, encoding="utf-8", errors="replace").read())
            titre, expose, articles = analyser(t)
            if not expose and re.search(r"^Exposé général des motifs$", t, re.M):
                note = "loi_de_finances_format_specifique"
            elif not expose and origine(t) == "senat":
                note = "transmis_par_le_senat_sans_expose"
            elif not expose and "BTC" in uid:
                note = "texte_de_commission_sans_expose"
            else:
                note = None
            out.write(json.dumps({
                "uid": uid, "type": type_texte(uid), "origine": origine(t), "titre": titre,
                "note": note,
                "expose_motifs": expose, "articles": articles,
                "nb_caracteres": {"expose": len(expose or ""), "articles": len(articles or "")},
                "url": f"https://www.assemblee-nationale.fr/dyn/opendata/{uid}.html",
            }, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} textes analysés")

if __name__ == "__main__":
    main()

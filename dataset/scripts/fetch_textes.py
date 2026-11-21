#!/usr/bin/env python3
"""Télécharge le texte complet (exposé des motifs + articles) des textes législatifs depuis assemblee-nationale.fr.

Usage (depuis la racine du dépôt) :
    python3 scripts/fetch_textes.py            # texte initial de chaque dossier (~710 fichiers, ~15 min)
    python3 scripts/fetch_textes.py --tous     # aussi les versions de commission (beaucoup plus)

Lit data/index/textes_a_telecharger.json, écrit data/sources/textes/<identifiant>.html.
Reprend là où il s'est arrêté (les fichiers déjà présents sont sautés). Une requête par seconde.
En cas d'erreur de certificat (proxy d'entreprise), bascule sur curl.
"""
import argparse, json, os, shutil, ssl, subprocess, sys, time, urllib.request, urllib.error

URL = "https://www.assemblee-nationale.fr/dyn/opendata/{}.html"
UA = "hemicycle-artificiel (hack1robo 2026)"

def contexte_ssl():
    """Certificats de certifi s'il est installé, sinon ceux du système."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

def via_curl(url, chemin):
    """curl sur macOS utilise le trousseau système (certificats d'un proxy d'entreprise compris)."""
    r = subprocess.run(["curl", "-sS", "-f", "-L", "--max-time", "60", "-A", UA, "-o", chemin, url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        if os.path.exists(chemin):
            os.remove(chemin)
        raise RuntimeError("curl : " + (r.stderr.strip() or f"code {r.returncode}"))

def telecharger(url, chemin, ctx, etat):
    if etat.get("curl"):
        return via_curl(url, chemin)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            data = r.read()
        open(chemin, "wb").write(data)
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), ssl.SSLError) and shutil.which("curl"):
            print("\n  Certificat refusé par Python : bascule sur curl pour la suite.", file=sys.stderr)
            etat["curl"] = True
            return via_curl(url, chemin)
        raise

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tous", action="store_true")
    ap.add_argument("--pause", type=float, default=1.0)
    args = ap.parse_args()
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    liste = json.load(open(os.path.join(racine, "data", "index", "textes_a_telecharger.json"), encoding="utf-8"))
    ids = []
    for d in liste.values():
        ids.extend(d["textes"] if args.tous else [d["texte_initial"]])
    ids = sorted(set(i for i in ids if i))
    out = os.path.join(racine, "data", "sources", "textes")
    os.makedirs(out, exist_ok=True)
    ok = deja = err = 0
    ctx, etat = contexte_ssl(), {}
    for n, uid in enumerate(ids, 1):
        chemin = os.path.join(out, uid + ".html")
        if os.path.exists(chemin) and os.path.getsize(chemin) > 0:
            deja += 1
            continue
        try:
            telecharger(URL.format(uid), chemin, ctx, etat)
            ok += 1
        except urllib.error.HTTPError as e:
            err += 1
            print(f"  {uid} : HTTP {e.code}", file=sys.stderr)
        except Exception as e:
            err += 1
            print(f"  {uid} : {e}", file=sys.stderr)
        print(f"\r{n}/{len(ids)}  téléchargés {ok}  déjà là {deja}  erreurs {err}", end="", flush=True)
        time.sleep(args.pause)
    print()

if __name__ == "__main__":
    main()

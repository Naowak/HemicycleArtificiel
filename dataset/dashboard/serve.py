#!/usr/bin/env python3
"""Lance le dashboard en local : python3 dashboard/serve.py  (puis http://localhost:8000)

Sert les fichiers de dashboard/ et, sous /data/, ceux de data/dashboard/.
Bibliothèque standard uniquement (Python 3.7+). N'écoute que sur 127.0.0.1.
Options : --port 8000, --no-browser
"""
import argparse, functools, http.server, os, posixpath, threading, urllib.parse, webbrowser

ICI = os.path.dirname(os.path.abspath(__file__))
DONNEES = os.path.join(os.path.dirname(ICI), "data", "dashboard")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".json": "application/json", ".css": "text/css", ".svg": "image/svg+xml"}

    def translate_path(self, path):
        chemin = posixpath.normpath(urllib.parse.unquote(urllib.parse.urlsplit(path).path))
        if chemin == "/data" or chemin.startswith("/data/"):
            parties = [p for p in chemin[len("/data"):].split("/") if p and p not in (".", "..")]
            return os.path.join(DONNEES, *parties)
        return super().translate_path(path)

    def log_message(self, fmt, *args):  # journal discret : seulement les erreurs
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(DONNEES, "meta.json")):
        print("Données absentes : téléchargez l'archive des données et dézippez-la à la racine du dépôt\n"
              f"(le fichier {os.path.join(DONNEES, 'meta.json')} doit exister). Voir le README.")
        return
    serveur = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), functools.partial(Handler, directory=ICI))
    url = f"http://localhost:{args.port}/"
    print(f"Hémicycle : {url}   (Ctrl-C pour arrêter)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()

"""Évalue le copilote sur les dossiers synthétiques dont les écarts sont connus.

Usage (services lancés) : python evaluation/evaluer.py [--url http://localhost:8000] [--repetitions 3]
Les LLM ne sont pas déterministes : répéter chaque dossier donne une idée de la stabilité.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "copilote"))
from noyau import comparer  # noqa: E402

ATTENDUS = Path(__file__).parent / "attendus"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--repetitions", type=int, default=1)
    args = p.parse_args()
    lignes = []
    for f in sorted(ATTENDUS.glob("*.json")):
        attendus = json.loads(f.read_text(encoding="utf-8"))
        for i in range(args.repetitions):
            req = urllib.request.Request(f"{args.url}/dossiers/{attendus['dossier']}/brouillon", method="POST")
            with urllib.request.urlopen(req, timeout=300) as rep:
                resultat = json.loads(rep.read().decode("utf-8"))
            score = comparer(resultat, attendus)
            lignes.append({"dossier": attendus["dossier"], "essai": i + 1, **score})
            print(json.dumps(lignes[-1], ensure_ascii=False))
    (Path(__file__).parent / "resultats.json").write_text(json.dumps(lignes, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

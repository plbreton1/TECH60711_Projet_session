"""Adaptateur BOSS : seul module qui connaît l'API de BOSS.

Pour brancher le vrai BOSS (ou une autre plateforme), on remplace ce module ;
le reste du copilote ne change pas. Ici, il parle au faux BOSS du prototype.
"""
import json
import os
import urllib.request

BOSS_URL = os.getenv("BOSS_URL", "http://localhost:8001")


def _requete(methode: str, chemin: str, corps: dict | None = None):
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    req = urllib.request.Request(f"{BOSS_URL}{chemin}", data=donnees, method=methode,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as rep:
        return json.loads(rep.read().decode("utf-8"))


def lister_dossiers() -> list:
    return _requete("GET", "/dossiers")


def lire_dossier(dossier_id: str) -> dict:
    return _requete("GET", f"/dossiers/{dossier_id}")


def ecrire_note(dossier_id: str, auteur: str, texte: str, resume: str) -> dict:
    return _requete("POST", f"/dossiers/{dossier_id}/notes",
                    {"auteur": auteur, "texte": texte, "resume_souscripteur": resume})

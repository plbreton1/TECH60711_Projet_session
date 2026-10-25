"""Faux BOSS : API factice qui simule la plateforme de courtage.

Elle sert des dossiers synthétiques (fichiers JSON) et reçoit les notes approuvées.
Le format des dossiers est provisoire : il sera ajusté à la liste réelle des champs BOSS.
"""
import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DOSSIERS = Path(__file__).parent / "data" / "dossiers"
NOTES_ECRITES = Path(__file__).parent / "data" / "notes_ecrites"
NOTES_ECRITES.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Faux BOSS (simulation)")


def charger(dossier_id: str) -> dict:
    chemin = DOSSIERS / f"{dossier_id}.json"
    if not chemin.exists():
        raise HTTPException(404, f"Dossier {dossier_id} introuvable")
    dossier = json.loads(chemin.read_text(encoding="utf-8"))
    # Les notes déjà écrites par le copilote s'ajoutent à l'historique, comme dans BOSS.
    for f in sorted(NOTES_ECRITES.glob(f"{dossier_id}_*.json")):
        note = json.loads(f.read_text(encoding="utf-8"))
        dossier["notes_anterieures"].append({"id": note["id"], "date": note["date"], "auteur": note["auteur"], "texte": note["texte"]})
    return dossier


@app.get("/dossiers")
def lister():
    return [{"id": f.stem, "client": json.loads(f.read_text(encoding="utf-8"))["formulaire"]["emprunteur"]["nom"]}
            for f in sorted(DOSSIERS.glob("*.json"))]


@app.get("/dossiers/{dossier_id}")
def lire(dossier_id: str):
    return charger(dossier_id)


class NoteApprouvee(BaseModel):
    auteur: str
    texte: str
    resume_souscripteur: str = ""


@app.post("/dossiers/{dossier_id}/notes", status_code=201)
def ecrire_note(dossier_id: str, note: NoteApprouvee):
    charger(dossier_id)  # vérifie que le dossier existe
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    enregistrement = {"id": f"NOTE-{horodatage}", "date": datetime.now().date().isoformat(), **note.model_dump()}
    (NOTES_ECRITES / f"{dossier_id}_{horodatage}.json").write_text(json.dumps(enregistrement, ensure_ascii=False, indent=2), encoding="utf-8")
    return enregistrement

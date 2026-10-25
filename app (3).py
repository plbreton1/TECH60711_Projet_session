"""Service copilote : API qui génère le brouillon et gère l'approbation."""
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import boss_adaptateur as boss
from llm import appeler_llm
from noyau import ampleur_correction, construire_messages, note_en_texte, valider

DATA = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
for sous in ("brouillons", "corrections"):
    (DATA / sous).mkdir(parents=True, exist_ok=True)
JOURNAL = DATA / "journal_audit.jsonl"

app = FastAPI(title="Copilote du conseiller hypothécaire")


def journaliser(evenement: str, **details):
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"horodatage": datetime.now().isoformat(timespec="seconds"), "evenement": evenement, **details}, ensure_ascii=False) + "\n")


@app.get("/sante")
def sante():
    return {"statut": "ok", "mode_llm": os.getenv("LLM_MODE", "openai"), "modele": os.getenv("OPENAI_MODEL")}


@app.get("/dossiers")
def dossiers():
    return boss.lister_dossiers()


@app.get("/dossiers/{dossier_id}")
def dossier(dossier_id: str):
    return boss.lire_dossier(dossier_id)


@app.post("/dossiers/{dossier_id}/brouillon")
def generer_brouillon(dossier_id: str):
    dossier = boss.lire_dossier(dossier_id)
    debut = time.perf_counter()
    try:
        brut = appeler_llm(construire_messages(dossier), dossier)
    except Exception as e:  # erreur de clé, de modèle ou de format
        raise HTTPException(502, f"Échec de l'appel au LLM : {e}")
    resultat = valider(brut, dossier)
    resultat.update({
        "brouillon_id": uuid.uuid4().hex[:8],
        "dossier_id": dossier_id,
        "duree_s": round(time.perf_counter() - debut, 1),
        "mode_llm": os.getenv("LLM_MODE", "openai"),
        "modele": os.getenv("OPENAI_MODEL"),
        "note_texte": note_en_texte(resultat),
    })
    (DATA / "brouillons" / f"{resultat['brouillon_id']}.json").write_text(json.dumps(resultat, ensure_ascii=False, indent=2), encoding="utf-8")
    journaliser("brouillon_genere", dossier_id=dossier_id, brouillon_id=resultat["brouillon_id"], controles=resultat["controles"])
    return resultat


class Decision(BaseModel):
    conseiller: str
    approuver: bool
    note_texte: str
    resume_texte: str
    commentaire: str = ""


@app.post("/brouillons/{brouillon_id}/decision")
def decider(brouillon_id: str, decision: Decision):
    chemin = DATA / "brouillons" / f"{brouillon_id}.json"
    if not chemin.exists():
        raise HTTPException(404, "Brouillon introuvable")
    brouillon = json.loads(chemin.read_text(encoding="utf-8"))
    correction = {
        "brouillon_id": brouillon_id,
        "dossier_id": brouillon["dossier_id"],
        "approuve": decision.approuver,
        "ampleur_correction_note": ampleur_correction(brouillon["note_texte"], decision.note_texte),
        "ampleur_correction_resume": ampleur_correction(brouillon["resume"]["texte"], decision.resume_texte),
        "note_brouillon": brouillon["note_texte"],
        "note_finale": decision.note_texte,
        "commentaire": decision.commentaire,
    }
    (DATA / "corrections" / f"{brouillon_id}.json").write_text(json.dumps(correction, ensure_ascii=False, indent=2), encoding="utf-8")
    ecriture = None
    if decision.approuver:  # seule une note approuvée est écrite dans BOSS
        ecriture = boss.ecrire_note(brouillon["dossier_id"], decision.conseiller, decision.note_texte, decision.resume_texte)
    journaliser("decision", dossier_id=brouillon["dossier_id"], brouillon_id=brouillon_id, conseiller=decision.conseiller,
                approuve=decision.approuver, ampleur_correction_note=correction["ampleur_correction_note"])
    return {"approuve": decision.approuver, "ecriture_boss": ecriture, "ampleur_correction_note": correction["ampleur_correction_note"]}

"""Service copilote : API qui génère le brouillon et gère l'approbation."""
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

import boss_adaptateur as boss
from llm import appeler_llm
from noyau import ampleur_correction, construire_messages, inventaire_sources, note_en_texte, valider

DATA = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
TRANSCRIPTION_URL = os.getenv("TRANSCRIPTION_URL", "http://localhost:8002")
for sous in ("brouillons", "corrections", "appels"):
    (DATA / sous).mkdir(parents=True, exist_ok=True)
JOURNAL = DATA / "journal_audit.jsonl"

app = FastAPI(title="Copilote du conseiller hypothécaire")


def journaliser(evenement: str, **details):
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"horodatage": datetime.now().isoformat(timespec="seconds"), "evenement": evenement, **details}, ensure_ascii=False) + "\n")


def dossier_complet(dossier_id: str) -> dict:
    """Dossier lu dans BOSS + appels transcrits par le copilote.

    BOSS ne capte pas les appels : les transcriptions sont des données propres au copilote,
    conservées de son côté et ajoutées au dossier au moment de l'analyse.
    """
    dossier = boss.lire_dossier(dossier_id)
    for f in sorted((DATA / "appels" / dossier_id).glob("*.json")):
        dossier.setdefault("transcriptions", []).append(json.loads(f.read_text(encoding="utf-8")))
    return dossier


@app.get("/sante")
def sante():
    return {"statut": "ok", "mode_llm": os.getenv("LLM_MODE", "openai"), "modele": os.getenv("OPENAI_MODEL")}


@app.get("/dossiers")
def dossiers():
    return boss.lister_dossiers()


@app.get("/dossiers/{dossier_id}")
def dossier(dossier_id: str):
    return dossier_complet(dossier_id)


@app.get("/dossiers/{dossier_id}/sources")
def sources(dossier_id: str):
    """Texte de chaque source citable, pour afficher les extraits cités dans l'interface."""
    return inventaire_sources(dossier_complet(dossier_id))


@app.post("/dossiers/{dossier_id}/appels")
async def ajouter_appel(dossier_id: str, request: Request, consentement: bool = False, date: str = ""):
    """Reçoit l'audio d'un appel, le fait transcrire localement et l'ajoute au dossier."""
    if not consentement:  # RF-13 : aucune transcription sans consentement consigné
        raise HTTPException(400, "Le consentement du client à l'enregistrement doit être confirmé avant la transcription.")
    audio = await request.body()
    dossier = dossier_complet(dossier_id)
    req = urllib.request.Request(f"{TRANSCRIPTION_URL}/transcrire?langue=fr", data=audio, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=900) as rep:
            resultat = json.loads(rep.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise HTTPException(502, f"Le service de transcription ne répond pas : {e}")
    numero = len(dossier.get("transcriptions", [])) + 1
    transcription = {
        "id": f"T{numero}",
        "date": date or datetime.now().date().isoformat(),
        "type": "appel_client",
        "origine": f"audio transcrit localement (Whisper {resultat['modele']})",
        "consentement_enregistrement": True,
        "tours": [{"id": f"T{numero}-{i:02d}", "debut": s["debut"], "texte": s["texte"]}
                  for i, s in enumerate(resultat["segments"], start=1)],
    }
    dossier_appels = DATA / "appels" / dossier_id
    dossier_appels.mkdir(parents=True, exist_ok=True)
    (dossier_appels / f"T{numero}.json").write_text(json.dumps(transcription, ensure_ascii=False, indent=2), encoding="utf-8")
    journaliser("appel_transcrit", dossier_id=dossier_id, transcription=transcription["id"],
                duree_audio_s=resultat["duree_audio_s"], duree_traitement_s=resultat["duree_traitement_s"])
    return {**transcription, "duree_audio_s": resultat["duree_audio_s"], "duree_traitement_s": resultat["duree_traitement_s"]}


@app.post("/dossiers/{dossier_id}/brouillon")
def generer_brouillon(dossier_id: str):
    dossier = dossier_complet(dossier_id)
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

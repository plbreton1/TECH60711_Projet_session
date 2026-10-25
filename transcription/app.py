"""Service de transcription : Whisper exécuté localement (faster-whisper, sur le processeur).

L'audio ne quitte jamais la machine. Le modèle est téléchargé une seule fois au premier usage.
"""
import os
import tempfile
import time

from fastapi import FastAPI, HTTPException, Request
from faster_whisper import WhisperModel

MODELE = os.getenv("WHISPER_MODEL", "small")
app = FastAPI(title="Transcription Whisper (locale)")
_modele = None


def modele() -> WhisperModel:
    global _modele
    if _modele is None:  # chargement paresseux : le service démarre vite, le premier appel est plus long
        _modele = WhisperModel(MODELE, device="cpu", compute_type="int8")
    return _modele


@app.get("/sante")
def sante():
    return {"statut": "ok", "modele": MODELE, "charge": _modele is not None}


@app.post("/transcrire")
async def transcrire(request: Request, langue: str = "fr"):
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "Aucun fichier audio reçu")
    debut = time.perf_counter()
    with tempfile.NamedTemporaryFile(suffix=".audio") as f:
        f.write(audio)
        f.flush()
        segments, info = modele().transcribe(f.name, language=langue, vad_filter=True)
        segments = [{"debut": round(s.start, 1), "fin": round(s.end, 1), "texte": s.text.strip()} for s in segments]
    return {"modele": MODELE, "duree_audio_s": round(info.duration, 1),
            "duree_traitement_s": round(time.perf_counter() - debut, 1), "segments": segments}

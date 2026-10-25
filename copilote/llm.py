"""Appel au modèle de langage.

LLM_MODE=openai : appel réel à l'API OpenAI (clé dans OPENAI_API_KEY, modèle dans OPENAI_MODEL).
LLM_MODE=fictif : réponse fixe, sans appel externe, pour tester la plomberie sans clé ni coût.
"""
import json
import os

from noyau import charger_config


def appeler_llm(messages: list, dossier: dict) -> dict:
    mode = os.getenv("LLM_MODE", "openai").lower()
    if mode == "fictif":
        return reponse_fictive(dossier)
    from openai import OpenAI  # importé ici pour que le mode fictif fonctionne sans le paquet

    modele = os.getenv("OPENAI_MODEL")
    if not os.getenv("OPENAI_API_KEY") or not modele:
        raise RuntimeError("OPENAI_API_KEY et OPENAI_MODEL doivent être définis dans le fichier .env (voir .env.example).")
    reponse = OpenAI().chat.completions.create(
        model=modele,
        messages=messages,
        response_format={"type": "json_object"},
    )
    return json.loads(reponse.choices[0].message.content)


def reponse_fictive(dossier: dict) -> dict:
    """Sortie fixe qui sert à tester l'interface et les contrôles. Elle ne démontre PAS l'IA."""
    gabarit, _, _ = charger_config()
    f = dossier["formulaire"]
    note = [{"section": s, "texte": f"[mode fictif] Contenu de la section « {s} ».", "sources": ["F:emprunteur.nom"]}
            for s in gabarit["sections"]]
    note[1]["texte"] = f"[mode fictif] {f['emploi']['poste']} chez {f['emploi']['employeur']} depuis {f['emploi']['depuis']}."
    note[1]["sources"] = ["F:emploi.poste", "F:emploi.employeur", "F:emploi.depuis"]
    return {
        "signalements": [
            {"type": "contexte", "champ": "emploi", "description": "[mode fictif] Vérifier la date d'embauche.",
             "sources": ["F:emploi.depuis"], "action": "Confirmer avec le client."},
            {"type": "manquant", "champ": "document:exemple", "description": "[mode fictif] Exemple de citation invalide, pour montrer le garde-fou.",
             "sources": ["X99"], "action": "Aucune."},
        ],
        "points_attention": [{"code": "stabilite_emploi", "constat": "[mode fictif] Exemple de point d'attention.", "sources": ["F:emploi"]}],
        "resume": {"texte": "[mode fictif] Résumé du dossier pour le souscripteur.", "sources": ["F:emprunteur.nom", "P:montant_demande"]},
        "note": note,
    }

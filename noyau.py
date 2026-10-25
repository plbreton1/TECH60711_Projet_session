"""Cœur du copilote, en Python standard (aucune dépendance externe).

- inventaire des sources du dossier, avec un identifiant citable pour chacune ;
- construction des messages envoyés au LLM ;
- vérification des sources citées (garde-fou contre les informations inventées) ;
- comparaison avec les écarts plantés (évaluation) ;
- mesure de l'écart entre le brouillon et la note approuvée (rétroaction).
"""
import difflib
import json
from pathlib import Path

CONFIG = Path(__file__).parent / "config"


def charger_config():
    gabarit = json.loads((CONFIG / "gabarit_note.json").read_text(encoding="utf-8"))
    points = json.loads((CONFIG / "points_attention.json").read_text(encoding="utf-8"))
    prompt = (CONFIG / "prompt_systeme.md").read_text(encoding="utf-8")
    return gabarit, points, prompt


# ---------- Sources ----------

def _aplatir(prefixe, valeur, sortie):
    if isinstance(valeur, dict):
        for cle, v in valeur.items():
            _aplatir(f"{prefixe}.{cle}" if prefixe else cle, v, sortie)
    elif isinstance(valeur, list):
        for i, v in enumerate(valeur):
            _aplatir(f"{prefixe}.{i}", v, sortie)
    else:
        sortie[prefixe] = valeur


def inventaire_sources(dossier: dict) -> dict:
    """Retourne {identifiant: texte} pour tout ce que le LLM a le droit de citer."""
    sources = {}
    champs = {}
    _aplatir("", dossier.get("formulaire", {}), champs)
    sources.update({f"F:{k}": v for k, v in champs.items()})
    produit = {}
    _aplatir("", dossier.get("produit_demande", {}), produit)
    sources.update({f"P:{k}": v for k, v in produit.items()})
    for n in dossier.get("notes_anterieures", []):
        sources[n["id"]] = f"Note du {n['date']} : {n['texte']}"
    for d in dossier.get("documents_deposes", []):
        sources[d["id"]] = f"Document déposé ({d['type']}, {d['date']}) : {d['description']}"
    for c in dossier.get("courriels", []):
        sources[c["id"]] = f"Courriel du {c['date']} ({c['de']}, « {c['objet']} ») : {c['corps']}"
    for t in dossier.get("transcriptions", []):
        for tour in t["tours"]:
            sources[tour["id"]] = f"Appel du {t['date']}, {tour['locuteur']} : {tour['texte']}"
    return sources


def source_valide(ident: str, sources: dict) -> bool:
    """Valide si l'identifiant existe, ou s'il désigne un groupe existant (ex. « F:emploi », « T1 »)."""
    if ident in sources:
        return True
    return any(cle.startswith(ident + ".") or cle.startswith(ident + "-") for cle in sources)


# ---------- Messages pour le LLM ----------

def construire_messages(dossier: dict) -> list:
    gabarit, points, prompt = charger_config()
    sources = inventaire_sources(dossier)
    lignes = "\n".join(f"[{k}] {v}" for k, v in sources.items())
    liste_points = "\n".join(f"- {p['code']} ({p['libelle']}) : {p['quand']}" for p in points["points"])
    docs = ", ".join(d["type"] for d in dossier.get("documents_deposes", [])) or "aucun"
    utilisateur = (
        f"Dossier {dossier['id']}.\n\n"
        f"SOURCES (cite uniquement ces identifiants) :\n{lignes}\n\n"
        f"Documents déjà déposés : {docs}\n\n"
        f"GABARIT DE LA NOTE (sections, dans l'ordre) : {', '.join(gabarit['sections'])}\n\n"
        f"POINTS D'ATTENTION AUTORISÉS :\n{liste_points}"
    )
    return [{"role": "system", "content": prompt}, {"role": "user", "content": utilisateur}]


# ---------- Contrôles après génération ----------

def _controler(element: dict, sources: dict) -> dict:
    citees = element.get("sources") or []
    invalides = [s for s in citees if not source_valide(s, sources)]
    element["sources_invalides"] = invalides
    element["non_source"] = len(citees) == len(invalides)  # aucune source valide
    return element


def valider(resultat: dict, dossier: dict) -> dict:
    """Ajoute à chaque élément les sources invalides et un drapeau « non_source »."""
    _, points, _ = charger_config()
    sources = inventaire_sources(dossier)
    codes = {p["code"] for p in points["points"]}
    for cle in ("signalements", "points_attention", "note"):
        resultat[cle] = [_controler(e, sources) for e in resultat.get(cle, [])]
    for p in resultat["points_attention"]:
        p["hors_liste"] = p.get("code") not in codes
    resultat["resume"] = _controler(resultat.get("resume") or {"texte": "", "sources": []}, sources)
    elements = resultat["signalements"] + resultat["points_attention"] + resultat["note"] + [resultat["resume"]]
    resultat["controles"] = {
        "elements": len(elements),
        "elements_non_sources": sum(e["non_source"] for e in elements),
        "citations_invalides": sum(len(e["sources_invalides"]) for e in elements),
        "points_hors_liste": sum(p["hors_liste"] for p in resultat["points_attention"]),
    }
    return resultat


def note_en_texte(resultat: dict) -> str:
    return "\n\n".join(f"{s['section']}\n{s['texte']}" for s in resultat.get("note", []))


# ---------- Évaluation ----------

def _correspond(attendu: dict, obtenu: dict) -> bool:
    # Correspondance sur le champ seulement : « contradiction » et « contexte » se chevauchent souvent.
    a, o = attendu["champ"].lower(), (obtenu.get("champ") or "").lower()
    return o == a or o.startswith(a + ".") or o.startswith(a + "_")


def comparer(resultat: dict, attendus: dict) -> dict:
    """Rappel et précision des signalements et des points d'attention par rapport aux écarts plantés."""
    obtenus = resultat.get("signalements", [])
    trouves = [a["id"] for a in attendus["signalements"] if any(_correspond(a, o) for o in obtenus)]
    utiles = [o for o in obtenus if any(_correspond(a, o) for a in attendus["signalements"])]
    codes_obtenus = {p.get("code") for p in resultat.get("points_attention", [])}
    codes_attendus = set(attendus["points_attention"])
    ratio = lambda n, d: round(n / d, 2) if d else None
    return {
        "signalements_rappel": ratio(len(trouves), len(attendus["signalements"])),
        "signalements_precision": ratio(len(utiles), len(obtenus)),
        "ecarts_manques": [a["id"] for a in attendus["signalements"] if a["id"] not in trouves],
        "points_rappel": ratio(len(codes_obtenus & codes_attendus), len(codes_attendus)),
        "points_precision": ratio(len(codes_obtenus & codes_attendus), len(codes_obtenus)),
        "elements_non_sources": resultat.get("controles", {}).get("elements_non_sources"),
    }


# ---------- Rétroaction ----------

def ampleur_correction(brouillon: str, final: str) -> float:
    """0 = aucune modification, 1 = texte entièrement réécrit."""
    return round(1 - difflib.SequenceMatcher(None, brouillon, final).ratio(), 3)

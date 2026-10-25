"""Tests du cœur du copilote, sans réseau ni LLM : python -m unittest discover tests"""
import json
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "copilote"))
from llm import reponse_fictive  # noqa: E402
from noyau import comparer, construire_messages, inventaire_sources, source_valide, valider  # noqa: E402

DOSSIER = json.loads((RACINE / "faux_boss/data/dossiers/D-001.json").read_text(encoding="utf-8"))
ATTENDUS = json.loads((RACINE / "evaluation/attendus/D-001.json").read_text(encoding="utf-8"))


class TestNoyau(unittest.TestCase):
    def test_sources(self):
        s = inventaire_sources(DOSSIER)
        for ident in ("F:revenus.revenu_annuel_brut", "P:terme", "C1", "T1-05", "N1", "D2"):
            self.assertIn(ident, s)
        self.assertTrue(source_valide("F:emploi", s))   # groupe de champs
        self.assertTrue(source_valide("T1", s))         # transcription entière
        self.assertFalse(source_valide("C9", s))

    def test_attendus_jamais_dans_le_prompt(self):
        texte = json.dumps(construire_messages(DOSSIER), ensure_ascii=False)
        self.assertNotIn("E1", texte.replace("Érables", ""))
        self.assertNotIn("lettre_de_don", texte)

    def test_garde_fou_sources(self):
        r = valider(reponse_fictive(DOSSIER), DOSSIER)
        self.assertEqual(r["controles"]["elements_non_sources"], 1)  # la citation « X99 » volontairement invalide
        self.assertEqual(r["controles"]["citations_invalides"], 1)

    def test_evaluation_parfaite(self):
        ideal = {"signalements": [{"type": a["type"], "champ": a["champ"], "sources": ["C1"]} for a in ATTENDUS["signalements"]],
                 "points_attention": [{"code": c, "sources": ["T1"]} for c in ATTENDUS["points_attention"]],
                 "note": [], "resume": {"texte": "", "sources": ["F:emploi"]}}
        score = comparer(valider(ideal, DOSSIER), ATTENDUS)
        self.assertEqual((score["signalements_rappel"], score["signalements_precision"], score["points_rappel"]), (1.0, 1.0, 1.0))

    def test_evaluation_mode_fictif(self):
        score = comparer(valider(reponse_fictive(DOSSIER), DOSSIER), ATTENDUS)
        self.assertLess(score["signalements_rappel"], 0.5)  # la réponse fixe ne détecte presque rien


if __name__ == "__main__":
    unittest.main()

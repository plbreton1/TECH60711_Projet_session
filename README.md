# Copilote du conseiller hypothécaire — prototype

Prototype du travail de session TECH 60711 (HEC Montréal). Le copilote aide le conseiller à **consolider** un dossier (faits tirés des échanges, informations manquantes, contradictions), puis à le **transmettre** au souscripteur (note-client et résumé avec points d'attention). Le conseiller relit, corrige et approuve ; seule une note approuvée est écrite dans BOSS.

> Données entièrement synthétiques. BOSS est simulé par une API factice.

## Parcours démontré

0. (Facultatif) Le conseiller enregistre ou téléverse un appel avec le client, après avoir confirmé son consentement. L'appel est transcrit **localement** par Whisper : l'audio ne quitte pas le poste. BOSS ne capte pas les appels ; c'est une valeur ajoutée du copilote.
1. Le copilote lit le dossier dans le faux BOSS (formulaire, produit, notes, documents, courriels) et y ajoute les appels transcrits.
2. Le LLM produit les signalements, les points d'attention, le résumé et le brouillon de note. Chaque élément cite ses sources.
3. Le copilote vérifie les sources citées : un élément sans source valide est marqué « non sourcé » (garde-fou contre les informations inventées).
4. Le conseiller corrige dans l'interface, puis approuve ou rejette.
5. Si la note est approuvée, elle est écrite dans le faux BOSS. L'ampleur de la correction est enregistrée pour l'évaluation.

## Architecture

```
interface (Streamlit, :8501) ──► copilote (FastAPI, :8000) ──► faux BOSS (FastAPI, :8001)
                                      │
                                      ├──► transcription (Whisper local, :8002)
                                      └──► API OpenAI (LLM)
```

| Dossier | Contenu |
|---|---|
| `faux_boss/` | API factice et dossiers synthétiques (`data/dossiers/*.json`) |
| `copilote/` | Service copilote. `boss_adaptateur.py` est le **seul** module qui connaît BOSS. |
| `copilote/noyau.py` | Sources citables, messages au LLM, contrôles, évaluation (Python standard) |
| `copilote/config/` | Gabarit de note, points d'attention et prompt système (provisoires) |
| `transcription/` | Service Whisper local (faster-whisper, sur le processeur) |
| `interface/` | Écran du conseiller, en parcours guidé de 4 étapes |
| `evaluation/` | Écarts plantés dans chaque dossier (`attendus/`) et script d'évaluation |
| `tests/` | Tests du cœur, sans réseau ni LLM |

## Lancer le prototype

Prérequis : Docker Desktop.

1. Copier `.env.example` sous le nom `.env`.
2. Créer **votre propre** clé sur https://platform.openai.com/api-keys et la mettre dans `OPENAI_API_KEY`.
3. Indiquer le nom exact du modèle dans `OPENAI_MODEL` (liste : https://platform.openai.com/docs/models).
4. Lancer :

   ```bash
   docker compose up --build
   ```

5. Ouvrir http://localhost:8501.

La première transcription télécharge le modèle Whisper (quelques centaines de Mo, une seule fois, conservé dans `transcription/modeles/`). Sur un ordinateur ordinaire, un appel de deux minutes se transcrit en environ une minute avec le modèle `small`. Pour aller plus vite, mettre `WHISPER_MODEL=base` dans `.env`.

Pour tester sans clé : `LLM_MODE=fictif` dans `.env`. Le copilote renvoie alors une réponse fixe : utile pour vérifier l'installation, mais **ne démontre pas l'IA**.

Le fichier `.env` ne doit jamais être versionné (il est dans `.gitignore`).

## Évaluer

Chaque dossier synthétique contient des écarts plantés volontairement, décrits dans `evaluation/attendus/`. Ces fichiers ne sont jamais envoyés au copilote.

```bash
python evaluation/evaluer.py --repetitions 3
```

Le script mesure, pour chaque dossier :
- le **rappel** des signalements : part des écarts plantés détectés ;
- la **précision** : part des signalements qui correspondent à un écart planté ;
- le rappel et la précision des points d'attention ;
- le nombre d'éléments **non sourcés**, à garder à zéro (l'erreur la plus grave est une information inventée).

Répéter les essais donne une idée de la stabilité : un LLM ne répond pas toujours la même chose.

Tests du cœur : `python -m unittest discover tests`

## Correspondance avec les requis fonctionnels

| Requis | Dans le prototype |
|---|---|
| RF-01 Extraction des courriels et documents | Oui |
| RF-02 Transcription des appels | Oui : enregistrement ou fichier audio, Whisper local. D-001 contient aussi un appel déjà transcrit. |
| RF-03 Brouillon de note-client | Oui |
| RF-04 Traçabilité des sources | Oui, avec vérification automatique des citations |
| RF-05 / RF-06 Manques et contradictions | Oui |
| RF-07 Résumé pour le souscripteur | Oui |
| RF-10 / RF-12 Lecture et écriture BOSS | Simulées (faux BOSS) |
| RF-11 Relecture et approbation | Oui |
| RF-15 Journal d'audit | Partiel (`copilote/data/journal_audit.jsonl`) |
| RF-16 Capture des corrections | Oui (`copilote/data/corrections/`) |
| RF-13 Consentement | Partiel : case obligatoire avant toute transcription |
| RF-17 Temps de réponse | Mesuré et affiché |

## Limites et écarts avec la solution complète

- **BOSS simulé** : le format des dossiers est une hypothèse, à ajuster à la liste réelle des champs BOSS. Seul `boss_adaptateur.py` changerait.
- **Pas de connexion au système téléphonique** : le conseiller enregistre ou téléverse l'appel. La connexion directe (Teams, centrale téléphonique) fait partie de la vision complète.
- **Locuteurs non identifiés** : Whisper découpe l'appel en segments horodatés sans savoir qui parle. Les sources sont donc citées par horodatage (ex. « T2-04 (01:32) »).
- **Consentement simplifié** : une case à cocher, sans preuve conservée ni gestion de la durée de conservation de l'audio.
- **Pas d'authentification** (RF-14).
- **Fournisseur de LLM** : OpenAI pour le prototype, avec des données synthétiques. Le choix pour la production dépend de la Loi 25 et du lieu d'hébergement des données.
- **Gabarit, points d'attention et prompt provisoires** : à valider par l'équipe et, idéalement, par des souscripteurs.
- **Peu de dossiers** : les mesures d'évaluation sont indicatives, pas statistiquement solides.
- **Le contrôle des sources vérifie qu'une source existe, pas qu'elle appuie vraiment l'affirmation.** C'est pourquoi la relecture humaine reste obligatoire.

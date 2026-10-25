"""Interface du conseiller : un parcours guidé en étapes.

1. Ajouter un appel (facultatif)  2. Analyser le dossier  3. Consolider  4. Transmettre et approuver
"""
import os

import requests
import streamlit as st

API = os.getenv("COPILOTE_URL", "http://localhost:8000")

st.set_page_config(page_title="Copilote du conseiller", page_icon=":material/assignment_turned_in:", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1200px;}
  .etapes {display: flex; gap: .5rem; margin: .25rem 0 1.25rem; flex-wrap: wrap;}
  .etape {padding: .35rem .8rem; border-radius: 999px; font-size: .85rem; border: 1px solid #C9D2DC; color: #5C6670;}
  .etape.fait {background: #E3EFE6; border-color: #7FA37A; color: #2E5A2B;}
  .etape.encours {background: #1F3A5F; border-color: #1F3A5F; color: #FFFFFF;}
  .aide {color: #5C6670; font-size: .95rem; margin-top: -.5rem;}
</style>
""", unsafe_allow_html=True)


# ---------- Accès au copilote ----------

def api(methode, chemin, **kwargs):
    try:
        rep = requests.request(methode, f"{API}{chemin}", timeout=kwargs.pop("timeout", 60), **kwargs)
    except requests.ConnectionError:
        st.error("Le service copilote ne répond pas. Vérifiez que `docker compose up` tourne toujours.")
        st.stop()
    if not rep.ok:
        try:
            detail = rep.json().get("detail", rep.text)
        except ValueError:
            detail = rep.text
        return None, detail
    return rep.json(), None


def etat(cle, defaut=None):
    return st.session_state.get(cle, defaut)


# ---------- Barre latérale : choix du dossier ----------

dossiers, _ = api("GET", "/dossiers")
sante, _ = api("GET", "/sante")

with st.sidebar:
    st.markdown("### Dossier")
    choix = st.selectbox("Dossier client", dossiers, format_func=lambda d: f"{d['id']} · {d['client']}", label_visibility="collapsed")
    if etat("dossier_id") != choix["id"]:  # nouveau dossier : on repart à zéro
        for cle in ("res", "decision", "derniere_transcription"):
            st.session_state.pop(cle, None)
        st.session_state["dossier_id"] = choix["id"]

    dossier, _ = api("GET", f"/dossiers/{choix['id']}")
    f, prod = dossier["formulaire"], dossier["produit_demande"]
    st.markdown(f"**{f['emprunteur']['nom']}**  \n{prod['type']} · {prod['terme']}")
    c1, c2 = st.columns(2)
    c1.metric("Montant demandé", f"{prod['montant_demande']:,} $".replace(",", " "))
    c2.metric("Prix d'achat", f"{f['propriete']['prix_achat']:,} $".replace(",", " "))
    st.caption(f"Au dossier : {len(dossier.get('courriels', []))} courriel(s) · {len(dossier.get('transcriptions', []))} appel(s) · "
               f"{len(dossier.get('documents_deposes', []))} document(s) · {len(dossier.get('notes_anterieures', []))} note(s)")

    st.divider()
    mode = sante["mode_llm"]
    if mode == "fictif":
        st.warning("Mode fictif : réponses fixes pour tester l'application. Elles ne démontrent pas l'IA.", icon=":material/science:")
    else:
        st.caption(f"Modèle : {sante.get('modele') or 'non défini'}")
    with st.expander("Comment ça marche"):
        st.markdown(
            "1. **Ajoutez un appel** (facultatif) : il est transcrit sur votre poste.\n"
            "2. **Analysez** : le copilote lit tout le dossier.\n"
            "3. **Consolidez** : traitez les manques et les contradictions.\n"
            "4. **Transmettez** : relisez la note et le résumé, puis approuvez.\n\n"
            "Chaque affirmation cite sa source. Rien n'est écrit dans BOSS sans votre approbation.")

sources, _ = api("GET", f"/dossiers/{choix['id']}/sources")
res = etat("res")

# ---------- En-tête et progression ----------

st.title("Copilote du conseiller hypothécaire")
st.markdown('<p class="aide">Consolidez le dossier, puis transmettez-le au souscripteur. '
            "Vous gardez le contrôle : rien n'est écrit dans BOSS sans votre approbation.</p>", unsafe_allow_html=True)

statuts = ["fait" if dossier.get("transcriptions") else "",
           "fait" if res else "encours",
           "fait" if res and etat("decision") else ("encours" if res else ""),
           "fait" if etat("decision") else ("encours" if res else "")]
noms = ["1. Ajouter un appel", "2. Analyser", "3. Consolider", "4. Transmettre et approuver"]
st.markdown('<div class="etapes">' + "".join(f'<span class="etape {s}">{n}</span>' for n, s in zip(noms, statuts)) + "</div>",
            unsafe_allow_html=True)


def extraits(ids):
    """Affiche le texte des sources citées, pour vérifier d'un coup d'œil."""
    for i in ids or []:
        trouves = [(k, v) for k, v in sources.items() if k == i or k.startswith(i + ".") or k.startswith(i + "-")]
        if not trouves:
            st.markdown(f"- :red[**{i}** : source introuvable dans le dossier]")
        for k, v in trouves:
            st.markdown(f"- **{k}** : {v}")


# ---------- Étape 1 : ajouter un appel ----------

with st.container(border=True):
    st.subheader(":material/call: 1. Ajouter un appel avec le client", anchor=False)
    st.caption("Facultatif. Enregistrez ou téléversez l'appel : il est transcrit localement par Whisper, sans quitter votre poste, "
               "puis ajouté aux sources du dossier.")
    consentement = st.checkbox("Le client a consenti à l'enregistrement et à l'analyse de cet appel")
    t_enr, t_fic = st.tabs(["Enregistrer au micro", "Téléverser un fichier"])
    with t_enr:
        enregistrement = st.audio_input("Enregistrer l'appel", disabled=not consentement, label_visibility="collapsed")
    with t_fic:
        fichier = st.file_uploader("Fichier audio", type=["wav", "mp3", "m4a", "ogg", "webm"], disabled=not consentement,
                                   label_visibility="collapsed")
    audio = fichier or enregistrement
    if not consentement:
        st.caption(":material/lock: Cochez le consentement pour activer l'enregistrement et la transcription.")
    if st.button("Transcrire et ajouter au dossier", icon=":material/graphic_eq:", disabled=not (consentement and audio)):
        with st.spinner("Transcription en cours… La première fois, le modèle Whisper se télécharge : comptez quelques minutes."):
            t, err = api("POST", f"/dossiers/{choix['id']}/appels", params={"consentement": "true"},
                         data=audio.getvalue(), headers={"Content-Type": "application/octet-stream"}, timeout=900)
        if err:
            st.error(err)
        else:
            st.session_state["derniere_transcription"] = t
            st.session_state.pop("res", None)  # le dossier a changé : l'analyse doit être refaite
            st.rerun()
    t = etat("derniere_transcription")
    if t:
        st.success(f"Appel {t['id']} ajouté : {len(t['tours'])} segment(s), {t['duree_audio_s']} s d'audio "
                   f"transcrites en {t['duree_traitement_s']} s.", icon=":material/check_circle:")
    for tr in dossier.get("transcriptions", []):
        with st.expander(f"Appel {tr['id']} du {tr['date']}" + (" · transcrit dans l'app" if tr.get("origine") else "")):
            for tour in tr["tours"]:
                moment = f"`{int(tour['debut']) // 60:02d}:{int(tour['debut']) % 60:02d}` " if "debut" in tour else ""
                qui = f"**{tour['locuteur']}** : " if tour.get("locuteur") else ""
                st.markdown(f"{moment}{qui}{tour['texte']}  \n:gray[{tour['id']}]")

# ---------- Étape 2 : analyser ----------

with st.container(border=True):
    st.subheader(":material/search_insights: 2. Analyser le dossier", anchor=False)
    st.caption("Le copilote lit le formulaire, les courriels, les appels, les notes et les documents. "
               "Il repère les écarts et prépare la note et le résumé, en citant ses sources.")
    if st.button("Analyser le dossier", type="primary", icon=":material/auto_awesome:"):
        with st.spinner("Analyse du dossier en cours…"):
            r, err = api("POST", f"/dossiers/{choix['id']}/brouillon", timeout=300)
        if err:
            st.error(f"L'analyse a échoué : {err}")
            st.caption("Si l'erreur concerne la clé, le modèle ou les crédits OpenAI, vérifiez le fichier .env. "
                       "Pour tester sans crédits, mettez LLM_MODE=fictif puis relancez Docker.")
        else:
            st.session_state["res"] = r
            st.session_state.pop("decision", None)
            st.rerun()
    if res:
        c = res["controles"]
        m = st.columns(4)
        m[0].metric("Écarts signalés", len(res["signalements"]))
        m[1].metric("Éléments sans source", c["elements_non_sources"], help="Doit rester à 0 : un élément sans source valide peut être inventé.")
        m[2].metric("Citations introuvables", c["citations_invalides"])
        m[3].metric("Durée", f"{res['duree_s']} s")

if not res:
    st.info("Lancez l'analyse (étape 2) pour voir les écarts, la note et le résumé.", icon=":material/arrow_upward:")
    st.stop()

# ---------- Étape 3 : consolider ----------

with st.container(border=True):
    st.subheader(":material/fact_check: 3. Consolider : ce qui manque ou se contredit", anchor=False)
    st.caption("Traitez chaque écart avant de transmettre le dossier. Cochez-les au fur et à mesure.")
    ordre = {"contradiction": 0, "manquant": 1, "contexte": 2}
    libelle = {"contradiction": ":red-background[Contradiction]", "manquant": ":orange-background[Information manquante]",
               "contexte": ":blue-background[Contexte à préciser]"}
    signalements = sorted(res["signalements"], key=lambda s: ordre.get(s.get("type"), 3))
    if not signalements:
        st.success("Aucun écart détecté. Relisez quand même la note avant de l'approuver.")
    faits = 0
    for i, s in enumerate(signalements):
        with st.container(border=True):
            gauche, droite = st.columns([5, 1])
            gauche.markdown(f"{libelle.get(s.get('type'), s.get('type'))} &nbsp; **{s.get('champ', '')}**")
            fait = droite.checkbox("Traité", key=f"traite_{res['brouillon_id']}_{i}")
            faits += fait
            st.markdown(s.get("description", ""))
            st.markdown(f":material/arrow_forward: **Action proposée** : {s.get('action', '')}")
            if s.get("non_source"):
                st.warning("Aucune source valide : à vérifier avant usage.", icon=":material/warning:")
            with st.expander("Voir les extraits cités"):
                extraits(s.get("sources"))
    if signalements:
        st.progress(faits / len(signalements), text=f"{faits} écart(s) traité(s) sur {len(signalements)}")

# ---------- Étape 4 : transmettre et approuver ----------

with st.container(border=True):
    st.subheader(":material/send: 4. Transmettre au souscripteur", anchor=False)
    st.caption("Relisez et corrigez au besoin. Ce que vous approuvez est écrit dans le dossier BOSS.")
    gauche, droite = st.columns([2, 3])
    with gauche:
        st.markdown("**Points d'attention**")
        if not res["points_attention"]:
            st.caption("Aucun point d'attention particulier.")
        for p in res["points_attention"]:
            with st.container(border=True):
                st.markdown(f"**{p.get('libelle')}**" + (" :orange[(hors liste)]" if p.get("hors_liste") else ""))
                st.markdown(p.get("constat", ""))
                with st.expander("Sources"):
                    extraits(p.get("sources"))
    with droite:
        resume = st.text_area("Résumé pour le souscripteur", res["resume"].get("texte", ""), height=200)
        with st.expander("Sources du résumé"):
            extraits(res["resume"].get("sources"))

    note = st.text_area("Note-client", res["note_texte"], height=380)
    with st.expander("Sources de chaque section de la note"):
        for s in res["note"]:
            st.markdown(f"**{s['section']}**" + (" :red[(non sourcé)]" if s.get("non_source") else ""))
            extraits(s.get("sources"))

    st.divider()
    a, b = st.columns(2)
    conseiller = a.text_input("Conseiller responsable", "Conseiller test")
    commentaire = b.text_input("Commentaire (facultatif)")
    nb_ecarts = len(res["signalements"])
    if nb_ecarts and faits < nb_ecarts:
        st.caption(f":material/info: {nb_ecarts - faits} écart(s) pas encore coché(s) comme traité(s). Vous pouvez quand même approuver.")
    c1, c2, _ = st.columns([2, 2, 3])
    for colonne, approuver in ((c1, True), (c2, False)):
        texte = "Approuver et écrire dans BOSS" if approuver else "Rejeter le brouillon"
        if colonne.button(texte, type="primary" if approuver else "secondary",
                          icon=":material/check:" if approuver else ":material/close:", disabled=bool(etat("decision"))):
            d, err = api("POST", f"/brouillons/{res['brouillon_id']}/decision",
                         json={"conseiller": conseiller, "approuver": approuver, "note_texte": note,
                               "resume_texte": resume, "commentaire": commentaire})
            if err:
                st.error(err)
            else:
                st.session_state["decision"] = d
                st.rerun()

    d = etat("decision")
    if d and d["approuve"]:
        st.success(f"Note écrite dans le dossier BOSS ({d['ecriture_boss']['id']}). "
                   f"Vous avez modifié {d['ampleur_correction_note']:.0%} du brouillon : cette correction servira à améliorer le copilote.",
                   icon=":material/task_alt:")
    elif d:
        st.info("Brouillon rejeté. Rien n'a été écrit dans BOSS.", icon=":material/block:")

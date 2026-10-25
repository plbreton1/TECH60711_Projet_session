"""Interface du conseiller : consolider le dossier, puis le transmettre au souscripteur."""
import os

import requests
import streamlit as st

API = os.getenv("COPILOTE_URL", "http://localhost:8000")
st.set_page_config(page_title="Copilote du conseiller", layout="wide")
st.title("Copilote du conseiller hypothécaire")
st.caption("Prototype · données synthétiques · BOSS simulé")

dossiers = requests.get(f"{API}/dossiers", timeout=30).json()
choix = st.sidebar.selectbox("Dossier", dossiers, format_func=lambda d: f"{d['id']} · {d['client']}")
sante = requests.get(f"{API}/sante", timeout=30).json()
st.sidebar.write(f"Mode LLM : **{sante['mode_llm']}**" + (f" ({sante['modele']})" if sante.get("modele") else ""))

with st.expander("Dossier dans BOSS (lecture)"):
    st.json(requests.get(f"{API}/dossiers/{choix['id']}", timeout=30).json())

if st.button("Générer le brouillon", type="primary"):
    with st.spinner("Le copilote analyse le dossier…"):
        rep = requests.post(f"{API}/dossiers/{choix['id']}/brouillon", timeout=180)
    if rep.ok:
        st.session_state["res"] = rep.json()
    else:
        st.error(rep.json().get("detail", rep.text))

res = st.session_state.get("res")
if res and res["dossier_id"] == choix["id"]:
    c = res["controles"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Durée", f"{res['duree_s']} s")
    m2.metric("Éléments sans source valide", c["elements_non_sources"])
    m3.metric("Citations invalides", c["citations_invalides"])
    m4.metric("Points hors liste", c["points_hors_liste"])

    def sources(e):
        txt = "Sources : " + ", ".join(e.get("sources") or ["aucune"])
        if e.get("sources_invalides"):
            txt += f" · ⚠ introuvables : {', '.join(e['sources_invalides'])}"
        return txt

    gauche, droite = st.columns(2)
    with gauche:
        st.subheader("1. Consolider le dossier")
        style = {"contradiction": st.error, "manquant": st.warning, "contexte": st.info}
        for s in res["signalements"]:
            style.get(s["type"], st.info)(
                f"**{s['type'].capitalize()} · {s['champ']}**\n\n{s['description']}\n\n"
                f"➜ Action proposée : {s['action']}\n\n_{sources(s)}_"
                + ("\n\n⚠ **Non sourcé : à vérifier avant usage.**" if s["non_source"] else ""))
    with droite:
        st.subheader("2. Transmettre au souscripteur")
        st.markdown("**Points d'attention**")
        for p in res["points_attention"]:
            st.markdown(f"- **{p['code']}** : {p['constat']}  \n  _{sources(p)}_" + (" ⚠ hors liste" if p["hors_liste"] else ""))
        resume = st.text_area("Résumé pour le souscripteur", res["resume"]["texte"], height=140)
        st.caption(sources(res["resume"]))

    st.subheader("Note-client (brouillon modifiable)")
    with st.expander("Sources par section"):
        for s in res["note"]:
            st.markdown(f"- **{s['section']}** : {sources(s)}" + (" ⚠ non sourcé" if s["non_source"] else ""))
    note = st.text_area("Note", res["note_texte"], height=360, label_visibility="collapsed")

    conseiller = st.text_input("Conseiller responsable", "Conseiller test")
    commentaire = st.text_input("Commentaire (optionnel)")
    a, r = st.columns(2)
    for bouton, approuver in ((a, True), (r, False)):
        if bouton.button("Approuver et écrire dans BOSS" if approuver else "Rejeter le brouillon", type="primary" if approuver else "secondary"):
            rep = requests.post(f"{API}/brouillons/{res['brouillon_id']}/decision", timeout=60,
                                json={"conseiller": conseiller, "approuver": approuver, "note_texte": note,
                                      "resume_texte": resume, "commentaire": commentaire}).json()
            if approuver:
                st.success(f"Note écrite dans BOSS ({rep['ecriture_boss']['id']}). Ampleur de correction : {rep['ampleur_correction_note']:.0%}")
            else:
                st.info("Brouillon rejeté. Rien n'a été écrit dans BOSS.")

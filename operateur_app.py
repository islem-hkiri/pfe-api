import streamlit as st
import requests
import pandas as pd
from streamlit_autorefresh import st_autorefresh

API_URL = "https://pfe-api-uju4.onrender.com"
st.set_page_config(page_title="Poste Opérateur")
st_autorefresh(interval=5000, key="main_refresh")

with st.sidebar:
    st.title("Session")
    id_op = st.text_input("ID Opérateur", "OP-01")
    shift = st.radio("Shift", ["A", "B"], horizontal=True)

st.title(f"👨‍🔧 Poste Soudure - Shift {shift}")

try:
    # Fetch tasks sorted by server priority[cite: 6]
    response = requests.get(f"{API_URL}/api/operateur_tasks?shift={shift}")
    if response.status_code == 200:
        tasks = response.json().get("tasks", [])
        if tasks:
            for t in tasks:
                with st.expander(f"📦 {t['reference']} - {t['statut']} ({t['urgence']})"):
                    st.write(f"Quantité: {t['quantite']}")
                    if "attente" in t['statut'].lower():
                        if st.button("▶️ Lancer Production", key=f"start_{t['id']}"):
                            requests.post(f"{API_URL}/api/start_production", 
                                          json={"demande_id": t['id'], "operateur_id": id_op})
                            st.rerun()
                    elif "cours" in t['statut'].lower():
                        st.warning("⚠️ En cours de traitement sur la machine...")
        else:
            st.info("Aucune tâche disponible.")
except:
    st.error("Connexion au serveur API impossible.")
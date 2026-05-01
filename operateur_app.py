import streamlit as st
import requests
import pandas as pd
from streamlit_autorefresh import st_autorefresh

API_URL = "https://pfe-api-uju4.onrender.com"

st.set_page_config(page_title="Poste Soudure Ultrasons")
# Auto-refresh kima el CDC yheb (Vitesse: Mise à jour instantanée[cite: 1])
st_autorefresh(interval=5000, key="main_refresh")

# ==========================
# SIDEBAR (Identification & Pannes)
# ==========================
with st.sidebar:
    st.title("Identification")
    id_op_saisie = st.text_input("ID Operateur", value="OP01")
    shift = st.radio("Shift", ["A", "B"], horizontal=True)

    st.subheader("Signalement Panne")
    cause = st.text_input("Cause de la panne")

    if st.button("Signaler Panne"):
        if cause and id_op_saisie:
            try:
                requests.post(f"{API_URL}/api/signal_panne", json={
                    "operateur_id": id_op_saisie,
                    "cause": cause
                })
                st.error("Panne signalée ✅")
            except:
                st.error("Erreur connexion API")
        else:
            st.warning("ID + cause obligatoires")

# ==========================
# TITRE
# ==========================
st.title(f"Poste Soudure Ultrasons - Shift {shift}")

# ==========================
# RECUPERATION TACHES (File d'attente intelligente[cite: 1])
# ==========================
try:
    # 1. Njibou el khedma mel API Render[cite: 3]
    response = requests.get(f"{API_URL}/api/operateur_tasks?shift={shift}")
    
    if response.status_code == 200:
        tasks = response.json().get("tasks", [])
        
        if tasks:
            for task in tasks:
                statut_label = task.get('statut', 'En attente')
                
                with st.expander(f"📦 {task['reference']} - {statut_label} (Urgence: {task['urgence']})"):
                    c1, c2 = st.columns(2)
                    with c1:
                        # Ken "En attente", nwarriw bouton "Lancer"[cite: 1]
                        if "attente" in statut_label.lower():
                            if st.button("▶️ Lancer Production", key=f"start_{task['id']}"):
                                requests.post(f"{API_URL}/api/start_production", 
                                            json={"demande_id": task['id'], "operateur_id": id_op_saisie})
                                st.rerun()
                    with c2:
                        # Ken "En cours", nwarriw bouton "Terminer"[cite: 3]
                        if "cours" in statut_label.lower():
                            if st.button("✅ Terminer", key=f"end_{task['id']}"):
                                requests.post(f"{API_URL}/api/terminer_production", 
                                            json={"demande_id": task['id']})
                                st.rerun()
        else:
            st.info("Tranquille! Ma fama 7atta khedma tawa.")
    else:
        st.error("Impossible de charger les tâches (API Error)")
except Exception as e:
    st.error(f"Mochkla fil connexion m3a l'API: {e}")
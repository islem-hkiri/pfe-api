import streamlit as st
import requests
import pandas as pd
from streamlit_autorefresh import st_autorefresh

API_URL = "https://pfe-api-uju4.onrender.com"

st.set_page_config(page_title="Poste Soudure Ultrasons")
st_autorefresh(interval=5000, key="main_refresh")

# ==========================
# SIDEBAR
# ==========================

with st.sidebar:
    st.title("Identification")
    id_op_saisie = st.text_input("ID Operateur")
    shift = st.radio("Shift", ["A", "B"], horizontal=True)

    st.subheader("Signalement Panne")

    cause = st.text_input("Cause de la panne")

    if st.button("Signaler Panne"):
        if cause and id_op_saisie:
            try:
                requests.post(
                    f"{API_URL}/api/signal_panne",
                    json={
                        "operateur_id": id_op_saisie,
                        "cause": cause
                    }
                )
                st.error("Panne signalée ✅")
            except:
                st.error("Erreur API")
        else:
            st.warning("ID + cause obligatoires")

# ==========================
# TITRE
# ==========================

st.title(f"Poste Soudure Ultrasons - Shift {shift}")

# ==========================
# RECUPERATION TACHES
# ==========================

# A remplacer fi operateur_app.py (Section récupération tâches)
try:
    # 1. Tjib el khedma s7i7a mel API mte3ek
    response = requests.get(f"{API_URL}/api/operateur_tasks?shift={shift}")
    
    if response.status_code == 200:
        tasks = response.json().get("tasks", [])
        
        if tasks:
            for task in tasks:
                # Synchronisation: kol task n7ottouha fi expander
                statut_label = task['statut']
                
                with st.expander(f"📦 {task['reference']} - {statut_label}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        # Ken "En attente", nwarriw bouton "Lancer"
                        if "attente" in statut_label.lower():
                            if st.button("▶️ Lancer Production", key=f"start_{task['id']}"):
                                # Hna el API lazem tbadal el statut l "En cours" 
                                # bech el Carte (WebSocket) tfiq biha
                                requests.post(f"{API_URL}/api/start_production", 
                                            json={"demande_id": task['id'], "operateur_id": id_op_saisie})
                                st.rerun()
                    with c2:
                        if "cours" in statut_label.lower():
                            if st.button("✅ Terminer", key=f"end_{task['id']}"):
                                requests.post(f"{API_URL}/api/terminer_production", 
                                            json={"demande_id": task['id']})
                                st.rerun()
        else:
            st.info("Tranquille! Ma fama 7atta khedma tawa.")
except:
    st.error("Mochkla fil connexion m3a el API Operateu")
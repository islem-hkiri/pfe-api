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

try:
    response = requests.get(
        f"{API_URL}/api/operateur_tasks?shift={shift}"
    )

    if response.status_code == 200:
        tasks = response.json().get("tasks", [])

        if tasks:
            for task in tasks:
                id_d = task["id"]
                module = task.get("module", task.get("reference", ""))
                qte = task["quantite"]
                statut = task["statut"]

                with st.expander(f"{module} | Qte {qte} | ID {id_d}"):

                    col1, col2 = st.columns(2)

                    with col1:
                        if statut == "🟢En cours":
                            st.button("Production en cours", disabled=True)
                        else:
                            if st.button("Lancer production", key=f"start_{id_d}"):
                                requests.post(
                                    f"{API_URL}/api/start_production",
                                    json={
                                        "demande_id": id_d,
                                        "operateur_id": id_op_saisie
                                    }
                                )
                                st.rerun()

                    with col2:
                        if st.button("Terminer", key=f"end_{id_d}"):
                            requests.post(
                                f"{API_URL}/api/terminer_production",
                                json={"demande_id": id_d}
                            )
                            st.rerun()

                    if "En attente" in statut:
                        st.warning("🟠 EN ATTENTE")
                    elif "En cours" in statut:
                        st.error("🟢 EN COURS")

        else:
            st.success("Aucune tâche active")

    else:
        st.error("Erreur API")

except Exception as e:
    st.error("Impossible de charger les tâches")
import streamlit as st
import requests
import pandas as pd
from streamlit_autorefresh import st_autorefresh

API_URL = "https://pfe-api-uju4.onrender.com"

st.set_page_config(page_title="Poste Soudure Ultrasons")
st_autorefresh(interval=5000, key="main_refresh")

# ═══════════════════════════════════════════════════════════════════
# FONCTIONS API
# ═══════════════════════════════════════════════════════════════════

def get_tasks_api(shift):
    try:
        response = requests.get(f"{API_URL}/api/operateur_tasks?shift={shift}", timeout=10)
        if response.status_code == 200:
            return response.json().get("tasks", [])
    except Exception as e:
        st.error(f"Erreur connexion API: {e}")
    return []

def start_production_api(demande_id, operateur_id):
    try:
        response = requests.post(
            f"{API_URL}/api/start_production",
            json={"demande_id": demande_id, "operateur_id": operateur_id},
            timeout=10
        )
        return response.status_code == 200
    except:
        return False

def terminer_production_api(demande_id):
    try:
        response = requests.post(
            f"{API_URL}/api/terminer_production",
            json={"demande_id": demande_id},
            timeout=10
        )
        return response.status_code == 200
    except:
        return False

def signal_panne_api(operateur_id, cause):
    try:
        response = requests.post(
            f"{API_URL}/api/signal_panne",
            json={"operateur_id": operateur_id, "cause": cause},
            timeout=10
        )
        return response.status_code == 200
    except:
        return False

def set_shift_api(shift):
    try:
        response = requests.post(
            f"{API_URL}/api/set_shift",
            json={"shift": shift},
            timeout=5
        )
        return response.status_code == 200
    except:
        return False

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("Identification")
    id_op_saisie = st.text_input("ID Operateur")

    # --- SHIFT SELECTOR ---
    # Initialiser le shift dans session_state si pas encore fait
    if "active_shift" not in st.session_state:
        st.session_state.active_shift = "A"

    shift = st.radio("Shift", ["A", "B"], 
                     index=["A", "B"].index(st.session_state.active_shift),
                     horizontal=True)

    # Ki tbaddel shift → notify API + update session
    if shift != st.session_state.active_shift:
        if set_shift_api(shift):
            st.session_state.active_shift = shift
            st.success(f"✅ Shift changé vers {shift}")
        else:
            st.warning("⚠️ Impossible de notifier l'API")
            # Revert visuellement au shift précédent
            shift = st.session_state.active_shift

    st.divider()

    # --- SIGNALEMENT PANNE (toujours visible dans la sidebar) ---
    st.subheader("🔧 Signalement Panne")
    cause = st.text_input("Cause de la panne")

    if st.button("Signaler Panne"):
        if cause and id_op_saisie:
            if signal_panne_api(id_op_saisie, cause):
                st.success("Panne signalée ✅")
            else:
                st.error("Erreur API")
        else:
            st.warning("ID + cause obligatoires")

# Utiliser toujours le shift actif depuis session_state
active_shift = st.session_state.get("active_shift", "A")

# ═══════════════════════════════════════════════════════════════════
# TITRE
# ═══════════════════════════════════════════════════════════════════

st.title(f"Poste Soudure Ultrasons — Shift {active_shift}")

# ═══════════════════════════════════════════════════════════════════
# RÉCUPÉRATION TÂCHES (mel shift actif)
# ═══════════════════════════════════════════════════════════════════

tasks = get_tasks_api(active_shift)

if tasks:
    for task in tasks:
        id_d = task["id"]
        module = task.get("reference", "N/A")
        qte = task["quantite"]
        statut = task["statut"]
        urgence = task.get("urgence", "Normal")

        # Couleur selon urgence
        if urgence == "Critique":
            border_color = "#ff4b4b"
        elif urgence == "Urgent":
            border_color = "#ffa421"
        else:
            border_color = "#262730"

        with st.expander(f"{module} | Qte {qte} | ID {id_d} | {urgence}"):
            st.markdown(f"""
                <div style='border-left: 4px solid {border_color}; padding-left: 10px;'>
                    <b>Référence:</b> {module}<br>
                    <b>Quantité:</b> {qte}<br>
                    <b>Urgence:</b> {urgence}<br>
                    <b>Statut:</b> {statut}
                </div>
            """, unsafe_allow_html=True)

            col1, col2 = st.columns(2)

            with col1:
                if "En cours" in statut:
                    st.button("Production en cours", disabled=True, key=f"disabled_{id_d}")
                else:
                    if st.button("Lancer production", key=f"start_{id_d}"):
                        if id_op_saisie:
                            if start_production_api(id_d, id_op_saisie):
                                st.success("Production démarrée !")
                                st.rerun()
                            else:
                                st.error("Erreur lors du démarrage")
                        else:
                            st.warning("Entrez votre ID d'abord !")

            with col2:
                if st.button("Terminer", key=f"end_{id_d}"):
                    if terminer_production_api(id_d):
                        st.success("Production terminée !")
                        st.rerun()
                    else:
                        st.error("Erreur lors de la terminaison")

            if "En attente" in statut:
                st.warning("🟠 EN ATTENTE")
            elif "En cours" in statut:
                st.info("🟢 EN COURS")

elif tasks == []:
    st.success("✅ Aucune tâche active pour ce shift")
else:
    st.error("Erreur lors du chargement des tâches")
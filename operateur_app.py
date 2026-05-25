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

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("Identification")
    id_op_saisie = st.text_input("ID Operateur")
    shift = st.radio("Shift", ["A", "B"], horizontal=True)

    st.subheader("Signalement Panne")
    cause = st.text_input("Cause de la panne")

    if st.button("Signaler Panne"):
        if cause and id_op_saisie:
            if signal_panne_api(id_op_saisie, cause):
                st.success("Panne signalée ✅")
            else:
                st.error("Erreur API")
        else:
            st.warning("ID + cause obligatoires")

# ═══════════════════════════════════════════════════════════════════
# TITRE
# ═══════════════════════════════════════════════════════════════════

st.title(f"Poste Soudure Ultrasons - Shift {shift}")

# ═══════════════════════════════════════════════════════════════════
# RECUPERATION TACHES (mil API)
# ═══════════════════════════════════════════════════════════════════

URGENCE_PRIORITY = {"Critique": 3, "Urgent": 2, "Normal": 1}

def get_priority_task(tasks):
    """Retourne la tâche avec la plus haute urgence qui n'est pas encore en cours."""
    pending = [t for t in tasks if "En cours" not in t.get("statut", "")]
    if not pending:
        return None
    return max(pending, key=lambda t: URGENCE_PRIORITY.get(t.get("urgence", "Normal"), 1))

tasks = get_tasks_api(shift)

# Trier les tâches par urgence (Critique > Urgent > Normal)
if tasks:
    tasks = sorted(tasks, key=lambda t: URGENCE_PRIORITY.get(t.get("urgence", "Normal"), 1), reverse=True)
    priority_task = get_priority_task(tasks)
    priority_id = priority_task["id"] if priority_task else None

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

        is_priority = (id_d == priority_id)
        priority_badge = " 🎯 PRIORITÉ" if is_priority else ""
        expander_label = f"{module} | Qte {qte} | ID {id_d} | {urgence}{priority_badge}"

        with st.expander(expander_label, expanded=is_priority):
            st.markdown(f"""
                <div style='border-left: 4px solid {border_color}; padding-left: 10px;'>
                    <b>Référence:</b> {module}<br>
                    <b>Quantité:</b> {qte}<br>
                    <b>Urgence:</b> {urgence}<br>
                    <b>Statut:</b> {statut}
                </div>
            """, unsafe_allow_html=True)

            if is_priority and "En cours" not in statut:
                st.info("⚡ C'est la tâche prioritaire — lancez celle-ci en premier !")

            col1, col2 = st.columns(2)

            with col1:
                if "En cours" in statut:
                    st.button("Production en cours", disabled=True, key=f"disabled_{id_d}")
                else:
                    btn_label = "🚀 Lancer (PRIORITÉ)" if is_priority else "Lancer production"
                    if st.button(btn_label, key=f"start_{id_d}", type="primary" if is_priority else "secondary"):
                        if id_op_saisie:
                            # Lancer toujours la tâche prioritaire en premier
                            target_id = priority_id if priority_id else id_d
                            if start_production_api(target_id, id_op_saisie):
                                if target_id != id_d:
                                    st.warning(f"⚡ Tâche prioritaire (ID {target_id}) lancée automatiquement !")
                                else:
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
    st.success("Aucune tâche active")
else:
    st.error("Erreur lors du chargement des tâches")
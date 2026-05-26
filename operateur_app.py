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
# AUTO-LANCEMENT: lance automatiquement la tâche la plus urgente
# si aucune n'est en cours et qu'un opérateur est identifié
# ═══════════════════════════════════════════════════════════════════

def auto_lancer_premiere_tache(tasks, operateur_id):
    """
    Ki ma kaynch tâche En cours,
    tlanca automatiquement l'awla tâche (akther urgence) fil liste.
    """
    if not operateur_id:
        return False

    # Vérifier si une tâche est déjà en cours
    en_cours = any("En cours" in t.get("statut", "") for t in tasks)
    if en_cours:
        return False

    # Prendre la première tâche en attente (déjà triée par urgence côté API)
    premiere = next((t for t in tasks if "En attente" in t.get("statut", "") or t.get("statut", "") == "En attente"), None)
    if not premiere:
        return False

    # Lancer automatiquement
    success = start_production_api(premiere["id"], operateur_id)
    return success

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("Identification")
    id_op_saisie = st.text_input("ID Operateur")
    shift = st.radio("Shift", ["A", "B"], horizontal=True)

    if "last_shift" not in st.session_state:
        st.session_state.last_shift = shift

    if shift != st.session_state.last_shift:
        try:
            requests.post(f"{API_URL}/api/set_shift", json={"shift": shift}, timeout=5)
            st.session_state.last_shift = shift
            st.success(f"✅ Shift changé vers {shift}")
        except:
            st.warning("⚠️ Impossible de notifier l'ESP32")

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
# RECUPERATION TACHES (trié par urgence côté API)
# ═══════════════════════════════════════════════════════════════════

tasks = get_tasks_api(shift)

if tasks:

    # ─── AUTO-LANCEMENT ───────────────────────────────────────────
    # Ki kayn ID opérateur w ma kaynch tâche en cours →
    # tlanca automatiquement l'awla tâche (akther urgence)
    if id_op_saisie:
        auto_key = f"auto_launched_{shift}"
        en_cours_exists = any("En cours" in t.get("statut", "") for t in tasks)

        if not en_cours_exists and not st.session_state.get(auto_key):
            launched = auto_lancer_premiere_tache(tasks, id_op_saisie)
            if launched:
                st.session_state[auto_key] = True
                st.toast("🚀 Tâche la plus urgente lancée automatiquement !", icon="✅")
                st.rerun()
        elif en_cours_exists:
            # Reset le flag ki la tâche en cours est terminée
            st.session_state[auto_key] = False
    # ──────────────────────────────────────────────────────────────

    for task in tasks:
        id_d = task["id"]
        module = task.get("reference", "N/A")
        qte = task["quantite"]
        statut = task["statut"]
        urgence = task.get("urgence", "Normal")

        # Couleur + badge selon urgence
        if urgence == "Critique":
            border_color = "#ff4b4b"
            badge = "🔴 CRITIQUE"
        elif urgence == "Urgent":
            border_color = "#ffa421"
            badge = "🟠 URGENT"
        else:
            border_color = "#262730"
            badge = "🟢 NORMAL"

        # Indiquer visuellement la tâche active (en cours)
        is_en_cours = "En cours" in statut
        expander_label = f"{'▶️ ' if is_en_cours else ''}{module} | Qté {qte} | ID {id_d} | {badge}"

        with st.expander(expander_label, expanded=is_en_cours):
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
                if is_en_cours:
                    st.button("▶️ Production en cours", disabled=True, key=f"disabled_{id_d}")
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
                if st.button("Terminer ✅", key=f"end_{id_d}"):
                    if terminer_production_api(id_d):
                        # Reset auto-launch flag → prochaine tâche sera lancée auto
                        st.session_state[f"auto_launched_{shift}"] = False
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
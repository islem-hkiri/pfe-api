import streamlit as st
import requests
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh

# Configuration
st.set_page_config(page_title="Logistique - Supervision", layout="wide")

API_URL = "https://pfe-api-uju4.onrender.com"

# AUTO REFRESH (5 secondes)
st_autorefresh(interval=5000, key="log_refresh")

# SIDEBAR & KPI
st.sidebar.title("Tableau de Bord")

# 1. Récupération des données via API (Render)
data = []
try:
    response = requests.get(f"{API_URL}/api/full_data", timeout=10)
    if response.status_code == 200:
        json_data = response.json()
        data = json_data.get("demandes", [])
    else:
        st.sidebar.error("Erreur de récupération des données API")
except Exception as e:
    st.sidebar.error(f"Erreur connexion API: {e}")

# 2. Calcul des métriques (KPI) directement depuis les données API
if data:
    df_all = pd.DataFrame(data)
    total = len(df_all)
    termine = len(df_all[df_all['statut'] == 'Terminé'])
    en_cours = len(df_all[df_all['statut'].str.contains('En cours', na=False)])
    en_attente = len(df_all[df_all['statut'].str.contains('En attente', na=False)])

    st.sidebar.metric("Total demandes", total)
    st.sidebar.metric("✅ Terminées", termine)
    st.sidebar.metric("🟢 En cours", en_cours)
    st.sidebar.metric("🟠 En attente", en_attente)
else:
    st.sidebar.info("Aucune donnée disponible")

st.sidebar.markdown("---")
st.sidebar.subheader("Performance (KPI)")

# KPI urgence
if data:
    df_urg = pd.DataFrame(data)
    urg_counts = df_urg[df_urg['statut'] != 'Terminé']['urgence'].value_counts()
    if not urg_counts.empty:
        st.sidebar.subheader("Répartition par urgence")
        st.sidebar.bar_chart(urg_counts)

# DECONNEXION
if st.sidebar.button("Déconnexion", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# INTERFACE PRINCIPALE
st.title("Demandes (Poste Soudure)")

# SECTION ALERTES PANNES (Objectif: Monitoring en direct)
st.subheader("Alertes de Panne en Temps Réel")

try:
    # On récupère les pannes depuis l'API (à adapter selon votre endpoint API si existant)
    # Ici on simule ou on utilise l'endpoint global
    if "pannes" in json_data:
        pannes = [p for p in json_data["pannes"] if p['statut'] == '🔴 Ouvert']
        if pannes:
            for p in pannes:
                st.error(f"**ALERTE PANNE**: {p['cause']} | Opérateur: {p['operateur_id']}")
        else:
            st.success("Aucune panne signalée.")
except:
    st.info("Système d'alertes prêt.")

# SUIVI DES FABRICATIONS (Objectif: Traçabilité)
st.markdown("---")
st.subheader("Suivi des fabrications en temps réel")

if data:
    df_suivi = pd.DataFrame(data)
    # Filtrer pour ne garder que ce qui n'est pas terminé
    df_active = df_suivi[df_suivi['statut'] != 'Terminé'].copy()
    
    if not df_active.empty:
        st.dataframe(df_active[["reference", "quantite", "urgence", "statut", "heure_demande"]], use_container_width=True)
    else:
        st.info("Aucune production active.")

# NOUVELLE DEMANDE (Objectif: Éliminer le papier[cite: 1])
st.markdown("---")
st.subheader("Nouvelle Demande de Production")

with st.form("form_demande"):
    ref = st.text_input("Référence")
    qte = st.number_input("Quantité", min_value=1, value=50)
    urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
    submit = st.form_submit_button("Envoyer la demande", use_container_width=True)
    
    if submit:
        try:
            res = requests.post(f"{API_URL}/api/create_demande", json={
                "reference": ref,
                "quantite": qte,
                "urgence": urg,
                "date_besoin": str(pd.Timestamp.now().date()),
                "shift": "B"
            })
            if res.status_code == 200:
                st.success("Demande envoyée!")
                st.rerun()
        except:
            st.error("Erreur lors de l'envoi")
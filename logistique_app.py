import streamlit as st
import requests  # Nsithom hna bech nkalmou Render
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Logistique - Supervision (Cloud)")

# --- URL DE TON API RENDER (A VÉRIFIER) ---
API_BASE = "https://pfe-api-uju4.onrender.com/api" 

# AUTO REFRESH (5 secondes)
st_autorefresh(interval=5000, key="log_refresh")

# --- SIDEBAR & KPI ---
st.sidebar.title("📊 Tableau de Bord (Render)")

# Fonction pour récupérer les données de l'API
def fetch_api_data(endpoint):
    try:
        response = requests.get(f"{API_BASE}/{endpoint}", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        return None
    return None

# Récupération des stats via API (Exemple si tu as un endpoint stats)
# Sinon on utilise les demandes pour calculer
all_demandes = fetch_api_data("get_demandes") # Endpoint à créer ou adapter

if all_demandes:
    df_all = pd.DataFrame(all_demandes)
    total = len(df_all)
    termine = len(df_all[df_all['statut'] == 'Terminé'])
    st.sidebar.metric("Total demandes", total)
    st.sidebar.metric("Terminées", termine)
else:
    st.sidebar.error("⚠️ Impossible de se connecter au serveur Render")

st.sidebar.markdown("---")
st.sidebar.subheader("🚀 Performance (KPI)")
st.sidebar.info("Données synchronisées avec le Cloud")

# --- INTERFACE PRINCIPALE ---
st.title("📦 Demandes (Poste Soudure)")

# --- SECTION ALERTES PANNES (Via API) ---
st.subheader("⚠️ Alertes de Panne en Temps Réel")
pannes = fetch_api_data("get_pannes") # Endpoint à créer sur ton FastAPI

if pannes:
    for p in pannes:
        if p['statut'] == '🔴 Ouvert':
            st.error(f"**ALERTE :** {p['cause']} (Par: {p['operateur_id']})")
            if st.button(f"Traiter {p['id']}"):
                requests.post(f"{API_BASE}/resolver_panne/{p['id']}")
                st.rerun()
else:
    st.success("✅ Aucune panne signalée.")

# --- SUIVI TEMPS RÉEL (C'est ça que tu voulais dans la vidéo) ---
st.subheader("🔄 Suivi des fabrications en temps réel (Serveur)")

if all_demandes:
    df_suivi = pd.DataFrame(all_demandes)
    # Filtrer uniquement ce qui est en cours ou en attente
    df_active = df_suivi[df_suivi['statut'].isin(['🟠En attente', '🟢En cours'])]
    if not df_active.empty:
        st.dataframe(df_active[["reference", "quantite", "urgence", "statut", "shift"]], use_container_width=True, hide_index=True)
    else:
        st.info("Aucune production active.")
else:
    st.warning("En attente de données du serveur...")

# --- PRÉPARATION DE COMMANDE ---
st.markdown("---")
st.subheader("🆕 Nouvelle Demande de Production")

if "panier" not in st.session_state:
    st.session_state.panier = []

# Pour le stock, on peut aussi l'appeler via API
stock_data = fetch_api_data("get_stock") 
if stock_data:
    refs = [s['reference'] for s in stock_data]
    c1, c2 = st.columns(2)
    with c1:
        ref_choisie = st.selectbox("Référence", refs)
        qte_voulue = st.number_input("Quantité", 1, 1000, 50)
    with c2:
        urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")

    if st.button("➕ Ajouter à la liste"):
        st.session_state.panier.append({
            "reference": ref_choisie,
            "quantite": qte_voulue,
            "urgence": urg,
            "date_besoin": str(date_b)
        })

# --- ENVOI AU MONTAGE (VERS RENDER) ---
if st.session_state.panier:
    st.write("📋 Liste en cours :")
    st.table(st.session_state.panier)
    
    if st.button("🚀 Envoyer au montage (Render)", type="primary"):
        success_count = 0
        for item in st.session_state.panier:
            # On envoie chaque item du panier au serveur Render
            payload = {
                "reference": item['reference'],
                "quantite": item['quantite'],
                "urgence": item['urgence'],
                "date_besoin": item['date_besoin'],
                "shift": "A" # Ou B selon ton choix
            }
            try:
                # Appeler ton endpoint FastAPI
                res = requests.post(f"{API_BASE}/create_demande", json=payload)
                if res.status_code == 200:
                    success_count += 1
            except:
                st.error(f"Erreur d'envoi pour {item['reference']}")

        if success_count > 0:
            st.success(f"✅ {success_count} demande(s) envoyée(s) avec succès !")
            st.session_state.panier = []
            st.rerun()
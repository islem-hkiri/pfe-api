import streamlit as st
import requests
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Logistique - Supervision (Cloud)")

# --- URL DE TON API RENDER ---
API_BASE = "https://pfe-api-uju4.onrender.com" 

# AUTO REFRESH (5 secondes)
st_autorefresh(interval=5000, key="log_refresh")

# --- FONCTIONS API ---
def fetch_api_data(endpoint):
    try:
        response = requests.get(f"{API_BASE}/{endpoint}", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        return None
    return None

def post_api_data(endpoint, payload):
    try:
        response = requests.post(f"{API_BASE}/{endpoint}", json=payload, timeout=5)
        return response.status_code == 200
    except Exception as e:
        return False

# --- SIDEBAR & KPI ---
st.sidebar.title("📊 Tableau de Bord (Render)")

# Récupération des données via API
all_demandes = fetch_api_data("get_demandes")

if all_demandes:
    df_all = pd.DataFrame(all_demandes)
    total = len(df_all)
    termine = len(df_all[df_all['statut'] == 'Terminé'])
    st.sidebar.metric("Total demandes", total)
    st.sidebar.metric("Terminées", termine)
    
    # KPI Temps moyen (si disponible)
    if 'debut_production' in df_all.columns and 'fin_production' in df_all.columns:
        df_termine = df_all[df_all['statut'] == 'Terminé']
        if not df_termine.empty:
            try:
                df_termine['duree'] = (pd.to_datetime(df_termine['fin_production']) - pd.to_datetime(df_termine['debut_production'])).dt.total_seconds()
                temps_moyen = int(df_termine['duree'].mean()) if not df_termine.empty and 'duree' in df_termine.columns else 0
                st.sidebar.metric("Temps moyen (s)", temps_moyen)
            except:
                st.sidebar.metric("Temps moyen (s)", "N/A")
        else:
            st.sidebar.metric("Temps moyen (s)", "0")
    else:
        st.sidebar.metric("Temps moyen (s)", "N/A")
else:
    st.sidebar.error("⚠️ Impossible de se connecter au serveur Render")
    st.sidebar.metric("Total demandes", "0")
    st.sidebar.metric("Terminées", "0")
    st.sidebar.metric("Temps moyen (s)", "0")

st.sidebar.markdown("---")
st.sidebar.subheader("🚀 Performance (KPI)")
st.sidebar.info("Données synchronisées avec le Cloud")

# KPI Taux d'Occupation (calculé depuis les demandes)
if all_demandes:
    df_all = pd.DataFrame(all_demandes)
    TEMPS_SHIFT_SEC = 8 * 3600
    
    try:
        df_termine_today = df_all[(df_all['statut'] == 'Terminé')]
        if 'fin_production' in df_all.columns and 'debut_production' in df_all.columns:
            df_termine_today = df_termine_today.copy()
            df_termine_today['duree'] = (pd.to_datetime(df_termine_today['fin_production']) - pd.to_datetime(df_termine_today['debut_production'])).dt.total_seconds()
            total_sec = df_termine_today['duree'].sum() if 'duree' in df_termine_today.columns else 0
            taux = (total_sec / TEMPS_SHIFT_SEC) * 100
            taux_clean = min(int(taux), 100)
            st.sidebar.metric("Taux d'Occupation Jour", f"{taux_clean}%")
            st.sidebar.progress(taux_clean / 100)
            if taux > 85:
                st.sidebar.warning("⚠️ Charge élevée détectée !")
        else:
            st.sidebar.metric("Taux d'Occupation Jour", "N/A")
    except:
        st.sidebar.metric("Taux d'Occupation Jour", "N/A")

# KPI Urgence
if all_demandes:
    df_all = pd.DataFrame(all_demandes)
    if 'urgence' in df_all.columns:
        df_urg = df_all.groupby('urgence').size().reset_index(name='total')
        st.sidebar.bar_chart(df_urg.set_index('urgence'))

# Historique (via API)
st.sidebar.markdown("---")
try:
    if all_demandes:
        df_all = pd.DataFrame(all_demandes)
        if 'heure_demande' in df_all.columns:
            df_hist = df_all.groupby('heure_demande').size().reset_index(name='Nb_Refs')
            df_hist = df_hist.sort_values('heure_demande', ascending=False).head(10)
            
            if st.sidebar.button("Vider l'historique", use_container_width=True):
                st.success("Historique vidé (via API)")
                st.rerun()
            
            for index, row in df_hist.iterrows():
                with st.sidebar.expander(f"Liste du {row['heure_demande']}"):
                    details = df_all[df_all['heure_demande'] == row['heure_demande']][['reference', 'quantite', 'statut']]
                    st.dataframe(details, use_container_width=True)
except Exception as e:
    st.sidebar.error(f"Erreur historique: {e}")

# --- INTERFACE PRINCIPALE ---
st.title("📦 Demandes (Poste Soudure)")

# --- SECTION ALERTES PANNES (Via API) ---
st.subheader("⚠️ Alertes de Panne en Temps Réel")

pannes = fetch_api_data("get_pannes")

if pannes:
    df_pannes = pd.DataFrame(pannes)
    df_alertes = df_pannes[df_pannes['statut'] == '🔴 Ouvert'] if 'statut' in df_pannes.columns else pd.DataFrame()
    
    if not df_alertes.empty:
        for index, row in df_alertes.iterrows():
            st.error(f"""
                **NOUVELLE ALERTE REÇUE**
                * **Message de l'Opérateur :** {row.get('cause', 'N/A')}
                * **Envoyé par :** {row.get('operateur_id', 'N/A')}
                * **Heure :** {row.get('debut_panne', 'N/A')}
            """)
        
        if st.button("✅ Confirmer la réception / Traiter"):
            for _, row in df_alertes.iterrows():
                post_api_data(f"resolver_panne/{row['id']}", {})
            st.success("L'alerte a été marquée comme traitée.")
            st.rerun()
    else:
        st.success("✅ Aucune panne signalée pour le moment.")
else:
    st.info("Système d'alertes prêt (en attente de messages...).")

# --- SUIVI TEMPS RÉEL ---
st.subheader("🔄 Suivi des fabrications en temps réel (Serveur)")

if all_demandes:
    df_suivi = pd.DataFrame(all_demandes)
    if 'statut' in df_suivi.columns:
        df_active = df_suivi[df_suivi['statut'].isin(['🟠En attente', '🟢En cours'])]
        if not df_active.empty:
            cols_to_show = [col for col in ["reference", "quantite", "urgence", "statut", "shift"] if col in df_active.columns]
            st.dataframe(df_active[cols_to_show], use_container_width=True, hide_index=True)
        else:
            st.info("Aucune production active.")
    else:
        st.info("Aucune donnée de suivi disponible.")
else:
    st.warning("En attente de données du serveur...")

# --- PRÉPARATION DE COMMANDE (PANIER) ---
st.markdown("---")
st.subheader("🆕 Nouvelle Demande de Production")

if "panier" not in st.session_state:
    st.session_state.panier = []

# Pour le stock, on appelle via API
stock_data = fetch_api_data("get_stock")

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        if stock_data:
            refs = [s['reference'] for s in stock_data]
            ref_choisie = st.selectbox("Référence", refs)
        else:
            ref_choisie = st.selectbox("Référence", ["Aucune donnée"])
        qte_voulue = st.number_input("Quantité totale souhaitée", 1, 10000, 50)
    with c2:
        urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")

    if st.button("➕ Ajouter à la liste", use_container_width=True):
        st.session_state.panier.append({
            "reference": ref_choisie,
            "quantite": qte_voulue,
            "urgence": urg,
            "date_besoin": str(date_b)
        })

# --- ENVOI AU MONTAGE (VERS RENDER) ---
if st.session_state.panier:
    st.write("📋 Liste en cours de préparation")
    st.dataframe(pd.DataFrame(st.session_state.panier), use_container_width=True)
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("❌ Annuler tout", use_container_width=True):
            st.session_state.panier = []
            st.rerun()
    with col_b2:
        if st.button("🚀 Envoyer au montage (Render)", type="primary", use_container_width=True):
            maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            success_count = 0
            
            for item in st.session_state.panier:
                # Calcul du besoin réel basé sur le stock
                stock_actuel = 0
                if stock_data:
                    for s in stock_data:
                        if s.get('reference') == item['reference']:
                            stock_actuel = s.get('quantite', 0)
                            break
                
                besoin_reel = max(0, item['quantite'] - stock_actuel)
                
                if besoin_reel > 0:
                    for s in ['A', 'B']:
                        payload = {
                            "reference": item['reference'],
                            "quantite": besoin_reel,
                            "date_besoin": item['date_besoin'],
                            "shift": s,
                            "statut": "🟠En attente",
                            "urgence": item['urgence'],
                            "heure_demande": maintenant
                        }
                        if post_api_data("create_demande", payload):
                            success_count += 1
                else:
                    st.warning(f"Stock suffisant pour {item['reference']}")

            if success_count > 0:
                st.success(f"✅ {success_count} demande(s) envoyée(s) avec succès !")
                st.session_state.panier = []
                st.rerun()

# --- SUPERVISION GRAPHIQUE ---
st.markdown("---")
st.subheader("📊 Historique de Production (Journalier)")

if all_demandes:
    df_all = pd.DataFrame(all_demandes)
    if 'fin_production' in df_all.columns and 'statut' in df_all.columns:
        df_termine = df_all[df_all['statut'] == 'Terminé'].copy()
        if not df_termine.empty:
            df_termine['jour'] = pd.to_datetime(df_termine['fin_production']).dt.date
            df_chart = df_termine.groupby('jour').size().reset_index(name='total')
            df_chart = df_chart.sort_values('jour')
            st.line_chart(df_chart.set_index('jour'))
        else:
            st.info("Aucune donnée terminée pour le moment.")
    else:
        st.info("En attente de données pour l'affichage du graphique.")
else:
    st.info("En attente de données du serveur...")
import requests
import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from database_v2 import init_db

# Configuration
st.set_page_config(page_title="Logistique - Supervision")

# API CONFIG
API_URL = "https://pfe-api-uju4.onrender.com"

# Paths Dynamiques (pour base locale fallback)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

if not os.path.exists(DB_PATH):
    init_db()

# AUTO REFRESH (5 secondes pour le temps réel)
st_autorefresh(interval=5000, key="log_refresh")

# ═══════════════════════════════════════════════════════════════════
# FONCTIONS API
# ═══════════════════════════════════════════════════════════════════

def get_demandes_api():
    try:
        response = requests.get(f"{API_URL}/api/get_demandes", timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.sidebar.error(f"API Error: {e}")
    return []

def get_pannes_api():
    try:
        response = requests.get(f"{API_URL}/api/get_pannes", timeout=10)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return []

def create_demande_api(data):
    try:
        response = requests.post(f"{API_URL}/api/create_demande", json=data, timeout=10)
        return response.status_code == 200
    except:
        return False

def resoudre_pannes_api():
    try:
        response = requests.post(f"{API_URL}/api/resoudre_pannes", timeout=10)
        return response.status_code == 200
    except:
        return False

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR & KPI (mil API)
# ═══════════════════════════════════════════════════════════════════

st.sidebar.title(" Tableau de Bord")

# Récupérer les données de l'API
demandes = get_demandes_api()

if demandes:
    df_demandes = pd.DataFrame(demandes)
    
    # KPI Total
    total = len(df_demandes)
    termine = len(df_demandes[df_demandes['statut'].str.contains('Terminé', na=False)])
    
    st.sidebar.metric("Total demandes", total)
    st.sidebar.metric("Terminées", termine)
    
    # KPI Temps moyen
    df_termines = df_demandes[df_demandes['statut'].str.contains('Terminé', na=False)]
    if not df_termines.empty and 'debut_production' in df_termines.columns and 'fin_production' in df_termines.columns:
        df_termines['duree'] = pd.to_datetime(df_termines['fin_production'], errors='coerce') - pd.to_datetime(df_termines['debut_production'], errors='coerce')
        duree_moyenne = df_termines['duree'].dt.total_seconds().mean()
        if pd.notna(duree_moyenne):
            st.sidebar.metric("Temps moyen (s)", int(duree_moyenne))
        else:
            st.sidebar.metric("Temps moyen (s)", "0")
    else:
        st.sidebar.metric("Temps moyen (s)", "0")
    
    # KPI Occupation
    st.sidebar.markdown("---")
    st.sidebar.subheader(" Performance (KPI)")
    TEMPS_SHIFT_SEC = 8 * 3600
    
    today = datetime.now().strftime('%Y-%m-%d')
    df_today = df_termines[df_termines['fin_production'].str.contains(today, na=False)] if 'fin_production' in df_termines.columns else pd.DataFrame()
    
    if not df_today.empty:
        df_today['duree_sec'] = df_today['duree'].dt.total_seconds()
        total_sec = df_today['duree_sec'].sum()
        taux = (total_sec / TEMPS_SHIFT_SEC) * 100
        taux_clean = min(int(taux), 100)
        st.sidebar.metric("Taux d'Occupation Jour", f"{taux_clean}%")
        st.sidebar.progress(taux_clean / 100)
        if taux > 85:
            st.sidebar.warning(" Charge élevée détectée !")
    else:
        st.sidebar.info("Attente de données de production...")
    
    # KPI Urgence
    if 'urgence' in df_demandes.columns:
        df_urg = df_demandes['urgence'].value_counts().reset_index()
        df_urg.columns = ['urgence', 'total']
        if not df_urg.empty:
            st.sidebar.bar_chart(df_urg.set_index("urgence"))
else:
    st.sidebar.metric("Total demandes", 0)
    st.sidebar.metric("Terminées", 0)
    st.sidebar.metric("Temps moyen (s)", "0")

# Historique
st.sidebar.markdown("---")
try:
    if demandes:
        df_hist = pd.DataFrame(demandes)
        if 'heure_demande' in df_hist.columns and 'statut' in df_hist.columns:
            df_hist = df_hist[~df_hist['statut'].str.contains('Archivé', na=False)]
            df_hist_group = df_hist.groupby('heure_demande').size().reset_index(name='Nb_Refs').tail(10)
            
            if not df_hist_group.empty:
                if st.sidebar.button("Vider l'historique", use_container_width=True):
                    # Archiver via API
                    conn_local = sqlite3.connect(DB_PATH)
                    conn_local.execute("UPDATE Demandes SET statut = 'Archivé' WHERE statut != 'Archivé'")
                    conn_local.commit()
                    conn_local.close()
                    st.rerun()
                
                for _, row in df_hist_group.iterrows():
                    with st.sidebar.expander(f"Liste du {row['heure_demande']}"):
                        details = df_hist[df_hist['heure_demande'] == row['heure_demande']][['reference', 'quantite', 'statut']]
                        st.dataframe(details, use_container_width=True)
except Exception as e:
    st.sidebar.error(f"Erreur historique: {e}")

# ═══════════════════════════════════════════════════════════════════
# INTERFACE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════

st.title(" Demandes (Poste Soudure)")

# --- ALERTES PANNES (mil API) ---
st.subheader(" Alertes de Panne en Temps Réel")

pannes = get_pannes_api()

if pannes:
    for panne in pannes:
        st.error(f"""
            **NOUVELLE ALERTE REÇUE**
            * **Message de l'Opérateur :** {panne.get('cause', 'N/A')}
            * **Envoyé par :** {panne.get('operateur_id', 'N/A')}
            * **Heure :** {panne.get('debut_panne', 'N/A')}
        """)
    
    if st.button(" Confirmer la réception / Traiter"):
        if resoudre_pannes_api():
            st.success("L'alerte a été marquée comme traitée.")
            st.rerun()
        else:
            st.error("Erreur lors de la résolution")
else:
    st.success(" Aucune panne signalée pour le moment.")

# --- SUIVI TEMPS RÉEL (mil API) ---
st.subheader(" Suivi des fabrications en temps réel")

try:
    if demandes:
        df_suivi = pd.DataFrame(demandes)
        df_suivi = df_suivi[df_suivi['statut'].str.contains('En attente|En cours', na=False, regex=True)]
        
        if not df_suivi.empty:
            cols = ['reference', 'quantite', 'urgence', 'statut', 'operateur_id']
            cols_dispo = [c for c in cols if c in df_suivi.columns]
            st.dataframe(df_suivi[cols_dispo], use_container_width=True, hide_index=True)
        else:
            st.success(" Aucune production en attente.")
    else:
        st.success(" Aucune production en attente.")
except Exception as e:
    st.error(f"Erreur de lecture du suivi: {e}")

# ═══════════════════════════════════════════════════════════════════
# PRÉPARATION DE COMMANDE (PANIER)
# ═══════════════════════════════════════════════════════════════════

if "panier" not in st.session_state:
    st.session_state.panier = []

st.markdown("---")
st.subheader(" Nouvelle Demande de Production")

# Récupérer stock localement
conn_local = sqlite3.connect(DB_PATH)
df_stock_info = pd.read_sql_query("SELECT reference, quantite FROM Stock", conn_local)
conn_local.close()

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        refs = df_stock_info['reference'].tolist() if not df_stock_info.empty else []
        if refs:
            ref_choisie = st.selectbox("Référence", refs)
        else:
            ref_choisie = st.text_input("Référence", "REF-001")
        qte_voulue = st.number_input("Quantité totale souhaitée", 1, 10000, 50)
    with c2:
        urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")

    if st.button(" Ajouter à la liste", use_container_width=True):
        st.session_state.panier.append({
            "reference": ref_choisie,
            "quantite": qte_voulue,
            "urgence": urg,
            "date_besoin": str(date_b)
        })
        st.success(f"{ref_choisie} ajouté !")
        st.rerun()

# AFFICHAGE PANIER + ENVOI
if st.session_state.panier:
    st.write("Liste en cours de préparation")
    st.dataframe(pd.DataFrame(st.session_state.panier), use_container_width=True)
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button(" Annuler tout", use_container_width=True):
            st.session_state.panier = []
            st.rerun()
    with col_b2:
        if st.button(" Envoyer au montage", type="primary", use_container_width=True):
            success_count = 0
            for item in st.session_state.panier:
                for s in ['A', 'B']:
                    data = {
                        "reference": item["reference"],
                        "quantite": item["quantite"],
                        "date_besoin": item["date_besoin"],
                        "shift": s,
                        "urgence": item["urgence"]
                    }
                    if create_demande_api(data):
                        success_count += 1
            
            st.session_state.panier = []
            if success_count > 0:
                st.success(f"Demandes envoyées avec succès ! ({success_count} créées)")
            else:
                st.error("Erreur lors de l'envoi des demandes")
            st.rerun()

# ═══════════════════════════════════════════════════════════════════
# SUPERVISION GRAPHIQUE (mil API)
# ═══════════════════════════════════════════════════════════════════

st.markdown("---")
st.subheader("📊 Historique de Production (Journalier)")

try:
    if demandes:
        df_chart = pd.DataFrame(demandes)
        df_term = df_chart[df_chart['statut'].str.contains('Terminé', na=False)]
        if 'fin_production' in df_term.columns:
            df_term['jour'] = pd.to_datetime(df_term['fin_production'], errors='coerce').dt.date
            df_chart_final = df_term.groupby('jour').size().reset_index(name='total')
            if not df_chart_final.empty:
                st.line_chart(df_chart_final.set_index("jour"))
            else:
                st.info("Aucune donnée terminée pour le moment.")
        else:
            st.info("Aucune donnée terminée pour le moment.")
    else:
        st.info("Aucune donnée terminée pour le moment.")
except Exception as e:
    st.info("En attente de données pour l'affichage du graphique.")
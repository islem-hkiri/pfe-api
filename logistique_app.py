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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

if not os.path.exists(DB_PATH):
    init_db()

st_autorefresh(interval=5000, key="log_refresh")

# ==========================
# SIDEBAR & KPI
# ==========================

st.sidebar.title(" Tableau de Bord")

# ✅ تعريف conn (كان ناقص)
conn = sqlite3.connect(DB_PATH)

# ✅ API call آمن (بدون KeyError)
try:
    response = requests.get("https://pfe-api-uju4.onrender.com/api/full_data")
    if response.status_code == 200:
        json_data = response.json()
        data = json_data.get("demandes", [])
    else:
        data = []
except:
    data = []

# KPI من قاعدة البيانات المحلية كما كان
total = conn.execute("SELECT COUNT(*) FROM Demandes").fetchone()[0]
termine = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut='Terminé'").fetchone()[0]

st.sidebar.metric("Total demandes", total)
st.sidebar.metric("Terminées", termine)

# KPI Temps moyen
df_time = pd.read_sql_query(
    "SELECT (strftime('%s', fin_production) - strftime('%s', debut_production)) as duree FROM Demandes WHERE statut='Terminé'",
    conn
)

if not df_time.empty and pd.notna(df_time['duree'].mean()):
    st.sidebar.metric("Temps moyen (s)", int(df_time['duree'].mean()))
else:
    st.sidebar.metric("Temps moyen (s)", "0")

st.sidebar.markdown("---")
st.sidebar.subheader(" Performance (KPI)")

TEMPS_SHIFT_SEC = 8 * 3600 

df_occ = pd.read_sql_query("""
SELECT SUM(strftime('%s', fin_production) - strftime('%s', debut_production)) as total_prod
FROM Demandes WHERE statut='Terminé' AND date(fin_production) = date('now')
""", conn)

if not df_occ.empty and df_occ['total_prod'].iloc[0] is not None:
    total_sec = df_occ['total_prod'].iloc[0]
    taux = (total_sec / TEMPS_SHIFT_SEC) * 100
    taux_clean = min(int(taux), 100)

    st.sidebar.metric("Taux d'Occupation Jour", f"{taux_clean}%")
    st.sidebar.progress(taux_clean / 100)
else:
    st.sidebar.info("Attente de données de production...")

# ==========================
# INTERFACE PRINCIPALE
# ==========================

st.title(" Demandes (Poste Soudure)")

# ==========================
# SUIVI TEMPS RÉEL
# ==========================

st.subheader(" Suivi des fabrications en temps réel")

try:
    query_suivi = """
    SELECT reference, quantite, urgence, statut, operateur_id
    FROM Demandes
    WHERE statut LIKE '%En attente%' OR statut LIKE '%En cours%'
    ORDER BY id DESC
    """
    encours_data = conn.execute(query_suivi).fetchall()

    if encours_data:
        df_suivi = pd.DataFrame(encours_data,
            columns=["Référence", "Qté", "Urgence", "État", "Opérateur"])
        st.dataframe(df_suivi, use_container_width=True, hide_index=True)
    else:
        st.success(" Aucune production en attente.")

except Exception as e:
    st.error(f"Erreur de lecture du suivi: {e}")

# ==========================
# PANIER
# ==========================

if "panier" not in st.session_state:
    st.session_state.panier = []

st.markdown("---")
st.subheader(" Nouvelle Demande de Production")

with st.container():
    c1, c2 = st.columns(2)

    with c1:
        df_stock_info = pd.read_sql_query(
            "SELECT reference, quantite FROM Stock", conn)
        refs = df_stock_info['reference'].tolist()
        ref_choisie = st.selectbox("Référence", refs)
        qte_voulue = st.number_input(
            "Quantité totale souhaitée", 1, 10000, 50)

    with c2:
        urg = st.selectbox(
            "Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")

    if st.button(" Ajouter à la liste"):
        st.session_state.panier.append({
            "Reference": ref_choisie,
            "Quantite": qte_voulue,
            "Urgence": urg,
            "Date_Besoin": str(date_b)
        })
        st.success(f"{ref_choisie} ajouté !")
        st.rerun()

# ==========================
# ENVOI DEMANDE
# ==========================

if st.session_state.panier:
    st.write("Liste en cours de préparation")
    st.dataframe(pd.DataFrame(st.session_state.panier),
                 use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        if st.button(" Annuler tout"):
            st.session_state.panier = []
            st.rerun()

    with col2:
        if st.button(" Envoyer au montage", type="primary"):
            for item in st.session_state.panier:
                try:
                    requests.post(
                        "https://pfe-api-uju4.onrender.com/api/create_demande",
                        json={
                            "reference": item["Reference"],
                            "quantite": item["Quantite"],
                            "date_besoin": item["Date_Besoin"],
                            "shift": "B",
                            "urgence": item["Urgence"]
                        },
                        timeout=10
                    )
                except Exception as e:
                    st.error(f"Erreur API: {e}")

            st.session_state.panier = []
            st.success("Demandes envoyées avec succès !")
            st.rerun()

# ==========================
# HISTORIQUE GRAPHIQUE
# ==========================

st.markdown("---")
st.subheader(" Historique de Production (Journalier)")

try:
    df_chart = pd.read_sql_query("""
        SELECT date(fin_production) as jour, COUNT(*) as total
        FROM Demandes WHERE statut='Terminé'
        GROUP BY jour ORDER BY jour
    """, conn)

    if not df_chart.empty:
        st.line_chart(df_chart.set_index("jour"))
    else:
        st.info("Aucune donnée terminée pour le moment.")

except:
    st.info("En attente de données pour l'affichage du graphique.")

conn.close()
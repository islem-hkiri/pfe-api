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

# ========== SIDEBAR & KPI ==========
st.sidebar.title("📊 Tableau de Bord")

conn = sqlite3.connect(DB_PATH)

# Stats complètes avec LIKE pour gérer les emojis
df_stats = pd.read_sql_query("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN statut LIKE '%En attente%' THEN 1 ELSE 0 END) as en_attente,
        SUM(CASE WHEN statut LIKE '%En cours%' THEN 1 ELSE 0 END) as en_cours,
        SUM(CASE WHEN statut LIKE '%Terminé%' THEN 1 ELSE 0 END) as termine
    FROM Demandes WHERE statut NOT LIKE '%Archivé%'
""", conn)

total = df_stats['total'].iloc[0]
en_attente = df_stats['en_attente'].iloc[0]
en_cours = df_stats['en_cours'].iloc[0]
termine = df_stats['termine'].iloc[0]

st.sidebar.metric("Total demandes", total)
st.sidebar.metric("🟠 En attente", en_attente)
st.sidebar.metric("🟢 En cours", en_cours)
st.sidebar.metric("✅ Terminées", termine)

# KPI Temps moyen
df_time = pd.read_sql_query("""
    SELECT (strftime('%s', fin_production) - strftime('%s', debut_production)) as duree
    FROM Demandes WHERE statut LIKE '%Terminé%'
""", conn)

if not df_time.empty and pd.notna(df_time['duree'].mean()):
    st.sidebar.metric("Temps moyen (s)", int(df_time['duree'].mean()))
else:
    st.sidebar.metric("Temps moyen (s)", "0")

st.sidebar.markdown("---")
st.sidebar.subheader("📈 Performance (KPI)")

TEMPS_SHIFT_SEC = 8 * 3600

df_occ = pd.read_sql_query("""
    SELECT SUM(strftime('%s', fin_production) - strftime('%s', debut_production)) as total_prod
    FROM Demandes WHERE statut LIKE '%Terminé%' AND date(fin_production) = date('now')
""", conn)

if not df_occ.empty and df_occ['total_prod'].iloc[0] is not None:
    total_sec = df_occ['total_prod'].iloc[0]
    taux = (total_sec / TEMPS_SHIFT_SEC) * 100
    taux_clean = min(int(taux), 100)
    st.sidebar.metric("Taux d'Occupation Jour", f"{taux_clean}%")
    st.sidebar.progress(taux_clean / 100)
    if taux > 85:
        st.sidebar.warning("⚠️ Charge élevée !")
else:
    st.sidebar.info("📭 En attente de production...")

# Chart Urgence
df_urg = pd.read_sql_query("""
    SELECT urgence, COUNT(*) as total
    FROM Demandes WHERE statut NOT LIKE '%Archivé%' GROUP BY urgence
""", conn)

if not df_urg.empty:
    st.sidebar.bar_chart(df_urg.set_index("urgence"))

# ========== INTERFACE PRINCIPALE ==========
st.title("📋 Demandes (Poste Soudure)")

# Alertes de Panne
st.subheader("🚨 Alertes de Panne en Temps Réel")

try:
    df_alertes = pd.read_sql_query("""
        SELECT operateur_id, cause, debut_panne, statut
        FROM Pannes WHERE statut = '🔴 Ouvert' ORDER BY id DESC
    """, conn)

    if not df_alertes.empty:
        for index, row in df_alertes.iterrows():
            st.error(f"**🚨 ALERTE**\n* Opérateur: {row['operateur_id']}\n* Message: {row['cause']}\n* Heure: {row['debut_panne']}")

        if st.button("✅ Confirmer / Traiter"):
            conn.execute("UPDATE Pannes SET statut = 'Résolu', fin_panne = datetime('now') WHERE statut = '🔴 Ouvert'")
            conn.commit()
            st.success("Alerte traitée!")
            st.rerun()
    else:
        st.success("✅ Aucune panne signalée")
except:
    st.info("Système d'alertes prêt...")

# Suivi Temps Réel
st.subheader("📡 Suivi des fabrications")

try:
    encours_data = conn.execute("""
        SELECT reference, quantite, urgence, statut, operateur_id
        FROM Demandes WHERE statut LIKE '%En attente%' OR statut LIKE '%En cours%' ORDER BY id DESC
    """).fetchall()

    if encours_data:
        df_suivi = pd.DataFrame(encours_data, columns=["Référence", "Qté", "Urgence", "État", "Opérateur"])
        st.dataframe(df_suivi, use_container_width=True, hide_index=True)
    else:
        st.success("✅ Aucune production en attente")
except:
    st.error("Erreur de lecture")

# ========== NOUVELLE COMMANDE ==========
st.markdown("---")
st.subheader("➕ Nouvelle Demande de Production")

if "panier" not in st.session_state:
    st.session_state.panier = []

c1, c2 = st.columns(2)
with c1:
    df_stock = pd.read_sql_query("SELECT reference FROM Stock", conn)
    ref_choisie = st.selectbox("Référence", df_stock['reference'].tolist())
    qte_voulue = st.number_input("Quantité", 1, 10000, 50)
with c2:
    urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
    date_b = st.date_input("Date de besoin")

if st.button("🛒 Ajouter à la liste"):
    st.session_state.panier.append({
        "Reference": ref_choisie,
        "Quantite": qte_voulue,
        "Urgence": urg,
        "Date_Besoin": str(date_b)
    })
    st.success(f"✅ {ref_choisie} ajouté!")
    st.rerun()

# Panier
if st.session_state.panier:
    st.markdown("### 📦 Liste en cours")
    st.dataframe(pd.DataFrame(st.session_state.panier))

    col_a, col_b = st.columns(2)
    with col_a:
        nb_a = conn.execute("SELECT COUNT(*) FROM Demandes WHERE shift='A' AND statut NOT LIKE '%Terminé%' AND statut NOT LIKE '%Archivé%'").fetchone()[0]
        st.info(f"📌 Shift A: **{nb_a}**")
    with col_b:
        nb_b = conn.execute("SELECT COUNT(*) FROM Demandes WHERE shift='B' AND statut NOT LIKE '%Terminé%' AND statut NOT LIKE '%Archivé%'").fetchone()[0]
        st.info(f"📌 Shift B: **{nb_b}**")

    shift_choisi = st.selectbox("🎯 Shift destinataire", ["A", "B"])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Annuler"):
            st.session_state.panier = []
            st.rerun()
    with col2:
        if st.button("📤 Envoyer", type="primary"):
            for item in st.session_state.panier:
                try:
                    requests.post("https://pfe-api-uju4.onrender.com/api/create_demande", json={
                        "reference": item["Reference"],
                        "quantite": item["Quantite"],
                        "date_besoin": item["Date_Besoin"],
                        "shift": shift_choisi,
                        "urgence": item["Urgence"]
                    }, timeout=10)
                except:
                    pass
            st.session_state.panier = []
            st.success(f"✅ Envoyé au Shift {shift_choisi}!")
            st.rerun()

# Historique
st.markdown("---")
st.subheader("📊 Historique (Journalier)")

df_chart = pd.read_sql_query("""
    SELECT date(fin_production) as jour, COUNT(*) as total
    FROM Demandes WHERE statut LIKE '%Terminé%' GROUP BY jour ORDER BY jour
""", conn)

if not df_chart.empty:
    st.line_chart(df_chart.set_index("jour"))
else:
    st.info("📭 En attente de données")

# Déconnexion
if st.sidebar.button("🚪 Déconnexion"):
    st.session_state.logged_in = False
    st.rerun()

conn.close()
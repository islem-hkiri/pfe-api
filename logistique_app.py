import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")
st.set_page_config(page_title="Logistique - Supervision")

# Auto-refresh pour voir les mises à jour en temps réel
st_autorefresh(interval=5000, key="log_refresh")

# Connexion base
conn = sqlite3.connect(DB_PATH)

# SIDEBAR - KPI
st.sidebar.title("📊 Tableau de Bord")

# Stats globales
total = conn.execute("SELECT COUNT(*) FROM Demandes").fetchone()[0]
termine = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut='Terminé'").fetchone()[0]
en_cours = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut='🟢En cours'").fetchone()[0]
en_attente = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut='🟠En attente'").fetchone()[0]

st.sidebar.metric("Total demandes", total)
st.sidebar.metric("✅ Terminées", termine)
st.sidebar.metric("🟢 En cours", en_cours)
st.sidebar.metric("🟠 En attente", en_attente)

# Temps moyen
df_time = pd.read_sql_query("""
    SELECT (strftime('%s', fin_production) - strftime('%s', debut_production)) as duree 
    FROM Demandes 
    WHERE statut='Terminé'
""", conn)

if not df_time.empty and pd.notna(df_time['duree'].mean()):
    st.sidebar.metric("⏱️ Temps moyen (s)", int(df_time['duree'].mean()))

# INTERFACE PRINCIPALE
st.title("📦 Logistique - Gestion des Demandes")

# SECTION 1: ALERTES PANNES (Messages des opérateurs)
st.subheader("🚨 Alertes de Panne en Temps Réel")
try:
    df_alertes = pd.read_sql_query("""
        SELECT operateur_id, cause, debut_panne, statut 
        FROM Pannes 
        WHERE statut = '🔴 Ouvert' 
        ORDER BY debut_panne DESC
    """, conn)

    if not df_alertes.empty:
        for index, row in df_alertes.iterrows():
            st.error(f"""
            **🚨 PANNE SIGNALÉE**
            - **Message:** {row['cause']}
            - **Par:** {row['operateur_id']}
            - **Heure:** {row['debut_panne']}
            """)
        
        if st.button("✅ Confirmer traitement"):
            conn.execute("UPDATE Pannes SET statut = 'Résolu', fin_panne = datetime('now') WHERE statut = '🔴 Ouvert'")
            conn.commit()
            st.rerun()
    else:
        st.success("✅ Aucune panne signalée")
except Exception as e:
    st.info("Système d'alertes prêt")

# SECTION 2: SUIVI TEMPS RÉEL (Ce qui est affiché chez l'opérateur)
st.markdown("---")
st.subheader("👁️ Suivi des fabrications (Temps réel)")

try:
    query_suivi = """
    SELECT 
        d.id,
        d.reference, 
        d.quantite, 
        d.urgence, 
        d.statut, 
        d.operateur_id,
        d.shift,
        d.heure_demande
    FROM Demandes
    WHERE d.statut IN ('🟠En attente', '🟢En cours')
    ORDER BY 
        CASE WHEN d.statut = '🟢En cours' THEN 1 ELSE 2 END, 
        d.id DESC
    """
    
    encours_data = conn.execute(query_suivi).fetchall()

    if encours_data:
        df_suivi = pd.DataFrame(encours_data, columns=[
            "ID", "Référence", "Qté", "Urgence", "Status", "Opérateur", "Shift", "Heure Demande"
        ])
        
        # Coloration selon status
        def color_status(val):
            if val == '🟢En cours':
                return 'background-color: lightgreen'
            elif val == '🟠En attente':
                return 'background-color: orange'
            return ''
        
        st.dataframe(
            df_suivi.style.applymap(color_status, subset=['Status']),
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.info("Aucune production en cours")

except Exception as e:
    st.error(f"Erreur: {e}")

# SECTION 3: ENVOI NOUVELLE DEMANDE
st.markdown("---")
st.subheader("➕ Nouvelle Demande de Production")

if "panier" not in st.session_state:
    st.session_state.panier = []

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        # Récupération des références disponibles
        try:
            df_stock_info = pd.read_sql_query("SELECT reference, quantite FROM Stock", conn)
            refs = df_stock_info['reference'].tolist()
        except:
            refs = []
        
        ref_choisie = st.selectbox("Référence Produit", refs if refs else ["Aucune référence"])
        qte_voulue = st.number_input("Quantité demandée", 1, 10000, 50)
    
    with c2:
        urg = st.selectbox("Niveau d'urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")
        shift_cible = st.multiselect("Shift cible", ["A", "B"], default=["A", "B"])

    if st.button("➕ Ajouter à la liste"):
        st.session_state.panier.append({
            "Reference": ref_choisie,
            "Quantite": qte_voulue,
            "Urgence": urg,
            "Date_Besoin": str(date_b),
            "Shifts": shift_cible
        })
        st.success("Ajouté!")

# Affichage panier
if st.session_state.panier:
    st.write("🛒 **Liste en préparation:**")
    st.dataframe(pd.DataFrame(st.session_state.panier), use_container_width=True)
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("❌ Vider la liste"):
            st.session_state.panier = []
            st.rerun()
    
    with col_b2:
        if st.button("📤 Envoyer aux postes", type="primary"):
            maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for item in st.session_state.panier:
                # Vérification stock
                res = conn.execute("SELECT quantite FROM Stock WHERE reference = ?", 
                                 (item['Reference'],)).fetchone()
                stock_actuel = res[0] if res else 0
                besoin_reel = max(0, item['Quantite'] - stock_actuel)

                if besoin_reel > 0:
                    # Envoi à chaque shift sélectionné
                    for s in item['Shifts']:
                        conn.execute("""
                            INSERT INTO Demandes 
                            (reference, quantite, date_besoin, shift, statut, urgence, heure_demande) 
                            VALUES (?, ?, ?, ?, '🟠En attente', ?, ?)
                        """, (item['Reference'], besoin_reel, item['Date_Besoin'], s, item['Urgence'], maintenant))
                    
                    st.success(f"✅ {item['Reference']} envoyé (Qté: {besoin_reel})")
                else:
                    st.info(f"ℹ️ Stock suffisant pour {item['Reference']}")

            conn.commit()
            st.session_state.panier = []
            st.balloons()
            st.rerun()

# SECTION 4: HISTORIQUE
st.markdown("---")
st.subheader("📈 Historique de Production")

try:
    df_chart = pd.read_sql_query("""
        SELECT 
            date(fin_production) as jour, 
            COUNT(*) as total,
            SUM(quantite) as qte_totale
        FROM Demandes 
        WHERE statut='Terminé'
        GROUP BY jour 
        ORDER BY jour DESC
        LIMIT 30
    """, conn)

    if not df_chart.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.line_chart(df_chart.set_index("jour")["total"], use_container_width=True)
        with col2:
            st.bar_chart(df_chart.set_index("jour")["qte_totale"], use_container_width=True)
    else:
        st.info("En attente de données")

except Exception as e:
    st.info("En attente de données")

conn.close()
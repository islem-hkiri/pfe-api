import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from database_v2 import init_db # importaion des données de la base 

# Configuration
st.set_page_config(page_title="Logistique - Supervision")

# Paths Dynamiques
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

# AUTO-INSTALLATION EL TABLES 
if not os.path.exists(DB_PATH):
    init_db()
# AUTO REFRESH (5 secondes pour le temps réel)
st_autorefresh(interval=5000, key="log_refresh")

# SIDEBAR & KPI

# --- POSITION CORRIGÉE ---
st.sidebar.title(" Tableau de Bord")

# Déplace cette ligne ICI (avant les calculs)
conn = sqlite3.connect(DB_PATH) 

# Maintenant 'conn' existe et peut être utilisé
total = conn.execute("SELECT COUNT(*) FROM Demandes").fetchone()[0]
termine = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut='Terminé'").fetchone()[0]

st.sidebar.metric("Total demandes", total)
st.sidebar.metric("Terminées", termine)

#  KPI Temps moyen
# --- SECTION KPI (Ligne 55 environ) ---
df_time = pd.read_sql_query("SELECT (strftime('%s', fin_production) - strftime('%s', debut_production)) as duree FROM Demandes WHERE statut='Terminé'", conn)

if not df_time.empty and pd.notna(df_time['duree'].mean()):
    st.sidebar.metric("Temps moyen (s)", int(df_time['duree'].mean()))
else:
    st.sidebar.metric("Temps moyen (s)", "0") # Ma3adech yeplanty hna

st.sidebar.markdown("---")
st.sidebar.subheader(" Performance (KPI)")

# le temps totale du travail
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
    
    if taux > 85:
        st.sidebar.warning(" Charge élevée détectée !")
else:
    st.sidebar.info("Attente de données de production...")

# KPI urgence
df_urg = pd.read_sql_query("""
SELECT urgence, COUNT(*) as total
FROM Demandes GROUP BY urgence
""", conn)

if not df_urg.empty:
    st.sidebar.bar_chart(df_urg.set_index("urgence"))

# Historique
st.sidebar.markdown("---")
try:
    query_hist = ("""
    SELECT heure_demande, COUNT(reference) as Nb_Refs
    FROM Demandes 
    WHERE statut != 'Archivé'
    GROUP BY heure_demande 
    ORDER BY heure_demande DESC LIMIT 10
    """)
    df_hist = pd.read_sql_query(query_hist, conn)

    if not df_hist.empty:
        if st.sidebar.button("Vider l'historique", use_container_width=True):
            conn.execute("UPDATE Demandes SET statut = 'Archivé' WHERE statut != 'Archivé'")
            conn.commit()
            st.rerun()
            
        for index, row in df_hist.iterrows():
            with st.sidebar.expander(f"Liste du {row['heure_demande']}"):
                details = conn.execute("""
                    SELECT reference, quantite, statut 
                    FROM Demandes WHERE heure_demande = ?
                """, (row['heure_demande'],)).fetchall()
                st.dataframe(pd.DataFrame(details, columns=["Ref", "Qté", "Statut"]), use_container_width=True)
except Exception as e:
    st.sidebar.error(f"Erreur historique: {e}")

# DECONNEXION
#if st.sidebar.button("Déconnexion", use_container_width=True):
 #   st.session_state.logged_in = False
  #  st.rerun()

# INTERFACE PRINCIPALE
st.title(" Demandes (Poste Soudure)")
# --- SECTION ALERTES PANNES (Notification du Message Opérateur) ---
st.subheader(" Alertes de Panne en Temps Réel")

try:
    #lire les pannes envoyé par l'operateur
    # On sélectionne la cause (le message) et l'ID de l'opérateur
    df_alertes = pd.read_sql_query("""
        SELECT operateur_id, cause, debut_panne, statut 
        FROM Pannes 
        WHERE statut = '🔴 Ouvert' 
        ORDER BY id DESC
    """, conn)

    if not df_alertes.empty:
        for index, row in df_alertes.iterrows():
            # affichage de message de la panne envoyé
            st.error(f"""
                **NOUVELLE ALERTE REÇUE**
                * **Message de l'Opérateur :** {row['cause']}
                * **Envoyé par :** {row['operateur_id']}
                * **Heure :** {row['debut_panne']}
            """)
        
        # Bouton pour effacer l'alerte une fois traitée
        if st.button(" Confirmer la réception / Traiter"):
            conn.execute("UPDATE Pannes SET statut = 'Résolu', fin_panne = datetime('now') WHERE statut = '🔴 Ouvert'")
            conn.commit()
            st.success("L'alerte a été marquée comme traitée.")
            st.rerun()
    else:
        st.success(" Aucune panne signalée pour le moment.")

except Exception as e:
    # Si la table est vide ou n'existe pas encore
    st.info("Système d'alertes prêt (en attente de messages...).")
# SUIVI TEMPS RÉEL
st.subheader(" Suivi des fabrications en temps réel")

try:
    query_suivi = """
    SELECT reference, quantite, urgence, statut, operateur_id
    FROM Demandes
    WHERE statut IN ('🟠En attente', '🟢En cours')
    ORDER BY CASE WHEN statut = '🟢En cours' THEN 1 ELSE 2 END, id DESC
    """
    encours_data = conn.execute(query_suivi).fetchall()

    if encours_data:
        df_suivi = pd.DataFrame(encours_data, columns=["Référence", "Qté", "Urgence", "État", "Opérateur"])
        st.dataframe(df_suivi, use_container_width=True, hide_index=True)
    else:
        st.success(" Aucune production en attente.")

except Exception as e:
    st.error(f"Erreur de lecture du suivi: {e}")
# PRÉPARATION DE COMMANDE (PANIER)
st.markdown("---")
st.subheader(" Nouvelle Demande de Production")

if "panier" not in st.session_state:
    st.session_state.panier = []

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        df_stock_info = pd.read_sql_query("SELECT reference, quantite FROM Stock", conn)
        refs = df_stock_info['reference'].tolist()
        ref_choisie = st.selectbox("Référence", refs)
        qte_voulue = st.number_input("Quantité totale souhaitée", 1, 10000, 50)
    with c2:
        urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")

    if st.button(" Ajouter à la liste", use_container_width=True):
        st.session_state.panier.append({
            "Reference": ref_choisie,
            "Quantite": qte_voulue,
            "Urgence": urg,
            "Date_Besoin": str(date_b)
        })

# ENVOI
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
            maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in st.session_state.panier:
                res = conn.execute("SELECT quantite FROM Stock WHERE reference = ?", (item['Reference'],)).fetchone()
                stock_actuel = res[0] if res else 0
                besoin_reel = max(0, item['Quantite'] - stock_actuel)

                if besoin_reel > 0:
                    for s in ['A', 'B']:
                        conn.execute("""
                            INSERT INTO Demandes 
                            (reference, quantite, date_besoin, shift, statut, urgence, heure_demande) 
                            VALUES (?, ?, ?, ?, '🟠En attente', ?, ?)
                        """, (item['Reference'], besoin_reel, item['Date_Besoin'], s, item['Urgence'], maintenant))
                else:
                    st.warning(f"Stock suffisant pour {item['Reference']}")

            conn.commit()
            st.session_state.panier = []
            st.success("Demandes envoyées avec succès !")
            st.rerun()

# SUPERVISION GRAPHIQUE
st.markdown("---")
st.subheader("📊 Historique de Production (Journalier)")

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

except Exception as e:
    st.info("En attente de données pour l'affichage du graphique.")

conn.close()
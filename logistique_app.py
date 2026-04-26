import requests
import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from database_v2 import init_db  # importation des données de la base

# Configuration
st.set_page_config(page_title="Logistique - Supervision")

# Paths Dynamiques
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

# AUTO-INSTALLATION DES TABLES
if not os.path.exists(DB_PATH):
    init_db()

# Connexion à la base de données
conn = sqlite3.connect(DB_PATH)

# AUTO REFRESH (5 secondes pour le temps réel)
st_autorefresh(interval=5000, key="log_refresh")

# SIDEBAR & KPI
st.sidebar.title("Tableau de Bord")

# Récupération des données API
try:
    response = requests.get("https://pfe-api-uju4.onrender.com/api/full_data", timeout=10)

    if response.status_code == 200:
        json_data = response.json()

        # ✅ ما عادش يطيح كي ما يلقاش demandes
        if isinstance(json_data, dict) and "demandes" in json_data:
            data = json_data["demandes"]
        else:
            data = []
    else:
        data = []

except Exception as e:
    st.sidebar.error(f"Erreur API: {e}")
    data = []

# Calcul des métriques
try:
    total = conn.execute("SELECT COUNT(*) FROM Demandes").fetchone()[0]
    termine = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut='Terminé'").fetchone()[0]
    en_cours = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut LIKE '%En cours%'").fetchone()[0]
    en_attente = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut LIKE '%En attente%'").fetchone()[0]
    
    st.sidebar.metric("Total demandes", total)
    st.sidebar.metric("✅ Terminées", termine)
    st.sidebar.metric("🟢En cours", en_cours)
    st.sidebar.metric("🟠En attente", en_attente)
except Exception as e:
    st.sidebar.error(f"Erreur métriques: {e}")

# KPI Temps moyen
try:
    df_time = pd.read_sql_query("""
        SELECT (strftime('%s', fin_production) - strftime('%s', debut_production)) as duree 
        FROM Demandes 
        WHERE statut='Terminé' 
        AND debut_production IS NOT NULL 
        AND fin_production IS NOT NULL
    """, conn)

    if not df_time.empty and pd.notna(df_time['duree'].mean()):
        temps_moyen = int(df_time['duree'].mean())
        st.sidebar.metric("Temps moyen (s)", temps_moyen)
    else:
        st.sidebar.metric("Temps moyen (s)", "N/A")
except Exception as e:
    st.sidebar.metric("Temps moyen (s)", "N/A")

st.sidebar.markdown("---")
st.sidebar.subheader("Performance (KPI)")

# Le temps total du travail
TEMPS_SHIFT_SEC = 8 * 3600

try:
    df_occ = pd.read_sql_query("""
    SELECT SUM(strftime('%s', fin_production) - strftime('%s', debut_production)) as total_prod
    FROM Demandes 
    WHERE statut='Terminé' 
    AND date(fin_production) = date('now')
    AND debut_production IS NOT NULL 
    AND fin_production IS NOT NULL
    """, conn)

    if not df_occ.empty and df_occ['total_prod'].iloc[0] is not None:
        total_sec = df_occ['total_prod'].iloc[0]
        taux = (total_sec / TEMPS_SHIFT_SEC) * 100
        taux_clean = min(int(taux), 100)
        
        st.sidebar.metric("Taux d'Occupation Jour", f"{taux_clean}%")
        st.sidebar.progress(taux_clean / 100)
        
        if taux > 85:
            st.sidebar.warning("Charge élevée détectée !")
    else:
        st.sidebar.info("Attente de données de production...")
except Exception as e:
    st.sidebar.info("Attente de données de production...")

# KPI urgence
try:
    df_urg = pd.read_sql_query("""
    SELECT urgence, COUNT(*) as total
    FROM Demandes 
    WHERE statut != 'Terminé' AND statut != 'Archivé'
    GROUP BY urgence
    """, conn)

    if not df_urg.empty:
        st.sidebar.subheader("Répartition par urgence")
        st.sidebar.bar_chart(df_urg.set_index("urgence"))
except Exception as e:
    pass

# Historique
st.sidebar.markdown("---")
st.sidebar.subheader("Historique")
try:
    query_hist = """
    SELECT heure_demande, COUNT(reference) as Nb_Refs
    FROM Demandes 
    WHERE statut != 'Archivé'
    GROUP BY heure_demande 
    ORDER BY heure_demande DESC LIMIT 10
    """
    df_hist = pd.read_sql_query(query_hist, conn)

    if not df_hist.empty:
        if st.sidebar.button("Vider l'historique", use_container_width=True):
            conn.execute("UPDATE Demandes SET statut = 'Archivé' WHERE statut != 'Archivé'")
            conn.commit()
            st.rerun()
            
        for index, row in df_hist.iterrows():
            with st.sidebar.expander(f"Liste du {row['heure_demande']} ({row['Nb_Refs']} refs)"):
                details = conn.execute("""
                    SELECT reference, quantite, statut 
                    FROM Demandes WHERE heure_demande = ?
                """, (row['heure_demande'],)).fetchall()
                st.dataframe(pd.DataFrame(details, columns=["Ref", "Qté", "Statut"]), use_container_width=True)
    else:
        st.sidebar.info("Aucun historique disponible")
except Exception as e:
    st.sidebar.error(f"Erreur historique: {e}")

# DECONNEXION
if st.sidebar.button("Déconnexion", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# INTERFACE PRINCIPALE
st.title("Demandes (Poste Soudure)")

# SECTION ALERTES PANNES
st.subheader("Alertes de Panne en Temps Réel")

try:
    df_alertes = pd.read_sql_query("""
        SELECT operateur_id, cause, debut_panne, statut 
        FROM Pannes 
        WHERE statut = '🔴 Ouvert' 
        ORDER BY id DESC
    """, conn)

    if not df_alertes.empty:
        for index, row in df_alertes.iterrows():
            st.error(f"""
                **NOUVELLE ALERTE REÇUE**
                * **Message de l'Opérateur :** {row['cause']}
                * **Envoyé par :** {row['operateur_id']}
                * **Heure :** {row['debut_panne']}
            """)
        
        if st.button("Confirmer la réception / Traiter"):
            conn.execute("UPDATE Pannes SET statut = 'Résolu', fin_panne = datetime('now') WHERE statut = '🔴 Ouvert'")
            conn.commit()
            st.success("L'alerte a été marquée comme traitée.")
            st.rerun()
    else:
        st.success("Aucune panne signalée pour le moment.")

except Exception as e:
    st.info("Système d'alertes prêt (en attente de messages...).")

# SUIVI TEMPS RÉEL
st.markdown("---")
st.subheader("Suivi des fabrications en temps réel")

try:
    query_suivi = """
    SELECT id, reference, quantite, urgence, statut, operateur_id, heure_demande
    FROM Demandes
    WHERE statut LIKE '%En attente%' OR statut LIKE '%En cours%'
    ORDER BY 
        CASE urgence
            WHEN 'Critique' THEN 1
            WHEN 'Urgent' THEN 2
            WHEN 'Normal' THEN 3
            ELSE 4
        END,
        CASE 
            WHEN statut LIKE '%En cours%' THEN 1 
            ELSE 2 
        END, 
        id DESC
    """
    encours_data = conn.execute(query_suivi).fetchall()

    if encours_data:
        df_suivi = pd.DataFrame(encours_data, columns=["ID", "Référence", "Qté", "Urgence", "État", "Opérateur", "Date demande"])
        
        # Style avec couleurs selon urgence
        def color_urgence(row):
            if row['Urgence'] == 'Critique':
                return ['background-color: #ffcccc'] * len(row)
            elif row['Urgence'] == 'Urgent':
                return ['background-color: #fff4cc'] * len(row)
            else:
                return ['background-color: #e6ffe6'] * len(row)
        
        st.dataframe(
            df_suivi.style.apply(color_urgence, axis=1),
            use_container_width=True, 
            hide_index=True
        )
        
        st.info(f"**{len(encours_data)} demande(s)** en cours de traitement")
    else:
        st.info("Aucune production en attente ou en cours.")

except Exception as e:
    st.error(f"Erreur de lecture du suivi: {e}")

# Initialize panier
if "panier" not in st.session_state:
    st.session_state.panier = []

# PRÉPARATION DE COMMANDE (PANIER)
st.markdown("---")
st.subheader("Nouvelle Demande de Production")

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        try:
            df_stock_info = pd.read_sql_query("SELECT reference, quantite FROM Stock", conn)
            if not df_stock_info.empty:
                refs = df_stock_info['reference'].tolist()
                ref_choisie = st.selectbox("Référence", refs)
                qte_voulue = st.number_input("Quantité totale souhaitée", 1, 10000, 50)
            else:
                st.warning("Aucune référence en stock")
                ref_choisie = None
        except Exception as e:
            st.error(f"Erreur stock: {e}")
            ref_choisie = None
            
    with c2:
        urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")

    if ref_choisie and st.button("Ajouter à la liste", use_container_width=True):
        st.session_state.panier.append({
            "Reference": ref_choisie,
            "Quantite": qte_voulue,
            "Urgence": urg,
            "Date_Besoin": str(date_b)
        })
        st.success(f"{ref_choisie} ajouté à la liste !")
        st.rerun()

# AFFICHAGE PANIER + ENVOI
if st.session_state.panier:
    st.write("**Liste en cours de préparation**")
    st.dataframe(pd.DataFrame(st.session_state.panier), use_container_width=True, hide_index=True)
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Annuler tout", use_container_width=True):
            st.session_state.panier = []
            st.rerun()
    with col_b2:
        if st.button("Envoyer au montage", type="primary", use_container_width=True):
            success_count = 0
            error_count = 0
            
            for item in st.session_state.panier:
                try:
                    response = requests.post(
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
                    if response.status_code == 200:
                        success_count += 1
                    else:
                        error_count += 1
                        st.error(f"Erreur pour {item['Reference']}: {response.status_code}")
                except Exception as e:
                    error_count += 1
                    st.error(f"Erreur connexion API pour {item['Reference']}: {e}")

            st.session_state.panier = []
            
            if success_count > 0:
                st.success(f"{success_count} demande(s) envoyée(s) avec succès !")
            if error_count > 0:
                st.warning(f"{error_count} demande(s) en erreur")
                
            st.rerun()

# SUPERVISION GRAPHIQUE
st.markdown("---")
st.subheader("Historique de Production (Journalier)")

try:
    df_chart = pd.read_sql_query("""
        SELECT date(fin_production) as jour, COUNT(*) as total
        FROM Demandes 
        WHERE statut='Terminé'
        AND fin_production IS NOT NULL
        GROUP BY jour 
        ORDER BY jour DESC
        LIMIT 30
    """, conn)

    if not df_chart.empty:
        st.line_chart(df_chart.set_index("jour"))
        st.caption(f"Historique des 30 derniers jours - Total: {df_chart['total'].sum()} pièces produites")
    else:
        st.info("Aucune donnée terminée pour le moment. Les données apparaîtront dès qu'une production sera complétée.")

except Exception as e:
    st.info("En attente de données pour l'affichage du graphique.")

# Fermeture de la connexion
conn.close()
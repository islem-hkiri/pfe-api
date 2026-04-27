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

# Paths Dynamiques
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

# AUTO-INSTALLATION DES TABLES
if not os.path.exists(DB_PATH):
    init_db()

# Connexion à la base de données
conn = sqlite3.connect(DB_PATH)

# AUTO REFRESH
st_autorefresh(interval=5000, key="log_refresh")

# SIDEBAR & KPI
st.sidebar.title("📊 Tableau de Bord")

# Calcul des métriques
try:
    total = conn.execute("SELECT COUNT(*) FROM Demandes").fetchone()[0]
    termine = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut='Terminé'").fetchone()[0]
    en_cours = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut LIKE '%En cours%'").fetchone()[0]
    en_attente = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut LIKE '%En attente%'").fetchone()[0]

    st.sidebar.metric("📦 Total demandes", total)
    st.sidebar.metric("✅ Terminées", termine)
    st.sidebar.metric("🟢 En cours", en_cours)
    st.sidebar.metric("🟠 En attente", en_attente)
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
        st.sidebar.metric("⏱️ Temps moyen (s)", temps_moyen)
    else:
        st.sidebar.metric("⏱️ Temps moyen (s)", "N/A")
except Exception as e:
    st.sidebar.metric("⏱️ Temps moyen (s)", "N/A")

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Performance (KPI)")

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
        
        st.sidebar.metric("📈 Taux d'Occupation Jour", f"{taux_clean}%")
        st.sidebar.progress(taux_clean / 100)
        
        if taux > 85:
            st.sidebar.warning("⚠️ Charge élevée détectée !")
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
        st.sidebar.subheader("🚨 Répartition par urgence")
        st.sidebar.bar_chart(df_urg.set_index("urgence"))
except Exception as e:
    pass

# Historique
st.sidebar.markdown("---")
st.sidebar.subheader("📜 Historique")
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
        if st.sidebar.button("🗑️ Vider l'historique", use_container_width=True):
            conn.execute("UPDATE Demandes SET statut = 'Archivé' WHERE statut != 'Archivé'")
            conn.commit()
            st.rerun()
            
        for index, row in df_hist.iterrows():
            with st.sidebar.expander(f"📅 Liste du {row['heure_demande']} ({row['Nb_Refs']} refs)"):
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
if st.sidebar.button("🚪 Déconnexion", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# INTERFACE PRINCIPALE
st.title("🏭 Demandes (Poste Soudure)")

# SECTION ALERTES PANNES
st.subheader("⚠️ Alertes de Panne en Temps Réel")

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
                **⚠️ NOUVELLE ALERTE REÇUE**
                * **Message de l'Opérateur :** {row['cause']}
                * **Envoyé par :** {row['operateur_id']}
                * **Heure :** {row['debut_panne']}
            """)
        
        if st.button("✅ Confirmer la réception / Traiter"):
            conn.execute("UPDATE Pannes SET statut = 'Résolu', fin_panne = datetime('now') WHERE statut = '🔴 Ouvert'")
            conn.commit()
            st.success("✅ L'alerte a été marquée comme traitée.")
            st.rerun()
    else:
        st.success("✅ Aucune panne signalée pour le moment.")

except Exception as e:
    st.info("Système d'alertes prêt (en attente de messages...).")

# SUIVI TEMPS RÉEL
st.markdown("---")
st.subheader("🔄 Suivi des fabrications en temps réel")

try:
    response_tasks = requests.get("https://pfe-api-uju4.onrender.com/api/full_data", timeout=10)
    
    if response_tasks.status_code == 200:
        api_data = response_tasks.json()
        
        if isinstance(api_data, dict) and "demandes" in api_data:
            all_tasks = api_data["demandes"]
            
            encours_data = [
                task for task in all_tasks 
                if "En attente" in task.get("statut", "") or "En cours" in task.get("statut", "")
            ]
            
            if encours_data:
                df_suivi = pd.DataFrame(encours_data)
                
                colonnes_affichees = ["id", "reference", "quantite", "urgence", "statut", "operateur_id", "heure_demande"]
                colonnes_disponibles = [col for col in colonnes_affichees if col in df_suivi.columns]
                
                df_suivi = df_suivi[colonnes_disponibles]
                df_suivi.columns = ["ID", "Référence", "Qté", "Urgence", "État", "Opérateur", "Date demande"][:len(colonnes_disponibles)]
                
                if "Opérateur" in df_suivi.columns:
                    df_suivi["Opérateur"] = df_suivi["Opérateur"].fillna("Non assigné")

                def format_etat(etat):
                    if "En cours" in str(etat):
                        return "🟢 En cours"
                    elif "En attente" in str(etat):
                        return "🟠 En attente"
                    else:
                        return etat

                if "État" in df_suivi.columns:
                    df_suivi["État"] = df_suivi["État"].apply(format_etat)

                ordre_urgence = {"Critique": 1, "Urgent": 2, "Normal": 3}
                df_suivi["_ordre_urgence"] = df_suivi["Urgence"].map(ordre_urgence).fillna(4)
                df_suivi["_ordre_statut"] = df_suivi["État"].apply(lambda x: 1 if "En cours" in str(x) else 2)
                
                df_suivi = df_suivi.sort_values(["_ordre_urgence", "_ordre_statut", "ID"], ascending=[True, True, False])
                df_suivi = df_suivi.drop(columns=["_ordre_urgence", "_ordre_statut"])

                def color_urgence(row):
                    if row.get('Urgence') == 'Critique':
                        return ['background-color: #ffcccc; color: black'] * len(row)
                    elif row.get('Urgence') == 'Urgent':
                        return ['background-color: #fff4cc; color: black'] * len(row)
                    else:
                        return ['background-color: #e6ffe6; color: black'] * len(row)

                st.dataframe(
                    df_suivi.style.apply(color_urgence, axis=1),
                    use_container_width=True,
                    hide_index=True
                )

                nb_en_cours = df_suivi["État"].str.contains("En cours", na=False).sum()
                nb_en_attente = df_suivi["État"].str.contains("En attente", na=False).sum()

                col1, col2, col3 = st.columns(3)
                col1.metric("📦 Total actif", len(encours_data))
                col2.metric("🟢 En cours", nb_en_cours)
                col3.metric("🟠 En attente", nb_en_attente)

            else:
                st.info("✅ Aucune production en attente ou en cours.")
        else:
            st.warning("⚠️ Format de données API incorrect")
    else:
        st.error(f"❌ Erreur API : {response_tasks.status_code}")

except Exception as e:
    st.error(f"❌ Erreur de connexion API: {e}")

# Initialize panier
if "panier" not in st.session_state:
    st.session_state.panier = []

# NOUVELLE DEMANDE DE PRODUCTION
st.markdown("---")
st.subheader("📝 Nouvelle Demande de Production")

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
                st.warning("⚠️ Aucune référence en stock")
                ref_choisie = None
        except Exception as e:
            st.error(f"Erreur stock: {e}")
            ref_choisie = None
            
    with c2:
        urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")

    if ref_choisie and st.button("➕ Ajouter à la liste", use_container_width=True):
        st.session_state.panier.append({
            "Reference": ref_choisie,
            "Quantite": qte_voulue,
            "Urgence": urg,
            "Date_Besoin": str(date_b)
        })
        st.success(f"✅ {ref_choisie} ajouté à la liste !")
        st.rerun()

# AFFICHAGE PANIER + ENVOI
if st.session_state.panier:
    st.write("📋 **Liste en cours de préparation**")
    st.dataframe(pd.DataFrame(st.session_state.panier), use_container_width=True, hide_index=True)
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("🗑️ Annuler tout", use_container_width=True):
            st.session_state.panier = []
            st.rerun()
    with col_b2:
        if st.button("📤 Envoyer au montage", type="primary", use_container_width=True):
            success_count = 0
            error_count = 0
            
            for item in st.session_state.panier:
                try:
                    # 🔥 CORRECTION: Utiliser /demandes au lieu de /create_demande
                    response = requests.post(
                        "https://pfe-api-uju4.onrender.com/demandes",  # ← CHANGEMENT ICI
                        json={
                            "reference": item["Reference"],
                            "quantite": item["Quantite"],
                            "date_besoin": item["Date_Besoin"],
                            "shift": "B",
                            "urgence": item["Urgence"]
                        },
                        timeout=10
                    )
                    
                    st.write(f"📊 Status: {response.status_code}")
                    st.write(f"📄 Response: {response.text}")
                    
                    if response.status_code in [200, 201]:
                        success_count += 1
                    else:
                        error_count += 1
                        st.error(f"❌ Erreur pour {item['Reference']}: {response.status_code}")
                        
                except Exception as e:
                    error_count += 1
                    st.error(f"❌ Erreur connexion API pour {item['Reference']}: {e}")

            st.session_state.panier = []
            
            if success_count > 0:
                st.success(f"✅ {success_count} demande(s) envoyée(s) avec succès !")
            if error_count > 0:
                st.warning(f"⚠️ {error_count} demande(s) en erreur")
                
            st.rerun()

# SUPERVISION GRAPHIQUE
st.markdown("---")
st.subheader("📊 Historique de Production (Journalier)")

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
        st.caption(f"📈 Historique des 30 derniers jours - Total: {df_chart['total'].sum()} pièces produites")
    else:
        st.info("ℹ️ Aucune donnée terminée pour le moment.")

except Exception as e:
    st.info("ℹ️ En attente de données pour l'affichage du graphique.")

# Fermeture connexion
conn.close()
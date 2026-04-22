import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from database_v2 import init_db

st.set_page_config(page_title="Logistique - Supervision")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

if not os.path.exists(DB_PATH):
    init_db()

st_autorefresh(interval=5000, key="log_refresh")

st.sidebar.title("ðŸ“Š Tableau de Bord")

conn = sqlite3.connect(DB_PATH)

total = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut NOT IN ('ðŸ“¦ ArchivÃ©')").fetchone()[0]
termine = conn.execute("SELECT COUNT(*) FROM Demandes WHERE statut='âœ… TerminÃ©'").fetchone()[0]

st.sidebar.metric("ðŸ“‹ Total demandes", total)
st.sidebar.metric("âœ… TerminÃ©es", termine)

df_time = pd.read_sql_query("SELECT (strftime('%s', fin_production) - strftime('%s', debut_production)) as duree FROM Demandes WHERE statut='âœ… TerminÃ©'", conn)

if not df_time.empty and pd.notna(df_time['duree'].mean()):
    st.sidebar.metric("â±ï¸ Temps moyen (s)", int(df_time['duree'].mean()))
else:
    st.sidebar.metric("â±ï¸ Temps moyen (s)", "0")

st.sidebar.markdown("---")
st.sidebar.subheader("ðŸ“ˆ Performance (KPI)")

TEMPS_SHIFT_SEC = 8 * 3600 

df_occ = pd.read_sql_query("""
SELECT SUM(strftime('%s', fin_production) - strftime('%s', debut_production)) as total_prod
FROM Demandes WHERE statut='âœ… TerminÃ©' AND date(fin_production) = date('now')
""", conn)

if not df_occ.empty and df_occ['total_prod'].iloc[0] is not None:
    total_sec = df_occ['total_prod'].iloc[0]
    taux = (total_sec / TEMPS_SHIFT_SEC) * 100
    taux_clean = min(int(taux), 100)
    
    st.sidebar.metric("ðŸ“Š Taux d'Occupation Jour", f"{taux_clean}%")
    st.sidebar.progress(taux_clean / 100)
    
    if taux > 85:
        st.sidebar.warning("âš ï¸ Charge Ã©levÃ©e dÃ©tectÃ©e !")
else:
    st.sidebar.info("ðŸ“­ Attente de donnÃ©es de production...")

df_urg = pd.read_sql_query("""
SELECT urgence, COUNT(*) as total
FROM Demandes GROUP BY urgence
""", conn)

if not df_urg.empty:
    st.sidebar.bar_chart(df_urg.set_index("urgence"))

st.sidebar.markdown("---")
try:
    query_hist = ("""
    SELECT heure_demande, COUNT(reference) as Nb_Refs
    FROM Demandes 
    WHERE statut != 'ðŸ“¦ ArchivÃ©'
    GROUP BY heure_demande 
    ORDER BY heure_demande DESC LIMIT 10
    """)
    df_hist = pd.read_sql_query(query_hist, conn)

    if not df_hist.empty:
        if st.sidebar.button("ðŸ—‘ï¸ Vider l'historique", use_container_width=True):
            conn.execute("UPDATE Demandes SET statut = 'ðŸ“¦ ArchivÃ©' WHERE statut NOT IN ('ðŸ“¦ ArchivÃ©')")
            conn.commit()
            st.rerun()
            
        for index, row in df_hist.iterrows():
            with st.sidebar.expander(f"ðŸ“… Liste du {row['heure_demande']}"):
                details = conn.execute("""
                    SELECT reference, quantite, statut 
                    FROM Demandes WHERE heure_demande = ?
                """, (row['heure_demande'],)).fetchall()
                st.dataframe(pd.DataFrame(details, columns=["Ref", "Qte", "Statut"]), use_container_width=True)
except Exception as e:
    st.sidebar.error(f"Erreur historique: {e}")

st.title("ðŸ­ Demandes (Poste Soudure)")

st.subheader("ðŸš¨ Alertes de Panne en Temps RÃ©el")

try:
    df_alertes = pd.read_sql_query("""
        SELECT operateur_id, cause, debut_panne, statut 
        FROM Pannes 
        WHERE statut = 'Ouvert' 
        ORDER BY id DESC
    """, conn)

    if not df_alertes.empty:
        for index, row in df_alertes.iterrows():
            st.error(f"""
                ðŸ”´ **NOUVELLE ALERTE REÃ‡UE**
                * **Message de l'OpÃ©rateur :** {row['cause']}
                * **EnvoyÃ© par :** {row['operateur_id']}
                * **Heure :** {row['debut_panne']}
            """)
        
        if st.button("âœ… Confirmer la rÃ©ception / Traiter"):
            conn.execute("UPDATE Pannes SET statut = 'RÃ©solu', fin_panne = datetime('now') WHERE statut = 'Ouvert'")
            conn.commit()
            st.success("âœ… L'alerte a Ã©tÃ© marquÃ©e comme traitÃ©e.")
            st.rerun()
    else:
        st.success("âœ… Aucune panne signalÃ©e pour le moment.")

except Exception as e:
    st.info("ðŸ”§ SystÃ¨me d'alertes prÃªt (en attente de messages...).")

st.subheader("ðŸ“‹ Suivi des fabrications en temps rÃ©el")

try:
    query_suivi = """
    SELECT reference, quantite, urgence, statut, operateur_id
    FROM Demandes
    WHERE statut IN ('ðŸŸ  En attente', 'ðŸŸ¢ En cours')
    ORDER BY CASE WHEN statut = 'ðŸŸ¢ En cours' THEN 1 ELSE 2 END, id DESC
    """
    encours_data = conn.execute(query_suivi).fetchall()

    if encours_data:
        df_suivi = pd.DataFrame(encours_data, columns=["RÃ©fÃ©rence", "QtÃ©", "Urgence", "Ã‰tat", "OpÃ©rateur"])
        st.dataframe(df_suivi, use_container_width=True, hide_index=True)
    else:
        st.success("âœ… Aucune production en attente.")

except Exception as e:
    st.error(f"Erreur de lecture du suivi: {e}")

st.markdown("---")
st.subheader("ðŸ“ Nouvelle Demande de Production")

if "panier" not in st.session_state:
    st.session_state.panier = []

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        df_stock_info = pd.read_sql_query("SELECT reference, quantite FROM Stock", conn)
        refs = df_stock_info['reference'].tolist()
        ref_choisie = st.selectbox("ðŸ”§ RÃ©fÃ©rence", refs)
        qte_voulue = st.number_input("ðŸ“¦ QuantitÃ© totale souhaitÃ©e", 1, 10000, 50)
    with c2:
        urg = st.selectbox("âš¡ Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("ðŸ“… Date de besoin")

    if st.button("âž• Ajouter Ã  la liste", use_container_width=True):
        st.session_state.panier.append({
            "Reference": ref_choisie,
            "Quantite": qte_voulue,
            "Urgence": urg,
            "Date_Besoin": str(date_b)
        })

if st.session_state.panier:
    st.write("ðŸ“‹ Liste en cours de prÃ©paration")
    st.dataframe(pd.DataFrame(st.session_state.panier), use_container_width=True)
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("âŒ Annuler tout", use_container_width=True):
            st.session_state.panier = []
            st.rerun()
    with col_b2:
        if st.button("ðŸ“¤ Envoyer au montage", type="primary", use_container_width=True):
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
                            VALUES (?, ?, ?, ?, 'ðŸŸ  En attente', ?, ?)
                        """, (item['Reference'], besoin_reel, item['Date_Besoin'], s, item['Urgence'], maintenant))
                else:
                    st.warning(f"âš ï¸ Stock suffisant pour {item['Reference']}")

            conn.commit()
            st.session_state.panier = []
            st.success("âœ… Demandes envoyÃ©es avec succÃ¨s !")
            st.rerun()

st.markdown("---")
st.subheader("ðŸ“ˆ Historique de Production (Journalier)")

try:
    df_chart = pd.read_sql_query("""
        SELECT date(fin_production) as jour, COUNT(*) as total
        FROM Demandes WHERE statut='âœ… TerminÃ©'
        GROUP BY jour ORDER BY jour
    """, conn)

    if not df_chart.empty:
        st.line_chart(df_chart.set_index("jour"))
    else:
        st.info("ðŸ“­ Aucune donnÃ©e terminÃ©e pour le moment.")

except Exception as e:
    st.info("ðŸ“­ En attente de donnÃ©es pour l'affichage du graphique.")

conn.close()
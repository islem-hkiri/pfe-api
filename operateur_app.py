import streamlit as st
import requests
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

API_URL = "https://pfe-api-uju4.onrender.com"
st.set_page_config(page_title="Poste Soudure Ultrasons")

st_autorefresh(interval=5000, key="main_refresh")

if 'task_counter' not in st.session_state:
    st.session_state.task_counter = 0

def generate_unique_key(base_name):
    st.session_state.task_counter += 1
    return f"{base_name}_{st.session_state.task_counter}"

with st.sidebar:
    st.title("Identification")
    id_op_saisie = st.text_input("ID Operateur (Saisie)", key="operateur_id")
    shift = st.radio("Shift", ["A", "B"], key="shift_selection", horizontal=True)
    
    st.subheader("Signalement Panne")
    with st.expander("Declarer une Panne"):
        cause = st.text_input("Cause de la panne", key="panne_cause")
        
        if st.button("Signaler Panne", key="signal_panne_btn"):
            if cause and id_op_saisie:
                try:
                    response = requests.get("https://pfe-api-uju4.onrender.com/api/full_data")
                    data = response.json()["demandes"]
                    if st.button("Signaler Panne", key="signal_panne_btn"):
                        if cause and id_op_saisie:
                            try:
                                requests.post(
                                    f"{API_URL}/api/signal_panne",
                                    json={
                                        "operateur_id": id_op_saisie,
                                        "cause": cause
                                    }
                                )
                                st.error("Panne signalée au superviseur !")
                            except Exception as e:
                                st.error(f"Erreur: {str(e)}")
                        else:
                            st.warning("Saisir ID operateur + cause")

    with st.expander("Historique"):
        conn = None
        try:
            response = requests.get("https://pfe-api-uju4.onrender.com/api/full_data")
            data = response.json()["demandes"]
            query = """
            SELECT 
                p.module, 
                d.operateur_id,
                d.debut_production,
                d.fin_production,
                (strftime('%s', d.fin_production) - strftime('%s', d.debut_production)) as duree_sec,
                p.pression,
                p.temps,
                p.amplitude
            FROM Demandes d
            JOIN Produits p ON d.reference = p.reference
            WHERE d.shift = ?
            AND d.statut = '✅ Terminé'
            ORDER BY d.fin_production DESC
            LIMIT 20
            """
            hist = conn.execute(query, (shift,)).fetchall()

            if hist:
                df = pd.DataFrame(hist, columns=[
                    "Module","Operateur","Debut","Fin","Duree(s)","Pression","Temps","Amplitude"
                ])
                st.dataframe(df, use_container_width=True)

                if st.button("Effacer l'historique", key="clear_history_btn"):
                    requests.post(
                        f"{API_URL}/api/start_production",
                        json={
                            "demande_id": id_d,
                            "operateur_id": id_op_saisie
                        }
                    )
                    conn.commit()
                    st.rerun()
            else:
                st.info("Aucune tache terminee recemment")
        except Exception as e:
            st.error(f"Erreur base de donnees: {str(e)}")
        finally:
            if conn:
                conn.close()

st.title(f"Poste Soudure Ultrasons - Shift {shift}")

conn = None
try:
    response = requests.get("https://pfe-api-uju4.onrender.com/api/full_data")
    data = response.json()["demandes"]
    query = """
    SELECT 
        d.id,
        p.famille,
        p.module,
        d.quantite,
        d.statut,
        p.pression,
        IFNULL(p.temps,0) as temps,
        IFNULL(p.amplitude,0) as amplitude,
        d.date_besoin
    FROM Demandes d
    JOIN Produits p ON d.reference = p.reference
    WHERE d.shift = ?
    AND d.statut NOT IN ('✅ Terminé','Archive')
    ORDER BY d.date_besoin ASC
    """
    tasks = conn.execute(query, (shift,)).fetchall()

    if tasks:
        for task in tasks:
            id_d, fam, mod, qte, stat, press, temps, amp, date_b = task
            
            if "En attente" in stat:
                st.markdown(f"🟠 **EN ATTENTE** - {mod}")
            
            with st.expander(f"{mod} | {fam} | Qte {qte} | Date besoin: {date_b} (ID: {id_d})"):
                cols = st.columns([1, 1, 2])
                
                with cols[0]:
                    if stat == '🟢En cours':
                        st.button("Production en cours", key=f"start_prod_{id_d}_{shift}", disabled=True)
                    else:
                        if st.button("Lancer production", key=f"start_prod_{id_d}_{shift}"):
                            conn.execute("""
                                UPDATE Demandes
                                SET statut = '🟢En cours',
                                    debut_production = datetime('now'),
                                    operateur_id = ?
                                WHERE id = ?
                            """, (id_op_saisie, id_d))
                            conn.commit()
                            st.success(f"Production lancée pour {mod}")
                            st.rerun()
                
                with cols[1]:
                    if st.button("Terminer", key=f"end_{id_d}"):
                        qte_a_ajouter = qte
                        conn.execute("""
                            UPDATE Stock 
                            SET quantite = quantite + ? 
                            WHERE reference = (SELECT reference FROM Demandes WHERE id=?)
                        """, (qte_a_ajouter, id_d))
                        requests.post(
                            f"{API_URL}/api/terminer",
                            json={
                                "demande_id": id_d
                            }  
                        )
                        st.rerun()
                
                with cols[2]:
                    if "En attente" in stat:
                        st.warning(" STATUT:🟠EN ATTENTE")
                    elif "En cours" in stat:
                        st.error(" STATUT:🟢EN COURS")
                    else:
                        st.write(f"**Statut:** {stat}")
                    
                    st.markdown(f"""
                    **Paramètres soudure automatiques:**
                    - **Pression:** {press if press else '~'} bar
                    - **Temps:** {temps if temps else '~'} s
                    - **Amplitude:** {amp if amp else '~'} %
                    """)

except Exception as e:
    st.error(f"Erreur lors de la recuperation des taches: {str(e)}")
finally:
    if conn:
        conn.close()
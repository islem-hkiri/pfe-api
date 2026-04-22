import streamlit as st
import sqlite3
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

st_autorefresh(interval=5000, key="main_refresh")

if 'task_counter' not in st.session_state:
    st.session_state.task_counter = 0

def generate_unique_key(base_name):
    st.session_state.task_counter += 1
    return f"{base_name}_{st.session_state.task_counter}"

with st.sidebar:
    st.title("Identification")
    id_op_saisie = st.text_input("ID Operateur",key="operateur_id")
    shift = st.radio("Shift", ["A", "B"], key="shift_selection", horizontal=True)
    
    st.subheader("Signalement Panne")
    with st.expander("ðŸ“¢ DÃ©clarer une Panne"):
        cause = st.text_input("Cause de la panne", key="panne_cause")
        
        if st.button("âš ï¸ Signaler Panne", key="signal_panne_btn"):
            if cause and id_op_saisie:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("""
                        INSERT INTO Pannes (operateur_id, cause, debut_panne, statut)
                        VALUES (?, ?, datetime('now'), 'Ouvert')
                    """, (id_op_saisie, cause))
                    conn.commit()
                    st.error("ðŸš¨ Panne signalÃ©e au superviseur !")
                except Exception as e:
                    st.error(f"Erreur: {str(e)}")
                finally:
                    conn.close()
            else:
                st.warning("âš ï¸ Saisir ID opÃ©rateur + cause")

    with st.expander("ðŸ“œ Historique"):
        try:
            conn = sqlite3.connect(DB_PATH)
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
            AND d.statut = 'âœ… TerminÃ©'
            ORDER BY d.fin_production DESC
            LIMIT 20
            """
            hist = conn.execute(query, (shift,)).fetchall()

            if hist:
                df = pd.DataFrame(hist, columns=[
                    "Module","OpÃ©rateur","DÃ©but","Fin","DurÃ©e(s)","Pression","Temps","Amplitude"
                ])
                st.dataframe(df, use_container_width=True)

                if st.button("ðŸ—‘ï¸ Effacer l'historique", key="clear_history_btn"):
                    conn.execute("""
                    UPDATE Demandes 
                    SET statut = 'ðŸ“¦ ArchivÃ©' 
                    WHERE shift = ? AND statut = 'âœ… TerminÃ©'
                    """, (shift,))
                    conn.commit()
                    st.rerun()
            else:
                st.info("ðŸ“­ Aucune tÃ¢che terminÃ©e rÃ©cemment")
        except Exception as e:
            st.error(f"Erreur base de donnÃ©es: {str(e)}")
        finally:
            conn.close()

st.title(f"ðŸ”Š Poste Soudure Ultrasons - Shift {shift}")

try:
    conn = sqlite3.connect(DB_PATH)
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
    AND d.statut NOT IN ('âœ… TerminÃ©', 'ðŸ“¦ ArchivÃ©')
    ORDER BY d.date_besoin ASC
    """
    tasks = conn.execute(query, (shift,)).fetchall()

    if tasks:
        for task in tasks:
            id_d, fam, mod, qte, stat, press, temps, amp, date_b = task
            
            with st.expander(f"ðŸ“¦ {mod} | {fam} | Qte {qte} | Date besoin: {date_b} (ID: {id_d})"):
                cols = st.columns([1, 1, 2])
                
                with cols[0]:
                    if stat == 'ðŸŸ¢ En cours':
                        st.button(
                            "âš™ï¸ Production en cours", 
                            key=f"start_prod_{id_d}_{shift}",
                            disabled=True
                        )
                    else:
                        if st.button("â–¶ï¸ Lancer production", key=f"start_prod_{id_d}_{shift}"):
                            if not id_op_saisie:
                                st.error("âš ï¸ Veuillez saisir votre ID opÃ©rateur dans la barre latÃ©rale")
                            else:
                                conn.execute("""
                                    UPDATE Demandes
                                    SET statut = 'ðŸŸ¢ En cours',
                                        debut_production = datetime('now'),
                                        operateur_id = ?
                                    WHERE id = ?
                                """, (id_op_saisie, id_d))
                                conn.commit()
                                st.success(f"âœ… Production lancÃ©e pour {mod}")
                                st.rerun()
                
                with cols[1]:
                    if st.button("ðŸ Terminer", key=f"end_{id_d}"):
                        qte_a_ajouter = qte
                        conn.execute("""
                            UPDATE Stock 
                            SET quantite = quantite + ? 
                            WHERE reference = (SELECT reference FROM Demandes WHERE id=?)
                        """, (qte_a_ajouter, id_d))
                        conn.execute("""
                            UPDATE Demandes 
                            SET statut='âœ… TerminÃ©', fin_production=datetime('now') 
                            WHERE id=?
                        """, (id_d,))
                        conn.commit()
                        st.success(f"âœ… Production terminÃ©e pour {mod}")
                        st.rerun()
                
                with cols[2]:
                    # Afficher le statut avec emoji
                    if stat == 'ðŸŸ¢ En cours':
                        stat_aff = "ðŸŸ¢ En cours"
                    elif stat == 'ðŸŸ  En attente':
                        stat_aff = "ðŸŸ  En attente"
                    else:
                        stat_aff = stat
                    st.write(f"**Statut:** {stat_aff}")
                    st.markdown("""
                    **ðŸ”§ ParamÃ¨tres soudure automatiques:**
                    - **Pression:** {} bar
                    - **Temps:** {} s
                    - **Amplitude:** {} %
                    """.format(press if press else '~', temps if temps else '~', amp if amp else '~'))
       
except Exception as e:
    st.error(f"Erreur lors de la rÃ©cupÃ©ration des tÃ¢ches: {str(e)}")
finally:
    conn.close()
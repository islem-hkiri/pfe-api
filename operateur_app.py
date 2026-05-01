import streamlit as st
import sqlite3
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")
st.set_page_config(page_title="Poste Soudure Ultrasons")

# Auto-refresh kol 5 secondes besh ychouf les demandes jdid
st_autorefresh(interval=5000, key="main_refresh")

# Session state pour les clés uniques
if 'task_counter' not in st.session_state:
    st.session_state.task_counter = 0

def generate_unique_key(base_name):
    st.session_state.task_counter += 1
    return f"{base_name}_{st.session_state.task_counter}"

# SIDEBAR - Identification
with st.sidebar:
    st.title("🔧 Identification")
    id_op_saisie = st.text_input("ID Opérateur", key="operateur_id")
    shift = st.radio("Shift", ["A", "B"], key="shift_selection", horizontal=True)
    
    # Signalement de panne
    st.subheader("⚠️ Signalement Panne")
    with st.expander("Déclarer une Panne"):
        cause = st.text_input("Cause de la panne", key="panne_cause")
        
        if st.button("Signaler Panne", key="signal_panne_btn"):
            if cause and id_op_saisie:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("""
                        INSERT INTO Pannes (operateur_id, cause, debut_panne, statut)
                        VALUES (?, ?, datetime('now'), '🔴 Ouvert')
                    """, (id_op_saisie, cause))
                    conn.commit()
                    st.success("Panne signalée !")
                except Exception as e:
                    st.error(f"Erreur: {str(e)}")
                finally:
                    conn.close()
            else:
                st.warning("Saisir ID opérateur + cause")

    # Historique local
    with st.expander("📜 Historique"):
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
            AND d.statut = 'Terminé'
            ORDER BY d.fin_production DESC
            LIMIT 20
            """
            hist = conn.execute(query, (shift,)).fetchall()

            if hist:
                df = pd.DataFrame(hist, columns=[
                    "Module","Opérateur","Début","Fin","Durée(s)","Pression","Temps","Amplitude"
                ])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Aucune tâche terminée")
        except Exception as e:
            st.error(f"Erreur: {str(e)}")
        finally:
            conn.close()

# INTERFACE PRINCIPALE - AFFICHAGE DES DEMANDES
st.title(f"🎯 Poste Soudure Ultrasons - Shift {shift}")

try:
    conn = sqlite3.connect(DB_PATH)
    
    # HETHI IL REQUETTE LIL LECTURE - T9RA LES DEMANDES MIL LOGISTIQUE
    query = """
    SELECT 
        d.id,
        p.famille,
        p.module,
        d.quantite,
        d.statut,  -- HETHI T AFFICHI IL STATUS (En attente/En cours/Terminé)
        p.pression,
        IFNULL(p.temps,0) as temps,
        IFNULL(p.amplitude,0) as amplitude,
        d.date_besoin,
        d.urgence
    FROM Demandes d
    JOIN Produits p ON d.reference = p.reference
    WHERE d.shift = ?
    AND d.statut NOT IN ('Terminé','Archivé')
    ORDER BY 
        CASE d.urgence 
            WHEN 'Critique' THEN 1 
            WHEN 'Urgent' THEN 2 
            ELSE 3 
        END,
        d.date_besoin ASC
    """
    
    tasks = conn.execute(query, (shift,)).fetchall()

    if not tasks:
        st.info("📭 Aucune demande en attente pour ce shift")
    else:
        st.write(f"📋 {len(tasks)} demande(s) à traiter")
        
        for task in tasks:
            id_d, fam, mod, qte, stat, press, temps, amp, date_b, urgence = task
            
            # Color coding selon l'urgence
            urgence_color = "🔴" if urgence == "Critique" else "🟠" if urgence == "Urgent" else "🟢"
            
            with st.expander(f"{urgence_color} {mod} | {fam} | Qté: {qte} | Status: {stat}"):
                cols = st.columns([1, 1, 2])
                
                with cols[0]:
                    if st.button(
                        "▶️ Lancer", 
                        key=f"start_prod_{id_d}",
                        disabled=(stat == '🟢En cours')
                    ):
                        conn.execute("""
                            UPDATE Demandes
                            SET statut = '🟢En cours',
                                debut_production = datetime('now'),
                                operateur_id = ?
                            WHERE id = ?
                        """, (id_op_saisie, id_d))
                        conn.commit()
                        st.rerun()
                
                with cols[1]:
                    if st.button("✅ Terminer", key=f"end_{id_d}", disabled=(stat != '🟢En cours')):
                        # Mise à jour stock
                        conn.execute("""
                            UPDATE Stock 
                            SET quantite = quantite + ? 
                            WHERE reference = (SELECT reference FROM Demandes WHERE id=?)
                        """, (qte, id_d))
                        
                        # Mise à jour statut
                        conn.execute("""
                            UPDATE Demandes 
                            SET statut='Terminé', 
                                fin_production=datetime('now') 
                            WHERE id=?
                        """, (id_d,))
                        
                        conn.commit()
                        st.success("Production terminée!")
                        st.rerun()
                
                with cols[2]:
                    st.write(f"**📊 Status Actuel:** `{stat}`")
                    st.write(f"**📅 Date besoin:** {date_b}")
                    st.write(f"**⚡ Urgence:** {urgence}")
                    
                    st.markdown("""
                    **🔧 Paramètres soudure:**
                    - Pression: {} bar
                    - Temps: {} s  
                    - Amplitude: {} %
                    """.format(press if press else '~', temps if temps else '~', amp if amp else '~'))
       
except Exception as e:
    st.error(f"❌ Erreur lors de la récupération des tâches: {str(e)}")
finally:
    if 'conn' in locals():
        conn.close()
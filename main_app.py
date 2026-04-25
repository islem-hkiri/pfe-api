import streamlit as st
import subprocess
import sys
import os
import socket
import time
import atexit
import requests
import sqlite3
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 🔥 CONFIGURATION API RENDER (serveur remote)
# ==========================================
API_BASE_URL = "https://pfe-api-uju4.onrender.com"

# Base de données locale
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

def init_local_db():
    """Initialiser la base locale si nécessaire"""
    from database_v2 import init_db
    if not os.path.exists(DB_PATH):
        init_db()

init_local_db()

# ==========================================
# 🔐 GESTION LOGIN
# ==========================================
if "role" not in st.session_state:
    st.session_state.role = None

def login():
    st.set_page_config(page_title="Gestion Production - Connexion", page_icon="")
    
    st.title(" Connexion - Gestion Production")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("https://cdn-icons-png.flaticon.com/512/295/295128.png", width=100)
        
        user = st.text_input(" Utilisateur", placeholder="logistique ou operateur")
        password = st.text_input(" Mot de passe", type="password", placeholder="********")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Se connecter", use_container_width=True, type="primary"):
                if user.lower() == "logistique" and password == "log123":
                    st.session_state.role = "Logistique"
                    st.rerun()
                elif user.lower() == "operateur" and password == "op123":
                    st.session_state.role = "Opérateur"
                    st.rerun()
                else:
                    st.error("❌ Utilisateur ou mot de passe incorrect")
        
        with col_btn2:
            if st.button("Réinitialiser", use_container_width=True):
                st.session_state.role = None
                st.rerun()

# Affichage du login si pas connecté
if st.session_state.role is None:
    login()
    st.stop()

# ==========================================
# INTERFACE PRINCIPALE APRÈS LOGIN
# ==========================================
st.set_page_config(page_title="Gestion Production", layout="wide")

# Sidebar avec infos
with st.sidebar:
    st.title(f" Bonjour {st.session_state.role}")
    
    # Tester la connexion à l'API Render
    try:
        response = requests.get(f"{API_BASE_URL}/api/etat?shift=B", timeout=5)
        if response.status_code == 200:
            st.success("🟢 Connecté à l'API Render")
            data = response.json()
            st.metric("État Machine Shift B", data.get('statut', 'Inconnu'))
            st.metric("Machine Disponible", "✅ Oui" if data.get('machine_disponible') else "❌ Non")
        else:
            st.error("🔴 API Render non disponible")
    except Exception as e:
        st.error(f"🔴 Erreur connexion API: {e}")
    
    st.markdown("---")
    
    # Bouton pour ajouter demande test
    if st.button("🧪 Ajouter demande TEST", use_container_width=True):
        try:
            response = requests.get(f"{API_BASE_URL}/api/add_direct", timeout=5)
            if response.status_code == 200:
                st.success("✅ Demande TEST ajoutée sur le serveur!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Erreur ajout demande")
        except Exception as e:
            st.error(f"Erreur: {e}")
    
    st.markdown("---")
    
    if st.button(" Déconnexion", use_container_width=True):
        st.session_state.role = None
        st.rerun()

# Auto refresh toutes les 5 secondes
st_autorefresh(interval=5000, key="refresh")

# ==========================================
# AFFICHAGE SELON LE RÔLE
# ==========================================
if st.session_state.role == "Logistique":
    # Interface Logistique
    st.title(" Interface Logistique - Supervision")
    st.markdown("---")
    
    try:
        # Récupérer l'état depuis l'API Render
        response = requests.get(f"{API_BASE_URL}/api/etat?shift=B", timeout=5)
        if response.status_code == 200:
            data = response.json()
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("État Machine", data.get('statut', 'Inconnu'))
            with col2:
                st.metric("Machine Disponible", "✅ Oui" if data.get('machine_disponible') else "❌ Non")
            with col3:
                st.metric("Dernière mise à jour", datetime.now().strftime("%H:%M:%S"))
        else:
            st.error("Impossible de récupérer l'état machine")
    except Exception as e:
        st.error(f"Erreur API: {e}")
    
    st.markdown("---")
    
    # Afficher les demandes en attente/en cours
    st.subheader(" Demandes de Production")
    
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT id, reference, quantite, shift, statut, urgence, date_besoin, heure_demande
    FROM Demandes 
    WHERE statut NOT LIKE '%Terminé%' AND statut != 'Archive'
    ORDER BY 
        CASE 
            WHEN statut LIKE '%En cours%' THEN 1 
            ELSE 2 
        END,
        date_besoin ASC
    """
    df = pd.read_sql_query(query, conn)
    
    if not df.empty:
        # Colorer les lignes selon le statut
        def color_status(val):
            if 'En cours' in val:
                return 'background-color: #ffcccc'
            elif 'En attente' in val:
                return 'background-color: #fff3cd'
            return ''
        
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info(" Aucune demande en attente ou en cours")
    
    # Ajouter nouvelle demande
    st.markdown("---")
    st.subheader(" Nouvelle Demande de Production")
    
    col1, col2 = st.columns(2)
    with col1:
        ref = st.text_input("Référence produit", "TEST_001")
        qte = st.number_input("Quantité", 1, 10000, 10)
    with col2:
        shift_choice = st.selectbox("Shift", ["A", "B"])
        urgence = st.selectbox("Niveau d'urgence", ["Normal", "Urgent", "Critique"])
        date_besoin = st.date_input("Date de besoin", datetime.now())
    
    if st.button(" Envoyer la demande", type="primary", use_container_width=True):
        try:
            # Ajouter directement dans la base locale (qui sera utilisée par l'API Render)
            conn.execute("""
                INSERT INTO Demandes (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
                VALUES (?, ?, ?, ?, '🟠En attente', ?, datetime('now'))
            """, (ref, qte, date_besoin.strftime("%Y-%m-%d"), shift_choice, urgence))
            conn.commit()
            st.success(f"✅ Demande ajoutée pour shift {shift_choice}!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Erreur: {e}")
    
    # Section alertes pannes
    st.markdown("---")
    st.subheader(" Alertes Pannes")
    
    try:
        df_pannes = pd.read_sql_query("""
            SELECT operateur_id, cause, debut_panne, statut 
            FROM Pannes 
            WHERE statut = '🔴 Ouvert' 
            ORDER BY id DESC
        """, conn)
        
        if not df_pannes.empty:
            for _, row in df_pannes.iterrows():
                st.error(f"""
                    ** ALERTE PANNE**
                    - **Opérateur:** {row['operateur_id']}
                    - **Message:** {row['cause']}
                    - **Heure:** {row['debut_panne']}
                """)
            
            if st.button("✅ Confirmer réception", use_container_width=True):
                conn.execute("UPDATE Pannes SET statut = 'Résolu', fin_panne = datetime('now') WHERE statut = '🔴 Ouvert'")
                conn.commit()
                st.success("Alertes marquées comme traitées")
                st.rerun()
        else:
            st.success("✅ Aucune panne signalée")
    except Exception as e:
        st.info("Système d'alertes prêt")
    
    conn.close()

else:
    # ==========================================
    # INTERFACE OPÉRATEUR
    # ==========================================
    st.title(" Interface Opérateur - Poste Soudure")
    st.markdown("---")
    
    # Sélection du shift
    shift_op = st.radio(" Sélectionner votre Shift", ["A", "B"], horizontal=True)
    
    st.subheader(f" Tâches pour Shift {shift_op}")
    
    conn = sqlite3.connect(DB_PATH)
    
    query = """
    SELECT d.id, d.reference, d.quantite, d.statut, 
        p.module, p.famille, p.pression, p.temps, p.amplitude,
        d.debut_production, d.fin_production
    FROM Demandes d
    LEFT JOIN Produits p ON d.reference = p.reference
    WHERE d.shift = ? AND d.statut NOT LIKE '%Terminé%' AND d.statut != 'Archive'
    ORDER BY 
        CASE 
            WHEN d.statut LIKE '%En cours%' THEN 1 
            ELSE 2 
        END,
        d.date_besoin ASC
    """
    tasks = conn.execute(query, (shift_op,)).fetchall()
    
    if tasks:
        for task in tasks:
            (id_d, ref, qte, statut, module, famille, 
            pression, temps, amplitude, debut_prod, fin_prod) = task
            
            # Déterminer la couleur selon le statut
            if "En cours" in statut:
                status_color = "🔴"
                status_text = "EN COURS"
            elif "En attente" in statut:
                status_color = "🟠"
                status_text = "EN ATTENTE"
            else:
                status_color = "⚪"
                status_text = statut
            
            with st.expander(f"{status_color} {status_text} - {module or ref} | {famille or ''} | Qté: {qte}"):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown(f"""
                    ** Détails de production:**
                    - **Référence:** `{ref}`
                    - **Quantité à produire:** `{qte}`
                    - **Module:** {module or 'Non défini'}
                    - **Famille:** {famille or 'Non définie'}
                    """)
                    
                    if pression or temps or amplitude:
                        st.markdown(f"""
                        ** Paramètres soudure:**
                        - **Pression:** {pression if pression else '~'} bar
                        - **Temps:** {temps if temps else '~'} s
                        - **Amplitude:** {amplitude if amplitude else '~'} %
                        """)
                
                with col2:
                    if "En attente" in statut:
                        if st.button(f" Lancer production", key=f"start_{id_d}", use_container_width=True):
                            try:
                                # Appeler l'API increment
                                response = requests.post(
                                    f"{API_BASE_URL}/api/increment",
                                    json={"shift": shift_op},
                                    timeout=5
                                )
                                if response.status_code == 200:
                                    st.success("✅ Production lancée!")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("Erreur lancement")
                            except Exception as e:
                                # Fallback local
                                conn.execute("""
                                    UPDATE Demandes 
                                    SET statut = '🟢En cours', debut_production = datetime('now') 
                                    WHERE id = ?
                                """, (id_d,))
                                conn.commit()
                                st.success("✅ Production lancée (mode local)!")
                                st.rerun()
                    
                    elif "En cours" in statut:
                        st.info("🔴 **Production en cours...**")
                        if debut_prod:
                            st.caption(f"Débutée à: {debut_prod}")
                        
                        if st.button(f"✅ Terminer production", key=f"end_{id_d}", use_container_width=True):
                            try:
                                # Incrémenter jusqu'à finir
                                response = requests.post(
                                    f"{API_BASE_URL}/api/increment",
                                    json={"shift": shift_op},
                                    timeout=5
                                )
                                st.rerun()
                            except:
                                conn.execute("""
                                    UPDATE Demandes 
                                    SET statut = '✅ Terminé', fin_production = datetime('now') 
                                    WHERE id = ?
                                """, (id_d,))
                                conn.commit()
                                st.rerun()
                    
                    st.caption(f" ID: {id_d}")
    else:
        st.success(" Aucune tâche en attente pour ce shift")
        st.info(" Si vous avez des demandes, vérifiez que le shift est correct")
    
    # Section signalement panne
    st.markdown("---")
    st.subheader(" Signaler une Panne")
    
    with st.form("panne_form"):
        cause = st.text_area("📝 Description de la panne", placeholder="Décrivez le problème...")
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button(" SIGNALER", use_container_width=True, type="primary")
        with col2:
            st.caption(f"Opérateur: {st.session_state.role} | Shift: {shift_op}")
        
        if submitted and cause:
            try:
                # Ajouter la panne dans la base locale
                conn.execute("""
                    INSERT INTO Pannes (operateur_id, cause, debut_panne, statut)
                    VALUES (?, ?, datetime('now'), '🔴 Ouvert')
                """, (f"OP_{shift_op}", cause))
                conn.commit()
                st.error("✅ Panne signalée au superviseur!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Erreur: {e}")
        elif submitted and not cause:
            st.warning("Veuillez décrire la panne")
    
    conn.close()
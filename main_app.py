import streamlit as st
import subprocess
import sys
import os
import socket
import time
import atexit
import threading
import requests
import sqlite3
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 🔥 CONFIGURATION
# ==========================================
API_BASE_URL = "http://localhost:8000"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

api_process = None

def init_local_db():
    """Initialiser la base locale si nécessaire"""
    try:
        from database_v2 import init_db
        if not os.path.exists(DB_PATH):
            init_db()
            print("✅ Base de données initialisée")
    except Exception as e:
        print(f"Erreur initialisation DB: {e}")

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return False
        except socket.error:
            return True

def run_api_in_background():
    """Exécute l'API dans un processus background"""
    global api_process
    if is_port_in_use(8000):
        print("✅ API déjà en cours d'exécution sur le port 8000")
        return None
    
    print("🚀 Démarrage de l'API en arrière-plan...")
    
    # Démarrer l'API en processus séparé
    api_process = subprocess.Popen(
        [sys.executable, "api_local_websocket.py"],
        stdout=subprocess.DEVNULL,   # Cache la sortie
        stderr=subprocess.DEVNULL,   # Cache les erreurs
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0  # Pas de fenêtre sur Windows
    )
    
    # Attendre que l'API soit prête
    time.sleep(3)
    
    if not is_port_in_use(8000):
        print("❌ L'API n'a pas démarré correctement")
        return None
    
    print("✅ API démarrée en arrière-plan sur http://localhost:8000")
    return api_process

def cleanup_api():
    """Nettoie l'API à la fermeture"""
    global api_process
    if api_process and api_process.poll() is None:
        api_process.terminate()
        print("🛑 API arrêtée")

def ajouter_demande_test():
    """Ajoute une demande test directement dans la base de données"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Demandes'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM Demandes WHERE shift = 'B' AND statut NOT LIKE '%Terminé%'")
            count = cursor.fetchone()[0]
            
            if count == 0:
                cursor.execute("""
                    INSERT INTO Demandes (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
                    VALUES ('TEST_001', 10, date('now'), 'B', '🟠En attente', 'Normal', datetime('now'))
                """)
                conn.commit()
                print("✅ Demande TEST_001 ajoutée automatiquement!")
                return True
        conn.close()
    except Exception as e:
        print(f"❌ Erreur ajout demande test: {e}")
    return False

# ==========================================
# INITIALISATION AU DÉMARRAGE
# ==========================================
init_local_db()

# Démarrer l'API en arrière-plan
if "api_started" not in st.session_state:
    st.session_state.api_started = True
    run_api_in_background()
    atexit.register(cleanup_api)
    
    # Attendre que l'API soit prête
    time.sleep(2)
    
    # Ajouter une demande test
    ajouter_demande_test()

# Vérifier périodiquement si l'API tourne
def check_api():
    try:
        response = requests.get(f"{API_BASE_URL}/api/etat?shift=B", timeout=2)
        return response.status_code == 200
    except:
        return False

# ==========================================
# GESTION LOGIN
# ==========================================
if "role" not in st.session_state:
    st.session_state.role = None

def login():
    st.set_page_config(page_title="Gestion Production - Connexion", page_icon="🔐")
    
    st.title("🔐 Connexion - Gestion Production")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 👷 Système de Gestion de Production")
        st.image("https://cdn-icons-png.flaticon.com/512/295/295128.png", width=80)
        st.markdown("---")
        
        user = st.text_input("👤 Utilisateur", placeholder="logistique ou operateur")
        password = st.text_input("🔒 Mot de passe", type="password", placeholder="********")
        
        if st.button("🔓 Se connecter", use_container_width=True, type="primary"):
            if user.lower() == "logistique" and password == "log123":
                st.session_state.role = "Logistique"
                st.rerun()
            elif user.lower() == "operateur" and password == "op123":
                st.session_state.role = "Opérateur"
                st.rerun()
            else:
                st.error("❌ Utilisateur ou mot de passe incorrect")
        
        st.markdown("---")
        st.caption("🔑 Identifiants: logistique/log123 | operateur/op123")

if st.session_state.role is None:
    login()
    st.stop()

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
st.set_page_config(page_title="Gestion Production", layout="wide")

st_autorefresh(interval=5000, key="refresh")

# Sidebar
with st.sidebar:
    st.title(f"👋 {st.session_state.role}")
    
    # Vérifier l'API en arrière-plan
    if check_api():
        st.success("🟢 API opérationnelle (arrière-plan)")
        try:
            response = requests.get(f"{API_BASE_URL}/api/etat?shift=B", timeout=3)
            if response.status_code == 200:
                data = response.json()
                st.metric("État Machine Shift B", data.get('statut', 'Inconnu'))
        except:
            pass
    else:
        st.warning("🟡 Démarrage de l'API en cours...")
    
    st.markdown("---")
    
    # Bouton pour forcer l'ajout d'une demande test
    if st.button("🧪 Ajouter demande TEST", use_container_width=True):
        if ajouter_demande_test():
            st.success("✅ Demande TEST ajoutée!")
            time.sleep(1)
            st.rerun()
        else:
            st.info("ℹ️ Demande déjà existante")
    
    st.markdown("---")
    
    # Afficher le statut de l'API
    st.caption("ℹ️ L'API tourne en arrière-plan")
    st.caption(f"📡 http://localhost:8000")
    
    if st.button("🚪 Déconnexion", use_container_width=True):
        st.session_state.role = None
        st.rerun()

# ==========================================
# INTERFACE LOGISTIQUE
# ==========================================
if st.session_state.role == "Logistique":
    st.title("🏭 Interface Logistique - Supervision")
    st.markdown("---")
    
    # Afficher l'état machine
    if check_api():
        try:
            response = requests.get(f"{API_BASE_URL}/api/etat?shift=B", timeout=3)
            if response.status_code == 200:
                data = response.json()
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🚦 État Machine", data.get('statut', 'Inconnu'))
                with col2:
                    st.metric("🟢 Machine Disponible", "✅ Oui" if data.get('machine_disponible') else "❌ Non")
                with col3:
                    st.metric("⏰ Mise à jour", datetime.now().strftime("%H:%M:%S"))
        except Exception as e:
            st.warning("⏳ API en cours de démarrage...")
    else:
        st.info("⏳ Démarrage de l'API en arrière-plan...")
    
    st.markdown("---")
    
    # Afficher les demandes
    st.subheader("📋 Demandes de Production")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT id, reference, quantite, shift, statut, urgence, date_besoin
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
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("📭 Aucune demande en attente ou en cours")
        
        # Ajouter nouvelle demande
        st.markdown("---")
        st.subheader("🛒 Nouvelle Demande")
        
        col1, col2 = st.columns(2)
        with col1:
            ref = st.text_input("Référence", "TEST_001")
            qte = st.number_input("Quantité", 1, 10000, 10)
        with col2:
            shift_choice = st.selectbox("Shift", ["A", "B"])
            urgence = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
            date_besoin = st.date_input("Date besoin", datetime.now())
        
        if st.button("📤 Envoyer", type="primary", use_container_width=True):
            conn.execute("""
                INSERT INTO Demandes (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
                VALUES (?, ?, ?, ?, '🟠En attente', ?, datetime('now'))
            """, (ref, qte, date_besoin.strftime("%Y-%m-%d"), shift_choice, urgence))
            conn.commit()
            st.success(f"✅ Demande ajoutée!")
            st.rerun()
        
        # Alertes pannes
        st.markdown("---")
        st.subheader("🚨 Alertes Pannes")
        
        df_pannes = pd.read_sql_query("""
            SELECT operateur_id, cause, debut_panne, statut 
            FROM Pannes WHERE statut = '🔴 Ouvert' ORDER BY id DESC
        """, conn)
        
        if not df_pannes.empty:
            for _, row in df_pannes.iterrows():
                st.error(f"""
                    **🚨 ALERTE PANNE**
                    - **Opérateur:** {row['operateur_id']}
                    - **Message:** {row['cause']}
                    - **Heure:** {row['debut_panne']}
                """)
            
            if st.button("✅ Confirmer réception", use_container_width=True):
                conn.execute("UPDATE Pannes SET statut = 'Résolu', fin_panne = datetime('now') WHERE statut = '🔴 Ouvert'")
                conn.commit()
                st.success("Alertes traitées")
                st.rerun()
        else:
            st.success("✅ Aucune panne signalée")
        
        conn.close()
    except Exception as e:
        st.error(f"Erreur: {e}")

# ==========================================
# INTERFACE OPÉRATEUR
# ==========================================
else:
    st.title("🔧 Interface Opérateur - Poste Soudure")
    
    shift_op = st.radio("📋 Shift", ["A", "B"], horizontal=True)
    st.subheader(f"📋 Tâches Shift {shift_op}")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT d.id, d.reference, d.quantite, d.statut, 
               p.module, p.famille, p.pression, p.temps, p.amplitude,
               d.debut_production
        FROM Demandes d
        LEFT JOIN Produits p ON d.reference = p.reference
        WHERE d.shift = ? AND d.statut NOT LIKE '%Terminé%' AND d.statut != 'Archive'
        ORDER BY 
            CASE WHEN d.statut LIKE '%En cours%' THEN 1 ELSE 2 END,
            d.date_besoin ASC
        """
        tasks = conn.execute(query, (shift_op,)).fetchall()
        
        if tasks:
            for task in tasks:
                (id_d, ref, qte, statut, module, famille, 
                 pression, temps, amplitude, debut_prod) = task
                
                emoji = "🔴" if "En cours" in statut else "🟠"
                
                with st.expander(f"{emoji} {module or ref} | Qté: {qte}"):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.write(f"**Réf:** {ref}")
                        st.write(f"**Famille:** {famille or '~'}")
                        if pression:
                            st.write(f"**Paramètres:** {pression} bar / {temps}s / {amplitude}%")
                    with col2:
                        if "En attente" in statut:
                            if st.button(f"🚀 Lancer", key=f"start_{id_d}"):
                                if check_api():
                                    try:
                                        requests.post(f"{API_BASE_URL}/api/increment", json={"shift": shift_op}, timeout=3)
                                        st.success("Lancé!")
                                        st.rerun()
                                    except:
                                        conn.execute("UPDATE Demandes SET statut = '🟢En cours', debut_production = datetime('now') WHERE id = ?", (id_d,))
                                        conn.commit()
                                        st.rerun()
                                else:
                                    conn.execute("UPDATE Demandes SET statut = '🟢En cours', debut_production = datetime('now') WHERE id = ?", (id_d,))
                                    conn.commit()
                                    st.rerun()
                        elif "En cours" in statut:
                            st.info("🔴 Production en cours...")
                            if debut_prod:
                                st.caption(f"Début: {debut_prod}")
        else:
            st.success("✅ Aucune tâche en attente")
        
        # Signaler panne
        st.markdown("---")
        st.subheader("🚨 Signaler Panne")
        with st.form("panne_form"):
            cause = st.text_area("Description de la panne")
            if st.form_submit_button("🚨 SIGNALER", type="primary"):
                if cause:
                    conn.execute("""
                        INSERT INTO Pannes (operateur_id, cause, debut_panne, statut)
                        VALUES (?, ?, datetime('now'), '🔴 Ouvert')
                    """, (f"OP_{shift_op}", cause))
                    conn.commit()
                    st.error("✅ Panne signalée au superviseur!")
                    st.rerun()
                else:
                    st.warning("Veuillez décrire la panne")
        
        conn.close()
    except Exception as e:
        st.error(f"Erreur: {e}")
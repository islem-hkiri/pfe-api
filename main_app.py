# main_app.py (version finale)
import streamlit as st
import subprocess
import sys
import os
import socket
import time
import atexit
import threading

# ========== AUTO-LANCEMENT API ==========
api_process = None

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return False
        except socket.error:
            return True

def start_api():
    global api_process
    if is_port_in_use(8000):
        st.sidebar.info("ℹ️ API déjà en cours d'exécution")
        return None
    
    try:
        api_process = subprocess.Popen(
            [sys.executable, "api_endpoints_fastapi.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        time.sleep(3)
        
        if is_port_in_use(8000):
            st.sidebar.success("✅ API démarrée avec succès!")
            return api_process
        else:
            st.sidebar.error("❌ L'API n'a pas démarré")
            return None
    except Exception as e:
        st.sidebar.error(f"❌ Erreur: {e}")
        return None

def cleanup_api():
    global api_process
    if api_process and api_process.poll() is None:
        try:
            api_process.terminate()
            time.sleep(1)
            if api_process.poll() is None:
                api_process.kill()
        except:
            pass

# Démarrer API au lancement
if "api_started" not in st.session_state:
    st.session_state.api_started = True
    start_api()
    atexit.register(cleanup_api)

# ========== INITIALISATION DB ==========
if "db_checked" not in st.session_state:
    st.session_state.db_checked = True
    try:
        import database_v2
        if not os.path.exists(database_v2.DB_PATH):
            st.info("📦 Première initialisation de la base...")
            database_v2.init_db()
    except Exception as e:
        st.warning(f"⚠️ Base non initialisée: {e}")

# ========== INTERFACE CONNEXION ==========
if "role" not in st.session_state:
    st.session_state.role = None

def login():
    st.title("🔐 Gestion Production - PFE")
    st.markdown("### Connexion")
    
    col1, col2 = st.columns(2)
    with col1:
        user = st.text_input("👤 Utilisateur", placeholder="logistique ou operateur")
        password = st.text_input("🔑 Mot de passe", type="password", placeholder="log123 ou op123")
        
        if st.button("🚀 Se connecter", use_container_width=True):
            if user.lower() == "logistique" and password == "log123":
                st.session_state.role = "Logistique"
                st.rerun()
            elif user.lower() == "operateur" and password == "op123":
                st.session_state.role = "Opérateur"
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect")
    
    with col2:
        st.info("""
        **Comptes par défaut:**
        - **Logistique:** `logistique` / `log123`
        - **Opérateur:** `operateur` / `op123`
        """)

if st.session_state.role is None:
    login()
else:
    with st.sidebar:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### 👋 {st.session_state.role}")
        with col2:
            if st.button("🚪", help="Déconnexion"):
                st.session_state.role = None
                st.rerun()
        
        st.markdown("---")
        
        # Statut API
        if is_port_in_use(8000):
            st.success("🟢 API: Connectée")
            st.caption(f"http://localhost:8000")
        else:
            st.error("🔴 API: Déconnectée")
            if st.button("🔄 Redémarrer API"):
                start_api()
                st.rerun()
    
    # Charger l'application selon le rôle
    if st.session_state.role == "Logistique":
        exec(open("logistique_app.py").read())
    elif st.session_state.role == "Opérateur":
        exec(open("operateur_app.py").read())
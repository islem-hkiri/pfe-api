import streamlit as st
import subprocess
import sys
import os
import socket
import time
import atexit
import requests
from streamlit_autorefresh import st_autorefresh
import sqlite3
import pandas as pd
from datetime import datetime
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

# ==========================================
# 🔥 CONFIGURATION API RENDER
# ==========================================
API_BASE_URL = "https://pfe-api-uju4.onrender.com"

# Base de données locale
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

def init_local_db():
    """Initialiser la base locale si nécessaire"""
    try:
        from database_v2 import init_db
        if not os.path.exists(DB_PATH):
            init_db()
    except Exception as e:
        st.error(f"Erreur initialisation DB: {e}")

# Initialiser la base au démarrage
init_local_db()
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
        return None
    
    api_process = subprocess.Popen(
        [sys.executable, "api_local_websocket.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    return api_process

def cleanup_api():
    global api_process
    if api_process and api_process.poll() is None:
        api_process.terminate()

if "api_started" not in st.session_state:
    st.session_state.api_started = True
    start_api()
    atexit.register(cleanup_api)

if "role" not in st.session_state:
    st.session_state.role = None

def login():
    st.title("Connexion")
    user = st.text_input("Utilisateur (Logistique ou Opérateur)")
    password = st.text_input("Mot de passe", type="password")
    
    if st.button("Se connecter"):
        if user.lower() == "logistique" and password == "log123":
            st.session_state.role = "Logistique"
            st.rerun()
        elif user.lower() == "operateur" and password == "op123":
            st.session_state.role = "Opérateur"
            st.rerun()
        else:
            st.error("Mot de passe incorrect")

if st.session_state.role is None:
    login()
else:
    with st.sidebar:
        if is_port_in_use(8000):
            st.success("🟢 API connectée")
        else:
            st.error("🔴 API déconnectée")
        
        if st.button("Déconnexion"):
            st.session_state.role = None
            st.rerun()
    
    st_autorefresh(interval=10000, key="datarefresh")
    
    try:
        response = requests.get("http://localhost:8000/api/etat?shift=A")
        if response.status_code == 200:
            data = response.json()
            st.write("Dernière mise à jour :", data)
        else:
            st.error(f"Erreur API: {response.status_code}")
    except Exception as e:
        st.error(f"Erreur lors de la récupération des données : {e}")
    
    if st.session_state.role == "Logistique":
        exec(open("logistique_app.py").read())
    elif st.session_state.role == "Opérateur":
        exec(open("operateur_app.py").read())
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
        st.info("✅ API déjà en cours d'exécution")
        return None
    
    st.info("🚀 Démarrage de l'API...")
    api_process = subprocess.Popen(
        [sys.executable, "api_local_websocket.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    return api_process

def cleanup_api():
    global api_process
    if api_process and api_process.poll() is None:
        api_process.terminate()

def ajouter_demande_test():
    """Ajoute une demande de test automatiquement"""
    try:
        conn = sqlite3.connect("gestion_production.db")
        cursor = conn.cursor()
        
        # Vérifier si la table Demandes existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Demandes'")
        if cursor.fetchone():
            # Ajouter une demande test pour shift B
            cursor.execute("""
                INSERT INTO Demandes (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
                VALUES ('TEST_001', 10, date('now'), 'B', '🟠En attente', 'Normal', datetime('now'))
            """)
            conn.commit()
            st.success("✅ Demande TEST_001 ajoutée avec succès!")
        else:
            st.warning("⚠️ Base de données pas encore initialisée")
        conn.close()
    except Exception as e:
        st.error(f"❌ Erreur ajout demande test: {e}")

# Démarrer l'API si pas encore démarrée
if "api_started" not in st.session_state:
    st.session_state.api_started = True
    api_proc = start_api()
    atexit.register(cleanup_api)
    
    # Attendre un peu que l'API soit prête
    time.sleep(2)
    
    # Ajouter une demande test automatiquement
    ajouter_demande_test()

with st.sidebar:
    if is_port_in_use(8000):
        st.success("🟢 API connectée")
    else:
        st.error("🔴 API déconnectée")
    
    # Bouton pour ajouter une demande test manuellement
    if st.button("➕ Ajouter demande TEST", use_container_width=True):
        ajouter_demande_test()
        st.rerun()
    
    st.markdown("---")
    
    # Sélecteur de rôle direct (sans mot de passe)
    role = st.radio("📱 Choisir l'interface", ["Logistique", "Opérateur"], horizontal=True)

st_autorefresh(interval=10000, key="datarefresh")

try:
    response = requests.get("http://localhost:8000/api/etat?shift=B")
    if response.status_code == 200:
        data = response.json()
        st.info(f"🔄 État machine shift B: {data.get('statut', 'Inconnu')}")
    else:
        st.error(f"Erreur API: {response.status_code}")
except Exception as e:
    st.error(f"Erreur connexion API: {e}")

if role == "Logistique":
    exec(open("logistique_app.py").read())
elif role == "Opérateur":
    exec(open("operateur_app.py").read())
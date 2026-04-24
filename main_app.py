# main_app.py
import streamlit as st
import subprocess
import sys
import os
import socket
import time
import atexit

from streamlit_autorefresh import st_autorefresh

# Refresh el page kol 10000ms (10 secondes)
st_autorefresh(interval=10000, key="datarefresh")

# El code elli ta7tou bech yet3awed automatique kol 10s
data = requests.get("https://pfe-api-uju4.onrender.com/api/etat?shift=shift").json()
st.write("Dernière mise à jour :", data)

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
        return None
    
    api_process = subprocess.Popen(
        [sys.executable, "api_endpoints_fastapi.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    return api_process

def cleanup_api():
    global api_process
    if api_process and api_process.poll() is None:
        api_process.terminate()

# Démarrer API au lancement
if "api_started" not in st.session_state:
    st.session_state.api_started = True
    start_api()
    atexit.register(cleanup_api)

# ========== TON CODE ORIGINAL (GARDE LA SUITE) ==========
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
        # Afficher statut API
        if is_port_in_use(8000):
            st.success("🟢 API connectée")
        else:
            st.error("🔴 API déconnectée")
        
        if st.button("Déconnexion"):
            st.session_state.role = None
            st.rerun()
    
    if st.session_state.role == "Logistique":
        exec(open("logistique_app.py").read())
    elif st.session_state.role == "Opérateur":
        exec(open("operateur_app.py").read())
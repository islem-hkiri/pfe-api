import streamlit as st
import subprocess
import sys
import os
import time
import requests
import atexit

# ========== كود باش يطلق API في الخلفية ==========
api_process = None

def start_api():
    """دالة باش تطلق API"""
    global api_process
    
    # نتأكد من أن API مش شغالة
    try:
        requests.get("http://localhost:8000/")
        print("✅ API شغالة قبل")
        return True
    except:
        pass
    
    print("🚀 نطلق API...")
    
    # مسار API
    api_file = "api_local_websocket.py"
    
    if sys.platform == "win32":
        # تخفي API (ما تظهرش نافذة)
        api_process = subprocess.Popen(
            ["python", api_file],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    else:
        api_process = subprocess.Popen(["python", api_file])
    
    # نستنو 3 ثواني باش API تطلق
    time.sleep(3)
    print(f"✅ API طلقت! (PID: {api_process.pid})")
    return True

def stop_api():
    """دالة باش تقفل API"""
    global api_process
    if api_process:
        print("🛑 نقفل API...")
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(api_process.pid)])
        else:
            api_process.terminate()
        print("✅ API تقفلت")

# لما تسكر التطبيق، API تقفل وحدها
atexit.register(stop_api)

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
    if st.sidebar.button("Déconnexion"):
        st.session_state.role = None
        st.rerun()

    if st.session_state.role == "Logistique":
        st.sidebar.success("Connecté : Logistique")
        exec(open("logistique_app.py").read())
    elif st.session_state.role == "Opérateur":
        st.sidebar.info("Connecté : Opérateur")
        exec(open("operateur_app.py").read())
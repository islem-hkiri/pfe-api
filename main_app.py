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
    
    # نتأكد إذا API شغالة
    try:
        requests.get("http://localhost:8000/")
        print("✅ API déjà en marche")
        return True
    except:
        pass
    
    print("🚀 تشغيل API...")
    
    api_file = "api_local_websocket.py"
    
    # نتأكد من وجود الفايل
    if not os.path.exists(api_file):
        print(f"❌ الملف {api_file} غير موجود!")
        return False

    try:
        if sys.platform == "win32":
            api_process = subprocess.Popen(
                ["python", api_file],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            api_process = subprocess.Popen(["python", api_file])
        
        # نستناو باش API تقوم
        time.sleep(3)

        # نتحقق مرة أخرى
        try:
            requests.get("http://localhost:8000/")
            print(f"✅ API تم تشغيلها (PID: {api_process.pid})")
            return True
        except:
            print("❌ API ما قامتش كما يلزم")
            return False

    except Exception as e:
        print(f"❌ خطأ أثناء تشغيل API: {e}")
        return False


def stop_api():
    """دالة باش تقفل API"""
    global api_process
    if api_process:
        print("🛑 إيقاف API...")
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(api_process.pid)])
            else:
                api_process.terminate()
            print("✅ API توقفت")
        except:
            pass


# لما تسكر التطبيق
atexit.register(stop_api)

# تشغيل API مرة واحدة فقط
if "api_started" not in st.session_state:
    start_api()
    st.session_state.api_started = True

# ========== AUTH ==========
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

# ========== MAIN ==========
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
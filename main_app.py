import streamlit as st
import requests

st.set_page_config(page_title="Système Production", layout="wide")

API_BASE_URL = "https://pfe-api-uju4.onrender.com"

# ==========================
# LOGIN
# ==========================

if "role" not in st.session_state:
    st.session_state.role = None

def login():
    st.title("Connexion")

    user = st.text_input("Utilisateur")
    password = st.text_input("Mot de passe", type="password")

    if st.button("Se connecter"):
        if user.lower() == "logistique" and password == "log123":
            st.session_state.role = "Logistique"
            st.rerun()
        elif user.lower() == "operateur" and password == "op123":
            st.session_state.role = "Opérateur"
            st.rerun()
        else:
            st.error("Identifiants incorrects")

# ==========================
# ROUTING
# ==========================

if st.session_state.role is None:
    login()

else:
    with st.sidebar:
        st.success(f"Connecté en tant que {st.session_state.role}")

        if st.button("Déconnexion"):
            st.session_state.role = None
            st.rerun()

    # Charger la bonne interface
    if st.session_state.role == "Logistique":
        exec(open("logistique_app.py").read())

    elif st.session_state.role == "Opérateur":
        exec(open("operateur_app.py").read())
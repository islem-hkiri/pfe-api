import streamlit as st

# ========== PLUS DE LANCEMENT AUTOMATIQUE DE L'API ==========
# Tu lanceras api_endpoints.py dans un terminal séparé.

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
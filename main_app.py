import streamlit as st
import requests
import sqlite3
import pandas as pd
import os
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
    try:
        from database_v2 import init_db
        if not os.path.exists(DB_PATH):
            init_db()
    except Exception as e:
        st.error(f"Erreur initialisation DB: {e}")

# Initialiser la base au démarrage
init_local_db()

# ==========================================
# 🔐 GESTION LOGIN
# ==========================================
if "role" not in st.session_state:
    st.session_state.role = None

def login():
    st.set_page_config(page_title="Gestion Production - Connexion", page_icon="🔐")
    
    st.title("🔐 Connexion - Gestion Production")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
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

if st.session_state.role is None:
    login()
    st.stop()

# ==========================================
# INTERFACE PRINCIPALE APRÈS LOGIN
# ==========================================
st.set_page_config(page_title="Gestion Production", layout="wide")

# Auto refresh toutes les 5 secondes
st_autorefresh(interval=5000, key="refresh")

# Sidebar
with st.sidebar:
    st.title(f"👋 {st.session_state.role}")
    
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
    
    if st.button("🚪 Déconnexion", use_container_width=True):
        st.session_state.role = None
        st.rerun()

# ==========================================
# INTERFACE LOGISTIQUE
# ==========================================
if st.session_state.role == "Logistique":
    st.title("🏭 Interface Logistique - Supervision")
    st.markdown("---")
    
    # Afficher l'état machine depuis Render
    try:
        response = requests.get(f"{API_BASE_URL}/api/etat?shift=B", timeout=5)
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
        st.error(f"Erreur API: {e}")
    
    st.markdown("---")
    
    # Afficher les demandes depuis la base locale
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
        
        if st.button("📤 Envoyer", type="primary"):
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
                    **🚨 ALERTE**
                    - **Opérateur:** {row['operateur_id']}
                    - **Message:** {row['cause']}
                    - **Heure:** {row['debut_panne']}
                """)
            
            if st.button("✅ Confirmer"):
                conn.execute("UPDATE Pannes SET statut = 'Résolu', fin_panne = datetime('now') WHERE statut = '🔴 Ouvert'")
                conn.commit()
                st.rerun()
        else:
            st.success("✅ Aucune panne")
        
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
        SELECT d.id, d.reference, d.quantite, d.statut, p.module, p.famille,
               p.pression, p.temps, p.amplitude, d.debut_production
        FROM Demandes d
        LEFT JOIN Produits p ON d.reference = p.reference
        WHERE d.shift = ? AND d.statut NOT LIKE '%Terminé%' AND d.statut != 'Archive'
        ORDER BY CASE WHEN d.statut LIKE '%En cours%' THEN 1 ELSE 2 END, d.date_besoin ASC
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
                                try:
                                    requests.post(f"{API_BASE_URL}/api/increment", json={"shift": shift_op}, timeout=5)
                                    st.success("Lancé!")
                                    st.rerun()
                                except:
                                    conn.execute("UPDATE Demandes SET statut = '🟢En cours', debut_production = datetime('now') WHERE id = ?", (id_d,))
                                    conn.commit()
                                    st.rerun()
                        elif "En cours" in statut:
                            st.info("🔴 En cours...")
                            if st.button(f"➕ +1", key=f"inc_{id_d}"):
                                try:
                                    requests.post(f"{API_BASE_URL}/api/increment", json={"shift": shift_op}, timeout=5)
                                    st.rerun()
                                except:
                                    st.rerun()
        else:
            st.success("✅ Aucune tâche")
        
        # Signaler panne
        st.markdown("---")
        st.subheader("🚨 Signaler Panne")
        with st.form("panne"):
            cause = st.text_area("Description")
            if st.form_submit_button("SIGNALER"):
                if cause:
                    conn.execute("""
                        INSERT INTO Pannes (operateur_id, cause, debut_panne, statut)
                        VALUES (?, ?, datetime('now'), '🔴 Ouvert')
                    """, (f"OP_{shift_op}", cause))
                    conn.commit()
                    st.error("✅ Panne signalée!")
                    st.rerun()
        
        conn.close()
    except Exception as e:
        st.error(f"Erreur: {e}")
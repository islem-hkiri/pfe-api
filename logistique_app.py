import streamlit as st
import sqlite3
import requests
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Logistique - Supervision", layout="wide")
st_autorefresh(interval=5000, key="log_refresh")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")
API_BASE = "https://pfe-api-uju4.onrender.com/api"

def get_demandes_api():
    try:
        r = requests.get(f"{API_BASE}/get_demandes", timeout=5)
        return r.json() if r.status_code == 200 else []
    except: return []

st.title("🏭 Demandes & Supervision Production")

# SECTION : SUIVI TEMPS RÉEL (Ordonnancement Intelligent)[cite: 4]
st.subheader("📊 État de la Production")
data = get_demandes_api()
if data:
    df = pd.DataFrame(data)
    # Filter active tasks only[cite: 4]
    df_active = df[~df['statut'].str.contains('Terminé|Archivé', na=False, case=False)].copy()
    
    if not df_active.empty:
        # Mapping priority for sorting[cite: 4]
        urg_map = {"Critique": 1, "Urgent": 2, "Normal": 3}
        df_active['prio_val'] = df_active['urgence'].map(urg_map).fillna(4)
        df_active['status_prio'] = df_active['statut'].apply(lambda x: 0 if 'cours' in str(x).lower() else 1)
        
        # Sort by: 1. Status (En cours first), 2. Urgency, 3. Date[cite: 4]
        df_active = df_active.sort_values(by=['status_prio', 'prio_val', 'date_besoin'])
        
        st.dataframe(df_active[['reference', 'quantite', 'statut', 'shift', 'urgence', 'date_besoin']], 
                     use_container_width=True, hide_index=True)
    else:
        st.success("Toutes les demandes sont traitées.")

st.divider()

# SECTION : CREATION DEMANDE[cite: 5]
st.subheader("➕ Nouvelle Demande")
with st.form("form_demande"):
    c1, c2 = st.columns(2)
    with c1:
        ref = st.text_input("Référence")
        qte = st.number_input("Quantité", 1, 10000, 50)
    with c2:
        urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")
    shift_s = st.radio("Shift", ["A", "B"], horizontal=True)
    
    if st.form_submit_button("Envoyer la demande"):
        resp = requests.post(f"{API_BASE}/create_demande", json={
            "reference": ref, "quantite": qte, "date_besoin": str(date_b),
            "shift": shift_s, "urgence": urg
        })
        if resp.status_code == 200:
            st.success("Demande enregistrée avec succès!")
            st.rerun()
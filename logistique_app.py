import streamlit as st
import sqlite3
import requests
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from database_v2 import init_db

# Configuration
st.set_page_config(page_title="Logistique - Supervision", page_icon="🏭", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")
API_BASE = "https://pfe-api-uju4.onrender.com/api"

if not os.path.exists(DB_PATH):
    init_db()

st_autorefresh(interval=5000, key="log_refresh")
conn_local = sqlite3.connect(DB_PATH)

# ═══════════════════════════════════════════════════════════════════
# FONCTIONS API (SANS CACHE pour test, ou TTL très court)
# ═══════════════════════════════════════════════════════════════════
def get_demandes_api():
    try:
        r = requests.get(f"{API_BASE}/get_demandes", timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Debug: décommenter pour voir les données brutes
            # st.sidebar.write(f"API retourne {len(data)} demandes")
            return data
        else:
            st.error(f"Erreur API: {r.status_code}")
            return []
    except Exception as e:
        st.error(f"Erreur connexion: {e}")
        return []

def get_pannes_api():
    try:
        r = requests.get(f"{API_BASE}/get_pannes", timeout=10)
        return r.json() if r.status_code == 200 else []
    except:
        return []

def create_demande_api(reference, quantite, date_besoin, shift, urgence):
    try:
        resp = requests.post(f"{API_BASE}/create_demande", json={
            "reference": reference, "quantite": quantite, 
            "date_besoin": date_besoin, "shift": shift, "urgence": urgence
        }, timeout=10)
        return resp.status_code == 200, resp.text
    except Exception as e:
        return False, str(e)

# ═══════════════════════════════════════════════════════════════════
# CHARGEMENT DONNÉES
# ═══════════════════════════════════════════════════════════════════
demandes_api = get_demandes_api()
pannes_api = get_pannes_api()

df_demandes = pd.DataFrame(demandes_api) if demandes_api else pd.DataFrame()

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR (KPI)
# ═══════════════════════════════════════════════════════════════════
st.sidebar.title("📊 Tableau de Bord")

# Debug option
show_debug = st.sidebar.checkbox("🐛 Mode Debug (voir données brutes)", value=False)

if show_debug and not df_demandes.empty:
    st.sidebar.write("Colonnes API:", df_demandes.columns.tolist())
    st.sidebar.write("Première ligne:", df_demandes.iloc[0].to_dict() if len(df_demandes) > 0 else "Vide")

total = len(df_demandes)
termine = df_demandes['statut'].str.contains('Terminé', na=False).sum() if not df_demandes.empty else 0

st.sidebar.metric("Total", total)
st.sidebar.metric("Terminées", termine)

# Bouton refresh manuel
if st.sidebar.button("🔄 Forcer le rafraîchissement"):
    st.rerun()

# ═══════════════════════════════════════════════════════════════════
# INTERFACE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════
st.title("🏭 Suivi Production - Render")

# SECTION 1: ALERTES PANNES
st.subheader("🔴 Alertes de Panne en Temps Réel")
df_pannes = pd.DataFrame(pannes_api) if pannes_api else pd.DataFrame()

if not df_pannes.empty:
    df_ouvertes = df_pannes[df_pannes['statut'].str.contains('Ouvert', na=False, case=False)]
    if not df_ouvertes.empty:
        for _, row in df_ouvertes.iterrows():
            st.error(f"🚨 **Panne** | Opérateur: {row.get('operateur_id')} | Cause: {row.get('cause')} | {row.get('debut_panne')}")
        if st.button("✅ Traiter les alertes"):
            requests.post(f"{API_BASE}/resoudre_pannes", timeout=10)
            st.rerun()
    else:
        st.success("✅ Aucune panne signalée")
else:
    st.info("Aucune donnée de panne")

# ═══════════════════════════════════════════════════════════════════
# SECTION 2: SUIVI TEMPS RÉEL - CORRIGÉ
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("📋 Suivi des fabrications en temps réel")

try:
    if df_demandes.empty:
        st.warning("🔄 Aucune donnée reçue de l'API (liste vide)")
        
        # Vérifier connexion
        try:
            test = requests.get(API_BASE.replace('/api', ''), timeout=5)
            st.info(f"Test connexion: {test.status_code}")
        except:
            st.error("❌ Impossible de contacter le serveur Render")
            
    else:
        # Voir toutes les données si mode debug
        if show_debug:
            with st.expander("Voir toutes les données brutes API"):
                st.dataframe(df_demandes)
                st.write("Statuts uniques:", df_demandes['statut'].unique() if 'statut' in df_demandes.columns else "Pas de colonne statut")
        
        # Vérifier que la colonne statut existe
        if 'statut' not in df_demandes.columns:
            st.error("❌ Colonne 'statut' manquante dans les données API")
            st.write("Colonnes disponibles:", df_demandes.columns.tolist())
        else:
            # FILTRAGE CORRIGÉ - Plus flexible avec les emojis
            # On normalise les statuts pour être sûr
            df_demandes['statut_clean'] = df_demandes['statut'].astype(str).str.strip()
            
            # Masque pour en attente ou en cours (insensible à la casse et aux emojis partiels)
            mask_en_cours = (
                df_demandes['statut_clean'].str.contains('cours', case=False, na=False) | 
                df_demandes['statut_clean'].str.contains('attente', case=False, na=False) |
                df_demandes['statut_clean'].str.contains('🟢', na=False) |
                df_demandes['statut_clean'].str.contains('🟠', na=False)
            )
            
            df_suivi = df_demandes[mask_en_cours].copy()
            
            if show_debug:
                st.write(f"Debug: {len(df_suivi)} demandes filtrées sur {len(df_demandes)} total")
            
            if df_suivi.empty:
                st.success("✅ Aucune production en attente ou en cours (tout est terminé ou vide)")
                
                # Afficher quand même un aperçu des 5 dernières demandes pour vérifier
                with st.expander("Voir les 5 dernières demandes (vérification)"):
                    st.dataframe(df_demandes[['reference', 'statut', 'quantite']].head())
            else:
                # TRI: En cours d'abord, puis En attente
                df_suivi['ordre'] = df_suivi['statut_clean'].apply(
                    lambda x: 1 if 'cours' in x.lower() or '🟢' in x else 2
                )
                df_suivi = df_suivi.sort_values(['ordre', 'id'] if 'id' in df_suivi.columns else 'ordre', 
                                                ascending=[True, False] if 'id' in df_suivi.columns else True)
                
                # SÉLECTION et RENOMMAGE des colonnes pour l'affichage
                colonnes_affichage = {
                    'reference': 'Référence',
                    'quantite': 'Qté', 
                    'urgence': 'Urgence',
                    'statut': 'État',
                    'operateur_id': 'Opérateur',
                    'shift': 'Shift',
                    'compteur': 'Produit',
                    'date_besoin': 'Date besoin'
                }
                
                # Ne garder que les colonnes qui existent
                cols_dispo = [c for c in colonnes_affichage.keys() if c in df_suivi.columns]
                df_display = df_suivi[cols_dispo].copy()
                df_display.rename(columns=colonnes_affichage, inplace=True)
                
                # Affichage avec style
                st.dataframe(
                    df_display, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "État": st.column_config.TextColumn("État", help="Statut de la production"),
                        "Qté": st.column_config.NumberColumn("Qté", help="Quantité demandée"),
                        "Urgence": st.column_config.TextColumn("Urgence")
                    }
                )
                
                # Indicateur visuel du nombre
                nbr_attente = len(df_suivi[df_suivi['statut_clean'].str.contains('attente', case=False)])
                nbr_cours = len(df_suivi[df_suivi['statut_clean'].str.contains('cours', case=False)])
                
                col1, col2 = st.columns(2)
                col1.metric("🟢 En cours", nbr_cours)
                col2.metric("🟠 En attente", nbr_attente)

except Exception as e:
    st.error(f"Erreur dans l'affichage du suivi: {e}")
    import traceback
    if show_debug:
        st.code(traceback.format_exc())

# ═══════════════════════════════════════════════════════════════════
# SECTION 3: NOUVELLE DEMANDE
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("➕ Nouvelle Demande")

if "panier" not in st.session_state:
    st.session_state.panier = []

c1, c2 = st.columns(2)
with c1:
    try:
        df_stock = pd.read_sql_query("SELECT reference, quantite FROM Stock", conn_local)
        ref = st.selectbox("Référence", df_stock['reference'].tolist())
        st.caption(f"Stock local: {df_stock[df_stock['reference']==ref]['quantite'].values[0]} pcs")
    except:
        ref = st.text_input("Référence")
    qte = st.number_input("Quantité", 1, 10000, 50)

with c2:
    urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
    date_b = st.date_input("Date besoin", datetime.now())

if st.button("➕ Ajouter au panier"):
    st.session_state.panier.append({
        "ref": ref, "qte": qte, "urg": urg, "date": str(date_b)
    })
    st.rerun()

if st.session_state.panier:
    st.write("🛒 Panier:")
    st.dataframe(pd.DataFrame(st.session_state.panier))
    
    if st.button("🚀 Envoyer à Render", type="primary"):
        for item in st.session_state.panier:
            for shift in ['A', 'B']:
                ok, msg = create_demande_api(item['ref'], item['qte'], item['date'], shift, item['urg'])
                if not ok:
                    st.error(f"Erreur {item['ref']}: {msg}")
        st.session_state.panier = []
        st.success("Envoyé!")
        st.rerun()

conn_local.close()
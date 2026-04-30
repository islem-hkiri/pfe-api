import requests
import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from database_v2 import init_db

# ─── Configuration ───────────────────────────────────────────────
st.set_page_config(page_title="Logistique - Supervision", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

API_BASE = "https://pfe-api-uju4.onrender.com/api"

if not os.path.exists(DB_PATH):
    init_db()

st_autorefresh(interval=5000, key="log_refresh")

# ─── Connexion DB locale (pour stock et historique) ──────────────
conn = sqlite3.connect(DB_PATH)

# ═══════════════════════════════════════════════════════════════════
# FONCTION : Récupérer les demandes depuis l'API EN LIGNE
# ═══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=5)
def get_demandes_api():
    try:
        response = requests.get(f"{API_BASE}/get_demandes", timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return []
    except Exception as e:
        return []

@st.cache_data(ttl=5)
def get_pannes_api():
    try:
        response = requests.get(f"{API_BASE}/get_pannes", timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return []
    except Exception as e:
        return []

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════
st.sidebar.success("Connecté : Logistique")
st.sidebar.title("📊 Tableau de Bord")

# KPI depuis API
demandes = get_demandes_api()
df_api = pd.DataFrame(demandes) if demandes else pd.DataFrame()

if not df_api.empty:
    total = len(df_api)
    termine = len(df_api[df_api['statut'] == 'Terminé']) if 'statut' in df_api.columns else 0
else:
    total = 0
    termine = 0

st.sidebar.metric("📦 Total demandes", total)
st.sidebar.metric("✅ Terminées", termine)

# Temps moyen
if not df_api.empty and 'debut_production' in df_api.columns and 'fin_production' in df_api.columns:
    df_done = df_api[df_api['statut'] == 'Terminé'].copy()
    if not df_done.empty:
        try:
            df_done['debut'] = pd.to_datetime(df_done['debut_production'])
            df_done['fin'] = pd.to_datetime(df_done['fin_production'])
            df_done['duree'] = (df_done['fin'] - df_done['debut']).dt.total_seconds()
            moy = int(df_done['duree'].mean())
            st.sidebar.metric("⏱️ Temps moyen (s)", moy)
        except:
            st.sidebar.metric("⏱️ Temps moyen (s)", "0")
    else:
        st.sidebar.metric("⏱️ Temps moyen (s)", "0")
else:
    st.sidebar.metric("⏱️ Temps moyen (s)", "0")

st.sidebar.markdown("---")
st.sidebar.subheader("⚡ Performance (KPI)")

TEMPS_SHIFT_SEC = 8 * 3600

if not df_api.empty and 'statut' in df_api.columns:
    df_today = df_api[
        (df_api['statut'] == 'Terminé') &
        (pd.to_datetime(df_api.get('fin_production', pd.NaT), errors='coerce').dt.date == datetime.today().date())
    ].copy()

    if not df_today.empty:
        try:
            df_today['debut'] = pd.to_datetime(df_today['debut_production'])
            df_today['fin'] = pd.to_datetime(df_today['fin_production'])
            total_sec = (df_today['fin'] - df_today['debut']).dt.total_seconds().sum()
            taux = min(int((total_sec / TEMPS_SHIFT_SEC) * 100), 100)
            st.sidebar.metric("🏭 Taux d'Occupation Jour", f"{taux}%")
            st.sidebar.progress(taux / 100)
            if taux > 85:
                st.sidebar.warning("⚠️ Charge élevée détectée !")
        except:
            st.sidebar.info("Attente de données de production...")
    else:
        st.sidebar.info("Attente de données de production...")
else:
    st.sidebar.info("Attente de données de production...")

# Bar chart urgence
if not df_api.empty and 'urgence' in df_api.columns:
    df_urg = df_api.groupby('urgence').size().reset_index(name='total')
    st.sidebar.bar_chart(df_urg.set_index('urgence'))

# Historique
st.sidebar.markdown("---")
try:
    if not df_api.empty and 'heure_demande' in df_api.columns:
        df_hist = df_api[df_api['statut'] != 'Archivé'].groupby('heure_demande')['reference'].count().reset_index()
        df_hist.columns = ['heure_demande', 'Nb_Refs']
        df_hist = df_hist.sort_values('heure_demande', ascending=False).head(10)

        if not df_hist.empty:
            if st.sidebar.button("🗑️ Vider l'historique", use_container_width=True):
                try:
                    requests.post(f"{API_BASE}/archiver_demandes", timeout=10)
                    st.rerun()
                except:
                    pass

            for _, row in df_hist.iterrows():
                with st.sidebar.expander(f"📋 Liste du {row['heure_demande']}"):
                    details = df_api[df_api['heure_demande'] == row['heure_demande']][['reference', 'quantite', 'statut']]
                    st.dataframe(details.rename(columns={'reference': 'Ref', 'quantite': 'Qté', 'statut': 'Statut'}),
                                 use_container_width=True)
except Exception as e:
    st.sidebar.error(f"Erreur historique: {e}")

# Déconnexion
if st.sidebar.button(" Déconnexion", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# ═══════════════════════════════════════════════════════════════════
# INTERFACE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════
st.title("Demandes (Poste Soudure)")

# ─── ALERTES PANNES ──────────────────────────────────────────────
st.subheader(" Alertes de Panne en Temps Réel")

try:
    pannes = get_pannes_api()
    df_pannes = pd.DataFrame(pannes) if pannes else pd.DataFrame()

    if not df_pannes.empty and 'statut' in df_pannes.columns:
        df_ouvertes = df_pannes[df_pannes['statut'] == '🔴 Ouvert']
        if not df_ouvertes.empty:
            for _, row in df_ouvertes.iterrows():
                st.error(f"""
                    🔴 **NOUVELLE ALERTE REÇUE**
                    * **Message de l'Opérateur :** {row.get('cause', 'N/A')}
                    * **Envoyé par :** {row.get('operateur_id', 'N/A')}
                    * **Heure :** {row.get('debut_panne', 'N/A')}
                """)
            if st.button("✅ Confirmer la réception / Traiter"):
                try:
                    requests.post(f"{API_BASE}/resoudre_pannes", timeout=10)
                    st.success("L'alerte a été marquée comme traitée.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur: {e}")
        else:
            st.success("✅ Aucune panne signalée pour le moment.")
    else:
        st.success("✅ Aucune panne signalée pour le moment.")
except Exception as e:
    st.info("Système d'alertes prêt (en attente de messages...).")

# ═══════════════════════════════════════════════════════════════════
# SUIVI TEMPS RÉEL - AFFICHAGE EN CARTES (STYLE TASWIRA)
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("🔄 Suivi des fabrications en temps réel")

# CSS pour les cartes
st.markdown("""
<style>
.card-container {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-top: 10px;
}

.demande-card {
    background: #1e1e2e;
    border-radius: 16px;
    padding: 20px;
    min-width: 280px;
    flex: 1;
    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    border-left: 6px solid #f39c12;
    color: white;
    font-family: 'Arial', sans-serif;
}

.demande-card.en-cours {
    border-left: 6px solid #2ecc71;
}

.demande-card.critique {
    border-left: 6px solid #e74c3c;
}

.demande-card .ref {
    font-size: 22px;
    font-weight: bold;
    margin-bottom: 8px;
    color: #f0f0f0;
}

.demande-card .badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: bold;
    margin-bottom: 12px;
}

.badge-attente { background: #f39c12; color: #000; }
.badge-encours { background: #2ecc71; color: #000; }
.badge-urgent  { background: #e74c3c; color: #fff; }
.badge-normal  { background: #3498db; color: #fff; }
.badge-critique{ background: #8e44ad; color: #fff; }

.demande-card .info-row {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px solid #333;
    font-size: 14px;
    color: #ccc;
}

.demande-card .info-row:last-child {
    border-bottom: none;
}

.demande-card .label {
    color: #aaa;
}

.demande-card .value {
    color: #fff;
    font-weight: bold;
}

.shift-badge {
    display: inline-block;
    background: #2c3e50;
    color: #3498db;
    border: 1px solid #3498db;
    border-radius: 8px;
    padding: 2px 10px;
    font-size: 12px;
    margin-left: 6px;
}
</style>
""", unsafe_allow_html=True)

try:
    if not df_api.empty and 'statut' in df_api.columns:
        # Filtrer En attente et En cours
        mask = df_api['statut'].str.contains('En attente|En cours', na=False)
        df_suivi = df_api[mask].copy()

        # Trier : En cours en premier
        df_suivi['sort_key'] = df_suivi['statut'].apply(
            lambda x: 1 if 'En cours' in str(x) else 2
        )
        df_suivi = df_suivi.sort_values('sort_key')

        if not df_suivi.empty:
            # Affichage en cartes
            cols = st.columns(3)
            for i, (_, row) in enumerate(df_suivi.iterrows()):
                statut = str(row.get('statut', 'En attente'))
                urgence = str(row.get('urgence', 'Normal'))
                ref = str(row.get('reference', 'N/A'))
                qte = str(row.get('quantite', 'N/A'))
                shift = str(row.get('shift', 'N/A'))
                operateur = str(row.get('operateur_id', 'Non assigné'))
                date_b = str(row.get('date_besoin', 'N/A'))
                heure = str(row.get('heure_demande', 'N/A'))

                # Choix couleur badge statut
                if 'En cours' in statut:
                    badge_statut = f'<span class="badge badge-encours">🟢 En cours</span>'
                    card_class = "demande-card en-cours"
                else:
                    badge_statut = f'<span class="badge badge-attente">🟡 En attente</span>'
                    card_class = "demande-card"

                # Choix couleur badge urgence
                if urgence == 'Critique':
                    badge_urg = f'<span class="badge badge-critique">🔴 Critique</span>'
                    card_class = "demande-card critique"
                elif urgence == 'Urgent':
                    badge_urg = f'<span class="badge badge-urgent">🟠 Urgent</span>'
                else:
                    badge_urg = f'<span class="badge badge-normal">🔵 Normal</span>'

                card_html = f"""
                <div class="{card_class}">
                    <div class="ref">📦 {ref}</div>
                    {badge_statut} {badge_urg}
                    <div class="info-row">
                        <span class="label">Quantité</span>
                        <span class="value">{qte} pcs</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Shift</span>
                        <span class="value"><span class="shift-badge">Shift {shift}</span></span>
                    </div>
                    <div class="info-row">
                        <span class="label">Opérateur</span>
                        <span class="value">{operateur}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Date besoin</span>
                        <span class="value">{date_b}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Heure demande</span>
                        <span class="value">{heure}</span>
                    </div>
                </div>
                """
                with cols[i % 3]:
                    st.markdown(card_html, unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)
        else:
            st.success("Aucune production en attente.")
    else:
        st.info("Chargement des données depuis l'API...")

except Exception as e:
    st.error(f"Erreur de lecture du suivi: {e}")

# ═══════════════════════════════════════════════════════════════════
# PANIER - NOUVELLE DEMANDE
# ═══════════════════════════════════════════════════════════════════
if "panier" not in st.session_state:
    st.session_state.panier = []

st.markdown("---")
st.subheader("Nouvelle Demande de Production")

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        try:
            df_stock_info = pd.read_sql_query("SELECT reference, quantite FROM Stock", conn)
            refs = df_stock_info['reference'].tolist()
        except:
            refs = []

        if refs:
            ref_choisie = st.selectbox("Référence", refs)
        else:
            ref_choisie = st.text_input("Référence (manuel)")

        qte_voulue = st.number_input("Quantité totale souhaitée", 1, 10000, 50)

    with c2:
        urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")

    if st.button("Ajouter à la liste", use_container_width=True):
        st.session_state.panier.append({
            "Reference": ref_choisie,
            "Quantite": qte_voulue,
            "Urgence": urg,
            "Date_Besoin": str(date_b)
        })
        st.success(f"✅ {ref_choisie} ajouté !")
        st.rerun()

# Affichage panier
if st.session_state.panier:
    st.write("### Liste en cours de préparation")
    st.dataframe(pd.DataFrame(st.session_state.panier), use_container_width=True)

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Annuler tout", use_container_width=True):
            st.session_state.panier = []
            st.rerun()
    with col_b2:
        if st.button("Envoyer au montage", type="primary", use_container_width=True):
            erreurs = []
            succes = 0
            for item in st.session_state.panier:
                for s in ['A', 'B']:
                    try:
                        response = requests.post(
                            f"{API_BASE}/create_demande",
                            json={
                                "reference": item["Reference"],
                                "quantite": item["Quantite"],
                                "date_besoin": item["Date_Besoin"],
                                "shift": s,
                                "urgence": item["Urgence"]
                            },
                            timeout=10
                        )
                        if response.status_code == 200:
                            succes += 1
                        else:
                            erreurs.append(f"{item['Reference']} Shift {s}: {response.text}")
                    except Exception as e:
                        erreurs.append(f"{item['Reference']} Shift {s}: {e}")

            st.session_state.panier = []
            st.cache_data.clear()

            if erreurs:
                for err in erreurs:
                    st.warning(f"⚠️ {err}")
            st.success(f"✅ {succes} demande(s) envoyée(s) avec succès !")
            st.rerun()

# ═══════════════════════════════════════════════════════════════════
# GRAPHIQUE HISTORIQUE
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("📊 Historique de Production (Journalier)")

try:
    if not df_api.empty and 'statut' in df_api.columns and 'fin_production' in df_api.columns:
        df_chart = df_api[df_api['statut'] == 'Terminé'].copy()
        df_chart['jour'] = pd.to_datetime(df_chart['fin_production'], errors='coerce').dt.date
        df_chart = df_chart.groupby('jour').size().reset_index(name='total')
        df_chart = df_chart.dropna().sort_values('jour')

        if not df_chart.empty:
            st.line_chart(df_chart.set_index('jour'))
        else:
            st.info("Aucune donnée terminée pour le moment.")
    else:
        st.info("En attente de données pour l'affichage du graphique.")
except Exception as e:
    st.info("En attente de données pour l'affichage du graphique.")

# ─── Fermeture DB ────────────────────────────────────────────────
conn.close()
import requests
import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from database_v2 import init_db

# Configuration
st.set_page_config(page_title="Logistique - Supervision")

# API CONFIG
API_URL = "https://pfe-api-uju4.onrender.com"

# Paths Dynamiques (pour base locale fallback)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

if not os.path.exists(DB_PATH):
    init_db()

# AUTO REFRESH (5 secondes pour le temps réel)
st_autorefresh(interval=5000, key="log_refresh")

# ═══════════════════════════════════════════════════════════════════
# FONCTIONS API
# ═══════════════════════════════════════════════════════════════════

def get_demandes_api():
    try:
        response = requests.get(f"{API_URL}/api/get_demandes", timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.sidebar.error(f"API Error: {e}")
    return []

def get_pannes_api():
    try:
        response = requests.get(f"{API_URL}/api/get_pannes", timeout=10)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return []

def create_demande_api(data):
    try:
        response = requests.post(f"{API_URL}/api/create_demande", json=data, timeout=10)
        return response.status_code == 200
    except:
        return False

def resoudre_pannes_api():
    try:
        response = requests.post(f"{API_URL}/api/resoudre_pannes", timeout=10)
        return response.status_code == 200
    except:
        return False

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR & KPI (mil API)
# ═══════════════════════════════════════════════════════════════════

st.sidebar.title("📊 Tableau de Bord")

# Récupérer les données fraîches mil API
try:
    resp = requests.get(f"{API_URL}/api/get_demandes", timeout=10)
    demandes = resp.json() if resp.status_code == 200 else []
except:
    demandes = []

if demandes:
    df_demandes = pd.DataFrame(demandes)

    # ── KPIs principaux ──────────────────────────
    total     = len(df_demandes)
    termine   = len(df_demandes[df_demandes['statut'].str.contains('Terminé', na=False)])
    en_cours  = len(df_demandes[df_demandes['statut'].str.contains('En cours', na=False)])
    en_attente= len(df_demandes[df_demandes['statut'].str.contains('En attente|attente', na=False)])

    st.sidebar.metric("Total demandes",  total)
    st.sidebar.metric("✅ Terminées",    termine)
    st.sidebar.metric("🟢 En cours",     en_cours)
    st.sidebar.metric("🟠 En attente",   en_attente)

    # ── Temps moyen ──────────────────────────────
    df_term = df_demandes[df_demandes['statut'].str.contains('Terminé', na=False)].copy()
    if not df_term.empty and 'debut_production' in df_term.columns and 'fin_production' in df_term.columns:
        df_term['duree'] = (
            pd.to_datetime(df_term['fin_production'],  errors='coerce') -
            pd.to_datetime(df_term['debut_production'], errors='coerce')
        )
        moy = df_term['duree'].dt.total_seconds().dropna()
        st.sidebar.metric("⏱ Temps moyen (s)", int(moy.mean()) if len(moy) else 0)
    else:
        st.sidebar.metric("⏱ Temps moyen (s)", 0)

    # ── Taux d'occupation (aujourd'hui) ──────────
    st.sidebar.markdown("---")
    st.sidebar.subheader("📈 Performance (KPI)")
    TEMPS_SHIFT_SEC = 8 * 3600
    today = datetime.now().strftime('%Y-%m-%d')

    if not df_term.empty and 'fin_production' in df_term.columns:
        df_today = df_term[df_term['fin_production'].str.startswith(today, na=False)].copy()
        if not df_today.empty and 'duree' in df_today.columns:
            total_sec = df_today['duree'].dt.total_seconds().dropna().sum()
            taux = min(int((total_sec / TEMPS_SHIFT_SEC) * 100), 100)
            st.sidebar.metric("Taux d'Occupation Jour", f"{taux}%")
            st.sidebar.progress(taux / 100)
            if taux > 85:
                st.sidebar.warning("⚠️ Charge élevée détectée !")
        else:
            st.sidebar.metric("Taux d'Occupation Jour", "0%")
            st.sidebar.progress(0)
    else:
        st.sidebar.metric("Taux d'Occupation Jour", "0%")
        st.sidebar.progress(0)

    # ── Répartition urgences ──────────────────────
    if 'urgence' in df_demandes.columns:
        df_urg = df_demandes['urgence'].value_counts().reset_index()
        df_urg.columns = ['urgence', 'total']
        if not df_urg.empty:
            st.sidebar.bar_chart(df_urg.set_index("urgence"))

else:
    st.sidebar.metric("Total demandes",  0)
    st.sidebar.metric("✅ Terminées",    0)
    st.sidebar.metric("🟢 En cours",     0)
    st.sidebar.metric("🟠 En attente",   0)
    st.sidebar.metric("⏱ Temps moyen (s)", 0)

# ── Historique journalier ─────────────────────────
st.sidebar.markdown("---")
try:
    if demandes:
        df_hist = pd.DataFrame(demandes)
        df_hist = df_hist[~df_hist['statut'].str.contains('Archivé', na=False)]
        if 'fin_production' in df_hist.columns:
            df_hist['jour'] = pd.to_datetime(df_hist['fin_production'], errors='coerce').dt.date
            df_hist_group = df_hist.dropna(subset=['jour']).groupby('jour').size().reset_index(name='total').tail(10)
            if not df_hist_group.empty:
                st.sidebar.subheader("📅 Historique")
                st.sidebar.dataframe(df_hist_group, use_container_width=True)
except Exception as e:
    st.sidebar.error(f"Erreur historique: {e}")

# ═══════════════════════════════════════════════════════════════════
# INTERFACE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════

st.title(" Demandes (Poste Soudure)")

# --- ALERTES PANNES (mil API) ---
st.subheader(" Alertes de Panne en Temps Réel")

pannes = get_pannes_api()

if pannes:
    for panne in pannes:
        st.error(f"""
            **NOUVELLE ALERTE REÇUE**
            * **Message de l'Opérateur :** {panne.get('cause', 'N/A')}
            * **Envoyé par :** {panne.get('operateur_id', 'N/A')}
            * **Heure :** {panne.get('debut_panne', 'N/A')}
        """)
    
    if st.button(" Confirmer la réception / Traiter"):
        if resoudre_pannes_api():
            st.success("L'alerte a été marquée comme traitée.")
            st.rerun()
        else:
            st.error("Erreur lors de la résolution")
else:
    st.success(" Aucune panne signalée pour le moment.")

# --- SUIVI TEMPS RÉEL (mil API) ---
# ═══════════════════════════════════════════════════════════════════
# SUIVI TEMPS RÉEL (ye5ou mil API enligne - PAS locale)
# ═══════════════════════════════════════════════════════════════════

st.subheader(" Suivi des fabrications en temps réel")

# ═══════════════════════════════════════════════════════════════════
# 1. JIB EL DONNÉES MIL API ENLIGNE (machi locale)
# ═══════════════════════════════════════════════════════════════════
try:
    # API CALL - ye5ou les demandes mil base enligne
    response = requests.get(f"{API_URL}/api/get_demandes", timeout=10)
    
    if response.status_code == 200:
        demandes_api = response.json()  # ← Héthi les données mil API enligne
        
        # ═══════════════════════════════════════════════════════════
        # 2. FILTRI LES DEMANDES ILI MAHICH TERMINÉES
        # ═══════════════════════════════════════════════════════════
        if demandes_api:
            df_suivi = pd.DataFrame(demandes_api)
            
            # Filtri: ken el demandes ili "En attente" wala "En cours"
            df_suivi = df_suivi[
                df_suivi['statut'].str.contains('En attente|En cours', na=False, regex=True)
            ]
            
            # ═══════════════════════════════════════════════════════
            # 3. AFFICHAGE B CARTES (kima operateur_app.py)
            # ═══════════════════════════════════════════════════════
            if not df_suivi.empty:
                
                # Résumé en haut
                total_encours = len(df_suivi[df_suivi['statut'].str.contains('En cours', na=False)])
                total_attente = len(df_suivi[df_suivi['statut'].str.contains('attente', na=False)])
                
                cols = st.columns(3)
                cols[0].metric("🟢 En cours", total_encours)
                cols[1].metric("🟠 En attente", total_attente)
                cols[2].metric("📊 Total actif", len(df_suivi))
                
                st.markdown("---")
                
                # Loop 3la koll demande w twarriha b carte
                for index, row in df_suivi.iterrows():
                    id_d = row.get('id', 'N/A')
                    module = row.get('reference', 'N/A')
                    qte = row.get('quantite', 0)
                    statut = row.get('statut', 'N/A')
                    urgence = row.get('urgence', 'Normal')
                    operateur = row.get('operateur_id', 'Non assigné')
                    shift = row.get('shift', 'N/A')
                    date_besoin = row.get('date_besoin', 'N/A')
                    heure_demande = row.get('heure_demande', 'N/A')
                    
                    # Couleur selon urgence
                    if urgence == "Critique":
                        border_color = "#ff4b4b"
                        bg_color = "#3d1f1f"
                    elif urgence == "Urgent":
                        border_color = "#ffa421"
                        bg_color = "#3d2a1f"
                    else:
                        border_color = "#262730"
                        bg_color = "#1e1e1e"
                    
                    # Couleur selon statut
                    if "En cours" in statut:
                        status_color = "#00ff88"
                        status_icon = "🟢"
                    else:
                        status_color = "#ffa421"
                        status_icon = "🟠"
                    
                    # ═══════════════════════════════════════════════════
                    # CARTE (expander)
                    # ═══════════════════════════════════════════════════
                    with st.expander(f"{status_icon} {module} | Qté: {qte} | Shift {shift} | ID: {id_d}"):
                        
                        # Info mta3 el demande
                        st.markdown(f"""
                            <div style='
                                background-color: {bg_color};
                                border-left: 5px solid {border_color};
                                padding: 15px;
                                border-radius: 5px;
                                margin: 5px 0;
                            '>
                                <h4 style='color: {border_color}; margin-top: 0;'>📦 {module}</h4>
                                <table style='width: 100%; color: white;'>
                                    <tr><td><b>ID:</b></td><td>#{id_d}</td></tr>
                                    <tr><td><b>Quantité:</b></td><td>{qte} unités</td></tr>
                                    <tr><td><b>Urgence:</b></td><td><span style='color: {border_color};'>● {urgence}</span></td></tr>
                                    <tr><td><b>Statut:</b></td><td><span style='color: {status_color};'>{status_icon} {statut}</span></td></tr>
                                    <tr><td><b>Shift:</b></td><td>{shift}</td></tr>
                                    <tr><td><b>Opérateur:</b></td><td>{operateur}</td></tr>
                                    <tr><td><b>Date besoin:</b></td><td>{date_besoin}</td></tr>
                                    <tr><td><b>Heure demande:</b></td><td>{heure_demande}</td></tr>
                                </table>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Boutons d'action
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.button("🔄 Rafraîchir", key=f"refresh_suivi_{id_d}", use_container_width=True):
                                st.rerun()
                        
                        with col2:
                            if st.button("🗑️ Archiver", key=f"archive_{id_d}", use_container_width=True):
                                # Archiver via API
                                try:
                                    arch_response = requests.post(
                                        f"{API_URL}/api/archiver_demande",
                                        json={"demande_id": id_d},
                                        timeout=10
                                    )
                                    if arch_response.status_code == 200:
                                        st.success("Demande archivée!")
                                        st.rerun()
                                    else:
                                        st.error("Erreur archivage")
                                except:
                                    st.error("API indisponible")
                
            else:
                st.success("✅ Aucune production en cours ou en attente.")
        else:
            st.info("📭 Aucune donnée dans la base enligne.")
    else:
        st.error(f"❌ Erreur API: {response.status_code}")

except requests.exceptions.ConnectionError:
    st.error("❌ Impossible de se connecter à l'API. Vérifiez que le serveur est en ligne.")
    st.info(f"💡 URL API: {API_URL}")
except Exception as e:
    st.error(f"❌ Erreur: {e}")

# ═══════════════════════════════════════════════════════════════════
# PRÉPARATION DE COMMANDE (PANIER)
# ═══════════════════════════════════════════════════════════════════

if "panier" not in st.session_state:
    st.session_state.panier = []

st.markdown("---")
st.subheader(" Nouvelle Demande de Production")

# APRÈS (API enligne ✅)
def get_stock_api():
    try:
        stock_resp = requests.get(f"{API_URL}/api/get_stock", timeout=10)
        if stock_resp.status_code == 200:
            df_stock_info = pd.DataFrame(stock_resp.json())
        else:
            df_stock_info = pd.DataFrame(columns=["reference", "quantite"])
    except Exception:
        df_stock_info = pd.DataFrame(columns=["reference", "quantite"])
    return df_stock_info
    df_stock_info = pd.DataFrame(columns=["reference", "quantite"])

df_stock_info = get_stock_api()

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        refs = df_stock_info['reference'].tolist() if not df_stock_info.empty else []
        if refs:
            ref_choisie = st.selectbox("Référence", refs)
        else:
            ref_choisie = st.text_input("Référence", "REF-001")
        qte_voulue = st.number_input("Quantité totale souhaitée", 1, 10000, 50)
    with c2:
        urg = st.selectbox("Urgence", ["Normal", "Urgent", "Critique"])
        date_b = st.date_input("Date de besoin")

    if st.button(" Ajouter à la liste", use_container_width=True):
        st.session_state.panier.append({
            "reference": ref_choisie,
            "quantite": qte_voulue,
            "urgence": urg,
            "date_besoin": str(date_b)
        })
        st.success(f"{ref_choisie} ajouté !")
        st.rerun()

# AFFICHAGE PANIER + ENVOI
if st.session_state.panier:
    st.write("Liste en cours de préparation")
    st.dataframe(pd.DataFrame(st.session_state.panier), use_container_width=True)
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Annuler tout", use_container_width=True):
            st.session_state.panier = []
            st.rerun()
    with col_b2:
        if st.button("Envoyer au montage", type="primary", use_container_width=True):

            # VERIFICATION STOCK ENLIGNE
            try:
                stock_response = requests.get(f"{API_URL}/api/get_stock", timeout=10)
                if stock_response.status_code == 200:
                    stock_dict = {item["reference"]: item["quantite"] for item in stock_response.json()}
                else:
                    st.error("❌ Impossible de vérifier le stock (erreur API)")
                    st.stop()
            except Exception as e:
                st.error(f"❌ Erreur connexion stock: {e}")
                st.stop()

            a_produire = []      # références qui nécessitent production
            deja_en_stock = []   # références déjà couvertes par le stock

            for item in st.session_state.panier:
                ref = item["reference"]
                qte_demandee = item["quantite"]
                stock_dispo = stock_dict.get(ref, 0)
                qte_manquante = qte_demandee - stock_dispo

                if stock_dispo >= qte_demandee:
                    # Stock suffisant — pas besoin de produire
                    deja_en_stock.append({
                        "ref": ref,
                        "stock": stock_dispo,
                        "demande": qte_demandee
                    })
                else:
                    # Stock insuffisant — produire uniquement la quantité manquante
                    a_produire.append({
                        "reference": ref,
                        "quantite": qte_manquante,   # ← juste le manque
                        "date_besoin": item["date_besoin"],
                        "urgence": item["urgence"]
                    })

            # Afficher les références déjà en stock
            if deja_en_stock:
                for s in deja_en_stock:
                    st.info(
                        f"✅ **{s['ref']}** — Déjà disponible en stock "
                        f"({s['stock']} unités disponibles, {s['demande']} demandées). "
                        f"Aucune production nécessaire."
                    )

            # Envoyer uniquement les demandes avec quantité manquante
            if a_produire:
                success_count = 0
                for item in a_produire:
                    for s in ['A', 'B']:
                        data = {
                            "reference": item["reference"],
                            "quantite": item["quantite"],   # ← quantité manquante
                            "date_besoin": item["date_besoin"],
                            "shift": s,
                            "urgence": item["urgence"]
                        }
                        if create_demande_api(data):
                            success_count += 1

                if success_count > 0:
                    st.success(f"✅ {len(a_produire)} demande(s) envoyée(s) — quantités manquantes uniquement.")
                else:
                    st.error("❌ Erreur lors de l'envoi des demandes")

            if not a_produire and not deja_en_stock:
                st.warning("⚠️ Panier vide.")

            st.session_state.panier = []
            st.rerun()
# ═══════════════════════════════════════════════════════════════════
# SUPERVISION GRAPHIQUE (mil API)
# ═══════════════════════════════════════════════════════════════════

st.markdown("---")
st.subheader("📊 Historique de Production (Journalier)")

try:
    if demandes:
        df_chart = pd.DataFrame(demandes)
        df_term = df_chart[df_chart['statut'].str.contains('Terminé', na=False)]
        if 'fin_production' in df_term.columns:
            df_term['jour'] = pd.to_datetime(df_term['fin_production'], errors='coerce').dt.date
            df_chart_final = df_term.groupby('jour').size().reset_index(name='total')
            if not df_chart_final.empty:
                st.line_chart(df_chart_final.set_index("jour"))
            else:
                st.info("Aucune donnée terminée pour le moment.")
        else:
            st.info("Aucune donnée terminée pour le moment.")
    else:
        st.info("Aucune donnée terminée pour le moment.")
except Exception as e:
    st.info("En attente de données pour l'affichage du graphique.")
import streamlit as st
import sqlite3
import requests
from datetime import datetime
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh
from database_v2 import init_db

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Logistique - Supervision",
    layout="wide"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")
API_BASE = "https://pfe-api-uju4.onrender.com/api"  # Votre API Render

# Initialisation DB locale (pour le Stock uniquement)
if not os.path.exists(DB_PATH):
    init_db()

# Auto-refresh toutes les 5 secondes pour le temps réel
st_autorefresh(interval=5000, key="log_refresh")

# Connexion locale uniquement pour le Stock (références)
conn_local = sqlite3.connect(DB_PATH)

# ═══════════════════════════════════════════════════════════════════
# FONCTIONS API (Connexion à Render)
# ═══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=5)
def get_demandes_api():
    """Récupère toutes les demandes depuis l'API en ligne"""
    try:
        r = requests.get(f"{API_BASE}/get_demandes", timeout=10)
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        st.error(f"Erreur connexion API Demandes: {e}")
        return []

@st.cache_data(ttl=5)
def get_pannes_api():
    """Récupère les pannes depuis l'API en ligne"""
    try:
        r = requests.get(f"{API_BASE}/get_pannes", timeout=10)
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        st.error(f"Erreur connexion API Pannes: {e}")
        return []

def create_demande_api(reference, quantite, date_besoin, shift, urgence):
    """Crée une demande via l'API"""
    try:
        resp = requests.post(
            f"{API_BASE}/create_demande",
            json={
                "reference": reference,
                "quantite": quantite,
                "date_besoin": date_besoin,
                "shift": shift,
                "urgence": urgence
            },
            timeout=10
        )
        return resp.status_code == 200, resp.text
    except Exception as e:
        return False, str(e)

def resoudre_pannes_api():
    """Marque les pannes comme résolues via l'API"""
    try:
        resp = requests.post(f"{API_BASE}/resoudre_pannes", timeout=10)
        return resp.status_code == 200
    except:
        return False

def archiver_demandes_api():
    """Archive les demandes via l'API"""
    try:
        resp = requests.post(f"{API_BASE}/archiver_demandes", timeout=10)
        return resp.status_code == 200
    except:
        return False

# ═══════════════════════════════════════════════════════════════════
# CHARGEMENT DES DONNÉES (Depuis Render)
# ═══════════════════════════════════════════════════════════════════
demandes_api = get_demandes_api()
pannes_api = get_pannes_api()

df_demandes = pd.DataFrame(demandes_api) if demandes_api else pd.DataFrame()
df_pannes = pd.DataFrame(pannes_api) if pannes_api else pd.DataFrame()

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR & KPI (Calculés sur les données API)
# ═══════════════════════════════════════════════════════════════════
st.sidebar.title("Tableau de Bord")

# KPI Total et Terminées
total = len(df_demandes) if not df_demandes.empty else 0
termine = 0

if not df_demandes.empty and 'statut' in df_demandes.columns:
    termine = df_demandes['statut'].str.contains('Terminé', na=False).sum()

st.sidebar.metric("Total demandes", total)
st.sidebar.metric("Terminées", termine)

# KPI Temps moyen
st.sidebar.markdown("---")
temps_moyen = 0
if not df_demandes.empty and 'statut' in df_demandes.columns:
    df_done = df_demandes[df_demandes['statut'].str.contains('Terminé', na=False)].copy()
    if not df_done.empty:
        try:
            df_done['debut'] = pd.to_datetime(df_done['debut_production'], errors='coerce')
            df_done['fin'] = pd.to_datetime(df_done['fin_production'], errors='coerce')
            df_done['duree'] = (df_done['fin'] - df_done['debut']).dt.total_seconds()
            temps_moyen = int(df_done['duree'].mean())
        except:
            temps_moyen = 0

st.sidebar.metric("Temps moyen (s)", temps_moyen if temps_moyen > 0 else "0")

# KPI Performance / Taux d'occupation
st.sidebar.subheader(" Performance (KPI)")
TEMPS_SHIFT_SEC = 8 * 3600

if not df_demandes.empty and 'statut' in df_demandes.columns:
    # Filtrer les terminés aujourd'hui
    try:
        df_done = df_demandes[df_demandes['statut'].str.contains('Terminé', na=False)].copy()
        df_done['fin_date'] = pd.to_datetime(df_done['fin_production'], errors='coerce').dt.date
        today = datetime.today().date()
        df_today = df_done[df_done['fin_date'] == today]
        
        if not df_today.empty:
            df_today['debut'] = pd.to_datetime(df_today['debut_production'], errors='coerce')
            df_today['fin'] = pd.to_datetime(df_today['fin_production'], errors='coerce')
            total_sec = (df_today['fin'] - df_today['debut']).dt.total_seconds().sum()
            
            taux = min(int((total_sec / TEMPS_SHIFT_SEC) * 100), 100)
            st.sidebar.metric("Taux d'Occupation Jour", f"{taux}%")
            st.sidebar.progress(taux / 100)
            
            if taux > 85:
                st.sidebar.warning("Charge élevée détectée !")
        else:
            st.sidebar.info("Attente de données de production...")
    except:
        st.sidebar.info("Attente de données...")

# KPI Urgence
if not df_demandes.empty and 'urgence' in df_demandes.columns:
    st.sidebar.markdown("---")
    df_urg = df_demandes.groupby('urgence').size().reset_index(name='total')
    st.sidebar.bar_chart(df_urg.set_index('urgence'))

# Historique
st.sidebar.markdown("---")
st.sidebar.subheader("Historique des Demandes")

try:
    if not df_demandes.empty and 'heure_demande' in df_demandes.columns:
        # Filtrer les non archivés
        df_non_arch = df_demandes[~df_demandes['statut'].str.contains('Archivé', na=False)]
        
        if not df_non_arch.empty:
            df_hist = df_non_arch.groupby('heure_demande')['reference'].count().reset_index()
            df_hist.columns = ['heure_demande', 'Nb_Refs']
            df_hist = df_hist.sort_values('heure_demande', ascending=False).head(10)
            
            if st.sidebar.button("Vider l'historique", use_container_width=True):
                if archiver_demandes_api():
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.sidebar.error("Erreur lors de l'archivage")
            
            for _, row in df_hist.iterrows():
                with st.sidebar.expander(f"{row['heure_demande']} ({row['Nb_Refs']} réfs)"):
                    details = df_demandes[df_demandes['heure_demande'] == row['heure_demande']][['reference', 'quantite', 'statut']]
                    st.dataframe(details, use_container_width=True, hide_index=True)
        else:
            st.sidebar.info("Aucun historique actif")
except Exception as e:
    st.sidebar.error(f"Erreur historique: {e}")

# ═══════════════════════════════════════════════════════════════════
# INTERFACE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════
st.title("Demandes - Poste Soudure (Connecté à Render)")

# SECTION 1 : ALERTES PANNES (Temps réel via API)
st.subheader("🔴 Alertes de Panne en Temps Réel")

try:
    if not df_pannes.empty and 'statut' in df_pannes.columns:
        df_ouvertes = df_pannes[df_pannes['statut'].str.contains('Ouvert', na=False)]
        
        if not df_ouvertes.empty:
            for _, row in df_ouvertes.iterrows():
                st.error(f"""
                **NOUVELLE ALERTE REÇUE**
                - **Message :** {row.get('cause', 'N/A')}
                - **Opérateur :** {row.get('operateur_id', 'N/A')}
                - **Heure :** {row.get('debut_panne', 'N/A')}
                """)
            
            if st.button("Confirmer la réception / Traiter", type="primary", use_container_width=True):
                if resoudre_pannes_api():
                    st.success("Alerte marquée comme traitée")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Erreur lors de la mise à jour")
        else:
            st.success("Aucune panne signalée pour le moment.")
    else:
        st.success("Aucune panne signalée.")
        
except Exception as e:
    st.info(f"Système d'alertes prêt (en attente de données...)")

# SECTION 2 : SUIVI TEMPS RÉEL
# ═══════════════════════════════════════════════════════════════════
# SECTION 2 : SUIVI TEMPS RÉEL (Données de la base en ligne)
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("📊 Suivi des fabrications en temps réel (Serveur)")

try:
    # 1. Récupération fraîche des données depuis l'API
    # Note: st_autorefresh rafraîchit toute la page, donc get_demandes_api() est ré-exécuté
    demandes_live = get_demandes_api()
    
    if demandes_live:
        df_suivi = pd.DataFrame(demandes_live)

        # 2. Filtrage : On ne garde que ce qui n'est pas encore archivé
        # On affiche : "En attente", "En cours", et "Terminé" (non archivé)
        if not df_suivi.empty:
            # Nettoyage des colonnes pour éviter les erreurs de tri
            if 'date_besoin' in df_suivi.columns:
                df_suivi['date_besoin'] = pd.to_datetime(df_suivi['date_besoin']).dt.date
            
            # 3. Création de catégories pour un affichage organisé
            en_cours = df_suivi[df_suivi['statut'].str.contains('cours', case=False, na=False)]
            en_attente = df_suivi[df_suivi['statut'].str.contains('attente', case=False, na=False)]
            recents = df_suivi[df_suivi['statut'].str.contains('Terminé', case=False, na=False)].head(5)

            # 4. Affichage des onglets pour plus de clarté
            tab1, tab2, tab3 = st.tabs([
                f"⚡ En cours ({len(en_cours)})", 
                f"⏳ File d'attente ({len(en_attente)})", 
                "✅ Derniers terminés"
            ])

            with tab1:
                if not en_cours.empty:
                    # On affiche en priorité les urgents
                    st.dataframe(
                        en_cours[['reference', 'quantite', 'shift', 'urgence', 'statut', 'debut_production']], 
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("Aucune production active sur les machines.")

            with tab2:
                if not en_attente.empty:
                    # Tri par urgence (Critique > Urgent > Normal)
                    priorite_map = {'Critique': 0, 'Urgent': 1, 'Normal': 2}
                    en_attente['prio_val'] = en_attente['urgence'].map(priorite_map)
                    en_attente = en_attente.sort_values('prio_val')
                    
                    st.dataframe(
                        en_attente[['reference', 'quantite', 'shift', 'urgence', 'date_besoin']], 
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.success("Toutes les demandes ont été traitées !")

            with tab3:
                if not recents.empty:
                    st.dataframe(
                        recents[['reference', 'quantite', 'statut', 'fin_production']], 
                        use_container_width=True, hide_index=True
                    )
        else:
            st.info("La base de données est vide.")
    else:
        st.warning("Impossible de récupérer les données depuis le serveur Render.")

except Exception as e:
    st.error(f"Erreur lors de l'affichage du suivi : {e}")
# SECTION 3 : NOUVELLE DEMANDE (Envoi via API)
st.markdown("---")
st.subheader("Nouvelle Demande de Production")

if "panier" not in st.session_state:
    st.session_state.panier = []

with st.container():
    c1, c2 = st.columns(2)
    with c1:
        # Stock local pour sélection des références
        try:
            df_stock_info = pd.read_sql_query("SELECT reference, quantite FROM Stock", conn_local)
            refs = df_stock_info['reference'].tolist()
            ref_choisie = st.selectbox("Référence", refs)
            
            # Afficher stock disponible
            stock_dispo = df_stock_info[df_stock_info['reference'] == ref_choisie]['quantite'].values[0]
            st.info(f"Stock disponible local : **{stock_dispo} pcs**")
        except:
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
        st.success(f"{ref_choisie} ajouté au panier")
        st.rerun()

# AFFICHAGE PANIER & ENVOI
if st.session_state.panier:
    st.markdown("---")
    st.write("**Liste en cours de préparation**")
    
    df_panier = pd.DataFrame(st.session_state.panier)
    st.dataframe(df_panier, use_container_width=True, hide_index=True)
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button(" Annuler tout", use_container_width=True):
            st.session_state.panier = []
            st.rerun()
            
    with col_b2:
        if st.button("Envoyer au montage (Render)", type="primary", use_container_width=True):
            maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            succes_count = 0
            erreurs = []
            
            with st.spinner("Envoi vers le serveur en cours..."):
                for item in st.session_state.panier:
                    # Vérification stock local (optionnel)
                    res = conn_local.execute("SELECT quantite FROM Stock WHERE reference = ?", 
                    (item['Reference'],)).fetchone()
                    stock_actuel = res[0] if res else 0
                    besoin_reel = max(0, item['Quantite'] - stock_actuel)
                    
                    if besoin_reel > 0:
                        # Envoi API pour chaque shift (A et B) comme dans votre logique
                        for shift in ['A', 'B']:
                            success, msg = create_demande_api(
                                reference=item['Reference'],
                                quantite=besoin_reel,
                                date_besoin=item['Date_Besoin'],
                                shift=shift,
                                urgence=item['Urgence']
                            )
                            if success:
                                succes_count += 1
                            else:
                                erreurs.append(f"{item['Reference']} Shift {shift}: {msg}")
                    else:
                        st.warning(f"Stock suffisant pour {item['Reference']} (pas d'envoi nécessaire)")
            
            # Nettoyage
            st.session_state.panier = []
            st.cache_data.clear()
            
            if erreurs:
                for err in erreurs:
                    st.error(f"❌ {err}")
            
            if succes_count > 0:
                st.success(f"✅ {succes_count} demande(s) envoyée(s) avec succès à Render !")
                st.balloons()
            
            st.rerun()

# SECTION 4 : GRAPHIQUE HISTORIQUE (Données API)
st.markdown("---")
st.subheader("Historique de Production (Journalier)")

try:
    if not df_demandes.empty and 'statut' in df_demandes.columns:
        df_chart = df_demandes[df_demandes['statut'].str.contains('Terminé', na=False)].copy()
        
        if not df_chart.empty and 'fin_production' in df_chart.columns:
            df_chart['jour'] = pd.to_datetime(df_chart['fin_production'], errors='coerce').dt.date
            df_chart = df_chart.groupby('jour').size().reset_index(name='total').dropna()
            
            if not df_chart.empty:
                st.line_chart(df_chart.set_index('jour'), use_container_width=True)
            else:
                st.info("Aucune donnée terminée pour le moment.")
        else:
            st.info("Aucune donnée terminée pour le moment.")
    else:
        st.info("En attente de données pour l'affichage du graphique.")

except Exception as e:
    st.info("En attente de données pour l'affichage du graphique.")

# Fermeture connexion locale (Stock uniquement)
conn_local.close()

# Footer
st.markdown("---")
st.caption(f"🟢 Connecté à l'API : {API_BASE} | Dernière mise à jour : {datetime.now().strftime('%H:%M:%S')}")
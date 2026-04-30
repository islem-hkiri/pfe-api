import requests
import streamlit as st
import sqlite3
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
    layout="wide",
    page_icon=""
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "gestion_production.db")
API_BASE = "https://pfe-api-uju4.onrender.com/api"

if not os.path.exists(DB_PATH):
    init_db()

st_autorefresh(interval=5000, key="log_refresh")

conn = sqlite3.connect(DB_PATH)

# ═══════════════════════════════════════════════════════════════════
# FONCTIONS API
# ═══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=5)
def get_demandes_api():
    try:
        r = requests.get(f"{API_BASE}/get_demandes", timeout=10)
        if r.status_code == 200:
            return r.json()
        return []
    except:
        return []

@st.cache_data(ttl=5)
def get_pannes_api():
    try:
        r = requests.get(f"{API_BASE}/get_pannes", timeout=10)
        if r.status_code == 200:
            return r.json()
        return []
    except:
        return []

# ═══════════════════════════════════════════════════════════════════
# CHARGEMENT DONNÉES
# ═══════════════════════════════════════════════════════════════════
demandes = get_demandes_api()
df_api   = pd.DataFrame(demandes) if demandes else pd.DataFrame()

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════
st.sidebar.success("🟢 Connecté : Logistique")
st.sidebar.title("📊 Tableau de Bord")
st.sidebar.markdown("---")

# ── KPI ───────────────────────────────────────────────────────────
total   = len(df_api) if not df_api.empty else 0
termine = 0

if not df_api.empty and 'statut' in df_api.columns:
    termine = df_api['statut'].str.contains('Terminé', na=False).sum()

col1, col2 = st.sidebar.columns(2)
col1.metric("Total", total)
col2.metric("Terminées", termine)

# ── Temps moyen ───────────────────────────────────────────────────
temps_moyen = 0
if not df_api.empty and 'statut' in df_api.columns:
    df_done = df_api[
        df_api['statut'].str.contains('Terminé', na=False)
    ].copy()
    if not df_done.empty:
        try:
            df_done['debut'] = pd.to_datetime(
                df_done['debut_production'], errors='coerce'
            )
            df_done['fin'] = pd.to_datetime(
                df_done['fin_production'], errors='coerce'
            )
            df_done['duree'] = (
                df_done['fin'] - df_done['debut']
            ).dt.total_seconds()
            temps_moyen = int(df_done['duree'].mean())
        except:
            temps_moyen = 0

st.sidebar.metric("⏱️ Temps moyen (s)", temps_moyen)

st.sidebar.markdown("---")
st.sidebar.subheader("⚡ Performance (KPI)")

# ── Taux occupation ───────────────────────────────────────────────
TEMPS_SHIFT_SEC = 8 * 3600

if not df_api.empty and 'statut' in df_api.columns:
    mask_today = (
        df_api['statut'].str.contains('Terminé', na=False) &
        (
            pd.to_datetime(
                df_api['fin_production'], errors='coerce'
            ).dt.date == datetime.today().date()
        )
    )
    df_today = df_api[mask_today].copy()

    if not df_today.empty:
        try:
            df_today['debut'] = pd.to_datetime(
                df_today['debut_production'], errors='coerce'
            )
            df_today['fin'] = pd.to_datetime(
                df_today['fin_production'], errors='coerce'
            )
            total_sec = (
                df_today['fin'] - df_today['debut']
            ).dt.total_seconds().sum()

            taux = min(int((total_sec / TEMPS_SHIFT_SEC) * 100), 100)
            st.sidebar.metric("Taux d'Occupation", f"{taux}%")
            st.sidebar.progress(taux / 100)

            if taux > 85:
                st.sidebar.warning("Charge élevée détectée !")
            elif taux > 50:
                st.sidebar.info(f"Occupation normale : {taux}%")
            else:
                st.sidebar.info(f"Faible occupation : {taux}%")
        except:
            st.sidebar.info("Attente de données...")
    else:
        st.sidebar.info("Attente de données de production...")
else:
    st.sidebar.info("Attente de données de production...")

# ── Bar chart urgence ─────────────────────────────────────────────
if not df_api.empty and 'urgence' in df_api.columns:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Répartition Urgences")
    df_urg = (
        df_api.groupby('urgence')
        .size()
        .reset_index(name='total')
    )
    st.sidebar.bar_chart(df_urg.set_index('urgence'))

# ── Historique ────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("Historique des Demandes")

try:
    if not df_api.empty and 'heure_demande' in df_api.columns:
        df_non_arch = df_api[
            ~df_api['statut'].str.contains('Archivé', na=False)
        ]
        df_hist = (
            df_non_arch
            .groupby('heure_demande')['reference']
            .count()
            .reset_index()
        )
        df_hist.columns = ['heure_demande', 'Nb_Refs']
        df_hist = df_hist.sort_values(
            'heure_demande', ascending=False
        ).head(10)

        if not df_hist.empty:
            if st.sidebar.button(
                "Vider l'historique",
                use_container_width=True
            ):
                try:
                    requests.post(
                        f"{API_BASE}/archiver_demandes",
                        timeout=10
                    )
                    st.cache_data.clear()
                    st.rerun()
                except:
                    pass

            for _, row in df_hist.iterrows():
                nb = row['Nb_Refs']
                heure = row['heure_demande']
                label = f" {heure}  ({nb} réf.)"

                with st.sidebar.expander(label):
                    details = df_api[
                        df_api['heure_demande'] == heure
                    ][['reference', 'quantite', 'statut']]

                    st.dataframe(
                        details.rename(columns={
                            'reference': 'Réf',
                            'quantite':  'Qté',
                            'statut':    'Statut'
                        }),
                        use_container_width=True,
                        hide_index=True
                    )
        else:
            st.sidebar.info("Aucun historique disponible.")
except Exception as e:
    st.sidebar.error(f"Erreur historique: {e}")

# ═══════════════════════════════════════════════════════════════════
# INTERFACE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════
st.title("Supervision - Poste Soudure")

# ═══════════════════════════════════════════════════════════════════
# SECTION 1 : ALERTES PANNES
# ═══════════════════════════════════════════════════════════════════
st.subheader("Alertes de Panne en Temps Réel")

try:
    pannes    = get_pannes_api()
    df_pannes = pd.DataFrame(pannes) if pannes else pd.DataFrame()

    if not df_pannes.empty and 'statut' in df_pannes.columns:
        df_ouvertes = df_pannes[
            df_pannes['statut'].str.contains('Ouvert', na=False)
        ]

        if not df_ouvertes.empty:
            for _, row in df_ouvertes.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([1, 3, 2])

                    with c1:
                        st.error("🔴 ALERTE")

                    with c2:
                        st.write(
                            f"**Message :** {row.get('cause', 'N/A')}"
                        )
                        st.write(
                            f"**Opérateur :** {row.get('operateur_id', 'N/A')}"
                        )

                    with c3:
                        st.write(
                            f"**Heure :** {row.get('debut_panne', 'N/A')}"
                        )

            st.markdown("")
            if st.button(
                "✅ Confirmer réception et Traiter",
                type="primary",
                use_container_width=True
            ):
                try:
                    requests.post(
                        f"{API_BASE}/resoudre_pannes",
                        timeout=10
                    )
                    st.success("✅ Alerte marquée comme traitée.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur: {e}")
        else:
            st.success("✅ Aucune panne signalée pour le moment.")
    else:
        st.success("✅ Aucune panne signalée pour le moment.")

except Exception:
    st.info("Système d'alertes prêt (en attente de messages...).")

# ═══════════════════════════════════════════════════════════════════
# SECTION 2 : SUIVI EN TEMPS RÉEL - CARTES PYTHON
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader(" Suivi des Fabrications en Temps Réel")

try:
    if not df_api.empty and 'statut' in df_api.columns:

        mask     = df_api['statut'].str.contains(
            'En attente|En cours', na=False
        )
        df_suivi = df_api[mask].copy()

        # Trier En cours en premier
        df_suivi['sort_key'] = df_suivi['statut'].apply(
            lambda x: 0 if 'En cours' in str(x) else 1
        )
        df_suivi = df_suivi.sort_values('sort_key').reset_index(drop=True)

        if not df_suivi.empty:
            # Affichage 3 colonnes
            cols = st.columns(3)

            for i, (_, row) in enumerate(df_suivi.iterrows()):
                statut   = str(row.get('statut',       'En attente'))
                urgence  = str(row.get('urgence',      'Normal'))
                ref      = str(row.get('reference',    'N/A'))
                qte      = row.get('quantite',          0)
                compteur = row.get('compteur',          0)
                shift    = str(row.get('shift',        'N/A'))
                operateur= str(row.get('operateur_id', 'Non assigné'))
                date_b   = str(row.get('date_besoin',  'N/A'))
                heure    = str(row.get('heure_demande','N/A'))

                # Progression
                try:
                    qte_int      = int(qte)
                    compteur_int = int(compteur)
                    progress_val = (
                        compteur_int / qte_int
                        if qte_int > 0 else 0
                    )
                    progress_val = min(progress_val, 1.0)
                    progress_pct = int(progress_val * 100)
                except:
                    progress_val = 0.0
                    progress_pct = 0

                # Icône statut
                if 'En cours' in statut:
                    icon_statut  = "🟢 En cours"
                    icon_urgence = "🔵 Normal"
                else:
                    icon_statut  = "🟡 En attente"

                # Icône urgence
                if urgence == 'Critique':
                    icon_urgence = "🔴 Critique"
                elif urgence == 'Urgent':
                    icon_urgence = "🟠 Urgent"
                else:
                    icon_urgence = "🔵 Normal"

                with cols[i % 3]:
                    with st.container(border=True):

                        # ── Ligne 1 : Ref + Statut ─────────────
                        h1, h2 = st.columns([2, 1])
                        with h1:
                            st.markdown(f"###  {ref}")
                        with h2:
                            st.markdown(f"**{icon_statut}**")

                        st.markdown(
                            f"**Urgence :** {icon_urgence}"
                        )
                        st.markdown("---")

                        # ── Infos ──────────────────────────────
                        i1, i2 = st.columns(2)
                        with i1:
                            st.metric("Quantité", f"{qte} pcs")
                            st.metric("Shift", f"Shift {shift}")
                        with i2:
                            st.metric("Produit", f"{compteur} pcs")
                            st.metric("Opérateur", operateur)

                        # ── Progression ────────────────────────
                        if 'En cours' in statut:
                            st.markdown(
                                f"**Progression : {compteur_int}"
                                f"/{qte_int} pcs ({progress_pct}%)**"
                            )
                            st.progress(progress_val)

                        # ── Date & Heure ───────────────────────
                        st.caption(
                            f"📅 Besoin : {date_b}  |  "
                            f"🕐 Demande : {heure}"
                        )
        else:
            st.success("✅ Aucune production en attente.")
    else:
        st.info(" Chargement des données depuis l'API...")

except Exception as e:
    st.error(f"Erreur suivi: {e}")

# ═══════════════════════════════════════════════════════════════════
# SECTION 3 : NOUVELLE DEMANDE - PANIER
# ═══════════════════════════════════════════════════════════════════
if "panier" not in st.session_state:
    st.session_state.panier = []

st.markdown("---")
st.subheader(" Nouvelle Demande de Production")

with st.container(border=True):
    c1, c2 = st.columns(2)

    with c1:
        try:
            df_stock = pd.read_sql_query(
                "SELECT reference, quantite FROM Stock", conn
            )
            refs = df_stock['reference'].tolist()
        except:
            refs = []

        if refs:
            ref_choisie = st.selectbox(" Référence", refs)
            # Afficher stock disponible
            try:
                stock_dispo = df_stock[
                    df_stock['reference'] == ref_choisie
                ]['quantite'].values[0]
                st.info(f" Stock disponible : **{stock_dispo} pcs**")
            except:
                pass
        else:
            ref_choisie = st.text_input(" Référence (manuel)")

        qte_voulue = st.number_input(
            "Quantité souhaitée", 1, 10000, 50
        )

    with c2:
        urg    = st.selectbox(
            "⚡ Urgence", ["Normal", "Urgent", "Critique"]
        )
        date_b = st.date_input(" Date de besoin")

    if st.button(" Ajouter à la liste", use_container_width=True):
        st.session_state.panier.append({
            "Reference":  ref_choisie,
            "Quantite":   qte_voulue,
            "Urgence":    urg,
            "Date_Besoin": str(date_b)
        })
        st.success(f"✅ {ref_choisie} ajouté au panier !")
        st.rerun()

# ── Affichage panier ──────────────────────────────────────────────
if st.session_state.panier:
    st.markdown("---")
    st.subheader(" Panier en cours")

    df_panier = pd.DataFrame(st.session_state.panier)
    st.dataframe(df_panier, use_container_width=True, hide_index=True)

    # Résumé
    nb_items = len(st.session_state.panier)
    total_qte = sum(i['Quantite'] for i in st.session_state.panier)
    r1, r2 = st.columns(2)
    r1.metric("Nombre de références", nb_items)
    r2.metric("Quantité totale", f"{total_qte} pcs")

    st.markdown("")
    col_b1, col_b2 = st.columns(2)

    with col_b1:
        if st.button(
            " Annuler tout",
            use_container_width=True
        ):
            st.session_state.panier = []
            st.rerun()

    with col_b2:
        if st.button(
            " Envoyer au montage",
            type="primary",
            use_container_width=True
        ):
            erreurs = []
            succes  = 0

            with st.spinner("Envoi en cours..."):
                for item in st.session_state.panier:
                    for s in ['A', 'B']:
                        try:
                            resp = requests.post(
                                f"{API_BASE}/create_demande",
                                json={
                                    "reference":  item["Reference"],
                                    "quantite":   item["Quantite"],
                                    "date_besoin":item["Date_Besoin"],
                                    "shift":      s,
                                    "urgence":    item["Urgence"]
                                },
                                timeout=10
                            )
                            if resp.status_code == 200:
                                succes += 1
                            else:
                                erreurs.append(
                                    f"{item['Reference']} "
                                    f"Shift {s}: {resp.text}"
                                )
                        except Exception as e:
                            erreurs.append(
                                f"{item['Reference']} Shift {s}: {e}"
                            )

            st.session_state.panier = []
            st.cache_data.clear()

            if erreurs:
                for err in erreurs:
                    st.warning(f"⚠️ {err}")

            st.success(
                f"✅ {succes} demande(s) envoyée(s) avec succès !"
            )
            st.rerun()

# ═══════════════════════════════════════════════════════════════════
# SECTION 4 : GRAPHIQUE HISTORIQUE
# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("📊 Historique de Production (Journalier)")

try:
    if (
        not df_api.empty
        and 'statut' in df_api.columns
        and 'fin_production' in df_api.columns
    ):
        df_chart = df_api[
            df_api['statut'].str.contains('Terminé', na=False)
        ].copy()

        df_chart['jour'] = pd.to_datetime(
            df_chart['fin_production'], errors='coerce'
        ).dt.date

        df_chart = (
            df_chart.groupby('jour')
            .size()
            .reset_index(name='Terminées')
            .dropna()
            .sort_values('jour')
        )

        if not df_chart.empty:
            tab1, tab2 = st.tabs(["📈 Courbe", "📋 Tableau"])

            with tab1:
                st.line_chart(
                    df_chart.set_index('jour'),
                    use_container_width=True
                )
            with tab2:
                st.dataframe(
                    df_chart,
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.info("Aucune donnée terminée pour le moment.")
    else:
        st.info(" En attente de données pour le graphique.")

except Exception:
    st.info(" En attente de données pour le graphique.")

# ─── Fermeture DB ────────────────────────────────────────────────
conn.close()
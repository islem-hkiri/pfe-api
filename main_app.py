import streamlit as st
import threading
import os
import sqlite3
from datetime import datetime
import pandas as pd
import subprocess
import time

# Configuration de base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

# ================= SERVEUR FLASK POUR ESP32 =================
# État machine partagé
machine_state = {
    "current_shift": "B",
    "current_demande_id": None,
    "current_counter": 0,
    "required_qty": 0,
    "production_active": False
}

def start_flask_server():
    """Démarre le serveur Flask pour communiquer avec ESP32"""
    from flask import Flask, request, jsonify
    import sqlite3
    from datetime import datetime
    
    app = Flask(__name__)
    
    @app.route('/api/etat', methods=['GET'])
    def get_etat():
        """ESP32 appelle cette route pour connaître l'état actuel"""
        shift = request.args.get('shift', 'B')
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Chercher la demande en cours pour ce shift
        cursor.execute("""
            SELECT id, quantite, statut 
            FROM Demandes 
            WHERE shift = ? AND statut IN ('🟢 En cours', '🟠 En attente')
            ORDER BY CASE WHEN statut = '🟢 En cours' THEN 1 ELSE 2 END, id ASC
            LIMIT 1
        """, (shift,))
        
        task = cursor.fetchone()
        conn.close()
        
        if task:
            demande_id, qty, statut = task
            if statut == '🟢 En cours':
                return jsonify({
                    "statut": "En cours",
                    "quantite_requise": qty,
                    "demande_id": demande_id
                })
            else:
                return jsonify({
                    "statut": "En attente",
                    "quantite_requise": qty,
                    "demande_id": demande_id
                })
        else:
            return jsonify({
                "statut": "Libre",
                "quantite_requise": 0,
                "demande_id": 0
            })
    
    @app.route('/api/lancer_automatique', methods=['POST'])
    def lancer_automatique():
        """ESP32 demande à lancer la prochaine production"""
        data = request.get_json()
        shift = data.get('shift', 'B')
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Chercher première demande en attente
        cursor.execute("""
            SELECT id, quantite, reference
            FROM Demandes 
            WHERE shift = ? AND statut = '🟠 En attente'
            ORDER BY date_besoin ASC, id ASC
            LIMIT 1
        """, (shift,))
        
        task = cursor.fetchone()
        
        if task:
            demande_id, qty, reference = task
            
            # Mettre à jour le statut
            cursor.execute("""
                UPDATE Demandes 
                SET statut = '🟢 En cours', 
                    debut_production = datetime('now'),
                    operateur_id = 'ESP32_AUTO'
                WHERE id = ?
            """, (demande_id,))
            
            conn.commit()
            conn.close()
            
            # Mettre à jour état machine
            machine_state["current_shift"] = shift
            machine_state["current_demande_id"] = demande_id
            machine_state["current_counter"] = 0
            machine_state["required_qty"] = qty
            machine_state["production_active"] = True
            
            return jsonify({
                "success": True,
                "demande_id": demande_id,
                "quantite_requise": qty,
                "reference": reference
            })
        
        conn.close()
        return jsonify({"success": False, "message": "Aucune demande en attente"})
    
    @app.route('/api/increment', methods=['POST'])
    def increment():
        """ESP32 incrémente le compteur de production"""
        data = request.get_json()
        shift = data.get('shift', 'B')
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Trouver la demande en cours
        cursor.execute("""
            SELECT id, quantite, reference
            FROM Demandes 
            WHERE shift = ? AND statut = '🟢 En cours'
            LIMIT 1
        """, (shift,))
        
        task = cursor.fetchone()
        
        if not task:
            conn.close()
            return jsonify({"error": "Aucune production en cours"}), 400
        
        demande_id, qty_requise, reference = task
        
        # Synchroniser le compteur avec la tâche en cours
        if machine_state["current_demande_id"] != demande_id:
            machine_state["current_demande_id"] = demande_id
            machine_state["current_counter"] = 0
            machine_state["required_qty"] = qty_requise
        
        machine_state["current_counter"] += 1
        compteur = machine_state["current_counter"]
        
        if compteur >= qty_requise:
            # Terminer la production
            cursor.execute("""
                UPDATE Demandes 
                SET statut = '✅ Terminé',
                    fin_production = datetime('now')
                WHERE id = ?
            """, (demande_id,))
            
            # Mettre à jour le stock
            cursor.execute("""
                UPDATE Stock 
                SET quantite = quantite + ?
                WHERE reference = ?
            """, (qty_requise, reference))
            
            conn.commit()
            conn.close()
            
            # Réinitialiser état machine
            machine_state["current_demande_id"] = None
            machine_state["current_counter"] = 0
            machine_state["production_active"] = False
            
            return jsonify({
                "success": True,
                "termine": True,
                "compteur": compteur
            })
        
        conn.close()
        return jsonify({
            "success": True,
            "termine": False,
            "compteur": compteur
        })
    
    @app.route('/api/decrement', methods=['POST'])
    def decrement():
        """ESP32 décrémente le compteur (bouton annulation)"""
        data = request.get_json()
        shift = data.get('shift', 'B')
        
        if machine_state["current_counter"] > 0:
            machine_state["current_counter"] -= 1
            return jsonify({"success": True, "compteur": machine_state["current_counter"]})
        
        return jsonify({"success": True, "compteur": 0})
    
    @app.route('/api/etat_machine', methods=['GET'])
    def get_machine_state():
        """Route pour debug - voir l'état de la machine"""
        return jsonify({
            "current_shift": machine_state["current_shift"],
            "current_demande_id": machine_state["current_demande_id"],
            "current_counter": machine_state["current_counter"],
            "required_qty": machine_state["required_qty"],
            "production_active": machine_state["production_active"]
        })
    
    @app.route('/api/health', methods=['GET'])
    def health():
        """Route de health check"""
        return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})
    
    # Démarrer Flask
    print("🚀 Demarrage du serveur Flask sur http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# Démarrer Flask dans un thread séparé (une seule fois)
if 'flask_started' not in st.session_state:
    flask_thread = threading.Thread(target=start_flask_server, daemon=True)
    flask_thread.start()
    st.session_state.flask_started = True
    print("✅ Serveur Flask demarre sur port 5000")
    time.sleep(2)  # Attendre que Flask démarre

# ================= SUITE DE L'APPLICATION STREAMLIT =================

if "role" not in st.session_state:
    st.session_state.role = None

def login():
    st.title("🔧 Connexion - Gestion Production")
    user = st.text_input("👤 Utilisateur (Logistique ou Operateur)")
    password = st.text_input("🔒 Mot de passe", type="password")
    
    if st.button("Se connecter"):
        if user.lower() == "logistique" and password == "log123":
            st.session_state.role = "Logistique"
            st.rerun()
        elif user.lower() == "operateur" and password == "op123":
            st.session_state.role = "Operateur"
            st.rerun()
        else:
            st.error("❌ Identifiants incorrects")

if st.session_state.role is None:
    login()
else:
    if st.sidebar.button("🚪 Deconnexion"):
        st.session_state.role = None
        st.rerun()

    # Afficher l'état de la machine ESP32 dans la sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("🤖 Etat Machine ESP32")
    
    # Tester la connexion avec l'API
    import requests
    try:
        response = requests.get("http://localhost:5000/api/health", timeout=2)
        if response.status_code == 200:
            st.sidebar.success("✅ API connectee")
        else:
            st.sidebar.error("❌ API erreur")
    except:
        st.sidebar.error("❌ API non accessible")
    
    # Couleurs selon l'état
    if machine_state["production_active"]:
        st.sidebar.markdown("🔴 **Etat:** En cours")
        st.sidebar.markdown(f"**Tache ID:** {machine_state['current_demande_id']}")
        st.sidebar.markdown(f"**Compteur:** {machine_state['current_counter']} / {machine_state['required_qty']}")
        if machine_state["required_qty"] > 0:
            progress = machine_state["current_counter"] / machine_state["required_qty"]
            st.sidebar.progress(progress)
    else:
        conn_check = sqlite3.connect(DB_PATH)
        pending = conn_check.execute("SELECT COUNT(*) FROM Demandes WHERE statut = '🟠 En attente'").fetchone()[0]
        conn_check.close()
        
        if pending > 0:
            st.sidebar.markdown("🟠 **Etat:** En attente")
            st.sidebar.markdown(f"**Taches en file:** {pending}")
        else:
            st.sidebar.markdown("🟢 **Etat:** Disponible")
    
    if st.session_state.role == "Logistique":
        st.sidebar.success("👔 Connecte : Logistique")
        # Utiliser utf-8 encoding
        with open("logistique_app.py", "r", encoding="utf-8") as f:
            exec(f.read())
        
    elif st.session_state.role == "Operateur":
        st.sidebar.info("🔧 Connecte : Operateur")
        # Utiliser utf-8 encoding
        with open("operateur_app.py", "r", encoding="utf-8") as f:
            exec(f.read())
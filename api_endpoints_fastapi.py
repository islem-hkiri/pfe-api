from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

class ShiftRequest(BaseModel):
    shift: str

@app.get("/")
def root():
    return {"message": "API PFE OK"}

# 🔹 ETAT MACHINE (LED) - CORRIGÉ
@app.get("/api/etat")
def get_etat(shift: str = "A"):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. Vérifier production en cours (avec ou sans emoji)
        cursor.execute("""
            SELECT id, statut, quantite
            FROM Demandes
            WHERE shift = ? AND (statut = '🟢En cours' OR statut = 'En cours')
            LIMIT 1
        """, (shift,))
        en_cours = cursor.fetchone()

        # 2. Vérifier demande en attente (avec ou sans emoji)
        cursor.execute("""
            SELECT id FROM Demandes
            WHERE shift = ? AND (statut = '🟠En attente' OR statut = 'En attente')
            LIMIT 1
        """, (shift,))
        attente = cursor.fetchone()

        conn.close()

        # 🔥 LOGIC LED (priorité: En cours > En attente > Libre)
        if en_cours:
            return {
                "statut": "🟢En cours",
                "machine_disponible": False
            }

        if attente:
            return {
                "statut": "🟠En attente",
                "machine_disponible": False  # ⚠️ Changement important: False car il y a du travail
            }

        return {
            "statut": "Libre",
            "machine_disponible": True
        }

    except Exception as e:
        return {"error": str(e)}

# 🔹 INCREMENT + AUTO START + AUTO TERMINER (CORRIGÉ)
@app.post("/api/increment")
def increment(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Vérifier production en cours
    cursor.execute("""
        SELECT id, quantite, reference 
        FROM Demandes 
        WHERE shift = ? AND (statut = '🟢En cours' OR statut = 'En cours')
        LIMIT 1
    """, (req.shift,))
    
    demande = cursor.fetchone()

    # 🔥 2. Si pas de production en cours, lancer automatiquement la première en attente
    if not demande:
        cursor.execute("""
            SELECT id, quantite, reference 
            FROM Demandes 
            WHERE shift = ? AND (statut = '🟠En attente' OR statut = 'En attente')
            ORDER BY id ASC LIMIT 1
        """, (req.shift,))
        
        demande = cursor.fetchone()

        if not demande:
            conn.close()
            return {"success": False, "message": "Aucune demande en attente"}

        demande_id, qte_max, ref = demande

        # Démarrer la production
        cursor.execute("""
            UPDATE Demandes 
            SET statut = '🟢En cours', debut_production = datetime('now') 
            WHERE id = ?
        """, (demande_id,))

        # Initialiser le compteur à 0 pour cette nouvelle production
        cursor.execute("""
            INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
            VALUES (?, 0, ?, datetime('now'))
            ON CONFLICT(shift) DO UPDATE 
            SET compteur_actuel = 0, demande_id = ?, last_update = datetime('now')
        """, (req.shift, demande_id, demande_id))
        
        compteur = 1  # Premier incrément

    else:
        demande_id, qte_max, ref = demande

        # Récupérer le compteur actuel
        cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
        row = cursor.fetchone()
        compteur = row[0] + 1 if row else 1

    # 🔹 Mettre à jour le compteur
    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(shift) DO UPDATE 
        SET compteur_actuel = ?, demande_id = ?, last_update = datetime('now')
    """, (req.shift, compteur, demande_id, compteur, demande_id))

    termine = (compteur >= qte_max)

    # 🔥 AUTO TERMINER
    if termine:
        cursor.execute("""
            UPDATE Demandes 
            SET statut = '✅ Terminé', fin_production = datetime('now') 
            WHERE id = ?
        """, (demande_id,))

        cursor.execute("""
            UPDATE Stock 
            SET quantite = quantite + ? 
            WHERE reference = ?
        """, (qte_max, ref))

        # Remettre le compteur à 0 pour la prochaine production
        cursor.execute("""
            UPDATE EtatMachine 
            SET compteur_actuel = 0, demande_id = NULL
            WHERE shift = ?
        """, (req.shift,))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "compteur": compteur,
        "max": qte_max,
        "termine": termine
    }

# 🔹 DECREMENT (BOUTON ANNULATION) - CORRIGÉ
@app.post("/api/decrement")
def decrement(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Vérifier si une production est en cours
    cursor.execute("""
        SELECT id FROM Demandes 
        WHERE shift = ? AND (statut = '🟢En cours' OR statut = 'En cours')
        LIMIT 1
    """, (req.shift,))
    
    en_cours = cursor.fetchone()
    
    if not en_cours:
        conn.close()
        return {"success": False, "message": "Aucune production en cours"}

    cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
    row = cursor.fetchone()

    if row and row[0] > 0:
        nouveau = row[0] - 1

        cursor.execute("""
            UPDATE EtatMachine 
            SET compteur_actuel = ?, last_update = datetime('now') 
            WHERE shift = ?
        """, (nouveau, req.shift))

        conn.commit()
        conn.close()

        return {"success": True, "compteur": nouveau}
@app.get("/api/debug")
def debug():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, shift, statut, quantite FROM Demandes LIMIT 10")
    data = cursor.fetchall()
    conn.close()
    return {"demandes": [{"id": d[0], "shift": d[1], "statut": d[2], "qte": d[3]} for d in data]}

@app.get("/api/add_direct")
def add_direct():
    import sqlite3
    from datetime import datetime
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Demandes (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
        VALUES ('TEST_001', 5, date('now'), 'A', 'En attente', 'Normal', datetime('now'))
    """)
    conn.commit()
    conn.close()
    return {"message": "Demande ajoutée avec succès! Maintenant teste /api/etat?shift=A"}
    # Ajouter après @app.get("/api/add_direct") et avant la dernière parenthèse

# 🔹 SYNC DATABASE ENDPOINT
@app.post("/api/sync-db")
def sync_database():
    """Force la synchronisation de la base de données"""
    try:
        # Importer database_v2 et lancer sync
        import database_v2
        result = database_v2.manual_sync()
        return result
    except Exception as e:
        return {"success": False, "message": f"Erreur sync: {str(e)}"}

@app.get("/api/sync-status")
def sync_status():
    """Vérifie le statut de la base de données"""
    try:
        import database_v2
        return database_v2.get_sync_status()
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/check-tables")
def check_tables():
    """Vérifie si toutes les tables existent"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    required = ['EtatMachine', 'Pannes', 'Produits', 'Stock', 'Demandes']
    missing = [t for t in required if t not in tables]
    
    return {
        "tables": tables,
        "missing": missing,
        "all_ok": len(missing) == 0
    }

    conn.close()
    return {"success": False, "message": "Compteur déjà à zéro"}
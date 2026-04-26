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

@app.get("/api/etat")
def get_etat(shift: str = "A"):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, statut, quantite
            FROM Demandes
            WHERE shift = ? AND (statut = '🟢En cours' OR statut = 'En cours')
            LIMIT 1
        """, (shift,))
        en_cours = cursor.fetchone()

        cursor.execute("""
            SELECT id FROM Demandes
            WHERE shift = ? AND (statut = '🟠En attente' OR statut = 'En attente')
            LIMIT 1
        """, (shift,))
        attente = cursor.fetchone()

        conn.close()

        if en_cours:
            return {
                "statut": "🟢En cours",
                "machine_disponible": False
            }

        if attente:
            return {
                "statut": "🟠En attente",
                "machine_disponible": False
            }

        return {
            "statut": "Libre",
            "machine_disponible": True
        }

    except Exception as e:
        return {"error": str(e)}

@app.post("/api/increment")
def increment(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, quantite, reference 
        FROM Demandes 
        WHERE shift = ? AND (statut = '🟢En cours' OR statut = 'En cours')
        LIMIT 1
    """, (req.shift,))
    
    demande = cursor.fetchone()

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

        demande_id, Qté, ref = demande

        cursor.execute("""
            UPDATE Demandes 
            SET statut = '🟢En cours', debut_production = datetime('now') 
            WHERE id = ?
        """, (demande_id,))

        cursor.execute("""
            INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
            VALUES (?, 0, ?, datetime('now'))
            ON CONFLICT(shift) DO UPDATE 
            SET compteur_actuel = 0, demande_id = ?, last_update = datetime('now')
        """, (req.shift, demande_id, demande_id))
        
        compteur = 1

    else:
        demande_id, Qté, ref = demande

        cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
        row = cursor.fetchone()
        compteur = row[0] if row else 0
        
        # ✅ VÉRIFICATION ICI
        if compteur >= Qté:
            conn.close()
            return {"success": False, "message": f"Quantité maximale {Qté} atteinte"}

        compteur += 1

    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(shift) DO UPDATE 
        SET compteur_actuel = ?, demande_id = ?, last_update = datetime('now')
    """, (req.shift, compteur, demande_id, compteur, demande_id))

    termine = (compteur >= Qté)

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
        """, (Qté, ref))

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
        "Qté": Qté,
        "termine": termine
    }

@app.post("/api/decrement")
def decrement(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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
    
    conn.close()
    return {"success": False, "message": "Compteur déjà à zéro"}

@app.get("/api/debug")
def debug():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, shift, statut, quantite FROM Demandes LIMIT 10")
    data = cursor.fetchall()
    conn.close()
    return {"demandes": [{"id": d[0], "shift": d[1], "statut": d[2], "Qté": d[3]} for d in data]}

@app.get("/api/add_direct")
def add_direct():
    import sqlite3
    from datetime import datetime
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO Demandes (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
        VALUES ('TEST_001', 10, date('now'), 'A', 'En attente', 'Normal', datetime('now'))
    """)
    
    conn.commit()
    conn.close()
    return {"message": "Demande TEST_001 ajoutée avec succès!"}
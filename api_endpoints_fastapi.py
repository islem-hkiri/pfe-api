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

# 🔹 ETAT MACHINE (LED)
@app.get("/api/etat")
def get_etat(shift: str = "A"):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. نشوف production en cours
        cursor.execute("""
            SELECT id, statut, quantite
            FROM Demandes
            WHERE shift = ? AND statut = 'En cours'
            LIMIT 1
        """, (shift,))
        en_cours = cursor.fetchone()

        # 2. نشوف attente
        cursor.execute("""
            SELECT id FROM Demandes
            WHERE shift = ? AND statut = 'En attente'
            LIMIT 1
        """, (shift,))
        attente = cursor.fetchone()

        conn.close()

        # 🔥 LOGIC LED
        if en_cours:
            return {
                "statut": "En cours",
                "machine_disponible": False
            }

        if attente:
            return {
                "statut": "En attente",
                "machine_disponible": True
            }

        return {
            "statut": "Libre",
            "machine_disponible": True
        }

    except Exception as e:
        return {"error": str(e)}

# 🔹 INCREMENT + AUTO START + AUTO TERMINER
@app.post("/api/increment")
def increment(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. production en cours ?
    cursor.execute("""
        SELECT id, quantite, reference 
        FROM Demandes 
        WHERE shift = ? AND statut = 'En cours'
        LIMIT 1
    """, (req.shift,))
    
    demande = cursor.fetchone()

    # 🔥 2. sinon → lancer automatique
    if not demande:
        cursor.execute("""
            SELECT id, quantite, reference 
            FROM Demandes 
            WHERE shift = ? AND statut = 'En attente'
            ORDER BY id ASC LIMIT 1
        """, (req.shift,))
        
        demande = cursor.fetchone()

        if not demande:
            conn.close()
            return {"success": False, "message": "Aucune demande"}

        demande_id, qte_max, ref = demande

        cursor.execute("""
            UPDATE Demandes 
            SET statut = 'En cours', debut_production = datetime('now') 
            WHERE id = ?
        """, (demande_id,))

        compteur = 1

    else:
        demande_id, qte_max, ref = demande

        cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
        row = cursor.fetchone()
        compteur = row[0] + 1 if row else 1

    # 🔹 update compteur
    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, last_update)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(shift) DO UPDATE 
        SET compteur_actuel = ?, last_update = datetime('now')
    """, (req.shift, compteur, compteur))

    termine = (compteur >= qte_max)

    # 🔥 AUTO TERMINER
    if termine:
        cursor.execute("""
            UPDATE Demandes 
            SET statut = 'Termine', fin_production = datetime('now') 
            WHERE id = ?
        """, (demande_id,))

        cursor.execute("""
            UPDATE Stock 
            SET quantite = quantite + ? 
            WHERE reference = ?
        """, (qte_max, ref))

        cursor.execute("""
            UPDATE EtatMachine 
            SET compteur_actuel = 0 
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

# 🔹 DECREMENT (BOUTON ANNULATION)
@app.post("/api/decrement")
def decrement(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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
    return {"success": False, "message": "Compteur deja a zero"}
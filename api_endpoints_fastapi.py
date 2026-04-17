from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3
import os
from datetime import datetime

app = FastAPI()

# Allow ESP32 to connect
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
    return {"message": "API PFE - Poste Soudure Ultrasons", "status": "online"}

@app.get("/api/etat")
def get_etat(shift: str = "A"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, reference, quantite, statut
        FROM Demandes
        WHERE shift = ? AND statut IN ('🟢En cours', '🟠En attente')
        ORDER BY CASE WHEN statut = '🟢En cours' THEN 1 ELSE 2 END, id ASC
        LIMIT 1
    """, (shift,))
    demande = cursor.fetchone()
    
    if not demande:
        conn.close()
        return {
            "machine_disponible": True,
            "demande_id": None,
            "quantite_requise": 0,
            "compteur_actuel": 0
        }
    
    demande_id, reference, quantite_requise, statut = demande
    
    cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (shift,))
    etat = cursor.fetchone()
    compteur_actuel = etat[0] if etat else 0
    
    machine_disponible = (statut != '🟢En cours')
    
    conn.close()
    return {
        "machine_disponible": machine_disponible,
        "demande_id": demande_id,
        "quantite_requise": quantite_requise,
        "compteur_actuel": compteur_actuel
    }

@app.post("/api/increment")
def increment(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, quantite, reference
        FROM Demandes
        WHERE shift = ? AND statut = '🟢En cours'
        ORDER BY id ASC LIMIT 1
    """, (req.shift,))
    demande = cursor.fetchone()
    
    if not demande:
        conn.close()
        return {"success": False, "message": "Aucune production en cours", "termine": False, "compteur": 0}
    
    demande_id, quantite_requise, reference = demande
    
    cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
    etat = cursor.fetchone()
    if etat:
        compteur_actuel = etat[0] + 1
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = ?, last_update = datetime('now') WHERE shift = ?", (compteur_actuel, req.shift))
    else:
        compteur_actuel = 1
        cursor.execute("INSERT INTO EtatMachine (shift, compteur_actuel, last_update) VALUES (?, ?, datetime('now'))", (req.shift, compteur_actuel))
    
    termine = (compteur_actuel >= quantite_requise)
    
    if termine:
        cursor.execute("""
            UPDATE Demandes
            SET statut = 'Terminé', fin_production = datetime('now')
            WHERE id = ?
        """, (demande_id,))
        
        cursor.execute("""
            UPDATE Stock
            SET quantite = quantite + ?
            WHERE reference = ?
        """, (quantite_requise, reference))
        
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = 0 WHERE shift = ?", (req.shift,))
        
        cursor.execute("""
            SELECT id
            FROM Demandes
            WHERE shift = ? AND statut = '🟠En attente'
            ORDER BY 
                CASE urgence WHEN 'Critique' THEN 1 WHEN 'Urgent' THEN 2 ELSE 3 END,
                id ASC
            LIMIT 1
        """, (req.shift,))
        next_demande = cursor.fetchone()
        
        if next_demande:
            cursor.execute("""
                UPDATE Demandes
                SET statut = '🟢En cours', debut_production = datetime('now')
                WHERE id = ?
            """, (next_demande[0],))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "termine": termine, "compteur": compteur_actuel}

@app.post("/api/decrement")
def decrement(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
    etat = cursor.fetchone()
    
    if etat and etat[0] > 0:
        nouveau = etat[0] - 1
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = ?, last_update = datetime('now') WHERE shift = ?", (nouveau, req.shift))
        conn.commit()
        conn.close()
        return {"success": True, "compteur": nouveau}
    else:
        conn.close()
        return {"success": False, "compteur": 0}

@app.get("/api/health")
def health():
    return {"status": "OK", "timestamp": datetime.now().isoformat()}
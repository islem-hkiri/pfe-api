from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import os
from datetime import datetime

app = FastAPI()

# Autoriser l'ESP32 (et toute autre origine)
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
    return {"message": "API PFE - Connectée", "status": "online"}

# ==================== État machine (pour les LEDs) ====================
@app.get("/api/etat")
def get_etat(shift: str = "A"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, statut, quantite
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
            "statut": "Libre",
            "quantite_requise": 0
        }
    
    demande_id, statut, qte = demande
    conn.close()
    
    return {
        "machine_disponible": (statut != '🟢En cours'),
        "demande_id": demande_id,
        "statut": statut,
        "quantite_requise": qte
    }

# ==================== Lancer automatiquement la première tâche en attente ====================
@app.post("/api/lancer_automatique")
def lancer_auto(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Chercher la première tâche en attente
    cursor.execute("""
        SELECT id FROM Demandes 
        WHERE shift = ? AND statut = '🟠En attente' 
        ORDER BY id ASC LIMIT 1
    """, (req.shift,))
    demande = cursor.fetchone()
    
    if not demande:
        conn.close()
        return {"success": False, "message": "Aucune tâche en attente"}
    
    # Passer la tâche en "En cours"
    cursor.execute("""
        UPDATE Demandes 
        SET statut = '🟢En cours', debut_production = datetime('now') 
        WHERE id = ?
    """, (demande[0],))
    
    # Réinitialiser le compteur de la machine pour ce shift
    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, last_update)
        VALUES (?, 0, datetime('now'))
        ON CONFLICT(shift) DO UPDATE SET compteur_actuel = 0, last_update = datetime('now')
    """, (req.shift,))
    
    conn.commit()
    conn.close()
    return {"success": True, "message": "Production lancée"}

# ==================== Incrémentation (+1) ====================
@app.post("/api/increment")
def increment(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Vérifier qu'une tâche est en cours
    cursor.execute("""
        SELECT id, quantite, reference 
        FROM Demandes 
        WHERE shift = ? AND statut = '🟢En cours'
        LIMIT 1
    """, (req.shift,))
    demande = cursor.fetchone()
    
    if not demande:
        conn.close()
        return {"success": False, "termine": False, "message": "Aucune production en cours"}
    
    demande_id, qte_max, ref = demande
    
    # Lire et incrémenter le compteur
    cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
    row = cursor.fetchone()
    compteur = row[0] + 1 if row else 1
    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, last_update)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(shift) DO UPDATE SET compteur_actuel = ?, last_update = datetime('now')
    """, (req.shift, compteur, compteur))
    
    termine = (compteur >= qte_max)
    
    if termine:
        # Terminer la tâche actuelle
        cursor.execute("""
            UPDATE Demandes 
            SET statut = 'Terminé', fin_production = datetime('now') 
            WHERE id = ?
        """, (demande_id,))
        # Mettre à jour le stock
        cursor.execute("""
            UPDATE Stock 
            SET quantite = quantite + ? 
            WHERE reference = ?
        """, (qte_max, ref))
        # Remettre le compteur à zéro
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = 0 WHERE shift = ?", (req.shift,))
    
    conn.commit()
    conn.close()
    return {"success": True, "termine": termine, "compteur": compteur}

# ==================== Décrémentation (-1) ====================
@app.post("/api/decrement")
def decrement(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
    row = cursor.fetchone()
    if row and row[0] > 0:
        nouveau = row[0] - 1
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = ?, last_update = datetime('now') WHERE shift = ?", (nouveau, req.shift))
        conn.commit()
        conn.close()
        return {"success": True, "compteur": nouveau}
    
    conn.close()
    return {"success": False, "compteur": 0}
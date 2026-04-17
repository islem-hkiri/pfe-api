from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import os

app = FastAPI()

# ================= CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= DB =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")

class ShiftRequest(BaseModel):
    shift: str

@app.get("/")
def root():
    return {"message": "API PFE OK"}

# =========================================================
# 🔵 ETAT MACHINE (LED)
# =========================================================
@app.get("/api/etat")
def get_etat(shift: str = "A"):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, statut, quantite
            FROM Demandes
            WHERE shift = ? 
            AND statut IN ('🟢En cours', '🟠En attente')
            ORDER BY 
                CASE 
                    WHEN statut = '🟢En cours' THEN 1 
                    WHEN statut = '🟠En attente' THEN 2 
                END,
                id ASC
            LIMIT 1
        """, (shift,))
        
        demande = cursor.fetchone()

        if not demande:
            return {
                "demande_id": None,
                "statut": "Libre",
                "quantite_requise": 0,
                "machine_disponible": True
            }

        demande_id, statut, qte = demande

        return {
            "demande_id": demande_id,
            "statut": statut,
            "quantite_requise": qte,
            "machine_disponible": (statut != '🟢En cours')
        }

    except Exception as e:
        return {"error": str(e)}

    finally:
        try:
            conn.close()
        except:
            pass

# =========================================================
# 🚀 LANCER PRODUCTION
# =========================================================
@app.post("/api/lancer_automatique")
def lancer_auto(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id FROM Demandes 
        WHERE shift = ? AND statut = '🟠En attente' 
        ORDER BY id ASC LIMIT 1
    """, (req.shift,))
    
    demande = cursor.fetchone()
    
    if not demande:
        conn.close()
        return {"success": False}

    cursor.execute("""
        UPDATE Demandes 
        SET statut = '🟢En cours', debut_production = datetime('now') 
        WHERE id = ?
    """, (demande[0],))
    
    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, last_update)
        VALUES (?, 0, datetime('now'))
        ON CONFLICT(shift) DO UPDATE 
        SET compteur_actuel = 0, last_update = datetime('now')
    """, (req.shift,))
    
    conn.commit()
    conn.close()
    return {"success": True}

# =========================================================
# ➕ INCREMENT
# =========================================================
@app.post("/api/increment")
def increment(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, quantite, reference 
        FROM Demandes 
        WHERE shift = ? AND statut = '🟢En cours'
        LIMIT 1
    """, (req.shift,))
    
    demande = cursor.fetchone()
    
    if not demande:
        conn.close()
        return {"success": False, "termine": False}
    
    demande_id, qte_max, ref = demande
    
    cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
    row = cursor.fetchone()
    compteur = row[0] + 1 if row else 1

    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, last_update)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(shift) DO UPDATE 
        SET compteur_actuel = ?, last_update = datetime('now')
    """, (req.shift, compteur, compteur))
    
    termine = (compteur >= qte_max)
    
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
        """, (qte_max, ref))
        
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = 0 WHERE shift = ?", (req.shift,))
    
    conn.commit()
    conn.close()
    return {"success": True, "termine": termine}

# =========================================================
# ➖ DECREMENT
# =========================================================
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
        return {"success": True}
    
    conn.close()
    return {"success": False}
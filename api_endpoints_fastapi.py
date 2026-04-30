from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import os
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION ET BASE DE DONNÉES
# ═══════════════════════════════════════════════════════════════════
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

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Table Demandes
    cursor.execute('''CREATE TABLE IF NOT EXISTS Demandes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference TEXT, quantite INTEGER, date_besoin TEXT,
        shift TEXT, statut TEXT, urgence TEXT, heure_demande TEXT,
        debut_production TEXT, fin_production TEXT)''')
    # Table Pannes
    cursor.execute('''CREATE TABLE IF NOT EXISTS Pannes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cause TEXT, operateur_id TEXT, debut_panne TEXT, statut TEXT)''')
    # Table Stock
    cursor.execute('''CREATE TABLE IF NOT EXISTS Stock (
        reference TEXT PRIMARY KEY, quantite INTEGER)''')
    # Table EtatMachine
    cursor.execute('''CREATE TABLE IF NOT EXISTS EtatMachine (
        shift TEXT PRIMARY KEY, compteur_actuel INTEGER, 
        demande_id INTEGER, last_update TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ═══════════════════════════════════════════════════════════════════
# MODÈLES DE DONNÉES
# ═══════════════════════════════════════════════════════════════════
class ShiftRequest(BaseModel):
    shift: str

# ═══════════════════════════════════════════════════════════════════
# GESTION DES WEBSOCKETS (Pour les Cartes ESP)
# ═══════════════════════════════════════════════════════════════════
class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
    
    async def connect(self, websocket: WebSocket, shift: str):
        await websocket.accept()
        self.active_connections[shift] = websocket
        print(f"✅ Carte {shift} connectée")
    
    def disconnect(self, shift: str):
        if shift in self.active_connections:
            del self.active_connections[shift]
            print(f"❌ Carte {shift} déconnectée")
    
    async def send_message(self, shift: str, message: str):
        if shift in self.active_connections:
            try:
                await self.active_connections[shift].send_text(message)
                return True
            except:
                self.disconnect(shift)
        return False

manager = ConnectionManager()

# ═══════════════════════════════════════════════════════════════════
# LOGIQUE DE PRODUCTION (INCREMENT / DECREMENT)
# ═══════════════════════════════════════════════════════════════════

def get_status_from_db(shift: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM Demandes WHERE shift = ? AND statut LIKE '%En cours%' LIMIT 1", (shift,))
        en_cours = cursor.fetchone()
        cursor.execute("SELECT id FROM Demandes WHERE shift = ? AND statut LIKE '%attente%' LIMIT 1", (shift,))
        attente = cursor.fetchone()
        conn.close()
        if en_cours: return "🟢En cours"
        if attente: return "🟠En attente"
        return "Libre"
    except:
        return "Libre"

async def send_status_to_card(shift: str):
    status = get_status_from_db(shift)
    await manager.send_message(shift, status)

def increment_sync(shift: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Chercher si une demande est déjà en cours
    cursor.execute("SELECT id, quantite, reference FROM Demandes WHERE shift = ? AND statut LIKE '%En cours%' LIMIT 1", (shift,))
    demande = cursor.fetchone()
    
    if not demande:
        # 2. Sinon, prendre la prochaine en attente
        cursor.execute("SELECT id, quantite, reference FROM Demandes WHERE shift = ? AND statut LIKE '%attente%' ORDER BY id ASC LIMIT 1", (shift,))
        demande = cursor.fetchone()
        if not demande:
            conn.close()
            return {"success": False, "message": "Rien à produire"}
        
        demande_id, qte_totale, ref = demande
        cursor.execute("UPDATE Demandes SET statut = '🟢En cours', debut_production = datetime('now') WHERE id = ?", (demande_id,))
        cursor.execute("INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update) VALUES (?, 0, ?, datetime('now')) ON CONFLICT(shift) DO UPDATE SET compteur_actuel=0, demande_id=?", (shift, demande_id, demande_id))
        compteur = 1
    else:
        demande_id, qte_totale, ref = demande
        cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (shift,))
        row = cursor.fetchone()
        compteur = (row[0] if row else 0) + 1
    
    # Mettre à jour le compteur
    cursor.execute("UPDATE EtatMachine SET compteur_actuel = ?, last_update = datetime('now') WHERE shift = ?", (compteur, shift))
    
    # Vérifier si fini
    termine = (compteur >= qte_totale)
    if termine:
        cursor.execute("UPDATE Demandes SET statut = '✅ Terminé', fin_production = datetime('now') WHERE id = ?", (demande_id,))
        cursor.execute("INSERT INTO Stock (reference, quantite) VALUES (?, ?) ON CONFLICT(reference) DO UPDATE SET quantite = Stock.quantite + ?", (ref, qte_totale, qte_totale))
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = 0, demande_id = NULL WHERE shift = ?", (shift,))

    conn.commit()
    conn.close()
    return {"success": True, "compteur": compteur, "termine": termine}

# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS API (Pour Streamlit et ESP)
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"message": "API Production Connectée", "time": datetime.now()}

# --- ROUTES SUPERVISION (STREAMLIT) ---

@app.get("/api/get_demandes")
def get_demandes():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Demandes ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/create_demande")
async def create_demande(data: dict):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Demandes (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
            VALUES (?, ?, ?, ?, '🟠En attente', ?, datetime('now'))
        """, (data['reference'], data['quantite'], data['date_besoin'], data['shift'], data['urgence']))
        conn.commit()
        conn.close()
        await send_status_to_card(data['shift'])
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/get_pannes")
def get_pannes():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Pannes WHERE statut = 'Ouvert' ORDER BY id DESC")
    pannes = cursor.fetchall()
    conn.close()
    return [dict(p) for p in pannes]

@app.post("/api/resoudre_pannes")
def resoudre():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE Pannes SET statut = 'Résolu' WHERE statut = 'Ouvert'")
    conn.commit()
    conn.close()
    return {"success": True}

@app.post("/api/archiver_demandes")
def archiver():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE Demandes SET statut = 'Archivé' WHERE statut LIKE '%Terminé%'")
    conn.commit()
    conn.close()
    return {"success": True}

# --- ROUTES CARTES / BOUTONS ---

@app.get("/api/etat")
async def get_etat(shift: str = "B"):
    status = get_status_from_db(shift)
    return {"statut": status, "machine_disponible": (status == "Libre")}

@app.post("/api/increment")
async def increment(req: ShiftRequest):
    res = increment_sync(req.shift)
    await send_status_to_card(req.shift)
    return res

@app.websocket("/ws/{shift}")
async def websocket_endpoint(websocket: WebSocket, shift: str):
    await manager.connect(websocket, shift)
    await send_status_to_card(shift)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "increment":
                increment_sync(shift)
                await send_status_to_card(shift)
            elif data == "get_status":
                await send_status_to_card(shift)
    except WebSocketDisconnect:
        manager.disconnect(shift)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
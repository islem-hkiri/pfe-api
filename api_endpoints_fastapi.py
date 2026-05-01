from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
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
        debut_production TEXT, fin_production TEXT, operateur_id TEXT)''')
    # Table Pannes
    cursor.execute('''CREATE TABLE IF NOT EXISTS Pannes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cause TEXT, operateur_id TEXT, debut_panne TEXT, 
        fin_panne TEXT, statut TEXT)''')
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

class DemandeCreate(BaseModel):
    reference: str
    quantite: int
    date_besoin: str
    shift: str
    urgence: str

class PanneCreate(BaseModel):
    operateur_id: str
    cause: str

class ProductionStart(BaseModel):
    demande_id: int
    operateur_id: str

class ProductionEnd(BaseModel):
    demande_id: int

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

def decrement_sync(shift: str):
    print(f"➖ DECREMENT pour shift {shift}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM Demandes WHERE shift = ? AND statut LIKE '%En cours%' LIMIT 1", (shift,))
    en_cours = cursor.fetchone()
    
    if not en_cours:
        conn.close()
        return {"success": False, "message": "Aucune production en cours"}
    
    cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (shift,))
    row = cursor.fetchone()
    
    if row and row[0] > 0:
        nouveau = row[0] - 1
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = ?, last_update = datetime('now') WHERE shift = ?", (nouveau, shift))
        conn.commit()
        conn.close()
        return {"success": True, "compteur": nouveau}
    
    conn.close()
    return {"success": False, "message": "Compteur déjà à zéro"}

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
async def create_demande(data: DemandeCreate):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Demandes (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
        VALUES (?, ?, ?, ?, '🟠En attente', ?, datetime('now'))
    """, (data.reference, data.quantite, data.date_besoin, data.shift, data.urgence))
    conn.commit()
    conn.close()
    await send_status_to_card(data.shift)
    return {"success": True, "message": "Demande créée"}

@app.get("/api/operateur_tasks")
def operateur_tasks(shift: str = "B"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, reference, quantite, statut, shift, urgence
        FROM Demandes
        WHERE shift = ?
        AND statut NOT IN ('✅ Terminé','Archive','Archivé')
        ORDER BY 
            CASE urgence
                WHEN 'Critique' THEN 1
                WHEN 'Urgent' THEN 2
                WHEN 'Normal' THEN 3
                ELSE 4
            END,
            id ASC
    """, (shift,))
    rows = cursor.fetchall()
    conn.close()
    return {"tasks": [{"id": r[0], "reference": r[1], "quantite": r[2], "statut": r[3], "shift": r[4], "urgence": r[5]} for r in rows]}

@app.get("/api/get_pannes")
def get_pannes():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Pannes WHERE statut = '🔴 Ouvert' OR statut = 'Ouvert' ORDER BY id DESC")
    pannes = cursor.fetchall()
    conn.close()
    return [dict(p) for p in pannes]

@app.post("/api/resoudre_pannes")
def resoudre():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE Pannes SET statut = 'Résolu', fin_panne = datetime('now') WHERE statut = '🔴 Ouvert' OR statut = 'Ouvert'")
    conn.commit()
    conn.close()
    return {"success": True}

@app.post("/api/start_production")
async def start_production(data: ProductionStart):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE Demandes 
        SET statut = '🟢En cours', debut_production = datetime('now'), operateur_id = ?
        WHERE id = ?
    """, (data.operateur_id, data.demande_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Production démarrée"}

@app.post("/api/terminer_production")
async def terminer_production(data: ProductionEnd):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE Demandes 
        SET statut = '✅ Terminé', fin_production = datetime('now')
        WHERE id = ?
    """, (data.demande_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Production terminée"}

@app.post("/api/signal_panne")
async def signal_panne(data: PanneCreate):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Pannes (operateur_id, cause, statut, debut_panne)
        VALUES (?, ?, '🔴 Ouvert', datetime('now'))
    """, (data.operateur_id, data.cause))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Panne signalée"}

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

@app.post("/api/decrement")
async def decrement(req: ShiftRequest):
    res = decrement_sync(req.shift)
    await send_status_to_card(req.shift)
    return res

@app.websocket("/ws/{shift}")
async def websocket_endpoint(websocket: WebSocket, shift: str):
    await manager.connect(websocket, shift)
    await send_status_to_card(shift)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
            elif data == "increment":
                increment_sync(shift)
                await send_status_to_card(shift)
            elif data == "decrement":
                decrement_sync(shift)
                await send_status_to_card(shift)
            elif data == "get_status":
                await send_status_to_card(shift)
    except WebSocketDisconnect:
        manager.disconnect(shift)

@app.get("/api/debug")
def debug():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, shift, statut, quantite FROM Demandes LIMIT 10")
    data = cursor.fetchall()
    conn.close()
    return {"demandes": [{"id": d[0], "shift": d[1], "statut": d[2], "Qté": d[3]} for d in data]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
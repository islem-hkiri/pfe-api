from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
    
    async def send_message(self, shift: str, message: str):
        if shift in self.active_connections:
            try:
                await self.active_connections[shift].send_text(message)
                return True
            except:
                self.disconnect(shift)
                return False
        return False

manager = ConnectionManager()

def get_status_from_db(shift: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM Demandes WHERE shift = ? AND (statut LIKE '%En cours%') LIMIT 1", (shift,))
        en_cours = cursor.fetchone()
        
        cursor.execute("SELECT id FROM Demandes WHERE shift = ? AND (statut LIKE '%En attente%') LIMIT 1", (shift,))
        attente = cursor.fetchone()
        
        conn.close()
        
        if en_cours:
            return "🟢En cours"
        elif attente:
            return "🟠En attente"
        else:
            return "Libre"
    except:
        return "Libre"

async def send_status_to_card(shift: str):
    status = get_status_from_db(shift)
    await manager.send_message(shift, status)
    return status

class ShiftRequest(BaseModel):
    shift: str

class DemandeCreate(BaseModel):
    reference: str
    quantite: int
    date_besoin: str
    shift: str
    urgence: str

@app.websocket("/ws/{shift}")
async def websocket_endpoint(websocket: WebSocket, shift: str):
    await manager.connect(websocket, shift)
    await send_status_to_card(shift)
    
    try:
        while True:
            data = await websocket.receive_text()
            
            if data == "ping":
                await websocket.send_text("pong")
            elif data == "get_status":
                await send_status_to_card(shift)
            elif data == "increment":
                increment_sync(ShiftRequest(shift=shift))
                await send_status_to_card(shift)
            elif data == "decrement":
                decrement_sync(ShiftRequest(shift=shift))
                await send_status_to_card(shift)
    except WebSocketDisconnect:
        manager.disconnect(shift)

def increment_sync(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, quantite, reference FROM Demandes WHERE shift = ? AND (statut LIKE '%En cours%') LIMIT 1", (req.shift,))
    demande = cursor.fetchone()

    if not demande:
        # ORDONNER PAR URGENCE: Critique > Urgent > Normal
        cursor.execute("""
            SELECT id, quantite, reference FROM Demandes
            WHERE shift = ? AND (statut LIKE '%En attente%')
            ORDER BY CASE urgence WHEN 'Critique' THEN 1 WHEN 'Urgent' THEN 2 WHEN 'Normal' THEN 3 ELSE 4 END, id ASC LIMIT 1
        """, (req.shift,))
        demande = cursor.fetchone()

        if not demande:
            conn.close()
            return {"success": False, "message": "Aucune demande en attente"}

        demande_id, Qté, ref = demande

        cursor.execute("UPDATE Demandes SET statut = '🟢En cours', debut_production = datetime('now') WHERE id = ?", (demande_id,))

        cursor.execute("INSERT INTO `EtatMachine` (shift, compteur_actuel, demande_id, last_update) VALUES (?, 0, ?, datetime('now')) ON CONFLICT(shift) DO UPDATE SET compteur_actuel = 0, demande_id = ?, last_update = datetime('now')", (req.shift, demande_id, demande_id))

        compteur = 1

    else:
        demande_id, Qté, ref = demande
        cursor.execute("SELECT compteur_actuel FROM `EtatMachine` WHERE shift = ?", (req.shift,))
        row = cursor.fetchone()
        compteur = row[0] if row else 0
        
        if compteur >= Qté:
            conn.close()
            return {"success": False, "message": f"Quantité maximale {Qté} atteinte"}
        
        compteur += 1

    cursor.execute("INSERT INTO `EtatMachine` (shift, compteur_actuel, demande_id, last_update) VALUES (?, ?, ?, datetime('now')) ON CONFLICT(shift) DO UPDATE SET compteur_actuel = ?, demande_id = ?, last_update = datetime('now')", (req.shift, compteur, demande_id, compteur, demande_id))

    termine = (compteur >= Qté)

    if terme:
        cursor.execute("UPDATE Demandes SET statut = '✅ Terminé', fin_production = datetime('now') WHERE id = ?", (demande_id,))
        cursor.execute("UPDATE Stock SET quantite = quantite + ? WHERE reference = ?", (Qté, ref))
        cursor.execute("UPDATE `EtatMachine` SET compteur_actuel = 0, demande_id = NULL WHERE shift = ?", (req.shift,))

        # AUTO-DEMARRAGE avec PRIORITÉ URGENCE
        cursor.execute("""
            SELECT id, quantite, reference FROM Demandes
            WHERE shift = ? AND (statut LIKE '%En attente%')
            ORDER BY CASE urgence WHEN 'Critique' THEN 1 WHEN 'Urgent' THEN 2 WHEN 'Normal' THEN 3 ELSE 4 END, id ASC LIMIT 1
        """, (req.shift,))
        next_demande = cursor.fetchone()

        if next_demande:
            next_id, next_qte, next_ref = next_demande
            cursor.execute("UPDATE Demandes SET statut = '🟢En cours', debut_production = datetime('now') WHERE id = ?", (next_id,))
            cursor.execute("INSERT INTO `EtatMachine` (shift, compteur_actuel, demande_id, last_update) VALUES (?, 0, ?, datetime('now')) ON CONFLICT(shift) DO UPDATE SET compteur_actuel = 0, demande_id = ?, last_update = datetime('now')", (req.shift, next_id, next_id))
            conn.commit()

    conn.commit()
    conn.close()
    return {"success": True, "compteur": compteur, "Qté": Qté, "termine": terme}

def decrement_sync(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM Demandes WHERE shift = ? AND (statut LIKE '%En cours%') LIMIT 1", (req.shift,))
    en_cours = cursor.fetchone()

    if not en_cours:
        conn.close()
        return {"success": False, "message": "Aucune production en cours"}

    cursor.execute("SELECT compteur_actuel FROM `EtatMachine` WHERE shift = ?", (req.shift,))
    row = cursor.fetchone()

    if row and row[0] > 0:
        nouveau = row[0] - 1
        cursor.execute("UPDATE `EtatMachine` SET compteur_actuel = ?, last_update = datetime('now') WHERE shift = ?", (nouveau, req.shift))
        conn.commit()
        conn.close()
        return {"success": True, "compteur": nouveau}

    conn.close()
    return {"success": False, "message": "Compteur déjà à zéro"}

@app.get("/")
def root():
    return {"message": "API PFE"}

@app.get("/api/etat")
async def get_etat(shift: str = "B"):
    status = get_status_from_db(shift)
    await send_status_to_card(shift)
    return {"statut": status, "machine_disponible": (status == "Libre")}

@app.post("/api/increment")
async def increment(req: ShiftRequest):
    return increment_sync(req)

@app.post("/api/decrement")
async def decrement(req: ShiftRequest):
    return decrement_sync(req)

@app.get("/api/debug")
def debug():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, shift, statut, quantite FROM Demandes LIMIT 10")
    data = cursor.fetchall()
    conn.close()
    return {"demandes": [{"id": d[0], "shift": d[1], "statut": d[2], "Qté": d[3]} for d in data]}

@app.post("/api/create_demande")
async def create_demande(data: DemandeCreate):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Demandes (reference, quantite, date_besoin, shift, statut, urgence, heure_demande) VALUES (?, ?, ?, ?, '🟠En attente', ?, datetime('now'))", (data.reference, data.quantite, data.date_besoin, data.shift, data.urgence))
    conn.commit()
    conn.close()
    await send_status_to_card(data.shift)
    return {"success": True}

@app.get("/api/operateur_tasks")
def operateur_tasks(shift: str = "B"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, reference, quantite, statut, shift FROM Demandes WHERE shift = ? AND statut NOT LIKE '%Terminé%' ORDER BY id ASC", (shift,))
    rows = cursor.fetchall()
    conn.close()
    return {"tasks": [{"id": r[0], "reference": r[1], "quantite": r[2], "statut": r[3], "shift": r[4]} for r in rows]}

if __name__ == "__main__":
    import uvicorn
    print("🚀 SERVEUR DÉMARRÉ")
    uvicorn.run(app, host="0.0.0.0", port=8000)
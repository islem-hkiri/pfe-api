from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import os
import asyncio

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
            print(f"❌ Carte {shift} déconnectée")
    
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
        
        cursor.execute("""
            SELECT id FROM Demandes
            WHERE shift = ? AND (statut LIKE '%En cours%')
            LIMIT 1
        """, (shift,))
        en_cours = cursor.fetchone()
        
        cursor.execute("""
            SELECT id FROM Demandes
            WHERE shift = ? AND (statut LIKE '%En attente%')
            LIMIT 1
        """, (shift,))
        attente = cursor.fetchone()
        
        conn.close()
        
        if en_cours:
            return "🟢En cours"
        elif attente:
            return "🟠En attente"
        else:
            return "Libre"
    except Exception as e:
        print(f"❌ Erreur DB: {e}")
        return "Libre"

async def send_status_to_card(shift: str):
    status = get_status_from_db(shift)
    await manager.send_message(shift, status)
    return status

class ShiftRequest(BaseModel):
    shift: str

@app.websocket("/ws/{shift}")
async def websocket_endpoint(websocket: WebSocket, shift: str):
    await manager.connect(websocket, shift)
    await send_status_to_card(shift)
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"📨 Reçu de {shift}: {data}")
            
            if data == "ping":
                await websocket.send_text("pong")
            elif data == "get_status":
                await send_status_to_card(shift)
            elif data == "increment":
                result = increment_sync(ShiftRequest(shift=shift))
                if result.get("success"):
                    await send_status_to_card(shift)
                else:
                    await websocket.send_text(f"ERROR:{result.get('message', 'Erreur')}")
            elif data == "decrement":
                decrement_sync(ShiftRequest(shift=shift))
                await send_status_to_card(shift)
                
    except WebSocketDisconnect:
        manager.disconnect(shift)

def increment_sync(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if there is already a production in progress[cite: 1, 2]
    cursor.execute("""
        SELECT id, quantite, reference 
        FROM Demandes 
        WHERE shift = ? AND (statut LIKE '%En cours%')
        LIMIT 1
    """, (req.shift,))
    
    demande = cursor.fetchone()
    
    if not demande:
        # Ordonnancement: Urgence (Critique > Urgent > Normal) then Date[cite: 1, 2]
        cursor.execute("""
            SELECT id, quantite, reference 
            FROM Demandes 
            WHERE shift = ? AND (statut LIKE '%En attente%')
            ORDER BY 
                CASE 
                    WHEN urgence = 'Critique' THEN 1 
                    WHEN urgence = 'Urgent' THEN 2 
                    WHEN urgence = 'Normal' THEN 3 
                    ELSE 4 
                END ASC, 
                date_besoin ASC, 
                heure_demande ASC 
            LIMIT 1
        """, (req.shift,))
        
        demande = cursor.fetchone()
        
        if not demande:
            conn.close()
            return {"success": False, "message": "Aucune demande en attente"}
        
        demande_id, Qté, ref = demande
        cursor.execute("UPDATE Demandes SET statut = '🟢En cours', debut_production = datetime('now') WHERE id = ?", (demande_id,))
        cursor.execute("""
            INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
            VALUES (?, 1, ?, datetime('now'))
            ON CONFLICT(shift) DO UPDATE 
            SET compteur_actuel = 1, demande_id = ?, last_update = datetime('now')
        """, (req.shift, demande_id, demande_id))
        compteur = 1
    else:
        demande_id, Qté, ref = demande
        cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
        row = cursor.fetchone()
        compteur = (row[0] if row else 0) + 1
        
        if compteur > Qté:
            conn.close()
            return {"success": False, "message": "Quantité maximale atteinte"}
            
        cursor.execute("""
            UPDATE EtatMachine 
            SET compteur_actuel = ?, last_update = datetime('now') 
            WHERE shift = ?
        """, (compteur, req.shift))

    termine = (compteur >= Qté)
    
    if termine:
        cursor.execute("UPDATE Demandes SET statut = '✅ Terminé', fin_production = datetime('now') WHERE id = ?", (demande_id,))
        cursor.execute("UPDATE Stock SET quantite = quantite + ? WHERE reference = ?", (Qté, ref))
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = 0, demande_id = NULL WHERE shift = ?", (req.shift,))
        
        # Auto-start next task according to priority[cite: 1, 2]
        cursor.execute("""
            SELECT id, quantite, reference FROM Demandes
            WHERE shift = ? AND (statut LIKE '%En attente%')
            ORDER BY 
                CASE WHEN urgence = 'Critique' THEN 1 WHEN urgence = 'Urgent' THEN 2 ELSE 3 END ASC, 
                date_besoin ASC LIMIT 1
        """, (req.shift,))
        next_d = cursor.fetchone()
        if next_d:
            cursor.execute("UPDATE Demandes SET statut = '🟢En cours', debut_production = datetime('now') WHERE id = ?", (next_d[0],))
            cursor.execute("UPDATE EtatMachine SET compteur_actuel = 0, demande_id = ? WHERE shift = ?", (next_d[0], req.shift))

    conn.commit()
    conn.close()
    return {"success": True, "compteur": compteur, "Qté": Qté, "termine": termine}

def decrement_sync(req: ShiftRequest):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
    row = cursor.fetchone()
    if row and row[0] > 0:
        cursor.execute("UPDATE EtatMachine SET compteur_actuel = ?, last_update = datetime('now') WHERE shift = ?", (row[0]-1, req.shift))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
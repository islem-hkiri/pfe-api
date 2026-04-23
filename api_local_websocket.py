from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import os
import asyncio
from typing import Dict
import threading

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

# ========== GESTION WEBSOCKET ==========
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.last_status: Dict[str, str] = {}
    
    async def connect(self, websocket: WebSocket, shift: str):
        await websocket.accept()
        self.active_connections[shift] = websocket
        print(f"✅ Carte {shift} connectée")
        
        # Envoyer le statut actuel immédiatement
        await self.send_status(shift)
        return True
    
    def disconnect(self, shift: str):
        if shift in self.active_connections:
            del self.active_connections[shift]
            print(f"❌ Carte {shift} déconnectée")
    
    async def send_to_card(self, shift: str, message: str):
        if shift in self.active_connections:
            try:
                await self.active_connections[shift].send_text(message)
                print(f"📤 Envoyé à {shift}: {message}")
                return True
            except:
                self.disconnect(shift)
                return False
        return False
    
    async def send_status(self, shift: str):
        """Récupère et envoie le statut actuel à une carte"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, statut FROM Demandes
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
                status = "🟢En cours"
            elif attente:
                status = "🟠En attente"
            else:
                status = "Libre"
            
            self.last_status[shift] = status
            await self.send_to_card(shift, status)
            print(f"📊 Statut envoyé à {shift}: {status}")
            
        except Exception as e:
            print(f"❌ Erreur send_status: {e}")

manager = ConnectionManager()

class ShiftRequest(BaseModel):
    shift: str

# ========== WEBSOCKET ENDPOINT ==========
@app.websocket("/ws/{shift}")
async def websocket_endpoint(websocket: WebSocket, shift: str):
    await manager.connect(websocket, shift)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"📨 Reçu de {shift}: {data}")
            
            # Traiter les commandes de l'ESP32
            if data == "ping":
                await websocket.send_text("pong")
            elif "increment" in data:
                # Appeler increment
                req = ShiftRequest(shift=shift)
                result = increment(req)
                # Envoyer le nouveau statut
                await manager.send_status(shift)
            elif "decrement" in data:
                req = ShiftRequest(shift=shift)
                result = decrement(req)
                await manager.send_status(shift)
                
    except WebSocketDisconnect:
        manager.disconnect(shift)

# ========== API ENDPOINTS ==========
@app.get("/")
def root():
    return {"message": "API PFE Local avec WebSocket"}

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
            status_data = {"statut": "🟢En cours", "machine_disponible": False}
        elif attente:
            status_data = {"statut": "🟠En attente", "machine_disponible": False}
        else:
            status_data = {"statut": "Libre", "machine_disponible": True}
        
        # Envoyer via WebSocket
        asyncio.create_task(manager.send_status(shift))
        
        return status_data
        
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/increment")
def increment(req: ShiftRequest):
    print(f"➕ INCREMENT pour shift {req.shift}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Vérifier production en cours
    cursor.execute("""
        SELECT id, quantite, reference 
        FROM Demandes 
        WHERE shift = ? AND (statut = '🟢En cours' OR statut = 'En cours')
        LIMIT 1
    """, (req.shift,))
    
    demande = cursor.fetchone()
    
    # Si pas de production, démarrer la première en attente
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
        
        # Initialiser compteur
        cursor.execute("""
            INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
            VALUES (?, 0, ?, datetime('now'))
            ON CONFLICT(shift) DO UPDATE 
            SET compteur_actuel = 0, demande_id = ?, last_update = datetime('now')
        """, (req.shift, demande_id, demande_id))
        
        compteur = 1
        print(f"🚀 Production démarrée: {ref} - Quantité: {qte_max}")
        
    else:
        demande_id, qte_max, ref = demande
        cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
        row = cursor.fetchone()
        compteur = row[0] + 1 if row else 1
        print(f"📊 Compteur: {compteur}/{qte_max}")
    
    # Mettre à jour compteur
    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(shift) DO UPDATE 
        SET compteur_actuel = ?, demande_id = ?, last_update = datetime('now')
    """, (req.shift, compteur, demande_id, compteur, demande_id))
    
    termine = (compteur >= qte_max)
    
    # Auto-terminer
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
        
        cursor.execute("""
            UPDATE EtatMachine 
            SET compteur_actuel = 0, demande_id = NULL
            WHERE shift = ?
        """, (req.shift,))
        
        print(f"✅ Production terminée! {qte_max} unités de {ref}")
    
    conn.commit()
    conn.close()
    
    # Envoyer le nouveau statut via WebSocket (IMPORTANT!)
    asyncio.create_task(manager.send_status(req.shift))
    
    return {
        "success": True,
        "compteur": compteur,
        "max": qte_max,
        "termine": termine
    }

@app.post("/api/decrement")
def decrement(req: ShiftRequest):
    print(f"➖ DECREMENT pour shift {req.shift}")
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
        
        # Envoyer le nouveau statut
        asyncio.create_task(manager.send_status(req.shift))
        
        return {"success": True, "compteur": nouveau}
    
    conn.close()
    return {"success": False, "message": "Compteur déjà à zéro"}

@app.get("/api/debug")
def debug():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, shift, statut, quantite FROM Demandes LIMIT 10")
    data = cursor.fetchall()
    conn.close()
    return {"demandes": [{"id": d[0], "shift": d[1], "statut": d[2], "qte": d[3]} for d in data]}

if __name__ == "__main__":
    import uvicorn
    print("="*50)
    print("🚀 SERVEUR DÉMARRÉ")
    print(f"📡 HTTP: http://localhost:8000")
    print(f"🔌 WebSocket: ws://localhost:8000/ws/{{shift}}")
    print("="*50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
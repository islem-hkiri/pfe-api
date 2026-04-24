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

# ========== STOCKAGE DES CONNEXIONS ==========
class ConnectionManager:
    def __init__(self):
        self.active_connections = {}  # {shift: websocket}
    
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
                print(f"📤 Envoyé à {shift}: {message}")
                return True
            except:
                self.disconnect(shift)
                return False
        return False

manager = ConnectionManager()

# Variable pour stocker la dernière tâche asyncio pour chaque shift
last_status_tasks = {}

def get_status_from_db(shift: str):
    """Récupère le statut depuis la base de données (synchrone)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id FROM Demandes
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
            return "🟢En cours"
        elif attente:
            return "🟠En attente"
        else:
            return "Libre"
    except Exception as e:
        print(f"❌ Erreur DB: {e}")
        return "Libre"

# Fonction asynchrone pour envoyer le statut
async def send_status_to_card(shift: str):
    """Envoie le statut actuel à la carte ESP32"""
    status = get_status_from_db(shift)
    await manager.send_message(shift, status)
    return status

class ShiftRequest(BaseModel):
    shift: str

# ========== WEBSOCKET ENDPOINT ==========
@app.websocket("/ws/{shift}")
async def websocket_endpoint(websocket: WebSocket, shift: str):
    await manager.connect(websocket, shift)
    
    # Envoyer le statut immédiatement après connexion
    await send_status_to_card(shift)
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"📨 Reçu de {shift}: {data}")
            
            if data == "ping":
                await websocket.send_text("pong")
                print("💓 Pong envoyé")
            
            elif data == "increment":
                print("➕ Traitement increment...")
                # Appeler la fonction increment (qui est synchrone)
                result = increment_sync(ShiftRequest(shift=shift))
                print(f"Résultat increment: {result}")
                # Envoyer le nouveau statut
                await send_status_to_card(shift)
            
            elif data == "decrement":
                print("➖ Traitement decrement...")
                result = decrement_sync(ShiftRequest(shift=shift))
                print(f"Résultat decrement: {result}")
                await send_status_to_card(shift)
            
            else:
                print(f"📝 Message non reconnu: {data}")
                
    except WebSocketDisconnect:
        manager.disconnect(shift)

# ========== FONCTIONS SYNC POUR INCREMENT/DECREMENT ==========
def increment_sync(req: ShiftRequest):
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
            print("❌ Aucune demande en attente")
            return {"success": False, "message": "Aucune demande en attente"}
        
        demande_id, Qté, ref = demande
        
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
        print(f"🚀 Production démarrée: {ref} - Quantité à produire: {Qté}")
        
    else:
        demande_id, Qté, ref = demande
        cursor.execute("SELECT compteur_actuel FROM EtatMachine WHERE shift = ?", (req.shift,))
        row = cursor.fetchone()
        compteur = (row[0] + 1) if row else 1
        print(f"📊 Progression: {compteur}/{Qté}")
    
    # Mettre à jour compteur
    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(shift) DO UPDATE 
        SET compteur_actuel = ?, demande_id = ?, last_update = datetime('now')
    """, (req.shift, compteur, demande_id, compteur, demande_id))
    
    termine = (compteur >= Qté)
    
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
        """, (Qté, ref))
        
        cursor.execute("""
            UPDATE EtatMachine 
            SET compteur_actuel = 0, demande_id = NULL
            WHERE shift = ?
        """, (req.shift,))
        
        print(f"✅ Production TERMINÉE! {Qté} unités de {ref}")
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "compteur": compteur,
        "Qté": Qté,
        "termine": termine
    }

def decrement_sync(req: ShiftRequest):
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
        print("❌ Aucune production en cours")
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
        print(f"📉 Compteur diminué à: {nouveau}")
        return {"success": True, "compteur": nouveau}
    
    conn.close()
    print("❌ Compteur déjà à zéro")
    return {"success": False, "message": "Compteur déjà à zéro"}

# ========== API ENDPOINTS (pour test via navigateur) ==========
@app.get("/")
def root():
    return {"message": "API PFE Local avec WebSocket"}

@app.get("/api/etat")
async def get_etat(shift: str = "A"):
    """Endpoint HTTP pour vérifier l'état"""
    status = get_status_from_db(shift)
    # Envoyer aussi via WebSocket si connecté
    await send_status_to_card(shift)
    return {"statut": status, "machine_disponible": (status == "Libre")}

@app.post("/api/increment")
async def increment(req: ShiftRequest):
    result = increment_sync(req)
    await send_status_to_card(req.shift)
    return result

@app.post("/api/decrement")
async def decrement(req: ShiftRequest):
    result = decrement_sync(req)
    await send_status_to_card(req.shift)
    return result

@app.get("/api/debug")
def debug():
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
        VALUES ('TEST_001',Qté , date('now'), 'B', '🟠En attente', 'Normal', datetime('now'))
    """)
    conn.commit()
    conn.close()
    return {"message": "Demande TEST_001 ajoutée pour shift B! Allez teste la pédale maintenant!"}

if __name__ == "__main__":
    import uvicorn
    print("="*50)
    print("🚀 SERVEUR DÉMARRÉ")
    print(f"📡 HTTP: http://localhost:8000")
    print(f"🔌 WebSocket: ws://localhost:8000/ws/{{shift}}")
    print("="*50)
    print("\n💡 Pour tester:")
    print("   1. Ouvre http://localhost:8000/api/add_direct")
    print("   2. Appuie sur la pédale ESP32")
    print("="*50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
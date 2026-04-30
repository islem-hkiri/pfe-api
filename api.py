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

# ═══════════════════════════════════════════════════════════════════
# CONNECTION MANAGER WebSocket
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
                print(f"Envoyé à {shift}: {message}")
                return True
            except:
                self.disconnect(shift)
                return False
        return False

manager = ConnectionManager()

# ═══════════════════════════════════════════════════════════════════
# MODELS Pydantic
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

# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_status_from_db(shift: str):
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id FROM Demandes
            WHERE shift = ? 
            AND (statut = '🟢En cours' OR statut = 'En cours')
            LIMIT 1
        """, (shift,))
        en_cours = cursor.fetchone()

        cursor.execute("""
            SELECT id FROM Demandes
            WHERE shift = ? 
            AND (statut = '🟠En attente' OR statut = 'En attente')
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
        print(f"❌ Erreur DB get_status: {e}")
        return "Libre"

async def send_status_to_card(shift: str):
    status = get_status_from_db(shift)
    await manager.send_message(shift, status)
    return status

# ═══════════════════════════════════════════════════════════════════
# LOGIQUE INCREMENT
# ═══════════════════════════════════════════════════════════════════
def increment_sync(req: ShiftRequest):
    print(f"➕ INCREMENT pour shift {req.shift}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── Chercher demande En cours ──────────────────────────────────
    cursor.execute("""
        SELECT id, quantite, reference 
        FROM Demandes 
        WHERE shift = ? 
        AND (statut = '🟢En cours' OR statut = 'En cours')
        LIMIT 1
    """, (req.shift,))
    demande = cursor.fetchone()

    if not demande:
        # ── Chercher demande En attente ────────────────────────────
        cursor.execute("""
            SELECT id, quantite, reference 
            FROM Demandes 
            WHERE shift = ? 
            AND (statut = '🟠En attente' OR statut = 'En attente')
            ORDER BY id ASC LIMIT 1
        """, (req.shift,))
        demande = cursor.fetchone()

        if not demande:
            conn.close()
            print("❌ Aucune demande disponible")
            return {"success": False, "message": "Aucune demande disponible"}

        demande_id, qte, ref = demande

        # Démarrer la production
        cursor.execute("""
            UPDATE Demandes 
            SET statut = '🟢En cours', debut_production = datetime('now') 
            WHERE id = ?
        """, (demande_id,))

        cursor.execute("""
            INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
            VALUES (?, 0, ?, datetime('now'))
            ON CONFLICT(shift) DO UPDATE 
            SET compteur_actuel = 0, 
                demande_id = ?, 
                last_update = datetime('now')
        """, (req.shift, demande_id, demande_id))

        compteur = 1
        print(f" Démarrage: {ref} | Qté: {qte}")

    else:
        demande_id, qte, ref = demande

        # Récupérer compteur actuel
        cursor.execute(
            "SELECT compteur_actuel FROM EtatMachine WHERE shift = ?",
            (req.shift,)
        )
        row = cursor.fetchone()
        compteur = row[0] if row else 0

        if compteur >= qte:
            conn.close()
            print(f"⚠️ Max atteint {compteur}/{qte}")
            return {"success": False, "message": f"Quantité max {qte} atteinte"}

        compteur += 1
        print(f"📊 Progression: {compteur}/{qte}")

    # ── Mise à jour EtatMachine ────────────────────────────────────
    cursor.execute("""
        INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(shift) DO UPDATE 
        SET compteur_actuel = ?, 
            demande_id = ?, 
            last_update = datetime('now')
    """, (req.shift, compteur, demande_id, compteur, demande_id))

    termine = (compteur >= qte)

    if termine:
        # ── Marquer Terminé ────────────────────────────────────────
        cursor.execute("""
            UPDATE Demandes 
            SET statut = '✅ Terminé', fin_production = datetime('now') 
            WHERE id = ?
        """, (demande_id,))

        # ── Mettre à jour Stock ────────────────────────────────────
        cursor.execute("""
            UPDATE Stock 
            SET quantite = quantite + ? 
            WHERE reference = ?
        """, (qte, ref))

        # ── Reset EtatMachine ──────────────────────────────────────
        cursor.execute("""
            UPDATE EtatMachine 
            SET compteur_actuel = 0, demande_id = NULL
            WHERE shift = ?
        """, (req.shift,))

        print(f"✅ Terminé: {qte} x {ref}")

        # ── Auto-démarrage prochaine demande ───────────────────────
        cursor.execute("""
            SELECT id, quantite, reference
            FROM Demandes
            WHERE shift = ? 
            AND (statut = '🟠En attente' OR statut = 'En attente')
            ORDER BY id ASC LIMIT 1
        """, (req.shift,))
        next_d = cursor.fetchone()

        if next_d:
            next_id, next_qte, next_ref = next_d

            cursor.execute("""
                UPDATE Demandes
                SET statut = '🟢En cours',
                    debut_production = datetime('now')
                WHERE id = ?
            """, (next_id,))

            cursor.execute("""
                INSERT INTO EtatMachine (shift, compteur_actuel, demande_id, last_update)
                VALUES (?, 0, ?, datetime('now'))
                ON CONFLICT(shift) DO UPDATE
                SET compteur_actuel = 0, 
                    demande_id = ?, 
                    last_update = datetime('now')
            """, (req.shift, next_id, next_id))

            print(f"🔄 Auto-démarrage: {next_ref} (Qté: {next_qte})")

    conn.commit()
    conn.close()

    return {
        "success": True,
        "compteur": compteur,
        "quantite": qte,
        "termine": termine
    }

# ═══════════════════════════════════════════════════════════════════
# LOGIQUE DECREMENT
# ═══════════════════════════════════════════════════════════════════
def decrement_sync(req: ShiftRequest):
    print(f"➖ DECREMENT pour shift {req.shift}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM Demandes 
        WHERE shift = ? 
        AND (statut = '🟢En cours' OR statut = 'En cours')
        LIMIT 1
    """, (req.shift,))
    en_cours = cursor.fetchone()

    if not en_cours:
        conn.close()
        return {"success": False, "message": "Aucune production en cours"}

    cursor.execute(
        "SELECT compteur_actuel FROM EtatMachine WHERE shift = ?",
        (req.shift,)
    )
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
        print(f"Compteur: {nouveau}")
        return {"success": True, "compteur": nouveau}

    conn.close()
    return {"success": False, "message": "Compteur déjà à zéro"}

# ═══════════════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINT
# ═══════════════════════════════════════════════════════════════════
@app.websocket("/ws/{shift}")
async def websocket_endpoint(websocket: WebSocket, shift: str):
    await manager.connect(websocket, shift)
    await send_status_to_card(shift)

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Reçu de {shift}: {data}")

            if data == "ping":
                await websocket.send_text("pong")

            elif data == "get_status":
                await send_status_to_card(shift)

            elif data == "increment":
                result = increment_sync(ShiftRequest(shift=shift))
                if result.get("success"):
                    await send_status_to_card(shift)
                else:
                    await websocket.send_text(
                        f"ERROR:{result.get('message', 'Erreur')}"
                    )

            elif data == "decrement":
                result = decrement_sync(ShiftRequest(shift=shift))
                await send_status_to_card(shift)

            else:
                print(f"Message inconnu: {data}")

    except WebSocketDisconnect:
        manager.disconnect(shift)

# ═══════════════════════════════════════════════════════════════════
# HTTP ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"message": "✅ API PFE - WebSocket + REST"}

# ── GET toutes les demandes (Streamlit Logistique) ─────────────────
@app.get("/api/get_demandes")
def get_demandes():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id, reference, quantite, date_besoin,
                shift, statut, urgence, heure_demande,
                debut_production, fin_production, operateur_id
            FROM Demandes
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()

        # Récupérer compteurs EtatMachine
        cursor.execute(
            "SELECT shift, compteur_actuel, demande_id FROM EtatMachine"
        )
        etats = {e[0]: {"compteur": e[1], "demande_id": e[2]} 
                 for e in cursor.fetchall()}

        conn.close()

        demandes = []
        for r in rows:
            shift = r[4]
            demande_id = r[0]
            etat = etats.get(shift, {})

            # Ajouter compteur si c'est la demande en cours
            compteur = 0
            if etat.get("demande_id") == demande_id:
                compteur = etat.get("compteur", 0)

            demandes.append({
                "id":               r[0],
                "reference":        r[1],
                "quantite":         r[2],
                "date_besoin":      r[3],
                "shift":            r[4],
                "statut":           r[5],
                "urgence":          r[6],
                "heure_demande":    r[7],
                "debut_production": r[8],
                "fin_production":   r[9],
                "operateur_id":     r[10],
                "compteur":         compteur
            })

        return demandes

    except Exception as e:
        print(f"❌ get_demandes error: {e}")
        return []

# ── GET pannes (Streamlit Logistique alertes) ──────────────────────
@app.get("/api/get_pannes")
def get_pannes():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, operateur_id, cause, debut_panne, fin_panne, statut
            FROM Pannes
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id":           r[0],
                "operateur_id": r[1],
                "cause":        r[2],
                "debut_panne":  r[3],
                "fin_panne":    r[4],
                "statut":       r[5]
            }
            for r in rows
        ]

    except Exception as e:
        print(f"❌ get_pannes error: {e}")
        return []

# ── POST créer demande (Streamlit Logistique panier) ───────────────
@app.post("/api/create_demande")
async def create_demande(data: DemandeCreate):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Demandes 
            (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
            VALUES (?, ?, ?, ?, '🟠En attente', ?, datetime('now'))
        """, (
            data.reference,
            data.quantite,
            data.date_besoin,
            data.shift,
            data.urgence
        ))
        conn.commit()
        conn.close()

        # Notifier ESP32 en temps réel
        await send_status_to_card(data.shift)

        return {"success": True, "message": f"Demande créée shift {data.shift}"}

    except Exception as e:
        return {"success": False, "error": str(e)}

# ── POST signaler panne (Opérateur) ───────────────────────────────
@app.post("/api/signaler_panne")
async def signaler_panne(data: PanneCreate):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Pannes (operateur_id, cause, debut_panne, statut)
            VALUES (?, ?, datetime('now'), '🔴 Ouvert')
        """, (data.operateur_id, data.cause))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Panne signalée"}

    except Exception as e:
        return {"success": False, "error": str(e)}

# ── POST résoudre pannes (Logistique confirme) ─────────────────────
@app.post("/api/resoudre_pannes")
def resoudre_pannes():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Pannes 
            SET statut = 'Résolu', fin_panne = datetime('now') 
            WHERE statut = '🔴 Ouvert'
        """)
        conn.commit()
        nb = cursor.rowcount
        conn.close()
        return {"success": True, "pannes_resolues": nb}

    except Exception as e:
        return {"success": False, "error": str(e)}

# ── POST archiver demandes (Logistique vider historique) ───────────
@app.post("/api/archiver_demandes")
def archiver_demandes():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Demandes 
            SET statut = 'Archivé' 
            WHERE statut != 'Archivé'
        """)
        conn.commit()
        nb = cursor.rowcount
        conn.close()
        return {"success": True, "archivees": nb}

    except Exception as e:
        return {"success": False, "error": str(e)}

# ── GET etat machine ───────────────────────────────────────────────
@app.get("/api/etat")
async def get_etat(shift: str = "B"):
    status = get_status_from_db(shift)
    await send_status_to_card(shift)
    return {"statut": status, "machine_disponible": (status == "Libre")}

# ── POST increment / decrement (HTTP fallback) ─────────────────────
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

# ── GET tâches opérateur ───────────────────────────────────────────
@app.get("/api/operateur_tasks")
def operateur_tasks(shift: str = "B"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, reference, quantite, statut, shift,
               urgence, debut_production, fin_production, operateur_id
        FROM Demandes
        WHERE shift = ?
        AND statut NOT IN ('✅ Terminé', 'Archivé')
        ORDER BY id ASC
    """, (shift,))
    rows = cursor.fetchall()

    cursor.execute(
        "SELECT compteur_actuel, demande_id FROM EtatMachine WHERE shift = ?",
        (shift,)
    )
    etat = cursor.fetchone()
    conn.close()

    compteur_actuel  = etat[0] if etat else 0
    demande_en_cours = etat[1] if etat else None

    tasks = []
    for r in rows:
        tasks.append({
            "id":               r[0],
            "reference":        r[1],
            "quantite":         r[2],
            "statut":           r[3],
            "shift":            r[4],
            "urgence":          r[5],
            "debut_production": r[6],
            "fin_production":   r[7],
            "operateur_id":     r[8],
            "compteur": compteur_actuel if r[0] == demande_en_cours else 0
        })

    return {"tasks": tasks, "compteur_actuel": compteur_actuel}

# ── GET debug ──────────────────────────────────────────────────────
@app.get("/api/debug")
def debug():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, shift, statut, quantite, reference 
        FROM Demandes ORDER BY id DESC LIMIT 20
    """)
    demandes = cursor.fetchall()

    cursor.execute(
        "SELECT shift, compteur_actuel, demande_id FROM EtatMachine"
    )
    etats = cursor.fetchall()
    conn.close()

    return {
        "demandes": [
            {"id": d[0], "shift": d[1], "statut": d[2], 
             "quantite": d[3], "reference": d[4]}
            for d in demandes
        ],
        "etat_machine": [
            {"shift": e[0], "compteur": e[1], "demande_id": e[2]}
            for e in etats
        ]
    }

# ── GET add_direct test ────────────────────────────────────────────
@app.get("/api/add_direct")
def add_direct():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Demandes 
        (reference, quantite, date_besoin, shift, statut, urgence, heure_demande)
        VALUES ('TEST_001', 20, date('now'), 'B', '🟠En attente', 'Normal', datetime('now'))
    """)
    conn.commit()
    conn.close()
    return {"message": "✅ TEST_001 ajouté shift B - 20 unités"}

# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("🚀 SERVEUR DÉMARRÉ")
    print("📡 HTTP  : http://localhost:8000")
    print("📋 Docs  : http://localhost:8000/docs")
    print("🔌 WS    : ws://localhost:8000/ws/{shift}")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
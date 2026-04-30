from fastapi import FastAPI
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
DB_PATH  = os.path.join(BASE_DIR, "gestion_production.db")

# ═══════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════
class DemandeCreate(BaseModel):
    reference:   str
    quantite:    int
    date_besoin: str
    shift:       str
    urgence:     str

class PanneCreate(BaseModel):
    operateur_id: str
    cause:        str

# ═══════════════════════════════════════════════════════════════════
# ROOT
# ═══════════════════════════════════════════════════════════════════
@app.get("/")
def root():
    return {"message": "✅ API Render Endpoints - PFE"}

# ═══════════════════════════════════════════════════════════════════
# GET DEMANDES
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/get_demandes")
def get_demandes():
    """
    Retourne toutes les demandes avec leur compteur actuel.
    Utilisé par Streamlit Logistique.
    """
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
        etats = {
            e[0]: {"compteur": e[1], "demande_id": e[2]}
            for e in cursor.fetchall()
        }
        conn.close()

        demandes = []
        for r in rows:
            shift      = r[4]
            demande_id = r[0]
            etat       = etats.get(shift, {})

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

# ═══════════════════════════════════════════════════════════════════
# GET PANNES
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/get_pannes")
def get_pannes():
    """
    Retourne toutes les pannes.
    Utilisé par Streamlit Logistique pour les alertes.
    """
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

# ═══════════════════════════════════════════════════════════════════
# CREATE DEMANDE
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/create_demande")
def create_demande(data: DemandeCreate):
    """
    Crée une nouvelle demande.
    Appelé par Streamlit Logistique (panier).
    """
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
        return {
            "success": True,
            "message": f"Demande créée pour shift {data.shift}"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════
# SIGNALER PANNE
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/signaler_panne")
def signaler_panne(data: PanneCreate):
    """
    Opérateur signale une panne.
    """
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

# ═══════════════════════════════════════════════════════════════════
# RESOUDRE PANNES
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/resoudre_pannes")
def resoudre_pannes():
    """
    Marque toutes les pannes ouvertes comme résolues.
    Appelé par bouton 'Confirmer' dans Streamlit Logistique.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Pannes
            SET statut    = 'Résolu',
                fin_panne = datetime('now')
            WHERE statut  = '🔴 Ouvert'
        """)
        conn.commit()
        nb = cursor.rowcount
        conn.close()
        return {"success": True, "pannes_resolues": nb}

    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════
# ARCHIVER DEMANDES
# ═══════════════════════════════════════════════════════════════════
@app.post("/api/archiver_demandes")
def archiver_demandes():
    """
    Archive toutes les demandes.
    Appelé par 'Vider historique' dans Streamlit Logistique.
    """
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

# ═══════════════════════════════════════════════════════════════════
# OPERATEUR TASKS
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/operateur_tasks")
def operateur_tasks(shift: str = "B"):
    """
    Retourne les tâches d'un opérateur par shift.
    Utilisé par Streamlit Opérateur.
    """
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

    return {
        "tasks":            tasks,
        "compteur_actuel":  compteur_actuel
    }

# ═══════════════════════════════════════════════════════════════════
# DEBUG
# ═══════════════════════════════════════════════════════════════════
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
            {
                "id":        d[0],
                "shift":     d[1],
                "statut":    d[2],
                "quantite":  d[3],
                "reference": d[4]
            }
            for d in demandes
        ],
        "etat_machine": [
            {
                "shift":      e[0],
                "compteur":   e[1],
                "demande_id": e[2]
            }
            for e in etats
        ]
    }

# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("🚀 SERVEUR RENDER ENDPOINTS DÉMARRÉ")
    print("📡 HTTP  : http://localhost:8001")
    print("📋 Docs  : http://localhost:8001/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8001)
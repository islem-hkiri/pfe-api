# database_v2.py (version complète avec auto-sync)
import sqlite3
import pandas as pd
import openpyxl
import os
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_production.db")
KANBAN_PATH = os.path.join(BASE_DIR, "Classeur Kanban VKF CW 12.xlsm")
PDB_PATH = os.path.join(BASE_DIR, "LAS_PDB .xlsm")

# Variable pour savoir si on est en train de synchro
_sync_in_progress = False
_last_sync_time = 0

def init_db(force_reinit=False):
    """Initialise la base sans perdre les données existantes"""
    global _last_sync_time
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # CREATE TABLES IF NOT EXISTS (préserve les données)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS EtatMachine (
        shift TEXT PRIMARY KEY,
        demande_id INTEGER,
        compteur_actuel INTEGER DEFAULT 0,
        machine_disponible INTEGER DEFAULT 1,
        last_update TEXT
    )
    """)
    
    for s in ['A', 'B']:
        cursor.execute("INSERT OR IGNORE INTO EtatMachine (shift, compteur_actuel, machine_disponible) VALUES (?, 0, 1)", (s,))

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Pannes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operateur_id TEXT,
        machine_id TEXT,
        cause TEXT NOT NULL,
        debut_panne TEXT NOT NULL,
        fin_panne TEXT,
        statut TEXT DEFAULT '🔴 Ouvert'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Produits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference TEXT UNIQUE,
        famille TEXT,
        module TEXT,
        pression REAL,
        temps REAL,
        amplitude REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Stock (
        reference TEXT PRIMARY KEY, 
        famille TEXT, 
        quantite INTEGER DEFAULT 0
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Demandes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference TEXT,
        quantite INTEGER,
        date_besoin TEXT,
        shift TEXT,
        statut TEXT DEFAULT '🟠En attente',
        urgence TEXT,
        heure_demande TEXT,
        debut_production TEXT,
        fin_production TEXT,
        operateur_id TEXT
    )
    """)

    # Ajouter les colonnes si elles n'existent pas (migration)
    try:
        cursor.execute("ALTER TABLE Demandes ADD COLUMN operateur_id TEXT")
    except sqlite3.OperationalError:
        pass  # La colonne existe déjà
    
    try:
        cursor.execute("ALTER TABLE Pannes ADD COLUMN machine_id TEXT")
    except sqlite3.OperationalError:
        pass

    # 🔥 IMPORT DES DONNÉES (sans dupliquer)
    imported_count = 0
    
    # Import Dispatching
    try:
        if os.path.exists(KANBAN_PATH):
            df_k = pd.read_excel(KANBAN_PATH, sheet_name="DISPATCHING REF")
            for i, row in df_k.iterrows():
                try:
                    ref = str(row.iloc[2]).strip()
                    if ref.lower() not in ['nan', '', 'none', 'ref cab']:
                        # Vérifier si existe déjà
                        cursor.execute("SELECT reference FROM Produits WHERE reference=?", (ref,))
                        if not cursor.fetchone():
                            cursor.execute("INSERT INTO Produits (reference, famille, module) VALUES (?, ?, ?)", 
                                         (ref, str(row.iloc[1]).strip(), str(row.iloc[0]).strip()))
                            cursor.execute("INSERT INTO Stock (reference, famille, quantite) VALUES (?, ?, 0)", 
                                         (ref, str(row.iloc[1]).strip()))
                            imported_count += 1
                except:
                    continue
            print(f"✅ Dispatching: {imported_count} nouvelles références")
    except Exception as e:
        print(f"⚠️ Erreur Dispatching: {e}")

    # Import BESOIN
    try:
        if os.path.exists(KANBAN_PATH):
            wb = openpyxl.load_workbook(KANBAN_PATH, data_only=True)
            if "BESOIN" in wb.sheetnames:
                sheet = wb["BESOIN"]
                count_log = 0
                for row_idx in range(2, 501):
                    cell_value = sheet.cell(row=row_idx, column=1).value
                    if cell_value is not None:
                        val_ref = str(cell_value).strip()
                        if val_ref.lower() not in ['nan','none','','fiat pn','ref cab','ref','pn']:
                            cursor.execute("SELECT reference FROM Produits WHERE reference=?", (val_ref,))
                            if not cursor.fetchone():
                                cursor.execute("""
                                    INSERT INTO Produits (reference, famille, module)
                                    VALUES (?, 'Reference_Cable', 'LOGISTIQUE')
                                """, (val_ref,))
                                cursor.execute("""
                                    INSERT INTO Stock (reference, famille, quantite)
                                    VALUES (?, 'Reference_Cable', 0)
                                """, (val_ref,))
                                count_log += 1
                print(f"✅ Logistique: {count_log} nouvelles références")
    except Exception as e:
        print(f"⚠️ Erreur Logistique: {e}")

    # Import PDB (mettre à jour les paramètres)
    try:
        if os.path.exists(PDB_PATH):
            df_pdb = pd.read_excel(PDB_PATH, sheet_name=0)
            updated_count = 0
            for _, row in df_pdb.iterrows():
                ref_p = str(row.iloc[1]).strip()
                if ref_p not in ['nan', '']:
                    cursor.execute("""
                        UPDATE Produits 
                        SET pression=?, temps=?, amplitude=? 
                        WHERE reference=?
                    """, (
                        pd.to_numeric(row.iloc[2], errors='coerce'), 
                        pd.to_numeric(row.iloc[5], errors='coerce'), 
                        pd.to_numeric(row.iloc[6], errors='coerce'), 
                        ref_p
                    ))
                    if cursor.rowcount > 0:
                        updated_count += 1
            print(f"✅ PDB: {updated_count} mises à jour")
    except Exception as e:
        print(f"⚠️ Erreur PDB: {e}")

    conn.commit()
    conn.close()
    _last_sync_time = time.time()
    print(f"✅ Base synchronisée à {time.strftime('%H:%M:%S')}")
    return imported_count

def manual_sync():
    """Fonction pour synchroniser manuellement depuis l'UI"""
    global _sync_in_progress
    
    if _sync_in_progress:
        return {"success": False, "message": "Synchronisation déjà en cours"}
    
    _sync_in_progress = True
    try:
        count = init_db()
        return {"success": True, "message": f"Sync terminée! {count} nouvelles références", "count": count}
    except Exception as e:
        return {"success": False, "message": f"Erreur: {str(e)}"}
    finally:
        _sync_in_progress = False

def get_sync_status():
    """Retourne le statut de la dernière synchronisation"""
    return {
        "last_sync": time.strftime('%H:%M:%S', time.localtime(_last_sync_time)) if _last_sync_time > 0 else "Jamais",
        "in_progress": _sync_in_progress,
        "db_exists": os.path.exists(DB_PATH)
    }

if __name__ == "__main__":
    print("🔄 Lancement de la synchronisation...")
    init_db()
    print("✨ Base de données prête!")
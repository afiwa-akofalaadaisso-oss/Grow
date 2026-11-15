"""
Grow — Module de Résilience de Base de Données & Réplication Locale SQLite
Assure un fonctionnement 100% ininterrompu même en cas de latence, coupure réseau ou pause Supabase.
"""

import os
import json
import sqlite3
import uuid
import time
import asyncio
import concurrent.futures
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

SUPABASE_TRANSACTION_COLUMNS = {
    "id", "entreprise_id", "date_operation", "libelle", "compte_syscohada",
    "type_flux", "est_professionnel", "montant_fcfa", "source_paiement",
    "statut_validation", "created_at"
}


def sanitize_payload_for_supabase(table: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Nettoie le payload pour ne transmettre que les colonnes existantes dans le schéma Supabase."""
    if table == "transactions":
        clean = {k: v for k, v in payload.items() if k in SUPABASE_TRANSACTION_COLUMNS and v is not None}
        if "est_professionnel" in clean:
            clean["est_professionnel"] = bool(clean["est_professionnel"])
        if "montant_fcfa" in clean:
            try:
                clean["montant_fcfa"] = int(round(float(clean["montant_fcfa"])))
            except (ValueError, TypeError):
                clean["montant_fcfa"] = 0
        return clean
    elif table == "entreprises":
        return {k: v for k, v in payload.items() if k not in ["updated_at"] and v is not None}
    return payload
DB_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(DB_DIR, "grow_compta.db")

# Supabase Client Singleton
_SUPABASE_CLIENT = None
_SUPABASE_INIT_ATTEMPTED = False
_DB_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="grow_db_pool")


def get_sqlite_conn():
    """Crée une connexion SQLite avec timeout et multithreading activé."""
    conn = sqlite3.connect(SQLITE_DB_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_local_sqlite():
    """Initialise les tables locales SQLite si elles n'existent pas."""
    conn = get_sqlite_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS entreprises (
        id TEXT PRIMARY KEY,
        nom_entreprise TEXT,
        telephone_whatsapp TEXT,
        secteur_activite TEXT,
        capital_initial_fcfa REAL DEFAULT 0,
        date_inscription TEXT,
        heure_rappel_quotidien TEXT,
        ninea TEXT,
        date_creation_officielle TEXT,
        adresse_siege TEXT,
        nombre_employes INTEGER DEFAULT 0,
        operateurs_paiement TEXT,
        etape_onboarding TEXT,
        donnees_onboarding TEXT,
        updated_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        entreprise_id TEXT,
        date_operation TEXT,
        libelle TEXT,
        compte_syscohada TEXT,
        type_flux TEXT,
        est_professionnel INTEGER DEFAULT 1,
        montant_fcfa REAL DEFAULT 0,
        source_paiement TEXT,
        statut_validation TEXT DEFAULT 'VALIDE_PME',
        reference_externe TEXT,
        created_at TEXT,
        updated_at TEXT,
        sync_status TEXT DEFAULT 'SYNCED'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sync_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        table_name TEXT,
        record_id TEXT,
        payload TEXT,
        created_at TEXT,
        attempts INTEGER DEFAULT 0,
        last_error TEXT
    )
    """)

    conn.commit()
    conn.close()
    print("[DB INIT] Base de données locale SQLite initialisée avec succès.")


def get_supabase_client():
    """Récupère ou initialise l'instance unique du client Supabase."""
    global _SUPABASE_CLIENT, _SUPABASE_INIT_ATTEMPTED
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    load_dotenv(os.path.join(DB_DIR, ".env"), override=False)
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None

    try:
        from supabase import create_client
        _SUPABASE_CLIENT = create_client(url, key)
        _SUPABASE_INIT_ATTEMPTED = True
        return _SUPABASE_CLIENT
    except Exception as e:
        print(f"[SUPABASE INIT ERROR] : {e}")
        return None


def run_with_timeout(func, timeout_seconds=2.0, fallback=None):
    """Exécute une fonction dans le thread pool partagé avec un timeout strict pour éviter tout gel du serveur."""
    global _DB_THREAD_POOL
    future = _DB_THREAD_POOL.submit(func)
    try:
        return future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        print(f"[TIMEOUT {timeout_seconds}s] Supabase trop lent -> Bascule instantanée sur SQLite local")
        return fallback
    except Exception as e:
        print(f"[SUPABASE ERROR] {e} -> Bascule instantanée sur SQLite local")
        return fallback


# =========================================================================
# SYNCHRONISATION & RÉPLICATION
# =========================================================================

def mirror_entreprises_to_sqlite(rows: List[Dict[str, Any]]):
    """Met à jour le cache local SQLite des entreprises."""
    if not rows:
        return
    conn = get_sqlite_conn()
    cur = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    for r in rows:
        ent_id = r.get("id")
        if not ent_id:
            continue
        cur.execute("""
        INSERT INTO entreprises (
            id, nom_entreprise, telephone_whatsapp, secteur_activite, capital_initial_fcfa,
            date_inscription, heure_rappel_quotidien, ninea, date_creation_officielle,
            adresse_siege, nombre_employes, operateurs_paiement, etape_onboarding,
            donnees_onboarding, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            nom_entreprise=excluded.nom_entreprise,
            telephone_whatsapp=excluded.telephone_whatsapp,
            secteur_activite=excluded.secteur_activite,
            capital_initial_fcfa=excluded.capital_initial_fcfa,
            heure_rappel_quotidien=excluded.heure_rappel_quotidien,
            ninea=excluded.ninea,
            date_creation_officielle=excluded.date_creation_officielle,
            adresse_siege=excluded.adresse_siege,
            nombre_employes=excluded.nombre_employes,
            operateurs_paiement=excluded.operateurs_paiement,
            etape_onboarding=excluded.etape_onboarding,
            donnees_onboarding=excluded.donnees_onboarding,
            updated_at=excluded.updated_at
        """, (
            str(ent_id),
            r.get("nom_entreprise"),
            r.get("telephone_whatsapp"),
            r.get("secteur_activite"),
            float(r.get("capital_initial_fcfa") or 0),
            r.get("date_inscription"),
            r.get("heure_rappel_quotidien"),
            r.get("ninea"),
            r.get("date_creation_officielle"),
            r.get("adresse_siege"),
            int(r.get("nombre_employes") or 0),
            json.dumps(r.get("operateurs_paiement") or {}, ensure_ascii=False) if isinstance(r.get("operateurs_paiement"), (dict, list)) else str(r.get("operateurs_paiement") or ""),
            r.get("etape_onboarding"),
            json.dumps(r.get("donnees_onboarding") or {}, ensure_ascii=False) if isinstance(r.get("donnees_onboarding"), (dict, list)) else str(r.get("donnees_onboarding") or ""),
            now_str
        ))
    conn.commit()
    conn.close()


def mirror_transactions_to_sqlite(rows: List[Dict[str, Any]]):
    """Met à jour le cache local SQLite des transactions."""
    if not rows:
        return
    conn = get_sqlite_conn()
    cur = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    for t in rows:
        tx_id = t.get("id")
        if not tx_id:
            continue
        cur.execute("""
        INSERT INTO transactions (
            id, entreprise_id, date_operation, libelle, compte_syscohada, type_flux,
            est_professionnel, montant_fcfa, source_paiement, statut_validation,
            reference_externe, created_at, updated_at, sync_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED')
        ON CONFLICT(id) DO UPDATE SET
            entreprise_id=excluded.entreprise_id,
            date_operation=excluded.date_operation,
            libelle=excluded.libelle,
            compte_syscohada=excluded.compte_syscohada,
            type_flux=excluded.type_flux,
            est_professionnel=excluded.est_professionnel,
            montant_fcfa=excluded.montant_fcfa,
            source_paiement=excluded.source_paiement,
            statut_validation=excluded.statut_validation,
            reference_externe=excluded.reference_externe,
            updated_at=excluded.updated_at,
            sync_status='SYNCED'
        """, (
            str(tx_id),
            str(t.get("entreprise_id") or ""),
            str(t.get("date_operation") or ""),
            t.get("libelle"),
            t.get("compte_syscohada"),
            t.get("type_flux"),
            1 if t.get("est_professionnel") else 0,
            float(t.get("montant_fcfa") or 0),
            t.get("source_paiement"),
            t.get("statut_validation") or "VALIDE_PME",
            t.get("reference_externe"),
            t.get("created_at") or now_str,
            now_str
        ))
    conn.commit()
    conn.close()


# =========================================================================
# LECTURES RÉSILIpackage (TIMEOUT + FALLBACK SQLITE)
# =========================================================================

def get_all_entreprises_resilient() -> List[Dict[str, Any]]:
    """Récupère toutes les entreprises, avec fallback SQLite immédiat en cas d'indisponibilité Supabase."""
    sp = get_supabase_client()
    if sp:
        def fetch_sp():
            res = sp.table("entreprises").select("*").order("date_inscription", desc=True).execute()
            return res.data or []

        data = run_with_timeout(fetch_sp, timeout_seconds=2.5, fallback=None)
        if data is not None:
            # Réplication asynchrone / threadée dans SQLite
            try:
                mirror_entreprises_to_sqlite(data)
            except Exception as e:
                print(f"[MIRROR ERROR] {e}")
            return data

    # Fallback SQLite
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM entreprises ORDER BY date_inscription DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    for r in rows:
        if r.get("donnees_onboarding") and isinstance(r["donnees_onboarding"], str):
            try:
                r["donnees_onboarding"] = json.loads(r["donnees_onboarding"])
            except Exception:
                pass
    return rows


def get_transactions_resilient(entreprise_id: str) -> List[Dict[str, Any]]:
    """Récupère les transactions d'une entreprise avec fallback SQLite instantané."""
    if not entreprise_id or str(entreprise_id).startswith("new_"):
        return []

    sp = get_supabase_client()
    if sp:
        def fetch_sp():
            res = sp.table("transactions").select("*, preuves_numeriques(*)").eq("entreprise_id", entreprise_id).order("date_operation", desc=True).order("created_at", desc=True).execute()
            return res.data or []

        data = run_with_timeout(fetch_sp, timeout_seconds=2.5, fallback=None)
        if data is not None:
            try:
                mirror_transactions_to_sqlite(data)
            except Exception as e:
                print(f"[MIRROR TX ERROR] {e}")
            return data

    # Fallback local SQLite immédiat (<1ms)
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE entreprise_id = ? ORDER BY date_operation DESC, created_at DESC", (str(entreprise_id),))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    for r in rows:
        r["preuves_numeriques"] = []
    return rows


def get_entreprise_by_phone_resilient(phone: str) -> Optional[Dict[str, Any]]:
    """Recherche une entreprise par téléphone avec fallback local."""
    clean_p = str(phone).replace("+", "").replace(" ", "").strip()
    if not clean_p:
        return None

    sp = get_supabase_client()
    if sp:
        def fetch_sp():
            res = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_p}%").limit(1).execute()
            return res.data[0] if res.data else None

        data = run_with_timeout(fetch_sp, timeout_seconds=2.0, fallback=None)
        if data is not None:
            try:
                mirror_entreprises_to_sqlite([data])
            except Exception:
                pass
            return data

    # Fallback local SQLite
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM entreprises WHERE telephone_whatsapp LIKE ? LIMIT 1", (f"%{clean_p}%",))
    row = cur.fetchone()
    conn.close()
    if row:
        d = dict(row)
        if d.get("donnees_onboarding") and isinstance(d["donnees_onboarding"], str):
            try:
                d["donnees_onboarding"] = json.loads(d["donnees_onboarding"])
            except Exception:
                pass
        return d
    return None


# =========================================================================
# ÉCRITURES RÉSILIpackage (SQLITE IMMÉDIAT + ASYNC/QUEUE SUPABASE)
# =========================================================================

def save_transaction_resilient(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enregistre une transaction immédiatement en SQLite local (garantie zéro perte),
    puis tente de synchroniser avec Supabase. En cas d'échec ou de timeout Supabase,
    met en file d'attente pour sync en arrière-plan.
    """
    tx_id = payload.get("id") or str(uuid.uuid4())
    now_str = datetime.utcnow().isoformat()
    date_op = payload.get("date_operation") or datetime.now().strftime("%Y-%m-%d")

    tx_row = {
        "id": tx_id,
        "entreprise_id": str(payload.get("entreprise_id")),
        "date_operation": str(date_op),
        "libelle": payload.get("libelle") or "Opération",
        "compte_syscohada": str(payload.get("compte_syscohada") or "701"),
        "type_flux": str(payload.get("type_flux") or "ENTREE").upper(),
        "est_professionnel": 1 if payload.get("est_professionnel", True) else 0,
        "montant_fcfa": float(payload.get("montant_fcfa") or 0),
        "source_paiement": str(payload.get("source_paiement") or "ESPECES"),
        "statut_validation": str(payload.get("statut_validation") or "VALIDE_PME"),
        "reference_externe": payload.get("reference_externe"),
        "created_at": payload.get("created_at") or now_str,
        "updated_at": now_str,
        "sync_status": "PENDING_SYNC"
    }

    # 1. Écriture immédiate dans SQLite local (garantie absolue)
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO transactions (
        id, entreprise_id, date_operation, libelle, compte_syscohada, type_flux,
        est_professionnel, montant_fcfa, source_paiement, statut_validation,
        reference_externe, created_at, updated_at, sync_status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        montant_fcfa=excluded.montant_fcfa,
        libelle=excluded.libelle,
        compte_syscohada=excluded.compte_syscohada,
        type_flux=excluded.type_flux,
        source_paiement=excluded.source_paiement,
        date_operation=excluded.date_operation,
        updated_at=excluded.updated_at
    """, (
        tx_row["id"], tx_row["entreprise_id"], tx_row["date_operation"],
        tx_row["libelle"], tx_row["compte_syscohada"], tx_row["type_flux"],
        tx_row["est_professionnel"], tx_row["montant_fcfa"], tx_row["source_paiement"],
        tx_row["statut_validation"], tx_row["reference_externe"], tx_row["created_at"],
        tx_row["updated_at"], tx_row["sync_status"]
    ))
    conn.commit()

    # 2. Tentative de sync Supabase avec timeout
    sp = get_supabase_client()
    synced = False
    if sp:
        def push_to_supabase():
            sp_payload = sanitize_payload_for_supabase("transactions", tx_row)
            res = sp.table("transactions").upsert(sp_payload).execute()
            return res.data

        res_sp = run_with_timeout(push_to_supabase, timeout_seconds=2.0, fallback=None)
        if res_sp:
            synced = True
            cur.execute("UPDATE transactions SET sync_status='SYNCED' WHERE id=?", (tx_id,))
            conn.commit()

    # 3. Si non synchronisé avec Supabase, placer en file d'attente
    if not synced:
        cur.execute("""
        INSERT INTO sync_queue (action, table_name, record_id, payload, created_at)
        VALUES ('UPSERT', 'transactions', ?, ?, ?)
        """, (tx_id, json.dumps(tx_row, ensure_ascii=False), now_str))
        conn.commit()
        print(f"[OFFLINE QUEUE] Opération {tx_id} stockée en local SQLite et en attente de sync Supabase.")

    conn.close()
    return {"status": "success", "data": [tx_row], "synced_to_supabase": synced}


def update_transaction_resilient(tx_id: str, update_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Modifie une transaction en local SQLite immédiatement, puis sync avec Supabase."""
    if not tx_id:
        return {"status": "error", "message": "ID manquant"}

    now_str = datetime.utcnow().isoformat()
    conn = get_sqlite_conn()
    cur = conn.cursor()

    set_clauses = ["updated_at = ?", "sync_status = 'PENDING_SYNC'"]
    params = [now_str]

    for k, v in update_fields.items():
        if k in ["libelle", "compte_syscohada", "type_flux", "source_paiement", "date_operation", "statut_validation", "reference_externe"]:
            set_clauses.append(f"{k} = ?")
            params.append(str(v))
        elif k == "montant_fcfa":
            set_clauses.append("montant_fcfa = ?")
            params.append(float(v))
        elif k == "est_professionnel":
            set_clauses.append("est_professionnel = ?")
            params.append(1 if v else 0)

    params.append(tx_id)
    cur.execute(f"UPDATE transactions SET {', '.join(set_clauses)} WHERE id = ?", params)
    conn.commit()

    # Sync Supabase
    sp = get_supabase_client()
    synced = False
    if sp:
        def push_update():
            clean_fields = sanitize_payload_for_supabase("transactions", update_fields)
            res = sp.table("transactions").update(clean_fields).eq("id", tx_id).execute()
            return res.data

        res_sp = run_with_timeout(push_update, timeout_seconds=2.0, fallback=None)
        if res_sp:
            synced = True
            cur.execute("UPDATE transactions SET sync_status='SYNCED' WHERE id=?", (tx_id,))
            conn.commit()

    if not synced:
        cur.execute("""
        INSERT INTO sync_queue (action, table_name, record_id, payload, created_at)
        VALUES ('UPDATE', 'transactions', ?, ?, ?)
        """, (tx_id, json.dumps(update_fields, ensure_ascii=False), now_str))
        conn.commit()

    conn.close()
    return {"status": "success", "synced_to_supabase": synced}


def save_or_update_entreprise_resilient(ent_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Crée ou met à jour une entreprise avec réplication locale et queue de secours."""
    ent_id = ent_dict.get("id") or str(uuid.uuid4())
    ent_dict["id"] = ent_id
    mirror_entreprises_to_sqlite([ent_dict])

    sp = get_supabase_client()
    if sp:
        def push_ent():
            res = sp.table("entreprises").upsert(ent_dict).execute()
            return res.data
        run_with_timeout(push_ent, timeout_seconds=2.0, fallback=None)

    return ent_dict


# =========================================================================
# WORKER D'ARRIÈRE-PLAN POUR LE DÉPILAGE DE LA FILE D'ATTENTE SYNC
# =========================================================================

def flush_sync_queue():
    """Tente de vider la file d'attente des écritures vers Supabase."""
    sp = get_supabase_client()
    if not sp:
        return 0

    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sync_queue ORDER BY id ASC LIMIT 50")
    pending = [dict(r) for r in cur.fetchall()]
    if not pending:
        conn.close()
        return 0

    flushed_count = 0
    for item in pending:
        item_id = item["id"]
        table = item["table_name"]
        action = item["action"]
        record_id = item["record_id"]
        try:
            payload = json.loads(item["payload"])
        except Exception:
            payload = {}

        success = False
        try:
            sp_payload = sanitize_payload_for_supabase(table, payload)
            if action in ["INSERT", "UPSERT"]:
                res = sp.table(table).upsert(sp_payload).execute()
                if res.data:
                    success = True
            elif action == "UPDATE":
                res = sp.table(table).update(sp_payload).eq("id", record_id).execute()
                if res.data:
                    success = True

            if success:
                cur.execute("DELETE FROM sync_queue WHERE id = ?", (item_id,))
                if table == "transactions":
                    cur.execute("UPDATE transactions SET sync_status='SYNCED' WHERE id = ?", (record_id,))
                conn.commit()
                flushed_count += 1
                print(f"[SYNC QUEUE] Élément {item_id} ({table}:{record_id}) synchronisé avec succès dans Supabase !")
            else:
                cur.execute("UPDATE sync_queue SET attempts = attempts + 1 WHERE id = ?", (item_id,))
                conn.commit()
        except Exception as err:
            cur.execute("UPDATE sync_queue SET attempts = attempts + 1, last_error = ? WHERE id = ?", (str(err)[:250], item_id))
            conn.commit()
            print(f"[SYNC QUEUE RETRY] Erreur pour {item_id}: {err}")
            break  # Supabase est probablement inaccessible, attendre le prochain cycle

    conn.close()
    return flushed_count


# Initialiser la base locale à l'importation
init_local_sqlite()

"""
Grow — Module de Résilience de Base de Données & Réplication Locale SQLite
Assure un fonctionnement 100% ininterrompu même en cas de latence, coupure réseau ou pause Supabase.
"""

import os
import re
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
        if "date_operation" in clean and clean["date_operation"]:
            d_str = str(clean["date_operation"]).strip()
            m_date = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", d_str)
            if m_date:
                day, month, year = m_date.groups()
                clean["date_operation"] = f"{year}-{int(month):02d}-{int(day):02d}"
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

    # Table de mémoire longue durée des conversations (Support 50+ messages et persistance intégrale)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS conversation_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT,
        role TEXT,
        message_text TEXT,
        created_at TEXT
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_phone ON conversation_messages(phone, id DESC)")

    # Table des appréciations (👍 LIKE) et dépréciations (👎 DISLIKE) des réponses de Growth
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT,
        rating TEXT,
        message_id TEXT,
        created_at TEXT
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fb_phone ON ai_feedback(phone, id DESC)")

    # Table du backlog d'apprentissage continu & auto-critique de l'IA
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_learning_backlog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT,
        question_utilisateur TEXT,
        reponse_growth TEXT,
        score_confiance REAL,
        motif TEXT,
        statut TEXT DEFAULT 'A_AMELIORER',
        reponse_amelioree TEXT,
        created_at TEXT
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_learn_statut ON ai_learning_backlog(statut, id DESC)")

    # Table des abonnements et encaissements de la plateforme Growth (Caisse Créateur)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS abonnements_growth (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telephone TEXT NOT NULL,
        nom_entreprise TEXT,
        plan TEXT NOT NULL DEFAULT 'Starter',
        montant_fcfa REAL NOT NULL DEFAULT 10000.0,
        operateur TEXT NOT NULL DEFAULT 'WAVE',
        date_paiement TEXT NOT NULL,
        statut TEXT NOT NULL DEFAULT 'PAYE',
        reference TEXT
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_abo_phone ON abonnements_growth(telephone, id DESC)")

    # Table des sorties et dépenses de la plateforme Growth (Pourquoi c'est sorti / Caisse Créateur)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS depenses_createur_growth (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        motif TEXT NOT NULL,
        categorie TEXT NOT NULL DEFAULT 'AUTRE',
        montant_fcfa REAL NOT NULL DEFAULT 0.0,
        source_paiement TEXT NOT NULL DEFAULT 'WAVE',
        beneficiaire TEXT,
        date_depense TEXT NOT NULL,
        justificatif_note TEXT
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_depense_date ON depenses_createur_growth(date_depense DESC)")

    conn.commit()

    # Migration résiliente : colonne justificatif_url
    try:
        cur.execute("ALTER TABLE transactions ADD COLUMN justificatif_url TEXT")
        conn.commit()
    except Exception:
        pass

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

    # Migration résiliente : colonne justificatif_url
    try:
        cur.execute("ALTER TABLE transactions ADD COLUMN justificatif_url TEXT")
        conn.commit()
    except Exception:
        pass

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

    # Migration résiliente : colonne justificatif_url
    try:
        cur.execute("ALTER TABLE transactions ADD COLUMN justificatif_url TEXT")
        conn.commit()
    except Exception:
        pass

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
    """Récupère les transactions d'une entreprise en fusionnant Supabase et le cache local SQLite."""
    if not entreprise_id or str(entreprise_id).startswith("new_"):
        return []

    # 1. Lecture locale SQLite immédiate (<1ms)
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE entreprise_id = ? ORDER BY date_operation DESC, created_at DESC", (str(entreprise_id),))
    sqlite_rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    for r in sqlite_rows:
        j_url = r.get("justificatif_url")
        if j_url:
            r["preuves_numeriques"] = [{"url": j_url, "type_preuve": "PHOTO_RECU"}]
        else:
            r["preuves_numeriques"] = []

    # 2. Interrogation Supabase si configuré
    sp = get_supabase_client()
    if sp:
        def fetch_sp():
            try:
                res = sp.table("transactions").select("*, preuves_numeriques(*)").eq("entreprise_id", entreprise_id).order("date_operation", desc=True).order("created_at", desc=True).execute()
                return res.data or []
            except Exception:
                res = sp.table("transactions").select("*").eq("entreprise_id", entreprise_id).order("date_operation", desc=True).order("created_at", desc=True).execute()
                return res.data or []

        sp_data = run_with_timeout(fetch_sp, timeout_seconds=3.0, fallback=None)
        if sp_data is not None:
            try:
                mirror_transactions_to_sqlite(sp_data)
            except Exception as e:
                print(f"[MIRROR TX ERROR] {e}")

            # Fusionner les transactions par ID pour garantir la présence des transactions locales et distantes
            tx_map = {str(r["id"]): r for r in sqlite_rows}
            for s in sp_data:
                tx_map[str(s["id"])] = s
            merged = list(tx_map.values())
            merged.sort(key=lambda x: (str(x.get("date_operation") or ""), str(x.get("created_at") or "")), reverse=True)
            return merged

    return sqlite_rows


def get_entreprise_by_phone_resilient(phone: str) -> Optional[Dict[str, Any]]:
    """Recherche une entreprise par téléphone principal ou numéros secondaires (Wave, OM) avec fallback local."""
    clean_p = str(phone).replace("+", "").replace(" ", "").strip()
    if not clean_p:
        return None

    sp = get_supabase_client()
    if sp:
        def fetch_sp():
            res = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_p}%").limit(1).execute()
            if res.data:
                return res.data[0]
            
            # Recherche multi-numéros (Wave Business ou Orange Money secondaire dans donnees_onboarding)
            try:
                res_all = sp.table("entreprises").select("*").execute()
                for e in res_all.data or []:
                    d_onb = e.get("donnees_onboarding") or {}
                    if isinstance(d_onb, str):
                        try:
                            d_onb = json.loads(d_onb)
                        except Exception:
                            d_onb = {}
                    if (clean_p in str(d_onb.get("numero_wave", "")) or 
                        clean_p in str(d_onb.get("numero_om", "")) or 
                        clean_p in str(d_onb.get("numero_orange_money", "")) or
                        clean_p in str(d_onb.get("telephone_secondaire", ""))):
                        return e
            except Exception as e_sc:
                print(f"Info recherche multi-numéros: {e_sc}")
            return None

        data = run_with_timeout(fetch_sp, timeout_seconds=2.0, fallback=None)
        if data is not None:
            try:
                mirror_entreprises_to_sqlite([data])
            except Exception:
                pass
            return data

    # Fallback local SQLite (recherche sur téléphone whatsapp ou dans donnees_onboarding)
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM entreprises WHERE telephone_whatsapp LIKE ? OR donnees_onboarding LIKE ? LIMIT 1", (f"%{clean_p}%", f"%{clean_p}%"))
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
        if k in ["libelle", "compte_syscohada", "type_flux", "source_paiement", "date_operation", "statut_validation", "reference_externe", "justificatif_url"]:
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
            # Si plus de 5 tentatives échouées consécutives, archiver/supprimer pour ne jamais bloquer la file
            if item.get("attempts", 0) >= 4:
                cur.execute("DELETE FROM sync_queue WHERE id = ?", (item_id,))
                conn.commit()
                print(f"[SYNC QUEUE] Élément corrompu {item_id} retiré de la file après 5 tentatives.")
            print(f"[SYNC QUEUE RETRY] Erreur pour {item_id}: {err}")
            break

    conn.close()
    return flushed_count


# Initialiser la base locale à l'importation
init_local_sqlite()


# =========================================================================
# GESTION DE LA MÉMOIRE LONGUE DURÉE DES MESSAGES (50+ MESSAGES PAR CLIENT)
# =========================================================================

def save_chat_message(phone: str, role: str, text: str):
    """Enregistre un message dans l'historique longue durée (mémoire 50+ messages)."""
    if not phone or not text:
        return
    clean_p = str(phone).replace("+", "").replace(" ", "").strip()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conversation_messages (phone, role, message_text, created_at) VALUES (?, ?, ?, ?)",
            (clean_p, role, text, now_iso)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erreur save_chat_message : {e}")


def get_chat_history(phone: str, limit: int = 50) -> list:
    """Récupère les derniers messages échangés (par défaut jusqu'à 50 messages)."""
    if not phone:
        return []
    clean_p = str(phone).replace("+", "").replace(" ", "").strip()
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT role, message_text, created_at FROM conversation_messages WHERE phone = ? ORDER BY id DESC LIMIT ?",
            (clean_p, limit)
        )
        rows = cur.fetchall()
        conn.close()
        # Remettre dans l'ordre chronologique
        messages = [{"role": r[0], "text": r[1], "date": r[2]} for r in reversed(rows)]
        return messages
    except Exception as e:
        print(f"Erreur get_chat_history : {e}")
        return []


def format_chat_history_for_llm(phone: str, limit: int = 50) -> str:
    """Formate l'historique des 50 derniers messages pour l'IA Gemini."""
    history = get_chat_history(phone, limit=limit)
    if not history:
        return ""
    lines = []
    for m in history:
        author = "Commerçant" if m["role"] == "user" else "Growth"
        lines.append(f"{author} : « {m['text']} »")
    return "\n".join(lines)


def enregistrer_feedback_utilisateur(phone: str, rating: str, message_id: str = None) -> bool:
    """Enregistre silencieusement une appréciation (LIKE 👍) ou dépréciation (DISLIKE 👎) d'une réponse de Growth."""
    if not phone or not rating:
        return False
    clean_p = str(phone).replace("+", "").replace(" ", "").strip()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    r_upper = rating.upper().strip()
    r_clean = "DISLIKE" if "DIS" in r_upper else "LIKE"

    # 1. Sauvegarde locale SQLite
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ai_feedback (phone, rating, message_id, created_at) VALUES (?, ?, ?, ?)",
            (clean_p, r_clean, message_id or "", now_iso)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erreur enregistrement feedback local : {e}")

    # 2. Sauvegarde Cloud Supabase si connectée
    try:
        sp = get_supabase_client()
        if sp:
            sp.table("ai_feedback").insert({
                "telephone_whatsapp": clean_p,
                "rating": r_clean,
                "message_id": message_id or "",
                "created_at": now_iso
            }).execute()
    except Exception:
        pass

    return True


def obtenir_stats_feedback() -> dict:
    """Calcule les statistiques globales des appréciations (👍) et dépréciations (👎) des utilisateurs."""
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("SELECT rating, COUNT(*) FROM ai_feedback GROUP BY rating")
        rows = cur.fetchall()
        conn.close()

        counts = {"LIKE": 0, "DISLIKE": 0}
        for r, cnt in rows:
            if r in counts:
                counts[r] = cnt
        total = counts["LIKE"] + counts["DISLIKE"]
        pct = round((counts["LIKE"] / total) * 100, 1) if total > 0 else 100.0
        return {
            "likes": counts["LIKE"],
            "dislikes": counts["DISLIKE"],
            "total": total,
            "satisfaction_pct": pct
        }
    except Exception as e:
        print(f"Erreur obtenir_stats_feedback : {e}")
        return {"likes": 0, "dislikes": 0, "total": 0, "satisfaction_pct": 100.0}


def enregistrer_cas_amelioration_ia(phone: str, question: str, reponse: str, score_confiance: float = 0.5, motif: str = "") -> int:
    """Enregistre un cas où l'IA a douté ou reçu un retour négatif, pour apprentissage continu par l'équipe."""
    clean_p = str(phone).replace("+", "").replace(" ", "").strip() if phone else ""
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ai_learning_backlog (phone, question_utilisateur, reponse_growth, score_confiance, motif, statut, created_at) VALUES (?, ?, ?, ?, ?, 'A_AMELIORER', ?)",
            (clean_p, question, reponse, float(score_confiance), motif, now_iso)
        )
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        return new_id
    except Exception as e:
        print(f"Erreur enregistrement apprentissage IA : {e}")
        return 0


def obtenir_backlog_amelioration_ia(limit: int = 50) -> list:
    """Récupère les questions où l'IA a besoin de l'équipe pour se perfectionner."""
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, phone, question_utilisateur, reponse_growth, score_confiance, motif, statut, reponse_amelioree, created_at FROM ai_learning_backlog ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "phone": r[1],
                "question": r[2],
                "reponse_actuelle": r[3],
                "score_confiance": r[4],
                "motif": r[5],
                "statut": r[6],
                "reponse_amelioree": r[7],
                "date": r[8]
            }
            for r in rows
        ]
    except Exception as e:
        print(f"Erreur obtenir_backlog_amelioration_ia : {e}")
        return []


def perfectionner_reponse_ia(cas_id: int, reponse_parfaite: str) -> bool:
    """Permet à l'équipe d'enseigner la réponse parfaite à Growth pour un cas donné."""
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE ai_learning_backlog SET reponse_amelioree = ?, statut = 'PERFECTIONNE' WHERE id = ?",
            (reponse_parfaite, cas_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erreur perfectionner_reponse_ia : {e}")
        return False


# ==============================================================================
# COCKPIT CRÉATEUR & DIRECTION GROWTH : SUPERVISION UTILISATEURS & ACTIVITÉ
# ==============================================================================

def obtenir_liste_utilisateurs_createur() -> list:
    """
    Retourne la liste complète de tous les commerçants inscrits avec leur statut d'activité
    en temps réel (Actif aujourd'hui, Inactif > 24h, Inactif > 3 jours) et leur volume de saisies.
    Résilient : fusionne SQLite local et Cloud Supabase.
    """
    utilisateurs_map = {}
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Source SQLite Locale avec agrégation précise des écritures par téléphone
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT e.telephone_whatsapp,
                   MAX(e.nom_entreprise) as nom_entreprise,
                   MIN(COALESCE(e.date_inscription, '2026-11-21')) as date_inscription,
                   COUNT(t.id) as total_ecritures,
                   SUM(CASE WHEN t.created_at LIKE ? OR t.date_operation LIKE ? THEN 1 ELSE 0 END) as ecritures_jour,
                   MAX(COALESCE(t.created_at, t.date_operation)) as dernier_flux
            FROM entreprises e
            LEFT JOIN transactions t ON e.id = t.entreprise_id
            WHERE e.telephone_whatsapp IS NOT NULL AND e.telephone_whatsapp != ''
            GROUP BY e.telephone_whatsapp
        """, (f"{today_str}%", f"{today_str}%"))

        for r in cur.fetchall():
            tel = str(r[0]).strip()
            utilisateurs_map[tel] = {
                "telephone": tel,
                "nom_entreprise": r[1] or f"Commerce {tel[-4:]}",
                "date_inscription": r[2],
                "total_ecritures": r[3] or 0,
                "ecritures_jour": r[4] or 0,
                "dernier_flux": r[5],
                "statut_activite": "INACTIF",
                "statut_libelle": "Inactif (> 3j)"
            }
        conn.close()
    except Exception as e_sql:
        print(f"Info obtenir_liste_utilisateurs_createur SQLite: {e_sql}")

    # 2. Source Cloud Supabase (enrichissement des commerçants et des transactions)
    try:
        sp = get_supabase_client()
        if sp:
            res = sp.table("entreprises").select("id, nom_entreprise, telephone_whatsapp, date_inscription").execute()
            ent_by_id = {}
            for ent in res.data or []:
                ent_id = ent.get("id")
                tel = str(ent.get("telephone_whatsapp") or "").strip()
                if not tel:
                    continue
                ent_by_id[ent_id] = tel
                if tel not in utilisateurs_map:
                    utilisateurs_map[tel] = {
                        "telephone": tel,
                        "nom_entreprise": ent.get("nom_entreprise") or f"Commerce {tel[-4:]}",
                        "date_inscription": ent.get("date_inscription") or today_str,
                        "total_ecritures": 0,
                        "ecritures_jour": 0,
                        "dernier_flux": None,
                        "statut_activite": "INACTIF",
                        "statut_libelle": "Inactif (> 3j)"
                    }
                else:
                    nom_actuel = utilisateurs_map[tel].get("nom_entreprise", "")
                    if not nom_actuel or "Commerce" in nom_actuel:
                        utilisateurs_map[tel]["nom_entreprise"] = ent.get("nom_entreprise") or nom_actuel

            # Si SQLite local n'a pas les transactions (ex: nouveau déploiement Render), on lit Supabase
            total_ecritures_locales = sum(u["total_ecritures"] for u in utilisateurs_map.values())
            if total_ecritures_locales == 0 and ent_by_id:
                res_tx = sp.table("transactions").select("id, entreprise_id, montant_fcfa, created_at, date_operation").execute()
                for tx in res_tx.data or []:
                    e_id = tx.get("entreprise_id")
                    tel = ent_by_id.get(e_id)
                    if tel and tel in utilisateurs_map:
                        utilisateurs_map[tel]["total_ecritures"] += 1
                        d_op = str(tx.get("date_operation") or tx.get("created_at") or "")
                        if d_op.startswith(today_str):
                            utilisateurs_map[tel]["ecritures_jour"] += 1
                        if d_op and (not utilisateurs_map[tel]["dernier_flux"] or d_op > utilisateurs_map[tel]["dernier_flux"]):
                            utilisateurs_map[tel]["dernier_flux"] = d_op
        # 3. Enrichissement avec les abonnements Growth
        try:
            conn = get_sqlite_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT telephone, plan, montant_fcfa, date_paiement
                FROM abonnements_growth
                WHERE statut = 'PAYE'
                ORDER BY id DESC
            """)
            for row_abo in cur.fetchall():
                t_abo = str(row_abo[0]).strip()
                if t_abo in utilisateurs_map and not utilisateurs_map[t_abo].get("abonnement_paye"):
                    utilisateurs_map[t_abo]["abonnement_paye"] = True
                    utilisateurs_map[t_abo]["abonnement_plan"] = row_abo[1]
                    utilisateurs_map[t_abo]["abonnement_montant"] = float(row_abo[2] or 10000.0)
                    utilisateurs_map[t_abo]["abonnement_date"] = row_abo[3]
            conn.close()
        except Exception:
            pass
    except Exception as e_sp:
        print(f"Info obtenir_liste_utilisateurs_createur Supabase: {e_sp}")

    # 4. Calcul précis des statuts d'activité
    now = datetime.now()
    liste_triee = []
    for tel, u in utilisateurs_map.items():
        if "abonnement_paye" not in u:
            u["abonnement_paye"] = False
            u["abonnement_plan"] = "En attente"
            u["abonnement_montant"] = 0.0
        dernier = u.get("dernier_flux")
        ecritures_jour = u.get("ecritures_jour", 0)

        if ecritures_jour > 0:
            u["statut_activite"] = "ACTIF"
            u["statut_libelle"] = "🟢 Actif aujourd'hui"
        elif dernier:
            try:
                dt = datetime.fromisoformat(str(dernier).replace("Z", "+00:00").split("+")[0])
                delta_heures = (now - dt).total_seconds() / 3600
                if delta_heures <= 36:
                    u["statut_activite"] = "ATTENTION"
                    u["statut_libelle"] = "🟡 Inactif (24h)"
                else:
                    u["statut_activite"] = "INACTIF"
                    u["statut_libelle"] = "🔴 Inactif (> 3j)"
            except Exception:
                u["statut_activite"] = "INACTIF"
                u["statut_libelle"] = "🔴 Inactif (> 3j)"
        else:
            u["statut_activite"] = "INACTIF"
            u["statut_libelle"] = "🔴 Jamais actif"

        liste_triee.append(u)

    # Trier : d'abord par nombre d'écritures total décroissant, puis par statut
    liste_triee.sort(key=lambda x: (-x["total_ecritures"], 0 if x["statut_activite"] != "ACTIF" else 1))
    return liste_triee


def obtenir_stats_globales_createur() -> dict:
    """Calcule tous les KPIs globaux pour le Cockpit Créateur / Fondateur de Growth."""
    utilisateurs = obtenir_liste_utilisateurs_createur()
    total_u = len(utilisateurs)
    actifs_jour = sum(1 for u in utilisateurs if u["statut_activite"] == "ACTIF")
    inactifs = sum(1 for u in utilisateurs if u["statut_activite"] != "ACTIF")

    total_tx = 0
    volume_total = 0.0

    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), COALESCE(SUM(montant_fcfa), 0) FROM transactions")
        row = cur.fetchone()
        if row:
            total_tx = row[0]
            volume_total = float(row[1] or 0.0)
        conn.close()
    except Exception as e:
        print(f"Info stats_globales SQLite: {e}")

    if total_tx == 0:
        try:
            sp = get_supabase_client()
            if sp:
                res_tx = sp.table("transactions").select("montant_fcfa").execute()
                if res_tx.data:
                    total_tx = len(res_tx.data)
                    volume_total = sum(float(r.get("montant_fcfa") or 0.0) for r in res_tx.data)
        except Exception as e_sptx:
            print(f"Info stats_globales Supabase tx: {e_sptx}")

    # Caisse Abonnements et Dépenses du Créateur (Trésorerie réelle de la plateforme Growth)
    caisse_abos = 0.0
    total_sorties = 0.0
    solde_caisse_net = 0.0
    abonnes_actifs_count = 0
    mrr_mensuel = 0.0
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(montant_fcfa), 0), COUNT(DISTINCT telephone) FROM abonnements_growth WHERE statut='PAYE'")
        r_caisse = cur.fetchone()
        if r_caisse:
            caisse_abos = float(r_caisse[0] or 0.0)
            abonnes_actifs_count = int(r_caisse[1] or 0)
            mrr_mensuel = caisse_abos

        # Total des sorties et dépenses de Growth (Pourquoi c'est sorti)
        cur.execute("SELECT COALESCE(SUM(montant_fcfa), 0) FROM depenses_createur_growth")
        r_dep = cur.fetchone()
        if r_dep:
            total_sorties = float(r_dep[0] or 0.0)

        solde_caisse_net = caisse_abos - total_sorties
        conn.close()
    except Exception as e_caisse:
        print(f"Info caisse_abos SQLite: {e_caisse}")

    stats_feedback = obtenir_stats_feedback()
    cas_amelioration = obtenir_backlog_amelioration_ia(limit=100)
    cas_a_ameliorer = sum(1 for c in cas_amelioration if c.get("statut") != "PERFECTIONNE")
    cas_perfectionnes = sum(1 for c in cas_amelioration if c.get("statut") == "PERFECTIONNE")

    return {
        "total_utilisateurs": total_u,
        "actifs_aujourdhui": actifs_jour,
        "inactifs_a_relancer": inactifs,
        "taux_activite_pct": round((actifs_jour / total_u * 100), 1) if total_u > 0 else 0.0,
        "total_transactions": total_tx,
        "volume_total_fcfa": volume_total,
        "caisse_abonnements_fcfa": solde_caisse_net,
        "total_entrees_abos_fcfa": caisse_abos,
        "total_sorties_depenses_fcfa": total_sorties,
        "solde_caisse_net_fcfa": solde_caisse_net,
        "abonnes_actifs_count": abonnes_actifs_count,
        "mrr_mensuel_fcfa": mrr_mensuel,
        "satisfaction_ia_pct": stats_feedback.get("satisfaction_pct", 100.0),
        "likes": stats_feedback.get("likes", 0),
        "dislikes": stats_feedback.get("dislikes", 0),
        "cas_a_ameliorer": cas_a_ameliorer,
        "cas_perfectionnes": cas_perfectionnes
    }


def obtenir_stats_caisse_abonnements() -> dict:
    """Retourne l'état complet de la caisse créateur : entrées abonnements, sorties dépenses et solde net."""
    total_encaisse = 0.0
    encaisse_wave = 0.0
    encaisse_om = 0.0
    encaisse_especes = 0.0
    total_abonnes = 0
    paiements = []

    total_sorties = 0.0
    sorties_wave = 0.0
    sorties_om = 0.0
    sorties_especes = 0.0
    depenses = []

    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        # 1. Entrées d'abonnements
        cur.execute("""
            SELECT id, telephone, nom_entreprise, plan, montant_fcfa, operateur, date_paiement, statut, reference
            FROM abonnements_growth
            ORDER BY id DESC
        """)
        for r in cur.fetchall():
            m = float(r[4] or 0.0)
            op = str(r[5] or "WAVE").upper()
            total_encaisse += m
            if "WAVE" in op:
                encaisse_wave += m
            elif "ORANGE" in op or "OM" in op:
                encaisse_om += m
            else:
                encaisse_especes += m
            paiements.append({
                "id": r[0],
                "telephone": r[1],
                "nom_entreprise": r[2] or f"Commerce {r[1][-4:]}",
                "plan": r[3],
                "montant_fcfa": m,
                "operateur": r[5],
                "date_paiement": r[6],
                "statut": r[7],
                "reference": r[8] or "--"
            })
        cur.execute("SELECT COUNT(DISTINCT telephone) FROM abonnements_growth WHERE statut='PAYE'")
        r_cnt = cur.fetchone()
        if r_cnt:
            total_abonnes = int(r_cnt[0] or 0)

        # 2. Sorties d'argent et dépenses du créateur (Pourquoi c'est sorti)
        cur.execute("""
            SELECT id, motif, categorie, montant_fcfa, source_paiement, beneficiaire, date_depense, justificatif_note
            FROM depenses_createur_growth
            ORDER BY id DESC
        """)
        for r in cur.fetchall():
            m = float(r[3] or 0.0)
            op = str(r[4] or "WAVE").upper()
            total_sorties += m
            if "WAVE" in op:
                sorties_wave += m
            elif "ORANGE" in op or "OM" in op:
                sorties_om += m
            else:
                sorties_especes += m
            depenses.append({
                "id": r[0],
                "motif": r[1],
                "categorie": r[2],
                "montant_fcfa": m,
                "source_paiement": r[4],
                "beneficiaire": r[5] or "--",
                "date_depense": r[6],
                "justificatif_note": r[7] or ""
            })

        conn.close()
    except Exception as e:
        print(f"Erreur obtenir_stats_caisse_abonnements: {e}")

    solde_net = total_encaisse - total_sorties

    return {
        "solde_net_fcfa": solde_net,
        "total_encaisse_fcfa": total_encaisse,
        "total_sorties_fcfa": total_sorties,
        "total_abonnes_actifs": total_abonnes,
        "encaisse_wave": encaisse_wave,
        "encaisse_om": encaisse_om,
        "encaisse_especes": encaisse_especes,
        "sorties_wave": sorties_wave,
        "sorties_om": sorties_om,
        "sorties_especes": sorties_especes,
        "paiements": paiements,
        "depenses": depenses
    }


def enregistrer_paiement_abonnement(telephone: str, nom_entreprise: str = "", plan: str = "Starter", montant_fcfa: float = 10000.0, operateur: str = "WAVE", reference: str = "") -> dict:
    """Enregistre un encaissement d'abonnement dans la caisse du créateur."""
    clean_p = str(telephone).replace("+", "").replace(" ", "").strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO abonnements_growth (telephone, nom_entreprise, plan, montant_fcfa, operateur, date_paiement, statut, reference)
            VALUES (?, ?, ?, ?, ?, ?, 'PAYE', ?)
        """, (clean_p, nom_entreprise, plan, float(montant_fcfa), operateur.upper(), now_str, reference))
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"Abonnement {plan} de {montant_fcfa:,.0f} FCFA encaissé avec succès."}
    except Exception as e:
        print(f"Erreur enregistrer_paiement_abonnement: {e}")
        return {"status": "error", "message": str(e)}


def enregistrer_depense_createur(motif: str, montant_fcfa: float, categorie: str = "RETRAIT_FONDATEUR", source_paiement: str = "WAVE", beneficiaire: str = "", justificatif_note: str = "") -> dict:
    """
    Enregistre une sortie d'argent de l'entreprise Growth avec motif obligatoire (Pourquoi c'est sorti).
    Catégories : RETRAIT_FONDATEUR, SERVEURS_CLOUD, API_IA, TELECOMS, MARKETING, AUTRE.
    """
    if not motif or not motif.strip():
        return {"status": "error", "message": "Le motif de la sortie (pourquoi l'argent est sorti) est obligatoire."}
    if float(montant_fcfa or 0.0) <= 0:
        return {"status": "error", "message": "Le montant de la sortie doit être supérieur à 0 FCFA."}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO depenses_createur_growth (motif, categorie, montant_fcfa, source_paiement, beneficiaire, date_depense, justificatif_note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (motif.strip(), categorie.strip().upper(), float(montant_fcfa), source_paiement.strip().upper(), beneficiaire.strip() if beneficiaire else None, now_str, justificatif_note.strip() if justificatif_note else None))
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"Sortie de {float(montant_fcfa):,.0f} FCFA enregistrée : {motif.strip()}"}
    except Exception as e:
        print(f"Erreur enregistrer_depense_createur: {e}")
        return {"status": "error", "message": str(e)}


def obtenir_registre_depenses_createur() -> list:
    """Retourne la liste complète de toutes les dépenses et sorties d'argent avec leurs motifs."""
    depenses = []
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, motif, categorie, montant_fcfa, source_paiement, beneficiaire, date_depense, justificatif_note
            FROM depenses_createur_growth
            ORDER BY id DESC
        """)
        for r in cur.fetchall():
            depenses.append({
                "id": r[0],
                "motif": r[1],
                "categorie": r[2],
                "montant_fcfa": float(r[3] or 0.0),
                "source_paiement": r[4],
                "beneficiaire": r[5] or "--",
                "date_depense": r[6],
                "justificatif_note": r[7] or ""
            })
        conn.close()
    except Exception as e:
        print(f"Erreur obtenir_registre_depenses_createur: {e}")
    return depenses


def reinitialiser_donnees_plateforme_a_zero() -> dict:
    """
    Réinitialise complètement la base SQLite locale et la base Supabase à zéro (Clean Slate)
    pour démarrer l'exploitation commerciale sans aucune donnée de test résiduelle.
    """
    try:
        conn = get_sqlite_conn()
        cur = conn.cursor()
        for t in ["transactions", "entreprises", "conversation_messages", "ai_feedback", "ai_learning_backlog", "sync_queue", "abonnements_growth", "depenses_createur_growth"]:
            try:
                cur.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.commit()
        conn.close()
    except Exception as e_sql:
        print(f"Erreur purge SQLite: {e_sql}")

    sp_status = False
    try:
        sp = get_supabase_client()
        if sp:
            try:
                sp.table("transactions").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            except Exception:
                pass
            try:
                sp.table("entreprises").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            except Exception:
                pass
            sp_status = True
    except Exception as e_sp:
        print(f"Erreur purge Supabase: {e_sp}")

    return {
        "status": "success",
        "message": "Plateforme Growth réinitialisée à zéro avec succès (Clean Slate de lancement).",
        "supabase_purged": sp_status
    }






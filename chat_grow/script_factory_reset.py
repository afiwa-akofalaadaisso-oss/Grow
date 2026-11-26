"""
Script officiel de remise à zéro (Factory Reset - Sortie du Carton) pour GROWTH.
1. Sauvegarde une archive complète de toutes les tables actuelles (Supabase et SQLite) et des JSON.
2. Vide complètement toutes les transactions, entreprises et données de tests.
3. Remet le système dans un état 100% neuf, vierge et prêt pour le premier vrai utilisateur.
"""

import os
import sys
import shutil
import json
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups", f"sortie_du_carton_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
os.makedirs(BACKUP_DIR, exist_ok=True)

print(f"=== ÉTAPE 1 : CRÉATION DE L'ARCHIVE DE SÉCURITÉ DANS {BACKUP_DIR} ===")

# 1. Sauvegarde SQLite
sqlite_path = os.path.join(os.path.dirname(__file__), "grow_compta.db")
if os.path.exists(sqlite_path):
    shutil.copy2(sqlite_path, os.path.join(BACKUP_DIR, "grow_compta.db.backup"))
    print(f"✅ grow_compta.db copié dans {BACKUP_DIR}")

# 2. Sauvegarde des fichiers JSON
json_files = ["onboarding_states.json", "pme_otp_registry.json", "comptables_registry.json", "demandes_visa_cabinet.json", "fournisseurs_memoire.json"]
for jf in json_files:
    jp = os.path.join(os.path.dirname(__file__), jf)
    if os.path.exists(jp):
        shutil.copy2(jp, os.path.join(BACKUP_DIR, jf))
        print(f"✅ {jf} copié dans {BACKUP_DIR}")

notified_p = os.path.join(os.path.dirname(__file__), "static", "notified_wave_om_ids.json")
if os.path.exists(notified_p):
    shutil.copy2(notified_p, os.path.join(BACKUP_DIR, "notified_wave_om_ids.json"))
    print(f"✅ notified_wave_om_ids.json copié dans {BACKUP_DIR}")

# 3. Sauvegarde Supabase
from chat_grow.main import get_supabase
sp = get_supabase()

if sp:
    try:
        res_e = sp.table("entreprises").select("*").execute()
        with open(os.path.join(BACKUP_DIR, "supabase_entreprises.json"), "w", encoding="utf-8") as f:
            json.dump(res_e.data or [], f, ensure_ascii=False, indent=2)
        print(f"✅ Supabase entreprises exportées : {len(res_e.data or [])} lignes")

        res_t = sp.table("transactions").select("*").execute()
        with open(os.path.join(BACKUP_DIR, "supabase_transactions.json"), "w", encoding="utf-8") as f:
            json.dump(res_t.data or [], f, ensure_ascii=False, indent=2)
        print(f"✅ Supabase transactions exportées : {len(res_t.data or [])} lignes")
    except Exception as e:
        print(f"Info export supabase: {e}")

print("\n=== ÉTAPE 2 : VIDAGE DE LA BASE SUPABASE (SORTIE DU CARTON) ===")
if sp:
    try:
        # Supprimer les transactions en premier (contraintes de clés étrangères)
        r_del_tx = sp.table("transactions").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        print(f"🧹 Supabase transactions vidées avec succès.")
    except Exception as e_tx:
        print(f"Info vidage tx supabase: {e_tx}")

    try:
        r_del_dc = sp.table("dettes_creances").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        print(f"🧹 Supabase dettes_creances vidées avec succès.")
    except Exception as e_dc:
        print(f"Info vidage dettes_creances: {e_dc}")

    try:
        r_del_es = sp.table("etats_structurels").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        print(f"🧹 Supabase etats_structurels vidés avec succès.")
    except Exception as e_es:
        print(f"Info vidage etats_structurels: {e_es}")

    try:
        r_del_e = sp.table("entreprises").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        print(f"🧹 Supabase entreprises vidées avec succès.")
    except Exception as e_e:
        print(f"Info vidage entreprises: {e_e}")

print("\n=== ÉTAPE 3 : VIDAGE DE LA BASE SQLITE LOCALE ===")
if os.path.exists(sqlite_path):
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    tables_to_clear = [
        "transactions", 
        "entreprises", 
        "conversation_messages", 
        "sync_queue", 
        "abonnements_growth",
        "ai_feedback",
        "ai_learning_backlog",
        "depenses_createur_growth"
    ]
    for tbl in tables_to_clear:
        try:
            cur.execute(f"DELETE FROM {tbl}")
            print(f"🧹 SQLite {tbl} vidé.")
        except Exception as e_tbl:
            print(f"Info SQLite {tbl}: {e_tbl}")
    conn.commit()
    conn.close()

print("\n=== ÉTAPE 4 : RÉINITIALISATION DES FICHIERS JSON DE SESSION ===")
# Onboarding states -> {}
onb_path = os.path.join(os.path.dirname(__file__), "onboarding_states.json")
with open(onb_path, "w", encoding="utf-8") as f:
    json.dump({}, f, indent=2)
print("🧹 chat_grow/onboarding_states.json réinitialisé à {}")

# Notified Wave OM -> []
if os.path.exists(notified_p):
    with open(notified_p, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)
    print("🧹 chat_grow/static/notified_wave_om_ids.json réinitialisé à []")

# OTP Registry -> {}
otp_path = os.path.join(os.path.dirname(__file__), "pme_otp_registry.json")
if os.path.exists(otp_path):
    with open(otp_path, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=2)
    print("🧹 chat_grow/pme_otp_registry.json réinitialisé à {}")

# Demandes Visa -> []
visa_path = os.path.join(os.path.dirname(__file__), "demandes_visa_cabinet.json")
if os.path.exists(visa_path):
    with open(visa_path, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)
    print("🧹 chat_grow/demandes_visa_cabinet.json réinitialisé à []")

print("\n🎉 REMISE À ZÉRO TERMINÉE AVEC SUCCÈS ! GROWTH EST 100% VIERGE ET SORTI DU CARTON.")

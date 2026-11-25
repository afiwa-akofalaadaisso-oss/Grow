"""
Growth — Module des Réalités de Terrain des PME Ouest-Africaines (Sénégal / UEMOA)

Prend en compte les vrais défis quotidiens des commerçants :
1. Séparation Argent Popote / Famille vs Caisse Boutique (Compte 108 de l'exploitant)
2. Gestion des Acomptes et Règlements par Tranches (« Dama lay fay par tranche »)
3. Émission Instantanée de Reçus Numériques WhatsApp pour les Clients
4. Suivi des Dettes Grossistes / Fournisseurs Marché (Compte 401)
5. Point de Stock Express au Dictaphone (Inventaire physique valorisé)
6. Réserve Virtuelle de Trésorerie pour le Loyer du Magasin & Woyofal Senelec
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

POPOTE_DB_FILE = os.path.join(os.path.dirname(__file__), "popote_depenses.json")
FOURNISSEURS_DB_FILE = os.path.join(os.path.dirname(__file__), "dettes_fournisseurs.json")


def _load_json(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_json(path: str, data: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[PME REALITES] Erreur sauvegarde {path}: {e}")


# ==============================================================================
# 1. COMPARTIMENT POPOTE & DÉPENSES PERSONNELLES (COMPTE SYSCOHADA 108)
# ==============================================================================

def enregistrer_prelevement_popote(phone: str, montant_fcfa: int, motif: str = "Popote / Famille") -> dict:
    """Enregistre un prélèvement personnel de l'exploitant sans fausser la rentabilité de la boutique."""
    clean_p = re.sub(r"\D", "", str(phone))
    db = _load_json(POPOTE_DB_FILE)
    if clean_p not in db:
        db[clean_p] = []

    mois_courant = datetime.now().strftime("%m/%Y")
    entry = {
        "id": f"pop_{int(datetime.now().timestamp())}",
        "montant": int(montant_fcfa),
        "motif": motif.strip(),
        "date": datetime.now().strftime("%d/%m/%Y à %H:%M"),
        "mois": mois_courant,
        "compte_syscohada": "108000 (Compte de l'Exploitant - Prélèvements Personnels)"
    }
    db[clean_p].append(entry)
    _save_json(POPOTE_DB_FILE, db)

    # Calcul du cumul du mois
    cumul_mois = sum(e.get("montant", 0) for e in db[clean_p] if e.get("mois") == mois_courant)
    return {
        "entry": entry,
        "cumul_mois": cumul_mois,
        "nb_prelevements": len([e for e in db[clean_p] if e.get("mois") == mois_courant])
    }


def obtenir_bilan_popote_mois(phone: str) -> dict:
    clean_p = re.sub(r"\D", "", str(phone))
    db = _load_json(POPOTE_DB_FILE)
    mois_courant = datetime.now().strftime("%m/%Y")
    entries = [e for e in db.get(clean_p, []) if e.get("mois") == mois_courant]
    total = sum(e.get("montant", 0) for e in entries)
    return {"total": total, "entries": entries, "mois": mois_courant}


# ==============================================================================
# 2. GESTION DES ACOMPTES ET RÈGLEMENTS PAR TRANCHES
# ==============================================================================

def traiter_acompte_client(phone: str, client_nom: str, montant_acompte: int) -> dict:
    """Déduit un acompte d'une dette client existante ou crée un versement partiel."""
    from chat_grow.whatsapp_features import load_credits_db, save_credits_db
    clean_p = re.sub(r"\D", "", str(phone))
    db = load_credits_db()
    credits = db.get(clean_p, [])

    client_clean = client_nom.lower().strip()
    credit_trouve = None

    for c in credits:
        if client_clean in c.get("client", "").lower() and c.get("statut") == "NON_PAYE":
            credit_trouve = c
            break

    if credit_trouve:
        solde_initial = credit_trouve.get("montant", 0)
        nouveau_solde = max(0, solde_initial - int(montant_acompte))
        credit_trouve["montant"] = nouveau_solde
        if nouveau_solde == 0:
            credit_trouve["statut"] = "SOLDE_TOTAL"
        save_credits_db(db)
        return {
            "trouve": True,
            "client": credit_trouve.get("client"),
            "acompte": montant_acompte,
            "solde_initial": solde_initial,
            "reste_du": nouveau_solde,
            "est_solde": nouveau_solde == 0
        }
    else:
        return {
            "trouve": False,
            "client": client_nom.title(),
            "acompte": montant_acompte
        }


# ==============================================================================
# 3. REÇU CLIENT NUMÉRIQUE WHATSAPP EN 1 CLIC
# ==============================================================================

def generer_recu_client_whatsapp(
    nom_boutique: str,
    client_nom: str,
    articles_libelle: str,
    montant_total: int,
    mode_paiement: str = "WAVE / ESPÈCES",
    numero_recu: str = None
) -> str:
    """Génère un reçu de caisse numérique officiel prêt à transférer au client sur WhatsApp."""
    date_jour = datetime.now().strftime("%d/%m/%Y à %H:%M")
    num_recu = numero_recu or f"REC-{datetime.now().strftime('%y%m%d')}-{abs(hash(articles_libelle + str(montant_total))) % 1000:03d}"
    montant_fmt = f"{montant_total:,} FCFA".replace(",", " ")

    recu = (
        f"🧾 *REÇU DE PAIEMENT NUMÉRIQUE*\n"
        f"*{nom_boutique.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Date : {date_jour}\n"
        f"🔖 N° Reçu : `{num_recu}`\n"
        f"👤 Client : *{client_nom.title()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Détail des Achats :*\n"
        f"• {articles_libelle}\n\n"
        f"💰 *MONTANT TOTAL PAYÉ : {montant_fmt}*\n"
        f"💳 Mode : {mode_paiement.upper()}\n"
        f"✅ Statut : Règlement Encaissé & Certifié\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🙏 *Merci pour votre confiance ! À très bientôt chez {nom_boutique}.*"
    )
    return recu


# ==============================================================================
# 4. GESTION DES DETTES GROSSISTES / FOURNISSEURS (COMPTE SYSCOHADA 401)
# ==============================================================================

def enregistrer_dette_fournisseur(
    phone: str,
    fournisseur_nom: str,
    montant_fcfa: int,
    marchandises: str = "",
    date_echeance: str = "Fin de mois"
) -> dict:
    """Enregistre un achat de stock à crédit auprès d'un grossiste du marché."""
    clean_p = re.sub(r"\D", "", str(phone))
    db = _load_json(FOURNISSEURS_DB_FILE)
    if clean_p not in db:
        db[clean_p] = []

    dette_entry = {
        "id": f"frn_{int(datetime.now().timestamp())}",
        "grossiste": fournisseur_nom.strip().title(),
        "montant": int(montant_fcfa),
        "marchandises": marchandises.strip() or "Réassort marchandises",
        "date_achat": datetime.now().strftime("%d/%m/%Y"),
        "date_echeance": date_echeance,
        "statut": "A_PAYER",
        "compte_syscohada": "401100 (Dettes Fournisseurs d'Exploitation)"
    }
    db[clean_p].append(dette_entry)
    _save_json(FOURNISSEURS_DB_FILE, db)
    return dette_entry


def obtenir_dettes_fournisseurs(phone: str) -> List[dict]:
    clean_p = re.sub(r"\D", "", str(phone))
    db = _load_json(FOURNISSEURS_DB_FILE)
    return [d for d in db.get(clean_p, []) if d.get("statut") == "A_PAYER"]

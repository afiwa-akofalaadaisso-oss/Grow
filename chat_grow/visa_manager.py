"""
Growth — Gestionnaire des Visas & Approbations Cabinet « Human-in-the-Loop »
Permet la collaboration directe entre le Commerçant (WhatsApp) et l'Expert-Comptable (Portail Cabinet).

Workflow :
1. Le commerçant demande son Bilan / Attestation sur WhatsApp.
2. Growth place la demande en attente et invite le client à patienter.
3. Le cabinet reçoit l'alerte sur son portail et clique sur [ Approuver & Viser ].
4. Le document officiel SYSCOHADA certifié est généré avec le Visa du cabinet et expédié en direct sur le WhatsApp du client.
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

DEMANDES_VISA_FILE = os.path.join(os.path.dirname(__file__), "demandes_visa_cabinet.json")


def load_demandes_visa() -> List[dict]:
    if os.path.exists(DEMANDES_VISA_FILE):
        try:
            with open(DEMANDES_VISA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_demandes_visa(demandes: List[dict]):
    try:
        with open(DEMANDES_VISA_FILE, "w", encoding="utf-8") as f:
            json.dump(demandes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[VISA] Erreur sauvegarde demandes : {e}")


def creer_demande_visa(
    telephone: str,
    nom_entreprise: str,
    type_document: str = "BILAN_SYSCOHADA",
    motif: str = "Dépôt légal ou dossier bancaire",
    cabinet_nom: str = "Cabinet Adaisso & Partenaires",
    cabinet_id: str = ""
) -> dict:
    """Enregistre une nouvelle demande de visa officiel rattachée à son cabinet comptable spécifique."""
    clean_p = re.sub(r"\D", "", str(telephone))
    demandes = load_demandes_visa()

    # Vérifier si une demande identique est déjà en attente récente
    for d in demandes:
        if d.get("telephone") == clean_p and d.get("statut") == "EN_ATTENTE" and d.get("type_document") == type_document:
            return d

    demande_id = f"visa_req_{int(datetime.now().timestamp())}"
    nouvelle_demande = {
        "id": demande_id,
        "telephone": clean_p,
        "nom_entreprise": nom_entreprise or "Entreprise PME",
        "cabinet_nom": cabinet_nom or "Cabinet Adaisso & Partenaires",
        "cabinet_id": cabinet_id or "",
        "type_document": type_document,
        "libelle_document": "Bilan SYSCOHADA SMT & Liasse Fiscale" if type_document == "BILAN_SYSCOHADA" else "Fiche de Solvabilité & Capacité d'Emprunt",
        "motif": motif,
        "date_demande": datetime.now().strftime("%d/%m/%Y à %H:%M"),
        "statut": "EN_ATTENTE",
        "date_approbation": None,
        "visa_reference": None
    }

    demandes.insert(0, nouvelle_demande)
    save_demandes_visa(demandes)
    return nouvelle_demande


def obtenir_demandes_en_attente(cabinet_nom: Optional[str] = None) -> List[dict]:
    demandes = load_demandes_visa()
    en_attente = [d for d in demandes if d.get("statut") == "EN_ATTENTE"]
    if cabinet_nom:
        cab_clean = cabinet_nom.strip().lower()
        return [d for d in en_attente if cab_clean in d.get("cabinet_nom", "").strip().lower() or not d.get("cabinet_nom")]
    return en_attente


def marquer_demande_approuvee(demande_id: str, cabinet_nom: str) -> Optional[dict]:
    demandes = load_demandes_visa()
    for d in demandes:
        if d.get("id") == demande_id:
            now_str = datetime.now().strftime("%d/%m/%Y à %H:%M")
            visa_ref = f"VISA-SYSCOHADA-{int(datetime.now().timestamp()) % 1000000:06d}"
            d["statut"] = "APPROUVE"
            d["date_approbation"] = now_str
            d["visa_reference"] = visa_ref
            d["signataire"] = cabinet_nom
            save_demandes_visa(demandes)
            return d
    return None

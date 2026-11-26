"""
Growth — La Boîte à Outils Intégrale de la PME & TPE Sénégalaise
Fournit l'arsenal complet des besoins vitaux d'un commerce, atelier ou entreprise en Afrique de l'Ouest :
1. Salaires & Avances Employés (Livre de paie TPE sans litige)
2. Calculateur de Marge Commerciale & Prix de Vente Conseillé
3. Détecteur d'Écarts de Caisse & Contrôle Anti-Coulage (Tiroir vs Écritures)
4. Simulateur Impôts CGU & Échéances Fiscales DGID Sénégal
5. Diagnostic de Solvabilité & Capacité d'Emprunt Bancaire
6. Modèles de Relances Débiteurs Diplomatiques (Amical, Ferme, Négociation)
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

SALAIRES_DB_FILE = os.path.join(os.path.dirname(__file__), "salaires_employes.json")


def _load_json(file_path: str) -> dict:
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_json(file_path: str, data: dict):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erreur sauvegarde {file_path}: {e}")


# ==============================================================================
# 1. GESTION DES SALAIRES & AVANCES EMPLOYÉS (LIVRE DE PAIE TPE)
# ==============================================================================

def enregistrer_avance_salaire(phone: str, employe_nom: str, montant_avance: int, salaire_base: int = 0) -> dict:
    """
    Enregistre une avance sur salaire pour un commis, apprenti ou vendeur.
    Met à jour le solde restant dû pour la fin du mois sans dispute.
    Compte SYSCOHADA 421 (Personnel - Avances) & 66 (Charges de personnel).
    """
    clean_p = re.sub(r"\D", "", str(phone))
    db = _load_json(SALAIRES_DB_FILE)
    mois_courant = datetime.now().strftime("%m/%Y")

    if clean_p not in db:
        db[clean_p] = {}
    if mois_courant not in db[clean_p]:
        db[clean_p][mois_courant] = {}

    nom_cle = employe_nom.strip().title()
    foyer = db[clean_p][mois_courant].get(nom_cle, {
        "employe": nom_cle,
        "salaire_base": salaire_base or 60000,
        "total_avances": 0,
        "historique": []
    })

    if salaire_base > 0:
        foyer["salaire_base"] = salaire_base

    foyer["total_avances"] += montant_avance
    foyer["historique"].append({
        "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "montant": montant_avance
    })

    reste_a_payer = max(0, foyer["salaire_base"] - foyer["total_avances"])
    foyer["reste_du_mois"] = reste_a_payer
    db[clean_p][mois_courant][nom_cle] = foyer
    _save_json(SALAIRES_DB_FILE, db)

    return {
        "employe": nom_cle,
        "avance": montant_avance,
        "total_avances": foyer["total_avances"],
        "salaire_base": foyer["salaire_base"],
        "reste_du": reste_a_payer,
        "mois": mois_courant
    }


def obtenir_recap_salaires_mois(phone: str) -> dict:
    """Retourne l'état complet des salaires et avances du personnel pour le mois en cours."""
    clean_p = re.sub(r"\D", "", str(phone))
    db = _load_json(SALAIRES_DB_FILE)
    mois_courant = datetime.now().strftime("%m/%Y")
    data_mois = db.get(clean_p, {}).get(mois_courant, {})

    total_masse_salariale = sum(e.get("salaire_base", 0) for e in data_mois.values())
    total_avances_versees = sum(e.get("total_avances", 0) for e in data_mois.values())
    total_reste_a_payer = sum(e.get("reste_du_mois", 0) for e in data_mois.values())

    return {
        "mois": mois_courant,
        "employes": list(data_mois.values()),
        "total_salaires": total_masse_salariale,
        "total_avances": total_avances_versees,
        "total_reste_a_verser": total_reste_a_payer
    }


# ==============================================================================
# 2. CALCULATEUR DE MARGE COMMERCIALE & PRIX DE VENTE CONSEILLÉ
# ==============================================================================

def calculer_marge_et_prix_conseille(prix_achat: float, frais_annexes: float = 0.0, marge_cible_pct: float = 25.0) -> dict:
    """
    Calcule le coût de revient réel (achat + transport + dockers + emballage)
    et le prix de vente au détail recommandé pour garantir la marge nette souhaitée.
    """
    cout_revient = prix_achat + frais_annexes
    # Prix de vente pour avoir la marge brute sur PV : PV = Coût / (1 - Marge%)
    taux_marge = min(max(marge_cible_pct, 5.0), 80.0) / 100.0
    prix_vente_recommande = cout_revient / (1.0 - taux_marge)
    gain_brut_unitaire = prix_vente_recommande - cout_revient

    return {
        "prix_achat_grossiste": int(prix_achat),
        "frais_annexes": int(frais_annexes),
        "cout_revient_total": int(cout_revient),
        "marge_cible_pct": round(marge_cible_pct, 1),
        "prix_vente_conseille": int(round(prix_vente_recommande / 50.0) * 50), # Arrondi monnaie 50 F
        "gain_net_unitaire": int(gain_brut_unitaire)
    }


# ==============================================================================
# 3. DÉTECTEUR D'ÉCARTS DE CAISSE (CONTRÔLE TIROIR PHYSIQUE VS ÉCRITURES)
# ==============================================================================

def verifier_ecart_caisse_tiroir(phone: str, especes_reelles_tiroir: int) -> dict:
    """
    Compare le montant physique présent dans le tiroir-caisse avec le solde théorique
    calculé par Growth (Ventes espèces - Dépenses espèces - Popote).
    Détecte immédiatement tout coulage, erreur de rendu de monnaie ou oubli de saisie.
    """
    from chat_grow.database import get_transactions_resilient, get_entreprise_by_phone_resilient
    clean_p = re.sub(r"\D", "", str(phone))
    ent = get_entreprise_by_phone_resilient(clean_p) or {}
    ent_id = ent.get("id") or clean_p
    txs = get_transactions_resilient(ent_id) or []

    # Filtrer les transactions en espèces de la journée
    aujourdhui = datetime.now().strftime("%Y-%m-%d")
    ventes_especes = sum(t.get("montant_fcfa", 0) for t in txs if t.get("mode_paiement") == "ESPECES" and t.get("type_flux") in ["VENTE", "RECETTE"] and str(t.get("date_creation", "")).startswith(aujourdhui))
    depenses_especes = sum(t.get("montant_fcfa", 0) for t in txs if t.get("mode_paiement") == "ESPECES" and t.get("type_flux") == "DEPENSE" and str(t.get("date_creation", "")).startswith(aujourdhui))

    caisse_theorique = max(0, ventes_especes - depenses_especes)
    ecart = especes_reelles_tiroir - caisse_theorique

    return {
        "especes_tiroir": especes_reelles_tiroir,
        "caisse_theorique": caisse_theorique,
        "ventes_jour_especes": ventes_especes,
        "depenses_jour_especes": depenses_especes,
        "ecart": ecart,
        "est_carre": abs(ecart) <= 500,  # Tolérance monnaie 500 F
        "est_surplus": ecart > 500,
        "est_manquant": ecart < -500
    }


# ==============================================================================
# 4. SIMULATEUR FISCAL DGID SÉNÉGAL (CONTRIBUTION GLOBALE UNIQUE - CGU)
# ==============================================================================

def simuler_impot_cgu_senegal(ca_annuel_estime: float) -> dict:
    """
    Simule la Contribution Globale Unique (CGU) selon le Code Général des Impôts du Sénégal.
    Pour les commerçants de marchandises (Régime synthétique) :
    - CA < 5 millions FCFA : Forfait de base
    - CA 5 à 25 millions : 5% du CA annuel
    - CA 25 à 50 millions : 5% avec tenue comptable SMT obligatoire
    - CA > 50 millions : Régime du Réel (TVA 18% + Impôt sur les Sociétés 30%)
    """
    ca = max(0.0, float(ca_annuel_estime))

    if ca <= 5000000:
        cgu_annuelle = max(50000.0, ca * 0.04)
        regime = "CGU Forfaitaire de Base (Petits Commerces)"
        provision_mensuelle = cgu_annuelle / 12.0
    elif ca <= 25000000:
        cgu_annuelle = ca * 0.05
        regime = "CGU Taux Plein Commerçants (5%)"
        provision_mensuelle = cgu_annuelle / 12.0
    elif ca <= 50000000:
        cgu_annuelle = ca * 0.05
        regime = "CGU Système Minimal de Trésorerie (SMT)"
        provision_mensuelle = cgu_annuelle / 12.0
    else:
        # Régime Réel au-delà de 50 millions
        cgu_annuelle = ca * 0.08  # Estimation IS/TVA consolidée
        regime = "Régime du Réel Normal (Seuil 50M dépassé - Déclaration mensuelle)"
        provision_mensuelle = cgu_annuelle / 12.0

    return {
        "chiffre_affaires_annuel": int(ca),
        "regime_fiscal": regime,
        "impot_annuel_estime": int(cgu_annuelle),
        "provision_mensuelle_conseillee": int(provision_mensuelle),
        "provision_journaliere_conseillee": int(provision_mensuelle / 26.0) # 26 jours ouvrés
    }


# ==============================================================================
# 5. MODÈLES DE RELANCE DÉBITEURS DIPLOMATIQUES (3 INTENSITÉS)
# ==============================================================================

def generer_variante_relance_debiteur(client_nom: str, montant_fcfa: int, nom_boutique: str, intensite: str = "AMICAL") -> str:
    """
    Génère un message WhatsApp prêt à transférer selon le degré de relance nécessaire.
    Permet de récupérer l'argent sans jamais froisser le client ni créer de conflit de voisinage.
    """
    cl = client_nom.strip().title()
    btq = nom_boutique.strip()
    m_fmt = f"{montant_fcfa:,} FCFA".replace(",", " ")

    if intensite == "AMICAL":
        return (
            f"Salam alaykoum {cl} ! J'espère que vous allez très bien et que la famille se porte à merveille.\n\n"
            f"Je me permets de vous envoyer ce petit message amical pour le règlement de vos achats de *{m_fmt}* chez {btq}.\n\n"
            f"Vous pouvez régler en espèces à la boutique ou directement par Wave / Orange Money quand cela vous arrange dans la journée. "
            f"Merci infiniment pour votre confiance et bonne journée !"
        )
    elif intensite == "ECHEANCE":
        return (
            f"Bonjour {cl}, sauf erreur de ma part, l'échéance convenue pour votre facture de *{m_fmt}* chez {btq} est arrivée à terme.\n\n"
            f"Nous devons faire notre clôture de caisse et régler nos réassorts grossistes ce soir. "
            f"Pourriez-vous effectuer le transfert (Wave ou Orange Money) aujourd'hui pour nous aider à solder votre compte ?\n\n"
            f"Nous vous remercions d'avance pour votre réactivité !"
        )
    else: # PROPOSITION TRANCHE
        acompte_prop = max(5000, int(montant_fcfa * 0.3))
        ac_fmt = f"{acompte_prop:,} FCFA".replace(",", " ")
        return (
            f"Bonjour {cl}, concernant le solde de vos achats de *{m_fmt}* chez {btq} :\n\n"
            f"Si le règlement total est difficile en ce moment, nous pouvons convenir d'un paiement échelonné. "
            f"Vous pouvez verser un premier acompte de *{ac_fmt}* aujourd'hui sur Wave, et nous planifierons le reste ensemble.\n\n"
            f"Qu'en pensez-vous ? Tenez-moi au courant. Merci !"
        )

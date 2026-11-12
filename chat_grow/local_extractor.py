# -*- coding: utf-8 -*-
"""
Grow - Grand Extracteur Local Robuste (100% Hors-API / 0 Crédit / 0 FCFA)
Traitement déterministe ultra-rapide pour PME et commerces au Sénégal.
Norme SYSCOHADA SMT - Dakar.
"""

import re
import unicodedata
from typing import Optional, Dict, Any, Tuple


def normaliser_texte(texte: str) -> str:
    """Nettoie et normalise une chaîne de caractères pour faciliter la recherche par motifs."""
    if not texte:
        return ""
    # Conserver les accents de base pour l'affichage mais nettoyer les espaces et caractères invisibles
    propre = texte.replace("\u202f", " ").replace("\xa0", " ").strip()
    return propre


# ==============================================================================
# 1. PARSEUR LOCAL DE MONTANTS ET DEVISE FCFA (Sénégal)
# ==============================================================================

MOTS_NOMBRES = {
    "zero": 0, "zéro": 0, "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "quinze": 15, "vingt": 20,
    "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "cent": 100
}


def parse_montant_fcfa(texte: str) -> int:
    """
    Extrait un montant entier en FCFA depuis n'importe quel texte ou expression locale :
    - '500mille', '500 mille', '500k', '500 k' -> 500 000
    - '1 million', '2.5 millions', '1,5m' -> 1 000 000, 2 500 000, 1 500 000
    - '25.000 F', '25 000 FCFA', '25000frs', '25.000fcfa' -> 25 000
    - 'dix mille', 'cent mille', 'cinquante mille' -> 10 000, 100 000, 50 000
    """
    if not texte:
        return 0

    clean = normaliser_texte(texte).lower()
    # Rapprocher les chiffres séparés par un espace ou point de millier (ex: 50 000 -> 50000, 150.000 -> 150000)
    clean_nombres = re.sub(r'(?<=\d)[\s\.](?=\d{3}\b)', '', clean)

    # 1. Millions (ex: 2.5 millions, 1 million, 3m)
    mil_match = re.search(r'(\d+[\.,]?\d*)\s*(?:million|millions|m)\b', clean, re.IGNORECASE)
    if mil_match:
        try:
            val = float(mil_match.group(1).replace(',', '.'))
            return int(val * 1_000_000)
        except Exception:
            pass

    # 2. Mille ou K (ex: 500mille, 500 mille, 500k, 25k)
    mille_match = re.search(r'(\d+)\s*(?:mille|milles|k)\b', clean, re.IGNORECASE)
    if mille_match:
        try:
            return int(mille_match.group(1)) * 1_000
        except Exception:
            pass

    # 3. Mots littéraires courants (ex: cent mille, cinquante mille, dix mille)
    if "cent mille" in clean: return 100_000
    if "cinquante mille" in clean: return 50_000
    if "quarante mille" in clean: return 40_000
    if "trente mille" in clean: return 30_000
    if "vingt mille" in clean: return 20_000
    if "dix mille" in clean: return 10_000
    if "cinq mille" in clean: return 5_000

    # 4. Montants suivis de FCFA, F, FRS, CFA ou précédés de montant/solde/prix/capital
    motif_devise = re.search(r'(\d[\d\s\.]{2,10})\s*(?:f\b|fcfa\b|frs\b|cfa\b)', clean, re.IGNORECASE)
    if motif_devise:
        digits = re.sub(r'[^\d]', '', motif_devise.group(1))
        if digits:
            return int(digits)

    # 5. Détection après mot-clé explicite (capital, montant, prix, solde, caisse)
    motif_cle = re.search(r'(?:capital|montant|prix|solde|caisse|coût|valeur)\D*(\d[\d\s\.]{2,10})', clean, re.IGNORECASE)
    if motif_cle:
        digits = re.sub(r'[^\d]', '', motif_cle.group(1))
        if digits:
            return int(digits)

    # 6. Fallback chiffres isolés dans texte normalisé
    tous_chiffres = re.findall(r'\b\d{3,9}\b', clean_nombres)
    if tous_chiffres:
        return int(tous_chiffres[0])

    return 0


# ==============================================================================
# 2. PARSEUR D'IDENTITÉ ADMINISTRATIVE PME & ATTESTATION NINEA (Sénégal)
# ==============================================================================

FORMES_JURIDIQUES = [
    ("ENTREPRISE INDIVIDUELLE", ["entreprise individuelle", "individuelle", "etablissement", "ets"]),
    ("SARL", ["sarl", "société à responsabilité limitée", "societe a responsabilite limitee"]),
    ("SUARL", ["suarl", "société unipersonnelle", "societe unipersonnelle"]),
    ("SAS", ["sas", "société par actions simplifiée", "societe par actions simplifiee"]),
    ("GIE", ["gie", "groupement d'intérêt économique", "groupement d interet economique"]),
    ("SA", ["société anonyme", "societe anonyme", r'\bsa\b'])
]


def extract_business_identity_local(texte: str, sender_phone: str = "", contact_name: str = "") -> Dict[str, Any]:
    """
    Extrait déterministement l'identité légale de l'entreprise :
    Nom, NINEA, Capital, Forme juridique, Registre de commerce RCCM.
    100% Local - 0 Crédit API.
    """
    if not texte:
        return {
            "nom_entreprise": None,
            "ninea": None,
            "capital_social_fcfa": 0,
            "forme_juridique": None,
            "registre_commerce": None,
            "activite_principale": None
        }

    clean = normaliser_texte(texte)

    # A. NINEA : 7 à 10 chiffres (+ lettre COFI éventuelle, ex: 00780069 2V2)
    ninea = None
    ninea_cofi = re.search(r'\b(\d{7,10})\s*([0-9][A-Z][0-9])\b', clean, re.IGNORECASE)
    if ninea_cofi:
        ninea = f"{ninea_cofi.group(1)} {ninea_cofi.group(2).upper()}"
    else:
        ninea_match = re.search(r'ninea\D*(\d{7,10})', clean, re.IGNORECASE)
        if ninea_match:
            ninea = ninea_match.group(1)
        else:
            all_nums = re.findall(r'\b\d{7,10}\b', clean)
            if all_nums:
                ninea = all_nums[0]

    # B. Capital social
    capital = parse_montant_fcfa(clean)

    # C. Forme juridique
    forme_juridique = None
    clean_lower = clean.lower()
    for forme_nom, keywords in FORMES_JURIDIQUES:
        for kw in keywords:
            if re.search(r'\b' + kw + r'\b', clean_lower):
                forme_juridique = forme_nom
                break
        if forme_juridique:
            break

    # D. Registre de Commerce (RCCM)
    # Formats sénégalais types : SN-DKR-2023-A-1234, SN.DKR.2024.B.56789, SN THS 2021 A 98
    rccm = None
    rccm_match = re.search(r'\b(SN[\.\s\-]?[A-Z]{3}[\.\s\-]?\d{4}[\.\s\-]?[A-Z][\.\s\-]?\d+)\b', clean, re.IGNORECASE)
    if rccm_match:
        rccm = rccm_match.group(1).upper().replace(".", "-").replace(" ", "-")

    # E. Nom de l'entreprise
    nom = None
    # 1. Label explicite : nom de l'entreprise, nom commercial, enseigne (JAMAIS le nom personnel)
    nom_label = re.search(r'(?:nom\s*(?:de\s*(?:l[\'’])?\s*(?:entreprise|société|societe|boutique|magasin))|nom\s*commercial|enseigne)\s*(?:est|:)?\s*([A-Za-z0-9\s\-]+?)(?:,|\.|\bet\b|\bavec\b|\bninea\b|\bcapital\b|$)', clean, re.IGNORECASE)
    if nom_label:
        cand = nom_label.group(1).strip()
        if len(cand) >= 2 and cand.lower() not in ['est', 'de', 'mon', 'le', 'la', 'un', 'notre', 'la personne', 'personne']:
            nom = cand.title()

    # 2. Préfixe commercial sénégalais (Boutique, Chez, Société, SARL, SUARL, Ets, Magasin, Atelier, Salon, Pharmacie, etc.)
    if not nom:
        nom_type = re.search(r'\b(Boutique|Société|Societe|SARL|SUARL|SAS|Ets|Etablissement|Magasin|Atelier|Salon|GIE|Pharmacie|Chez|Restaurant|Agence|Cabinet)\s+([A-Za-z0-9\s\-]+?)(?:,|\.|\bet\b|\bavec\b|\bninea\b|\brccm\b|\bcapital\b|$)', clean, re.IGNORECASE)
        if nom_type:
            nom = f"{nom_type.group(1).upper() if nom_type.group(1).upper() in ['SARL', 'SUARL', 'SAS', 'GIE'] else nom_type.group(1).title()} {nom_type.group(2).strip().title()}"

    # 3. Nom précédant 'capital' ou 'ninea' (ex: 'Carine Store, capital 500mille')
    if not nom:
        nom_avant = re.search(r'^([A-Za-z0-9\s\-]{3,35})\s*(?:,|\.|\bet\b|\bavec\b)\s*(?:ninea|capital)\b', clean, re.IGNORECASE)
        if nom_avant:
            cand = nom_avant.group(1).strip()
            if not re.search(r'\b(je|mon|ma|mes|notre|nous|voici|bonjour|salut)\b', cand, re.IGNORECASE):
                nom = cand.title()

    # 4. Fallback label entreprise : X
    if not nom:
        nom_fb = re.search(r'\b(?:entreprise|société|societe)\s*:\s*([A-Za-z0-9\s\-]+?)(?:,|\.|\bet\b|\bavec\b|\bninea\b|\bcapital\b|$)', clean, re.IGNORECASE)
        if nom_fb:
            cand = nom_fb.group(1).strip()
            if len(cand) >= 2:
                nom = cand.title()

    return {
        "nom_entreprise": nom,
        "ninea": ninea,
        "capital_social_fcfa": capital,
        "forme_juridique": forme_juridique,
        "registre_commerce": rccm,
        "activite_principale": None
    }


# ==============================================================================
# 3. PARSEUR LOCAL DES NOTIFICATIONS & SMS OPÉRATEURS (Wave, OM, Free)
# ==============================================================================

def parse_operator_sms_local(sms_text: str) -> Optional[Dict[str, Any]]:
    """
    Découpe et catégorise automatiquement un SMS Wave, Orange Money ou Free Money.
    100% Local - 0 Crédit API.
    """
    if not sms_text:
        return None

    clean = normaliser_texte(sms_text)
    lower = clean.lower()

    # Détection Wave
    is_wave = "wave" in lower or "wv-" in lower or "réf:" in lower and "f" in lower
    # Détection Orange Money
    is_om = "orange money" in lower or "om" in lower or re.search(r'\b(?:ci|mp)\d{6,}', lower)
    # Détection Free Money
    is_free = "free money" in lower

    if not (is_wave or is_om or is_free or "reçu" in lower or "recu" in lower or "transfert" in lower or "paiement" in lower):
        return None

    operateur = "WAVE" if is_wave else ("ORANGE_MONEY" if is_om else "AUTRE")
    type_flux = "ENTREE"
    montant = 0
    frais = 0
    tiers_nom = None
    tiers_phone = None
    reference = None
    solde_nouveau = 0

    # 1. Type de flux (ENTREE ou SORTIE)
    if any(k in lower for k in ["vous avez reçu", "vous avez recu", "reçu de", "recu de", "dépôt de", "depot de", "crédité de"]):
        type_flux = "ENTREE"
    elif any(k in lower for k in ["transfert de", "transféré", "payé", "paiement de", "retrait de", "débité de", "envoyé à"]):
        type_flux = "SORTIE"

    # 2. Montant de l'opération
    m_match = re.search(r'(?:reçu|recu|transfert de|paiement de|retrait de|montant:?)\s*(\d[\d\s\.]{2,10})\s*(?:f|fcfa|frs|cfa)?', lower)
    if m_match:
        montant = int(re.sub(r'[^\d]', '', m_match.group(1)))
    else:
        montant = parse_montant_fcfa(clean)

    # 3. Référence de transaction
    ref_match = re.search(r'(?:réf|ref|id|transaction)\s*:?\s*([A-Za-z0-9\.\-_]+)', clean, re.IGNORECASE)
    if ref_match:
        reference = ref_match.group(1).strip()

    # 4. Tiers (Nom et Téléphone)
    phone_match = re.search(r'\b((?:221)?\s*(?:77|78|76|70|75)\s*\d{3}\s*\d{2}\s*\d{2})\b', clean)
    if phone_match:
        tiers_phone = re.sub(r'[^\d]', '', phone_match.group(1))

    nom_match = re.search(r'(?:de|vers|à|chez)\s+([A-Za-z\s\-]{3,25})(?:\(|\.|\,|\bavec\b|\bréf\b|\bref\b|$)', clean, re.IGNORECASE)
    if nom_match:
        c = nom_match.group(1).strip()
        if c.lower() not in ["votre", "compte", "succès", "frais", "solde"]:
            tiers_nom = c.title()

    # 5. Nouveau solde
    solde_match = re.search(r'(?:nouveau solde|solde:?)\s*(\d[\d\s\.]{2,10})', lower)
    if solde_match:
        solde_nouveau = int(re.sub(r'[^\d]', '', solde_match.group(1)))

    # Imputation SYSCOHADA déterministe
    if type_flux == "ENTREE":
        compte = "701"  # Ventes de marchandises / Chiffre d'affaires
        libelle = f"Vente encaissée via {operateur} - {tiers_nom or 'Client'}"
    else:
        compte = "601"  # Achats par défaut
        libelle = f"Paiement {operateur} - {tiers_nom or 'Fournisseur'}"

    return {
        "is_sms": True,
        "operateur": operateur,
        "type_flux": type_flux,
        "montant_fcfa": montant,
        "frais_fcfa": frais,
        "tiers_nom": tiers_nom or "Tiers",
        "tiers_phone": tiers_phone,
        "reference_externe": reference or f"{operateur[:2]}-{int(montant)}",
        "solde_nouveau_fcfa": solde_nouveau,
        "compte_syscohada": compte,
        "libelle": libelle
    }


# ==============================================================================
# 4. PARSEUR LOCAL D'OPÉRATIONS FINANCIÈRES & CHARGES COURANTES (SYSCOHADA)
# ==============================================================================

def parse_operation_financiere_locale(user_text: str) -> Optional[Dict[str, Any]]:
    """
    Extrait les transactions de vente ou dépense courantes déclarées par texte.
    100% Local - 0 Crédit API.
    """
    if not user_text:
        return None

    clean = normaliser_texte(user_text)
    lower = clean.lower()

    montant = parse_montant_fcfa(clean)
    if montant <= 0:
        return None

    # Source de paiement
    source = "ESPECES"
    if "wave" in lower:
        source = "WAVE"
    elif "orange" in lower or "om" in lower:
        source = "ORANGE_MONEY"
    elif any(k in lower for k in ["banque", "chèque", "cheque", "virement"]):
        source = "BANQUE"

    # Type de flux & Affectation SYSCOHADA
    # 1. Ventes (Entrées)
    if any(k in lower for k in ["vente", "vendu", "encaissement", "reçu", "recu", "chiffre d'affaire", "chiffre d affaire"]):
        return {
            "is_transaction": True,
            "type_flux": "ENTREE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "701",
            "libelle": f"Vente de marchandises ({source})",
            "besoin_justificatif": False
        }

    # 2. Carburant / Transport
    if any(k in lower for k in ["carburant", "essence", "gasoil", "total", "shell", "ola", "transport", "taxi", "tiak tiak"]):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "605",
            "libelle": f"Frais de carburant et déplacements ({source})",
            "besoin_justificatif": source == "ESPECES"
        }

    # 3. Loyer
    if any(k in lower for k in ["loyer", "bail"]):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "622",
            "libelle": f"Paiement du loyer commercial ({source})",
            "besoin_justificatif": source == "ESPECES"
        }

    # 4. Électricité & Eau (Senelec, Sen'Eau)
    if any(k in lower for k in ["senelec", "woyofal", "électricité", "electricite", "eau", "sen'eau", "sde"]):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "605",
            "libelle": f"Facture Senelec / Eau ({source})",
            "besoin_justificatif": source == "ESPECES"
        }

    # 5. Salaires
    if any(k in lower for k in ["salaire", "salaires", "paie", "avance salaire"]):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "661",
            "libelle": f"Règlement salaires du personnel ({source})",
            "besoin_justificatif": source == "ESPECES"
        }

    # 6. Achat de stock / Marchandises
    if any(k in lower for k in ["achat", "acheté", "achete", "stock", "marchandise", "fournisseur", "commande"]):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "601",
            "libelle": f"Achat de marchandises / stock ({source})",
            "besoin_justificatif": source == "ESPECES"
        }

    return None


# ==============================================================================
# 5. PARSEUR MULTI-OPÉRATEURS POUR LE BILAN D'OUVERTURE (Étape 5/5)
# ==============================================================================

def parse_soldes_multi_operateurs(texte: str, default_solde: int = 0, default_op: str = "WAVE") -> Dict[str, int]:
    """
    Extrait les soldes initiaux déclarés ou constatés par opérateur :
    Wave, Orange Money, Caisse Espèces, Compte Bancaire.
    Exemples :
    - 'Wave 50 000, Orange Money 30 000 et Caisse 20 000'
    - '150 000 sur Wave et 50 000 en espèces'
    - 'Solde 100 000'
    """
    soldes = {}
    if not texte:
        if default_solde > 0:
            soldes[default_op] = default_solde
        return soldes

    clauses = re.split(r'[,;\n\+]|\bet\b', texte, flags=re.IGNORECASE)
    for clause in clauses:
        c_clean = clause.strip().lower()
        if not c_clean:
            continue
        op = None
        if "wave" in c_clean:
            op = "WAVE"
        elif "orange" in c_clean or "om" in c_clean:
            op = "ORANGE_MONEY"
        elif any(k in c_clean for k in ["caisse", "espece", "especes", "cash"]):
            op = "ESPECES"
        elif any(k in c_clean for k in ["banque", "compte", "bancaire"]):
            op = "BANQUE"

        if op:
            val = parse_montant_fcfa(c_clean)
            if val > 0:
                soldes[op] = val

    if not soldes:
        val_total = parse_montant_fcfa(texte) or default_solde
        if val_total > 0:
            soldes[default_op] = val_total

    return soldes

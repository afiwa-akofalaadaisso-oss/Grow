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

    # 0. Élimination des quantités d'articles pour ne pas confondre quantité et montant (ex: '500 sacs', '10 cartons')
    clean_sans_qte = re.sub(
        r'\b\d+\s*(?:sacs?|sacu|kg|kilos?|colis|cartons?|caisses?|unit[ée]s?|pi[èe]ces?|bouteilles?|litres?|paquets?)\b',
        '', clean, flags=re.IGNORECASE
    )

    # Rapprocher les chiffres séparés par un espace ou point de millier (ex: 50 000 -> 50000, 150.000 -> 150000)
    clean_nombres = re.sub(r'(?<=\d)[\s\.](?=\d{3}\b)', '', clean_sans_qte)

    # 1. Millions (ex: 2.5 millions, 1 million, 3m)
    mil_match = re.search(r'(\d+[\.,]?\d*)\s*(?:million|millions|m)\b', clean, re.IGNORECASE)
    if mil_match:
        try:
            val = float(mil_match.group(1).replace(',', '.'))
            return int(val * 1_000_000)
        except Exception:
            pass

    # 2. Mille ou K (ex: 500mille, 500 mille, 500k, 25k)
    mille_match = re.search(r'(\d+)\s*(?:mille|milles|k)\b', clean_sans_qte, re.IGNORECASE)
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

    # 4. Montants explicites après verbe de coût/total en wolof ou français (def, muy def, fait, montant, coût)
    motif_cout = re.search(r'(?:muy def|mu def|defal|def|fait|co[uû]te?|montant|somme|prix|fey|fay)\D*(\d[\d\s\.]{2,10})', clean, re.IGNORECASE)
    if motif_cout:
        digits = re.sub(r'[^\d]', '', motif_cout.group(1))
        if digits:
            return int(digits)

    # 5. Montants suivis de FCFA, F, FRS, CFA
    motif_devise = re.search(r'(\d[\d\s\.]{2,10})\s*(?:f\b|fcfa\b|frs\b|cfa\b)', clean_sans_qte, re.IGNORECASE)
    if motif_devise:
        digits = re.sub(r'[^\d]', '', motif_devise.group(1))
        if digits:
            return int(digits)

    # 6. Détection après mot-clé explicite (capital, montant, prix, solde, caisse)
    motif_cle = re.search(r'(?:capital|montant|prix|solde|caisse|coût|valeur)\D*(\d[\d\s\.]{2,10})', clean_sans_qte, re.IGNORECASE)
    if motif_cle:
        digits = re.sub(r'[^\d]', '', motif_cle.group(1))
        if digits:
            return int(digits)

    # 7. Fallback chiffres isolés dans texte nettoyé des quantités (on prend le plus grand nombre)
    tous_chiffres = re.findall(r'\b\d{3,9}\b', clean_nombres)
    if tous_chiffres:
        nums = [int(c) for c in tous_chiffres]
        return max(nums)

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


def nettoyer_nom_entreprise(texte: str) -> str:
    """
    Nettoie rigoureusement le nom d'entreprise en éliminant toutes les phrases
    conversationnelles d'introduction ('mon entreprise est nghy' -> 'Nghy').
    """
    if not texte:
        return ""
    t = texte.strip().strip("\"'«»“”")
    
    # 0. Salutations
    t = re.sub(r"^(?:bonjour|salut|bonsoir|hello|merci|ok|d['’]accord|svp|s['’]il\s+vous\s+pla[îi]t)\s*[,!;:.]?\s*", "", t, flags=re.IGNORECASE).strip()
    
    # A. Formules "le nom (de ...)? (est|c'est|cest|c est|c|:)"
    t = re.sub(r"^(?:le\s+nom(?:\s+commercial)?(?:\s+(?:de\s+|d['’])(?:mon\s+|ma\s+|notre\s+|la\s+|l['’])?\s*(?:entreprise|soci[ée]t[ée]|boutique|commerce|magasin|atelier|agence|bo[îi]te))?\s*(?:est|c['’\s]?est|\bc\b|:))\s*", "", t, flags=re.IGNORECASE).strip()
    
    # B. "(mon|ma|notre|l'|la)\s*(entreprise|société|boutique|commerce|magasin|atelier|agence|boîte|enseigne)\s*(est|c'est|cest|c est|c|s'appelle|se nomme)?\s*:?"
    t = re.sub(r"^(?:(?:mon|ma|notre|l['’\s]?|la)\s*(?:entreprise|soci[ée]t[ée]|boutique|commerce|magasin|atelier|agence|bo[îi]te|enseigne))\s*(?:est|c['’\s]?est|\bc\b|s['’\s]?appelle|se\s+nomme)?\s*:?\s*", "", t, flags=re.IGNORECASE).strip()
    
    # C. "c'est X", "cest X", "c est X", "il s'agit de X", "il sagit de X", "nom: X", "nom X"
    t = re.sub(r"^(?:c['’\s]?est|\bc\b|il\s+s['’\s]?agit\s+de|je\s+m['’\s]?appelle|nous\s+sommes|nom\s*:?)\s*", "", t, flags=re.IGNORECASE).strip()
    
    # D. Répétition si enchaîné (ex: "est X", "c'est X")
    t = re.sub(r"^(?:est|c['’\s]?est|\bc\b|:)\s*", "", t, flags=re.IGNORECASE).strip()
    
    # D2. Normaliser 'la/le/l' boutique X' -> 'Boutique X'
    t = re.sub(r"^(?:la|le|l['’\s]?)\s+(boutique|magasin|atelier|commerce|agence|soci[ée]t[ée]|bo[îi]te)\b", r"\1", t, flags=re.IGNORECASE).strip()
    
    # E. Supprimer les guillemets et ponctuations
    t = t.strip("\"'«»“”.,:;!?-").strip()
    
    if t.isupper() and len(t) <= 8:
        return t
    mots = t.split()
    mots_propres = []
    for m in mots:
        if m.isupper() and len(m) <= 6:
            mots_propres.append(m)
        else:
            mots_propres.append(m.capitalize())
    return " ".join(mots_propres)


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
    # 0. Détection directe phrases : "mon entreprise est nghy", "le nom de mon entreprise est nghy"
    phrase_directe = re.search(r'(?:(?:le\s+nom\s+(?:de\s+(?:mon|ma|notre|la|l[\'’])?\s*(?:entreprise|soci[ée]t[ée]|boutique|commerce|magasin|atelier|agence|bo[îi]te))?\s*(?:est|c[\'’\s]?est|\bc\b|:))|(?:(?:mon|ma|notre|l[\'’\s]?|la)\s*(?:entreprise|soci[ée]t[ée]|boutique|commerce|magasin|atelier|agence|bo[îi]te|enseigne)\s*(?:est|c[\'’\s]?est|\bc\b|s[\'’\s]?appelle|se\s+nomme)?\s*:?))\s*([A-Za-z0-9\s\-]+?)(?:,|\.|\bet\b|\bavec\b|\bninea\b|\bcapital\b|$)', clean, re.IGNORECASE)
    if phrase_directe:
        cand = phrase_directe.group(1).strip()
        cand_clean = nettoyer_nom_entreprise(cand)
        if len(cand_clean) >= 2:
            nom = cand_clean

    # 1. Label explicite : nom de l'entreprise, nom commercial, enseigne (JAMAIS le nom personnel)
    if not nom:
        nom_label = re.search(r'(?:nom\s*(?:de\s*(?:mon|ma|notre|l[\'’])?\s*(?:entreprise|société|societe|boutique|magasin))|nom\s*commercial|enseigne)\s*(?:est|:)?\s*([A-Za-z0-9\s\-]+?)(?:,|\.|\bet\b|\bavec\b|\bninea\b|\bcapital\b|$)', clean, re.IGNORECASE)
        if nom_label:
            cand = nom_label.group(1).strip()
            cand_clean = nettoyer_nom_entreprise(cand)
            if len(cand_clean) >= 2 and cand_clean.lower() not in ['est', 'de', 'mon', 'le', 'la', 'un', 'notre', 'la personne', 'personne']:
                nom = cand_clean

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
            cand_clean = nettoyer_nom_entreprise(cand)
            if len(cand_clean) >= 2:
                nom = cand_clean

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

    # 2.bis Frais de transfert / retrait (Wave / OM)
    frais_match = re.search(r'(?:frais\s*:?|frais\s+de)\s*(\d[\d\s\.]{1,6})\s*(?:f|fcfa|frs|cfa)?', lower)
    if frais_match:
        try:
            frais = int(re.sub(r'[^\d]', '', frais_match.group(1)))
        except Exception:
            frais = 0

    # 3. Référence de transaction
    ref_match = re.search(r'(?:réf|ref|id|transaction)\s*:?\s*([A-Za-z0-9\.\-_]+)', clean, re.IGNORECASE)
    if ref_match:
        reference = ref_match.group(1).strip()
    elif "w-" in lower or "t_" in lower or "m_" in lower:
        code_match = re.search(r'\b([TMWhW][_\-][A-Za-z0-9]+)\b', clean)
        if code_match:
            reference = code_match.group(1).strip()

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

    # Source de paiement (Français & Wolof)
    source = "ESPECES"
    if "wave" in lower:
        source = "WAVE"
    elif "orange" in lower or "om" in lower:
        source = "ORANGE_MONEY"
    elif any(k in lower for k in ["banque", "chèque", "cheque", "virement", "kàmp"]):
        source = "BANQUE"
    elif any(k in lower for k in ["espece", "espèces", "cash", "loxo", "ci loxo"]):
        source = "ESPECES"

    # 0.bis Prélèvements personnels de l'exploitant / Popote / Famille / Maison (SYSCOHADA Compte 104)
    # Important : Dépenses non déductibles de l'entreprise mais imputées sur la caisse privée de l'exploitant
    mots_perso = [
        "popote", "dépense personnelle", "depense personnelle", "dépenses personnelles",
        "argent popote", "perso", "sama bopp", "sama bop", "pour la maison", "kër", "keur",
        "famille", "ordonnance", "pharmacie maison", "dépense maison", "depense maison",
        "frais maison", "scolarité", "scolarite", "fourniture scolaire", "retrait personnel",
        "retrait perso", "khalsou kër", "xalissu kër"
    ]
    if any(k in lower for k in mots_perso) and not any(k in lower for k in ["loyer", "bail"]):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "104",
            "est_professionnel": False,
            "libelle": f"Prélèvement personnel exploitant / Popote ({source})",
            "besoin_justificatif": False
        }

    # 0.ter Virements internes de trésorerie (SYSCOHADA Compte 585)
    # Important : Transfert neutre de compte à compte (ex: Wave vers Caisse ou Orange vers Wave)
    mots_virement_interne = [
        "virement interne", "transfert interne", "retrait wave pour caisse", "retrait wave pour la caisse",
        "wave vers caisse", "caisse vers wave", "orange vers caisse", "retrait om pour caisse",
        "alimenter la caisse", "alimenter caisse", "vers compte bancaire", "vers banque",
        "retrait pour la caisse", "transfert de compte"
    ]
    is_virement = any(k in lower for k in mots_virement_interne) or (
        any(k in lower for k in ["retrait", "virement", "transfert"]) and any(k in lower for k in ["pour la caisse", "pour caisse", "vers caisse", "vers wave", "vers orange", "alimenter caisse", "alimenter la caisse", "interne"])
    )
    if is_virement:
        return {
            "is_transaction": True,
            "type_flux": "VIREMENT_INTERNE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "585",
            "est_professionnel": True,
            "libelle": f"Virement interne de trésorerie ({source})",
            "besoin_justificatif": False
        }

    # 0.quater Pertes sur stocks, avaries, vol et marchandises périmées (SYSCOHADA Compte 654)
    mots_perte_stock = [
        "perte de stock", "pertes de stock", "perte stock", "pertes stock", "marchandise pourrie",
        "marchandise avariée", "marchandise abîmée", "marchandises avariées", "stock avarié",
        "stock pourri", "produits périmés", "produit périmé", "produit perime", "jeté à la poubelle",
        "stock jeté", "yakhou", "yakhou na", "volé", "vol de marchandise", "casse de stock"
    ]
    if any(k in lower for k in mots_perte_stock):
        return {
            "is_transaction": True,
            "type_flux": "PERTE_STOCK",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "654",
            "est_professionnel": True,
            "libelle": f"Pertes sur stocks et avaries (SYSCOHADA 654)",
            "besoin_justificatif": False
        }

    # Type de flux & Affectation SYSCOHADA (Français & Wolof)
    # 1. Ventes (Entrées) : vente, vendu, encaissement, reçu, jaay, jaay naa, dug na, jot naa
    mots_ventes = [
        "vente", "vendu", "encaissement", "reçu", "recu", "chiffre d'affaire", "chiffre d affaire",
        "jaay", "jaay na", "jaay naa", "dama jaay", "am na jaay", "dug na", "dugna", "jot naa", "encaisser"
    ]
    if any(k in lower for k in mots_ventes):
        return {
            "is_transaction": True,
            "type_flux": "ENTREE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "701",
            "libelle": f"Vente de marchandises / Jaay ({source})",
            "besoin_justificatif": False
        }

    # 2. Achats & Marchandise (Sorties 601) : jënd, jend, achat, marchandise, stock
    mots_achats = [
        "achat", "acheté", "achete", "jënd", "jënd na", "jënd naa", "jend", "jend na", "jend naa",
        "dama jënd", "dama jend", "marchandise", "stock"
    ]
    if any(k in lower for k in mots_achats):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "601",
            "libelle": f"Achat de marchandises / Jënd ({source})",
            "besoin_justificatif": source == "ESPECES"
        }

    # 3. Carburant / Transport : essence, carburant, tiak tiak, taxi, dem ak dikk
    mots_transport = [
        "carburant", "essence", "gasoil", "total", "shell", "ola",
        "transport", "taxi", "tiak tiak", "tiak-tiak", "car rapide", "dem ak dikk"
    ]
    if any(k in lower for k in mots_transport):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "605",
            "libelle": f"Frais de carburant et déplacements ({source})",
            "besoin_justificatif": source == "ESPECES"
        }

    # 4. Loyer : loyer, bail, kër gi
    if any(k in lower for k in ["loyer", "bail", "kër gi", "keur gui"]):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "622",
            "libelle": f"Paiement du loyer commercial ({source})",
            "besoin_justificatif": source == "ESPECES"
        }

    # 5. Électricité & Eau (Senelec, Sen'Eau, Woyofal)
    if any(k in lower for k in ["senelec", "woyofal", "électricité", "electricite", "eau", "sen'eau", "sde", "kuraŋ"]):
        return {
            "is_transaction": True,
            "type_flux": "SORTIE",
            "montant_fcfa": montant,
            "source_paiement": source,
            "compte_syscohada": "605",
            "libelle": f"Facture Senelec / Eau ({source})",
            "besoin_justificatif": source == "ESPECES"
        }

    # 6. Salaires / Fey : salaire, salaires, paie, avance, fey liggeeykat
    if any(k in lower for k in ["salaire", "salaires", "paie", "avance salaire", "fey liggeeykat", "fey"]):
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


# ==============================================================================
# 6. PARSEUR LOCAL DES PAIEMENTS MIXTES (WAVE + CASH / OM + CASH)
# ==============================================================================

def parse_paiement_mixte_local(texte: str) -> Optional[Dict[str, Any]]:
    """
    Détecte et ventile les paiements mixtes courants au Sénégal :
    - Exemples :
      * "Vente de 35 000 : 15 000 en espèces et 20 000 par Wave"
      * "Vente 50000 : 30000 wave et 20000 cash"
      * "Client bi fey na 45 000 : 25 000 ci wave ak 20 000 ci loxo"
      * "Achat marchandise 60 000 : 40 000 wave et 20 000 espèces"
    """
    if not texte:
        return None
    clean = normaliser_texte(texte)
    lower = clean.lower()

    # Doit contenir à la fois un moyen digital (Wave/OM) ET du cash/espèces
    has_digital = any(k in lower for k in ["wave", "orange money", "om", "free money"])
    has_cash = any(k in lower for k in ["espece", "espèces", "cash", "liquide", "caisse", "loxo", "ci loxo"])

    if not (has_digital and has_cash):
        return None

    part_wave = 0
    part_om = 0
    part_cash = 0

    # 1. Motif Wave
    m_wave = re.search(r'(\d[\d\s\.]{1,8})\s*(?:k|mille)?\s*(?:sur|par|ci\s+|via)?\s*wave|wave\D*(\d[\d\s\.]{1,8})', lower)
    if m_wave:
        raw_w = m_wave.group(1) or m_wave.group(2)
        part_wave = parse_montant_fcfa(raw_w)

    # 2. Motif Orange Money
    m_om = re.search(r'(\d[\d\s\.]{1,8})\s*(?:k|mille)?\s*(?:sur|par|ci\s+|via)?\s*(?:om|orange\s+money)|(?:om|orange\s+money)\D*(\d[\d\s\.]{1,8})', lower)
    if m_om:
        raw_om = m_om.group(1) or m_om.group(2)
        part_om = parse_montant_fcfa(raw_om)

    # 3. Motif Cash / Espèces
    m_cash = re.search(r'(\d[\d\s\.]{1,8})\s*(?:k|mille)?\s*(?:en\s+|ci\s+)?(?:espece|espèces|cash|liquide|loxo)|(?:espece|espèces|cash|liquide|loxo)\D*(\d[\d\s\.]{1,8})', lower)
    if m_cash:
        raw_c = m_cash.group(1) or m_cash.group(2)
        part_cash = parse_montant_fcfa(raw_c)

    if (part_wave > 0 or part_om > 0) and part_cash > 0:
        total = part_wave + part_om + part_cash
        
        # Détection type de flux
        mots_achats = ["achat", "acheté", "achete", "dépense", "depense", "fournisseur", "jënd", "jend", "payé", "frais"]
        is_sortie = any(k in lower for k in mots_achats)
        type_flux = "SORTIE" if is_sortie else "ENTREE"
        compte = "601" if is_sortie else "701"

        return {
            "is_mixte": True,
            "type_flux": type_flux,
            "total_fcfa": total,
            "part_wave": part_wave,
            "part_om": part_om,
            "part_cash": part_cash,
            "compte_syscohada": compte,
            "libelle": f"{'Vente' if type_flux == 'ENTREE' else 'Achat'} mixte ({f'{part_wave:,.0f} Wave' if part_wave else ''} {f'+ {part_om:,.0f} OM' if part_om else ''} + {part_cash:,.0f} Espèces)"
        }

    return None


# ==============================================================================
# 7. DÉTECTION DE RUPTURE DE STOCK & MARCHANDISES ÉPUISÉES (Sénégal & Wolof)
# ==============================================================================

def detecter_declaration_rupture_stock(texte: str) -> bool:
    """
    Détecte les déclarations d'épuisement ou de rupture de stock en Français ou Wolof :
    - 'le stock est fini', 'plus de stock', 'rupture de stock', 'stock vide', 'stock à zéro'
    - 'marchandise bi diekh na', 'diekh na', 'amul stock', 'stock bi diekh na'
    """
    if not texte:
        return False
    lower = normaliser_texte(texte).lower()
    
    mots_rupture = [
        "le stock est fini", "stock est fini", "stock fini", "plus de stock",
        "rupture de stock", "en rupture", "stock vide", "stock à zéro", "stock a zero",
        "on a plus de marchandise", "je n'ai plus de stock", "il n'y a plus de stock",
        "diekh na", "jex na", "marchandise bi diekh na", "stock bi diekh na", "amul stock",
        "amul marchandise", "stock bi diekh"
    ]
    return any(k in lower for k in mots_rupture)


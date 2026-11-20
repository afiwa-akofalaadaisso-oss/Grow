"""
Grow - Module de Reconstitution Historique Multicanal
Analyse et qualification automatique d'anciens relevés (Wave Business, Orange Money, Banque, Wave Perso Multi-SMS)
Sépare les flux Professionnels (Comptes 6 et 7) des flux Personnels (Compte de l'exploitant 104)
et isole les incertitudes en Compte d'attente (471).
"""

import re
import csv
import io
from datetime import datetime
from typing import Dict, Any, List, Optional

# Mots-clés des fournisseurs et charges pro récurrentes au Sénégal
CHARGES_PRO_PATTERNS = [
    (r"\b(?:senelec|woyofal|sodeci)\b", "605", "Électricité & Énergie (Senelec/Woyofal)", "SORTIE"),
    (r"\b(?:sen'?eau|sde)\b", "605", "Eau d'exploitation (Sen'Eau)", "SORTIE"),
    (r"\b(?:sonatel|orange|free|expresso|canal\+?)\b", "628", "Télécom, Internet & Abonnements", "SORTIE"),
    (r"\b(?:total|shell|ola|star oil|oil libya|petrosen|carburant|essence|gazoil)\b", "612", "Carburant & Déplacements pro", "SORTIE"),
    (r"\b(?:ciment|sococim|dangote|quincaillerie|fer|materiel|fournisseur|grossiste|marchandise|stock)\b", "601", "Achats de matières & marchandises", "SORTIE"),
    (r"\b(?:loyer|bail|magasin|boutique|entrepot)\b", "622", "Locations & Loyers commerciaux", "SORTIE"),
    (r"\b(?:salaire|paie|personnel|employe|gardiennage|securite)\b", "661", "Rémunération du personnel", "SORTIE"),
    (r"\b(?:dgid|impot|taxe|douane|brs|vrs|patente|fiscal)\b", "641", "Impôts, Taxes & Versements fiscaux", "SORTIE"),
    (r"\b(?:cbao|ecobank|boa|sgbs|bicis|banque|agios|frais bancaires)\b", "631", "Frais financiers & services bancaires", "SORTIE"),
    (r"\b(?:frais wave|frais de retrait|frais om)\b", "631", "Frais de transfert & Mobile Money", "SORTIE"),
]

# Patterns de dépenses purement personnelles (à router en Compte 104)
DEPENSES_PERSO_PATTERNS = [
    r"\b(?:maman|papa|famille|maison|enfant|ecole|tontine|aide|tabaski|korite|bapteme|mariage|hopital|ordonnance|pharmacie)\b",
    r"\b(?:retrait dab|retrait distributeur|retrait guichet|retrait personnel)\b",
    r"\b(?:supermarche|carrefour|auchan|exclusive|courses|alimentation)\b"
]

def normaliser_chaine(texte: str) -> str:
    if not texte:
        return ""
    return re.sub(r"\s+", " ", str(texte)).strip()

def parser_montant(val: Any) -> float:
    if isinstance(val, (int, float)):
        return abs(float(val))
    if not val:
        return 0.0
    clean = re.sub(r"[^\d,\.]", "", str(val))
    if "," in clean and "." in clean:
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        clean = clean.replace(",", ".")
    try:
        return abs(float(clean))
    except Exception:
        return 0.0

def normaliser_date_iso(date_str: str) -> str:
    """Convertit les dates DD/MM/YYYY ou DD/MM/YY en format ISO standard YYYY-MM-DD."""
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    d = str(date_str).strip()
    m = re.match(r'^(\d{2})[/\-\.](\d{2})[/\-\.](\d{4})$', d)
    if m:
        return f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
    m2 = re.match(r'^(\d{2})[/\-\.](\d{2})[/\-\.](\d{2})$', d)
    if m2:
        return f'20{m2.group(3)}-{m2.group(2)}-{m2.group(1)}'
    m3 = re.match(r'^(\d{4})[/\-\.](\d{2})[/\-\.](\d{2})$', d)
    if m3:
        return d[:10]
    return d[:10] if len(d) >= 10 else datetime.now().strftime("%Y-%m-%d")

def qualifier_flux(libelle: str, montant: float, type_flux_brut: str = "AUTO") -> Dict[str, Any]:
    """
    Qualifie un flux financier en SYSCOHADA :
    - 701/706 si Encaissement Client (Pro)
    - 60-66 si Dépense d'exploitation qualifiée (Pro)
    - 104 si Dépense Personnelle / Prélèvement de l'exploitant
    - 471 si Flou / Oublié / En attente
    """
    lib_low = libelle.lower()
    
    # 1. Détection du sens du flux (ENTREE vs SORTIE)
    if type_flux_brut in ["ENTREE", "CREDIT", "RECU", "DEPOT", "ENCAISSEMENT"]:
        type_flux = "ENTREE"
    elif type_flux_brut in ["SORTIE", "DEBIT", "ENVOYE", "RETRAIT", "PAIEMENT"]:
        type_flux = "SORTIE"
    else:
        # Détection automatique par mots-clés
        if any(w in lib_low for w in ["reçu", "recu", "paiement reçu", "dépôt", "depot", "credit", "reception"]):
            type_flux = "ENTREE"
        else:
            type_flux = "SORTIE"

    # 2. Si c'est un flux entrant (Recette)
    if type_flux == "ENTREE":
        return {
            "type_flux": "ENTREE",
            "compte_syscohada": "701",
            "categorie": "PRO_RECETTE",
            "statut": "VALIDE_PRO",
            "justification": "Chiffre d'affaires Ventes / Prestations (SYSCOHADA 701)",
            "certitude": 0.90
        }

    # 3. Si c'est un flux sortant (Dépense) : tester les patterns PRO
    for pat, cpt, nom_cpt, _ in CHARGES_PRO_PATTERNS:
        if re.search(pat, lib_low):
            return {
                "type_flux": "SORTIE",
                "compte_syscohada": cpt,
                "categorie": "PRO_CHARGE",
                "statut": "VALIDE_PRO",
                "justification": f"{nom_cpt} (SYSCOHADA {cpt})",
                "certitude": 0.95
            }

    # 4. Tester les patterns PERSO évidents -> Compte de l'exploitant 104
    for pat in DEPENSES_PERSO_PATTERNS:
        if re.search(pat, lib_low):
            return {
                "type_flux": "SORTIE",
                "compte_syscohada": "104",
                "categorie": "PERSO_EXPLOITANT",
                "statut": "VALIDE_PERSO",
                "justification": "Prélèvement personnel de l'exploitant (Compte 104 - Isolé)",
                "certitude": 0.85
            }

    # 5. Détection heuristique des gros transferts récurrents (ex: loyer ou gros fournisseur)
    if montant >= 100000:
        return {
            "type_flux": "SORTIE",
            "compte_syscohada": "601",
            "categorie": "PRO_CHARGE",
            "statut": "A_CONFIRMER",
            "justification": "Achat important fournisseur présumé (Compte 601)",
            "certitude": 0.70
        }

    # 6. Flux incertain ou micro-transfert oublié -> Compte d'attente 471
    return {
        "type_flux": "SORTIE",
        "compte_syscohada": "471",
        "categorie": "ATTENTE_REGULARISATION",
        "statut": "A_CONFIRMER",
        "justification": "Opération non identifiée (Compte d'attente SYSCOHADA 471)",
        "certitude": 0.50
    }

# ==============================================================================
# PARSEURS SPÉCIFIQUES MULTI-SOURCES
# ==============================================================================

def parser_releve_wave_business(contenu_texte: str) -> List[Dict[str, Any]]:
    """Parse l'export CSV/TSV officiel ou l'export PDF du portail Wave Business Merchant."""
    lignes = []

    # 1. Vérifier si c'est un export PDF vertical Wave Business (tokens 'merchant_payment' ou 'merchant_sweep')
    tokens = contenu_texte.split()
    if any(t in tokens for t in ["merchant_payment", "merchant_sweep"]):
        for i, tok in enumerate(tokens):
            if tok in ["merchant_payment", "merchant_sweep"]:
                tx_type = tok
                tx_id = tokens[i-1] if i > 0 else f"WV-{int(datetime.now().timestamp())}"
                if not tx_id.startswith("T_") and not tx_id.startswith("LT_sn_"):
                    if i >= 2 and (tokens[i-2].startswith("T_") or tokens[i-2].startswith("LT_sn_")):
                        tx_id = tokens[i-2] + tx_id

                date_str = datetime.now().strftime("%Y-%m-%d")
                for j in range(max(0, i-6), i):
                    if len(tokens[j]) == 10 and tokens[j][4] == "-" and tokens[j][7] == "-":
                        date_str = tokens[j]
                        break

                amt_str = tokens[i+1] if i+1 < len(tokens) else "0"
                fee_str = tokens[i+2] if i+2 < len(tokens) else "0"
                montant_raw = int(amt_str) if amt_str.lstrip("-").isdigit() else 0
                montant = abs(montant_raw)
                frais = int(fee_str) if fee_str.isdigit() else 0

                if montant > 0:
                    if tx_type == "merchant_payment":
                        sens = "ENTREE"
                        libelle = f"Vente Wave Business ({tx_id})"
                        qualif = {
                            "type_flux": "ENTREE",
                            "compte_syscohada": "701",
                            "categorie": "PRO_RECETTE",
                            "statut": "VALIDE_PRO",
                            "justification": "Encaissement Vente Wave Business (SYSCOHADA 701)",
                            "certitude": 0.99
                        }
                    else: # merchant_sweep
                        sens = "SORTIE"
                        libelle = f"Virement automatique compte / caisse ({tx_id})"
                        qualif = {
                            "type_flux": "SORTIE",
                            "compte_syscohada": "104",
                            "categorie": "PERSO_EXPLOITANT",
                            "statut": "VALIDE_PERSO",
                            "justification": "Virement sweep automatique (Compte 104)",
                            "certitude": 0.95
                        }

                    lignes.append({
                        "date": normaliser_date_iso(date_str),
                        "reference": tx_id,
                        "libelle": libelle,
                        "montant": float(montant),
                        "frais": float(frais),
                        "source": "WAVE_BUSINESS",
                        "tiers": "Client Wave" if sens == "ENTREE" else "Compte Exploitant",
                        **qualif
                    })
        if lignes:
            return lignes

    # 2. Tentative de lecture CSV standard
    reader = csv.reader(io.StringIO(contenu_texte))
    headers = []
    for idx, row in enumerate(reader):
        if not row or all(c.strip() == "" for c in row):
            continue
        if idx == 0 or not headers:
            headers = [c.lower().strip() for c in row]
            continue
        
        # Mapping automatique des colonnes Wave Business
        row_dict = {}
        for i, val in enumerate(row):
            if i < len(headers):
                row_dict[headers[i]] = val.strip()

        date_str = row_dict.get("date") or row_dict.get("created_at") or row_dict.get("horodatage") or datetime.now().strftime("%Y-%m-%d")
        montant = parser_montant(row_dict.get("amount") or row_dict.get("montant") or row_dict.get("net") or 0)
        frais = parser_montant(row_dict.get("fee") or row_dict.get("frais") or 0)
        type_w = (row_dict.get("type") or row_dict.get("status") or "").upper()
        tiers = row_dict.get("name") or row_dict.get("client") or row_dict.get("destinataire") or row_dict.get("counterparty") or "Tiers Wave"
        ref = row_dict.get("id") or row_dict.get("reference") or row_dict.get("tx_id") or f"WV-{int(datetime.now().timestamp())}"

        if montant <= 0:
            continue

        sens = "ENTREE" if any(k in type_w.lower() for k in ["payment", "deposit", "recu", "paiement", "encaissement", "receive"]) else "SORTIE"
        libelle = f"Wave Business : {type_w} {tiers}".strip()
        qualif = qualifier_flux(f"{type_w} {tiers}", montant, sens)

        lignes.append({
            "date": normaliser_date_iso(date_str),
            "reference": ref,
            "libelle": libelle,
            "montant": montant,
            "frais": frais,
            "source": "WAVE_BUSINESS",
            "tiers": tiers,
            **qualif
        })
    return lignes

def parser_releve_orange_money(contenu_texte: str) -> List[Dict[str, Any]]:
    """Parse les relevés Orange Money (reçus Max it, exports marchands ou relevés PDF/texte)."""
    lignes = []
    lines = contenu_texte.split("\n")
    for line in lines:
        l = line.strip()
        if not l or len(l) < 10:
            continue
        
        # Recherche montant
        m_match = re.search(r"(\d[\d\s\.]{2,9})\s*(?:fcfa|f|cfa)", l, re.IGNORECASE)
        if not m_match:
            continue
        montant = parser_montant(m_match.group(1))
        if montant <= 0:
            continue

        # Recherche date (ex: 12/04/2024 ou 2024-04-12)
        d_match = re.search(r"\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4}|\d{4}[/\-\.]\d{2}[/\-\.]\d{2})\b", l)
        date_str = d_match.group(1) if d_match else datetime.now().strftime("%Y-%m-%d")

        # Réf Orange Money (ex: CI240512.1420.A01234 ou MP...)
        r_match = re.search(r"\b([A-Z0-9]{8,20}(?:\.[A-Z0-9]+)?)\b", l)
        ref = r_match.group(1) if r_match else f"OM-{int(datetime.now().timestamp())}"

        sens = "ENTREE" if any(w in l.lower() for w in ["reçu", "recu", "dépôt", "crédit", "entree"]) else "SORTIE"
        qualif = qualifier_flux(l, montant, sens)

        lignes.append({
            "date": normaliser_date_iso(date_str),
            "reference": ref,
            "libelle": f"Orange Money : {l[:60]}...",
            "montant": montant,
            "frais": 0.0,
            "source": "ORANGE_MONEY",
            "tiers": "Tiers OM",
            **qualif
        })
    return lignes

def parser_releve_wave_perso_sms(contenu_texte: str) -> List[Dict[str, Any]]:
    """
    Parse les historiques de SMS Wave Personnel :
    Pour les comptes Wave perso sans bouton d'export PDF officiel,
    l'entrepreneur copie-colle simplement son historique de SMS reçus de Wave !
    """
    lignes = []
    # Découpage par blocs de SMS
    # Ex: 'Vous avez reçu 25000F de Moussa Diop le 12/04/24. Réf: WV-123. Nouveau solde: 50000F'
    # ou 'Transfert de 15000F envoyé à Senelec...'
    pattern_sms = re.compile(
        r"(?:vous avez (?:reçu|recu|envoyé|envoye)|transfert de|retrait de|paiement de).*?(?=vous avez (?:reçu|recu|envoyé|envoye)|transfert de|retrait de|paiement de|$)",
        re.IGNORECASE | re.DOTALL
    )
    blocs = pattern_sms.findall(contenu_texte)
    if not blocs:
        # Tentative ligne par ligne
        blocs = [l.strip() for l in contenu_texte.split("\n") if len(l.strip()) > 15]

    for bloc in blocs:
        b_clean = normaliser_chaine(bloc)
        b_low = b_clean.lower()
        if not ("wave" in b_low or "f" in b_low or "fcfa" in b_low or "wv-" in b_low):
            continue

        # Montant
        m_match = re.search(r"(?:reçu|recu|transfert de|paiement de|retrait de|montant:?)\s*(\d[\d\s\.]{2,10})\s*(?:f|fcfa|frs)?", b_low)
        if not m_match:
            m_match = re.search(r"(\d[\d\s\.]{2,10})\s*(?:f|fcfa|frs)", b_low)
        if not m_match:
            continue

        montant = parser_montant(m_match.group(1))
        if montant <= 0:
            continue

        # Sens
        if any(w in b_low for w in ["reçu", "recu", "dépôt", "depot", "crédité"]):
            sens = "ENTREE"
        else:
            sens = "SORTIE"

        # Tiers
        nom_match = re.search(r"(?:de|vers|à|chez)\s+([A-Za-z\s\-]{3,30})(?:\(|\.|\,|\bavec\b|\bréf\b|\bref\b|$)", b_clean, re.IGNORECASE)
        tiers = nom_match.group(1).strip() if nom_match else "Tiers Wave"

        # Réf
        r_match = re.search(r"(?:réf|ref|id)\s*:?\s*([A-Za-z0-9\.\-_]{6,25})", b_clean, re.IGNORECASE)
        ref = r_match.group(1).strip() if r_match else f"SMS-WV-{int(datetime.now().timestamp())}"

        # Date
        d_match = re.search(r"\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{2,4}|\d{4}[/\-\.]\d{2}[/\-\.]\d{2})\b", b_clean)
        date_str = d_match.group(1) if d_match else datetime.now().strftime("%Y-%m-%d")

        qualif = qualifier_flux(f"{tiers} {b_clean}", montant, sens)

        lignes.append({
            "date": normaliser_date_iso(date_str),
            "reference": ref,
            "libelle": f"Wave Perso (SMS) : {sens} {montant:,.0f} F - {tiers}",
            "montant": montant,
            "frais": 0.0,
            "source": "WAVE_PERSO_SMS",
            "tiers": tiers,
            **qualif
        })
    return lignes

def parser_releve_bancaire_standard(contenu_texte: str) -> List[Dict[str, Any]]:
    """Parse les relevés bancaires classiques (CBAO, SGBS, Ecobank, BOA)."""
    lignes = []
    lines = contenu_texte.split("\n")
    for line in lines:
        l = line.strip()
        if not l or len(l) < 15:
            continue
        
        # Détection date
        d_match = re.search(r"^(\d{2}[/\-\.]\d{2}[/\-\.]\d{2,4})", l)
        if not d_match:
            continue
        date_str = d_match.group(1)

        # Montants Débit / Crédit
        chiffres = re.findall(r"(\d[\d\s\.]{2,10}(?:,\d{2})?)", l)
        if not chiffres:
            continue
        montant = parser_montant(chiffres[-1])
        if montant <= 0:
            continue

        # Déterminer sens : si mots clés crédit ou fin de ligne
        sens = "ENTREE" if any(k in l.lower() for k in ["remise", "virement recu", "credit", "versement"]) else "SORTIE"
        qualif = qualifier_flux(l, montant, sens)

        lignes.append({
            "date": date_str,
            "reference": f"BNQ-{int(datetime.now().timestamp())}",
            "libelle": f"Banque : {l[:60]}",
            "montant": montant,
            "frais": 0.0,
            "source": "BANQUE",
            "tiers": "Banque",
            **qualif
        })
    return lignes


# ==============================================================================
# MOTEUR PRINCIPAL D'ANALYSE ET RAPPORT DE RECONSTITUTION
# ==============================================================================

def reconstituer_historique(type_source: str, contenu_texte: str) -> Dict[str, Any]:
    """
    Exécute l'analyse globale et génère le rapport de reconstitution financière.
    Calcule le taux de complétude (> 80%), la séparation Pro/Perso et la ventilation SYSCOHADA.
    """
    type_src = type_source.upper()
    if "WAVE_BUSINESS" in type_src:
        operations = parser_releve_wave_business(contenu_texte)
    elif "ORANGE" in type_src:
        operations = parser_releve_orange_money(contenu_texte)
    elif "SMS" in type_src or "WAVE_PERSO" in type_src:
        operations = parser_releve_wave_perso_sms(contenu_texte)
    else:
        # Par défaut bancaire ou multi-détection
        operations = parser_releve_bancaire_standard(contenu_texte)
        if not operations:
            operations = parser_releve_wave_perso_sms(contenu_texte)

    if not operations:
        return {
            "status": "empty",
            "message": "Aucune transaction financière détectée dans ce document.",
            "nb_total": 0,
            "taux_qualification_pct": 0
        }

    nb_total = len(operations)
    total_recettes_pro = 0.0
    total_charges_pro = 0.0
    total_perso_exploitant = 0.0
    total_attente = 0.0

    nb_qualifiees = 0

    for op in operations:
        m = op.get("montant", 0.0)
        cat = op.get("categorie")
        if cat == "PRO_RECETTE":
            total_recettes_pro += m
            nb_qualifiees += 1
        elif cat == "PRO_CHARGE":
            total_charges_pro += m
            nb_qualifiees += 1
        elif cat == "PERSO_EXPLOITANT":
            total_perso_exploitant += m
            nb_qualifiees += 1
        else: # ATTENTE_REGULARISATION
            total_attente += m

    taux_qualification = round((nb_qualifiees / nb_total) * 100, 1) if nb_total > 0 else 0
    solde_net_pro = total_recettes_pro - total_charges_pro

    return {
        "status": "success",
        "nb_total": nb_total,
        "taux_qualification_pct": taux_qualification,
        "total_recettes_pro_fcfa": total_recettes_pro,
        "total_charges_pro_fcfa": total_charges_pro,
        "total_perso_exploitant_fcfa": total_perso_exploitant,
        "total_attente_fcfa": total_attente,
        "solde_net_pro_fcfa": solde_net_pro,
        "operations": operations,
        "message": f"Succès : {nb_total} transactions analysées avec {taux_qualification}% de preuves financières isolées."
    }


def extraire_texte_document(media_bytes: bytes, filename: str = "", mime_type: str = "") -> str:
    """Extrait le texte brut d'un document (CSV, TXT, PDF)."""
    if not media_bytes:
        return ""
    
    # 1. Si c'est du PDF
    if (filename and filename.lower().endswith(".pdf")) or "pdf" in (mime_type or "").lower():
        try:
            import io, pypdf
            reader = pypdf.PdfReader(io.BytesIO(media_bytes))
            pages = []
            for p in reader.pages:
                txt = p.extract_text()
                if txt:
                    pages.append(txt)
            if pages:
                return "\n".join(pages)
        except Exception as e:
            print(f"Info lecture PDF pypdf: {e}")

    # 2. Si c'est du texte ou CSV
    try:
        return media_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return media_bytes.decode("latin-1", errors="ignore")
        except Exception:
            return ""


def formater_rapport_whatsapp(res: Dict[str, Any], lang: str = "fr") -> str:
    """Génère le message WhatsApp officiel avec mise en page soignée, emojis et montants lisibles."""
    nb_total = res.get("nb_total", 0)
    taux = res.get("taux_qualification_pct", 0)
    recettes = res.get("total_recettes_pro_fcfa", 0.0)
    charges = res.get("total_charges_pro_fcfa", 0.0)
    perso = res.get("total_perso_exploitant_fcfa", 0.0)
    attente = res.get("total_attente_fcfa", 0.0)
    net = res.get("solde_net_pro_fcfa", 0.0)

    if lang == "wo":
        signe = "+" if net >= 0 else "-"
        return (
            "📊 *DEFARAT SA HISTORIQUE COMPTES CI GROW* 🚀\n\n"
            f"Saytu nañu sa document bi ak jàmm !\n\n"
            f"🎯 *Taux bu nu certifier :* {taux}% ci say préuves financières wer nañu te mengóok SYSCOHADA.\n\n"
            f"📈 *Jaay / Koom-koom Pro (Ventes 701) :* +{recettes:,.0f} FCFA\n"
            f"📉 *Dépenses Pro d'Exploitation (60-66) :* -{charges:,.0f} FCFA\n"
            f"👤 *Dépenses personnelles yi nu ber (Compte 104) :* {perso:,.0f} FCFA\n"
            f"❓ *Yiy xaar clarification (Compte 471) :* {attente:,.0f} FCFA\n\n"
            f"💰 *Bénéfice Net d'Exploitation :* {signe}{abs(net):,.0f} FCFA\n\n"
            f"✅ *{nb_total} écritures yépp dugal nañu leen ci sa teere compte !*\n"
            "Sa pré-bilan ngir banque bi pare na leegi.\n"
            "Bindal *BILAN* ngir giss liasse bi !"
        )
    else:
        signe = "+" if net >= 0 else "-"
        return (
            "📊 *RECONSTITUTION HISTORIQUE DE VOS COMPTES GROW* 🚀\n\n"
            f"J'ai analysé votre historique ({nb_total} opérations) avec succès !\n\n"
            f"🎯 *Taux de qualification :* {taux}% de vos preuves financières sont isolées et conformes SYSCOHADA.\n\n"
            f"📈 *Chiffre d'Affaires Pro (Ventes 701) :* +{recettes:,.0f} FCFA\n"
            f"📉 *Charges d'Exploitation Pro (60-66) :* -{charges:,.0f} FCFA\n"
            f"👤 *Dépenses Personnelles isolées (Compte 104) :* {perso:,.0f} FCFA\n"
            f"❓ *Opérations en attente (Compte 471) :* {attente:,.0f} FCFA\n\n"
            f"💰 *Bénéfice Net d'Exploitation :* {signe}{abs(net):,.0f} FCFA\n\n"
            f"✅ *Les {nb_total} écritures ont été intégrées dans votre journal comptable !*\n"
            "Votre historique et votre pré-bilan pour la banque sont prêts.\n"
            "Tapez *BILAN* pour consulter votre synthèse financière !"
        )



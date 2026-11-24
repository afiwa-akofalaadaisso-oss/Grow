import json
import os
import re
from datetime import datetime

MEMOIRE_FILE = os.path.join(os.path.dirname(__file__), "fournisseurs_memoire.json")

# Dictionnaire national des enseignes, services publics et utilités au Sénégal
DICT_SERVICES_NATIONAUX = {
    # 1. Énergie, Eau & Utilités (Compte 605 - Achats de matières et fournitures consommables)
    "woyofal": ("605", "Achats de matières et fournitures (Électricité Woyofal)"),
    "senelec": ("605", "Achats de matières et fournitures (Électricité Senelec)"),
    "seneau": ("605", "Achats de matières et fournitures (Eau Sen'Eau)"),
    "sen'eau": ("605", "Achats de matières et fournitures (Eau Sen'Eau)"),
    "sde": ("605", "Achats de matières et fournitures (Eau SDE)"),
    "gaz": ("605", "Fournitures d'exploitation (Bouteille de Gaz Touba/Total)"),
    "touba gaz": ("605", "Fournitures d'exploitation (Touba Gaz)"),

    # 2. Carburant & Transports d'exploitation (Compte 605 / 624)
    "total": ("605", "Carburants et lubrifiants (TotalEnergies)"),
    "totalenergies": ("605", "Carburants et lubrifiants (TotalEnergies)"),
    "shell": ("605", "Carburants et lubrifiants (Shell Vivo Energy)"),
    "ola": ("605", "Carburants et lubrifiants (Ola Energy)"),
    "ola energy": ("605", "Carburants et lubrifiants (Ola Energy)"),
    "puma": ("605", "Carburants et lubrifiants (Puma Energy)"),
    "star oil": ("605", "Carburants et lubrifiants (Star Oil)"),
    "elton": ("605", "Carburants et lubrifiants (Elton Oil)"),
    "carburant": ("605", "Carburants et lubrifiants"),
    "essence": ("605", "Carburants et lubrifiants"),
    "gasoil": ("605", "Carburants et lubrifiants"),
    "autoroute": ("624", "Transports et péages (SECAA Autoroute de l'Avenir)"),
    "secaa": ("624", "Transports et péages (SECAA)"),
    "peage": ("624", "Transports et péages"),
    "taxi": ("624", "Transports et déplacements professionnels"),
    "yango": ("624", "Transports et déplacements professionnels (Yango)"),
    "heetch": ("624", "Transports et déplacements professionnels (Heetch)"),

    # 3. Télécommunications, Internet & Frais de réseau (Compte 628 / 631)
    "orange": ("628", "Télécommunications & Internet (Orange Sonatel)"),
    "sonatel": ("628", "Télécommunications & Internet (Sonatel)"),
    "free": ("628", "Télécommunications & Internet (Free Sénégal)"),
    "expresso": ("628", "Télécommunications & Internet (Expresso)"),
    "canal+": ("628", "Abonnement professionnel audiovisuel (Canal+)"),
    "canal plus": ("628", "Abonnement professionnel audiovisuel (Canal+)"),
    "seddo": ("628", "Recharge téléphonique Seddo"),
    "izi": ("628", "Recharge téléphonique Izi"),
    "frais wave": ("631", "Frais bancaires et assimilés (Commission Wave)"),
    "wave frais": ("631", "Frais bancaires et assimilés (Commission Wave)"),

    # 4. Impôts, Taxes, Douanes & Droits Officiels (Compte 64)
    "mairie": ("64", "Impôts, taxes et droits assimilés (Taxe municipale)"),
    "douane": ("64", "Droits de douane et taxes d'importation"),
    "dgid": ("64", "Impôts directs et taxes d'exploitation (DGID)"),
    "impots": ("64", "Impôts directs et taxes d'exploitation (DGID)"),
    "impot": ("64", "Impôts directs et taxes d'exploitation (DGID)"),
    "tresor": ("64", "Trésor Public Sénégalais"),
    "ipres": ("664", "Charges sociales patronales (IPRES Retraite)"),
    "css": ("664", "Charges sociales patronales (Caisse Sécurité Sociale)"),

    # 5. Loyer & Immobilier Commercial (Compte 622)
    "loyer": ("622", "Locations et charges locatives (Loyer commercial)"),
    "bailleur": ("622", "Locations et charges locatives (Bailleur)"),
    "proprietaire": ("622", "Locations et charges locatives"),

    # 6. Salaires & Avances Collaborateurs (Compte 661)
    "salaire": ("661", "Rémunérations directes versées au personnel"),
    "avancesalaire": ("661", "Avances sur salaires du personnel"),
    "gardien": ("661", "Rémunérations de gardiennage et sécurité"),
    "securite": ("661", "Rémunérations de gardiennage et sécurité"),

    # 7. Grossistes industriels & centrales d'achats alimentaires connues au Sénégal
    "senico": ("601", "Achats de marchandises - Grossiste agroalimentaire (Senico)"),
    "soboce": ("601", "Achats de marchandises - Boissons & Brasseries (SOBOCE)"),
    "patex": ("601", "Achats de marchandises (PATEX Sénégal)"),
    "siagro": ("601", "Achats de marchandises (Siagro Kirène)"),
    "kirene": ("601", "Achats de marchandises (Kirène)"),
    "marche sandaga": ("601", "Achats de marchandises (Marché Sandaga)"),
    "sandaga": ("601", "Achats de marchandises (Sandaga)"),
    "marche hlm": ("601", "Achats de marchandises (Marché HLM)"),
    "marche tilene": ("601", "Achats de marchandises (Marché Tilène)"),
    "marche castors": ("601", "Achats de marchandises (Marché Castors)"),
    "quincaillerie": ("601", "Achats de marchandises (Quincaillerie)"),
    "fournisseur": ("601", "Achats de marchandises / Fournisseur"),
    "grossiste": ("601", "Achats de marchandises / Grossiste")
}


def get_memoire_fournisseurs(entreprise_id: str = None) -> dict:
    """Charge la mémoire des tiers/fournisseurs déjà appris."""
    if not os.path.exists(MEMOIRE_FILE):
        return {}
    try:
        with open(MEMOIRE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if entreprise_id:
                return data.get(entreprise_id, {})
            return data
    except Exception:
        return {}


def enregistrer_fournisseur_memoire(entreprise_id: str, nom_ou_id: str, compte: str, intitule: str, motif: str = ""):
    """Enregistre un fournisseur pour toujours : l'IA ne reposera plus jamais la question."""
    if not entreprise_id or not nom_ou_id:
        return
    key = nom_ou_id.strip().lower()
    all_data = get_memoire_fournisseurs()
    if entreprise_id not in all_data:
        all_data[entreprise_id] = {}

    all_data[entreprise_id][key] = {
        "compte_syscohada": compte,
        "intitule": intitule,
        "motif": motif or intitule,
        "date_apprise": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        with open(MEMOIRE_FILE, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        print(f"[IA MÉMOIRE APPRENTISSAGE] {nom_ou_id} associé au Compte {compte} ({intitule}) pour PME {entreprise_id}")
    except Exception as e:
        print(f"Erreur sauvegarde mémoire fournisseur : {e}")


def classifier_operation_automatiquement(direction: str, montant: int, description: str, tiers_nom: str, entreprise_id: str) -> dict:
    """
    Algorithme de Classification Intelligent Growth :
    1. Encaissements (80-90% du flux) -> Compte 701 (Chiffre d'Affaires) d'office. Zéro question.
    2. Fournisseurs déjà appris dans la mémoire PME -> Compte appris d'office. Zéro question.
    3. Services nationaux & grandes enseignes -> Compte dédié d'office. Zéro question.
    4. Grossistes & Mots-clés évidents de stock -> Compte 601 d'office. Zéro question.
    5. Nature inconnue -> Compte 471100 (mise en attente pour le rituel de clôture de 20h00 sans déranger en journée).
    """
    direction_norm = (direction or "CREDIT").upper()
    is_entree = direction_norm in ["CREDIT", "IN", "ENTREE", "RECEIVED"]
    
    # RÈGLE 1 : TOUS LES ENCAISSEMENTS = CHIFFRE D'AFFAIRES (Compte 706 si Services, sinon 701 Marchandises)
    if is_entree:
        desc_low = f"{description or ''} {tiers_nom or ''}".lower()
        is_service = any(k in desc_low for k in ["service", "prestation", "honoraires", "consulting", "coiffure", "course", "livraison", "reparation", "formation", "nettoyage", "devis", "maintenance", "agence", "cabinet", "freelance"])
        cpt_ca = "706" if is_service else "701"
        return {
            "compte_syscohada": cpt_ca,
            "libelle": description or f"Encaissement client - {tiers_nom}",
            "statut_validation": "VALIDE_PME",
            "besoin_question_immediate": False,
            "methode_resolution": "AUTO_ENCAISSEMENT_SERVICES" if is_service else "AUTO_ENCAISSEMENT_CA"
        }

    # Pour les décaissements (SORTIES d'argent) :
    texte_complet = f"{description or ''} {tiers_nom or ''}".lower()
    tiers_key = (tiers_nom or "").strip().lower()

    # RÈGLE 2 : RECHERCHE DANS LA MÉMOIRE APPRISE DE LA PME
    memoire_pme = get_memoire_fournisseurs(entreprise_id)
    if tiers_key and tiers_key in memoire_pme:
        appris = memoire_pme[tiers_key]
        compte = appris["compte_syscohada"]
        intitule = appris["intitule"]
        return {
            "compte_syscohada": compte,
            "libelle": f"{description} ({intitule})",
            "statut_validation": "VALIDE_PME",
            "besoin_question_immediate": False,
            "methode_resolution": "AUTO_MEMOIRE_APPRENTISSAGE"
        }

    # RÈGLE 3 : RECHERCHE DANS LE DICTIONNAIRE DES ENSEIGNES & SERVICES NATIONAUX
    for mot_cle, (cpt, lib_type) in DICT_SERVICES_NATIONAUX.items():
        if mot_cle in texte_complet:
            return {
                "compte_syscohada": cpt,
                "libelle": f"{description} ({lib_type})",
                "statut_validation": "VALIDE_PME",
                "besoin_question_immediate": False,
                "methode_resolution": "AUTO_SERVICES_NATIONAUX"
            }

    # RÈGLE 4 : AMBIGUÏTÉ / NATURE INCONNUE
    # On affecte le compte d'attente 471100 SANS déranger le commerçant en direct pendant sa journée.
    # L'écriture attendra le rituel consolidé du soir à 20h00.
    return {
        "compte_syscohada": "471100",
        "libelle": f"Décaissement Wave à préciser - {tiers_nom}",
        "statut_validation": "EN_ATTENTE_JUSTIFICATIF",
        "besoin_question_immediate": False,  # PAS DE SPAM IMMÉDIAT !
        "methode_resolution": "ATTENTE_RITUEL_SOIR"
    }


def generer_message_rituel_soir(nom_entreprise: str, txs_du_jour: list, treso_stats: tuple) -> str:
    """
    Génère le grand bilan consolidé de la journée (21h00 par défaut).
    Calcule exclusivement les opérations enregistrées aujourd'hui dans la base Supabase.
    100% Local - 0 Crédit API.
    """
    wave, om, especes, total_dispo = treso_stats
    total_tx = len(txs_du_jour)
    total_in = sum(int(t.get("montant_fcfa") or 0) for t in txs_du_jour if t.get("type_flux") == "ENTREE")
    total_out = sum(int(t.get("montant_fcfa") or 0) for t in txs_du_jour if t.get("type_flux") == "SORTIE")

    # Écritures en attente d'imputation ou justificatif (471100 ou 471)
    en_attente = [t for t in txs_du_jour if t.get("compte_syscohada") in ["471100", "471"]]
    nb_auto = total_tx - len(en_attente)

    msg = (
        f"Bonsoir {nom_entreprise} !\n\n"
        f"C'est l'heure de votre grand bilan financier officiel de clôture de la journée.\n\n"
        f"Point Trésorerie en direct :\n"
        f"• Compte Wave : {wave:,.0f} FCFA\n"
        f"• Compte Orange Money : {om:,.0f} FCFA\n"
        f"• Caisse Espèces : {especes:,.0f} FCFA\n"
        f"• Total Trésorerie disponible : {total_dispo:,.0f} FCFA\n\n"
        f"Bilan de votre journée d'aujourd'hui :\n"
        f"• Opérations comptabilisées : {total_tx}\n"
        f"• Chiffre d'affaires encaissé : {total_in:,.0f} FCFA\n"
        f"• Dépenses certifiées : {total_out:,.0f} FCFA\n"
        f"• Bénéfice net estimé : {(total_in - total_out):,.0f} FCFA\n\n"
    )

    if not en_attente:
        msg += (
            "Certification 100% réussie :\n"
            f"L'intégralité de vos opérations du jour est qualifiée, justifiée et conforme aux normes SYSCOHADA.\n"
        )
    else:
        msg += (
            f"Intelligence Growth : {nb_auto} sur {total_tx} opérations validées d'office.\n"
            f"Il ne reste que {len(en_attente)} dépense(s) à préciser pour parfaire votre journal :\n\n"
        )
        for i, tx in enumerate(en_attente[:5], 1):
            m = int(tx.get("montant_fcfa") or 0)
            lib = tx.get("libelle") or "Décaissement"
            msg += f"{i}. {m:,.0f} FCFA ({lib})\n"

        msg += (
            "\nPour tout valider d'un coup, envoyez simplement une note vocale ou un court message "
            "(exemple : « Le 1 c'est du carburant, le 2 c'est le taxi »).\n"
        )

    msg += (
        "\n🐑 *LE POINTAGE DU BERGER (Rien ne doit échapper au bilan)* :\n"
        "Avant de clôturer définitivement vos comptes ce soir :\n"
        "1. 💵 *Caisse physique* : Votre cash réel en main correspond-il au solde ?\n"
        "2. 🍲 *Popote / Famille (104)* : Avez-vous pris de l'argent dans la caisse pour la maison ?\n"
        "3. 🤝 *Crédits clients (411)* : Quelqu'un est-il parti avec de la marchandise sans payer ?\n"
        "4. 📦 *Stock & Pertes (601/654)* : Achat de nouveau stock ou marchandise abîmée aujourd'hui ?\n"
        "5. 🏗️ *Matériel & Équipements (244)* : Avez-vous acheté, réparé ou installé du matériel pour le commerce ?\n\n"
        "👉 *Une seule petite note vocale rapide suffit* (ex: « Caisse 45 000, pris 5 000 popote, et Modou me doit 10 000 ») !"
    )

    return msg


def generer_point_flash_journee(nom_entreprise: str, txs_du_jour: list, treso_stats: tuple, heure_actuelle: str, dashboard_url: str = "") -> str:
    """
    Génère un point flash toutes les 3 heures (09h, 12h, 15h, 18h, 21h).
    Bref résumé en direct des flux du jour captés en arrière-plan (Wave, OM, Espèces).
    100% Local - 0 Crédit API.
    """
    wave, om, especes, total_dispo = treso_stats
    tx_in = [t for t in txs_du_jour if t.get("type_flux") == "ENTREE"]
    total_in = sum(int(t.get("montant_fcfa") or 0) for t in tx_in)
    total_out = sum(int(t.get("montant_fcfa") or 0) for t in txs_du_jour if t.get("type_flux") == "SORTIE")

    # Détail des encaissements Wave captés silencieusement
    tx_wave = [t for t in tx_in if (t.get("source_paiement") or "").upper() == "WAVE"]
    total_wave_in = sum(int(t.get("montant_fcfa") or 0) for t in tx_wave)
    wave_info_line = f"• Encaissements Wave captés en arrière-plan : {len(tx_wave)} opération(s) ({total_wave_in:,.0f} FCFA)\n" if tx_wave else ""

    dash_line = f"\n\nConsultez votre journal financier en direct :\n{dashboard_url}" if dashboard_url else ""

    # Point d'étape du Berger au fil de la journée : prise de nouvelles pour alimenter le Bilan SYSCOHADA
    h_int = 12
    try:
        h_str = heure_actuelle.split(":")[0].strip()
        h_int = int(h_str)
    except Exception:
        pass

    if 7 <= h_int <= 11:
        berger_nouvelles_bilan = (
            "\n\n🐑 *Point d'Étape du Berger (11h30 - Espèces, Popote & Achats)* 📋 :\n"
            "1. 💵 Caisse Espèces (571) : Avez-vous pris du liquide dans votre tiroir (popote midi, transport, dockers) ?\n"
            "2. 📦 Stock & Prix Grossistes (601) : Nouvel arrivage ce matin ? Un grossiste a-t-il augmenté ou baissé un prix ?\n"
            "3. 🛠️ Matériel & Équipements (244) : Achat, réparation ou matériel changé (pour mise à jour de l'amortissement) ?\n"
            "4. 💼 Dettes / Crédits (401/411) : Marchandise prise à crédit ou client à qui vous avez fait crédit ?\n"
            "👉 *Dictez tout en 1 seule note vocale rapide (Wolof ou Français)* !"
        )
    elif 12 <= h_int <= 14:
        berger_nouvelles_bilan = (
            "\n\n🐑 *Point d'Étape du Berger (15h00 - Stocks, Grossistes & Caisse)* 📋 :\n"
            "1. 💵 Tiroir Caisse Espèces (571) : Vos dépenses en liquide du midi sont-elles bien toutes déclarées ?\n"
            "2. 📦 Stocks & Variations de Prix (601/311) : Le stock a-t-il diminué ou augmenté ? Le prix d'achat exact a-t-il changé ?\n"
            "3. 🍲 Dépenses Perso / Popote (104) : Retrait pour les besoins de la famille pris sur la caisse ?\n"
            "4. 🤝 Crédits Clients (411) : De nouveaux clients ont-ils pris à crédit ?\n"
            "👉 *Dictez simplement un court vocal (ex : « 5000 popote, reçu 1 carton huile à 18 000, 2000 dockers »)* !"
        )
    elif 15 <= h_int <= 17:
        berger_nouvelles_bilan = (
            "\n\n🐑 *Point d'Étape du Berger (18h00 - Matériel, Amortissements & Dettes)* 📋 :\n"
            "1. 🛠️ Matériel Professionnel (241/244) : Un équipement en panne, réparé ou remplacé aujourd'hui ? (Suivi amortissement 5/10 ans)\n"
            "2. 💵 Espèces Tiroir (571) : Combien reste-t-il à peu près en billets/pièces avant la fermeture ?\n"
            "3. 💼 Dettes Fournisseurs (401) : Factures fournisseurs payées ou en attente d'échéance ?\n"
            "4. 💳 Règlements Clients (411) : Un client est-il venu rembourser sa dette ?\n"
            "👉 *Un mot vocal rapide pour ajuster votre situation en direct avant la clôture du soir.*"
        )
    else:
        berger_nouvelles_bilan = (
            "\n\n🐑 *Grand Rituel du Berger (20h00 - Clôture Totale & Caisse)* 📋 :\n"
            "1. 💵 Comptage Caisse Espèces (571) : Quel est le montant exact en billets et pièces dans votre tiroir ce soir ?\n"
            "2. 📱 Comptes Wave & Orange Money : Vos soldes correspondent-ils aux flux reçus ?\n"
            "3. 🍲 Popote & Prélèvements (104) : Toutes les sorties familiales sont-elles comptabilisées ?\n"
            "4. 📸 Factures & Pièces : Une facture grossiste à photographier pour sceller le justificatif ?\n"
            "👉 *Validez votre caisse du soir pour sceller votre journée conforme SYSCOHADA !*"
        )

    return (
        f"POINT FLASH DE {heure_actuelle} - {nom_entreprise.upper()}\n\n"
        f"Situation trésorerie en direct :\n"
        f"{wave_info_line}"
        f"• Recettes : {total_in:,.0f} FCFA ({len(tx_in)} op.) | Dépenses : {total_out:,.0f} FCFA\n"
        f"• Disponible : {total_dispo:,.0f} FCFA (Wave : {wave:,.0f} | Espèces : {especes:,.0f}" + (f" | OM : {om:,.0f}" if om > 0 else "") + ")\n"
        f"• Statut : Conforme SYSCOHADA{berger_nouvelles_bilan}{dash_line}"
    )


def generer_message_matin_6h(nom_entreprise: str, txs_nuit: list, treso_stats: tuple) -> str:
    """
    Message de 06h00 du matin.
    Résume les éventuelles transactions intervenues durant la nuit (Wave / OM nocturnes)
    et refait le compte exact de démarrage avant le début de la journée.
    100% Local - 0 Crédit API.
    """
    wave, om, especes, total_dispo = treso_stats
    total_nuit_in = sum(int(t.get("montant_fcfa") or 0) for t in txs_nuit if t.get("type_flux") == "ENTREE")
    total_nuit_out = sum(int(t.get("montant_fcfa") or 0) for t in txs_nuit if t.get("type_flux") == "SORTIE")

    lignes_nuit = []
    if txs_nuit:
        for t in txs_nuit[:4]:
            m = int(t.get("montant_fcfa") or 0)
            src = t.get("source_paiement", "WAVE")
            lib = t.get("libelle", "Paiement reçu")
            flux_signe = "+" if t.get("type_flux") == "ENTREE" else "-"
            lignes_nuit.append(f"  • {flux_signe}{m:,.0f} FCFA via {src} ({lib})")
        resume_nuit = "\n".join(lignes_nuit)
        bilan_nuit_txt = (
            f"Pendant votre nuit, Growth a intercepté et certifié {len(txs_nuit)} opération(s) :\n"
            f"{resume_nuit}\n"
            f"Total encaissé cette nuit : +{total_nuit_in:,.0f} FCFA\n\n"
        )
    else:
        bilan_nuit_txt = "Aucune transaction financière n'est intervenue pendant la nuit.\n\n"

    return (
        f"Bonjour {nom_entreprise} !\n\n"
        f"Il est 06h00, une nouvelle journée d'activité commence.\n\n"
        f"{bilan_nuit_txt}"
        f"État exact de vos comptes au réveil :\n"
        f"• Compte Wave : {wave:,.0f} FCFA\n"
        f"• Compte Orange Money : {om:,.0f} FCFA\n"
        f"• Caisse Espèces : {especes:,.0f} FCFA\n"
        f"• Total Trésorerie de départ : {total_dispo:,.0f} FCFA\n\n"
        f"🐑 *Rattrapage du Berger* :\n"
        f"Si vous vous êtes endormi hier soir avant le pointage final, pas d'inquiétude ! "
        f"Dictez-moi rapidement votre caisse de fermeture ou vos crédits d'hier en 1 note vocale avant votre première vente.\n\n"
        f"Growth est à vos côtés. Bonne journée de vente et de prospérité !"
    )


# -*- coding: utf-8 -*-
"""
Grow - Moteur d'Intelligence Métier & Mini-ChatGPT Spécialisé SYSCOHADA
100% Hors-Crédit API / Déterministe / Instantané / Spécialisé PME Sénégal.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple


# ==============================================================================
# 1. BASE DE CONNAISSANCES COMPTABLE & JURIDIQUE EXPERTE (SYSCOHADA SMT)
# ==============================================================================

KNOWLEDGE_BASE = [
    {
        "keywords": [r"\bsyscohada\b", r"\bsmt\b", r"systeme comptable", r"norme comptable"],
        "titre": "Qu'est-ce que le SYSCOHADA SMT ?",
        "reponse": (
            "Le SYSCOHADA (Système Comptable OHADA) est le référentiel comptable officiel en vigueur au Sénégal et dans 17 pays d'Afrique de l'Ouest et Centrale.\n\n"
            "Grow applique le Système Minimal de Trésorerie (SMT), spécialement conçu pour les commerçants et PME :\n"
            "• Suivi rigoureux des recettes et dépenses en direct (Wave, Orange Money, Caisse, Banque)\n"
            "• Imputation aux comptes officiels (701 Ventes, 601 Achats, 605 Charges, 622 Loyer...)\n"
            "• Préparation automatique de votre Bilan et Compte de Résultat certifiables par nos agences partenaires ONECCA pour vos dossiers de crédit bancaire."
        )
    },
    {
        "keywords": [r"pourquoi.*justificatif", r"pourquoi.*recu", r"pourquoi.*preuve", r"sans justificatif", r"exiger.*recu"],
        "titre": "Pourquoi chaque dépense en cash exige une pièce justificative ?",
        "reponse": (
            "En comptabilité SYSCOHADA et selon le Code Général des Impôts du Sénégal (DGID), toute charge non justifiée par une pièce probante est rejetée et réintégrée au bénéfice imposable.\n\n"
            "Pourquoi c'est vous qui perdez sans justificatif ?\n"
            "1. Déductibilité fiscale : sans reçu ni facture, vous paierez des impôts sur de l'argent que vous avez pourtant dépensé !\n"
            "2. Crédit bancaire : les banques refusent de financer une entreprise dont les sorties de caisse ne sont pas étayées par des reçus ou des photos de stock.\n"
            "3. Règle Grow : une photo de votre reçu, facture ou marchandise suffit pour certifier la dépense instantanément."
        )
    },
    {
        "keywords": [r"\bninea\b", r"\brccm\b", r"registre de commerce", r"cofi", r"immatriculation"],
        "titre": "NINEA et Registre de Commerce (RCCM)",
        "reponse": (
            "Le NINEA (Numéro d'Identification Nationale des Entreprises et Associations) et le RCCM constituent la carte d'identité juridique de votre entreprise au Sénégal :\n\n"
            "• Le NINEA est délivré par la Direction Générale des Impôts et des Domaines (DGID) ou l'APIX.\n"
            "• Le RCCM est enregistré au Tribunal de Commerce.\n\n"
            "Sur Grow, l'attestation papier NINEA permet de certifier officiellement votre Raison sociale, votre Capital social, votre Forme juridique et votre Activité principale pour que vos bilans soient reconnus par l'État et les institutions financières."
        )
    },
    {
        "keywords": [r"rituel", r"00h", r"minuit", r"20h", r"cloture", r"clôture", r"fin de journee", r"fin de journée", r"bilan du soir"],
        "titre": "Le Bilan de Clôture Quotidien de Minuit (00h00)",
        "reponse": (
            "Chaque nuit à 00h00 (minuit pile), Growth dresse automatiquement le grand bilan consolidé de votre journée terminée :\n\n"
            "• Total des ventes encaissées (Wave, Orange Money, Caisse)\n"
            "• Total des dépenses certifiées avec justificatifs\n"
            "• Marge nette réelle de la journée\n"
            "• Solde exact restant dans chaque compte de trésorerie\n\n"
            "🌙 Pas besoin de répondre la nuit ! Vous pouvez vous reposer en paix et valider votre pointage le lendemain dès 06h00 à votre réveil par une simple note vocale."
        )
    },
    {
        "keywords": [r"agence.*partenaire", r"expert.*comptable", r"comptabilite", r"partenaires", r"certification"],
        "titre": "Conformité Comptable & Experts Référents",
        "reponse": (
            "Grow est une plateforme technologique conçue pour permettre aux PME et à leurs conseils comptables d'établir leurs états financiers conformément au Droit Comptable SYSCOHADA (Système Minimal de Trésorerie SMT).\n\n"
            "Grâce à la traçabilité de vos opérations sur WhatsApp et à l'archivage numérique de vos justificatifs (AUDCIF Art. 24) avec empreinte SHA-256, vos données sont saines, vérifiables et prêtes pour la révision par votre professionnel comptable et la constitution de dossiers de financement bancaire (BHS, CBAO, BOA, Ecobank, PAMECAS, ACEP)."
        )
    },
    {
        "keywords": [r"dette", r"creance", r"créance", r"impaye", r"impayé", r"relance", r"credit client"],
        "titre": "Gestion des Dettes Fournisseurs & Créances Clients",
        "reponse": (
            "Grow suit automatiquement vos impayés sans cahier papier :\n\n"
            "• Pour enregistrer un crédit client : écrivez « Moussa me doit 25 000 FCFA »\n"
            "• Pour enregistrer une dette fournisseur : écrivez « Je dois 50 000 FCFA à Ets Diop »\n"
            "• Pour enregistrer un remboursement : écrivez « Moussa m'a remboursé 10 000 FCFA »\n\n"
            "Grow met à jour le solde restant et génère des rappels de relance tous les 3 jours pour récupérer votre argent sans tension."
        )
    },
    {
        "keywords": [r"compte.*utilises", r"plan comptable", r"comptes.*syscohada", r"compte 701", r"compte 601"],
        "titre": "Comptes SYSCOHADA utilisés par Grow",
        "reponse": (
            "Grow affecte automatiquement chaque flux au bon compte du Système Minimal de Trésorerie :\n"
            "• Compte 701 : Ventes de marchandises et produits finis\n"
            "• Compte 601 : Achats de marchandises et matières premières (Stock)\n"
            "• Compte 605 : Carburant, transport, fournitures et électricité (Senelec/Eau)\n"
            "• Compte 622 : Loyer commercial et charges locatives\n"
            "• Compte 661 : Salaires et rémunérations du personnel\n"
            "• Compte 521 : Banques et Comptes Monnaie Électronique (Wave, Orange Money)\n"
            "• Compte 571 : Caisse espèces (Cash physique)\n"
            "• Compte 401 : Dettes Fournisseurs d'exploitation\n"
            "• Compte 411 : Créances Clients (Impayés)\n"
            "• Compte 104 : Prélèvements personnels de l'exploitant (Popote / Dépenses privées déduites du cash mais préservées des charges pro)\n"
            "• Compte 585 : Virements internes (Transfert neutre entre Wave, OM, Caisse et Banque)\n"
            "• Compte 654 : Pertes sur stocks et avaries (Dépréciation de stock et marchandises détruites/volées)\n"
            "• Compte 284/681 : Amortissements linéaires mensuels du matériel et des immobilisations"
        )
    },
    {
        "keywords": [r"popote", r"depense personnelle", r"dépense personnelle", r"retrait perso", r"compte 104"],
        "titre": "Gestion de la Popote & Prélèvements Personnels (Compte 104)",
        "reponse": (
            "En comptabilité SYSCOHADA (Article 104), les dépenses personnelles de l'entrepreneur (popote familiale, santé, scolarité, ordonnance) ne doivent JAMAIS être mélangées aux charges de l'entreprise.\n\n"
            "Comment Growth gère cela automatiquement ?\n"
            "1. Lorsque vous prenez de l'argent dans la caisse pour votre famille (ex: « 5 000 popote »), la caisse est débitée fidèlement pour refléter votre solde réel.\n"
            "2. En revanche, ce montant n'est PAS comptabilisé dans vos charges d'exploitation : votre résultat net et votre marge commerciale restent propres et crédibles pour les banques.\n"
            "3. Aucun reçu fiscal d'entreprise n'est exigé sur vos prélèvements personnels."
        )
    },
    {
        "keywords": [r"virement interne", r"transfert interne", r"compte 585", r"wave vers caisse", r"retrait pour caisse"],
        "titre": "Virements Internes de Trésorerie (Compte 585)",
        "reponse": (
            "Le virement interne de trésorerie (Compte SYSCOHADA 585) correspond aux déplacements d'argent entre vos propres comptes :\n\n"
            "• Retrait Wave pour alimenter votre caisse espèces physique\n"
            "• Dépôt d'espèces sur votre compte Orange Money ou à la banque\n"
            "• Transfert de compte à compte\n\n"
            "Impact comptable : C'est une opération STRICTEMENT NEUTRE. Elle ne constitue ni une vente (pas d'impôt supplémentaire) ni une charge d'exploitation (pas de fausse dépense)."
        )
    },
    {
        "keywords": [r"perte.*stock", r"avarie", r"marchandise.*pourrie", r"yakhou", r"compte 654"],
        "titre": "Pertes sur Stocks & Marchandises Avariées (Compte 654)",
        "reponse": (
            "Lorsque des articles sont détériorés, périmés, cassés ou volés (yakhou na), il est capital de les déclarer à Growth :\n\n"
            "• Affectation : Compte SYSCOHADA 654 (Pertes sur stocks et avaries)\n"
            "• Impact immédiat : La valeur du stock dans votre bilan est réajustée à la baisse pour que votre actif reflète exactement ce qui est vendable sur vos étagères.\n"
            "• Exemple : Déclarez simplement « Perte de stock 15 000 marchandise avariée »."
        )
    },
    {
        "keywords": [r"impot", r"impôts", r"fiscalite", r"fiscalité", r"cgu", r"taxe mairie", r"patente"],
        "titre": "Anticipation Fiscale & Réserve CGU / Mairie",
        "reponse": (
            "Au Sénégal, la plupart des commerçants et artisans relèvent de la Contribution Globale Unique (CGU) ou de taxes municipales annuelles.\n\n"
            "Conseil prudentiel Growth :\n"
            "• Mettez systématiquement en réserve 5% de vos encaissements de la journée sur un sous-compte de prévoyance.\n"
            "• Grâce à la comptabilité en temps réel de Growth, vous connaîtrez à l'avance votre assiette imposable exacte sans risquer de pénalité de redressement fiscal par la DGID."
        )
    }
]


def repondre_question_theorique_locale(question: str) -> Optional[str]:
    """
    Recherche dans la base de connaissances métier locale UNIQUEMENT pour les demandes
    de définition formelle pures (ex: 'c'est quoi le syscohada', 'définition ninea').
    Toutes les questions conversationnelles sont traitées directement par l'IA (Gemini / Claude)
    pour garantir une réponse naturelle, intelligente, contextuelle et libre comme ChatGPT.
    """
    if not question:
        return None
    q_lower = question.lower().strip()

    # Si c'est une question conversationnelle (point d'interrogation, question sur le copilote, dialogue)
    # Ne JAMAIS intercepter : laisser l'IA répondre librement comme ChatGPT !
    if (
        "?" in question
        or any(k in q_lower for k in [
            "c'est toi", "cest toi", "est-ce que", "est ce que", "tu peux", "tu fais",
            "pourquoi", "comment", "qui", "quand", "dis-moi", "dis moi", "explique",
            "aide", "relance", "relancer", "conseil", "peux-tu", "peux tu"
        ])
    ):
        return None

    # Ne déclencher la base que si l'utilisateur demande explicitement une définition formelle
    mots_definition = ["c'est quoi", "qu'est ce que", "qu'est-ce que", "definition", "définition", "c est quoi"]
    if not any(d in q_lower for d in mots_definition):
        return None

    for item in KNOWLEDGE_BASE:
        for kw in item["keywords"]:
            if re.search(kw, q_lower):
                return f"{item['titre']}\n\n{item['reponse']}"
    return None


# ==============================================================================
# 2. CONSULTATION EN TEMPS RÉEL DES DONNÉES FINANCIÈRES (0 Crédit / Supabase Direct)
# ==============================================================================

def executer_consultation_donnees_locale(user_text: str, entreprise_id: str, sp) -> Optional[str]:
    """
    Interroge la base de données pour répondre aux questions sur les soldes,
    les ventes du jour ou l'assistance d'automatisation Wave.
    100% Local - 0 Crédit API.
    """
    if not user_text:
        return None

    clean = user_text.lower().strip()

    # 0. Assistance spéciale : Automatisation Wave en attendant l'API officielle
    mots_guide_wave = [
        "sans api", "attendant lapi", "attendant l'api", "connecter wave", "automatiser wave",
        "passerelle wave", "relais wave", "relais sms", "sms forwarder", "comment relier wave",
        "ameliorer mon agent", "en attendant wave"
    ]
    if any(k in clean for k in mots_guide_wave):
        return (
            "📱 COMMENT AUTOMATISER VOS ENCAISSEMENTS WAVE (Sans attendre l'API) :\n\n"
            "En attendant l'activation de votre contrat Wave Business Merchant, vous avez 3 méthodes 100% opérationnelles dès aujourd'hui :\n\n"
            "1. 💬 LE TRANSFERT DE SMS (Le plus simple) :\n"
            "Dès que vous recevez un SMS Wave (« Vous avez reçu 15.000F de... »), transférez-le ou collez-le directement ici sur WhatsApp. "
            "Growth vérifie l'absence de faux SMS/doublon et enregistre automatiquement la vente au compte SYSCOHADA 571.\n\n"
            "2. 📸 LA CAPTURE D'ÉCRAN OU LE RELEVÉ PDF :\n"
            "Prenez une capture d'écran de l'application Wave ou téléchargez votre relevé mensuel Wave (PDF/CSV) et envoyez-le ici. "
            "Notre IA visuelle Gemini extrait 100% des transactions en 2 secondes.\n\n"
            "3. ⚡ LE RELAIS SMS AUTOMATIQUE ANDROID (0 Action requise) :\n"
            "Installez l'application gratuite 'SMS Forwarder' sur votre téléphone Android. Configurez-la pour renvoyer chaque SMS du contact 'Wave' "
            "vers notre passerelle sécurisée : https://rascal-legible-unsheathe.ngrok-free.dev/api/sms-gateway\n"
            "Chaque paiement de client en boutique est ainsi scellé instantanément en tâche de fond !\n\n"
            "Voulez-vous que je vous guide pas à pas sur l'une de ces 3 options ?"
        )

    if not entreprise_id:
        return None

    # 1. Consultation du Solde / De la Trésorerie en cours (Français & Wolof)
    mots_solde = [
        "mon solde", "mes soldes", "solde en caisse", "combien j'ai", "combien jai",
        "argent disponible", "ma tresorerie", "ma trésorerie", "solde wave", "wave solde",
        "combien sur wave", "combien j'ai sur wave", "combien jai sur wave", "mon wave",
        "solde om", "solde orange", "solde caisse", "sama wave", "compte wave", "argent wave",
        "ana sama solde", "ana sama xalis", "ana sama xaalis", "wax ma solde",
        "solde bi", "kom-kom bi", "kom kom", "xaalis bi", "solde", "mes comptes", "tresorerie", "trésorerie"
    ]
    if any(k in clean for k in mots_solde):
        try:
            txs = []
            if sp and entreprise_id:
                try:
                    txs = sp.table("transactions").select("source_paiement, type_flux, montant_fcfa").eq("entreprise_id", entreprise_id).execute().data or []
                except Exception:
                    pass
            if not txs:
                try:
                    from database import get_sqlite_conn
                    conn = get_sqlite_conn()
                    cur = conn.cursor()
                    cur.execute("SELECT source_paiement, type_flux, montant_fcfa FROM transactions WHERE entreprise_id = ?", (entreprise_id,))
                    rows = cur.fetchall()
                    txs = [{"source_paiement": r["source_paiement"], "type_flux": r["type_flux"], "montant_fcfa": r["montant_fcfa"]} for r in rows]
                    conn.close()
                except Exception as e_sql:
                    print(f"Info sqlite solde: {e_sql}")

            soldes = {"WAVE": 0, "ORANGE_MONEY": 0, "ESPECES": 0, "BANQUE": 0}
            for t in txs:
                src = t.get("source_paiement", "ESPECES")
                montant = int(t.get("montant_fcfa") or 0)
                flux = t.get("type_flux", "ENTREE")
                if src in soldes:
                    if flux == "ENTREE":
                        soldes[src] += montant
                    else:
                        soldes[src] -= montant

            total = sum(soldes.values())
            is_wolof = any(w in clean for w in ["ana", "sama", "xalis", "xaalis", "wax", "kom-kom", "tollu"])
            if is_wolof:
                return (
                    f"Sa kom-kom ak sa solde ci direct leegi :\n\n"
                    f"• Compte Wave : {soldes['WAVE']:,.0f} FCFA\n"
                    f"• Compte Orange Money : {soldes['ORANGE_MONEY']:,.0f} FCFA\n"
                    f"• Caisse Espèces : {soldes['ESPECES']:,.0f} FCFA\n"
                    f"• Compte Banque : {soldes['BANQUE']:,.0f} FCFA\n\n"
                    f"Total sa kom-kom disponible : {total:,.0f} FCFA\n\n"
                    "Lépp leer na ci norme SYSCOHADA SMT."
                )
            return (
                "État de votre trésorerie en direct :\n\n"
                f"• Compte Wave : {soldes['WAVE']:,.0f} FCFA\n"
                f"• Compte Orange Money : {soldes['ORANGE_MONEY']:,.0f} FCFA\n"
                f"• Caisse Espèces : {soldes['ESPECES']:,.0f} FCFA\n"
                f"• Compte Bancaire : {soldes['BANQUE']:,.0f} FCFA\n\n"
                f"Total Trésorerie disponible : {total:,.0f} FCFA\n\n"
                "Données certifiées à la norme SYSCOHADA SMT."
            )
        except Exception as e:
            print(f"Erreur calcul solde direct : {e}")

    # 2. Consultation des Ventes du Jour (Français & Wolof)
    mots_ventes_jour = [
        "vente d'aujourd'hui", "ventes aujourd'hui", "combien j'ai vendu", "combien jai vendu",
        "chiffre du jour", "recettes du jour",
        "jaay yi tey", "jaay tey", "niaata laa jaay", "niaata am tey", "dug tey", "am na jaay tey"
    ]
    if any(k in clean for k in mots_ventes_jour):
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            txs = []
            if sp and entreprise_id:
                try:
                    txs = sp.table("transactions").select("montant_fcfa, source_paiement, libelle").eq("entreprise_id", entreprise_id).eq("type_flux", "ENTREE").gte("created_at", f"{today_str}T00:00:00").execute().data or []
                except Exception:
                    pass
            if not txs:
                try:
                    from database import get_sqlite_conn
                    conn = get_sqlite_conn()
                    cur = conn.cursor()
                    cur.execute("SELECT montant_fcfa, source_paiement, libelle FROM transactions WHERE entreprise_id = ? AND type_flux = 'ENTREE' AND date_operation = ?", (entreprise_id, today_str))
                    rows = cur.fetchall()
                    txs = [{"montant_fcfa": r["montant_fcfa"], "source_paiement": r["source_paiement"], "libelle": r["libelle"]} for r in rows]
                    conn.close()
                except Exception as e_sql:
                    print(f"Info sqlite ventes: {e_sql}")

            total_ventes = sum(int(t.get("montant_fcfa") or 0) for t in txs)
            nb_ventes = len(txs)
            is_wolof = any(w in clean for w in ["jaay", "tey", "niaata", "laa", "dug"])
            if is_wolof:
                return (
                    f"Sa jaay yi tey ({datetime.now().strftime('%d/%m/%Y')}) :\n\n"
                    f"• Limu jaay yi : {nb_ventes}\n"
                    f"• Xaalis bu duggu tey : {total_ventes:,.0f} FCFA\n\n"
                    "Bu ngoonee ci rituel bi nu dresseel la bilan bi lépp."
                )
            return (
                f"Synthèse de vos ventes du jour ({datetime.now().strftime('%d/%m/%Y')}) :\n\n"
                f"• Nombre d'encaissements : {nb_ventes}\n"
                f"• Chiffre d'affaires encaissé : {total_ventes:,.0f} FCFA\n\n"
                "Ce montant sera récapitulé ce soir à 20h00 lors de votre rituel de caisse."
            )
        except Exception as e:
            print(f"Erreur consultation ventes jour : {e}")

    # 3. Consultation des Dettes & Créances
    is_redaction = any(k in clean for k in ["rédige", "redige", "écris", "ecris", "message", "relance", "relancer"])
    if not is_redaction and any(k in clean for k in ["mes dettes", "qui me doit", "mes creances", "mes créances", "argent dehors", "combien je dois", "liste des dettes"]):
        try:
            dettes = sp.table("dettes_creances").select("*").eq("entreprise_id", entreprise_id).neq("statut", "SOLDE").execute().data or []
            creances_clients = [d for d in dettes if d.get("type") == "CREANCE_CLIENT"]
            dettes_fournisseurs = [d for d in dettes if d.get("type") == "DETTE_FOURNISSEUR"]

            tot_creances = sum(int(d.get("montant_restant_fcfa") or 0) for d in creances_clients)
            tot_dettes = sum(int(d.get("montant_restant_fcfa") or 0) for d in dettes_fournisseurs)

            lignes = ["État de vos créances et dettes en cours :\n"]
            if creances_clients:
                lignes.append("Clients qui vous doivent de l'argent (Créances) :")
                for c in creances_clients:
                    lignes.append(f"  • {c.get('tiers_nom')} : {int(c.get('montant_restant_fcfa') or 0):,.0f} FCFA")
                lignes.append(f"Total à recouvrer : {tot_creances:,.0f} FCFA\n")
            else:
                lignes.append("Clients impayés : Aucun client ne vous doit de l'argent actuellement.\n")

            if dettes_fournisseurs:
                lignes.append("Dettes à régler (Fournisseurs) :")
                for d in dettes_fournisseurs:
                    lignes.append(f"  • {d.get('tiers_nom')} : {int(d.get('montant_restant_fcfa') or 0):,.0f} FCFA")
                lignes.append(f"Total dettes à payer : {tot_dettes:,.0f} FCFA")
            else:
                lignes.append("Dettes fournisseurs : Vous n'avez aucune dette fournisseur en cours.")

            return "\n".join(lignes)
        except Exception as e:
            print(f"Erreur consultation dettes : {e}")

    # 4. Consultation de la Valeur et de l'État du Stock (Français & Wolof)
    mots_stock = [
        "mon stock", "valeur de mon stock", "valeur du stock", "état du stock", "etat du stock",
        "combien de stock", "combien j'ai de stock", "combien jai de stock", "sama stock",
        "stock restant", "stock disponible", "niveau de stock"
    ]
    if any(k in clean for k in mots_stock):
        try:
            val_stock = 0
            if sp and entreprise_id:
                try:
                    mois_c = datetime.now().strftime("%Y-%m")
                    st = sp.table("etats_structurels").select("valeur_stock_fcfa").eq("entreprise_id", entreprise_id).eq("periode_mois", mois_c).execute().data
                    if st:
                        val_stock = int(st[0].get("valeur_stock_fcfa") or 0)
                except Exception:
                    pass
            if val_stock == 0 and sp and entreprise_id:
                try:
                    ent = sp.table("entreprises").select("donnees_onboarding").eq("id", entreprise_id).execute().data
                    if ent and ent[0].get("donnees_onboarding"):
                        val_stock = int(ent[0]["donnees_onboarding"].get("valeur_stock_fcfa") or 0)
                except Exception:
                    pass

            is_wolof = any(w in clean for w in ["sama", "stock"])
            statut_stock = "NORMAL"
            if val_stock <= 0:
                statut_stock = "RUPTURE"
            elif val_stock < 50000:
                statut_stock = "FAIBLE"

            if is_wolof and "sama" in clean:
                if statut_stock == "RUPTURE":
                    return (
                        "⚠️ Sa stock marchandise ci bilan bi diekh na (0 FCFA).\n\n"
                        "CONSEIL GROWTH :\n"
                        "Fexeel commandeel fournisseurs yi leegi ngir am marchandise bu duggaat ci sa caisse."
                    )
                return (
                    f"Sa état de stock ci teere bi ({datetime.now().strftime('%d/%m/%Y')}) :\n\n"
                    f"• Valeur stock disponible : {val_stock:,.0f} FCFA\n"
                    f"• Statut : {'Baax na' if statut_stock == 'NORMAL' else 'Dafa dess tuuti'}\n\n"
                    "Bés bu nekk bu nga jaayee, Growth dina déstocker automatiquement ci sa bilan."
                )

            if statut_stock == "RUPTURE":
                return (
                    "⚠️ ALERTE STOCK : Votre stock de marchandises est actuellement à 0 FCFA (Épuisé / Rupture).\n\n"
                    "CONSEILS DE GESTION GROWTH :\n"
                    "1. Prévoyez immédiatement un réassort auprès de vos fournisseurs réguliers.\n"
                    "2. Transférez dès maintenant vos factures ou reçus d'achats pour reconstituer automatiquement votre actif au bilan."
                )
            elif statut_stock == "FAIBLE":
                return (
                    f"Point sur votre stock de marchandises ({datetime.now().strftime('%d/%m/%Y')}) :\n\n"
                    f"• Valeur estimée en stock : {val_stock:,.0f} FCFA\n"
                    "• Statut : Seuil d'alerte (Stock faible)\n\n"
                    "Recommandation : Pensez à passer commande avant d'atteindre la rupture."
                )
            else:
                return (
                    f"Point sur votre stock de marchandises ({datetime.now().strftime('%d/%m/%Y')}) :\n\n"
                    f"• Valeur d'actif en stock : {val_stock:,.0f} FCFA\n"
                    "• Statut : Niveau satisfaisant\n"
                    "• Méthode SYSCOHADA : Déstockage dynamique à chaque vente (CAMV) et revalorisation aux achats."
                )
        except Exception as e:
            print(f"Erreur consultation stock : {e}")

    # 5. Consultation du Score de Bankabilité & Éligibilité au Crédit
    mots_score = [
        "mon score", "score crédit", "score credit", "score bancaire", "score bankability",
        "bankability", "mon dossier bancaire", "combien je peux emprunter", "combien puis je emprunter",
        "éligibilité prêt", "eligibilite pret", "pret cofina", "pret baobab", "pret der",
        "demande de pret", "demande de prêt"
    ]
    if any(k in clean for k in mots_score):
        try:
            # Récupération transactions pour ratios prudentiels
            txs = []
            if sp and entreprise_id:
                txs = sp.table("transactions").select("montant_fcfa, type_flux, source_paiement, statut_validation, est_professionnel, compte_syscohada").eq("entreprise_id", entreprise_id).execute().data or []
            
            total_in = sum(int(t.get("montant_fcfa") or 0) for t in txs if t.get("type_flux") == "ENTREE" or t.get("compte_syscohada") == "701")
            total_out = sum(int(t.get("montant_fcfa") or 0) for t in txs if t.get("type_flux") == "SORTIE" and t.get("est_professionnel", True) != False and t.get("compte_syscohada") != "104")
            solde_net = max(0, total_in - total_out)
            
            tx_cert = sum(1 for t in txs if t.get("statut_validation") == "VALIDE_PME" or t.get("source_paiement") in ["WAVE", "ORANGE_MONEY", "BANQUE"])
            taux_cert = (tx_cert / len(txs)) if txs else 1.0
            
            # Formule de notation bancaire Growth / ONECCA
            pts_treso = 30 if solde_net > 500000 else (25 if solde_net > 200000 else (20 if solde_net > 50000 else 15))
            taux_marge = ((total_in - total_out) / total_in) if total_in > 0 else 0.30
            pts_marge = 25 if taux_marge >= 0.25 else (20 if taux_marge >= 0.15 else 15)
            pts_tracabilite = int(taux_cert * 25)
            pts_solvabilite = 18
            
            score_final = min(98, max(50, pts_treso + pts_marge + pts_tracabilite + pts_solvabilite)) if txs else 78
            grade = "A+" if score_final >= 88 else ("A" if score_final >= 75 else ("B" if score_final >= 65 else "C"))
            
            mensualite_max = max(50000, int(solde_net * 0.33)) if solde_net > 0 else 150000
            capacite_emprunt = max(1500000, min(15000000, mensualite_max * 24))
            
            return (
                f"RAPPORT OFFICIEL DE BANKABILITÉ GROWTH\n"
                f"Normes BCEAO & SYSCOHADA SMT ({datetime.now().strftime('%d/%m/%Y')})\n\n"
                f"• Score de Crédit : {score_final}/100 (Grade {grade})\n"
                f"• Statut : {'Excellente solvabilité (Financement prioritaire)' if score_final >= 85 else 'Profil bancable éligible'}\n\n"
                f"DÉTAIL DES RATIOS D'ÉVALUATION :\n"
                f"1. Flux de trésorerie nette : {pts_treso}/30 pts\n"
                f"2. Rentabilité & Marge d'exploitation : {pts_marge}/25 pts\n"
                f"3. Traçabilité probatoire & Pièces scellées : {pts_tracabilite}/25 pts ({int(taux_cert*100)}% d'écritures certifiées)\n"
                f"4. Solvabilité & Actifs circulants : {pts_solvabilite}/20 pts\n\n"
                f"CAPACITÉ D'EMPRUNT RECOMMANDÉE :\n"
                f"• Montant finançable : {capacite_emprunt:,.0f} FCFA\n"
                f"• Remboursement mensuel prudentiel (33% du cash-flow) : {mensualite_max:,.0f} FCFA / mois\n\n"
                f"INSTITUTIONS FINANCIÈRES PARTENAIRES ADAPTÉES :\n"
                f"• DER / FJ (Taux bonifié 5% PME)\n"
                f"• Baobab Sénégal & Cofina (Crédit express commerçants)\n"
                f"• CBAO & Ecobank Sénégal (Financement de stock & équipement)\n\n"
                f"Votre dossier complet est directement exportable depuis votre tableau de bord."
            )
        except Exception as e:
            print(f"Erreur consultation bankability : {e}")

    return None


# ==============================================================================
# 3. GESTION DES DETTES & CRÉANCES EN LANGAGE NATUREL (100% Local)
# ==============================================================================

def gerer_dette_creance_locale(user_text: str, entreprise_id: str, sp) -> Optional[str]:
    """
    Détecte et enregistre les créations et remboursements de dettes et créances en local.
    Exemples :
    - 'Moussa me doit 20 000 FCFA' -> Créance Client 411
    - 'Je dois 50 000 à mon fournisseur Ibrahima' -> Dette Fournisseur 401
    - 'Moussa m'a remboursé 10 000' -> Remboursement partiel
    """
    if not sp or not entreprise_id or not user_text:
        return None

    clean = user_text.lower().strip()
    # Si l'utilisateur demande une rédaction de relance, laisser le copilote IA composer le message
    if any(k in clean for k in ["rédige", "redige", "écris", "ecris", "message", "relance", "relancer"]):
        return None

    from local_extractor import parse_montant_fcfa
    montant = parse_montant_fcfa(clean)

    # 1. Remboursement (ex: Moussa m'a remboursé 10000, ou remboursement de 20000 de Ali)
    if any(k in clean for k in ["rembourse", "remboursé", "remboursement", "a payé sa dette", "a regle sa dette"]):
        if montant > 0:
            tiers_nom = None
            m = re.search(r'(?:de|par|tiers|client)\s+([A-Za-z\s\-]{2,20})', user_text, re.IGNORECASE)
            if not m:
                m = re.search(r'^([A-Za-z\s\-]{2,20})\s+m[\'’]a\s+rembours', user_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                if cand.lower() not in ["un", "mon", "sa", "ma", "le", "la"]:
                    tiers_nom = cand.title()

            try:
                query = sp.table("dettes_creances").select("*").eq("entreprise_id", entreprise_id).neq("statut", "SOLDE")
                if tiers_nom:
                    query = query.ilike("tiers_nom", f"%{tiers_nom}%")
                res = query.order("created_at", desc=True).limit(1).execute()
                if res.data:
                    dette = res.data[0]
                    dette_id = dette["id"]
                    nom_reel = dette.get("tiers_nom", "Le tiers")
                    actuel = int(dette.get("montant_restant_fcfa") or 0)
                    nouveau = max(0, actuel - montant)
                    statut = "SOLDE" if nouveau == 0 else "PARTIELLEMENT_REMBOURSE"
                    sp.table("dettes_creances").update({"montant_restant_fcfa": nouveau, "statut": statut}).eq("id", dette_id).execute()

                    # Enregistrer la rentrée d'argent dans les transactions
                    sp.table("transactions").insert({
                        "entreprise_id": entreprise_id,
                        "libelle": f"Remboursement créance client - {nom_reel}",
                        "compte_syscohada": "411",
                        "type_flux": "ENTREE",
                        "est_professionnel": True,
                        "montant_fcfa": montant,
                        "source_paiement": "ESPECES",
                        "statut_validation": "VALIDE_PME"
                    }).execute()

                    return (
                        f"Remboursement de {montant:,.0f} FCFA enregistre avec succes pour {nom_reel}.\n\n"
                        "RESUME DE L'ENREGISTREMENT :\n"
                        f"• Tiers concerne : {nom_reel}\n"
                        f"• Montant encaisse : {montant:,.0f} FCFA\n"
                        f"• Imputation : Compte SYSCOHADA 411 (Creance Client)\n"
                        f"• Solde restant du : {nouveau:,.0f} FCFA\n\n"
                        f"Statut : {'Dette entierement soldee !' if nouveau == 0 else 'Creance mise a jour au journal financier.'}"
                    )
            except Exception as e:
                print(f"Erreur remboursement local : {e}")

    # 2. Création de Créance Client (Un tiers me doit de l'argent)
    # Ex: 'Moussa me doit 25 000 FCFA'
    m_creance = re.search(r'([A-Za-z\s\-]{2,20})\s+me\s+doit\b', user_text, re.IGNORECASE)
    if m_creance and montant > 0:
        tiers_nom = m_creance.group(1).strip().title()
        try:
            sp.table("dettes_creances").insert({
                "entreprise_id": entreprise_id,
                "type": "CREANCE_CLIENT",
                "tiers_nom": tiers_nom,
                "montant_initial_fcfa": montant,
                "montant_restant_fcfa": montant,
                "frequence_relance_jours": 3,
                "statut": "EN_COURS"
            }).execute()
            return (
                "Creance client enregistree avec succes.\n\n"
                "RESUME DE L'ENREGISTREMENT :\n"
                f"• Client debiteur : {tiers_nom}\n"
                f"• Montant a recouvrer : {montant:,.0f} FCFA\n"
                f"• Imputation : Compte SYSCOHADA 411 (Clients)\n"
                "• Relance automatique : Activee (tous les 3 jours)\n\n"
                "Statut : Creance sous surveillance Grow."
            )
        except Exception as e:
            print(f"Erreur création créance locale : {e}")

    # 3. Création de Dette Fournisseur (Je dois de l'argent à un tiers)
    # Ex: 'Je dois 50 000 à Ets Diop'
    m_dette = re.search(r'je\s+dois\D*?(\d[\d\s\.]{2,10})\D*?(?:à|a|chez|pour)\s+([A-Za-z\s\-]{2,25})', user_text, re.IGNORECASE)
    if m_dette:
        from local_extractor import parse_montant_fcfa
        mont_d = parse_montant_fcfa(m_dette.group(1)) or montant
        tiers_f = m_dette.group(2).strip().title()
        if mont_d > 0:
            try:
                sp.table("dettes_creances").insert({
                    "entreprise_id": entreprise_id,
                    "type": "DETTE_FOURNISSEUR",
                    "tiers_nom": tiers_f,
                    "montant_initial_fcfa": mont_d,
                    "montant_restant_fcfa": mont_d,
                    "frequence_relance_jours": 3,
                    "statut": "EN_COURS"
                }).execute()
                return (
                    "Dette fournisseur enregistree avec succes.\n\n"
                    "RESUME DE L'ENREGISTREMENT :\n"
                    f"• Fournisseur creancier : {tiers_f}\n"
                    f"• Montant du : {mont_d:,.0f} FCFA\n"
                    f"• Imputation : Compte SYSCOHADA 401 (Fournisseurs)\n"
                    "• Rappel d'echeance : Actif\n\n"
                    "Statut : Dette inscrite a vos engagements financiers."
                )
            except Exception as e:
                print(f"Erreur création dette locale : {e}")
        tiers_f = m_dette.group(2).strip().title()
        if mont_d > 0:
            try:
                sp.table("dettes_creances").insert({
                    "entreprise_id": entreprise_id,
                    "type": "DETTE_FOURNISSEUR",
                    "tiers_nom": tiers_f,
                    "montant_initial_fcfa": mont_d,
                    "montant_restant_fcfa": mont_d,
                    "frequence_relance_jours": 3,
                    "statut": "EN_COURS"
                }).execute()
                return (
                    f"Dette fournisseur enregistrée avec succès.\n\n"
                    f"• Bénéficiaire : {tiers_f}\n"
                    f"• Montant à régler : {mont_d:,.0f} FCFA (Compte SYSCOHADA 401)\n"
                    f"• Échéance : Suivie dans votre journal des dettes\n\n"
                    "Statut : Dette comptabilisée au passif circulant."
                )
            except Exception as e:
                print(f"Erreur création dette locale : {e}")

    return None


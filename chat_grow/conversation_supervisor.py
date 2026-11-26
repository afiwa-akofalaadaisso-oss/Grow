"""
Grow MVP - Superviseur Conversationnel Intelligent & Souplesse Humaine (Gemini 3.1 Flash Lite)
Permet à Growth de dialoguer avec la finesse, la pédagogie et la liberté de réflexion de ChatGPT :
- Comprendre et expliquer n'importe quelle question comptable, juridique ou technique (NINEA, SYSCOHADA, Wave, tarifs, sécurité).
- Corriger et modifier une information passée sans réinitialiser ni bloquer.
- Sauter une étape ou reporter à plus tard sans insister.
- Comprendre le Wolof, le Français et le mélange des deux naturellement.
"""

import os
import re
import json
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)


def get_gemini_client():
    """Initialise le client Google GenAI."""
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Erreur initialisation Gemini: {e}")
        return None


def get_description_etape(etape: str, onboarding: dict) -> str:
    """Fournit une description contextuelle précise de l'étape active pour le LLM."""
    nom_ent = onboarding.get("nom_entreprise") or onboarding.get("nom_entreprise_detecte") or "votre entreprise"

    if etape in ["PHASE_1_ACCUEIL", "DEMANDE_MODE"]:
        return (
            "ÉTAPE : ACCUEIL ET CHOIX DU MODE D'ÉCHANGE.\n"
            "Action attendue : Choisir son mode d'échange entre 1) Note vocale ou 2) Par écrit."
        )
    if etape == "PHASE_2_NUMERO_SECONDAIRE":
        return (
            f"ÉTAPE : RACCORDEMENT DU DEUXIÈME OPÉRATEUR (Entreprise: {nom_ent}).\n"
            "Action attendue : Donner son numéro Orange Money ou dire 'Non, Wave seulement'."
        )
    if etape == "PHASE_2_CHOIX_OPERATEURS":
        return (
            f"ÉTAPE : CHOIX DES OPÉRATEURS & COMPTES BANCAIRES/MOBILES (Entreprise: {nom_ent}).\n"
            "Action attendue : Choisir son statut (Wave Business, Orange Business, Comptes Personnels, Mixte)."
        )
    if etape in ["PHASE_3_IDENTIFICATION_NINEA", "PHASE_2_CREATION_ENTREPRISE", "DEMANDE_NINEA"]:
        return (
            f"ÉTAPE : IDENTITÉ OFFICIELLE & NINEA/RCCM (Entreprise: {nom_ent}).\n"
            "Action attendue : Envoyer la photo du NINEA/RCCM ou dire simplement 'Non' / 'Pas encore' (c'est optionnel pour démarrer)."
        )
    if etape in ["PHASE_3_NOM_COMMERCIAL_SANS_NINEA", "PHASE_3_NOM_COMMERCIAL"]:
        return (
            f"ÉTAPE : NOM COMMERCIAL / ENSEIGNE DE L'ENTREPRISE (Entreprise: {nom_ent}).\n"
            "Action attendue : Donner le nom ou l'enseigne de son entreprise (ex: 'Keur Fatou Cosmétiques', 'Atelier Diallo Couture')."
        )
    if etape == "PHASE_3_QUESTION_CABINET":
        return (
            f"ÉTAPE : SUPERVISION PAR UN CABINET COMPTABLE PARTENAIRE (Entreprise: {nom_ent}).\n"
            "Action attendue : Dire s'il travaille déjà avec un cabinet comptable (donner le nom) ou dire 'Non' / 'Aucun'."
        )
    if etape == "PHASE_3_CHOIX_PROPOSITION_CABINET":
        return (
            f"ÉTAPE : RATTACHEMENT À UN CABINET COMPTABLE PARTENAIRE AGRÉÉ (Entreprise: {nom_ent}).\n"
            "Action attendue : Répondre 1 (Oui pour être rattaché) ou 2 (Non pour gestion autonome)."
        )
    if etape == "PHASE_2_CAPITAL_INITIAL":
        return (
            f"ÉTAPE : CAPITAL DE DÉPART DE L'ENTREPRISE (Entreprise: {nom_ent}).\n"
            "Action attendue : Indiquer le montant approximatif du capital investi en FCFA (ex: 500 000 FCFA ou dire 'Zéro')."
        )
    if etape in ["PHASE_3_RELEVE", "PHASE_3_BILAN_DEPART"]:
        return (
            f"ÉTAPE : RECONSTITUTION TRÉSORERIE DE DÉPART (Entreprise: {nom_ent}).\n"
            "Action attendue : Envoyer capture d'écran Wave/OM/banque ou déclarer ses soldes actuels (Wave, Orange, espèces)."
        )
    if etape == "PHASE_3_STOCK":
        return (
            f"ÉTAPE : VALEUR ESTIMÉE DU STOCK (Entreprise: {nom_ent}).\n"
            "Action attendue : Indiquer la valeur estimée des marchandises en FCFA (ou dire '0' / 'aucun stock')."
        )
    if etape == "PHASE_3_MATERIEL":
        return (
            f"ÉTAPE : MATÉRIEL ET ÉQUIPEMENTS PROFESSIONNELS (Entreprise: {nom_ent}).\n"
            "Action attendue : Citer ses machines/outils/véhicules (ou dire 'aucun' / 'non')."
        )
    if etape == "PHASE_3_DETTES":
        return (
            f"ÉTAPE : DETTES FOURNISSEURS & CRÉANCES CLIENTS (Entreprise: {nom_ent}).\n"
            "Action attendue : Indiquer ses dettes ou créances en cours (ou dire 'aucune' / 'rien')."
        )
    if etape == "PHASE_4_RAPPEL_JOURNEE":
        return (
            f"ÉTAPE : VALIDATION DU RITUEL DE CLÔTURE DU SOIR À 21H (Entreprise: {nom_ent}).\n"
            "Action attendue : Confirmer qu'on est prêt à démarrer en disant 'Oui' ou 'Prêt'."
        )
    return f"ÉTAPE : ACCOMPAGNEMENT PERMANENT (Entreprise: {nom_ent})."


def prompt_rappel_etape(etape: str, onboarding: dict) -> str:
    """Retourne la question de l'étape active formulée avec courtoisie pour relancer après une explication."""
    nom_ent = onboarding.get("nom_entreprise") or onboarding.get("nom_entreprise_detecte") or "votre entreprise"

    if etape in ["PHASE_1_ACCUEIL", "DEMANDE_MODE"]:
        return (
            "Vous pouvez m'écrire par message ou m'envoyer directement des notes vocales en français ou en wolof à tout moment !"
        )
    if etape == "PHASE_2_NUMERO_SECONDAIRE":
        return (
            "Avez-vous également un numéro pour Orange Money à relier à votre compte ?\n"
            "(Si vous utilisez Wave seulement, dites-le moi simplement)."
        )
    if etape == "PHASE_2_CHOIX_OPERATEURS":
        return (
            "Utilisez-vous principalement Wave Business, Orange Business, ou vos comptes personnels ?"
        )
    if etape in ["PHASE_3_IDENTIFICATION_NINEA", "PHASE_2_CREATION_ENTREPRISE", "DEMANDE_NINEA"]:
        return (
            "Avez-vous un document NINEA ou Registre de Commerce (RCCM) pour votre entreprise ?\n"
            "(Si vous n'en avez pas encore, ce n'est pas bloquant, dites-moi simplement « Pas encore »)."
        )
    if etape in ["PHASE_3_NOM_COMMERCIAL_SANS_NINEA", "PHASE_3_NOM_COMMERCIAL"]:
        return "Quel est le nom ou l'enseigne de votre entreprise ?"
    if etape in ["PHASE_3_QUESTION_CABINET", "PHASE_3_CHOIX_PROPOSITION_CABINET"]:
        return (
            "Travaillez-vous déjà avec un cabinet comptable ? (Si oui, quel est son nom ? Sinon, répondez simplement « Non »)."
        )
    if etape == "PHASE_2_ACTIVITE_LOCALISATION":
        return (
            "Quelle est votre activité exacte (ce que vous vendez ou vos services) et où se trouve votre entreprise ou atelier (quartier, marché, ville) ?\n"
            "(Exemple : « Alimentation Générale au Marché Sandaga, Dakar » ou « Atelier Couture à Thiès »)."
        )
    if etape == "PHASE_2_CAPITAL_INITIAL":
        return (
            "Quel est le capital approximatif (en FCFA) que vous avez investi pour démarrer votre activité ?\n"
            "(Exemple : « 500 000 FCFA », ou dites « Zéro » si vous avez démarré sans capital)."
        )
    if etape in ["PHASE_3_RELEVE", "PHASE_3_BILAN_DEPART"]:
        return (
            "Pour votre bilan de départ, combien avez-vous actuellement sur votre compte Wave / Orange Money et dans votre caisse en espèces ?\n"
            "(Ou envoyez simplement une capture d'écran de votre solde)."
        )
    if etape == "PHASE_3_STOCK":
        return (
            "Quelle est la valeur estimée de votre stock de marchandises actuel ?\n"
            "(Si vous n'avez pas de stock ou si vous faites du service, dites simplement « Zéro »)."
        )
    if etape == "PHASE_3_MATERIEL":
        return (
            "Avez-vous du matériel professionnel ou des équipements (machines, véhicules, frigos, ordinateurs) ?\n"
            "(Si vous n'en avez pas, dites simplement « Non »)."
        )
    if etape == "PHASE_3_DETTES":
        return (
            "Avez-vous des dettes fournisseurs à payer ou des créances clients à récupérer ?\n"
            "(Si vous n'en avez pas, dites simplement « Aucune »)."
        )
    if etape == "PHASE_4_RAPPEL_JOURNEE":
        return (
            "Êtes-vous prêt pour vos rappels de clôture chaque soir à 21h00 ?\n"
            "👉 Répondez simplement « Oui » ou « Prêt » pour valider !"
        )
    return "Je reste à votre écoute pour enregistrer vos opérations au quotidien !"


def sauter_vers_etape_suivante(etape_actuelle: str, onboarding: dict) -> tuple[str, str]:
    """
    Détermine l'étape suivante lorsque l'utilisateur demande de sauter ou reporter.
    Retourne (nouvelle_etape, message_transition).
    """
    nom_ent = onboarding.get("nom_entreprise") or onboarding.get("nom_entreprise_detecte") or "votre entreprise"

    if etape_actuelle in ["PHASE_1_ACCUEIL", "DEMANDE_MODE"]:
        return "PHASE_2_CREATION_ENTREPRISE", (
            "Pas de problème, nous utiliserons les messages écrits par défaut (vous pourrez changer pour les notes vocales à tout moment).\n\n"
            + prompt_rappel_etape("PHASE_2_CREATION_ENTREPRISE", onboarding)
        )
    if etape_actuelle == "PHASE_2_NUMERO_SECONDAIRE":
        return "PHASE_2_CREATION_ENTREPRISE", (
            "C'est noté, nous restons configurés sur vos encaissements Wave Business actuels !\n\n"
            + prompt_rappel_etape("PHASE_2_CREATION_ENTREPRISE", onboarding)
        )
    if etape_actuelle in ["PHASE_2_CREATION_ENTREPRISE", "DEMANDE_NINEA"]:
        return "PHASE_3_RELEVE", (
            "Très bien, on met le NINEA de côté pour le moment. Vous pourrez le rattacher plus tard quand vous le souhaiterez !\n\n"
            + prompt_rappel_etape("PHASE_3_RELEVE", onboarding)
        )
    if etape_actuelle in ["PHASE_3_RELEVE", "PHASE_3_BILAN_DEPART"]:
        return "PHASE_3_STOCK", (
            "D'accord, nous partons avec une trésorerie initiale à zéro et nous enregistrerons vos flux au fur et à mesure.\n\n"
            + prompt_rappel_etape("PHASE_3_STOCK", onboarding)
        )
    if etape_actuelle == "PHASE_3_STOCK":
        return "PHASE_3_MATERIEL", (
            "C'est noté, stock fixé à 0 FCFA pour le moment.\n\n"
            + prompt_rappel_etape("PHASE_3_MATERIEL", onboarding)
        )
    if etape_actuelle == "PHASE_3_MATERIEL":
        return "PHASE_3_DETTES", (
            "C'est noté, aucun équipement lourd enregistré pour le moment.\n\n"
            + prompt_rappel_etape("PHASE_3_DETTES", onboarding)
        )
    if etape_actuelle == "PHASE_3_DETTES":
        return "PHASE_4_RAPPEL_JOURNEE", (
            "C'est noté, aucune dette ni créance de départ.\n\n"
            + prompt_rappel_etape("PHASE_4_RAPPEL_JOURNEE", onboarding)
        )
    if etape_actuelle == "PHASE_4_RAPPEL_JOURNEE":
        return "TERMINE", (
            f"Félicitations ! « {nom_ent} » entre officiellement dans la Phase 5 de Growth : votre copilote financier et comptable permanent.\n\n"
            "Vous pouvez dès à présent m'envoyer vos ventes, vos dépenses ou vos questions financières."
        )

    return "TERMINE", "C'est bien noté, nous passons à la suite !"


async def superviser_message_onboarding(
    sender_phone: str,
    user_text: str,
    etape_actuelle: str,
    onboarding: dict,
    contact_name: str = None
) -> dict:
    """
    Cerveau Conversationnel Intelligent (Gemini 3.1 Flash Lite) :
    Analyse le message de l'utilisateur avec toute la souplesse, la finesse d'esprit
    et la pédagogie de ChatGPT.
    """
    if not user_text or not user_text.strip():
        return {"action": "PASSTHROUGH_REPONSE_ETAPE"}

    u_txt = user_text.strip()
    u_low = u_txt.lower()

    # Raccourcis directs évidents (ex: juste "1", "2", ou un numéro pur de 9 chiffres)
    if etape_actuelle in ["PHASE_1_ACCUEIL", "DEMANDE_MODE"]:
        if u_low in ["1", "1)", "1.", "vocal", "2", "2)", "2.", "ecrit", "écrit"]:
            return {"action": "PASSTHROUGH_REPONSE_ETAPE"}
        chiffres = re.sub(r"[^\d]", "", u_txt)
        if len(chiffres) >= 9 and len(u_txt.split()) <= 2:
            return {"action": "PASSTHROUGH_REPONSE_ETAPE"}

    client = get_gemini_client()
    if not client:
        return {"action": "PASSTHROUGH_REPONSE_ETAPE"}

    contexte_etape = get_description_etape(etape_actuelle, onboarding)
    nom_ent = onboarding.get("nom_entreprise") or onboarding.get("nom_entreprise_detecte") or "Entreprise"
    dernier_msg_growth = onboarding.get("dernier_message_envoye") or ""

    try:
        from database import format_chat_history_for_llm
        history_50 = format_chat_history_for_llm(sender_phone, limit=50)
    except Exception:
        history_50 = ""

    contexte_dialogue = ""
    if history_50:
        contexte_dialogue = f"\n- Historique complet des échanges avec ce commerçant (50 derniers messages) :\n{history_50}\n"
    elif dernier_msg_growth:
        contexte_dialogue = f"\n- Question ou message précédent envoyé par Growth au commerçant : « {dernier_msg_growth} »"

    system_prompt = f"""Tu es Growth, le copilote financier et comptable intelligent (SYSCOHADA) pour les PME et commerçants au Sénégal (Dakar).
Tu es doté d'une intelligence conversationnelle vivante, bienveillante, respectueuse (Teranga sénégalaise) et pédagogique, EXACTEMENT COMME CHATGPT.
Tu t'exprimes avec clarté, sans jargon inutile, et tu comprends parfaitement le Wolof urbain dakarois, le Français, et le mélange des deux.

CONNAISSANCES JURIDIQUES & FISCALES AU SÉNÉGAL (À UTILISER AVEC EXACTITUDE) :
- Formalisation d'une Entreprise Individuelle à l'APIX / Greffe du Tribunal (RCCM + NINEA délivrés en 24h-48h) :
  * Mode 14 000 FCFA : En nom propre (sans nom commercial) = 10 000 F greffe + 4 000 F timbres fiscaux.
  * Mode 24 000 FCFA : Avec nom commercial / enseigne protégée OAPI = 10 000 F greffe + 10 000 F dépôt OAPI + 4 000 F timbres fiscaux.
  * Pièces requises : 2 copies CNI + Certificat de résidence + Casier judiciaire (ou attestation sur l'honneur remplie sur place) + 2 timbres de 2 000 F.
  * Ce document n'est pas bloquant pour démarrer ses écritures sur Growth, mais indispensable pour certifier son bilan et obtenir un prêt bancaire.

RÈGLES FONDAMENTALES :
1. CONTINUITÉ DU DIALOGUE & INTERDICTION D'EXCUSES INUTILES :
   - Si Growth a précédemment posé une question au commerçant (par exemple : sur ses ventes, sa visibilité, son stock ou sa trésorerie) et que le commerçant répond simplement "non", "pas tout à fait", "oui", "un peu", ou "je ne sais pas" :
     C'EST UNE RÉPONSE DIRECTE À LA QUESTION DE GROWTH !
     INTERDICTION ABSOLUE de t'excuser pour une "incompréhension" ou de demander "quel point n'est pas clair" !
     Poursuis la conversation avec empathie et conseille-le positivement :
     Exemple : "Ce n'est pas grave du tout, c'est justement la mission de Growth ! Pour que je vous calcule votre visibilité et votre chiffre d'affaires, envoyez-moi simplement vos premières ventes ou transférez vos SMS Wave / Orange Money."
2. Bannissement absolu des mots "boutique" et "commerce" : utilise toujours "entreprise", "activité", "structure" ou "atelier" (tous les clients ne font pas du commerce de marchandise, certains sont prestataires, artisans, agences).
3. Bannissement du mot "pré-comptable" : utilise "comptable" ou "copilote financier".
4. Tu ne dois JAMAIS être un robot rigide. Si le commerçant :
   - Pose une question (ex: "C'est quoi le NINEA ?", "Pourquoi vous me demandez ça ?", "C'est payant ?", "Est-ce sécurisé ?", "Qui êtes-vous ?"), réponds avec pédagogie, empathie et précision.
   - Veut modifier ou corriger quelque chose du passé (ex: "Je me suis trompé sur le nom, mets plutôt Keur Fatou", "Je préfère les notes vocales", "Change mon numéro"), comprends et extrait la correction.
   - Veut sauter l'étape ou remettre à plus tard (ex: "On verra plus tard", "Saute ça", "Passe à la suite", "Je sais pas", "Dinaa ko def ëllëk"), accepte avec bienveillance sans bloquer.
   - Salue poliment ("Bonjour comment tu vas", "Merci beaucoup"), réponds chaleureusement.
   - Répond normalement à l'étape en cours, identifie qu'il s'agit d'une réponse valide.
5. DISSOCIATION WHATSAPP & WEBHOOK / API :
   - Si l'utilisateur fait remarquer ou demande s'il peut écrire depuis n'importe quel numéro WhatsApp et fournir le Webhook ou l'API d'un compte marchand :
     CONFIRME AVEC FORCE ET PÉDAGOGIE : C'est exactement comme cela que Growth fonctionne !
     Le numéro WhatsApp personnel sert de salon de commande pour recevoir les alertes et clôturer la caisse à 20h00.
     Les encaissements Wave Business et Orange Business sont captés directement par le Webhook / l'API du compte marchand officiel.
   - INTERDICTION ABSOLUE de proposer de ton propre chef un "numéro de magasin" ou de demander des numéros annexes à l'Étape 1 ou 2 : à l'étape 1, on demande uniquement le choix du mode (Vocal ou Écrit), et à l'étape 2 le choix de l'opérateur (A, B, C, D, E).

6. RÈGLE D'OR SUR LE BILAN (LÉGALITÉ & DÉONTOLOGIE COMPTABLE) :
   - Growth NE GÉNÈRE PAS lui-même les bilans de l'entreprise !
   - Growth prépare rigoureusement les écritures et pièces (caisse, Wave, Orange Money), puis FAIT PARVENIR LA DEMANDE DE BILAN À TON CABINET COMPTABLE partenaire.
   - Dès que le cabinet examine et appose son visa officiel, tu reçois ton bilan certifié en PDF directement ici dans notre discussion WhatsApp.
   - INTERDICTION STRICTE de dire "je génère tes bilans" ou "je fais ton bilan".
   - Dis toujours : "Je prépare tes comptes et je fais parvenir la demande à ton cabinet comptable partenaire, et dès que c'est fait et visé, tu le reçois directement ici dans la discussion."

CONTEXTE ACTUEL :
- Nom de l'entreprise : {nom_ent}
- Étape active dans l'onboarding : {etape_actuelle}{contexte_dialogue}
- Description de l'étape :
{contexte_etape}

Réponds STRICTEMENT au format JSON valide suivant :
{{
  "intention": "QUESTION_EXPLICATION" | "CORRECTION_RETOUR" | "SAUTER_ETAPE" | "REPONSE_ETAPE" | "SALUTATION_COURTOISIE",
  "langue": "fr" | "wo",
  "explication_pedagogique": "Ta réponse explicative détaillée, humaine, rassurante et chaleureuse si l'utilisateur a posé une question ou salué. Sinon null.",
  "correction_champ": "nom_entreprise" | "mode_communication" | "numero_magasin" | "numero_orange_money" | "stock" | "tresorerie" | null,
  "valeur_corrigee": "nouvelle valeur propre extraite si correction demandée, sinon null",
  "reponse_etape_extraite": "valeur propre extraite si l'utilisateur répondait à l'étape active dans une phrase complète, sinon null"
}}"""

    user_query = f"""Message de l'utilisateur ({sender_phone}) :
« {u_txt} »

Analyse ce message en tenant compte du dialogue précédent et génère le JSON strict :"""

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-3.1-flash-lite",
            contents=[system_prompt, user_query]
        )
        raw_text = response.text.strip()
        m = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if not m:
            return {"action": "PASSTHROUGH_REPONSE_ETAPE"}

        res = json.loads(m.group(0))
        intention = res.get("intention")

        # 1. CAS QUESTION_EXPLICATION ou SALUTATION_COURTOISIE
        if intention in ["QUESTION_EXPLICATION", "SALUTATION_COURTOISIE"]:
            explication = res.get("explication_pedagogique") or ""
            # Filtre strict légalité : interdiction absolue de prétendre générer soi-même les bilans
            remplacements_bilan = [
                (r"je génère tes bilans pour", "je transmets tes demandes de bilan à ton cabinet d'expertise comptable pour"),
                (r"je génère vos bilans pour", "je transmets vos demandes de bilan à votre cabinet d'expertise comptable pour"),
                (r"je génère tes bilans", "je prépare tes comptes et transmets la demande de bilan à ton cabinet comptable"),
                (r"je génère votre bilan", "je prépare vos comptes et transmets la demande de bilan à votre cabinet comptable"),
                (r"je génère ton bilan", "je prépare tes comptes et transmets la demande de bilan à ton cabinet comptable"),
                (r"générer votre bilan", "transmettre votre demande de bilan à votre expert-comptable"),
                (r"générer vos bilans", "transmettre vos demandes de bilan à votre expert-comptable"),
                (r"générer tes bilans", "transmettre tes demandes de bilan à ton cabinet comptable"),
                (r"générer ton bilan", "transmettre ta demande de bilan à ton cabinet comptable"),
                (r"je fais tes bilans", "je prépare tes comptes et transmets la demande à ton cabinet comptable"),
                (r"je fais votre bilan", "je prépare vos comptes et transmets la demande à votre cabinet comptable"),
            ]
            for pat, rep in remplacements_bilan:
                explication = re.sub(pat, rep, explication, flags=re.IGNORECASE)

            rappel = prompt_rappel_etape(etape_actuelle, onboarding)
            
            # Formuler la réponse humaine complète : Explication + Relance douce
            msg_final = f"{explication}\n\n👉 {rappel}"
            return {
                "action": "REPONDRE_ET_REORIENTER",
                "message_reponse": msg_final
            }

        # 2. CAS CORRECTION_RETOUR
        if intention == "CORRECTION_RETOUR":
            champ = res.get("correction_champ")
            valeur = res.get("valeur_corrigee")
            champs_corriges = {}
            msg_confirm = "C'est bien noté, la modification a été prise en compte !"

            if champ and valeur:
                champs_corriges[champ] = valeur
                if champ == "nom_entreprise":
                    msg_confirm = f"✅ C'est corrigé ! Le nom officiel de votre entreprise est désormais *{valeur}*."
                elif champ == "mode_communication":
                    mode_aff = "Notes vocales 🎙️" if str(valeur).upper() in ["VOCAL", "AUDIO", "VOIX"] else "Messages écrits ✍️"
                    msg_confirm = f"✅ C'est bien noté ! Votre préférence d'échange est maintenant fixée sur : *{mode_aff}*."
                elif champ in ["numero_magasin", "numero_orange_money"]:
                    msg_confirm = f"✅ Votre numéro a été mis à jour : `{valeur}`."
                else:
                    msg_confirm = f"✅ Votre correction pour {champ} a bien été enregistrée : *{valeur}*."

            rappel = prompt_rappel_etape(etape_actuelle, onboarding)
            return {
                "action": "APPLIQUER_CORRECTION",
                "message_reponse": f"{msg_confirm}\n\n{rappel}",
                "champs_corriges": champs_corriges
            }

        # 3. CAS SAUTER_ETAPE
        if intention == "SAUTER_ETAPE":
            nouvelle_etape, msg_suivante = sauter_vers_etape_suivante(etape_actuelle, onboarding)
            return {
                "action": "SAUTER_ETAPE",
                "nouvelle_etape": nouvelle_etape,
                "message_reponse": msg_suivante
            }

        # 4. CAS REPONSE_ETAPE
        return {
            "action": "PASSTHROUGH_REPONSE_ETAPE",
            "entite_extraite": res.get("reponse_etape_extraite")
        }

    except Exception as e:
        print(f"Erreur supervision Gemini: {e}")
        return {"action": "PASSTHROUGH_REPONSE_ETAPE"}


async def superviser_conversation_claude(
    sender_phone: str,
    user_text: str,
    onboarding: dict,
    historique_recente: str = ""
) -> str:
    """Rétrocompatibilité : superviseur conversationnel unifié."""
    etape = onboarding.get("etape", "PHASE_1_ACCUEIL")
    res = await superviser_message_onboarding(sender_phone, user_text, etape, onboarding)
    return res.get("message_reponse")


"""
Grow MVP - Superviseur Conversationnel Intelligent (Anthropic Claude)
Gère le suivi de la conversation, les relances, les questions et les réponses ambiguës
sans JAMAIS toucher aux extractions déterministes ni réinitialiser le tunnel d'onboarding.
Normes : SYSCOHADA, Sénégal (Dakar), 0 émojis, courtoisie et rigueur comptable.
"""

import os
import re
from dotenv import load_dotenv
import anthropic

load_dotenv(override=True)

MODEL_CLAUDE = "claude-haiku-4-5-20251001"
FALLBACK_CLAUDE = "claude-haiku-4-5-20251001"


def remove_all_emojis(text: str) -> str:
    """Supprime absolument tous les émojis et symboles non professionnels."""
    if not text:
        return ""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text).strip()


def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        return anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        print(f"Erreur initialisation Anthropic: {e}")
        return None


def get_contexte_etape(etape: str, onboarding: dict) -> str:
    """Retourne la description précise de l'étape active pour orienter Claude."""
    nom = onboarding.get("nom_entreprise") or onboarding.get("nom_personne_physique") or "l'entreprise"
    ninea = onboarding.get("ninea") or "en attente"
    equipe = onboarding.get("nombre_employes") or "en attente"
    ops = onboarding.get("operateurs") or "en attente"
    immos = onboarding.get("immobilisations") or "en attente"

    if etape == "DEMANDE_NOM_COMMERCIAL":
        return (
            f"ÉTAPE ACTUELLE : DEMANDE DU NOM COMMERCIAL DE L'ENTREPRISE.\n"
            f"L'attestation NINEA officielle a été reçue et validée au nom de « {onboarding.get('nom_personne_physique', 'l exploitant')} ».\n"
            "Comme il s'agit d'une Entreprise Individuelle, cette dénomination est le nom de la personne physique.\n"
            "On attend que le commerçant donne le NOM COMMERCIAL ou l'enseigne de sa boutique/atelier (ex: « Boutique Keur Fatou », « Ets Diallo »).\n"
            "Objectif : Acknowledge poliment, et demander clairement quel est le nom commercial de son entreprise."
        )

    if etape == "DEMANDE_NINEA":
        return (
            "ÉTAPE ACTUELLE : ÉTAPE 1/5 - IDENTITÉ DE L'ENTREPRISE (ATTESTATION NINEA).\n"
            "On attend OBLIGATOIREMENT la photo ou le document PDF de l'attestation papier officielle NINEA.\n"
            "Sans cette pièce justificative, Grow ne peut pas certifier le NINEA, le RCCM, la forme juridique et le capital.\n"
            "Si le commerçant écrit juste du texte, dit 'Choisi', pose une question ou hésite, explique avec courtoisie pourquoi cette pièce est indispensable et demande-lui d'envoyer la photo."
        )

    if etape == "DEMANDE_EQUIPE":
        return (
            f"ÉTAPE ACTUELLE : ÉTAPE 2/5 - NOMBRE D'EMPLOYÉS (Entreprise: {nom}).\n"
            "On attend le nombre exact de personnes travaillant dans la structure (salariés, apprentis, associés, ou 'moi seul').\n"
            "Si la réponse de l'utilisateur est vague, demande-lui de préciser en un chiffre ou une phrase simple combien de personnes travaillent avec lui."
        )

    if etape == "DEMANDE_OPERATEURS":
        return (
            f"ÉTAPE ACTUELLE : ÉTAPE 3/5 - MOYENS DE PAIEMENT & OPÉRATEURS (Entreprise: {nom}).\n"
            "On attend la liste des moyens de paiement utilisés au quotidien (exemples : Wave, Orange Money, Caisse Espèces, Compte Bancaire, Free Money).\n"
            "ATTENTION : Si l'utilisateur a écrit 'Choisi', 'Les normaux', ou une réponse floue, il n'a PAS précisé ses opérateurs !\n"
            "Rapproche-toi de lui en disant avec tact : vous avez écrit 'Choisi', mais veuillez me citer concrètement les moyens que vous utilisez (Wave, Orange Money, Caisse Espèces, etc.)."
        )

    if etape == "DEMANDE_IMMOBILISATIONS":
        val_notee = onboarding.get("valeur_equipements_fcfa")
        immo_notee = onboarding.get("immobilisations")
        return (
            f"ÉTAPE ACTUELLE : ÉTAPE 4/5 - ÉQUIPEMENTS & IMMOBILISATIONS (Entreprise: {nom}).\n"
            f"Matériels déjà mentionnés : {immo_notee or 'aucun pour le moment'}.\n"
            f"Valeur estimée notée : {val_notee or 'aucune pour le moment'}.\n"
            "EXIGENCE STRICTE GROW : Pour valider cette étape, il faut OBLIGATOIREMENT :\n"
            "1. La description des matériels\n"
            "2. La valeur estimée globale en FCFA\n"
            "3. La photo justificative des équipements en boutique ou la facture d'achat.\n"
            "Si l'utilisateur a listé du matériel sans valeur ni photo, remercie-le, confirme le matériel noté, et demande-lui la valeur en FCFA et la photo."
        )

    if etape == "DEMANDE_TRESORERIE_INITIALE":
        ops_configures = onboarding.get("liste_operateurs_cles") or ["Wave", "Caisse Espèces"]
        ops_txt = " et ".join(ops_configures)
        return (
            f"ÉTAPE ACTUELLE : ÉTAPE 5/5 - TRÉSORERIE DISPONIBLE T0 (Entreprise: {nom}).\n"
            f"Opérateurs choisis à l'étape 3 : {ops_txt}.\n"
            "EXIGENCE STRICTE GROW : L'utilisateur doit OBLIGATOIREMENT fournir la capture d'écran de son solde Wave/Orange Money/Banque (ou la photo de sa caisse espèces).\n"
            "Sans cette capture, Grow refuse de valider la trésorerie de départ (principe de justification probatoire SYSCOHADA).\n"
            f"Rappelle-lui d'envoyer la capture d'écran du solde de ses comptes ({ops_txt})."
        )

    return (
        f"L'entreprise est en cours de configuration. Étape : {etape}."
    )


async def superviser_conversation_claude(
    sender_phone: str,
    user_text: str,
    onboarding: dict,
    historique_recente: str = ""
) -> str:
    """
    Appelle Anthropic Claude pour répondre intelligemment à un message imprévu,
    ambigu ou conversationnel, sans jamais réinitialiser l'onboarding.
    """
    client = get_anthropic_client()
    if not client:
        return None

    etape = onboarding.get("etape", "DEMANDE_NINEA")
    contexte_etape = get_contexte_etape(etape, onboarding)
    nom_client = onboarding.get("nom_personne_physique") or onboarding.get("nom_entreprise") or "Cher partenaire"

    system_prompt = f"""Tu es l'assistant pré-comptable officiel de Grow (Fintech basée à Dakar, Sénégal).
Tu assistes les commerçants, artisans et dirigeants de PME sénégalais pour tenir leur comptabilité conforme aux normes SYSCOHADA et préparer leurs bilans fiscaux.

CONSIGNES STRICTES DE STYLE ET DE FORME :
1. AUCUN EMOJI. STRICTEMENT ZÉRO EMOJI dans toutes tes réponses. N'utilise jamais de symboles emoji ni de smileys.
2. Ton : Professionnel, chaleureux, courtois, respectueux de la culture sénégalaise (TERANGA), clair et précis.
3. RÔLE : Tu es le CERVEAU DE SUIVI CONVERSATIONNEL. Tu ne fais pas les écritures comptables toi-même ici, tu gères la conversation pour que le commerçant ne soit jamais perdu, confus ou bloqué.
4. RÈGLE D'OR : Ne JAMAIS réinitialiser la session, ne jamais lui redemander de s'abonner (son abonnement est déjà actif et payé), et ne jamais faire comme si tu le voyais pour la première fois !
5. OBJECTIF IMMÉDIAT : Répondre avec pertinence à ce que vient de dire le commerçant (par exemple s'il a écrit « Choisi », s'il demande « Pourquoi », s'il est hésitant ou s'il fait une remarque), dissiper son doute avec bienveillance, puis LE RÉORIENTER DIRECTEMENT ET CLAIREMENT vers l'action attendue pour l'étape en cours.

{contexte_etape}
"""

    prompt_user = f"""Le commerçant (numéro {sender_phone}) vient de t'envoyer ce message :
« {user_text} »

Rédige une réponse courte (3 à 5 phrases maximum), claire, sans aucun emoji :
1. Réagis à son message avec courtoisie et intelligence.
2. Rappelle-lui exactement ce qui est attendu pour l'étape active afin de continuer la configuration de son entreprise.
Termine par la ligne de contact standard :
Pour toute assistance, contactez le service Grow au 78 877 38 27."""

    models_to_try = [MODEL_CLAUDE, FALLBACK_CLAUDE]
    for model_name in models_to_try:
        try:
            res = client.messages.create(
                model=model_name,
                max_tokens=1000,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt_user}]
            )
            reponse = "".join(b.text for b in res.content if hasattr(b, "text")).strip()
            reponse = remove_all_emojis(reponse)
            if reponse:
                return reponse
        except Exception as e:
            print(f"Erreur appel Anthropic Claude ({model_name}): {e}")

    return None


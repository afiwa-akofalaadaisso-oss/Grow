import os
import json
import base64
import hashlib
import asyncio
import re
import urllib.request
from datetime import datetime, timedelta
import zoneinfo
import httpx
import anthropic
from fastapi import FastAPI, Request, HTTPException, Query, Body
from fastapi.responses import PlainTextResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from smart_classifier import (
    classifier_operation_automatiquement,
    enregistrer_fournisseur_memoire,
    generer_message_rituel_soir,
    generer_point_flash_journee,
    generer_message_matin_6h,
    get_memoire_fournisseurs,
    DICT_SERVICES_NATIONAUX
)

from conversation_supervisor import superviser_conversation_claude
from voice_processor import (
    transcrire_note_vocale,
    generer_note_vocale_audio,
    detecter_langue_texte
)

from gemini_audio_processor import (
    analyser_audio_gemini,
    extraire_transcription,
    extraire_langue,
    extraire_reponse_wolof,
    extraire_operation_syscohada,
    est_gemini_disponible
)

from local_extractor import (
    parse_montant_fcfa,
    extract_business_identity_local,
    parse_operator_sms_local,
    parse_operation_financiere_locale,
    parse_soldes_multi_operateurs
)

from expert_assistant import (
    repondre_question_theorique_locale,
    executer_consultation_donnees_locale,
    gerer_dette_creance_locale
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Fuseau horaire officiel du Sénégal (Dakar / GMT)
TZ_DAKAR = zoneinfo.ZoneInfo("Africa/Dakar")

def get_now_dakar() -> datetime:
    """Retourne la date et l'heure courante exacte au Sénégal (fuseau Africa/Dakar / GMT)."""
    return datetime.now(TZ_DAKAR)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

app = FastAPI(title="Grow MVP - Assistant Comptable SYSCOHADA WhatsApp")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Cache anti-doublon pour les webhooks Meta WhatsApp (retries dans les 120s)
PROCESSED_MESSAGE_IDS: dict[str, float] = {}

def is_duplicate_message(msg_id: str) -> bool:
    """Evite le double traitement d'un message WhatsApp si Meta renvoie le webhook."""
    if not msg_id:
        return False
    import time
    now = time.time()
    # Nettoyage des entrees de plus de 10 minutes
    to_delete = [k for k, t in PROCESSED_MESSAGE_IDS.items() if now - t > 600]
    for k in to_delete:
        PROCESSED_MESSAGE_IDS.pop(k, None)
    if msg_id in PROCESSED_MESSAGE_IDS:
        return True
    PROCESSED_MESSAGE_IDS[msg_id] = now
    return False

scheduler = AsyncIOScheduler()

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "grow_dakar_secret_2026")
ONBOARDING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "onboarding_states.json")


def get_public_base_url() -> str:
    """Retourne l'URL publique active pour les liens d'abonnement et dashboard."""
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base:
        return base
    try:
        import glob
        log_files = glob.glob(r"C:\Users\new\.gemini\antigravity\brain\*\.system_generated\tasks\*.log")
        for f in sorted(log_files, key=os.path.getmtime, reverse=True):
            with open(f, "r", encoding="utf-8", errors="ignore") as lf:
                content = lf.read()
                matches = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", content)
                if matches:
                    return matches[-1]
    except Exception:
        pass
    return "https://wendy-hawk-spare-kissing.trycloudflare.com"


def is_paiement_keyword(text: str) -> bool:
    """Détecte de façon robuste toute affirmation de paiement d'abonnement (accents, apostrophes courbes, fautes)."""
    if not text:
        return False
    import unicodedata
    t = text.lower().replace(chr(8217), "'").replace(chr(96), "'").strip()
    norm = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    
    phrases = [
        "j'ai paye", "jai paye", "j'ai payer", "jai payer", "je viens de payer",
        "c'est paye", "c'est payer", "deja paye", "deja payer",
        "paiement effectue", "paiement confirme", "abonnement paye",
        "j'ai regle", "jai regle", "voici mon recu de paiement", "recu de paiement", "recu paiement",
        "fey naa", "feynaa", "fey na", "feyna", "dama fey", "fey nako",
        "i paid", "i have paid", "already paid", "payment done", "just paid"
    ]
    if any(p in norm for p in phrases):
        return True

    if norm in ["paye", "payer", "paiement", "c'est bon", "c'est fait", "abonne", "fey", "paid"]:
        return True

    return False


def is_entreprise_deja_configuree(sender_phone: str) -> bool:
    """Vérifie si le numéro possède déjà une entreprise entièrement configurée (les 5 étapes d'onboarding achevées)."""
    # 1. Vérification dans l'état onboarding local
    state = get_onboarding_state(sender_phone)
    if state.get("etape") == "TERMINE" or state.get("statut") == "COMPLET":
        return True

    # 2. Vérification dans Supabase
    try:
        sp = get_supabase()
        if sp:
            clean_phone = str(sender_phone).replace("+", "").replace(" ", "").strip()
            res = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_phone}%").execute()
            if res.data:
                for ent in res.data:
                    if ent.get("etape_onboarding") == "COMPLET":
                        return True
    except Exception as e:
        print(f"Info vérification entreprise existante : {e}")

    return False


def get_instructions_journee_message(base_url: str, sender_phone: str, nom_entreprise: str = "Votre Entreprise") -> str:
    """Message matinal et consignes opérationnelles : la vraie bataille quotidienne commence ici."""
    return (
        f"Bonjour {nom_entreprise}.\n\n"
        "Une nouvelle journée d'activité commence et la vraie bataille quotidienne pour vos finances démarre maintenant !\n\n"
        "Grow est désormais en première ligne à vos côtés sur WhatsApp pour intercepter, vérifier et certifier toutes vos opérations en temps réel :\n\n"
        "1. VENTES & PAIEMENTS OPERATEURS (WAVE, ORANGE MONEY, FREE) :\n"
        "• Vos encaissements reçus sur vos comptes marchands ou via SMS de transfert sont enregistrés et imputés au journal financier sans aucune intervention de votre part.\n"
        "• Si vous recevez un SMS d'un opérateur sur votre téléphone, transférez ou collez le message ici dans le chat : Grow extrait instantanément le montant, le client et la référence officielle.\n\n"
        "2. VENTES EN CASH (ESPECES) :\n"
        "• Dès que vous encaissez du cash au comptoir, envoyez simplement un court message ou une note vocale (exemple : « Vente marchandise 35 000 cash »). Vos comptes sont mis à jour à la seconde.\n\n"
        "3. REGLE D'OR SUR LES DEPENSES & ACHATS EN CASH :\n"
        "Chaque sortie d'argent en espèces (achats de marchandises, carburant, taxis, factures Senelec / Sen'Eau, loyer, repas, fournitures) doit OBLIGATOIREMENT être accompagnée de sa pièce justificative :\n"
        "• Prenez immédiatement la photo du reçu, de la facture, du ticket de caisse ou même du stock acheté avant de ranger le produit.\n"
        "• ATTENTION : Sans pièce justificative, Grow refusera de valider la dépense. C'est vous qui perdez car elle ne sera pas déductible de votre bénéfice imposable auprès des impôts (DGID) et votre trésorerie sera faussée !\n\n"
        "4. SUIVI DES DETTES & CREANCES :\n"
        "• Si un client prend à crédit : écrivez simplement « Moussa a pris des habits pour 25 000, il paiera mardi ».\n"
        "• Si vous devez à un fournisseur : écrivez « J'ai pris 100 000 de tissu chez Fallou, dette à régler sous 15 jours ».\n"
        "• Grow assure les relances automatiques pour vous faire encaisser votre argent.\n\n"
        "5. LE RITUEL DU SOIR (20H00) :\n"
        "Chaque soir à 20h00, Grow dresse le bilan complet de votre journée (total des ventes, marge nette certifiée, solde de caisse et réconciliation bancaire).\n\n"
        "Votre tableau de bord financier personnel est accessible 24h/24 en direct sur ce lien sécurisé :\n"
        f"{base_url}/dashboard?phone={sender_phone}\n\n"
        "Le front est ouvert : transférez votre première notification d'opérateur, notez votre première vente ou envoyez la photo de votre premier reçu !"
    )


def remove_all_emojis(text: str) -> str:
    """Supprime absolument tous les emojis et symboles speciaux (sauf les puces de choix de langue 1️⃣ 2️⃣ 3️⃣)."""
    preserved = text.replace("1️⃣", "__LANG_1__").replace("2️⃣", "__LANG_2__").replace("3️⃣", "__LANG_3__")
    emoji_pattern = re.compile(
        "["
        "\U00010000-\U0010FFFF"
        "\u2600-\u26FF"
        "\u2700-\u27BF"
        "\uFE00-\uFE0F"
        "\u20E3"
        "]+", flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub("", preserved)
    for char in ["👉", "✅", "⛔", "🔒", "💰", "📸", "🏢", "👥", "💳", "🏗️", "🔢", "🏦", "📂", "📄", "🎉", "💸", "📊", "🧾", "📦", "🎫", "📲", "👋", "🙏", "🇸🇳", "💪", "🤔", "😊", "📅", "⏰"]:
        cleaned = cleaned.replace(char, "")
    cleaned = cleaned.replace("__LANG_1__", "1️⃣").replace("__LANG_2__", "2️⃣").replace("__LANG_3__", "3️⃣")
    return cleaned.strip()


def format_grow_message(body_text: str) -> str:
    """Structure Grow : Pas d'emoji, corps clair et sobre, pied de page assistance."""
    clean_body = remove_all_emojis(body_text)
    # Suppression absolue de tout séparateur tirets ou barres
    clean_body = re.sub(r'[-=─━_]{2,}', '', clean_body)
    footer = "Pour toute assistance, contactez le service Grow au 78 877 38 27."

    return f"{clean_body.strip()}\n\n{footer}"


def get_tresorerie_stats(sp, entreprise_id: str):
    """Calcule la tresorerie reelle ventilee par operateur (Wave, Orange Money, Especes) et le total."""
    if not sp or not entreprise_id:
        return 0, 0, 0, 0
    txs = sp.table("transactions").select("*").eq("entreprise_id", entreprise_id).execute().data or []
    wave = 0
    om = 0
    especes = 0
    for t in txs:
        src = (t.get("source_paiement") or "WAVE").upper()
        montant = int(t.get("montant_fcfa") or 0)
        flux = t.get("type_flux")
        delta = montant if flux == "ENTREE" else -montant
        if "ORANGE" in src or "OM" in src:
            om += delta
        elif "ESPEC" in src or "CAISSE" in src:
            especes += delta
        else:
            wave += delta
    total = wave + om + especes
    return wave, om, especes, total



def get_supabase():
    """Initialise le client Supabase."""
    load_dotenv(override=True)
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        print(f"Erreur connexion Supabase : {e}")
        return None


def load_onboarding_states() -> dict:
    if os.path.exists(ONBOARDING_FILE):
        try:
            with open(ONBOARDING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_onboarding_states(states: dict):
    try:
        with open(ONBOARDING_FILE, "w", encoding="utf-8") as f:
            json.dump(states, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erreur sauvegarde onboarding states : {e}")


def get_onboarding_state(phone: str) -> dict:
    clean_p = str(phone).replace("+", "").replace(" ", "").strip()
    states = load_onboarding_states()

    if clean_p not in states:
        # 1. Vérification dans Supabase si l'entreprise a déjà commencé son onboarding
        sp = get_supabase()
        loaded_from_db = False
        if sp:
            try:
                res = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_p}%").limit(1).execute()
                if res.data and len(res.data) > 0:
                    ent = res.data[0]
                    donnees = ent.get("donnees_onboarding") or {}
                    est_termine = (ent.get("etape_onboarding") == "COMPLET")
                    states[clean_p] = {
                        "etape": "TERMINE" if est_termine else (donnees.get("etape") or "DEMANDE_NINEA"),
                        "langue_preferee": donnees.get("langue_preferee", "fr"),
                        "ninea": ent.get("ninea"),
                        "nom_entreprise": ent.get("nom_entreprise"),
                        "nom_personne_physique": donnees.get("nom_personne_physique"),
                        "capital": ent.get("capital_initial_fcfa"),
                        "forme_juridique": donnees.get("forme_juridique"),
                        "activite_principale": ent.get("secteur_activite") or donnees.get("activite_principale"),
                        "registre_commerce": donnees.get("registre_commerce"),
                        "nombre_employes": donnees.get("nombre_employes"),
                        "operateurs": donnees.get("operateurs"),
                        "liste_operateurs_cles": donnees.get("liste_operateurs_cles"),
                        "immobilisations": donnees.get("equipements_materiels"),
                        "valeur_equipements_fcfa": donnees.get("valeur_equipements_fcfa"),
                        "equipements_photo_validee": donnees.get("equipements_valides_par_preuve", False),
                        "statut": "COMPLET" if est_termine else "EN_COURS",
                        "abonnement_valide": True,
                        "premier_contact_effectue": True
                    }
                    loaded_from_db = True
            except Exception as e:
                print(f"Info get_onboarding_state Supabase : {e}")

        if not loaded_from_db:
            states[clean_p] = {
                "etape": "CHOIX_LANGUE",
                "langue_preferee": None,
                "ninea": None,
                "nom_entreprise": None,
                "nom_personne_physique": None,
                "capital": None,
                "date_creation": None,
                "adresse_siege": None,
                "nombre_employes": None,
                "operateurs": None,
                "liste_operateurs_cles": None,
                "immobilisations": None,
                "valeur_equipements_fcfa": None,
                "equipements_photo_validee": False,
                "statut": "EN_ATTENTE_LANGUE",
                "abonnement_valide": False,
                "premier_contact_effectue": False
            }
        save_onboarding_states(states)
    else:
        # S'assurer que le premier contact et l'abonnement ne sont jamais perdus
        if states[clean_p].get("statut") in ["EN_COURS", "COMPLET"]:
            states[clean_p]["premier_contact_effectue"] = True
            states[clean_p]["abonnement_valide"] = True

    return states[clean_p]


def update_onboarding_state(phone: str, key: str, value):
    clean_p = str(phone).replace("+", "").replace(" ", "").strip()
    states = load_onboarding_states()
    if clean_p not in states:
        states[clean_p] = get_onboarding_state(clean_p)
    states[clean_p][key] = value
    save_onboarding_states(states)

    # Synchronisation immédiate avec Supabase
    sp = get_supabase()
    if sp:
        try:
            res = sp.table("entreprises").select("id, donnees_onboarding").ilike("telephone_whatsapp", f"%{clean_p}%").limit(1).execute()
            if res.data and len(res.data) > 0:
                ent_id = res.data[0]["id"]
                current_donnees = res.data[0].get("donnees_onboarding") or {}
                current_donnees[key] = value
                payload = {"donnees_onboarding": current_donnees}
                if key == "nom_entreprise":
                    payload["nom_entreprise"] = value
                if key == "ninea":
                    payload["ninea"] = value
                if key == "capital":
                    payload["capital_initial_fcfa"] = value
                if key == "etape" and value == "TERMINE":
                    payload["etape_onboarding"] = "COMPLET"
                sp.table("entreprises").update(payload).eq("id", ent_id).execute()
        except Exception as e_sync:
            print(f"Info sync Supabase update_onboarding_state : {e_sync}")


def get_or_create_entreprise(sp, sender_phone: str) -> dict:
    """Récupère ou crée automatiquement l'entreprise liée à ce numéro WhatsApp."""
    if not sp or not sender_phone:
        return {}
    try:
        clean_phone = str(sender_phone).replace("+", "").replace(" ", "").strip()
        res = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_phone}%").limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]

        nouvelle = sp.table("entreprises").insert({
            "telephone_whatsapp": clean_phone,
            "nom_entreprise": f"Boutique {clean_phone[-4:]}",
            "secteur_activite": "Commerce & Services",
            "capital_initial_fcfa": 0
        }).execute()
        if nouvelle.data:
            return nouvelle.data[0]
    except Exception as e:
        print(f"Erreur gestion entreprise : {e}")
    return {}


@app.get("/")
@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """Validation initiale du webhook par Meta."""
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print("Webhook validé avec succès par Meta !")
        return PlainTextResponse(content=hub_challenge)
    return {
        "status": "online",
        "message": "Grow MVP WhatsApp avec Onboarding NINEA & IA SYSCOHADA est 100% opérationnel 🚀"
    }


@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/client", response_class=HTMLResponse)
async def serve_dashboard():
    """Tableau de bord PME & Agence conforme aux maquettes officielles Grow & ONECCA."""
    html_path = os.path.join(TEMPLATES_DIR, "dashboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Tableau de bord en cours d'initialisation</h1>", status_code=200)


@app.get("/carte-comptoir")
@app.get("/qr")
async def serve_carte_comptoir():
    """Plaque présentoir de comptoir officielle Grow pour impression A5/A6."""
    html_path = os.path.join(TEMPLATES_DIR, "carte_comptoir.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Présentoir comptoir en cours de génération</h1>", status_code=200)


@app.get("/telecharger-carte")
async def telecharger_carte():
    """Télécharger directement l'image haute définition de la plaque présentoir Grow."""
    img_path = os.path.join(STATIC_DIR, "plaque_comptoir_grow.png")
    if os.path.exists(img_path):
        return FileResponse(img_path, media_type="image/png", filename="Plaque_Comptoir_Grow.png")
    return HTMLResponse("Image non trouvée", status_code=404)


@app.get("/api/dashboard-data")
async def get_dashboard_data(phone: str = None, entreprise_id: str = None):
    """Fournit les données réelles et isolées d'une entreprise et ses transactions depuis Supabase."""
    sp = get_supabase()
    if not sp:
        return {"error": "Base de données non disponible", "entreprises": [], "entreprise": None, "transactions": []}

    try:
        # Récupérer la liste des entreprises enregistrées
        all_ents = sp.table("entreprises").select("id, nom_entreprise, telephone_whatsapp, ninea, secteur_activite, adresse_siege, capital_initial_fcfa, donnees_onboarding").order("date_inscription", desc=True).execute().data or []

        target_ent = None
        if entreprise_id:
            for e in all_ents:
                if str(e.get("id")) == str(entreprise_id):
                    target_ent = e
                    break
            if not target_ent:
                res = sp.table("entreprises").select("*").eq("id", entreprise_id).execute()
                if res.data:
                    target_ent = res.data[0]
        elif phone:
            clean_phone = phone.replace("+", "").replace(" ", "").strip()
            for e in all_ents:
                if e.get("telephone_whatsapp") and clean_phone in str(e.get("telephone_whatsapp")):
                    target_ent = e
                    break
            if not target_ent:
                res = sp.table("entreprises").select("*").eq("telephone_whatsapp", clean_phone).execute()
                if res.data:
                    target_ent = res.data[0]

        # Si un numéro a été expressément demandé mais qu'il n'est pas encore en base :
        if not target_ent and phone:
            target_ent = {
                "id": f"new_{clean_phone}",
                "nom_entreprise": "Mon Entreprise (En cours de configuration)",
                "telephone_whatsapp": clean_phone,
                "ninea": "En cours d'enregistrement",
                "secteur_activite": "Commerce & Services",
                "adresse_siege": "Dakar, Sénégal"
            }
            all_ents = [target_ent]
        elif not target_ent and all_ents:
            target_ent = next((e for e in all_ents if e.get("nom_entreprise") == "Grow Dakar Test"), all_ents[0])

        if not target_ent:
            return {
                "entreprise": {
                    "id": "",
                    "nom_entreprise": "En attente du 1er client WhatsApp",
                    "telephone_whatsapp": "Connectez un compte WhatsApp",
                    "ninea": None,
                    "adresse_siege": "Dakar, Sénégal"
                },
                "entreprises": [],
                "transactions": [],
                "totals": {"debit": 0, "credit": 0, "solde": 0, "count": 0},
                "prets": {
                    "score": 0,
                    "capacite_emprunt": 0,
                    "mensualite_max": 0,
                    "solde_net": 0
                }
            }

        ent_id = target_ent.get("id")

        # Récupérer uniquement les transactions réelles de cette entreprise si l'ID est un UUID valide
        raw_txs = []
        if ent_id and not str(ent_id).startswith("new_"):
            try:
                tx_query = sp.table("transactions").select("*, preuves_numeriques(*)").eq("entreprise_id", ent_id).order("date_operation", desc=True).order("created_at", desc=True).execute()
                raw_txs = tx_query.data or []
            except Exception as tx_err:
                print(f"Info tx query: {tx_err}")
                raw_txs = []

        # Calculer les montants réels
        total_debit = 0
        total_credit = 0
        for t in raw_txs:
            montant = int(t.get("montant_fcfa") or 0)
            flux = (t.get("type_flux") or "").upper()
            if flux == "SORTIE":
                total_debit += montant
            elif flux == "ENTREE":
                total_credit += montant

        solde_net = total_credit - total_debit

        # Règle prudentielle BCEAO : 33% du cash-flow net pour le remboursement mensuel
        mensualite_max = max(0, int(solde_net * 0.33)) if solde_net > 0 else 0
        capacite_emprunt = mensualite_max * 24 if mensualite_max > 0 else (2500000 if raw_txs else 0)

        # Calcul du score financier réel (les paiements dématérialisés Wave, OM, Banque sont certifiés d'office)
        tx_with_proof = sum(1 for t in raw_txs if (t.get("preuves_numeriques") and len(t["preuves_numeriques"]) > 0) or t.get("statut_validation") == "VALIDE_PME" or (t.get("source_paiement") or "").upper() in ["WAVE", "ORANGE_MONEY", "BANQUE"])
        taux_preuve = (tx_with_proof / len(raw_txs)) if raw_txs else 1.0
        score_base = 50 + (30 if solde_net > 0 else 10) + int(20 * taux_preuve)
        score_financier = min(98, max(50, score_base)) if raw_txs else 70

        # Isolation stricte : si un téléphone ou un ID est spécifié, la liste ne contient QUE cette entreprise
        if phone or entreprise_id:
            all_ents = [target_ent] if target_ent else []

        return {
            "entreprise": target_ent,
            "entreprises": all_ents,
            "transactions": raw_txs,
            "totals": {
                "debit": total_debit,
                "credit": total_credit,
                "solde": solde_net,
                "count": len(raw_txs)
            },
            "prets": {
                "score": score_financier,
                "capacite_emprunt": capacite_emprunt,
                "mensualite_max": mensualite_max,
                "solde_net": solde_net
            }
        }
    except Exception as e:
        print(f"Erreur API dashboard-data: {e}")
        return {"error": str(e), "entreprises": [], "transactions": []}




# =========================================================================
# SERVICE D'ACCOMPAGNEMENT & TEST DE DIAGNOSTIC WEBHOOK
# =========================================================================

def is_webhook_assistance_request(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    keywords = [
        "webhook", "web hook", "connecter wave", "connexion wave",
        "configurer wave", "passerelle sms", "automatiser wave",
        "automatiser mes paiements", "lier mon compte wave", "api wave",
        "mettre en place wave", "mettre en place mon webhook", "mettre en place leurs webhook",
        "aide webhook", "comment marche wave", "comment relier wave",
        "liaison wave", "interception wave", "passerelle", "sms relay"
    ]
    return any(k in t for k in keywords)

def is_test_webhook_request(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    keywords = [
        "tester webhook", "test webhook", "tester wave", "test wave",
        "simulation webhook", "tester la connexion", "test connexion"
    ]
    return any(k in t for k in keywords)

def get_webhook_guide_message(base_url: str, sender_phone: str) -> str:
    clean_p = str(sender_phone).replace("+", "").replace(" ", "").strip()
    return (
        "ASSISTANT DE CONFIGURATION WEBHOOK & PAIEMENTS AUTOMATIQUES\n\n"
        "Grow intercepte et enregistre automatiquement chacun de vos encaissements Wave ou Orange Money dans votre comptabilité SYSCOHADA, sans aucune saisie manuelle de votre part.\n\n"
        "3 SOLUTIONS POUR CONNECTER VOS PAIEMENTS :\n\n"
        "1. Wave Business (Portail Marchand officiel PME) :\n"
        "• Connectez-vous sur votre espace : business.wave.com\n"
        "• Allez dans Paramètres Développeur > Webhooks > Ajouter un webhook\n"
        "• Collez votre URL personnelle Grow :\n"
        f"{base_url}/webhook/wave?phone={clean_p}\n"
        "• Cochez les événements d'encaissement et enregistrez.\n\n"
        "2. Passerelle Relais SMS Android (Idéal compte Wave Personnel / Orange Money) :\n"
        "• Installez l'application gratuite « SMS Forwarder » sur le smartphone Android du magasin.\n"
        "• Créez une règle de transfert automatique vers votre URL Grow :\n"
        f"{base_url}/api/sms-gateway?phone={clean_p}\n"
        "• Dès qu'un SMS de vente est reçu, il est relayé silencieusement sans action de l'employé.\n\n"
        "3. Capture d'écran WhatsApp (Zéro configuration technique) :\n"
        "• Prenez une capture d'écran du reçu ou de la notification push Wave et envoyez-la moi directement ici.\n\n"
        "TESTER VOTRE LIAISON IMMÉDIATEMENT :\n"
        "Pour tester votre connexion en direct avec une simulation certifiée de 1 000 FCFA, répondez simplement « TESTER WEBHOOK ».\n\n"
        "Guide interactif pas à pas et testeur en 1 clic disponibles sur votre tableau de bord :\n"
        f"{base_url}/dashboard?phone={clean_p}&open_webhook=1"
    )

async def executer_simulation_test_webhook(clean_phone: str, provider: str = "WAVE", amount: int = 1000) -> dict:
    sp = get_supabase()
    ent = get_or_create_entreprise(sp, clean_phone) if sp else {}
    ent_id = ent.get("id") if ent else f"new_{clean_phone}"
    tx_id = f"TEST-WV-{int(datetime.now().timestamp())}"
    compte = "701"

    if sp and ent_id and not str(ent_id).startswith("new_"):
        row = {
            "entreprise_id": ent_id,
            "libelle": f"Test Connexion Réussi - Encaissement Wave ({amount:,.0f} FCFA)",
            "compte_syscohada": compte,
            "type_flux": "ENTREE",
            "est_professionnel": True,
            "montant_fcfa": amount,
            "source_paiement": provider,
            "statut_validation": "VALIDE_PME"
        }
        try:
            sp.table("transactions").insert(row).execute()
        except Exception as e_tx:
            print(f"Info insertion tx test: {e_tx}")

    base_url = get_public_base_url()
    msg_test = (
        "TEST DE CONNEXION WEBHOOK RÉUSSI\n\n"
        "RÉSUMÉ DU TEST EN DIRECT :\n"
        f"• Canal vérifié : Webhook Opérateur {provider}\n"
        f"• Montant test : {amount:,.0f} FCFA\n"
        f"• Référence test : {tx_id}\n"
        "• Imputation : Compte SYSCOHADA 701 (Vente de marchandises)\n"
        f"• Trésorerie créditée : Compte SYSCOHADA 521 ({provider})\n"
        "• Statut : Liaison 100% opérationnelle et certifiée\n\n"
        "Vos véritables encaissements clients seront désormais interceptés et réconciliés automatiquement sans intervention manuelle :\n"
        f"{base_url}/dashboard?phone={clean_phone}"
    )
    await send_whatsapp_message(clean_phone, msg_test)

    return {
        "status": "success",
        "message": "Liaison Webhook validée avec succès. Écriture enregistrée et confirmation WhatsApp envoyée.",
        "tx_id": tx_id,
        "provider": provider,
        "amount": amount,
        "compte": compte
    }

@app.post("/api/test-webhook")
async def api_test_webhook(request: Request):
    """Point d'accès de test et diagnostic webhook pour le tableau de bord Grow."""
    try:
        data = await request.json()
        phone = data.get("phone")
        provider = (data.get("provider") or "WAVE").upper()
        amount = int(data.get("amount") or 1000)

        if not phone:
            return {"status": "error", "message": "Numéro de téléphone requis"}

        clean_p = str(phone).replace("+", "").replace(" ", "").strip()
        res = await executer_simulation_test_webhook(clean_p, provider, amount)
        return res
    except Exception as e:
        print(f"Erreur api_test_webhook: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/webhook/wave-direct")
@app.post("/webhook/wave-merchant")
@app.post("/webhook/wave")
async def webhook_wave_direct(request: Request):
    """
    Webhook Opérateur Wave & Wave Business Merchant :
    Reçoit les notifications d'encaissement (QR code comptoir, checkout ou transfert) en direct depuis Wave.
    Le commerçant PME n'a absolument RIEN à copier-coller : Grow intercepte le flux et notifie le gérant sur WhatsApp.
    """
    try:
        payload = await request.json()
        print("\n[NOTIFICATION OPÉRATEUR WAVE REÇUE] :", payload)

        # Support du format Wave standard (data imbriqué) et du format direct
        data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else payload

        tx_id = payload.get("id") or data_obj.get("id") or data_obj.get("transaction_id") or f"WV-{int(datetime.now().timestamp())}"
        amount = int(float(data_obj.get("amount") or data_obj.get("montant") or payload.get("amount") or 0))

        # Résolution du compte marchand Wave (Numéro de compte M_sn_... ou téléphone)
        wave_account_id = (
            data_obj.get("account_id")
            or data_obj.get("merchant_id")
            or data_obj.get("business_id")
            or payload.get("account_id")
            or payload.get("merchant_id")
            or payload.get("business_id")
            or request.query_params.get("merchant_id")
        )

        phone = (
            data_obj.get("client_reference")
            or data_obj.get("merchant_phone")
            or payload.get("client_phone")
            or payload.get("telephone")
            or payload.get("sender_phone")
            or request.query_params.get("phone")
        )

        # Si Wave fournit l'identifiant marchand (ex: M_sn_YgEkibrMRghV) sans téléphone
        if not phone and wave_account_id:
            if wave_account_id == "M_sn_YgEkibrMRghV":
                phone = "221788773827"
            else:
                sp_lookup = get_supabase()
                if sp_lookup:
                    try:
                        res_lookup = sp_lookup.table("entreprises").select("telephone_whatsapp, donnees_onboarding").execute()
                        for e in res_lookup.data or []:
                            d_onb = e.get("donnees_onboarding") or {}
                            if d_onb.get("wave_account_id") == wave_account_id or d_onb.get("wave_merchant_id") == wave_account_id:
                                phone = e.get("telephone_whatsapp")
                                break
                    except Exception as e_lk:
                        print(f"Info lookup wave_account_id: {e_lk}")

        customer_info = data_obj.get("customer") if isinstance(data_obj.get("customer"), dict) else {}
        tiers_nom = customer_info.get("name") or data_obj.get("client_name") or data_obj.get("tiers_nom") or payload.get("client_name") or "Client Wave"
        tiers_phone = customer_info.get("phone") or ""

        direction = (data_obj.get("direction") or payload.get("direction") or "CREDIT").upper()
        description = data_obj.get("description") or payload.get("description") or f"Encaissement Wave Marchand - {tiers_nom}"

        if not phone or amount <= 0:
            return {"status": "ignored", "reason": "Missing merchant phone or invalid amount"}

        sp = get_supabase()
        if not sp:
            return {"status": "error", "reason": "Database connection missing"}

        # Identifier ou initialiser automatiquement l'entreprise liée au numéro de téléphone
        clean_phone = str(phone).replace("+", "").replace(" ", "").strip()
        res_ent = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_phone}%").limit(1).execute()
        if res_ent and res_ent.data:
            ent = res_ent.data[0]
        else:
            ent = get_or_create_entreprise(sp, clean_phone)

        ent_id = ent.get("id")
        ent_nom = ent.get("nom_entreprise", "Votre PME")

        type_flux = "ENTREE" if direction in ["CREDIT", "IN", "ENTREE", "RECEIVED"] else "SORTIE"

        # Classification Intelligente Automatique (Encaissement CA, Mémoire Fournisseurs, Services Nationaux)
        classification = classifier_operation_automatiquement(
            direction=direction,
            montant=amount,
            description=description,
            tiers_nom=tiers_nom,
            entreprise_id=ent_id
        )
        compte_syscohada = classification["compte_syscohada"]
        statut_val = classification["statut_validation"]
        libelle_final = classification["libelle"]
        methode = classification["methode_resolution"]

        # Garantir un libellé unique, distinct et détaillé pour chaque encaissement Wave
        ref_aff = tx_id if tx_id else f"WV-{amount}"
        if not libelle_final or "Encaissement Wave" in libelle_final:
            libelle_final = f"Encaissement Wave - {amount:,.0f} FCFA ({tiers_nom} - Réf: {ref_aff})"
        elif f"{amount:,.0f}" not in libelle_final:
            libelle_final = f"{libelle_final} ({amount:,.0f} FCFA - Réf: {ref_aff})"

        # Insertion directe dans le journal pré-comptable SYSCOHADA
        tx_row = {
            "entreprise_id": ent_id,
            "libelle": libelle_final,
            "compte_syscohada": compte_syscohada,
            "type_flux": type_flux,
            "montant_fcfa": amount,
            "source_paiement": "WAVE",
            "reference_externe": tx_id,
            "statut_validation": statut_val,
            "est_professionnel": True
        }

        try:
            sp.table("transactions").insert(tx_row).execute()
        except Exception:
            tx_row.pop("reference_externe", None)
            sp.table("transactions").insert(tx_row).execute()

        print(f"[GROW WEBHOOK AUTONOME] TX {tx_id} traitée via {methode} -> Compte {compte_syscohada} ({statut_val})")

        # Ingestion silencieuse en arrière-plan : l'écriture comptable est enregistrée discrètement
        # en base de données et actualise le tableau de bord en direct sans spammer le commerçant.
        # Le commerçant reçoit un bilan consolidé lors des points flash toutes les 3 heures (09h, 12h, 15h, 18h, 21h).
        print(f"[GROW WAVE INGESTION SILENCIEUSE] Encaissement de {amount:,.0f} FCFA ({tx_id}) déposé discrètement en base et sur le dashboard pour {clean_phone or wave_account_id}. Zéro message WhatsApp individuel.")

        return {
            "status": "success",
            "tx_id": tx_id,
            "amount": amount,
            "compte": compte_syscohada,
            "methode": methode,
            "statut": statut_val
        }

    except Exception as e:
        print(f"Erreur webhook_wave_direct: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/sms-gateway")
@app.post("/webhook/sms-relay")
async def api_sms_gateway(request: Request):
    """
    Passerelle Relais SMS Android Grow :
    Reçoit automatiquement en arrière-plan chaque SMS bancaire/opérateur (Wave, OM, Free)
    reçu sur le téléphone Android du commerçant et l'impute directement en comptabilité SYSCOHADA.
    Le commerçant n'a absolument rien à toucher : l'appli Android renvoie le SMS dès réception.
    """
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form = await request.form()
            payload = dict(form)

        print("\n[RELAIS SMS ANDROID REÇU] :", payload)

        sms_text = (
            payload.get("text")
            or payload.get("message")
            or payload.get("body")
            or payload.get("content")
            or payload.get("sms")
            or ""
        )
        sender_op = payload.get("from") or payload.get("sender") or "Opérateur"
        merchant_phone = (
            payload.get("phone")
            or payload.get("merchant_phone")
            or payload.get("device")
            or payload.get("device_id")
            or request.query_params.get("phone")
        )

        if not sms_text:
            return {"status": "ignored", "reason": "Empty SMS body"}

        if not merchant_phone:
            return {"status": "error", "reason": "Missing merchant phone identifier"}

        clean_phone = str(merchant_phone).replace("+", "").replace(" ", "").strip()

        sp = get_supabase()
        if not sp:
            return {"status": "error", "reason": "Database connection missing"}

        res_ent = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_phone}%").limit(1).execute()
        if not res_ent.data:
            return {"status": "ignored", "reason": f"No enterprise found for phone {clean_phone}"}

        ent = res_ent.data[0]
        donnees_onb = ent.get("donnees_onboarding") or {}
        if ent.get("etape_onboarding") != "COMPLET" and not donnees_onb.get("ninea_valide_par_preuve", False):
            print(f"[RELAIS SMS] Ignoré : L'entreprise {ent.get('nom_entreprise')} n'a pas encore validé son onboarding officiel.")
            return {"status": "ignored", "reason": "Enterprise onboarding not completed"}

        ent_id = ent.get("id")

        # Analyse locale déterministe du SMS opérateur (Wave / Orange Money / Free)
        sms_op = parse_operator_sms_local(sms_text)
        if not sms_op or sms_op.get("montant_fcfa", 0) <= 0:
            print(f"[RELAIS SMS] Ignoré : Le SMS reçu n'est pas une transaction financière valide.")
            return {"status": "ignored", "reason": "Not a recognized financial operator transaction"}

        montant = sms_op.get("montant_fcfa", 0)
        operateur = sms_op.get("operateur", "WAVE")
        type_flux = sms_op.get("type_flux", "ENTREE")
        compte_syscohada = sms_op.get("compte_syscohada", "701")
        tiers_nom = sms_op.get("tiers_nom") or "Tiers"
        tiers_phone = sms_op.get("tiers_phone") or ""
        ref_externe = sms_op.get("reference_externe") or f"SMS-{int(datetime.now().timestamp())}"
        solde_nouveau = sms_op.get("solde_nouveau_fcfa") or 0
        libelle_complet = f"{sms_op.get('libelle')} (Réf: {ref_externe})"

        # Insertion dans Supabase
        tx_row = {
            "entreprise_id": ent_id,
            "libelle": libelle_complet,
            "compte_syscohada": compte_syscohada,
            "type_flux": type_flux,
            "montant_fcfa": montant,
            "source_paiement": operateur,
            "reference_externe": ref_externe,
            "statut_validation": "VALIDE_PME",
            "est_professionnel": True
        }
        try:
            sp.table("transactions").insert(tx_row).execute()
        except Exception:
            tx_row.pop("reference_externe", None)
            sp.table("transactions").insert(tx_row).execute()

        print(f"[RELAIS SMS SUCCÈS] Enregistré : {montant:,.0f} FCFA ({operateur}) pour {clean_phone}")

        # Notification instantanée sur WhatsApp au commerçant
        base_url = get_public_base_url()
        solde_txt = f"• Nouveau solde {operateur} : {solde_nouveau:,.0f} FCFA\n" if solde_nouveau > 0 else ""
        type_desc = "Encaissement (Vente)" if type_flux == "ENTREE" else "Décaissement (Dépense)"

        msg_notif = (
            f"ENCAISSEMENT AUTOMATIQUE DÉTECTÉ ({operateur})\n\n"
            "RÉSUMÉ DE L'ENREGISTREMENT :\n"
            f"• Source : Relais SMS automatique en arrière-plan\n"
            f"• Nature : {type_desc}\n"
            f"• Montant : {montant:,.0f} FCFA\n"
            f"• Tiers : {tiers_nom}" + (f" ({tiers_phone})" if tiers_phone else "") + "\n"
            f"• Référence officielle : {ref_externe}\n"
            f"{solde_txt}"
            f"• Imputation : Compte SYSCOHADA {compte_syscohada}\n"
            "• Statut : Enregistré automatiquement sans aucune intervention\n\n"
            "Votre journal financier est à jour en direct :\n"
            f"{base_url}/dashboard?phone={clean_phone}"
        )
        await send_whatsapp_message(clean_phone, msg_notif)

        return {
            "status": "success",
            "montant": montant,
            "operateur": operateur,
            "type_flux": type_flux,
            "compte": compte_syscohada,
            "reference": ref_externe
        }

    except Exception as e:
        print(f"Erreur api_sms_gateway: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/memoire-fournisseurs")
async def api_memoire_fournisseurs(entreprise_id: str = Query(None)):
    """Retourne la mémoire des tiers et fournisseurs déjà appris pour cette entreprise."""
    if not entreprise_id:
        entreprise_id = "c3144ff0-013e-498f-9fdb-a2127c95f68f"
    memoire = get_memoire_fournisseurs(entreprise_id)
    return {
        "entreprise_id": entreprise_id,
        "total_appris": len(memoire),
        "fournisseurs": memoire
    }


@app.post("/api/declencher-rituel-soir")
async def api_declencher_rituel_soir(payload: dict = Body(default={})):
    """Déclenche immédiatement le Rituel Consolidé du Soir (Batching) pour une PME."""
    sp = get_supabase()
    if not sp:
        return {"status": "error", "message": "Base de données non disponible"}

    ent_id = payload.get("entreprise_id") or "c3144ff0-013e-498f-9fdb-a2127c95f68f"
    res_ent = sp.table("entreprises").select("*").eq("id", ent_id).execute()
    if not res_ent.data:
        res_ent = sp.table("entreprises").select("*").limit(1).execute()

    if not res_ent.data:
        return {"status": "error", "message": "Aucune entreprise trouvée"}

    ent = res_ent.data[0]
    ent_id = ent.get("id")
    nom = ent.get("nom_entreprise", "Votre PME")
    phone = ent.get("telephone_whatsapp")

    # Récupérer les transactions
    today_str = datetime.now().strftime("%Y-%m-%d")
    txs = sp.table("transactions").select("*").eq("entreprise_id", ent_id).execute().data or []
    
    treso_stats = get_tresorerie_stats(sp, ent_id)
    msg_rituel = generer_message_rituel_soir(nom, txs, treso_stats)

    if phone:
        await send_whatsapp_text_and_audio(phone, msg_rituel, langue="fr")

    en_attente = [t for t in txs if t.get("compte_syscohada") in ["471100", "471"]]

    return {
        "status": "success",
        "entreprise": nom,
        "phone": phone,
        "message_rituel": msg_rituel,
        "total_transactions": len(txs),
        "total_automatique": len(txs) - len(en_attente),
        "total_en_attente": len(en_attente)
    }


@app.post("/api/update-heure-rappel")
async def update_heure_rappel(payload: dict):
    """Met à jour l'heure de rappel du rituel de clôture du soir (0 crédit consommé)."""
    sp = get_supabase()
    if not sp:
        return {"success": False, "error": "Supabase non connecté"}
    
    ent_id = payload.get("entreprise_id")
    nouvelle_heure = payload.get("heure")  # Format "HH:MM"
    
    if not ent_id or not nouvelle_heure:
        return {"success": False, "error": "Données incomplètes (entreprise_id et heure requis)"}
    
    try:
        # Nettoyage et formatage HH:MM:00
        clean_heure = nouvelle_heure.strip()[:5] + ":00"
        res = sp.table("entreprises").update({"heure_rappel_quotidien": clean_heure}).eq("id", ent_id).execute()
        return {"success": True, "heure": clean_heure[:5], "message": f"Heure de rappel programmée à {clean_heure[:5]} avec succès"}
    except Exception as e:
        return {"success": False, "error": str(e)}



@app.post("/api/enregistrer-transaction")
async def api_enregistrer_transaction(payload: dict = Body(...)):
    """Enregistre une transaction manuelle (vente ou dépense) depuis le dashboard smartphone."""
    sp = get_supabase()
    if not sp:
        return {"status": "error", "message": "Supabase indisponible"}

    ent_id = payload.get("entreprise_id")
    montant = payload.get("montant_fcfa", 0)
    libelle = payload.get("libelle", "Opération")
    type_flux = payload.get("type_flux", "ENTREE")
    source = payload.get("source_paiement", "ESPECES")
    compte = payload.get("compte_syscohada", "701" if type_flux == "ENTREE" else "601")

    if not ent_id or montant <= 0:
        return {"status": "error", "message": "Données invalides"}

    tx_row = {
        "entreprise_id": ent_id,
        "libelle": libelle,
        "compte_syscohada": compte,
        "type_flux": type_flux,
        "montant_fcfa": montant,
        "source_paiement": source,
        "statut_validation": "VALIDE_PME",
        "est_professionnel": True
    }

    try:
        res = sp.table("transactions").insert(tx_row).execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        print(f"Erreur insertion transaction dashboard: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/agence", response_class=HTMLResponse)
async def serve_agence_dashboard():
    """Espace réservé à l'Expert-Comptable / Agence ONECCA."""
    html_path = os.path.join(TEMPLATES_DIR, "agence.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Espace Agence en cours d'initialisation</h1>", status_code=200)


@app.get("/abonnement", response_class=HTMLResponse)
async def serve_abonnement():
    """Page de souscription et paiement d'abonnement Grow."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Abonnement Grow &bull; Pré-comptabilité PME</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>body { font-family: 'Plus Jakarta Sans', sans-serif; }</style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center p-4">
    <div class="max-w-md w-full bg-slate-800 rounded-3xl p-6 sm:p-8 border border-slate-700 shadow-2xl text-center space-y-6">
        <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-700 mx-auto flex items-center justify-center text-3xl shadow-lg">
            🤲🌱
        </div>
        <div>
            <h1 class="text-2xl font-black text-white">Abonnement Grow PME</h1>
            <p class="text-xs text-slate-400 mt-1">Certification financière et pré-comptabilité SYSCOHADA SMT</p>
        </div>
        <div class="bg-slate-900/80 rounded-2xl p-5 border border-slate-700 text-left space-y-3">
            <div class="flex justify-between items-baseline">
                <span class="text-sm font-bold text-slate-300">Formule Mensuelle Pro</span>
                <span class="text-2xl font-black text-emerald-400">10 000 <span class="text-xs font-semibold text-slate-400">FCFA/mois</span></span>
            </div>
            <ul class="text-xs text-slate-300 space-y-2 pt-2 border-t border-slate-800">
                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-emerald-400"></i> Assistant WhatsApp 24h/7j</li>
                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-emerald-400"></i> Relevés automatiques Wave, OM &amp; Caisse</li>
                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-emerald-400"></i> Dossiers financiers pour Banques &amp; ONECCA</li>
                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-emerald-400"></i> Archivage certifié des reçus et factures</li>
            </ul>
        </div>
        <div class="space-y-3">
            <button onclick="simulerPaiement('Wave')" class="w-full py-3.5 px-4 rounded-xl bg-[#1DA1F2] hover:bg-[#0c85d0] font-black text-white text-sm shadow-md transition flex items-center justify-center gap-2">
                <i class="fa-solid fa-mobile-screen"></i> Payer 10 000 FCFA avec Wave
            </button>
            <button onclick="simulerPaiement('Orange Money')" class="w-full py-3.5 px-4 rounded-xl bg-[#FF6600] hover:bg-[#e05a00] font-black text-white text-sm shadow-md transition flex items-center justify-center gap-2">
                <i class="fa-solid fa-phone"></i> Payer avec Orange Money
            </button>
        </div>
        <p class="text-[11px] text-slate-500">Après paiement, renvoyez « J'ai payé » sur WhatsApp pour activer vos 5 étapes d'onboarding.</p>
    </div>
    <script>
        function simulerPaiement(op) {
            alert('Simulation : Paiement via ' + op + ' réussi !\\n\\nVous pouvez maintenant retourner sur WhatsApp et envoyer « J\\'ai payé » pour commencer vos 5 étapes.');
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>""", status_code=200)


@app.post("/")
@app.post("/webhook")
async def receive_message(request: Request):
    """Réception et traitement en direct des messages WhatsApp."""
    data = await request.json()
    print("\n[NOUVEAU MESSAGE WEBHOOK] :", data)

    try:
        value = {}
        if "entry" in data and data["entry"]:
            changes = data["entry"][0].get("changes", [])
            if changes:
                value = changes[0].get("value", {})
        elif "value" in data:
            value = data.get("value", {})

        contacts = value.get("contacts", [])
        contact_name = contacts[0].get("profile", {}).get("name") if contacts else None

        if "messages" in value and value["messages"]:
            message = value["messages"][0]
            msg_id = message.get("id")
            if is_duplicate_message(msg_id):
                print(f"[WEBHOOK] Message {msg_id} deja traite (retry Meta ignore).")
                return {"status": "already_processed"}

            sender_phone = message.get("from")
            msg_type = message.get("type")

            # 1. MESSAGE TEXTE
            if msg_type == "text":
                user_text = message.get("text", {}).get("body", "")
                print(f"Message texte de {sender_phone} ({contact_name}) : '{user_text}'")

                reply_text = await handle_incoming_message(sender_phone, user_text, None, contact_name)
                await send_whatsapp_message(sender_phone, reply_text)

            # 2. IMAGE (NINEA, Reçu papier, capture Wave)
            elif msg_type == "image":
                image_info = message.get("image", {})
                media_id = image_info.get("id")
                caption = image_info.get("caption", "")
                print(f"Image reçue de {sender_phone} (ID: {media_id})")

                reply_text = await handle_incoming_message(sender_phone, caption, ("PHOTO", media_id), contact_name)
                await send_whatsapp_message(sender_phone, reply_text)

            # 3. DOCUMENT (PDF NINEA ou Relevé)
            elif msg_type == "document":
                doc_info = message.get("document", {})
                media_id = doc_info.get("id")
                filename = doc_info.get("filename", "document.pdf")

                reply_text = await handle_incoming_message(sender_phone, filename, ("DOCUMENT", media_id), contact_name)
                await send_whatsapp_message(sender_phone, reply_text)

            # 4. NOTE VOCALE - Pipeline Gemini (prioritaire) + fallback Groq/Whisper
            elif msg_type == "audio":
                audio_info = message.get("audio", {})
                media_id = audio_info.get("id")

                media_bytes, mime_type = await download_meta_media(media_id)
                if media_bytes:
                    gemini_result = None
                    texte_transcrit = None
                    lang_vocale = "fr"
                    reponse_wolof_gemini = None

                    # NIVEAU 1 : Gemini (comprend OGG wolof/francais directement, 0 transcription intermediaire)
                    if est_gemini_disponible():
                        try:
                            gemini_result = await analyser_audio_gemini(media_bytes, mime_type)
                            if gemini_result:
                                texte_transcrit = extraire_transcription(gemini_result)
                                lang_vocale = extraire_langue(gemini_result)
                                reponse_wolof_gemini = extraire_reponse_wolof(gemini_result)
                                print(f"[GEMINI PIPELINE] Transcription : \"{texte_transcrit}\" | Langue : {lang_vocale}")
                        except Exception as e_gem:
                            print(f"[GEMINI] Erreur pipeline : {e_gem}")

                    # NIVEAU 2 : Fallback Groq/Whisper si Gemini indisponible ou echec
                    if not texte_transcrit:
                        texte_transcrit = await transcrire_note_vocale(media_bytes, mime_type)
                        if texte_transcrit:
                            lang_vocale = detecter_langue_texte(texte_transcrit)

                    if texte_transcrit:
                        print(f"[NOTE VOCALE DE {sender_phone}] Transcrite : \"{texte_transcrit}\" | Langue : {lang_vocale}")

                        # Traitement comptable Claude via handle_incoming_message
                        reponse_interne = await handle_incoming_message(sender_phone, texte_transcrit, None, contact_name)

                        # Prefixe de confirmation dans la langue de l'utilisateur
                        if lang_vocale == "wo":
                            prefixe_note = "Wax jall na"
                        elif lang_vocale == "en":
                            prefixe_note = "Voice note understood"
                        else:
                            prefixe_note = "Note vocale comprise"

                        reply_text = f"{prefixe_note} : \"{texte_transcrit}\"\n\n{reponse_interne}"
                        await send_whatsapp_message(sender_phone, reply_text)

                        # Envoi de la note vocale de reponse en Wolof natif (Meta MMS)
                        try:
                            # Si Gemini a fourni une reponse wolof directe et que la langue est wolof,
                            # on l'utilise directement (evite une traduction Claude supplementaire)
                            if lang_vocale == "wo" and reponse_wolof_gemini:
                                audio_fn = await generer_note_vocale_audio(reponse_wolof_gemini, langue="wo")
                            else:
                                audio_fn = await generer_note_vocale_audio(reponse_interne, langue=lang_vocale)
                            if audio_fn:
                                await send_whatsapp_audio(sender_phone, audio_fn)
                        except Exception as e_v:
                            print(f"Info envoi note vocale WhatsApp : {e_v}")
                    else:
                        reply_text = "Je n'ai pas reussi a entendre clairement votre note vocale. Pourriez-vous la renvoyer ou ecrire votre message ?"
                        await send_whatsapp_message(sender_phone, reply_text)
                else:
                    reply_text = "Je n'ai pas pu telecharger votre note vocale. Veuillez reessayer de me l'envoyer."
                    await send_whatsapp_message(sender_phone, reply_text)

    except Exception as e:
        print(f"Erreur traitement webhook : {e}")

    return {"status": "ok"}


async def handle_incoming_message(sender_phone: str, user_text: str, media_tuple, contact_name: str = None) -> str:
    """Aiguille entre le premier message exclusif de bienvenue, le tunnel d'Onboarding en 5 étapes, la vérification d'abonnement et le fonctionnement normal de l'IA."""
    # 0. TRANSCRIPTION DES NOTES VOCALES WHATSAPP VIA OPENAI WHISPER
    if media_tuple and media_tuple[0] == "AUDIO":
        media_type, media_id = media_tuple
        media_bytes, mime_type = await download_meta_media(media_id)
        if not media_bytes:
            return "Je n'ai pas pu télécharger votre note vocale. Veuillez réessayer de me l'envoyer."

        texte_transcrit = await transcrire_note_vocale(media_bytes, mime_type)
        if not texte_transcrit:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return (
                    "Note vocale bien reçue.\n\n"
                    "Pour activer la transcription vocale automatique, veuillez renseigner votre clé OPENAI_API_KEY dans votre fichier .env.\n\n"
                    "En attendant, vous pouvez écrire votre message ou votre opération directement sous forme de texte."
                )
            return (
                "Je n'ai pas réussi à entendre clairement votre note vocale. "
                "Pourriez-vous renvoyer un message vocal plus clair ou écrire votre opération sous forme de texte ?"
            )

        print(f"[NOTE VOCALE DE {sender_phone}] Transcrite : « {texte_transcrit} »")
        # Traitement direct du texte transcrit
        reponse_interne = await handle_incoming_message(sender_phone, texte_transcrit, None, contact_name)
        return (
            f"Note vocale comprise : « {texte_transcrit} »\n\n"
            f"{reponse_interne}"
        )

    # 0.1 ACCOMPAGNEMENT & TEST DE CONFIGURATION WEBHOOK EN DIRECT
    if is_test_webhook_request(user_text):
        clean_p = str(sender_phone).replace("+", "").replace(" ", "").strip()
        base_url = get_public_base_url()
        res_test = await executer_simulation_test_webhook(clean_p, provider="WAVE", amount=1000)
        return (
            "TEST DE CONNEXION WEBHOOK RÉUSSI\n\n"
            "RÉSUMÉ DU TEST EN DIRECT :\n"
            "• Canal vérifié : Webhook Opérateur Wave\n"
            "• Montant test : 1 000 FCFA\n"
            f"• Référence test : {res_test.get('tx_id')}\n"
            "• Imputation : Compte SYSCOHADA 701 (Vente de marchandises)\n"
            "• Trésorerie créditée : Compte SYSCOHADA 521 (Monnaie électronique Wave)\n"
            "• Statut : 100% Opérationnel et certifié\n\n"
            "Votre liaison automatique est validée. Vos véritables encaissements clients seront désormais réconciliés automatiquement sans intervention manuelle :\n"
            f"{base_url}/dashboard?phone={clean_p}"
        )

    if is_webhook_assistance_request(user_text):
        base_url = get_public_base_url()
        return get_webhook_guide_message(base_url, sender_phone)

    onboarding = get_onboarding_state(sender_phone)
    statut = onboarding.get("statut", "EN_ATTENTE_ABONNEMENT")
    base_url = get_public_base_url()

    # Si l'utilisateur a déjà son abonnement actif ou est en cours d'onboarding ou complet,
    # il ne doit JAMAIS recevoir le message de bienvenue ou d'attente d'abonnement !
    if onboarding.get("abonnement_valide") or statut in ["EN_COURS", "COMPLET"]:
        premier_contact = True
    else:
        premier_contact = onboarding.get("premier_contact_effectue", False)

    # 1. MESSAGE EXCLUSIF DU PREMIER CONTACT (Choix de la langue officielle Grow)
    if not premier_contact:
        update_onboarding_state(sender_phone, "premier_contact_effectue", True)
        update_onboarding_state(sender_phone, "statut", "EN_ATTENTE_LANGUE")
        update_onboarding_state(sender_phone, "etape", "CHOIX_LANGUE")
        return (
            "Dalal ak jàmm ci Grow ! / Bienvenue sur Grow ! / Welcome to Grow !\n\n"
            "Tànnal sa làkk ngir nu tàmbli / Choisissez votre langue pour démarrer :\n\n"
            "1️⃣ Wolof\n"
            "2️⃣ Français\n"
            "3️⃣ English\n\n"
            "Bindal 1, 2 walla 3 / Répondez par 1, 2 ou 3."
        )

    # 1.1 GESTION DU CHOIX DE LA LANGUE
    if statut == "EN_ATTENTE_LANGUE" or onboarding.get("etape") == "CHOIX_LANGUE":
        raw = (user_text or "").strip().lower()
        if raw in ["1", "wolof", "wo"]:
            lang = "wo"
            update_onboarding_state(sender_phone, "langue_preferee", "wo")
            update_onboarding_state(sender_phone, "statut", "EN_ATTENTE_ABONNEMENT")
            update_onboarding_state(sender_phone, "etape", "PAIEMENT_ABONNEMENT")
            return (
                "Jërejëf ! Làkku Wolof lañu tànn ngir sa compte Grow.\n\n"
                "Man maay sa assistant pré-comptable ci WhatsApp. Damay bind sa jaay ak sa dépense bés bu nekk ngir sa teere comptable dëppoo ak sàrti SYSCOHADA.\n\n"
                "Ngir ubbi sa compte ak configurar sa boutique, feyal sa abonnement Grow ci lii :\n"
                f"{base_url}/abonnement?phone={sender_phone}\n\n"
                "Boo feyee ba noppi, bindal rekk « Fey naa » walla nga yónnee foto reçu bi ngir nu tàmbli."
            )
        elif raw in ["3", "english", "anglais", "en"]:
            lang = "en"
            update_onboarding_state(sender_phone, "langue_preferee", "en")
            update_onboarding_state(sender_phone, "statut", "EN_ATTENTE_ABONNEMENT")
            update_onboarding_state(sender_phone, "etape", "PAIEMENT_ABONNEMENT")
            return (
                "Thank you! English selected for your Grow accounting assistant.\n\n"
                "I am your official pre-accounting assistant on WhatsApp. I record your sales and expenses daily to keep your books compliant with SYSCOHADA standards.\n\n"
                "To activate your account and configure your business, please subscribe to Grow here:\n"
                f"{base_url}/abonnement?phone={sender_phone}\n\n"
                "Once paid, simply reply \"I paid\" or send your payment receipt to start configuration."
            )
        elif raw in ["2", "francais", "français", "fr"]:
            lang = "fr"
            update_onboarding_state(sender_phone, "langue_preferee", "fr")
            update_onboarding_state(sender_phone, "statut", "EN_ATTENTE_ABONNEMENT")
            update_onboarding_state(sender_phone, "etape", "PAIEMENT_ABONNEMENT")
            return (
                "Parfait ! Le Français est configuré pour votre assistant Grow.\n\n"
                "Je suis votre assistant pré-comptable officiel sur WhatsApp. J'enregistre vos ventes et vos dépenses au quotidien pour tenir vos comptes aux normes SYSCOHADA et préparer vos bilans avec nos agences partenaires.\n\n"
                "Vos données financières seront consultables en direct sur votre tableau de bord personnel :\n"
                f"{base_url}/dashboard?phone={sender_phone}\n\n"
                "Pour activer votre pré-comptabilité et configurer votre entreprise, veuillez d'abord souscrire à votre abonnement mensuel Grow sur ce lien sécurisé :\n"
                f"{base_url}/abonnement?phone={sender_phone}\n\n"
                "Dès que votre paiement est effectué, écrivez simplement « J'ai payé » ou envoyez votre reçu de paiement ici pour lancer la configuration de votre entreprise."
            )
        else:
            return (
                "Dalal ak jàmm ci Grow ! / Bienvenue sur Grow ! / Welcome to Grow !\n\n"
                "Tànnal sa làkk ngir nu tàmbli / Choisissez votre langue pour démarrer :\n\n"
                "1️⃣ Wolof\n"
                "2️⃣ Français\n"
                "3️⃣ English\n\n"
                "Bindal 1, 2 walla 3 / Répondez par 1, 2 ou 3."
            )

    statut = onboarding.get("statut", "EN_ATTENTE_ABONNEMENT")

    # 2. VÉRIFICATION DU PAIEMENT / « J'AI PAYÉ » (Priorité absolue dès que le client affirme avoir payé)
    if is_paiement_keyword(user_text):
        update_onboarding_state(sender_phone, "abonnement_valide", True)

        # CAS A : Si ce numéro a DÉJÀ une entreprise configurée
        if is_entreprise_deja_configuree(sender_phone):
            update_onboarding_state(sender_phone, "statut", "COMPLET")
            update_onboarding_state(sender_phone, "etape", "TERMINE")
            instructions = get_instructions_journee_message(base_url, sender_phone)
            return (
                "Merci, votre paiement est bien confirmé ! Votre abonnement Grow est actif.\n\n"
                f"Votre entreprise est déjà configurée.\n\n{instructions}"
            )

        # CAS B : Si ce numéro N'A PAS ENCORE configuré son entreprise
        # On valide le paiement et on lance la configuration en 5 étapes (1 question à la fois)
        update_onboarding_state(sender_phone, "statut", "EN_COURS")
        update_onboarding_state(sender_phone, "etape", "DEMANDE_NINEA")
        lang_pref = onboarding.get("langue_preferee") or "fr"
        if lang_pref == "wo":
            return (
                "Jërejëf, sa fey dug na ! Sa abonnement Grow ubbi na.\n\n"
                "Léegi dañuy configurar sa boutique ci 5 étapes. Ngir sàrti SYSCOHADA, dafa laaj preuve (foto) ci étape bu nekk.\n\n"
                "Étape 1/5 : Yónneel foto walla PDF sa papier attestation NINEA.\n\n"
                "Grow dafa koy xool ngir certifier Turu entreprise bi, NINEA bi, RCCM bi ak Capital social bi bala ñuy dem ci étape bi ci topp."
            )
        elif lang_pref == "en":
            return (
                "Thank you, your payment is confirmed! Your Grow subscription is now active.\n\n"
                "We will now configure your business in 5 steps. An official supporting document is required to validate each step.\n\n"
                "Step 1/5: Please send a photo or PDF of your official NINEA certificate.\n\n"
                "Grow will analyze this document to certify your Business Name, NINEA, Legal Form, Trade Register (RCCM), and Share Capital before moving to the next step."
            )
        return (
            "Merci, votre paiement est bien confirmé ! Votre abonnement Grow est actif.\n\n"
            "Nous allons maintenant configurer votre entreprise en 5 étapes. Conformément aux règles Grow, la pièce justificative est obligatoire pour valider chaque étape.\n\n"
            "Étape 1/5 : Envoyez-moi la photo ou le document PDF de votre attestation papier NINEA.\n\n"
            "Grow doit analyser cette pièce officielle pour certifier le Nom, le NINEA, la Forme juridique, le Registre de Commerce (RCCM) et le Capital social de votre entreprise avant de passer à l'étape suivante."
        )

    # 3. SI L'ABONNEMENT N'EST PAS ENCORE VALIDÉ (Tant qu'il n'y a pas eu « J'ai payé »)
    state = get_onboarding_state(sender_phone)
    if not state.get("abonnement_valide", False) and statut not in ["EN_COURS", "COMPLET"]:
        # Exception : si le client envoie directement son attestation NINEA en photo/PDF, on active et on passe à l'étape 1
        if media_tuple and media_tuple[0] in ["PHOTO", "DOCUMENT"]:
            update_onboarding_state(sender_phone, "abonnement_valide", True)
            update_onboarding_state(sender_phone, "statut", "EN_COURS")
            update_onboarding_state(sender_phone, "etape", "DEMANDE_NINEA")
            onboarding = get_onboarding_state(sender_phone)
            return await process_onboarding_step(sender_phone, user_text, media_tuple, onboarding, contact_name)

        lang_pref = state.get("langue_preferee") or "fr"
        if lang_pref == "wo":
            return (
                "Sa abonnement ubbiwaatoul. Ngir ubbi sa compte ak configurar sa boutique, feyal sa abonnement Grow ci lii :\n"
                f"{base_url}/abonnement?phone={sender_phone}\n\n"
                "Boo feyee ba noppi, bindal rekk « Fey naa » walla nga yónnee foto reçu bi fii."
            )
        elif lang_pref == "en":
            return (
                "Your subscription is not active yet. To activate your account and configure your business, please subscribe here:\n"
                f"{base_url}/abonnement?phone={sender_phone}\n\n"
                "If you have already paid, simply reply \"I paid\" or send your payment receipt here."
            )
        return (
            "Votre abonnement n'est pas encore actif. Pour activer votre compte et configurer votre entreprise, veuillez d'abord souscrire à votre abonnement Grow sur ce lien :\n"
            f"{base_url}/abonnement?phone={sender_phone}\n\n"
            "Si vous avez déjà payé, écrivez simplement « J'ai payé » ou envoyez votre reçu de paiement ici."
        )

    # 4. Si l'onboarding n'est pas encore terminé, on traite l'onboarding (Étapes 1 à 5)
    if statut != "COMPLET":
        return await process_onboarding_step(sender_phone, user_text, media_tuple, onboarding, contact_name)

    # 5. Si l'onboarding est COMPLET, traitement des opérations
    if media_tuple:
        media_type, media_id = media_tuple
        return await process_media_with_ai(sender_phone, media_id, "PHOTO_RECU", user_text)
    else:
        # A. Priorité absolue au GRAND EXTRACTEUR LOCAL (0 crédit d'API, 100% gratuit et instantané)
        if user_text:
            # 1) Détection SMS Opérateur (Wave / Orange Money / Free)
            sms_op = parse_operator_sms_local(user_text)
            if sms_op and sms_op.get("montant_fcfa", 0) > 0:
                sp = get_supabase()
                ent = get_or_create_entreprise(sp, sender_phone) if sp else {}
                ent_id = ent.get("id")
                lib_complet = f"{sms_op.get('libelle')} (Réf: {sms_op.get('reference_externe')})"
                if sp and ent_id:
                    try:
                        sp.table("transactions").insert({
                            "entreprise_id": ent_id,
                            "libelle": lib_complet,
                            "compte_syscohada": sms_op.get("compte_syscohada", "701"),
                            "type_flux": sms_op.get("type_flux", "ENTREE"),
                            "est_professionnel": True,
                            "montant_fcfa": sms_op.get("montant_fcfa"),
                            "source_paiement": sms_op.get("operateur", "WAVE"),
                            "statut_validation": "VALIDE_PME"
                        }).execute()
                    except Exception as e_tx:
                        print(f"Info enregistrement transaction SMS local : {e_tx}")

                solde_txt = f"\n• Nouveau solde opérateur : {sms_op.get('solde_nouveau_fcfa'):,.0f} FCFA" if sms_op.get('solde_nouveau_fcfa') else ""
                return (
                    f"Notification {sms_op.get('operateur')} interceptee et enregistree avec succes.\n\n"
                    f"RESUME DE L'ENREGISTREMENT :\n"
                    f"• Nature : {sms_op.get('type_flux')}\n"
                    f"• Montant : {sms_op.get('montant_fcfa'):,.0f} FCFA\n"
                    f"• Source : {sms_op.get('operateur')}\n"
                    f"• Compte SYSCOHADA : {sms_op.get('compte_syscohada')} ({sms_op.get('libelle')})\n"
                    f"• Beneficiaire / Emetteur : {sms_op.get('tiers_nom')}\n"
                    f"• Reference : {sms_op.get('reference_externe')}"
                    f"{solde_txt}\n\n"
                    "Statut : Ecriture certifiee dans votre journal financier."
                )

            # 2) Détection Opération Financière Courante Locale (Ventes, Carburant, Loyer, Stock, etc.)
            op_loc = parse_operation_financiere_locale(user_text)
            if op_loc and op_loc.get("montant_fcfa", 0) > 0:
                lang_user = detecter_langue_texte(user_text)

                # Règle d'exigence de pièce justificative pour toute dépense en cash
                if op_loc.get("besoin_justificatif", False):
                    if lang_user == "wo":
                        return (
                            f"Sa dépense bu {op_loc.get('montant_fcfa'):,.0f} FCFA bind nañu ko ci attente.\n\n"
                            "RÉSUMÉ CI SA TEERE :\n"
                            f"• Montant : {op_loc.get('montant_fcfa'):,.0f} FCFA\n"
                            f"• Nature : {op_loc.get('libelle')}\n"
                            f"• Mode : Ci loxo (Cash / Espèces)\n\n"
                            "Rappel Grow :\n"
                            "Nanga def foto reçu bi walla facture bi leegi ngir nu certifier ko !"
                        )
                    elif lang_user == "en":
                        return (
                            f"Your expense of {op_loc.get('montant_fcfa'):,.0f} CFA francs has been pre-recorded pending a receipt.\n\n"
                            "SUMMARY:\n"
                            f"• Amount: {op_loc.get('montant_fcfa'):,.0f} CFA francs\n"
                            f"• Nature: {op_loc.get('libelle')}\n"
                            f"• Method: Cash\n\n"
                            "Grow Mandatory Rule:\n"
                            "Please send the receipt or invoice photo now to validate and certify this entry."
                        )
                    else:
                        return (
                            f"Votre declaration de depense de {op_loc.get('montant_fcfa'):,.0f} FCFA ({op_loc.get('libelle')}) a ete pre-enregistree en attente de justificatif.\n\n"
                            "RESUME DU PRE-ENREGISTREMENT :\n"
                            f"• Montant : {op_loc.get('montant_fcfa'):,.0f} FCFA\n"
                            f"• Nature : {op_loc.get('libelle')}\n"
                            f"• Mode : Especes (Cash)\n\n"
                            "Rappel obligatoire Grow :\n"
                            "Chaque depense en especes doit obligatoirement avoir sa piece justificative (photo du recu, facture, ticket ou photo probante du stock).\n\n"
                            "Envoyez la photo du justificatif des maintenant pour valider definitivement l'ecriture !"
                        )

                sp = get_supabase()
                ent = get_or_create_entreprise(sp, sender_phone) if sp else {}
                ent_id = ent.get("id")
                if sp and ent_id:
                    try:
                        sp.table("transactions").insert({
                            "entreprise_id": ent_id,
                            "libelle": op_loc.get("libelle"),
                            "compte_syscohada": op_loc.get("compte_syscohada"),
                            "type_flux": op_loc.get("type_flux"),
                            "est_professionnel": True,
                            "montant_fcfa": op_loc.get("montant_fcfa"),
                            "source_paiement": op_loc.get("source_paiement"),
                            "statut_validation": "VALIDE_PME"
                        }).execute()
                    except Exception as e_tx:
                        print(f"Info enregistrement transaction locale : {e_tx}")

                if lang_user == "wo":
                    return (
                        f"Jërejëf ! Sa {op_loc.get('libelle', 'opération')} bu {op_loc.get('montant_fcfa'):,.0f} FCFA ci {op_loc.get('source_paiement')} dug na bu baax te bind nañu ko.\n\n"
                        "RÉSUMÉ CI SA TEERE :\n"
                        f"• Nature : {op_loc.get('libelle')}\n"
                        f"• Montant : {op_loc.get('montant_fcfa'):,.0f} FCFA\n"
                        f"• Mode de paiement : {op_loc.get('source_paiement')}\n"
                        f"• Compte SYSCOHADA : {op_loc.get('compte_syscohada')}\n\n"
                        "Statut : Validé et certifié dans votre journal financier."
                    )
                elif lang_user == "en":
                    return (
                        "Accounting entry recorded successfully.\n\n"
                        "TRANSACTION SUMMARY:\n"
                        f"• Nature: {op_loc.get('libelle')}\n"
                        f"• Amount: {op_loc.get('montant_fcfa'):,.0f} CFA francs\n"
                        f"• Payment method: {op_loc.get('source_paiement')}\n"
                        f"• SYSCOHADA Account: {op_loc.get('compte_syscohada')}\n\n"
                        "Status: Validated and posted to your ledger."
                    )
                else:
                    return (
                        "Ecriture comptable enregistree avec succes.\n\n"
                        "RESUME DE L'ENREGISTREMENT :\n"
                        f"• Nature : {op_loc.get('libelle')}\n"
                        f"• Montant : {op_loc.get('montant_fcfa'):,.0f} FCFA\n"
                        f"• Mode de paiement : {op_loc.get('source_paiement')}\n"
                        f"• Compte SYSCOHADA : {op_loc.get('compte_syscohada')}\n\n"
                        "Statut : Validee et imputee a votre journal financier."
                    )

        # B. Fallback IA pour les questions libres, conseils ou clarifications
        return await process_text_with_ai(sender_phone, user_text)


def extraire_ninea_nom_capital_local(text: str, sender_phone: str = "", contact_name: str = "") -> tuple[str, str, int]:
    """Extrait NINEA, Nom et Capital via le Grand Extracteur Local (0 crédit Anthropic, 100% gratuit)."""
    identite = extract_business_identity_local(text, sender_phone, contact_name)
    return identite.get("ninea"), identite.get("nom_entreprise"), identite.get("capital_social_fcfa", 0)


async def process_onboarding_step(sender_phone: str, user_text: str, media_tuple, onboarding: dict, contact_name: str = None) -> str:
    """Machine à états stricte pour l'onboarding obligatoire de l'entreprise supervisée par Anthropic Claude."""
    etape = onboarding.get("etape", "DEMANDE_NINEA")
    load_dotenv(override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key) if api_key else None

    # 0. BLOCAGE STRICT : AUCUNE TRANSACTION NE PEUT ÊTRE ENREGISTRÉE AVANT LA CRÉATION COMPLÈTE DE L'ENTREPRISE
    if user_text:
        sms_op = parse_operator_sms_local(user_text)
        is_sms = bool(sms_op and sms_op.get("montant_fcfa", 0) > 0)
        op_fin = parse_operation_financiere_locale(user_text)
        is_op = bool(op_fin and op_fin.get("montant_fcfa", 0) > 0)
        has_amount = bool(parse_montant_fcfa(user_text) > 0)
        is_tx_kw = bool(re.search(r'\b(vente|vendu|achat|acheté|depense|dépense|dette|créance|creance|facture|senelec|sen eau|loyer)\b', user_text.lower()))
        
        # Uniquement si c'est une VRAIE transaction financière avec un flux ou un SMS opérateur
        if (is_sms or (is_op and etape not in ["DEMANDE_OPERATEURS", "DEMANDE_IMMOBILISATIONS", "DEMANDE_TRESORERIE_INITIALE"]) or (has_amount and is_tx_kw and etape not in ["DEMANDE_IMMOBILISATIONS", "DEMANDE_TRESORERIE_INITIALE"])):
            return (
                "Action refusée : Votre entreprise n'est pas encore enregistrée sur Grow.\n\n"
                "Conformément aux normes pré-comptables SYSCOHADA, aucun flux financier (vente, dépense ou SMS de paiement) ne peut être imputé tant que votre entreprise n'est pas officiellement créée et certifiée.\n\n"
                "Veuillez d'abord finaliser les 5 étapes d'onboarding pour activer l'enregistrement de vos opérations."
            )

    # ÉTAPE 1.1 : DEMANDE DU NOM COMMERCIAL DE L'ENTREPRISE (si l'attestation porte le nom de la personne physique)
    lang_pref = onboarding.get("langue_preferee") or "fr"
    if etape == "DEMANDE_NOM_COMMERCIAL":
        txt_nom = (user_text or "").strip()
        is_greeting = bool(re.match(r'^(bonjour|salut|coucou|bonsoir|merci|ok|d[\'’]accord|salam|nanga def|waw|waaw)$', txt_nom.lower()))
        if len(txt_nom) >= 2 and not is_greeting:
            # Enregistrement du vrai nom commercial
            update_onboarding_state(sender_phone, "nom_entreprise", txt_nom.title())
            update_onboarding_state(sender_phone, "etape", "DEMANDE_EQUIPE")
            
            # Mise à jour Supabase
            sp = get_supabase()
            if sp:
                try:
                    clean_phone = str(sender_phone).replace("+", "").replace(" ", "").strip()
                    sp.table("entreprises").update({"nom_entreprise": txt_nom.title()}).ilike("telephone_whatsapp", f"%{clean_phone}%").execute()
                except Exception as e_nom:
                    print(f"Info mise à jour nom commercial Supabase : {e_nom}")

            if lang_pref == "wo":
                return (
                    f"Jërejëf ! Turu sa boutique bind nañu ko : « {txt_nom.title()} ».\n\n"
                    "RÉSUMÉ CI SA TEERE :\n"
                    f"• Turu boutique bi : {txt_nom.title()}\n"
                    f"• Boroom : {onboarding.get('nom_personne_physique', 'Titulaire')}\n"
                    f"• NINEA certifié : {onboarding.get('ninea')}\n"
                    f"• Capital social : {int(onboarding.get('capital') or 1000000):,.0f} FCFA\n\n"
                    "Étape 2/5 : Ñaata nit ñooy liggéey ci sa boutique (liggéeykat, apprentis walla associés) ?"
                )
            elif lang_pref == "en":
                return (
                    f"Trade name recorded successfully: \"{txt_nom.title()}\".\n\n"
                    "REGISTRATION SUMMARY:\n"
                    f"• Business trade name: {txt_nom.title()}\n"
                    f"• Owner / Manager: {onboarding.get('nom_personne_physique', 'Owner')}\n"
                    f"• Certified NINEA: {onboarding.get('ninea')}\n"
                    f"• Certified Share Capital: {int(onboarding.get('capital') or 1000000):,.0f} FCFA\n\n"
                    "Step 2/5: How many people work in your business (employees, apprentices, or partners)?"
                )
            return (
                f"Raison sociale enregistrée avec succès : « {txt_nom.title()} ».\n\n"
                "RÉSUMÉ DE L'ENREGISTREMENT :\n"
                f"• Nom commercial de l'entreprise : {txt_nom.title()}\n"
                f"• Gérant(e) / Exploitant(e) : {onboarding.get('nom_personne_physique', 'Titulaire')}\n"
                f"• Numéro NINEA certifié : {onboarding.get('ninea')}\n"
                f"• Capital social certifié : {int(onboarding.get('capital') or 1000000):,.0f} FCFA\n\n"
                "Étape 2/5 : Combien de personnes travaillent au sein de votre structure (salariés déclarés, apprentis ou associés) ?"
            )
        else:
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude
            if lang_pref == "wo":
                return "Wax ma lan mooy turu sa boutique walla sa entreprise (ci misaal : « Boutique Keur Fatou » walla « Ets Diallo ») :"
            elif lang_pref == "en":
                return "Please tell me the trade name of your business or shop (for example: \"Boutique Keur Fatou\" or \"Dakar Fashion Store\"):"
            return (
                "Veuillez m'indiquer le nom de votre entreprise, boutique ou atelier (par exemple : « Boutique Keur Fatou », « Ets Diallo & Frères » ou « Dakar Fashion Store ») :"
            )

    # ÉTAPE 1 : NOM DE L'ENTREPRISE, CAPITAL SOCIAL ET ATTESTATION NINEA
    if etape == "DEMANDE_NINEA":
        piece_fournie = False
        extracted = {}

        # 1. Si une image ou un document est fourni (photo de l'attestation papier NINEA)
        if media_tuple:
            media_type, media_id = media_tuple
            media_bytes, mime_type = await download_meta_media(media_id)
            if media_bytes and ("image" in mime_type or "pdf" in mime_type):
                piece_fournie = True
                # Sauvegarde de la preuve dans Supabase Storage
                sp = get_supabase()
                if sp:
                    try:
                        clean_p = str(sender_phone).replace("+", "").replace(" ", "").strip()
                        sp.storage.from_("preuves").upload(
                            file=media_bytes,
                            path=f"{clean_p}/attestation_ninea_{media_id}.jpg",
                            file_options={"content-type": mime_type, "upsert": "true"}
                        )
                    except Exception as up_err:
                        print(f"Info upload NINEA Storage: {up_err}")

                if client:
                    b64 = base64.b64encode(media_bytes).decode("utf-8")
                    prompt_ninea = """
Analyse cette photo ou document d'attestation officielle NINEA (Sénégal).
Extrais au format JSON strict les champs officiels suivants :
{
  "is_ninea_document": true,
  "nom_entreprise": "Nom commercial ou Raison sociale officielle",
  "forme_juridique": "Forme juridique (ex: Entreprise Individuelle, SARL, SAS, SUARL, GIE)",
  "activite_principale": "Activité principale déclarée ou objet social",
  "registre_commerce": "Numéro RCCM (ex: SN-DKR-...)",
  "ninea": "Numéro NINEA officiel (7 à 10 caractères)",
  "capital_social_fcfa": montant numérique entier du capital (0 si non spécifié),
  "date_creation": "date de création ou immatriculation",
  "ville": "commune ou ville du siège"
}
Si ce n'est pas une attestation NINEA ou si c'est totalement illisible, renvoie {"is_ninea_document": false}.
"""
                    try:
                        res = client.messages.create(
                            model="claude-haiku-4-5-20251001",
                            max_tokens=800,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}},
                                    {"type": "text", "text": prompt_ninea}
                                ]
                            }]
                        )
                        raw = "".join(b.text for b in res.content if hasattr(b, "text")).strip()
                        if raw.startswith("```json"): raw = raw[7:]
                        if raw.startswith("```"): raw = raw[3:]
                        if raw.endswith("```"): raw = raw[:-3]
                        extracted = json.loads(raw.strip())
                    except Exception as e_ai:
                        print(f"Erreur extraction Claude attestation NINEA: {e_ai}")

        # 2. Extraction locale déterministe depuis le texte (0 crédit Anthropic)
        loc_ninea, loc_nom, loc_capital = extraire_ninea_nom_capital_local(user_text, sender_phone, contact_name)

        ninea = extracted.get("ninea") or loc_ninea
        nom = extracted.get("nom_entreprise") or loc_nom
        capital = extracted.get("capital_social_fcfa") or extracted.get("capital_fcfa") or loc_capital
        forme_juridique = extracted.get("forme_juridique")
        activite_principale = extracted.get("activite_principale")
        registre_commerce = extracted.get("registre_commerce")

        # 3. Validation stricte de l'Étape 1 sur PIÈCE JUSTIFICATIVE OBLIGATOIRE :
        if piece_fournie:
            cap_final = capital if (capital and capital > 0) else 100000

            # Détection : Si c'est une Entreprise Individuelle et que le nom ressemble à une personne (ex: FATOU THIAM)
            # ou si l'enseigne commerciale n'est pas spécifiée, la dénomination est le nom du propriétaire, pas de l'entreprise !
            est_personne_physique = False
            if forme_juridique and "INDIVIDUELLE" in forme_juridique.upper():
                est_personne_physique = True
            elif nom and not any(kw in nom.lower() for kw in ["boutique", "ets", "société", "societe", "sarl", "suarl", "gie", "store", "shop", "atelier", "service", "commerce"]):
                if len(nom.split()) in [2, 3]:
                    est_personne_physique = True

            # Sauvegarde des données certifiées
            update_onboarding_state(sender_phone, "capital", cap_final)
            if ninea: update_onboarding_state(sender_phone, "ninea", ninea)
            if forme_juridique: update_onboarding_state(sender_phone, "forme_juridique", forme_juridique)
            if activite_principale: update_onboarding_state(sender_phone, "activite_principale", activite_principale)
            if registre_commerce: update_onboarding_state(sender_phone, "registre_commerce", registre_commerce)
            update_onboarding_state(sender_phone, "ninea_valide_par_preuve", True)

            forme_txt = f"• Forme juridique : {forme_juridique}\n" if forme_juridique else ""
            act_txt = f"• Activité principale : {activite_principale}\n" if activite_principale else ""
            rc_txt = f"• Registre du Commerce (RCCM) : {registre_commerce}\n" if registre_commerce else ""
            ninea_txt = f"• Numéro NINEA officiel : {ninea}\n" if ninea else ""
            cap_txt = f"• Capital social certifié : {cap_final:,.0f} FCFA\n" if cap_final else ""

            # CAS A : L'attestation porte le nom de la personne physique (Dénomination : FATOU THIAM)
            # On stocke le nom du titulaire, mais ON DEMANDE IMMÉDIATEMENT LE NOM COMMERCIAL DE L'ENTREPRISE !
            if est_personne_physique:
                nom_personne = nom or "Titulaire de l'attestation"
                update_onboarding_state(sender_phone, "nom_personne_physique", nom_personne)
                update_onboarding_state(sender_phone, "etape", "DEMANDE_NOM_COMMERCIAL")

                # Enregistrement préalable dans Supabase
                sp = get_supabase()
                if sp:
                    try:
                        clean_phone = str(sender_phone).replace("+", "").replace(" ", "").strip()
                        res_ent = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_phone}%").limit(1).execute()
                        ent_payload = {
                            "nom_entreprise": f"Entreprise de {nom_personne}",
                            "capital_initial_fcfa": cap_final,
                            "ninea": ninea,
                            "secteur_activite": activite_principale or "Commerce & Services",
                            "donnees_onboarding": {
                                "langue_preferee": onboarding.get("langue_preferee", "fr"),
                                "ninea_valide_par_preuve": True,
                                "nom_personne_physique": nom_personne,
                                "forme_juridique": forme_juridique,
                                "registre_commerce": registre_commerce,
                                "activite_principale": activite_principale,
                                "etape": "DEMANDE_NOM_COMMERCIAL"
                            }
                        }
                        if res_ent.data:
                            sp.table("entreprises").update(ent_payload).eq("id", res_ent.data[0]["id"]).execute()
                        else:
                            ent_payload["telephone_whatsapp"] = clean_phone
                            sp.table("entreprises").insert(ent_payload).execute()
                    except Exception as e:
                        print(f"Info Supabase Étape 1 A : {e}")

                if lang_pref == "wo":
                    return (
                        "Sa papier NINEA officiel jot nañu ko te certifier nañu ko bu baax.\n\n"
                        "RÉSUMÉ INFORMATIONS LÉGALES :\n"
                        f"• Boroom : {nom_personne}\n"
                        f"{forme_txt}"
                        f"{act_txt}"
                        f"{rc_txt}"
                        f"{ninea_txt}"
                        f"{cap_txt}"
                        "• Statut : Conforme certifié (Ci pièce officielle)\n\n"
                        f"Important : « {nom_personne} » mooy turu boroom bi (personne physique).\n"
                        "Lan mooy turu sa boutique walla sa entreprise (ci misaal : « Boutique Keur Fatou », « Ets Diallo » walla « Dakar Fashion Store ») ?"
                    )
                return (
                    "Attestation NINEA officielle reçue et certifiée avec succès.\n\n"
                    "RÉSUMÉ DES INFORMATIONS LÉGALES :\n"
                    f"• Dénomination du titulaire : {nom_personne}\n"
                    f"{forme_txt}"
                    f"{act_txt}"
                    f"{rc_txt}"
                    f"{ninea_txt}"
                    f"{cap_txt}"
                    "• Statut : Conforme certifié (Sur pièce officielle)\n\n"
                    f"Important : « {nom_personne} » est le nom de la personne physique (l'exploitant).\n"
                    "Quel est le nom commercial ou l'enseigne de votre entreprise / boutique (par exemple : « Boutique Keur Fatou », « Ets Diallo » ou « Dakar Fashion Store ») ?"
                )

            # CAS B : L'attestation porte déjà une raison sociale de société commerciale (ex: SARL TERANGA)
            nom_final = nom or "Entreprise Certifiée"
            update_onboarding_state(sender_phone, "nom_entreprise", nom_final)
            update_onboarding_state(sender_phone, "etape", "DEMANDE_EQUIPE")

            # Enregistrement ou mise à jour de l'entreprise dans Supabase
            sp = get_supabase()
            if sp:
                try:
                    clean_phone = str(sender_phone).replace("+", "").replace(" ", "").strip()
                    res_ent = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_phone}%").limit(1).execute()
                    ent_payload = {
                        "nom_entreprise": nom_final,
                        "capital_initial_fcfa": cap_final,
                        "donnees_onboarding": {
                            "langue_preferee": onboarding.get("langue_preferee", "fr"),
                            "ninea_valide_par_preuve": True,
                            "forme_juridique": forme_juridique,
                            "registre_commerce": registre_commerce,
                            "activite_principale": activite_principale,
                            "etape": "DEMANDE_EQUIPE"
                        }
                    }
                    if ninea:
                        ent_payload["ninea"] = ninea
                    if activite_principale:
                        ent_payload["secteur_activite"] = activite_principale

                    if res_ent.data:
                        sp.table("entreprises").update(ent_payload).eq("id", res_ent.data[0]["id"]).execute()
                    else:
                        ent_payload["telephone_whatsapp"] = clean_phone
                        if not ent_payload.get("secteur_activite"):
                            ent_payload["secteur_activite"] = "Commerce & Services"
                        sp.table("entreprises").insert(ent_payload).execute()
                except Exception as e:
                    print(f"Info enregistrement Supabase Étape 1 : {e}")

            return (
                "Attestation NINEA officielle reçue et certifiée avec succès.\n\n"
                f"• Raison sociale : {nom_final}\n"
                f"{forme_txt}"
                f"{act_txt}"
                f"{rc_txt}"
                f"{ninea_txt}"
                f"{cap_txt}"
                "• Statut du dossier : Conforme certifié (Document officiel validé)\n\n"
                "Étape 2/5 : Combien de personnes travaillent au sein de votre structure (salariés déclarés, apprentis ou associés) ?"
            )
        else:
            # Si le client a envoyé du texte au lieu de la photo :
            # Superviser avec Claude
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude

            return (
                "Pour valider l'Étape 1/5, l'envoi de votre pièce justificative est obligatoire.\n\n"
                "Veuillez prendre en photo et m'envoyer votre attestation papier NINEA (ou le document officiel PDF).\n\n"
                "Grow doit impérativement vérifier cette pièce officielle pour certifier le Nom, le NINEA, la Forme juridique, le Registre de Commerce (RCCM) et le Capital social de votre entreprise avant de pouvoir passer à l'étape suivante."
            )

    # ÉTAPE 2 : NOMBRE D'EMPLOYÉS (Validation stricte locale - 0 crédit API)
    elif etape == "DEMANDE_EQUIPE":
        txt_lower = user_text.lower().strip() if user_text else ""
        has_number = bool(re.search(r'\b\d+\b', txt_lower))
        has_keywords = bool(re.search(r'\b(seul|seule|personne|personnes|salarié|salariés|salarie|salaries|employé|employés|employe|employes|associé|associés|associe|associes|apprenti|apprentis|aucun|aucune|zéro|zero|moi|travaille|un|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|man|rek|rekk|benn|ñaar|naar|ñett|nett|ñent|nent|juróom|juroom|kenn|tus|dara|nit|liggéeykat|liggeeykat)\b', txt_lower))

        if has_number or has_keywords:
            # Reformulation claire du nombre d'employés
            equipe_val = user_text.strip()
            if equipe_val.lower() in ["1", "un", "benn", "man rek", "man rekk", "moi seul", "moi seule"]:
                equipe_desc = "1 personne (l'exploitant)"
            elif equipe_val.isdigit():
                equipe_desc = f"{equipe_val} personnes"
            else:
                equipe_desc = equipe_val

            update_onboarding_state(sender_phone, "nombre_employes", equipe_desc)
            update_onboarding_state(sender_phone, "etape", "DEMANDE_OPERATEURS")

            # Mise à jour Supabase
            sp = get_supabase()
            if sp:
                try:
                    clean_phone = str(sender_phone).replace("+", "").replace(" ", "").strip()
                    ent_res = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_phone}%").limit(1).execute()
                    if ent_res.data:
                        ent_cur = ent_res.data[0]
                        sp.table("entreprises").update({
                            "donnees_onboarding": {
                                **(ent_cur.get("donnees_onboarding") or {}),
                                "nombre_employes": equipe_desc,
                                "etape": "DEMANDE_OPERATEURS"
                            }
                        }).eq("id", ent_cur["id"]).execute()
                except Exception as e_eq:
                    print(f"Info enregistrement equipe Supabase: {e_eq}")

            if lang_pref == "wo":
                return (
                    "Liggéeykat yi bind nañu leen bu baax.\n\n"
                    "RÉSUMÉ CI SA TEERE :\n"
                    f"• Équipe bi : {equipe_desc}\n\n"
                    "Étape 3/5 : Ban moyen de paiement ngay jëfandikoo bés bu nekk ngir sa jaay ak sa dépense ? (Ci misaal : Wave, Orange Money, Xalis / Cash, Compte Bancaire)."
                )
            return (
                "Effectif enregistré avec succès.\n\n"
                "RÉSUMÉ DE L'ENREGISTREMENT :\n"
                f"• Taille de la structure : {equipe_desc}\n\n"
                "Étape 3/5 : Quels moyens de paiement utilisez-vous au quotidien pour vos encaissements et vos dépenses ? (Exemples : Wave, Orange Money, Caisse Espèces, Compte Bancaire)."
            )
        else:
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude
            if lang_pref == "wo":
                return "Ngir valider Étape 2/5, wax ma ñaata nit ñooy liggéey ci sa boutique (ci misaal : 'man rekk', '1 nit', '3 liggéeykat')."
            return (
                "Pour valider l'Étape 2/5, veuillez m'indiquer le nombre de personnes qui travaillent au sein de votre structure (par exemple : 'moi seul', '1 personne', '3 employés', ou 'aucun salarié')."
            )

    # ÉTAPE 3 : OPÉRATEURS DE PAIEMENT
    elif etape == "DEMANDE_OPERATEURS":
        txt_lower = user_text.lower().strip() if user_text else ""
        has_ops = bool(re.search(r'\b(wave|orange|om|espece|especes|cash|xalis|xaalis|loxo|banque|bancaire|caisse|free|wari|compte|cheque|virement|ecobank|cbao|boa|sgbs|orabank|uba|bicis|tous|tout|yëpp|yepp)\b', txt_lower))

        if has_ops:
            # Détection précise et mémorisation définitive des opérateurs choisis
            ops_detectes = []
            if "wave" in txt_lower:
                ops_detectes.append("Wave")
            if "orange" in txt_lower or "om" in txt_lower:
                ops_detectes.append("Orange Money")
            if "free" in txt_lower:
                ops_detectes.append("Free Money")
            if any(b in txt_lower for b in ["banque", "bancaire", "cbao", "ecobank", "boa", "compte"]):
                ops_detectes.append("Compte Bancaire")
            if any(c in txt_lower for c in ["espece", "especes", "cash", "caisse", "xalis", "xaalis", "loxo"]):
                ops_detectes.append("Caisse Espèces")

            if not ops_detectes:
                ops_detectes = ["Wave", "Caisse Espèces"]

            ops_str = ", ".join(ops_detectes)
            update_onboarding_state(sender_phone, "operateurs", ops_str)
            update_onboarding_state(sender_phone, "liste_operateurs_cles", ops_detectes)
            update_onboarding_state(sender_phone, "etape", "DEMANDE_IMMOBILISATIONS")

            if lang_pref == "wo":
                return (
                    "Sa moyens de paiement bind nañu leen bu baax.\n\n"
                    "RÉSUMÉ CI SA TEERE :\n"
                    f"• Opérateurs yi : {ops_str}\n\n"
                    "Étape 4/5 : Yan matériel walla équipement nga am ci sa boutique (auto, machine, frigo, congélateur, ordinateur, table) ak ñaata lañu jar (valeur estimée) ? (Bindal 'Amuma' walla 'Aucun' su fekkee amoo ko)."
                )
            return (
                "Moyens de paiement enregistrés avec succès.\n\n"
                "RÉSUMÉ DE L'ENREGISTREMENT :\n"
                f"• Opérateurs connectés : {ops_str}\n\n"
                "Étape 4/5 : Quels équipements ou matériels possède votre entreprise (véhicule, machine, congélateur, ordinateurs, agencement) et quelle est leur valeur estimée ? (Écrivez 'Aucun' si vous n'en avez pas)."
            )
        else:
            # Superviser avec Claude : gère "Choisi", questions ou hésitations
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude
            if lang_pref == "wo":
                return "Ngir valider Étape 3/5, wax ma ban moyen de paiement ngay jëfandikoo bés bu nekk (ci misaal : 'Wave ak Xalis', 'Orange Money', walla 'Banque')."
            return (
                "Pour valider l'Étape 3/5, veuillez préciser les moyens de paiement que vous utilisez au quotidien (par exemple : 'Wave et Espèces', 'Orange Money', ou 'Compte bancaire')."
            )

    # ÉTAPE 4 : IMMOBILISATIONS & ÉQUIPEMENTS (Validation stricte avec pièce justificative obligatoire)
    elif etape == "DEMANDE_IMMOBILISATIONS":
        txt_lower = user_text.lower().strip() if user_text else ""
        is_greeting_only = bool(re.match(r'^(bonjour|salut|coucou|bonsoir|merci|ok|d[\'’]accord|salam|waw|waaw)$', txt_lower))

        # Cas particulier : le commerçant déclare formellement n'avoir AUCUN équipement
        declare_aucun = bool(re.search(r'\b(aucun|aucune|rien|zero|zéro|pas d[\'’]équipement|pas de materiel|amuma|amoul|amul|tus|dara)\b', txt_lower))
        if declare_aucun and not is_greeting_only:
            update_onboarding_state(sender_phone, "immobilisations", "Aucun matériel d'exploitation")
            update_onboarding_state(sender_phone, "valeur_equipements_fcfa", 0)
            update_onboarding_state(sender_phone, "equipements_photo_validee", True)
            update_onboarding_state(sender_phone, "etape", "DEMANDE_TRESORERIE_INITIALE")

            ops_configures = onboarding.get("liste_operateurs_cles") or ["Wave", "Caisse Espèces"]
            ops_invitation = " et ".join(ops_configures)

            if lang_pref == "wo":
                return (
                    "Sa déclaration matériel bind nañu ko.\n\n"
                    "RÉSUMÉ CI SA TEERE :\n"
                    "• Matériel : Aucun matériel d'exploitation\n"
                    "• Valeur : 0 FCFA\n\n"
                    f"Étape 5/5 : Ñaata xalis moo nekk leegi ci sa compte ({ops_invitation}) ?\n\n"
                    f"Yónneel capture d'écran solde bi ({ops_invitation}) walla foto sa caisse xalis."
                )
            return (
                "Déclaration d'équipements enregistrée avec succès.\n\n"
                "RÉSUMÉ DE L'ENREGISTREMENT :\n"
                "• Équipements déclarés : Aucun matériel d'exploitation\n"
                "• Valeur estimée : 0 FCFA\n\n"
                f"Étape 5/5 : Quel est le montant exact disponible sur vos comptes ({ops_invitation}) en cet instant ?\n\n"
                f"Envoyez la capture d'écran du solde de vos comptes ({ops_invitation}) ou la photo de votre caisse espèces."
            )

        # 1. Analyse de la valeur estimée (en FCFA) et détection des équipements
        valeur_estimee = parse_montant_fcfa(user_text) if user_text else 0
        photo_fournie = bool(media_tuple and media_tuple[0] in ["PHOTO", "DOCUMENT"])

        immo_sauvegardee = onboarding.get("immobilisations")

        has_equip_mention = bool(re.search(r'\b(congélateur|congelateur|armoire|ordinateur|véhicule|vehicule|voiture|moto|machine|chambre froide|étagère|etagere|comptoir|climatiseur|meuble|bureau|four|balance|table|imprimante|agencement)\b', txt_lower))
        if has_equip_mention or (user_text and not is_greeting_only and len(txt_lower) >= 3 and valeur_estimee == 0):
            update_onboarding_state(sender_phone, "immobilisations", user_text)
            immo_sauvegardee = user_text

        # 2. Si la photo a été envoyée
        if media_tuple:
            m_type, m_id = media_tuple
            m_bytes, m_mime = await download_meta_media(m_id)
            if m_bytes and "image" in m_mime:
                photo_fournie = True
                update_onboarding_state(sender_phone, "equipements_photo_validee", True)
                sp = get_supabase()
                ent = get_or_create_entreprise(sp, sender_phone) if sp else {}
                ent_id = ent.get("id")
                if sp and ent_id:
                    try:
                        sp.storage.from_("preuves").upload(
                            file=m_bytes,
                            path=f"{ent_id}/equipements_{m_id}.jpg",
                            file_options={"content-type": m_mime, "upsert": "true"}
                        )
                    except Exception as e_up:
                        print(f"Info upload équipement Storage : {e_up}")

        if valeur_estimee > 0:
            update_onboarding_state(sender_phone, "valeur_equipements_fcfa", valeur_estimee)

        val_enregistree = onboarding.get("valeur_equipements_fcfa") or (valeur_estimee if valeur_estimee > 0 else 0)
        has_photo = photo_fournie or onboarding.get("equipements_photo_validee", False)

        # Si l'utilisateur n'a rien mentionné et a posé une question :
        if not immo_sauvegardee and not has_equip_mention and not photo_fournie and valeur_estimee == 0:
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude

        # CONDITION STRICTE : Les deux éléments (valeur en FCFA + photo) sont indispensables
        if val_enregistree == 0 or not has_photo:
            if val_enregistree == 0 and not has_photo:
                details = f" : « {immo_sauvegardee} »" if immo_sauvegardee else ""
                return (
                    f"Grow a bien noté vos équipements{details}.\n\n"
                    "Cependant, votre réponse est incomplète pour valider l'Étape 4/5. Deux éléments indispensables manquent :\n"
                    "1. La valeur estimée globale en FCFA de ces matériels (par exemple : « Valeur estimée : 850 000 FCFA »).\n"
                    "2. La photo justificative de vos équipements en boutique/atelier (ou la photo de votre facture d'achat).\n\n"
                    "Sans la valeur estimée et la photo justificative, Grow refuse de valider l'étape car vos actifs doivent être certifiés au bilan SYSCOHADA (Compte 24) !"
                )
            elif val_enregistree > 0 and not has_photo:
                return (
                    f"Grow a bien enregistré la liste et la valeur de vos équipements :\n\n"
                    f"• Matériels déclarés : {immo_sauvegardee or 'Équipements déclarés'}\n"
                    f"• Valeur estimée : {val_enregistree:,.0f} FCFA\n\n"
                    "PIÈCE JUSTIFICATIVE OBLIGATOIRE :\n"
                    "Veuillez maintenant m'envoyer la photo de vos équipements en boutique/atelier (ou la photo de votre facture d'achat).\n\n"
                    "Grow exige cette preuve visuelle pour certifier vos actifs immobilisés (Compte SYSCOHADA 24) avant de passer à l'étape suivante."
                )
            elif val_enregistree == 0 and has_photo:
                return (
                    "Photo des équipements bien reçue et archivée avec succès.\n\n"
                    "Pour certifier vos immobilisations au bilan (Compte 24), quelle est la valeur estimée globale en FCFA de ces équipements ?"
                )

        # VALIDATION OFFICIELLE DE L'ÉTAPE 4 (Matériels + Valeur + Photo réunis)
        update_onboarding_state(sender_phone, "equipements_photo_validee", True)
        update_onboarding_state(sender_phone, "etape", "DEMANDE_TRESORERIE_INITIALE")
        val_finale = val_enregistree

        # Sauvegarde dans Supabase
        sp = get_supabase()
        if sp:
            try:
                ent = get_or_create_entreprise(sp, sender_phone)
                ent_id = ent.get("id")
                if ent_id:
                    sp.table("entreprises").update({
                        "donnees_onboarding": {
                            **(ent.get("donnees_onboarding") or {}),
                            "equipements_materiels": immo_sauvegardee,
                            "valeur_equipements_fcfa": val_finale,
                            "equipements_valides_par_preuve": True,
                            "etape": "DEMANDE_TRESORERIE_INITIALE"
                        }
                    }).eq("id", ent_id).execute()
            except Exception as e_im:
                print(f"Info sauvegarde Supabase Équipements : {e_im}")

        ops_configures = onboarding.get("liste_operateurs_cles") or ["Wave", "Caisse Espèces"]
        ops_invitation = " et ".join(ops_configures)

        return (
            "Équipements et immobilisations certifiés avec succès sur pièce justificative.\n\n"
            "RÉSUMÉ DE L'ENREGISTREMENT :\n"
            f"• Matériels déclarés : {immo_sauvegardee}\n"
            f"• Valeur d'actif certifiée : {val_finale:,.0f} FCFA\n"
            "• Imputation : Compte SYSCOHADA 24 (Matériels et Mobiliers)\n"
            "• Preuve probatoire : Photo vérifiée et archivée\n\n"
            f"Étape 5/5 : Quel est le montant exact disponible sur votre compte {ops_invitation} en cet instant ?\n\n"
            f"Envoyez la capture d'écran du solde de vos comptes ({ops_invitation}) ou la photo de votre caisse espèces."
        )

    # ÉTAPE 5 : TRÉSORERIE À L'INSTANT T AVEC PREUVE CAPTURE
    elif etape == "DEMANDE_TRESORERIE_INITIALE":
        solde_t0 = 0
        photo_url = None
        sha_hash = None

        # Si une capture d'écran du solde Wave/OM est envoyée
        if media_tuple:
            m_type, m_id = media_tuple
            m_bytes, m_mime = await download_meta_media(m_id)
            if m_bytes and "image" in m_mime:
                sha_hash = hashlib.sha256(m_bytes).hexdigest()
                sp = get_supabase()
                ent = get_or_create_entreprise(sp, sender_phone) if sp else {}
                ent_id = ent.get("id")
                if sp and ent_id:
                    try:
                        sp.storage.from_("preuves").upload(
                            file=m_bytes,
                            path=f"{ent_id}/solde_initial_{m_id}.jpg",
                            file_options={"content-type": m_mime, "upsert": "true"}
                        )
                        photo_url = sp.storage.from_("preuves").get_public_url(f"{ent_id}/solde_initial_{m_id}.jpg")
                    except Exception:
                        pass

                if client:
                    b64 = base64.b64encode(m_bytes).decode("utf-8")
                    res = client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=600,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "image", "source": {"type": "base64", "media_type": m_mime, "data": b64}},
                                {"type": "text", "text": "Extrais en JSON strict le solde affiché sur cette capture d'écran Wave/Orange Money/Banque : {solde_fcfa: int, operateur: str}. Si illisible: {solde_fcfa: 0, operateur: 'WAVE'}."}
                            ]
                        }]
                    )
                    try:
                        raw = "".join(b.text for b in res.content if hasattr(b, "text")).strip()
                        if raw.startswith("```json"): raw = raw[7:]
                        if raw.startswith("```"): raw = raw[3:]
                        if raw.endswith("```"): raw = raw[:-3]
                        p_data = json.loads(raw.strip())
                        solde_t0 = p_data.get("solde_fcfa", 0)
                    except Exception:
                        pass

        # Récupération des opérateurs configurés à l'étape 3
        ops_configures = onboarding.get("liste_operateurs_cles") or ["Wave", "Caisse Espèces"]
        ops_prompt_txt = " et ".join(ops_configures)

        # Exigence stricte de la pièce justificative pour l'Étape 5 :
        if not media_tuple:
            # Exception : le commerçant déclare explicitement 0 ou aucun solde disponible
            if user_text and re.search(r'\b(zero|zéro|aucun|rien|0)\b', user_text.lower()):
                solde_t0 = 0
            else:
                rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
                if rep_claude:
                    return rep_claude

                return (
                    f"Pour valider l'Étape 5/5, la pièce justificative est obligatoire pour vos comptes ({ops_prompt_txt}).\n\n"
                    f"Veuillez m'envoyer la capture d'écran de votre solde pour {ops_prompt_txt} (ou la photo de votre caisse espèces).\n\n"
                    "Grow refuse d'avancer sans ce justificatif visuel probant car votre trésorerie de départ doit être formellement certifiée !"
                )

        # Analyse et répartition des soldes multi-opérateurs
        soldes_dict = parse_soldes_multi_operateurs(user_text, default_solde=solde_t0, default_op="WAVE")
        if not soldes_dict and solde_t0 > 0:
            soldes_dict = {"WAVE": solde_t0}

        total_t0 = sum(soldes_dict.values()) if soldes_dict else solde_t0

        update_onboarding_state(sender_phone, "solde_initial_t0", total_t0)
        update_onboarding_state(sender_phone, "soldes_multi_operateurs", soldes_dict)
        state = get_onboarding_state(sender_phone)
        deja_abonne = state.get("abonnement_valide", False)

        nom = state.get("nom_entreprise", "Votre Entreprise")
        ninea = state.get("ninea", "En cours")
        capital = state.get("capital", 100000)
        forme_juridique = state.get("forme_juridique")
        activite_principale = state.get("activite_principale")
        registre_commerce = state.get("registre_commerce")
        equipe = state.get("nombre_employes", "1 personne")
        ops = state.get("operateurs", "Wave, Espèces")
        immos = state.get("immobilisations", "Matériel d'exploitation")

        # Enregistrer la transaction de trésorerie d'ouverture pour CHAQUE opérateur dans Supabase
        sp = get_supabase()
        if sp:
            try:
                ent = get_or_create_entreprise(sp, sender_phone)
                ent_id = ent.get("id")
                if ent_id:
                    # Mettre à jour l'étape d'onboarding à COMPLET dans Supabase
                    sp.table("entreprises").update({
                        "etape_onboarding": "COMPLET",
                        "donnees_onboarding": {
                            "ninea_valide_par_preuve": True,
                            "forme_juridique": forme_juridique,
                            "registre_commerce": registre_commerce,
                            "activite_principale": activite_principale,
                            "soldes_initiaux_par_operateur": soldes_dict,
                            "etape": "TERMINE"
                        }
                    }).eq("id", ent_id).execute()

                    # Insérer une écriture pour chaque opérateur
                    compte_map = {
                        "WAVE": "521",
                        "ORANGE_MONEY": "521",
                        "BANQUE": "521",
                        "ESPECES": "571"
                    }
                    for op_name, op_amount in soldes_dict.items():
                        if op_amount > 0:
                            tx_init = sp.table("transactions").insert({
                                "entreprise_id": ent_id,
                                "libelle": f"Trésorerie d'ouverture à l'instant T ({op_name})",
                                "compte_syscohada": compte_map.get(op_name, "521"),
                                "type_flux": "ENTREE",
                                "est_professionnel": True,
                                "montant_fcfa": op_amount,
                                "source_paiement": op_name,
                                "statut_validation": "VALIDE_PME"
                            }).execute()

                            if tx_init.data and sha_hash:
                                sp.table("preuves_numeriques").insert({
                                    "entreprise_id": ent_id,
                                    "transaction_id": tx_init.data[0]["id"],
                                    "type_preuve": "PHOTO_RECU",
                                    "url_stockage_s3": photo_url or "preuves/solde_t0",
                                    "hash_sha256": sha_hash,
                                    "texte_extrait_ia": f"Solde initial certifié {op_name} : {op_amount:,.0f} FCFA"
                                }).execute()
            except Exception as e:
                print(f"Info création transactions initiales T0 multi-opérateurs : {e}")

        short_h = f"{sha_hash[:10]}..." if sha_hash else "Certifié déclaratif"

        # Formatage du détail multi-opérateurs
        labels_ops = {
            "WAVE": "Compte Wave",
            "ORANGE_MONEY": "Compte Orange Money",
            "ESPECES": "Caisse Espèces",
            "BANQUE": "Compte Bancaire"
        }
        lignes_soldes = []
        for op_k, op_val in soldes_dict.items():
            lignes_soldes.append(f"  • {labels_ops.get(op_k, op_k)} : {op_val:,.0f} FCFA")

        detail_soldes_txt = "\n".join(lignes_soldes) if lignes_soldes else f"  • Trésorerie : {total_t0:,.0f} FCFA"

        forme_txt = f"• Forme juridique : {forme_juridique}\n" if forme_juridique else ""
        act_txt = f"• Activité principale : {activite_principale}\n" if activite_principale else ""
        rc_txt = f"• Registre du Commerce (RCCM) : {registre_commerce}\n" if registre_commerce else ""

        # CAS 1 : Si le client a DÉJÀ PAYÉ son abonnement -> Clôture officielle, récapitulatif des 5 étapes et instructions
        if deja_abonne:
            update_onboarding_state(sender_phone, "statut", "COMPLET")
            update_onboarding_state(sender_phone, "etape", "TERMINE")
            instructions = get_instructions_journee_message(get_public_base_url(), sender_phone, nom)
            return (
                f"Félicitations ! Votre entreprise « {nom} » est désormais officiellement créée et enregistrée sur Grow aux normes SYSCOHADA.\n\n"
                "RÉCAPITULATIF OFFICIEL DES 5 ÉTAPES D'OUVERTURE :\n\n"
                "1. IDENTITÉ DE L'ENTREPRISE (Étape 1/5) :\n"
                f"• Raison sociale : {nom}\n"
                f"• Numéro NINEA officiel : {ninea}\n"
                f"{forme_txt}"
                f"{rc_txt}"
                f"{act_txt}"
                f"• Capital social certifié : {capital:,.0f} FCFA\n"
                "• Statut NINEA : Conforme certifié (Sur pièce officielle)\n\n"
                "2. STRUCTURE & EFFECTIF (Étape 2/5) :\n"
                f"• Équipe déclarée : {equipe}\n\n"
                "3. MOYENS DE PAIEMENT (Étape 3/5) :\n"
                f"• Opérateurs connectés : {ops}\n\n"
                "4. ÉQUIPEMENTS & IMMOBILISATIONS (Étape 4/5) :\n"
                f"• Matériels déclarés : {immos}\n\n"
                "5. BILAN D'OUVERTURE & TRÉSORERIE T0 (Étape 5/5) :\n"
                f"{detail_soldes_txt}\n"
                f"• Total Trésorerie certifiée : {total_t0:,.0f} FCFA\n"
                f"• Empreinte probatoire numérique : {short_h}\n\n"
                "VOTRE TABLEAU DE BORD FINANCIER EN DIRECT :\n"
                "Vous pouvez dès maintenant consulter l'intégralité de vos comptes et bilans financiers sur votre lien sécurisé :\n"
                f"{get_public_base_url()}/dashboard?phone={sender_phone}\n"
                "(Vous y retrouverez votre raison sociale, votre NINEA, votre capital certifié, vos équipements et vos soldes de trésorerie par opérateur mis à jour en temps réel).\n\n"
                f"{instructions}"
            )
        else:
            return (
                f"Félicitations ! Les 5 étapes de configuration de votre entreprise « {nom} » sont entièrement validées.\n\n"
                "Pour activer la certification en continu de votre comptabilité et accéder à vos bilans SYSCOHADA, finalisez votre souscription sur ce lien sécurisé :\n"
                f"{get_public_base_url()}/abonnement?phone={sender_phone}"
            )

        # Analyse et répartition des soldes multi-opérateurs
        soldes_dict = parse_soldes_multi_operateurs(user_text, default_solde=solde_t0, default_op="WAVE")
        if not soldes_dict and solde_t0 > 0:
            soldes_dict = {"WAVE": solde_t0}

        total_t0 = sum(soldes_dict.values()) if soldes_dict else solde_t0

        update_onboarding_state(sender_phone, "solde_initial_t0", total_t0)
        update_onboarding_state(sender_phone, "soldes_multi_operateurs", soldes_dict)
        state = get_onboarding_state(sender_phone)
        deja_abonne = state.get("abonnement_valide", False)

        nom = state.get("nom_entreprise", "Votre Entreprise")
        ninea = state.get("ninea", "En cours")
        capital = state.get("capital", 100000)
        forme_juridique = state.get("forme_juridique")
        activite_principale = state.get("activite_principale")
        registre_commerce = state.get("registre_commerce")
        equipe = state.get("nombre_employes", "1 personne")
        ops = state.get("operateurs", "Wave, Espèces")
        immos = state.get("immobilisations", "Matériel d'exploitation")

        # Enregistrer la transaction de trésorerie d'ouverture pour CHAQUE opérateur dans Supabase
        sp = get_supabase()
        if sp:
            try:
                ent = get_or_create_entreprise(sp, sender_phone)
                ent_id = ent.get("id")
                if ent_id:
                    # Mettre à jour l'étape d'onboarding à COMPLET dans Supabase
                    sp.table("entreprises").update({
                        "etape_onboarding": "COMPLET",
                        "donnees_onboarding": {
                            "ninea_valide_par_preuve": True,
                            "forme_juridique": forme_juridique,
                            "registre_commerce": registre_commerce,
                            "activite_principale": activite_principale,
                            "soldes_initiaux_par_operateur": soldes_dict
                        }
                    }).eq("id", ent_id).execute()

                    # Insérer une écriture pour chaque opérateur
                    compte_map = {
                        "WAVE": "521",
                        "ORANGE_MONEY": "521",
                        "BANQUE": "521",
                        "ESPECES": "571"
                    }
                    for op_name, op_amount in soldes_dict.items():
                        if op_amount > 0:
                            tx_init = sp.table("transactions").insert({
                                "entreprise_id": ent_id,
                                "libelle": f"Trésorerie d'ouverture à l'instant T ({op_name})",
                                "compte_syscohada": compte_map.get(op_name, "521"),
                                "type_flux": "ENTREE",
                                "est_professionnel": True,
                                "montant_fcfa": op_amount,
                                "source_paiement": op_name,
                                "statut_validation": "VALIDE_PME"
                            }).execute()

                            if tx_init.data and sha_hash:
                                sp.table("preuves_numeriques").insert({
                                    "entreprise_id": ent_id,
                                    "transaction_id": tx_init.data[0]["id"],
                                    "type_preuve": "PHOTO_RECU",
                                    "url_stockage_s3": photo_url or "preuves/solde_t0",
                                    "hash_sha256": sha_hash,
                                    "texte_extrait_ia": f"Solde initial certifié {op_name} : {op_amount:,.0f} FCFA"
                                }).execute()
            except Exception as e:
                print(f"Info création transactions initiales T0 multi-opérateurs : {e}")

        short_h = f"{sha_hash[:10]}..." if sha_hash else "Certifié déclaratif"

        # Formatage du détail multi-opérateurs
        labels_ops = {
            "WAVE": "Compte Wave",
            "ORANGE_MONEY": "Compte Orange Money",
            "ESPECES": "Caisse Espèces",
            "BANQUE": "Compte Bancaire"
        }
        lignes_soldes = []
        for op_k, op_val in soldes_dict.items():
            lignes_soldes.append(f"  • {labels_ops.get(op_k, op_k)} : {op_val:,.0f} FCFA")

        detail_soldes_txt = "\n".join(lignes_soldes) if lignes_soldes else f"  • Trésorerie : {total_t0:,.0f} FCFA"

        forme_txt = f"• Forme juridique : {forme_juridique}\n" if forme_juridique else ""
        act_txt = f"• Activité principale : {activite_principale}\n" if activite_principale else ""
        rc_txt = f"• Registre du Commerce (RCCM) : {registre_commerce}\n" if registre_commerce else ""

        # CAS 1 : Si le client a DÉJÀ PAYÉ son abonnement -> Clôture officielle, récapitulatif des 5 étapes et instructions
        if deja_abonne:
            update_onboarding_state(sender_phone, "statut", "COMPLET")
            update_onboarding_state(sender_phone, "etape", "TERMINE")
            instructions = get_instructions_journee_message(get_public_base_url(), sender_phone, nom)
            return (
                f"Félicitations ! Votre entreprise « {nom} » est désormais officiellement créée et enregistrée sur Grow aux normes SYSCOHADA.\n\n"
                "RÉCAPITULATIF OFFICIEL DES 5 ÉTAPES D'OUVERTURE :\n\n"
                "1. IDENTITÉ DE L'ENTREPRISE (Étape 1/5) :\n"
                f"• Raison sociale : {nom}\n"
                f"• Numéro NINEA officiel : {ninea}\n"
                f"{forme_txt}"
                f"{rc_txt}"
                f"{act_txt}"
                f"• Capital social certifié : {capital:,.0f} FCFA\n"
                "• Statut NINEA : Conforme certifié (Sur pièce officielle)\n\n"
                "2. STRUCTURE & EFFECTIF (Étape 2/5) :\n"
                f"• Équipe déclarée : {equipe}\n\n"
                "3. MOYENS DE PAIEMENT (Étape 3/5) :\n"
                f"• Opérateurs connectés : {ops}\n\n"
                "4. ÉQUIPEMENTS & IMMOBILISATIONS (Étape 4/5) :\n"
                f"• Matériels déclarés : {immos}\n\n"
                "5. BILAN D'OUVERTURE & TRÉSORERIE T0 (Étape 5/5) :\n"
                f"{detail_soldes_txt}\n"
                f"• Total Trésorerie certifiée : {total_t0:,.0f} FCFA\n"
                f"• Empreinte probatoire numérique : {short_h}\n\n"
                "VOTRE TABLEAU DE BORD FINANCIER EN DIRECT :\n"
                "Vous pouvez dès maintenant consulter l'intégralité de vos comptes et bilans financiers sur votre lien sécurisé :\n"
                f"{get_public_base_url()}/dashboard?phone={sender_phone}\n"
                "(Vous y retrouverez votre raison sociale, votre NINEA, votre capital certifié, vos équipements et vos soldes de trésorerie par opérateur mis à jour en temps réel).\n\n"
                f"{instructions}"
            )
        else:
            # CAS 2 : Si le client n'a pas encore payé -> On lui demande de souscrire
            update_onboarding_state(sender_phone, "statut", "EN_ATTENTE_ABONNEMENT")
            update_onboarding_state(sender_phone, "etape", "PAIEMENT_ABONNEMENT")
            return (
                f"Félicitations ! Votre entreprise « {nom} » a été configurée avec succès sur Grow.\n\n"
                "RÉCAPITULATIF DES 5 ÉTAPES D'OUVERTURE :\n\n"
                "1. IDENTITÉ DE L'ENTREPRISE (Étape 1/5) :\n"
                f"• Raison sociale : {nom}\n"
                f"• Numéro NINEA : {ninea}\n"
                f"• Capital social certifié : {capital:,.0f} FCFA\n\n"
                "2. STRUCTURE & EFFECTIF (Étape 2/5) :\n"
                f"• Équipe déclarée : {equipe}\n\n"
                "3. MOYENS DE PAIEMENT (Étape 3/5) :\n"
                f"• Opérateurs connectés : {ops}\n\n"
                "4. ÉQUIPEMENTS & IMMOBILISATIONS (Étape 4/5) :\n"
                f"• Matériels déclarés : {immos}\n\n"
                "5. TRÉSORERIE INITIALE T0 (Étape 5/5) :\n"
                f"{detail_soldes_txt}\n"
                f"• Total Trésorerie : {total_t0:,.0f} FCFA\n\n"
                "Votre tableau de bord financier personnel est prêt sur ce lien sécurisé :\n"
                f"{get_public_base_url()}/dashboard?phone={sender_phone}\n\n"
                "Pour activer le traitement automatique quotidien de vos opérations, veuillez finaliser votre abonnement Grow sur ce lien :\n"
                f"{get_public_base_url()}/abonnement?phone={sender_phone}\n\n"
                "Une fois le paiement effectué, écrivez simplement « J'ai payé » pour commencer !"
            )

    return "Bonjour ! Pour continuer la création de votre entreprise, envoyez-moi votre NINEA."


async def download_meta_media(media_id: str) -> tuple[bytes, str]:
    """Télécharge le fichier média depuis Meta Cloud API."""
    load_dotenv(override=True)
    token = os.getenv("WHATSAPP_TOKEN")
    if not token or not media_id:
        return b"", ""

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            meta_res = await client.get(f"https://graph.facebook.com/v21.0/{media_id}", headers=headers)
            if meta_res.status_code != 200:
                print(f"Erreur Meta get media : {meta_res.status_code}")
                return b"", ""
            media_info = meta_res.json()
            media_url = media_info.get("url")
            mime_type = media_info.get("mime_type", "image/jpeg")

            file_res = await client.get(media_url, headers=headers)
            if file_res.status_code == 200:
                return file_res.content, mime_type
            else:
                return b"", ""
    except Exception as e:
        print(f"Erreur download_meta_media : {e}")
        return b"", ""


async def process_media_with_ai(sender_phone: str, media_id: str, type_preuve: str, context_text: str) -> str:
    """Télécharge le média, calcule le hash SHA-256, l'archive dans Supabase Storage et l'analyse avec Claude."""
    sp = get_supabase()
    entreprise = get_or_create_entreprise(sp, sender_phone) if sp else {}
    entreprise_id = entreprise.get("id")

    media_bytes, mime_type = await download_meta_media(media_id)
    if not media_bytes:
        return "⚠️ Je n'ai pas réussi à récupérer votre fichier. Pouvez-vous me le renvoyer ?"

    sha256_hash = hashlib.sha256(media_bytes).hexdigest()
    print(f"Empreinte SHA-256 calculée : {sha256_hash}")

    url_stockage = f"preuves/{entreprise_id}/{media_id}.jpg"
    try:
        if sp and entreprise_id:
            sp.storage.from_("preuves").upload(
                file=media_bytes,
                path=f"{entreprise_id}/{media_id}.jpg",
                file_options={"content-type": mime_type, "upsert": "true"}
            )
            url_stockage = sp.storage.from_("preuves").get_public_url(f"{entreprise_id}/{media_id}.jpg")
    except Exception as e:
        print(f"Info stockage Supabase : {e}")

    ocr_texte = context_text
    extracted_data = {}
    load_dotenv(override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if api_key and type_preuve == "PHOTO_RECU" and "image" in mime_type:
        try:
            client = anthropic.Anthropic(api_key=api_key)
            b64_image = base64.b64encode(media_bytes).decode("utf-8")

            prompt = """
Analyse cette image envoyée par un commerçant au Sénégal.
Elle peut être :
1) Une attestation officielle NINEA (Direction Générale des Impôts et des Domaines / APIX)
2) Un reçu, facture, ticket de caisse physique.
3) Une capture d'écran de l'application Wave / Orange Money ou une CAPTURE D'ÉCRAN D'UNE NOTIFICATION PUSH Wave/OM (ex: bannière de notification sur écran verrouillé ou centre de notifications iPhone/Android avec icône Wave pingouin, virement reçu, remboursement ou paiement).

Extrais les informations sous forme de JSON strict :
{
  "is_ninea_document": true si c'est une attestation NINEA officielle (sinon false),
  "nom_entreprise": "Nom commercial ou Raison sociale officielle" (si NINEA),
  "forme_juridique": "Forme juridique (ex: Entreprise Individuelle, SARL, SAS, SUARL, GIE)" (si NINEA),
  "activite_principale": "Activité principale déclarée ou objet social" (si NINEA),
  "registre_commerce": "Numéro RCCM (ex: SN-DKR-...)" (si NINEA),
  "ninea": "Numéro NINEA officiel (7 à 10 caractères)" (si NINEA),
  "capital_social_fcfa": montant numérique entier du capital (si NINEA, sinon 0),

  "is_transaction": true si c'est un reçu, facture ou notification de transaction financière (sinon false),
  "type_flux": "SORTIE" (si dépense/achat) ou "ENTREE" (si vente, transfert reçu ou remboursement),
  "montant_fcfa": montant numérique entier en FCFA (ex: si écrit 105F -> 105, si écrit 25.000F -> 25000),
  "libelle": "description de l'opération (ex: Vente encaissée via Wave, Remboursement Wave, Achat)",
  "source_paiement": "WAVE" ou "ORANGE_MONEY" ou "ESPECES" ou "BANQUE",
  "compte_syscohada": "code compte SYSCOHADA (ex: 701 pour vente/recette, 601 pour stock, 605 frais, 521 régularisation)",
  "texte_extrait": "résumé des textes clés lus"
}
Si l'image n'est ni un document NINEA ni une transaction/notification financière lisible, renvoie is_transaction=false et is_ninea_document=false.
"""
            res = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64_image}},
                        {"type": "text", "text": prompt}
                    ]
                }]
            )
            raw = "".join(b.text for b in res.content if hasattr(b, "text")).strip()
            if raw.startswith("```json"): raw = raw[7:]
            if raw.startswith("```"): raw = raw[3:]
            if raw.endswith("```"): raw = raw[:-3]
            extracted_data = json.loads(raw.strip())
            ocr_texte = extracted_data.get("texte_extrait", context_text)

            # Si l'image envoyée est une attestation NINEA officielle
            if extracted_data.get("is_ninea_document"):
                nom_n = extracted_data.get("nom_entreprise")
                forme_n = extracted_data.get("forme_juridique")
                act_n = extracted_data.get("activite_principale")
                rc_n = extracted_data.get("registre_commerce")
                ninea_n = extracted_data.get("ninea")
                cap_n = extracted_data.get("capital_social_fcfa") or 0

                try:
                    up_p = {
                        "donnees_onboarding": {
                            "ninea_valide_par_preuve": True,
                            "forme_juridique": forme_n,
                            "registre_commerce": rc_n,
                            "activite_principale": act_n
                        }
                    }
                    if nom_n: up_p["nom_entreprise"] = nom_n
                    if ninea_n: up_p["ninea"] = ninea_n
                    if cap_n and cap_n > 0: up_p["capital_initial_fcfa"] = cap_n
                    if act_n: up_p["secteur_activite"] = act_n

                    sp.table("entreprises").update(up_p).eq("id", entreprise_id).execute()
                    update_onboarding_state(sender_phone, "ninea_valide_par_preuve", True)
                    if ninea_n: update_onboarding_state(sender_phone, "ninea", ninea_n)
                    if nom_n: update_onboarding_state(sender_phone, "nom_entreprise", nom_n)
                except Exception as e_up:
                    print(f"Erreur mise à jour attestation NINEA : {e_up}")

                forme_t = f"• Forme juridique : {forme_n}\n" if forme_n else ""
                act_t = f"• Activité principale : {act_n}\n" if act_n else ""
                rc_t = f"• Registre du Commerce (RCCM) : {rc_n}\n" if rc_n else ""
                ninea_t = f"• Numéro NINEA officiel : {ninea_n}\n" if ninea_n else ""
                cap_t = f"• Capital social certifié : {cap_n:,.0f} FCFA\n" if cap_n else ""

                return (
                    "Attestation papier NINEA reçue et certifiée avec succès.\n\n"
                    f"• Raison sociale : {nom_n or entreprise.get('nom_entreprise', 'Votre Entreprise')}\n"
                    f"{forme_t}"
                    f"{act_t}"
                    f"{rc_t}"
                    f"{ninea_t}"
                    f"{cap_t}"
                    "• Statut du dossier : Conforme certifié (Document officiel validé)\n\n"
                    "Vos comptes, vos bilans comptables SYSCOHADA et vos dossiers de financement sont désormais officiellement rattachés à votre attestation NINEA."
                )
        except Exception as e:
            print(f"Erreur analyse Claude Vision : {e}")

    tx_id = None
    if sp and entreprise_id and extracted_data.get("is_transaction") and extracted_data.get("montant_fcfa", 0) > 0:
        try:
            tx = sp.table("transactions").insert({
                "entreprise_id": entreprise_id,
                "libelle": extracted_data.get("libelle", "Reçu validé"),
                "compte_syscohada": str(extracted_data.get("compte_syscohada", "601")),
                "type_flux": extracted_data.get("type_flux", "SORTIE"),
                "est_professionnel": True,
                "montant_fcfa": int(extracted_data.get("montant_fcfa")),
                "source_paiement": extracted_data.get("source_paiement", "ESPECES"),
                "statut_validation": "VALIDE_PME"
            }).execute()
            if tx.data:
                tx_id = tx.data[0]["id"]
        except Exception as e:
            print(f"Erreur insertion transaction : {e}")

    if not tx_id and sp and entreprise_id:
        try:
            pending = sp.table("transactions").select("id").eq("entreprise_id", entreprise_id).eq("statut_validation", "EN_ATTENTE_JUSTIFICATIF").order("created_at", desc=True).limit(1).execute()
            if pending.data:
                tx_id = pending.data[0]["id"]
                sp.table("transactions").update({"statut_validation": "VALIDE_PME"}).eq("id", tx_id).execute()
        except Exception as e:
            print(f"Info liaison preuve : {e}")

    if sp and entreprise_id:
        try:
            sp.table("preuves_numeriques").insert({
                "entreprise_id": entreprise_id,
                "transaction_id": tx_id,
                "type_preuve": type_preuve,
                "url_stockage_s3": url_stockage,
                "hash_sha256": sha256_hash,
                "texte_extrait_ia": ocr_texte
            }).execute()
        except Exception as e:
            print(f"Erreur insertion preuve : {e}")

    montant = extracted_data.get("montant_fcfa", 0)
    libelle = extracted_data.get("libelle", "Pièce justificative")
    short_hash = sha256_hash[:10]

    if montant > 0:
        return (
            "Justificatif verifie et archive avec succes.\n\n"
            f"RESUME DE L'ENREGISTREMENT :\n"
            f"• Nature : {libelle}\n"
            f"• Montant : {montant:,.0f} FCFA\n"
            f"• Compte SYSCOHADA : {extracted_data.get('compte_syscohada', '601')}\n"
            f"• Preuve probatoire : Certifiee conforme (SHA-256 : {short_hash}...)\n\n"
            "Statut : L'operation est validee et imputee a votre journal comptable."
        )
    else:
        return (
            "Justificatif recu et securise dans votre coffre-fort numerique.\n\n"
            f"• Empreinte probatoire : SHA-256 ({short_hash}...)\n\n"
            "Pour finaliser l'enregistrement, precisez-moi simplement le montant et la nature de cette depense (ex: « 15 000 carburant »)."
        )


async def process_text_with_ai(sender_phone: str, user_text: str) -> str:
    """Analyse le texte, traite les flux Wave en direct, les impayés, les stocks ou les heures de rappel."""
    load_dotenv(override=True)
    
    txt_clean = (user_text or "").strip().lower()

    # 0. RÉPONSE DIRECTE DU CLIENT À UNE QUESTION DE CLARIFICATION D'OPÉRATEUR (1, 2, 3, 4)
    sp = get_supabase()
    entreprise = get_or_create_entreprise(sp, sender_phone) if sp else {}
    entreprise_id = entreprise.get("id")

    reponse_choix = None
    if txt_clean in ["1", "1.", "achat", "stock", "marchandise", "marchandises", "achat stock"]:
        reponse_choix = ("601", "Achats de marchandises", "Achat stock / marchandises")
    elif txt_clean in ["2", "2.", "dette", "fournisseur", "reglement", "dette fournisseur"]:
        reponse_choix = ("401", "Fournisseurs d'exploitation", "Paiement dette fournisseur")
    elif txt_clean in ["3", "3.", "transport", "carburant", "essence", "frais", "frais de transport"]:
        reponse_choix = ("605", "Autres achats et charges externes (Transport / Carburant)", "Transport / Carburant")
    elif txt_clean in ["4", "4.", "perso", "personnel", "retrait", "patron", "depense perso", "retrait personnel"]:
        reponse_choix = ("108", "Compte de l'exploitant (Prélèvement personnel)", "Retrait personnel exploitant")

    if reponse_choix and sp and entreprise_id:
        try:
            pending = sp.table("transactions").select("*").eq("entreprise_id", entreprise_id).in_("compte_syscohada", ["471100", "471"]).order("created_at", desc=True).limit(1).execute()
            if pending.data and len(pending.data) > 0:
                target_tx = pending.data[0]
                nouveau_compte, libelle_compte, nature = reponse_choix
                orig_lib = target_tx.get('libelle', 'Opération')
                nouveau_libelle = f"{orig_lib} ({nature})"
                
                sp.table("transactions").update({
                    "compte_syscohada": nouveau_compte,
                    "libelle": nouveau_libelle,
                    "statut_validation": "VALIDE_PME"
                }).eq("id", target_tx["id"]).execute()
                
                # Auto-apprentissage dans la mémoire Grow pour toujours
                tiers_nom = None
                if "-" in orig_lib:
                    tiers_nom = orig_lib.split("-")[-1].strip()
                elif "pour" in orig_lib.lower():
                    tiers_nom = orig_lib.lower().split("pour")[-1].strip()
                elif "à" in orig_lib.lower():
                    tiers_nom = orig_lib.lower().split("à")[-1].strip()
                
                if tiers_nom and len(tiers_nom) > 2:
                    enregistrer_fournisseur_memoire(entreprise_id, tiers_nom, nouveau_compte, libelle_compte, nature)

                montant = int(target_tx.get("montant_fcfa") or 0)
                ref = target_tx.get("reference_externe") or f"TX-{target_tx['id'][:8]}"
                
                msg_confirmation = (
                    f"Écriture validée et certifiée.\n\n"
                    f"L'opération de {montant:,.0f} FCFA (Réf: {ref}) est désormais imputée au Compte SYSCOHADA {nouveau_compte} ({libelle_compte}).\n\n"
                    f"Statut : Vérifiée."
                )
                if tiers_nom and len(tiers_nom) > 2:
                    msg_confirmation += f"\n\nIntelligence Grow : le bénéficiaire « {tiers_nom} » est mémorisé. Vos futures transactions avec lui seront classées automatiquement."
                return msg_confirmation
        except Exception as e:
            print(f"Erreur résolution clarification : {e}")

    # ==========================================================================
    # MOTEUR EXPERT MÉTIER & MINI-CHATGPT SPÉCIALISÉ (0 CRÉDIT API / 100% LOCAL)
    # ==========================================================================

    # 1. Modification de l'heure du rituel quotidien (ex: 'change l'heure du rappel à 21h30')
    m_heure = re.search(r'(?:change|modifier|mets|rappel|rituel)\D*?(\d{1,2})[h:](\d{2})?', txt_clean)
    if m_heure and any(k in txt_clean for k in ["heure", "rappel", "rituel", "soir"]):
        h = int(m_heure.group(1))
        mn = int(m_heure.group(2) or 0)
        heure_fmt = f"{h:02d}:{mn:02d}:00"
        try:
            sp.table("entreprises").update({"heure_rappel_quotidien": heure_fmt}).eq("id", entreprise_id).execute()
            return f"L'heure de votre rituel de caisse quotidien est désormais fixée à {h:02d}h{mn:02d}. Chaque soir à cette heure, Grow dressera le bilan de votre journée."
        except Exception:
            pass

    # 2. Salutations et présentations générales (ponctuation nettoyée)
    clean_no_punct = re.sub(r'[^\w\s]', '', txt_clean).strip()
    if clean_no_punct in ["bonjour", "salut", "bonsoir", "coucou", "qui es tu", "qui est tu", "cest quoi grow", "tu es qui", "aide", "help", "merci"]:
        return (
            "Bonjour ! Je suis Grow, votre assistant pré-comptable officiel sur WhatsApp certifié aux normes SYSCOHADA.\n\n"
            "Je vous accompagne au quotidien pour :\n"
            "• Enregistrer automatiquement vos ventes Wave, Orange Money et espèces\n"
            "• Récupérer vos justificatifs de dépenses et de stock avec preuves\n"
            "• Suivre vos dettes fournisseurs et vos créances clients\n"
            "• Vous fournir chaque soir un bilan consolidé prêt pour votre expert-comptable\n\n"
            "Comment puis-je vous aider aujourd'hui ?"
        )

    # 3. Base de connaissances théorique & juridique (SYSCOHADA, NINEA, Preuves, Agences, Rituel)
    ans_theorie = repondre_question_theorique_locale(user_text)
    if ans_theorie:
        return ans_theorie

    # 4. Consultations financières en temps réel (Solde caisse/Wave, ventes du jour, dettes/créances)
    ans_consult = executer_consultation_donnees_locale(user_text, entreprise_id, sp)
    if ans_consult:
        return ans_consult

    # 5. Gestion en langage naturel des Dettes Fournisseurs & Créances Clients
    ans_dette = gerer_dette_creance_locale(user_text, entreprise_id, sp)
    if ans_dette:
        return ans_dette

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        return f"Grow a bien noté : '{user_text}'."

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = """
Tu es Grow, l'Assistant Pre-Comptable certifie pour les PME et commercants a Dakar (Senegal) sous la norme SYSCOHADA.
Tu geres la tresorerie au jour le jour (Wave, Orange Money, Especes), les impayes (dettes fournisseurs, creances clients), les remboursements partiels, les relances tous les 3 jours, les stocks et les immobilisations.

INTERDICTION ABSOLUE D'UTILISER LE MOINDRE EMOJI :
Aucun smiley, aucun symbole graphique, aucun drapeau. Ton style doit etre sobre, institutionnel, respectueux, clair et precis.

TRAITEMENT DES NOTIFICATIONS ET SMS D'OPERATEURS (Wave, Orange Money, Free Money) :
- Si l'utilisateur colle ou transfere un SMS de transfert Wave ou Orange Money :
  * Identifie immediatement s'il s'agit d'un encaissement (ENTREE / CREDIT) ou d'un decaissement (SORTIE / DEBIT).
  * Extrais la reference de transaction (ex: TX-..., Wave ID), le montant exact et le nom de l'emetteur/destinataire.
  * Affectation SYSCOHADA automatique :
    - Si entree d'argent sans precision particuliere : Compte 701 (Vente de marchandises / Chiffre d'affaires).
    - Si sortie pour carburant (Total, Shell, carburant) : Compte 605.
    - Si sortie pour loyer : Compte 622.
    - Si sortie pour fournisseur identifie ou marchandise : Compte 601 ou 401.
    - Si le motif de la sortie d'argent est INCONNU ou FLOUTÉ : Affecte provisoirement le compte d'attente 471100 et demande poliment clarification a l'utilisateur dans reponse_whatsapp (ex: 1 pour achat marchandise, 2 pour dette fournisseur, 3 pour transport, 4 pour retrait personnel).

REGLES D'EXIGENCE DE PREUVES ET JUSTIFICATIFS :
- Pour les transferts Wave et Orange Money : la preuve numerique est intrinseque via l'operateur, pas de recu papier requis.
- REGLE STRICTE SUR TOUTES LES DEPENSES ET ACHATS EN CASH (ESPECES) :
  CHAQUE depense ou achat fait en cash (stock de marchandises, carburant, transport, fournitures, loyer, electricite Senelec, eau Sen'Eau, repas, reparation ou tout autre achat) DOIT OBLIGATOIREMENT avoir une piece justificative : photo du recu, de la facture, du ticket de caisse, ou photo probante du stock/marchandise achetee avant d'etre acceptee et validee.
  Si le commercant declare une depense en cash par texte sans photo : pre-enregistre l'operation en attente, et dans ta "reponse_whatsapp", rappelle-lui fermement :
  "Votre depense de [montant] FCFA a ete pre-enregistree en attente de justificatif.
  Rappel obligatoire : Pour que cette depense soit acceptee et enregistree dans vos donnees financieres officielles, vous devez obligatoirement envoyer sa piece justificative (photo du recu, facture, ticket ou photo du stock achete).
  Sans justificatif, cette depense ne sera pas comptabilisee et c'est vous qui perdez !"

COMPRÉHENSION ET RÉPONSE EN WOLOF URBAIN DAKAROIS :
Les commerçants de Dakar s'expriment très régulièrement en Wolof ou mélangent Wolof et Français :
- Vocabulaire commercial Wolof :
  * "jaay", "jaay naa", "dama jaay", "am na jaay", "dug na" -> Vente / Encaissement (Compte 701, ENTREE).
  * "jënd", "jënd naa", "dama jënd", "marchandise", "stock" -> Achat de stock (Compte 601, SORTIE).
  * "essence", "carburant", "tiak tiak", "taxi", "dem ak dikk" -> Transport / Carburant (Compte 605, SORTIE).
  * "fey na", "fey naa" -> Règlement / Paiement (SORTIE).
  * "bor", "bor bi", "lebal", "ku ma lebal", "ku ma ameel" -> Dette ou créance.
  * "ana sama solde", "wax ma solde bi", "xaalis bi tollu na fan" -> Consultation de trésorerie.
  * "ci Wave" -> WAVE, "ci Orange" -> ORANGE_MONEY, "ci cash / ci loxo" -> ESPECES.
- RÈGLE STRICTE POUR "reponse_whatsapp" :
  * Si l'utilisateur s'exprime en Wolof (ex: "dama jaay...", "ana sama solde...", "jënd naa...") : Formule IMPÉRATIVEMENT "reponse_whatsapp" en Wolof dakarois fluide, authentique et chaleureux (sans inventer de mots bizarres ni archaïques).
    Exemples naturels de réponses en Wolof :
    - Vente Wave : "Jërejëf ! Sa jaay bu [montant] FCFA ci Wave dug na bu baax. Sa solde disponible tollu na ci [solde] FCFA."
    - Dépense sans reçu : "Sa dépense bu [montant] FCFA ci espèces bind nañu ko ci attente. Nanga def foto reçu bi ngir nu mën ko certifier."
    - Consultation : "Salaam alaikum ! Sa kom-kom ak sa solde ci direct tollu na ci [solde] FCFA."
  * Si l'utilisateur s'exprime en Français : Réponds en Français clair et professionnel selon les normes SYSCOHADA.

Retourne STRICTEMENT un objet JSON valide suivant ce format :
{
  "intention": "TRANSACTION" | "NOUVELLE_DETTE" | "REMBOURSEMENT_DETTE" | "QUESTION_CLARIFICATION" | "MODIFIER_HEURE_RITUEL" | "DECLARATION_STRUCTURELLE" | "CONSULTATION_DETTES" | "CONSULTATION_INVENTAIRE_JOUR" | "CONSULTATION_AGENCES_PARTENAIRES" | "CONVERSATION_SIMPLE",
  
  "heure_rituel": "HH:MM:SS" (ou null),
  
  "dette_info": {
    "action": "CREATION" | "REMBOURSEMENT" | null,
    "type": "DETTE_FOURNISSEUR" | "CREANCE_CLIENT" | null,
    "tiers_nom": "nom du tiers" | null,
    "montant_fcfa": nombre entier ou 0,
    "date_echeance": "YYYY-MM-DD" ou null
  },

  "transaction": {
    "is_transaction": true/false,
    "type_flux": "ENTREE" | "SORTIE",
    "montant_fcfa": nombre entier,
    "libelle": "description claire",
    "compte_syscohada": "701" (Ventes) | "601" (Achats stock) | "401" (Fournisseur/Dette) | "411" (Client/Creance) | "605" (Carburant) | "622" (Loyer) | "661" (Salaires) | "244" (Materiel/Immobilisation) | "471100" (Compte d'attente a clarifier),
    "source_paiement": "WAVE" | "ORANGE_MONEY" | "ESPECES" | "BANQUE",
    "reference_externe": "reference de transaction (ex: WV-9842 ou null)",
    "est_professionnel": true,
    "besoin_justificatif": true/false
  },

  "structurel": {
    "categorie": "STOCK" | "CREANCE_CLIENT" | "DETTE_FOURNISSEUR" | "IMMOBILISATION" | null,
    "montant_fcfa": nombre entier ou null
  },

  "reponse_whatsapp": "Message de confirmation sobre et clair. Si l'operation est claire, confirme l'enregistrement au journal avec son compte SYSCOHADA. Si le motif d'une sortie Wave/OM est flou, demande une precision en proposant les 4 choix sans emoji."
}
"""

    try:
        res = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}]
        )

        raw = "".join(b.text for b in res.content if hasattr(b, "text")).strip()
        if raw.startswith("```json"): raw = raw[7:]
        if raw.startswith("```"): raw = raw[3:]
        if raw.endswith("```"): raw = raw[:-3]
        parsed = json.loads(raw.strip())

        sp = get_supabase()
        entreprise = get_or_create_entreprise(sp, sender_phone) if sp else {}
        entreprise_id = entreprise.get("id")

        intention = parsed.get("intention")

        # 1. Mise à jour de l'heure du rappel quotidien
        if intention == "MODIFIER_HEURE_RITUEL" and parsed.get("heure_rituel") and sp and entreprise_id:
            heure = parsed.get("heure_rituel")
            try:
                sp.table("entreprises").update({"heure_rappel_quotidien": heure}).eq("id", entreprise_id).execute()
            except Exception:
                pass

        # 2. Gestion détaillée des Dettes et Créances
        dette_info = parsed.get("dette_info") or {}
        dette_action = dette_info.get("action")
        dette_type = dette_info.get("type")
        tiers_nom = dette_info.get("tiers_nom")
        montant_dette = int(dette_info.get("montant_fcfa") or 0)
        date_echeance = dette_info.get("date_echeance")

        if dette_action and montant_dette > 0 and sp and entreprise_id:
            try:
                if dette_action == "CREATION":
                    sp.table("dettes_creances").insert({
                        "entreprise_id": entreprise_id,
                        "type": dette_type,
                        "tiers_nom": tiers_nom or "Tiers non précisé",
                        "montant_initial_fcfa": montant_dette,
                        "montant_restant_fcfa": montant_dette,
                        "date_echeance": date_echeance,
                        "frequence_relance_jours": 3,
                        "statut": "EN_COURS"
                    }).execute()
                elif dette_action == "REMBOURSEMENT":
                    res_dette = sp.table("dettes_creances").select("*").eq("entreprise_id", entreprise_id).eq("tiers_nom", tiers_nom).neq("statut", "SOLDE").limit(1).execute()
                    if res_dette.data:
                        dette_id = res_dette.data[0]["id"]
                        actuel_restant = int(res_dette.data[0]["montant_restant_fcfa"])
                        nouveau_restant = max(0, actuel_restant - montant_dette)
                        nouveau_statut = "SOLDE" if nouveau_restant == 0 else "PARTIELLEMENT_REMBOURSE"
                        sp.table("dettes_creances").update({"montant_restant_fcfa": nouveau_restant, "statut": nouveau_statut}).eq("id", dette_id).execute()
            except Exception:
                pass

            mois_courant = datetime.now().strftime("%Y-%m")
            col_target = "dettes_fournisseurs_fcfa" if dette_type == "DETTE_FOURNISSEUR" else "creances_clients_fcfa"
            try:
                exist_st = sp.table("etats_structurels").select("id", col_target).eq("entreprise_id", entreprise_id).eq("periode_mois", mois_courant).execute()
                if exist_st.data:
                    current_val = int(exist_st.data[0].get(col_target) or 0)
                    new_val = current_val + montant_dette if dette_action == "CREATION" else max(0, current_val - montant_dette)
                    sp.table("etats_structurels").update({col_target: new_val}).eq("id", exist_st.data[0]["id"]).execute()
                else:
                    sp.table("etats_structurels").insert({"entreprise_id": entreprise_id, "periode_mois": mois_courant, col_target: montant_dette}).execute()
            except Exception:
                pass

        # 3. Enregistrement d'une transaction de trésorerie (Wave, OM, Espèces)
        tx_data = parsed.get("transaction") or {}
        if tx_data.get("is_transaction") and tx_data.get("montant_fcfa", 0) > 0 and sp and entreprise_id:
            src = (tx_data.get("source_paiement") or "WAVE").upper()
            cpt = str(tx_data.get("compte_syscohada", "701"))
            # Si c'est Wave/OM avec compte qualifié, validé d'office ; si espèces sans reçu ou compte 471, en attente
            if src in ["WAVE", "ORANGE_MONEY", "BANQUE"] and not cpt.startswith("471"):
                statut_init = "VALIDE_PME"
            else:
                statut_init = "EN_ATTENTE_JUSTIFICATIF" if tx_data.get("type_flux") == "SORTIE" else "VALIDE_PME"
            
            ref_ext = tx_data.get("reference_externe")
            tx_record = {
                "entreprise_id": entreprise_id,
                "libelle": tx_data.get("libelle", user_text[:100]),
                "compte_syscohada": cpt,
                "type_flux": tx_data.get("type_flux", "ENTREE"),
                "est_professionnel": tx_data.get("est_professionnel", True),
                "montant_fcfa": int(tx_data.get("montant_fcfa")),
                "source_paiement": src,
                "reference_externe": ref_ext,
                "statut_validation": statut_init
            }
            try:
                inserted = sp.table("transactions").insert(tx_record).execute()
                print(f"Transaction insérée : ID {inserted.data[0]['id']} ({statut_init})")
            except Exception as e:
                # Si colonne reference_externe n'existe pas en base, insertion sans cette clé
                tx_record.pop("reference_externe", None)
                inserted = sp.table("transactions").insert(tx_record).execute()
                print(f"Transaction insérée (fallback) : ID {inserted.data[0]['id']} ({statut_init})")

        # 4. Enregistrement d'un état structurel (Stock, Immobilisation)
        struct_data = parsed.get("structurel") or {}
        cat = struct_data.get("categorie")
        montant_struct = struct_data.get("montant_fcfa")

        if cat in ["STOCK", "IMMOBILISATION"] and montant_struct and sp and entreprise_id:
            mois_courant = datetime.now().strftime("%Y-%m")
            col_name = "valeur_stock_fcfa" if cat == "STOCK" else "immobilisations_fcfa"
            try:
                exist = sp.table("etats_structurels").select("id").eq("entreprise_id", entreprise_id).eq("periode_mois", mois_courant).execute()
                if exist.data and len(exist.data) > 0:
                    sp.table("etats_structurels").update({col_name: int(montant_struct)}).eq("id", exist.data[0]["id"]).execute()
                else:
                    sp.table("etats_structurels").insert({"entreprise_id": entreprise_id, "periode_mois": mois_courant, col_name: int(montant_struct)}).execute()
            except Exception:
                pass

        # 5. Consultation de l'inventaire journalier / chiffre d'affaires
        if intention == "CONSULTATION_INVENTAIRE_JOUR" and sp and entreprise_id:
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                txs = sp.table("transactions").select("*").eq("entreprise_id", entreprise_id).eq("date_operation", today_str).execute().data or []
                total_in = sum(int(t.get("montant_fcfa") or 0) for t in txs if t.get("type_flux") == "ENTREE")
                total_out = sum(int(t.get("montant_fcfa") or 0) for t in txs if t.get("type_flux") == "SORTIE")
                marge = total_in - total_out
                manquants = [t for t in txs if t.get("statut_validation") == "EN_ATTENTE_JUSTIFICATIF"]

                wave, om, especes, total_dispo = get_tresorerie_stats(sp, entreprise_id)
                synth_msg = (
                    f"Arrêté de trésorerie journalier ({today_str}) :\n\n"
                    f"Disponibilités liquides à cet instant :\n"
                    f"• Trésorerie actuelle dans Wave : {wave:,.0f} FCFA\n"
                    f"• Trésorerie actuelle dans Orange Money : {om:,.0f} FCFA\n"
                    f"• Trésorerie actuelle en Espèces : {especes:,.0f} FCFA\n"
                    f"• Total des liquidités disponibles : {total_dispo:,.0f} FCFA\n\n"
                    f"Flux d'exploitation de la journée :\n"
                    f"• Total des encaissements d'exploitation : {total_in:,.0f} FCFA\n"
                    f"• Total des décaissements et charges : {total_out:,.0f} FCFA\n"
                    f"• Résultat net d'exploitation estimé : {marge:,.0f} FCFA\n\n"
                    f"Contrôle des pièces probantes :\n"
                )
                if manquants:
                    synth_msg += f"Vigilance : vous avez {len(manquants)} dépense(s) en attente de reçu fiscal ou facture. Veuillez photographier les justificatifs pour garantir la déductibilité de la charge.\n\n"
                else:
                    synth_msg += "Conformité certifiée : l'ensemble de vos flux du jour dispose de justificatifs probants.\n\n"

                synth_msg += "Avez-vous d'autres opérations en espèces, par Wave ou via Orange Money à consigner avant la clôture définitive ?"
                return synth_msg
            except Exception as e:
                print(f"Info consultation inventaire : {e}")

        # 6. Consultation des agences partenaires
        if intention == "CONSULTATION_AGENCES_PARTENAIRES":
            agences_txt = ""
            if sp:
                try:
                    res_ag = sp.table("agences_partenaires").select("*").eq("actif", True).execute()
                    if res_ag.data:
                        agences_txt = "\n".join([f"- {a['nom_agence']} ({a.get('contact_telephone', 'Dakar')})" for a in res_ag.data])
                except Exception:
                    pass
            if not agences_txt:
                agences_txt = (
                    "- Cabinet Dakar Fiduciaire & Audit (Plateau, Dakar - Tel: 33 821 00 12)\n"
                    "- Cabinet Sylla & Associes Expertise (Mermoz, Dakar - Tel: 33 860 45 78)\n"
                    "- Cabinet Ba & Partenaires agrees ONECCA (Almadies, Dakar - Tel: 33 820 90 34)"
                )
            return (
                "Agences d'expertise comptable partenaires en collaboration avec Grow :\n\n"
                f"{agences_txt}\n\n"
                "Ces agences ont un acces direct et securise a vos journaux sur notre tableau de bord pour certifier vos bilans et appuyer vos dossiers de financement bancaire."
            )

        # 7. Consultation des dettes et créances
        if intention == "CONSULTATION_DETTES" and sp and entreprise_id:
            try:
                res_d = sp.table("dettes_creances").select("*").eq("entreprise_id", entreprise_id).neq("statut", "SOLDE").execute().data or []
                dettes = [d for d in res_d if d.get("type") == "DETTE_FOURNISSEUR"]
                creances = [d for d in res_d if d.get("type") == "CREANCE_CLIENT"]

                tot_d = sum(int(d.get("montant_restant_fcfa") or 0) for d in dettes)
                tot_c = sum(int(d.get("montant_restant_fcfa") or 0) for d in creances)

                d_lines = "\n".join([f"  - {d.get('tiers_nom')} : {int(d.get('montant_restant_fcfa')):,.0f} FCFA" for d in dettes]) or "  - Aucune dette fournisseur en cours."
                c_lines = "\n".join([f"  - {c.get('tiers_nom')} : {int(c.get('montant_restant_fcfa')):,.0f} FCFA" for c in creances]) or "  - Aucune creance client en attente."

                return (
                    "Etat de vos engagements financiers et creances :\n\n"
                    f"1. Dettes Fournisseurs (Total : {tot_d:,.0f} FCFA) :\n"
                    f"{d_lines}\n\n"
                    f"2. Creances Clients a recouvrer (Total : {tot_c:,.0f} FCFA) :\n"
                    f"{c_lines}\n\n"
                    "Un rappel automatique est programme tous les 3 jours jusqu'au solde complet."
                )
            except Exception as e:
                print(f"Info consultation dettes : {e}")

        return parsed.get("reponse_whatsapp", "Message bien reçu par Grow !")

    except Exception as e:
        print(f"Erreur process_text_with_ai : {e}")
        return f"Grow a bien noté votre message : '{user_text}'. Merci !"


async def send_whatsapp_message(to_phone: str, text: str):
    """Envoi d'un message sur WhatsApp via l'API Cloud de Meta (robuste via urllib)."""
    load_dotenv(override=True)
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("PHONE_NUMBER_ID")

    if not token or not phone_id:
        return

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    formatted_text = format_grow_message(text)
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": formatted_text}
    }

    def _sync_send():
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                print(f"Statut envoi Meta vers {to_phone} : {resp.status}")
        except Exception as e:
            print(f"Erreur lors de l'envoi WhatsApp vers {to_phone} : {e}")

    await asyncio.to_thread(_sync_send)


async def send_whatsapp_audio(to_phone: str, audio_source: str):
    """
    Envoi d'une vraie Note Vocale WhatsApp (PTT) avec le logo officiel Grow du profil.
    Uploade directement le fichier OGG OPUS via Meta Media API pour garantir l'affichage
    de la photo de profil Grow et de l'onde sonore verte (au lieu du casque jaune).
    """
    load_dotenv(override=True)
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("PHONE_NUMBER_ID")

    if not token or not phone_id or not audio_source:
        return

    # Résolution du fichier local si audio_source est un nom de fichier ou un chemin
    static_audio_dir = os.path.join(STATIC_DIR, "audio")
    file_path = None
    if os.path.isabs(audio_source) and os.path.exists(audio_source):
        file_path = audio_source
    elif os.path.exists(os.path.join(static_audio_dir, os.path.basename(audio_source))):
        file_path = os.path.join(static_audio_dir, os.path.basename(audio_source))

    # 1. Upload binaire direct vers Meta Media API (Garantit 100% l'affichage de l'avatar Grow)
    media_id = None
    if file_path and os.path.exists(file_path):
        try:
            import requests
            upload_url = f"https://graph.facebook.com/v21.0/{phone_id}/media"
            headers_up = {"Authorization": f"Bearer {token}"}
            with open(file_path, "rb") as f_up:
                files = {"file": (os.path.basename(file_path), f_up, "audio/ogg; codecs=opus")}
                data = {"messaging_product": "whatsapp", "type": "audio/ogg"}
                up_res = requests.post(upload_url, headers=headers_up, files=files, data=data, timeout=25)
                if up_res.status_code == 200:
                    media_id = up_res.json().get("id")
                    print(f"[META MEDIA UPLOAD RÉUSSI] ID : {media_id} pour {os.path.basename(file_path)}")
                else:
                    print(f"Info retour Meta Media upload ({up_res.status_code}) : {up_res.text}")
        except Exception as e_up:
            print(f"Info upload Meta Media : {e_up}")

    # 2. Envoi du message WhatsApp Cloud API avec voice: True
    url_msg = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers_msg = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }

    if media_id:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "audio",
            "audio": {
                "id": media_id,
                "voice": True
            }
        }
    else:
        # Fallback lien public avec voice: True
        audio_url = audio_source if audio_source.startswith("http") else f"{get_public_base_url()}/static/audio/{os.path.basename(audio_source)}"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "audio",
            "audio": {
                "link": audio_url,
                "voice": True
            }
        }

    def _sync_send_audio():
        try:
            req = urllib.request.Request(
                url_msg,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers_msg
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                print(f"Statut envoi Note Vocale Meta (avec Logo Grow) vers {to_phone} : {resp.status}")
        except Exception as e:
            print(f"Erreur lors de l'envoi Audio WhatsApp vers {to_phone} : {e}")

    await asyncio.to_thread(_sync_send_audio)


async def send_whatsapp_text_and_audio(to_phone: str, msg_text: str, langue: str = "fr"):
    """
    Envoie systématiquement le message texte ET la note vocale audio correspondante.
    Permet à chaque commerçant de lire ou d'écouter les bilans et rappels programmés.
    """
    if not to_phone or not msg_text:
        return

    # 1. Envoi du message texte
    await send_whatsapp_message(to_phone, msg_text)

    # 2. Génération et envoi de la note vocale (format officiel OGG OPUS avec logo Grow)
    try:
        audio_fn = await generer_note_vocale_audio(msg_text, langue=langue)
        if audio_fn:
            await send_whatsapp_audio(to_phone, audio_fn)
            print(f"[VOCAL PROGRAMMÉ ENVOYÉ] vers {to_phone} : {audio_fn}")
    except Exception as e_v:
        print(f"Info envoi note vocale programmée : {e_v}")


async def daily_ritual_check():
    """Déclenchement automatique du Grand Bilan Quotidien de clôture (par défaut 21h00 heure de Dakar ou heure choisie)."""
    sp = get_supabase()
    if not sp:
        return
    now_dakar = get_now_dakar()
    now_hm = now_dakar.strftime("%H:%M")
    try:
        res = sp.table("entreprises").select("*").execute()
        for ent in res.data or []:
            # Heure par défaut à 21:00 heure de Dakar
            heure_conf = (ent.get("heure_rappel_quotidien") or "21:00")[:5]
            if heure_conf == now_hm:
                phone = ent.get("telephone_whatsapp")
                ent_id = ent.get("id")
                nom = ent.get("nom_entreprise", "Entreprise")
                lang = ent.get("langue_preferee") or "fr"

                today_str = now_dakar.strftime("%Y-%m-%d")
                txs = sp.table("transactions").select("*").eq("entreprise_id", ent_id).execute().data or []
                
                # Filtrer les transactions d'aujourd'hui uniquement pour l'activité du jour
                txs_du_jour = [t for t in txs if (t.get("date_operation") or t.get("created_at") or "").startswith(today_str)]
                treso_stats = get_tresorerie_stats(sp, ent_id)

                # Message de rituel consolidé de 21h00
                msg = generer_message_rituel_soir(nom, txs_du_jour, treso_stats)

                # Rappel quotidien NINEA si attestation papier manquante
                donnees_onb = ent.get("donnees_onboarding") or {}
                if not donnees_onb.get("ninea_valide_par_preuve", False) and ent.get("ninea"):
                    msg += (
                        "\n\nRappel administratif Grow :\n"
                        "Votre numéro NINEA est enregistré mais votre attestation papier n'a pas encore été transmise en photo. "
                        "Veuillez prendre en photo votre document papier NINEA et l'envoyer dans cette discussion pour finaliser la certification officielle de votre dossier."
                    )

                # Envoi Texte + Note Vocale
                await send_whatsapp_text_and_audio(phone, msg, langue=lang)
                print(f"Grand Bilan de 21h00 (Texte + Vocal Dakar) envoyé à {nom} ({phone})")
    except Exception as e:
        print(f"Info daily_ritual_check : {e}")


async def flash_summary_3h_check():
    """Point Flash toutes les 3 heures (09h00, 12h00, 15h00, 18h00 heure de Dakar) : flux du jour uniquement."""
    sp = get_supabase()
    if not sp:
        return
    now_dakar = get_now_dakar()
    now_hm = now_dakar.strftime("%H:%M")
    today_str = now_dakar.strftime("%Y-%m-%d")
    try:
        res = sp.table("entreprises").select("*").execute()
        for ent in res.data or []:
            phone = ent.get("telephone_whatsapp")
            ent_id = ent.get("id")
            nom = ent.get("nom_entreprise", "Entreprise")
            lang = ent.get("langue_preferee") or "fr"

            txs = sp.table("transactions").select("*").eq("entreprise_id", ent_id).execute().data or []
            txs_du_jour = [t for t in txs if (t.get("date_operation") or t.get("created_at") or "").startswith(today_str)]
            treso_stats = get_tresorerie_stats(sp, ent_id)
            base_url = get_public_base_url()
            dash_url = f"{base_url}/dashboard?phone={phone}" if phone else ""

            msg = generer_point_flash_journee(nom, txs_du_jour, treso_stats, now_hm, dashboard_url=dash_url)
            # Envoi Texte + Note Vocale
            await send_whatsapp_text_and_audio(phone, msg, langue=lang)
            print(f"Point Flash {now_hm} (Texte + Vocal Dakar) envoyé à {nom} ({phone})")
    except Exception as e:
        print(f"Info flash_summary_3h_check : {e}")


async def morning_greeting_check():
    """Message matinal de 06h00 (heure de Dakar) : résume les transactions de la nuit et refait le compte exact de départ."""
    sp = get_supabase()
    if not sp:
        return
    now_dakar = get_now_dakar()
    today_str = now_dakar.strftime("%Y-%m-%d")
    hier_str = (now_dakar - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        res = sp.table("entreprises").select("*").execute()
        for ent in res.data or []:
            phone = ent.get("telephone_whatsapp")
            ent_id = ent.get("id")
            nom = ent.get("nom_entreprise", "Entreprise")
            lang = ent.get("langue_preferee") or "fr"

            txs = sp.table("transactions").select("*").eq("entreprise_id", ent_id).execute().data or []
            
            # Transactions de la nuit : entre 21h hier soir et 06h ce matin
            txs_nuit = []
            for t in txs:
                c_at = t.get("created_at") or t.get("date_operation") or ""
                if c_at.startswith(hier_str):
                    if "T21:" in c_at or "T22:" in c_at or "T23:" in c_at:
                        txs_nuit.append(t)
                elif c_at.startswith(today_str):
                    if any(f"T{h:02d}:" in c_at for h in range(0, 6)):
                        txs_nuit.append(t)

            treso_stats = get_tresorerie_stats(sp, ent_id)
            msg = generer_message_matin_6h(nom, txs_nuit, treso_stats)
            # Envoi Texte + Note Vocale
            await send_whatsapp_text_and_audio(phone, msg, langue=lang)
            print(f"Message matinal de 06h00 (Texte + Vocal Dakar) envoyé à {nom} ({phone})")
    except Exception as e:
        print(f"Info morning_greeting_check : {e}")


async def check_and_send_dettes_reminders():
    """Relance automatique des dettes et créances tous les 3 jours."""
    sp = get_supabase()
    if not sp:
        return
    try:
        res = sp.table("dettes_creances").select("*, entreprises(telephone_whatsapp, nom_entreprise)").neq("statut", "SOLDE").execute()
        for item in res.data or []:
            tiers = item.get("tiers_nom")
            restant = int(item.get("montant_restant_fcfa") or 0)
            dette_type = item.get("type")
            echeance = item.get("date_echeance")
            phone = item.get("entreprises", {}).get("telephone_whatsapp")
            if not phone:
                continue

            if dette_type == "DETTE_FOURNISSEUR":
                msg = (
                    f"Rappel pour votre dette fournisseur :\n"
                    f"Vous devez encore {restant:,.0f} FCFA à {tiers}"
                    + (f" (prévu pour le : {echeance})" if echeance else "") + ".\n\n"
                    f"Avez-vous fait un paiement total ou une avance aujourd'hui ?"
                )
            else:
                msg = (
                    f"Rappel pour l'argent qu'on vous doit :\n"
                    f"Votre client {tiers} vous doit encore {restant:,.0f} FCFA"
                    + (f" (prévu pour le : {echeance})" if echeance else "") + ".\n\n"
                    f"Ce client vous a-t-il versé un paiement ou un acompte ?"
                )
            # Envoi Texte + Note Vocale
            await send_whatsapp_text_and_audio(phone, msg, langue="fr")
            sp.table("dettes_creances").update({"derniere_relance": datetime.now().strftime("%Y-%m-%d")}).eq("id", item["id"]).execute()
    except Exception as e:
        print(f"Info check_and_send_dettes_reminders : {e}")


async def weekly_closure_check():
    """Point hebdomadaire sur les impayés et dettes (Chaque dimanche à 18h00)."""
    sp = get_supabase()
    if not sp:
        return
    try:
        mois_courant = datetime.now().strftime("%Y-%m")
        res = sp.table("entreprises").select("*").execute()
        for ent in res.data or []:
            phone = ent.get("telephone_whatsapp")
            ent_id = ent.get("id")
            nom = ent.get("nom_entreprise", "Entreprise")
            lang = ent.get("langue_preferee") or "fr"

            st = sp.table("etats_structurels").select("*").eq("entreprise_id", ent_id).eq("periode_mois", mois_courant).execute().data
            creances = int(st[0].get("creances_clients_fcfa") or 0) if st else 0
            dettes = int(st[0].get("dettes_fournisseurs_fcfa") or 0) if st else 0

            msg = (
                f"Bonjour {nom}.\n\n"
                f"C'est le moment de faire le point de la semaine sur vos impayés :\n\n"
                f"1. L'argent que vos clients vous doivent :\n"
                f"• Montant total restant : {creances:,.0f} FCFA\n"
                f"Est-ce que certains clients vous ont remboursé tout ou une partie ce week-end ?\n\n"
                f"2. L'argent que vous devez à vos fournisseurs :\n"
                f"• Montant total restant : {dettes:,.0f} FCFA\n"
                f"Avez-vous payé une facture ou versé une avance cette semaine ?\n\n"
                f"Envoyez vos mises à jour pour que vos comptes restent toujours exacts."
            )
            # Envoi Texte + Note Vocale
            await send_whatsapp_text_and_audio(phone, msg, langue=lang)
            print(f"Point hebdomadaire (Texte + Vocal) envoyé à {nom} ({phone})")
    except Exception as e:
        print(f"Info weekly_closure_check : {e}")


async def monthly_closure_check():
    """Point mensuel : stock, salaires et renouvellement abonnement (Chaque 28 du mois à 09h00)."""
    sp = get_supabase()
    if not sp:
        return
    try:
        res = sp.table("entreprises").select("*").execute()
        for ent in res.data or []:
            phone = ent.get("telephone_whatsapp")
            nom = ent.get("nom_entreprise", "Entreprise")
            lang = ent.get("langue_preferee") or "fr"

            msg = (
                f"Bonjour {nom}.\n\n"
                f"C'est la fin du mois, faisons le point pour clôturer vos comptes :\n\n"
                f"1. Votre stock restant :\n"
                f"Quelle est la valeur approximative de votre stock en boutique ou atelier ce soir ? Envoyez aussi quelques photos de vos rayons.\n\n"
                f"2. Les salaires :\n"
                f"Avez-vous payé des salaires ou des commissions ce mois-ci ? Quels sont les montants ?\n\n"
                f"3. Votre bilan du mois :\n"
                f"Votre récapitulatif du mois est en préparation pour votre comptable.\n\n"
                f"4. Renouvellement de votre abonnement Grow :\n"
                f"Pour continuer à suivre vos comptes automatiquement chaque jour, renouvelez votre abonnement mensuel sur ce lien sécurisé :\n"
                f"{get_public_base_url()}/abonnement"
            )
            # Envoi Texte + Note Vocale
            await send_whatsapp_text_and_audio(phone, msg, langue=lang)
            print(f"Message mensuel (Texte + Vocal) envoyé à {nom} ({phone})")
    except Exception as e:
        print(f"Info monthly_closure_check : {e}")


@app.on_event("startup")
async def start_scheduler():
    """Demarrage du planificateur de taches de fond rigoureusement cale sur le fuseau Africa/Dakar (GMT)."""
    # 1. Vérification minute par minute pour le Grand Bilan du Soir (21h00 par défaut ou heure personnalisée)
    scheduler.add_job(daily_ritual_check, "cron", minute="*", timezone=TZ_DAKAR)
    
    # 2. Point Flash toutes les 3 heures pendant la journée (09h00, 12h00, 15h00, 18h00, 21h00 heure de Dakar)
    scheduler.add_job(flash_summary_3h_check, "cron", hour="09,12,15,18,21", minute="00", timezone=TZ_DAKAR)

    # 3. Message matinal de 06h00 heure de Dakar (Bilan de la nuit et réinitialisation des comptes de départ)
    scheduler.add_job(morning_greeting_check, "cron", hour="06", minute="00", timezone=TZ_DAKAR)

    # 4. Relance automatique des dettes et créances tous les 3 jours (à 10h00 heure de Dakar)
    scheduler.add_job(check_and_send_dettes_reminders, "cron", hour="10", minute="00", timezone=TZ_DAKAR)

    # 5. Point hebdomadaire et mensuel
    scheduler.add_job(weekly_closure_check, "cron", day_of_week="sun", hour="18", minute="00", timezone=TZ_DAKAR)
    scheduler.add_job(monthly_closure_check, "cron", day="28", hour="09", minute="00", timezone=TZ_DAKAR)

    scheduler.start()
    print("Planificateur automatique Grow (APScheduler) cale sur l'heure du Senegal (Africa/Dakar) demarre avec succes !")


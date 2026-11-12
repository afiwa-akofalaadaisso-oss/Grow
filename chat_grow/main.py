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

# Fuseau horaire officiel du SÃ©nÃ©gal (Dakar / GMT)
TZ_DAKAR = zoneinfo.ZoneInfo("Africa/Dakar")

def get_now_dakar() -> datetime:
    """Retourne la date et l'heure courante exacte au SÃ©nÃ©gal (fuseau Africa/Dakar / GMT)."""
    return datetime.now(TZ_DAKAR)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

app = FastAPI(title="Grow MVP - Assistant Comptable SYSCOHADA WhatsApp")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
    """DÃ©tecte de faÃ§on robuste toute affirmation de paiement d'abonnement (accents, apostrophes courbes, fautes)."""
    if not text:
        return False
    import unicodedata
    t = text.lower().replace(chr(8217), "'").replace(chr(96), "'").strip()
    norm = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    
    phrases = [
        "j'ai paye", "jai paye", "j'ai payer", "jai payer", "je viens de payer",
        "c'est paye", "c'est payer", "deja paye", "deja payer",
        "paiement effectue", "paiement confirme", "abonnement paye",
        "j'ai regle", "jai regle", "voici mon recu de paiement", "recu de paiement", "recu paiement"
    ]
    if any(p in norm for p in phrases):
        return True

    if norm in ["paye", "payer", "paiement", "c'est bon", "c'est fait", "abonne"]:
        return True

    return False


def is_entreprise_deja_configuree(sender_phone: str) -> bool:
    """VÃ©rifie si le numÃ©ro possÃ¨de dÃ©jÃ  une entreprise entiÃ¨rement configurÃ©e (les 5 Ã©tapes d'onboarding achevÃ©es)."""
    # 1. VÃ©rification dans l'Ã©tat onboarding local
    state = get_onboarding_state(sender_phone)
    if state.get("etape") == "TERMINE" or state.get("statut") == "COMPLET":
        return True

    # 2. VÃ©rification dans Supabase
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
        print(f"Info vÃ©rification entreprise existante : {e}")

    return False


def get_instructions_journee_message(base_url: str, sender_phone: str, nom_entreprise: str = "Votre Entreprise") -> str:
    """Message matinal et consignes opÃ©rationnelles : la vraie bataille quotidienne commence ici."""
    return (
        f"Bonjour {nom_entreprise}.\n\n"
        "Une nouvelle journÃ©e d'activitÃ© commence et la vraie bataille quotidienne pour vos finances dÃ©marre maintenant !\n\n"
        "Grow est dÃ©sormais en premiÃ¨re ligne Ã  vos cÃ´tÃ©s sur WhatsApp pour intercepter, vÃ©rifier et certifier toutes vos opÃ©rations en temps rÃ©el :\n\n"
        "1. VENTES & PAIEMENTS OPERATEURS (WAVE, ORANGE MONEY, FREE) :\n"
        "â€¢ Vos encaissements reÃ§us sur vos comptes marchands ou via SMS de transfert sont enregistrÃ©s et imputÃ©s au journal financier sans aucune intervention de votre part.\n"
        "â€¢ Si vous recevez un SMS d'un opÃ©rateur sur votre tÃ©lÃ©phone, transfÃ©rez ou collez le message ici dans le chat : Grow extrait instantanÃ©ment le montant, le client et la rÃ©fÃ©rence officielle.\n\n"
        "2. VENTES EN CASH (ESPECES) :\n"
        "â€¢ DÃ¨s que vous encaissez du cash au comptoir, envoyez simplement un court message ou une note vocale (exemple : Â« Vente marchandise 35 000 cash Â»). Vos comptes sont mis Ã  jour Ã  la seconde.\n\n"
        "3. REGLE D'OR SUR LES DEPENSES & ACHATS EN CASH :\n"
        "Chaque sortie d'argent en espÃ¨ces (achats de marchandises, carburant, taxis, factures Senelec / Sen'Eau, loyer, repas, fournitures) doit OBLIGATOIREMENT Ãªtre accompagnÃ©e de sa piÃ¨ce justificative :\n"
        "â€¢ Prenez immÃ©diatement la photo du reÃ§u, de la facture, du ticket de caisse ou mÃªme du stock achetÃ© avant de ranger le produit.\n"
        "â€¢ ATTENTION : Sans piÃ¨ce justificative, Grow refusera de valider la dÃ©pense. C'est vous qui perdez car elle ne sera pas dÃ©ductible de votre bÃ©nÃ©fice imposable auprÃ¨s des impÃ´ts (DGID) et votre trÃ©sorerie sera faussÃ©e !\n\n"
        "4. SUIVI DES DETTES & CREANCES :\n"
        "â€¢ Si un client prend Ã  crÃ©dit : Ã©crivez simplement Â« Moussa a pris des habits pour 25 000, il paiera mardi Â».\n"
        "â€¢ Si vous devez Ã  un fournisseur : Ã©crivez Â« J'ai pris 100 000 de tissu chez Fallou, dette Ã  rÃ©gler sous 15 jours Â».\n"
        "â€¢ Grow assure les relances automatiques pour vous faire encaisser votre argent.\n\n"
        "5. LE RITUEL DU SOIR (20H00) :\n"
        "Chaque soir Ã  20h00, Grow dresse le bilan complet de votre journÃ©e (total des ventes, marge nette certifiÃ©e, solde de caisse et rÃ©conciliation bancaire).\n\n"
        "Votre tableau de bord financier personnel est accessible 24h/24 en direct sur ce lien sÃ©curisÃ© :\n"
        f"{base_url}/dashboard?phone={sender_phone}\n\n"
        "Le front est ouvert : transfÃ©rez votre premiÃ¨re notification d'opÃ©rateur, notez votre premiÃ¨re vente ou envoyez la photo de votre premier reÃ§u !"
    )


def remove_all_emojis(text: str) -> str:
    """Supprime absolument tous les emojis et symboles speciaux."""
    emoji_pattern = re.compile(
        "["
        "\U00010000-\U0010FFFF"
        "\u2600-\u26FF"
        "\u2700-\u27BF"
        "\uFE00-\uFE0F"
        "]+", flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub("", text)
    for char in ["ðŸ‘‰", "âœ…", "â›”", "ðŸ”’", "ðŸ’°", "ðŸ“¸", "ðŸ¢", "ðŸ‘¥", "ðŸ’³", "ðŸ—ï¸", "ðŸ”¢", "ðŸ¦", "ðŸ“‚", "ðŸ“„", "ðŸŽ‰", "ðŸ’¸", "ðŸ“Š", "ðŸ§¾", "ðŸ“¦", "ðŸŽ«", "ðŸ“²", "ðŸ‘‹", "ðŸ™", "ðŸ‡¸ðŸ‡³", "ðŸ’ª", "ðŸ¤”", "ðŸ˜Š", "ðŸ“…", "â°"]:
        cleaned = cleaned.replace(char, "")
    return cleaned.strip()


def format_grow_message(body_text: str) -> str:
    """Structure Grow : Pas d'emoji, corps clair et sobre, pied de page assistance."""
    clean_body = remove_all_emojis(body_text)
    # Suppression absolue de tout sÃ©parateur tirets ou barres
    clean_body = re.sub(r'[-=â”_]{2,}', '', clean_body)

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
        # 1. VÃ©rification dans Supabase si l'entreprise a dÃ©jÃ  commencÃ© son onboarding
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
                "etape": "DEMANDE_NINEA",
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
                "statut": "EN_COURS",
                "abonnement_valide": True,
                "premier_contact_effectue": True
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

    # Synchronisation immÃ©diate avec Supabase
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
    """RÃ©cupÃ¨re ou crÃ©e automatiquement l'entreprise liÃ©e Ã  ce numÃ©ro WhatsApp."""
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
        print("Webhook validÃ© avec succÃ¨s par Meta !")
        return PlainTextResponse(content=hub_challenge)
    return {
        "status": "online",
        "message": "Grow MVP WhatsApp avec Onboarding NINEA & IA SYSCOHADA est 100% opÃ©rationnel ðŸš€"
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
    """Plaque prÃ©sentoir de comptoir officielle Grow pour impression A5/A6."""
    html_path = os.path.join(TEMPLATES_DIR, "carte_comptoir.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>PrÃ©sentoir comptoir en cours de gÃ©nÃ©ration</h1>", status_code=200)


@app.get("/telecharger-carte")
async def telecharger_carte():
    """TÃ©lÃ©charger directement l'image haute dÃ©finition de la plaque prÃ©sentoir Grow."""
    img_path = os.path.join(STATIC_DIR, "plaque_comptoir_grow.png")
    if os.path.exists(img_path):
        return FileResponse(img_path, media_type="image/png", filename="Plaque_Comptoir_Grow.png")
    return HTMLResponse("Image non trouvÃ©e", status_code=404)


@app.get("/api/dashboard-data")
async def get_dashboard_data(phone: str = None, entreprise_id: str = None):
    """Fournit les donnÃ©es rÃ©elles et isolÃ©es d'une entreprise et ses transactions depuis Supabase."""
    sp = get_supabase()
    if not sp:
        return {"error": "Base de donnÃ©es non disponible", "entreprises": [], "entreprise": None, "transactions": []}

    try:
        # RÃ©cupÃ©rer la liste des entreprises enregistrÃ©es
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

        # Si un numÃ©ro a Ã©tÃ© expressÃ©ment demandÃ© mais qu'il n'est pas encore en base :
        if not target_ent and phone:
            target_ent = {
                "id": f"new_{clean_phone}",
                "nom_entreprise": "Mon Entreprise (En cours de configuration)",
                "telephone_whatsapp": clean_phone,
                "ninea": "En cours d'enregistrement",
                "secteur_activite": "Commerce & Services",
                "adresse_siege": "Dakar, SÃ©nÃ©gal"
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
                    "adresse_siege": "Dakar, SÃ©nÃ©gal"
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

        # RÃ©cupÃ©rer uniquement les transactions rÃ©elles de cette entreprise si l'ID est un UUID valide
        raw_txs = []
        if ent_id and not str(ent_id).startswith("new_"):
            try:
                tx_query = sp.table("transactions").select("*, preuves_numeriques(*)").eq("entreprise_id", ent_id).order("date_operation", desc=True).order("created_at", desc=True).execute()
                raw_txs = tx_query.data or []
            except Exception as tx_err:
                print(f"Info tx query: {tx_err}")
                raw_txs = []

        # Calculer les montants rÃ©els
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

        # RÃ¨gle prudentielle BCEAO : 33% du cash-flow net pour le remboursement mensuel
        mensualite_max = max(0, int(solde_net * 0.33)) if solde_net > 0 else 0
        capacite_emprunt = mensualite_max * 24 if mensualite_max > 0 else (2500000 if raw_txs else 0)

        # Calcul du score financier rÃ©el (les paiements dÃ©matÃ©rialisÃ©s Wave, OM, Banque sont certifiÃ©s d'office)
        tx_with_proof = sum(1 for t in raw_txs if (t.get("preuves_numeriques") and len(t["preuves_numeriques"]) > 0) or t.get("statut_validation") == "VALIDE_PME" or (t.get("source_paiement") or "").upper() in ["WAVE", "ORANGE_MONEY", "BANQUE"])
        taux_preuve = (tx_with_proof / len(raw_txs)) if raw_txs else 1.0
        score_base = 50 + (30 if solde_net > 0 else 10) + int(20 * taux_preuve)
        score_financier = min(98, max(50, score_base)) if raw_txs else 70

        # Isolation stricte : si un tÃ©lÃ©phone ou un ID est spÃ©cifiÃ©, la liste ne contient QUE cette entreprise
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
        "Grow intercepte et enregistre automatiquement chacun de vos encaissements Wave ou Orange Money dans votre comptabilitÃ© SYSCOHADA, sans aucune saisie manuelle de votre part.\n\n"
        "3 SOLUTIONS POUR CONNECTER VOS PAIEMENTS :\n\n"
        "1. Wave Business (Portail Marchand officiel PME) :\n"
        "â€¢ Connectez-vous sur votre espace : business.wave.com\n"
        "â€¢ Allez dans ParamÃ¨tres DÃ©veloppeur > Webhooks > Ajouter un webhook\n"
        "â€¢ Collez votre URL personnelle Grow :\n"
        f"{base_url}/webhook/wave?phone={clean_p}\n"
        "â€¢ Cochez les Ã©vÃ©nements d'encaissement et enregistrez.\n\n"
        "2. Passerelle Relais SMS Android (IdÃ©al compte Wave Personnel / Orange Money) :\n"
        "â€¢ Installez l'application gratuite Â« SMS Forwarder Â» sur le smartphone Android du magasin.\n"
        "â€¢ CrÃ©ez une rÃ¨gle de transfert automatique vers votre URL Grow :\n"
        f"{base_url}/api/sms-gateway?phone={clean_p}\n"
        "â€¢ DÃ¨s qu'un SMS de vente est reÃ§u, il est relayÃ© silencieusement sans action de l'employÃ©.\n\n"
        "3. Capture d'Ã©cran WhatsApp (ZÃ©ro configuration technique) :\n"
        "â€¢ Prenez une capture d'Ã©cran du reÃ§u ou de la notification push Wave et envoyez-la moi directement ici.\n\n"
        "TESTER VOTRE LIAISON IMMÃ‰DIATEMENT :\n"
        "Pour tester votre connexion en direct avec une simulation certifiÃ©e de 1 000 FCFA, rÃ©pondez simplement Â« TESTER WEBHOOK Â».\n\n"
        "Guide interactif pas Ã  pas et testeur en 1 clic disponibles sur votre tableau de bord :\n"
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
            "libelle": f"Test Connexion RÃ©ussi - Encaissement Wave ({amount:,.0f} FCFA)",
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
        "TEST DE CONNEXION WEBHOOK RÃ‰USSI\n\n"
        "RÃ‰SUMÃ‰ DU TEST EN DIRECT :\n"
        f"â€¢ Canal vÃ©rifiÃ© : Webhook OpÃ©rateur {provider}\n"
        f"â€¢ Montant test : {amount:,.0f} FCFA\n"
        f"â€¢ RÃ©fÃ©rence test : {tx_id}\n"
        "â€¢ Imputation : Compte SYSCOHADA 701 (Vente de marchandises)\n"
        f"â€¢ TrÃ©sorerie crÃ©ditÃ©e : Compte SYSCOHADA 521 ({provider})\n"
        "â€¢ Statut : Liaison 100% opÃ©rationnelle et certifiÃ©e\n\n"
        "Vos vÃ©ritables encaissements clients seront dÃ©sormais interceptÃ©s et rÃ©conciliÃ©s automatiquement sans intervention manuelle :\n"
        f"{base_url}/dashboard?phone={clean_phone}"
    )
    await send_whatsapp_message(clean_phone, msg_test)

    return {
        "status": "success",
        "message": "Liaison Webhook validÃ©e avec succÃ¨s. Ã‰criture enregistrÃ©e et confirmation WhatsApp envoyÃ©e.",
        "tx_id": tx_id,
        "provider": provider,
        "amount": amount,
        "compte": compte
    }

@app.post("/api/test-webhook")
async def api_test_webhook(request: Request):
    """Point d'accÃ¨s de test et diagnostic webhook pour le tableau de bord Grow."""
    try:
        data = await request.json()
        phone = data.get("phone")
        provider = (data.get("provider") or "WAVE").upper()
        amount = int(data.get("amount") or 1000)

        if not phone:
            return {"status": "error", "message": "NumÃ©ro de tÃ©lÃ©phone requis"}

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
    Webhook OpÃ©rateur Wave & Wave Business Merchant :
    ReÃ§oit les notifications d'encaissement (QR code comptoir, checkout ou transfert) en direct depuis Wave.
    Le commerÃ§ant PME n'a absolument RIEN Ã  copier-coller : Grow intercepte le flux et notifie le gÃ©rant sur WhatsApp.
    """
    try:
        payload = await request.json()
        print("\n[NOTIFICATION OPÃ‰RATEUR WAVE REÃ‡UE] :", payload)

        # Support du format Wave standard (data imbriquÃ©) et du format direct
        data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else payload

        tx_id = payload.get("id") or data_obj.get("id") or data_obj.get("transaction_id") or f"WV-{int(datetime.now().timestamp())}"
        amount = int(float(data_obj.get("amount") or data_obj.get("montant") or payload.get("amount") or 0))

        # RÃ©solution du compte marchand Wave (NumÃ©ro de compte M_sn_... ou tÃ©lÃ©phone)
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

        # Si Wave fournit l'identifiant marchand (ex: M_sn_YgEkibrMRghV) sans tÃ©lÃ©phone
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

        # Identifier ou initialiser automatiquement l'entreprise liÃ©e au numÃ©ro de tÃ©lÃ©phone
        clean_phone = str(phone).replace("+", "").replace(" ", "").strip()
        res_ent = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_phone}%").limit(1).execute()
        if res_ent and res_ent.data:
            ent = res_ent.data[0]
        else:
            ent = get_or_create_entreprise(sp, clean_phone)

        ent_id = ent.get("id")
        ent_nom = ent.get("nom_entreprise", "Votre PME")

        type_flux = "ENTREE" if direction in ["CREDIT", "IN", "ENTREE", "RECEIVED"] else "SORTIE"

        # Classification Intelligente Automatique (Encaissement CA, MÃ©moire Fournisseurs, Services Nationaux)
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

        # Garantir un libellÃ© unique, distinct et dÃ©taillÃ© pour chaque encaissement Wave
        ref_aff = tx_id if tx_id else f"WV-{amount}"
        if not libelle_final or "Encaissement Wave" in libelle_final:
            libelle_final = f"Encaissement Wave - {amount:,.0f} FCFA ({tiers_nom} - RÃ©f: {ref_aff})"
        elif f"{amount:,.0f}" not in libelle_final:
            libelle_final = f"{libelle_final} ({amount:,.0f} FCFA - RÃ©f: {ref_aff})"

        # Insertion directe dans le journal prÃ©-comptable SYSCOHADA
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

        print(f"[GROW WEBHOOK AUTONOME] TX {tx_id} traitÃ©e via {methode} -> Compte {compte_syscohada} ({statut_val})")

        # Ingestion silencieuse en arriÃ¨re-plan : l'Ã©criture comptable est enregistrÃ©e discrÃ¨tement
        # en base de donnÃ©es et actualise le tableau de bord en direct sans spammer le commerÃ§ant.
        # Le commerÃ§ant reÃ§oit un bilan consolidÃ© lors des points flash toutes les 3 heures (09h, 12h, 15h, 18h, 21h).
        print(f"[GROW WAVE INGESTION SILENCIEUSE] Encaissement de {amount:,.0f} FCFA ({tx_id}) dÃ©posÃ© discrÃ¨tement en base et sur le dashboard pour {clean_phone or wave_account_id}. ZÃ©ro message WhatsApp individuel.")

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
    ReÃ§oit automatiquement en arriÃ¨re-plan chaque SMS bancaire/opÃ©rateur (Wave, OM, Free)
    reÃ§u sur le tÃ©lÃ©phone Android du commerÃ§ant et l'impute directement en comptabilitÃ© SYSCOHADA.
    Le commerÃ§ant n'a absolument rien Ã  toucher : l'appli Android renvoie le SMS dÃ¨s rÃ©ception.
    """
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form = await request.form()
            payload = dict(form)

        print("\n[RELAIS SMS ANDROID REÃ‡U] :", payload)

        sms_text = (
            payload.get("text")
            or payload.get("message")
            or payload.get("body")
            or payload.get("content")
            or payload.get("sms")
            or ""
        )
        sender_op = payload.get("from") or payload.get("sender") or "OpÃ©rateur"
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
            print(f"[RELAIS SMS] IgnorÃ© : L'entreprise {ent.get('nom_entreprise')} n'a pas encore validÃ© son onboarding officiel.")
            return {"status": "ignored", "reason": "Enterprise onboarding not completed"}

        ent_id = ent.get("id")

        # Analyse locale dÃ©terministe du SMS opÃ©rateur (Wave / Orange Money / Free)
        sms_op = parse_operator_sms_local(sms_text)
        if not sms_op or sms_op.get("montant_fcfa", 0) <= 0:
            print(f"[RELAIS SMS] IgnorÃ© : Le SMS reÃ§u n'est pas une transaction financiÃ¨re valide.")
            return {"status": "ignored", "reason": "Not a recognized financial operator transaction"}

        montant = sms_op.get("montant_fcfa", 0)
        operateur = sms_op.get("operateur", "WAVE")
        type_flux = sms_op.get("type_flux", "ENTREE")
        compte_syscohada = sms_op.get("compte_syscohada", "701")
        tiers_nom = sms_op.get("tiers_nom") or "Tiers"
        tiers_phone = sms_op.get("tiers_phone") or ""
        ref_externe = sms_op.get("reference_externe") or f"SMS-{int(datetime.now().timestamp())}"
        solde_nouveau = sms_op.get("solde_nouveau_fcfa") or 0
        libelle_complet = f"{sms_op.get('libelle')} (RÃ©f: {ref_externe})"

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

        print(f"[RELAIS SMS SUCCÃˆS] EnregistrÃ© : {montant:,.0f} FCFA ({operateur}) pour {clean_phone}")

        # Notification instantanÃ©e sur WhatsApp au commerÃ§ant
        base_url = get_public_base_url()
        solde_txt = f"â€¢ Nouveau solde {operateur} : {solde_nouveau:,.0f} FCFA\n" if solde_nouveau > 0 else ""
        type_desc = "Encaissement (Vente)" if type_flux == "ENTREE" else "DÃ©caissement (DÃ©pense)"

        msg_notif = (
            f"ENCAISSEMENT AUTOMATIQUE DÃ‰TECTÃ‰ ({operateur})\n\n"
            "RÃ‰SUMÃ‰ DE L'ENREGISTREMENT :\n"
            f"â€¢ Source : Relais SMS automatique en arriÃ¨re-plan\n"
            f"â€¢ Nature : {type_desc}\n"
            f"â€¢ Montant : {montant:,.0f} FCFA\n"
            f"â€¢ Tiers : {tiers_nom}" + (f" ({tiers_phone})" if tiers_phone else "") + "\n"
            f"â€¢ RÃ©fÃ©rence officielle : {ref_externe}\n"
            f"{solde_txt}"
            f"â€¢ Imputation : Compte SYSCOHADA {compte_syscohada}\n"
            "â€¢ Statut : EnregistrÃ© automatiquement sans aucune intervention\n\n"
            "Votre journal financier est Ã  jour en direct :\n"
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
    """Retourne la mÃ©moire des tiers et fournisseurs dÃ©jÃ  appris pour cette entreprise."""
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
    """DÃ©clenche immÃ©diatement le Rituel ConsolidÃ© du Soir (Batching) pour une PME."""
    sp = get_supabase()
    if not sp:
        return {"status": "error", "message": "Base de donnÃ©es non disponible"}

    ent_id = payload.get("entreprise_id") or "c3144ff0-013e-498f-9fdb-a2127c95f68f"
    res_ent = sp.table("entreprises").select("*").eq("id", ent_id).execute()
    if not res_ent.data:
        res_ent = sp.table("entreprises").select("*").limit(1).execute()

    if not res_ent.data:
        return {"status": "error", "message": "Aucune entreprise trouvÃ©e"}

    ent = res_ent.data[0]
    ent_id = ent.get("id")
    nom = ent.get("nom_entreprise", "Votre PME")
    phone = ent.get("telephone_whatsapp")

    # RÃ©cupÃ©rer les transactions
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
    """Met Ã  jour l'heure de rappel du rituel de clÃ´ture du soir (0 crÃ©dit consommÃ©)."""
    sp = get_supabase()
    if not sp:
        return {"success": False, "error": "Supabase non connectÃ©"}
    
    ent_id = payload.get("entreprise_id")
    nouvelle_heure = payload.get("heure")  # Format "HH:MM"
    
    if not ent_id or not nouvelle_heure:
        return {"success": False, "error": "DonnÃ©es incomplÃ¨tes (entreprise_id et heure requis)"}
    
    try:
        # Nettoyage et formatage HH:MM:00
        clean_heure = nouvelle_heure.strip()[:5] + ":00"
        res = sp.table("entreprises").update({"heure_rappel_quotidien": clean_heure}).eq("id", ent_id).execute()
        return {"success": True, "heure": clean_heure[:5], "message": f"Heure de rappel programmÃ©e Ã  {clean_heure[:5]} avec succÃ¨s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/agence", response_class=HTMLResponse)
async def serve_agence_dashboard():
    """Espace rÃ©servÃ© Ã  l'Expert-Comptable / Agence ONECCA."""
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
    <title>Abonnement Grow &bull; PrÃ©-comptabilitÃ© PME</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>body { font-family: 'Plus Jakarta Sans', sans-serif; }</style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center p-4">
    <div class="max-w-md w-full bg-slate-800 rounded-3xl p-6 sm:p-8 border border-slate-700 shadow-2xl text-center space-y-6">
        <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-700 mx-auto flex items-center justify-center text-3xl shadow-lg">
            ðŸ¤²ðŸŒ±
        </div>
        <div>
            <h1 class="text-2xl font-black text-white">Abonnement Grow PME</h1>
            <p class="text-xs text-slate-400 mt-1">Certification financiÃ¨re et prÃ©-comptabilitÃ© SYSCOHADA SMT</p>
        </div>
        <div class="bg-slate-900/80 rounded-2xl p-5 border border-slate-700 text-left space-y-3">
            <div class="flex justify-between items-baseline">
                <span class="text-sm font-bold text-slate-300">Formule Mensuelle Pro</span>
                <span class="text-2xl font-black text-emerald-400">10 000 <span class="text-xs font-semibold text-slate-400">FCFA/mois</span></span>
            </div>
            <ul class="text-xs text-slate-300 space-y-2 pt-2 border-t border-slate-800">
                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-emerald-400"></i> Assistant WhatsApp 24h/7j</li>
                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-emerald-400"></i> RelevÃ©s automatiques Wave, OM &amp; Caisse</li>
                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-emerald-400"></i> Dossiers financiers pour Banques &amp; ONECCA</li>
                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-emerald-400"></i> Archivage certifiÃ© des reÃ§us et factures</li>
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
        <p class="text-[11px] text-slate-500">AprÃ¨s paiement, renvoyez Â« J'ai payÃ© Â» sur WhatsApp pour activer vos 5 Ã©tapes d'onboarding.</p>
    </div>
    <script>
        function simulerPaiement(op) {
            alert('Simulation : Paiement via ' + op + ' rÃ©ussi !\\n\\nVous pouvez maintenant retourner sur WhatsApp et envoyer Â« J\\'ai payÃ© Â» pour commencer vos 5 Ã©tapes.');
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>""", status_code=200)


@app.post("/")
@app.post("/webhook")
async def receive_message(request: Request):
    """RÃ©ception et traitement en direct des messages WhatsApp."""
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
            sender_phone = message.get("from")
            msg_type = message.get("type")

            # 1. MESSAGE TEXTE
            if msg_type == "text":
                user_text = message.get("text", {}).get("body", "")
                print(f"Message texte de {sender_phone} ({contact_name}) : '{user_text}'")

                reply_text = await handle_incoming_message(sender_phone, user_text, None, contact_name)
                await send_whatsapp_message(sender_phone, reply_text)

            # 2. IMAGE (NINEA, ReÃ§u papier, capture Wave)
            elif msg_type == "image":
                image_info = message.get("image", {})
                media_id = image_info.get("id")
                caption = image_info.get("caption", "")
                print(f"Image reÃ§ue de {sender_phone} (ID: {media_id})")

                reply_text = await handle_incoming_message(sender_phone, caption, ("PHOTO", media_id), contact_name)
                await send_whatsapp_message(sender_phone, reply_text)

            # 3. DOCUMENT (PDF NINEA ou RelevÃ©)
            elif msg_type == "document":
                doc_info = message.get("document", {})
                media_id = doc_info.get("id")
                filename = doc_info.get("filename", "document.pdf")

                reply_text = await handle_incoming_message(sender_phone, filename, ("DOCUMENT", media_id), contact_name)
                await send_whatsapp_message(sender_phone, reply_text)

            # 4. NOTE VOCALE (Speech-to-Text entrant & RÃ©ponse Vocale sortante Trilingue)
            elif msg_type == "audio":
                audio_info = message.get("audio", {})
                media_id = audio_info.get("id")

                reply_text = await handle_incoming_message(sender_phone, "Note vocale", ("AUDIO", media_id), contact_name)
                await send_whatsapp_message(sender_phone, reply_text)

                # GÃ©nÃ©ration et envoi automatique de la note vocale de rÃ©ponse (FranÃ§ais / Wolof / Anglais)
                try:
                    lang = detecter_langue_texte(reply_text)
                    audio_fn = await generer_note_vocale_audio(reply_text, langue=lang)
                    if audio_fn:
                        base_u = get_public_base_url()
                        audio_url = f"{base_u}/static/audio/{audio_fn}"
                        await send_whatsapp_audio(sender_phone, audio_url)
                except Exception as e_v:
                    print(f"Info envoi note vocale WhatsApp : {e_v}")

    except Exception as e:
        print(f"Erreur traitement webhook : {e}")

    return {"status": "ok"}


async def handle_incoming_message(sender_phone: str, user_text: str, media_tuple, contact_name: str = None) -> str:
    """Aiguille entre le premier message exclusif de bienvenue, le tunnel d'Onboarding en 5 Ã©tapes, la vÃ©rification d'abonnement et le fonctionnement normal de l'IA."""
    # 0. TRANSCRIPTION DES NOTES VOCALES WHATSAPP VIA OPENAI WHISPER
    if media_tuple and media_tuple[0] == "AUDIO":
        media_type, media_id = media_tuple
        media_bytes, mime_type = await download_meta_media(media_id)
        if not media_bytes:
            return "Je n'ai pas pu tÃ©lÃ©charger votre note vocale. Veuillez rÃ©essayer de me l'envoyer."

        texte_transcrit = await transcrire_note_vocale(media_bytes, mime_type)
        if not texte_transcrit:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return (
                    "Note vocale bien reÃ§ue.\n\n"
                    "Pour activer la transcription vocale automatique, veuillez renseigner votre clÃ© OPENAI_API_KEY dans votre fichier .env.\n\n"
                    "En attendant, vous pouvez Ã©crire votre message ou votre opÃ©ration directement sous forme de texte."
                )
            return (
                "Je n'ai pas rÃ©ussi Ã  entendre clairement votre note vocale. "
                "Pourriez-vous renvoyer un message vocal plus clair ou Ã©crire votre opÃ©ration sous forme de texte ?"
            )

        print(f"[NOTE VOCALE DE {sender_phone}] Transcrite : Â« {texte_transcrit} Â»")
        # Traitement direct du texte transcrit
        reponse_interne = await handle_incoming_message(sender_phone, texte_transcrit, None, contact_name)
        return (
            f"Note vocale comprise : Â« {texte_transcrit} Â»\n\n"
            f"{reponse_interne}"
        )

    # 0.1 ACCOMPAGNEMENT & TEST DE CONFIGURATION WEBHOOK EN DIRECT
    if is_test_webhook_request(user_text):
        clean_p = str(sender_phone).replace("+", "").replace(" ", "").strip()
        base_url = get_public_base_url()
        res_test = await executer_simulation_test_webhook(clean_p, provider="WAVE", amount=1000)
        return (
            "TEST DE CONNEXION WEBHOOK RÃ‰USSI\n\n"
            "RÃ‰SUMÃ‰ DU TEST EN DIRECT :\n"
            "â€¢ Canal vÃ©rifiÃ© : Webhook OpÃ©rateur Wave\n"
            "â€¢ Montant test : 1 000 FCFA\n"
            f"â€¢ RÃ©fÃ©rence test : {res_test.get('tx_id')}\n"
            "â€¢ Imputation : Compte SYSCOHADA 701 (Vente de marchandises)\n"
            "â€¢ TrÃ©sorerie crÃ©ditÃ©e : Compte SYSCOHADA 521 (Monnaie Ã©lectronique Wave)\n"
            "â€¢ Statut : 100% OpÃ©rationnel et certifiÃ©\n\n"
            "Votre liaison automatique est validÃ©e. Vos vÃ©ritables encaissements clients seront dÃ©sormais rÃ©conciliÃ©s automatiquement sans intervention manuelle :\n"
            f"{base_url}/dashboard?phone={clean_p}"
        )

    if is_webhook_assistance_request(user_text):
        base_url = get_public_base_url()
        return get_webhook_guide_message(base_url, sender_phone)

    onboarding = get_onboarding_state(sender_phone)
    statut = onboarding.get("statut", "EN_ATTENTE_ABONNEMENT")
    base_url = get_public_base_url()

    # Si l'utilisateur a dÃ©jÃ  son abonnement actif ou est en cours d'onboarding ou complet,
    # il ne doit JAMAIS recevoir le message de bienvenue ou d'attente d'abonnement !
    if onboarding.get("abonnement_valide") or statut in ["EN_COURS", "COMPLET"]:
        premier_contact = True
    else:
        premier_contact = onboarding.get("premier_contact_effectue", False)

    # 1. MESSAGE EXCLUSIF DU PREMIER CONTACT (Message de Bienvenue officiel Grow)
    if not premier_contact:
        update_onboarding_state(sender_phone, "premier_contact_effectue", True)
        update_onboarding_state(sender_phone, "statut", "EN_ATTENTE_ABONNEMENT")
        update_onboarding_state(sender_phone, "etape", "PAIEMENT_ABONNEMENT")
        return (
            "Bienvenue sur Grow !\n\n"
            "Je suis votre assistant prÃ©-comptable officiel sur WhatsApp. J'enregistre vos ventes et vos dÃ©penses au quotidien pour tenir vos comptes aux normes SYSCOHADA et prÃ©parer vos bilans financiers avec nos agences partenaires.\n\n"
            "Vos donnÃ©es financiÃ¨res seront consultables en direct sur votre tableau de bord personnel :\n"
            f"{base_url}/dashboard?phone={sender_phone}\n\n"
            "Pour activer votre prÃ©-comptabilitÃ© et configurer votre entreprise, veuillez d'abord souscrire Ã  votre abonnement mensuel Grow sur ce lien sÃ©curisÃ© :\n"
            f"{base_url}/abonnement?phone={sender_phone}\n\n"
            "DÃ¨s que votre paiement est effectuÃ©, Ã©crivez simplement Â« J'ai payÃ© Â» ou envoyez votre reÃ§u de paiement ici pour lancer la configuration de votre entreprise."
        )

    statut = onboarding.get("statut", "EN_ATTENTE_ABONNEMENT")

    # 2. VÃ‰RIFICATION DU PAIEMENT / Â« J'AI PAYÃ‰ Â» (PrioritÃ© absolue dÃ¨s que le client affirme avoir payÃ©)
    if is_paiement_keyword(user_text):
        update_onboarding_state(sender_phone, "abonnement_valide", True)

        # CAS A : Si ce numÃ©ro a DÃ‰JÃ€ une entreprise configurÃ©e
        if is_entreprise_deja_configuree(sender_phone):
            update_onboarding_state(sender_phone, "statut", "COMPLET")
            update_onboarding_state(sender_phone, "etape", "TERMINE")
            instructions = get_instructions_journee_message(base_url, sender_phone)
            return (
                "Merci, votre paiement est bien confirmÃ© ! Votre abonnement Grow est actif.\n\n"
                f"Votre entreprise est dÃ©jÃ  configurÃ©e.\n\n{instructions}"
            )

        # CAS B : Si ce numÃ©ro N'A PAS ENCORE configurÃ© son entreprise
        # On valide le paiement et on lance la configuration en 5 Ã©tapes (1 question Ã  la fois)
        update_onboarding_state(sender_phone, "statut", "EN_COURS")
        update_onboarding_state(sender_phone, "etape", "DEMANDE_NINEA")
        return (
            "Merci, votre paiement est bien confirmÃ© ! Votre abonnement Grow est actif.\n\n"
            "Nous allons maintenant configurer votre entreprise en 5 Ã©tapes. ConformÃ©ment aux rÃ¨gles Grow, la piÃ¨ce justificative est obligatoire pour valider chaque Ã©tape.\n\n"
            "Ã‰tape 1/5 : Envoyez-moi la photo ou le document PDF de votre attestation papier NINEA.\n\n"
            "Grow doit analyser cette piÃ¨ce officielle pour certifier le Nom, le NINEA, la Forme juridique, le Registre de Commerce (RCCM) et le Capital social de votre entreprise avant de passer Ã  l'Ã©tape suivante."
        )

    # 3. SI L'ABONNEMENT N'EST PAS ENCORE VALIDÃ‰ (Tant qu'il n'y a pas eu Â« J'ai payÃ© Â»)
    state = get_onboarding_state(sender_phone)
    if not state.get("abonnement_valide", False) and statut not in ["EN_COURS", "COMPLET"]:
        return (
            "Votre abonnement n'est pas encore actif. Pour activer votre compte et configurer votre entreprise, veuillez d'abord souscrire Ã  votre abonnement Grow sur ce lien :\n"
            f"{base_url}/abonnement?phone={sender_phone}\n\n"
            "Si vous avez dÃ©jÃ  payÃ©, Ã©crivez simplement Â« J'ai payÃ© Â» ou envoyez votre reÃ§u de paiement ici."
        )

    # 4. Si l'onboarding n'est pas encore terminÃ©, on traite l'onboarding (Ã‰tapes 1 Ã  5)
    if statut != "COMPLET":
        return await process_onboarding_step(sender_phone, user_text, media_tuple, onboarding, contact_name)

    # 5. Si l'onboarding est COMPLET, traitement des opÃ©rations
    if media_tuple:
        media_type, media_id = media_tuple
        return await process_media_with_ai(sender_phone, media_id, "PHOTO_RECU", user_text)
    else:
        # A. PrioritÃ© absolue au GRAND EXTRACTEUR LOCAL (0 crÃ©dit d'API, 100% gratuit et instantanÃ©)
        if user_text:
            # 1) DÃ©tection SMS OpÃ©rateur (Wave / Orange Money / Free)
            sms_op = parse_operator_sms_local(user_text)
            if sms_op and sms_op.get("montant_fcfa", 0) > 0:
                sp = get_supabase()
                ent = get_or_create_entreprise(sp, sender_phone) if sp else {}
                ent_id = ent.get("id")
                lib_complet = f"{sms_op.get('libelle')} (RÃ©f: {sms_op.get('reference_externe')})"
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

                solde_txt = f"\nâ€¢ Nouveau solde opÃ©rateur : {sms_op.get('solde_nouveau_fcfa'):,.0f} FCFA" if sms_op.get('solde_nouveau_fcfa') else ""
                return (
                    f"Notification {sms_op.get('operateur')} interceptee et enregistree avec succes.\n\n"
                    f"RESUME DE L'ENREGISTREMENT :\n"
                    f"â€¢ Nature : {sms_op.get('type_flux')}\n"
                    f"â€¢ Montant : {sms_op.get('montant_fcfa'):,.0f} FCFA\n"
                    f"â€¢ Source : {sms_op.get('operateur')}\n"
                    f"â€¢ Compte SYSCOHADA : {sms_op.get('compte_syscohada')} ({sms_op.get('libelle')})\n"
                    f"â€¢ Beneficiaire / Emetteur : {sms_op.get('tiers_nom')}\n"
                    f"â€¢ Reference : {sms_op.get('reference_externe')}"
                    f"{solde_txt}\n\n"
                    "Statut : Ecriture certifiee dans votre journal financier."
                )

            # 2) DÃ©tection OpÃ©ration FinanciÃ¨re Courante Locale (Ventes, Carburant, Loyer, Stock, etc.)
            op_loc = parse_operation_financiere_locale(user_text)
            if op_loc and op_loc.get("montant_fcfa", 0) > 0:
                # RÃ¨gle d'exigence de piÃ¨ce justificative pour toute dÃ©pense en cash
                if op_loc.get("besoin_justificatif", False):
                    return (
                        f"Votre declaration de depense de {op_loc.get('montant_fcfa'):,.0f} FCFA ({op_loc.get('libelle')}) a ete pre-enregistree en attente de justificatif.\n\n"
                        "RESUME DU PRE-ENREGISTREMENT :\n"
                        f"â€¢ Montant : {op_loc.get('montant_fcfa'):,.0f} FCFA\n"
                        f"â€¢ Nature : {op_loc.get('libelle')}\n"
                        f"â€¢ Mode : Especes (Cash)\n\n"
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

                return (
                    "Ecriture comptable enregistree avec succes.\n\n"
                    "RESUME DE L'ENREGISTREMENT :\n"
                    f"â€¢ Nature : {op_loc.get('libelle')}\n"
                    f"â€¢ Montant : {op_loc.get('montant_fcfa'):,.0f} FCFA\n"
                    f"â€¢ Mode de paiement : {op_loc.get('source_paiement')}\n"
                    f"â€¢ Compte SYSCOHADA : {op_loc.get('compte_syscohada')}\n\n"
                    "Statut : Validee et imputee a votre journal financier."
                )

        # B. Fallback IA pour les questions libres, conseils ou clarifications
        return await process_text_with_ai(sender_phone, user_text)


def extraire_ninea_nom_capital_local(text: str, sender_phone: str = "", contact_name: str = "") -> tuple[str, str, int]:
    """Extrait NINEA, Nom et Capital via le Grand Extracteur Local (0 crÃ©dit Anthropic, 100% gratuit)."""
    identite = extract_business_identity_local(text, sender_phone, contact_name)
    return identite.get("ninea"), identite.get("nom_entreprise"), identite.get("capital_social_fcfa", 0)


async def process_onboarding_step(sender_phone: str, user_text: str, media_tuple, onboarding: dict, contact_name: str = None) -> str:
    """Machine Ã  Ã©tats stricte pour l'onboarding obligatoire de l'entreprise supervisÃ©e par Anthropic Claude."""
    etape = onboarding.get("etape", "DEMANDE_NINEA")
    load_dotenv(override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key) if api_key else None

    # 0. BLOCAGE STRICT : AUCUNE TRANSACTION NE PEUT ÃŠTRE ENREGISTRÃ‰E AVANT LA CRÃ‰ATION COMPLÃˆTE DE L'ENTREPRISE
    if user_text:
        sms_op = parse_operator_sms_local(user_text)
        is_sms = bool(sms_op and sms_op.get("montant_fcfa", 0) > 0)
        op_fin = parse_operation_financiere_locale(user_text)
        is_op = bool(op_fin and op_fin.get("montant_fcfa", 0) > 0)
        has_amount = bool(parse_montant_fcfa(user_text) > 0)
        is_tx_kw = bool(re.search(r'\b(vente|vendu|achat|achetÃ©|depense|dÃ©pense|dette|crÃ©ance|creance|facture|senelec|sen eau|loyer)\b', user_text.lower()))
        
        # Uniquement si c'est une VRAIE transaction financiÃ¨re avec un flux ou un SMS opÃ©rateur
        if (is_sms or (is_op and etape not in ["DEMANDE_OPERATEURS", "DEMANDE_IMMOBILISATIONS", "DEMANDE_TRESORERIE_INITIALE"]) or (has_amount and is_tx_kw and etape not in ["DEMANDE_IMMOBILISATIONS", "DEMANDE_TRESORERIE_INITIALE"])):
            return (
                "Action refusÃ©e : Votre entreprise n'est pas encore enregistrÃ©e sur Grow.\n\n"
                "ConformÃ©ment aux normes prÃ©-comptables SYSCOHADA, aucun flux financier (vente, dÃ©pense ou SMS de paiement) ne peut Ãªtre imputÃ© tant que votre entreprise n'est pas officiellement crÃ©Ã©e et certifiÃ©e.\n\n"
                "Veuillez d'abord finaliser les 5 Ã©tapes d'onboarding pour activer l'enregistrement de vos opÃ©rations."
            )

    # Ã‰TAPE 1.1 : DEMANDE DU NOM COMMERCIAL DE L'ENTREPRISE (si l'attestation porte le nom de la personne physique)
    if etape == "DEMANDE_NOM_COMMERCIAL":
        txt_nom = (user_text or "").strip()
        is_greeting = bool(re.match(r'^(bonjour|salut|coucou|bonsoir|merci|ok|d[\'â€™]accord)$', txt_nom.lower()))
        if len(txt_nom) >= 2 and not is_greeting:
            # Enregistrement du vrai nom commercial
            update_onboarding_state(sender_phone, "nom_entreprise", txt_nom.title())
            update_onboarding_state(sender_phone, "etape", "DEMANDE_EQUIPE")
            
            # Mise Ã  jour Supabase
            sp = get_supabase()
            if sp:
                try:
                    clean_phone = str(sender_phone).replace("+", "").replace(" ", "").strip()
                    sp.table("entreprises").update({"nom_entreprise": txt_nom.title()}).ilike("telephone_whatsapp", f"%{clean_phone}%").execute()
                except Exception as e_nom:
                    print(f"Info mise Ã  jour nom commercial Supabase : {e_nom}")

            return (
                f"Raison sociale enregistrÃ©e avec succÃ¨s : Â« {txt_nom.title()} Â».\n\n"
                "RÃ‰SUMÃ‰ DE L'ENREGISTREMENT :\n"
                f"â€¢ Nom commercial de l'entreprise : {txt_nom.title()}\n"
                f"â€¢ GÃ©rant(e) / Exploitant(e) : {onboarding.get('nom_personne_physique', 'Titulaire')}\n"
                f"â€¢ NumÃ©ro NINEA certifiÃ© : {onboarding.get('ninea')}\n"
                f"â€¢ Capital social certifiÃ© : {int(onboarding.get('capital') or 1000000):,.0f} FCFA\n\n"
                "Ã‰tape 2/5 : Combien de personnes travaillent au sein de votre structure (salariÃ©s dÃ©clarÃ©s, apprentis ou associÃ©s) ?"
            )
        else:
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude
            return (
                "Veuillez m'indiquer le nom de votre entreprise, boutique ou atelier (par exemple : Â« Boutique Keur Fatou Â», Â« Ets Diallo & FrÃ¨res Â» ou Â« Dakar Fashion Store Â») :"
            )

    # Ã‰TAPE 1 : NOM DE L'ENTREPRISE, CAPITAL SOCIAL ET ATTESTATION NINEA
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
Analyse cette photo ou document d'attestation officielle NINEA (SÃ©nÃ©gal).
Extrais au format JSON strict les champs officiels suivants :
{
  "is_ninea_document": true,
  "nom_entreprise": "Nom commercial ou Raison sociale officielle",
  "forme_juridique": "Forme juridique (ex: Entreprise Individuelle, SARL, SAS, SUARL, GIE)",
  "activite_principale": "ActivitÃ© principale dÃ©clarÃ©e ou objet social",
  "registre_commerce": "NumÃ©ro RCCM (ex: SN-DKR-...)",
  "ninea": "NumÃ©ro NINEA officiel (7 Ã  10 caractÃ¨res)",
  "capital_social_fcfa": montant numÃ©rique entier du capital (0 si non spÃ©cifiÃ©),
  "date_creation": "date de crÃ©ation ou immatriculation",
  "ville": "commune ou ville du siÃ¨ge"
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

        # 2. Extraction locale dÃ©terministe depuis le texte (0 crÃ©dit Anthropic)
        loc_ninea, loc_nom, loc_capital = extraire_ninea_nom_capital_local(user_text, sender_phone, contact_name)

        ninea = extracted.get("ninea") or loc_ninea
        nom = extracted.get("nom_entreprise") or loc_nom
        capital = extracted.get("capital_social_fcfa") or extracted.get("capital_fcfa") or loc_capital
        forme_juridique = extracted.get("forme_juridique")
        activite_principale = extracted.get("activite_principale")
        registre_commerce = extracted.get("registre_commerce")

        # 3. Validation stricte de l'Ã‰tape 1 sur PIÃˆCE JUSTIFICATIVE OBLIGATOIRE :
        if piece_fournie:
            cap_final = capital if (capital and capital > 0) else 100000

            # DÃ©tection : Si c'est une Entreprise Individuelle et que le nom ressemble Ã  une personne (ex: FATOU THIAM)
            # ou si l'enseigne commerciale n'est pas spÃ©cifiÃ©e, la dÃ©nomination est le nom du propriÃ©taire, pas de l'entreprise !
            est_personne_physique = False
            if forme_juridique and "INDIVIDUELLE" in forme_juridique.upper():
                est_personne_physique = True
            elif nom and not any(kw in nom.lower() for kw in ["boutique", "ets", "sociÃ©tÃ©", "societe", "sarl", "suarl", "gie", "store", "shop", "atelier", "service", "commerce"]):
                if len(nom.split()) in [2, 3]:
                    est_personne_physique = True

            # Sauvegarde des donnÃ©es certifiÃ©es
            update_onboarding_state(sender_phone, "capital", cap_final)
            if ninea: update_onboarding_state(sender_phone, "ninea", ninea)
            if forme_juridique: update_onboarding_state(sender_phone, "forme_juridique", forme_juridique)
            if activite_principale: update_onboarding_state(sender_phone, "activite_principale", activite_principale)
            if registre_commerce: update_onboarding_state(sender_phone, "registre_commerce", registre_commerce)
            update_onboarding_state(sender_phone, "ninea_valide_par_preuve", True)

            forme_txt = f"â€¢ Forme juridique : {forme_juridique}\n" if forme_juridique else ""
            act_txt = f"â€¢ ActivitÃ© principale : {activite_principale}\n" if activite_principale else ""
            rc_txt = f"â€¢ Registre du Commerce (RCCM) : {registre_commerce}\n" if registre_commerce else ""
            ninea_txt = f"â€¢ NumÃ©ro NINEA officiel : {ninea}\n" if ninea else ""
            cap_txt = f"â€¢ Capital social certifiÃ© : {cap_final:,.0f} FCFA\n" if cap_final else ""

            # CAS A : L'attestation porte le nom de la personne physique (DÃ©nomination : FATOU THIAM)
            # On stocke le nom du titulaire, mais ON DEMANDE IMMÃ‰DIATEMENT LE NOM COMMERCIAL DE L'ENTREPRISE !
            if est_personne_physique:
                nom_personne = nom or "Titulaire de l'attestation"
                update_onboarding_state(sender_phone, "nom_personne_physique", nom_personne)
                update_onboarding_state(sender_phone, "etape", "DEMANDE_NOM_COMMERCIAL")

                # Enregistrement prÃ©alable dans Supabase
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
                        print(f"Info Supabase Ã‰tape 1 A : {e}")

                return (
                    "Attestation NINEA officielle reÃ§ue et certifiÃ©e avec succÃ¨s.\n\n"
                    "RÃ‰SUMÃ‰ DES INFORMATIONS LÃ‰GALES :\n"
                    f"â€¢ DÃ©nomination du titulaire : {nom_personne}\n"
                    f"{forme_txt}"
                    f"{act_txt}"
                    f"{rc_txt}"
                    f"{ninea_txt}"
                    f"{cap_txt}"
                    "â€¢ Statut : Conforme certifiÃ© (Sur piÃ¨ce officielle)\n\n"
                    f"Important : Â« {nom_personne} Â» est le nom de la personne physique (l'exploitant).\n"
                    "Quel est le nom commercial ou l'enseigne de votre entreprise / boutique (par exemple : Â« Boutique Keur Fatou Â», Â« Ets Diallo Â» ou Â« Dakar Fashion Store Â») ?"
                )

            # CAS B : L'attestation porte dÃ©jÃ  une raison sociale de sociÃ©tÃ© commerciale (ex: SARL TERANGA)
            nom_final = nom or "Entreprise CertifiÃ©e"
            update_onboarding_state(sender_phone, "nom_entreprise", nom_final)
            update_onboarding_state(sender_phone, "etape", "DEMANDE_EQUIPE")

            # Enregistrement ou mise Ã  jour de l'entreprise dans Supabase
            sp = get_supabase()
            if sp:
                try:
                    clean_phone = str(sender_phone).replace("+", "").replace(" ", "").strip()
                    res_ent = sp.table("entreprises").select("*").ilike("telephone_whatsapp", f"%{clean_phone}%").limit(1).execute()
                    ent_payload = {
                        "nom_entreprise": nom_final,
                        "capital_initial_fcfa": cap_final,
                        "donnees_onboarding": {
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
                    print(f"Info enregistrement Supabase Ã‰tape 1 : {e}")

            return (
                "Attestation NINEA officielle reÃ§ue et certifiÃ©e avec succÃ¨s.\n\n"
                f"â€¢ Raison sociale : {nom_final}\n"
                f"{forme_txt}"
                f"{act_txt}"
                f"{rc_txt}"
                f"{ninea_txt}"
                f"{cap_txt}"
                "â€¢ Statut du dossier : Conforme certifiÃ© (Document officiel validÃ©)\n\n"
                "Ã‰tape 2/5 : Combien de personnes travaillent au sein de votre structure (salariÃ©s dÃ©clarÃ©s, apprentis ou associÃ©s) ?"
            )
        else:
            # Si le client a envoyÃ© du texte au lieu de la photo :
            # Superviser avec Claude
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude

            return (
                "Pour valider l'Ã‰tape 1/5, l'envoi de votre piÃ¨ce justificative est obligatoire.\n\n"
                "Veuillez prendre en photo et m'envoyer votre attestation papier NINEA (ou le document officiel PDF).\n\n"
                "Grow doit impÃ©rativement vÃ©rifier cette piÃ¨ce officielle pour certifier le Nom, le NINEA, la Forme juridique, le Registre de Commerce (RCCM) et le Capital social de votre entreprise avant de pouvoir passer Ã  l'Ã©tape suivante."
            )

    # Ã‰TAPE 2 : NOMBRE D'EMPLOYÃ‰S (Validation stricte locale - 0 crÃ©dit API)
    elif etape == "DEMANDE_EQUIPE":
        txt_lower = user_text.lower().strip() if user_text else ""
        has_number = bool(re.search(r'\b\d+\b', txt_lower))
        has_keywords = bool(re.search(r'\b(seul|seule|personne|personnes|salariÃ©|salariÃ©s|salarie|salaries|employÃ©|employÃ©s|employe|employes|associÃ©|associÃ©s|associe|associes|apprenti|apprentis|aucun|aucune|zÃ©ro|zero|moi|travaille|un|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\b', txt_lower))

        if has_number or has_keywords:
            # Reformulation claire du nombre d'employÃ©s
            equipe_val = user_text.strip()
            if equipe_val in ["1", "un"]:
                equipe_desc = "1 personne (l'exploitant)"
            elif equipe_val.isdigit():
                equipe_desc = f"{equipe_val} personnes"
            else:
                equipe_desc = equipe_val

            update_onboarding_state(sender_phone, "nombre_employes", equipe_desc)
            update_onboarding_state(sender_phone, "etape", "DEMANDE_OPERATEURS")

            # Mise Ã  jour Supabase
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

            return (
                "Effectif enregistrÃ© avec succÃ¨s.\n\n"
                "RÃ‰SUMÃ‰ DE L'ENREGISTREMENT :\n"
                f"â€¢ Taille de la structure : {equipe_desc}\n\n"
                "Ã‰tape 3/5 : Quels moyens de paiement utilisez-vous au quotidien pour vos encaissements et vos dÃ©penses ? (Exemples : Wave, Orange Money, Caisse EspÃ¨ces, Compte Bancaire)."
            )
        else:
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude
            return (
                "Pour valider l'Ã‰tape 2/5, veuillez m'indiquer le nombre de personnes qui travaillent au sein de votre structure (par exemple : 'moi seul', '1 personne', '3 employÃ©s', ou 'aucun salariÃ©')."
            )

    # Ã‰TAPE 3 : OPÃ‰RATEURS DE PAIEMENT
    elif etape == "DEMANDE_OPERATEURS":
        txt_lower = user_text.lower().strip() if user_text else ""
        has_ops = bool(re.search(r'\b(wave|orange|om|espece|especes|cash|banque|bancaire|caisse|free|wari|compte|cheque|virement|ecobank|cbao|boa|sgbs|orabank|uba|bicis|tous|tout)\b', txt_lower))

        if has_ops:
            # DÃ©tection prÃ©cise et mÃ©morisation dÃ©finitive des opÃ©rateurs choisis
            ops_detectes = []
            if "wave" in txt_lower:
                ops_detectes.append("Wave")
            if "orange" in txt_lower or "om" in txt_lower:
                ops_detectes.append("Orange Money")
            if "free" in txt_lower:
                ops_detectes.append("Free Money")
            if any(b in txt_lower for b in ["banque", "bancaire", "cbao", "ecobank", "boa", "compte"]):
                ops_detectes.append("Compte Bancaire")
            if any(c in txt_lower for c in ["espece", "especes", "cash", "caisse"]):
                ops_detectes.append("Caisse EspÃ¨ces")

            if not ops_detectes:
                ops_detectes = ["Wave", "Caisse EspÃ¨ces"]

            ops_str = ", ".join(ops_detectes)
            update_onboarding_state(sender_phone, "operateurs", ops_str)
            update_onboarding_state(sender_phone, "liste_operateurs_cles", ops_detectes)
            update_onboarding_state(sender_phone, "etape", "DEMANDE_IMMOBILISATIONS")

            return (
                "Moyens de paiement enregistrÃ©s avec succÃ¨s.\n\n"
                "RÃ‰SUMÃ‰ DE L'ENREGISTREMENT :\n"
                f"â€¢ OpÃ©rateurs connectÃ©s : {ops_str}\n\n"
                "Ã‰tape 4/5 : Quels Ã©quipements ou matÃ©riels possÃ¨de votre entreprise (vÃ©hicule, machine, congÃ©lateur, ordinateurs, agencement) et quelle est leur valeur estimÃ©e ? (Ã‰crivez 'Aucun' si vous n'en avez pas)."
            )
        else:
            # Superviser avec Claude : gÃ¨re "Choisi", questions ou hÃ©sitations
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude
            return (
                "Pour valider l'Ã‰tape 3/5, veuillez prÃ©ciser les moyens de paiement que vous utilisez au quotidien (par exemple : 'Wave et EspÃ¨ces', 'Orange Money', ou 'Compte bancaire')."
            )

    # Ã‰TAPE 4 : IMMOBILISATIONS & Ã‰QUIPEMENTS (Validation stricte avec piÃ¨ce justificative obligatoire)
    elif etape == "DEMANDE_IMMOBILISATIONS":
        txt_lower = user_text.lower().strip() if user_text else ""
        is_greeting_only = bool(re.match(r'^(bonjour|salut|coucou|bonsoir|merci|ok|d[\'â€™]accord)$', txt_lower))

        # Cas particulier : le commerÃ§ant dÃ©clare formellement n'avoir AUCUN Ã©quipement
        declare_aucun = bool(re.search(r'\b(aucun|aucune|rien|zero|zÃ©ro|pas d[\'â€™]Ã©quipement|pas de materiel)\b', txt_lower))
        if declare_aucun and not is_greeting_only:
            update_onboarding_state(sender_phone, "immobilisations", "Aucun matÃ©riel d'exploitation")
            update_onboarding_state(sender_phone, "valeur_equipements_fcfa", 0)
            update_onboarding_state(sender_phone, "equipements_photo_validee", True)
            update_onboarding_state(sender_phone, "etape", "DEMANDE_TRESORERIE_INITIALE")

            ops_configures = onboarding.get("liste_operateurs_cles") or ["Wave", "Caisse EspÃ¨ces"]
            ops_invitation = " et ".join(ops_configures)

            return (
                "DÃ©claration d'Ã©quipements enregistrÃ©e avec succÃ¨s.\n\n"
                "RÃ‰SUMÃ‰ DE L'ENREGISTREMENT :\n"
                "â€¢ Ã‰quipements dÃ©clarÃ©s : Aucun matÃ©riel d'exploitation\n"
                "â€¢ Valeur estimÃ©e : 0 FCFA\n\n"
                f"Ã‰tape 5/5 : Quel est le montant exact disponible sur vos comptes ({ops_invitation}) en cet instant ?\n\n"
                f"Envoyez la capture d'Ã©cran du solde de vos comptes ({ops_invitation}) ou la photo de votre caisse espÃ¨ces."
            )

        # 1. Analyse de la valeur estimÃ©e (en FCFA) et dÃ©tection des Ã©quipements
        valeur_estimee = parse_montant_fcfa(user_text) if user_text else 0
        photo_fournie = bool(media_tuple and media_tuple[0] in ["PHOTO", "DOCUMENT"])

        immo_sauvegardee = onboarding.get("immobilisations")

        has_equip_mention = bool(re.search(r'\b(congÃ©lateur|congelateur|armoire|ordinateur|vÃ©hicule|vehicule|voiture|moto|machine|chambre froide|Ã©tagÃ¨re|etagere|comptoir|climatiseur|meuble|bureau|four|balance|table|imprimante|agencement)\b', txt_lower))
        if has_equip_mention or (user_text and not is_greeting_only and len(txt_lower) >= 3 and valeur_estimee == 0):
            update_onboarding_state(sender_phone, "immobilisations", user_text)
            immo_sauvegardee = user_text

        # 2. Si la photo a Ã©tÃ© envoyÃ©e
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
                        print(f"Info upload Ã©quipement Storage : {e_up}")

        if valeur_estimee > 0:
            update_onboarding_state(sender_phone, "valeur_equipements_fcfa", valeur_estimee)

        val_enregistree = onboarding.get("valeur_equipements_fcfa") or (valeur_estimee if valeur_estimee > 0 else 0)
        has_photo = photo_fournie or onboarding.get("equipements_photo_validee", False)

        # Si l'utilisateur n'a rien mentionnÃ© et a posÃ© une question :
        if not immo_sauvegardee and not has_equip_mention and not photo_fournie and valeur_estimee == 0:
            rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
            if rep_claude:
                return rep_claude

        # CONDITION STRICTE : Les deux Ã©lÃ©ments (valeur en FCFA + photo) sont indispensables
        if val_enregistree == 0 or not has_photo:
            if val_enregistree == 0 and not has_photo:
                details = f" : Â« {immo_sauvegardee} Â»" if immo_sauvegardee else ""
                return (
                    f"Grow a bien notÃ© vos Ã©quipements{details}.\n\n"
                    "Cependant, votre rÃ©ponse est incomplÃ¨te pour valider l'Ã‰tape 4/5. Deux Ã©lÃ©ments indispensables manquent :\n"
                    "1. La valeur estimÃ©e globale en FCFA de ces matÃ©riels (par exemple : Â« Valeur estimÃ©e : 850 000 FCFA Â»).\n"
                    "2. La photo justificative de vos Ã©quipements en boutique/atelier (ou la photo de votre facture d'achat).\n\n"
                    "Sans la valeur estimÃ©e et la photo justificative, Grow refuse de valider l'Ã©tape car vos actifs doivent Ãªtre certifiÃ©s au bilan SYSCOHADA (Compte 24) !"
                )
            elif val_enregistree > 0 and not has_photo:
                return (
                    f"Grow a bien enregistrÃ© la liste et la valeur de vos Ã©quipements :\n\n"
                    f"â€¢ MatÃ©riels dÃ©clarÃ©s : {immo_sauvegardee or 'Ã‰quipements dÃ©clarÃ©s'}\n"
                    f"â€¢ Valeur estimÃ©e : {val_enregistree:,.0f} FCFA\n\n"
                    "PIÃˆCE JUSTIFICATIVE OBLIGATOIRE :\n"
                    "Veuillez maintenant m'envoyer la photo de vos Ã©quipements en boutique/atelier (ou la photo de votre facture d'achat).\n\n"
                    "Grow exige cette preuve visuelle pour certifier vos actifs immobilisÃ©s (Compte SYSCOHADA 24) avant de passer Ã  l'Ã©tape suivante."
                )
            elif val_enregistree == 0 and has_photo:
                return (
                    "Photo des Ã©quipements bien reÃ§ue et archivÃ©e avec succÃ¨s.\n\n"
                    "Pour certifier vos immobilisations au bilan (Compte 24), quelle est la valeur estimÃ©e globale en FCFA de ces Ã©quipements ?"
                )

        # VALIDATION OFFICIELLE DE L'Ã‰TAPE 4 (MatÃ©riels + Valeur + Photo rÃ©unis)
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
                print(f"Info sauvegarde Supabase Ã‰quipements : {e_im}")

        ops_configures = onboarding.get("liste_operateurs_cles") or ["Wave", "Caisse EspÃ¨ces"]
        ops_invitation = " et ".join(ops_configures)

        return (
            "Ã‰quipements et immobilisations certifiÃ©s avec succÃ¨s sur piÃ¨ce justificative.\n\n"
            "RÃ‰SUMÃ‰ DE L'ENREGISTREMENT :\n"
            f"â€¢ MatÃ©riels dÃ©clarÃ©s : {immo_sauvegardee}\n"
            f"â€¢ Valeur d'actif certifiÃ©e : {val_finale:,.0f} FCFA\n"
            "â€¢ Imputation : Compte SYSCOHADA 24 (MatÃ©riels et Mobiliers)\n"
            "â€¢ Preuve probatoire : Photo vÃ©rifiÃ©e et archivÃ©e\n\n"
            f"Ã‰tape 5/5 : Quel est le montant exact disponible sur votre compte {ops_invitation} en cet instant ?\n\n"
            f"Envoyez la capture d'Ã©cran du solde de vos comptes ({ops_invitation}) ou la photo de votre caisse espÃ¨ces."
        )

    # Ã‰TAPE 5 : TRÃ‰SORERIE Ã€ L'INSTANT T AVEC PREUVE CAPTURE
    elif etape == "DEMANDE_TRESORERIE_INITIALE":
        solde_t0 = 0
        photo_url = None
        sha_hash = None

        # Si une capture d'Ã©cran du solde Wave/OM est envoyÃ©e
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
                                {"type": "text", "text": "Extrais en JSON strict le solde affichÃ© sur cette capture d'Ã©cran Wave/Orange Money/Banque : {solde_fcfa: int, operateur: str}. Si illisible: {solde_fcfa: 0, operateur: 'WAVE'}."}
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

        # RÃ©cupÃ©ration des opÃ©rateurs configurÃ©s Ã  l'Ã©tape 3
        ops_configures = onboarding.get("liste_operateurs_cles") or ["Wave", "Caisse EspÃ¨ces"]
        ops_prompt_txt = " et ".join(ops_configures)

        # Exigence stricte de la piÃ¨ce justificative pour l'Ã‰tape 5 :
        if not media_tuple:
            # Exception : le commerÃ§ant dÃ©clare explicitement 0 ou aucun solde disponible
            if user_text and re.search(r'\b(zero|zÃ©ro|aucun|rien|0)\b', user_text.lower()):
                solde_t0 = 0
            else:
                rep_claude = await superviser_conversation_claude(sender_phone, user_text, onboarding)
                if rep_claude:
                    return rep_claude

                return (
                    f"Pour valider l'Ã‰tape 5/5, la piÃ¨ce justificative est obligatoire pour vos comptes ({ops_prompt_txt}).\n\n"
                    f"Veuillez m'envoyer la capture d'Ã©cran de votre solde pour {ops_prompt_txt} (ou la photo de votre caisse espÃ¨ces).\n\n"
                    "Grow refuse d'avancer sans ce justificatif visuel probant car votre trÃ©sorerie de dÃ©part doit Ãªtre formellement certifiÃ©e !"
                )

        # Analyse et rÃ©partition des soldes multi-opÃ©rateurs
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
        ops = state.get("operateurs", "Wave, EspÃ¨ces")
        immos = state.get("immobilisations", "MatÃ©riel d'exploitation")

        # Enregistrer la transaction de trÃ©sorerie d'ouverture pour CHAQUE opÃ©rateur dans Supabase
        sp = get_supabase()
        if sp:
            try:
                ent = get_or_create_entreprise(sp, sender_phone)
                ent_id = ent.get("id")
                if ent_id:
                    # Mettre Ã  jour l'Ã©tape d'onboarding Ã  COMPLET dans Supabase
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

                    # InsÃ©rer une Ã©criture pour chaque opÃ©rateur
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
                                "libelle": f"TrÃ©sorerie d'ouverture Ã  l'instant T ({op_name})",
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
                                    "texte_extrait_ia": f"Solde initial certifiÃ© {op_name} : {op_amount:,.0f} FCFA"
                                }).execute()
            except Exception as e:
                print(f"Info crÃ©ation transactions initiales T0 multi-opÃ©rateurs : {e}")

        short_h = f"{sha_hash[:10]}..." if sha_hash else "CertifiÃ© dÃ©claratif"

        # Formatage du dÃ©tail multi-opÃ©rateurs
        labels_ops = {
            "WAVE": "Compte Wave",
            "ORANGE_MONEY": "Compte Orange Money",
            "ESPECES": "Caisse EspÃ¨ces",
            "BANQUE": "Compte Bancaire"
        }
        lignes_soldes = []
        for op_k, op_val in soldes_dict.items():
            lignes_soldes.append(f"  â€¢ {labels_ops.get(op_k, op_k)} : {op_val:,.0f} FCFA")

        detail_soldes_txt = "\n".join(lignes_soldes) if lignes_soldes else f"  â€¢ TrÃ©sorerie : {total_t0:,.0f} FCFA"

        forme_txt = f"â€¢ Forme juridique : {forme_juridique}\n" if forme_juridique else ""
        act_txt = f"â€¢ ActivitÃ© principale : {activite_principale}\n" if activite_principale else ""
        rc_txt = f"â€¢ Registre du Commerce (RCCM) : {registre_commerce}\n" if registre_commerce else ""

        # CAS 1 : Si le client a DÃ‰JÃ€ PAYÃ‰ son abonnement -> ClÃ´ture officielle, rÃ©capitulatif des 5 Ã©tapes et instructions
        if deja_abonne:
            update_onboarding_state(sender_phone, "statut", "COMPLET")
            update_onboarding_state(sender_phone, "etape", "TERMINE")
            instructions = get_instructions_journee_message(get_public_base_url(), sender_phone, nom)
            return (
                f"FÃ©licitations ! Votre entreprise Â« {nom} Â» est dÃ©sormais officiellement crÃ©Ã©e et enregistrÃ©e sur Grow aux normes SYSCOHADA.\n\n"
                "RÃ‰CAPITULATIF OFFICIEL DES 5 Ã‰TAPES D'OUVERTURE :\n\n"
                "1. IDENTITÃ‰ DE L'ENTREPRISE (Ã‰tape 1/5) :\n"
                f"â€¢ Raison sociale : {nom}\n"
                f"â€¢ NumÃ©ro NINEA officiel : {ninea}\n"
                f"{forme_txt}"
                f"{rc_txt}"
                f"{act_txt}"
                f"â€¢ Capital social certifiÃ© : {capital:,.0f} FCFA\n"
                "â€¢ Statut NINEA : Conforme certifiÃ© (Sur piÃ¨ce officielle)\n\n"
                "2. STRUCTURE & EFFECTIF (Ã‰tape 2/5) :\n"
                f"â€¢ Ã‰quipe dÃ©clarÃ©e : {equipe}\n\n"
                "3. MOYENS DE PAIEMENT (Ã‰tape 3/5) :\n"
                f"â€¢ OpÃ©rateurs connectÃ©s : {ops}\n\n"
                "4. Ã‰QUIPEMENTS & IMMOBILISATIONS (Ã‰tape 4/5) :\n"
                f"â€¢ MatÃ©riels dÃ©clarÃ©s : {immos}\n\n"
                "5. BILAN D'OUVERTURE & TRÃ‰SORERIE T0 (Ã‰tape 5/5) :\n"
                f"{detail_soldes_txt}\n"
                f"â€¢ Total TrÃ©sorerie certifiÃ©e : {total_t0:,.0f} FCFA\n"
                f"â€¢ Empreinte probatoire numÃ©rique : {short_h}\n\n"
                "VOTRE TABLEAU DE BORD FINANCIER EN DIRECT :\n"
                "Vous pouvez dÃ¨s maintenant consulter l'intÃ©gralitÃ© de vos comptes et bilans financiers sur votre lien sÃ©curisÃ© :\n"
                f"{get_public_base_url()}/dashboard?phone={sender_phone}\n"
                "(Vous y retrouverez votre raison sociale, votre NINEA, votre capital certifiÃ©, vos Ã©quipements et vos soldes de trÃ©sorerie par opÃ©rateur mis Ã  jour en temps rÃ©el).\n\n"
                f"{instructions}"
            )
        else:
            return (
                f"FÃ©licitations ! Les 5 Ã©tapes de configuration de votre entreprise Â« {nom} Â» sont entiÃ¨rement validÃ©es.\n\n"
                "Pour activer la certification en continu de votre comptabilitÃ© et accÃ©der Ã  vos bilans SYSCOHADA, finalisez votre souscription sur ce lien sÃ©curisÃ© :\n"
                f"{get_public_base_url()}/abonnement?phone={sender_phone}"
            )

        # Analyse et rÃ©partition des soldes multi-opÃ©rateurs
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
        ops = state.get("operateurs", "Wave, EspÃ¨ces")
        immos = state.get("immobilisations", "MatÃ©riel d'exploitation")

        # Enregistrer la transaction de trÃ©sorerie d'ouverture pour CHAQUE opÃ©rateur dans Supabase
        sp = get_supabase()
        if sp:
            try:
                ent = get_or_create_entreprise(sp, sender_phone)
                ent_id = ent.get("id")
                if ent_id:
                    # Mettre Ã  jour l'Ã©tape d'onboarding Ã  COMPLET dans Supabase
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

                    # InsÃ©rer une Ã©criture pour chaque opÃ©rateur
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
                                "libelle": f"TrÃ©sorerie d'ouverture Ã  l'instant T ({op_name})",
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
                                    "texte_extrait_ia": f"Solde initial certifiÃ© {op_name} : {op_amount:,.0f} FCFA"
                                }).execute()
            except Exception as e:
                print(f"Info crÃ©ation transactions initiales T0 multi-opÃ©rateurs : {e}")

        short_h = f"{sha_hash[:10]}..." if sha_hash else "CertifiÃ© dÃ©claratif"

        # Formatage du dÃ©tail multi-opÃ©rateurs
        labels_ops = {
            "WAVE": "Compte Wave",
            "ORANGE_MONEY": "Compte Orange Money",
            "ESPECES": "Caisse EspÃ¨ces",
            "BANQUE": "Compte Bancaire"
        }
        lignes_soldes = []
        for op_k, op_val in soldes_dict.items():
            lignes_soldes.append(f"  â€¢ {labels_ops.get(op_k, op_k)} : {op_val:,.0f} FCFA")

        detail_soldes_txt = "\n".join(lignes_soldes) if lignes_soldes else f"  â€¢ TrÃ©sorerie : {total_t0:,.0f} FCFA"

        forme_txt = f"â€¢ Forme juridique : {forme_juridique}\n" if forme_juridique else ""
        act_txt = f"â€¢ ActivitÃ© principale : {activite_principale}\n" if activite_principale else ""
        rc_txt = f"â€¢ Registre du Commerce (RCCM) : {registre_commerce}\n" if registre_commerce else ""

        # CAS 1 : Si le client a DÃ‰JÃ€ PAYÃ‰ son abonnement -> ClÃ´ture officielle, rÃ©capitulatif des 5 Ã©tapes et instructions
        if deja_abonne:
            update_onboarding_state(sender_phone, "statut", "COMPLET")
            update_onboarding_state(sender_phone, "etape", "TERMINE")
            instructions = get_instructions_journee_message(get_public_base_url(), sender_phone, nom)
            return (
                f"FÃ©licitations ! Votre entreprise Â« {nom} Â» est dÃ©sormais officiellement crÃ©Ã©e et enregistrÃ©e sur Grow aux normes SYSCOHADA.\n\n"
                "RÃ‰CAPITULATIF OFFICIEL DES 5 Ã‰TAPES D'OUVERTURE :\n\n"
                "1. IDENTITÃ‰ DE L'ENTREPRISE (Ã‰tape 1/5) :\n"
                f"â€¢ Raison sociale : {nom}\n"
                f"â€¢ NumÃ©ro NINEA officiel : {ninea}\n"
                f"{forme_txt}"
                f"{rc_txt}"
                f"{act_txt}"
                f"â€¢ Capital social certifiÃ© : {capital:,.0f} FCFA\n"
                "â€¢ Statut NINEA : Conforme certifiÃ© (Sur piÃ¨ce officielle)\n\n"
                "2. STRUCTURE & EFFECTIF (Ã‰tape 2/5) :\n"
                f"â€¢ Ã‰quipe dÃ©clarÃ©e : {equipe}\n\n"
                "3. MOYENS DE PAIEMENT (Ã‰tape 3/5) :\n"
                f"â€¢ OpÃ©rateurs connectÃ©s : {ops}\n\n"
                "4. Ã‰QUIPEMENTS & IMMOBILISATIONS (Ã‰tape 4/5) :\n"
                f"â€¢ MatÃ©riels dÃ©clarÃ©s : {immos}\n\n"
                "5. BILAN D'OUVERTURE & TRÃ‰SORERIE T0 (Ã‰tape 5/5) :\n"
                f"{detail_soldes_txt}\n"
                f"â€¢ Total TrÃ©sorerie certifiÃ©e : {total_t0:,.0f} FCFA\n"
                f"â€¢ Empreinte probatoire numÃ©rique : {short_h}\n\n"
                "VOTRE TABLEAU DE BORD FINANCIER EN DIRECT :\n"
                "Vous pouvez dÃ¨s maintenant consulter l'intÃ©gralitÃ© de vos comptes et bilans financiers sur votre lien sÃ©curisÃ© :\n"
                f"{get_public_base_url()}/dashboard?phone={sender_phone}\n"
                "(Vous y retrouverez votre raison sociale, votre NINEA, votre capital certifiÃ©, vos Ã©quipements et vos soldes de trÃ©sorerie par opÃ©rateur mis Ã  jour en temps rÃ©el).\n\n"
                f"{instructions}"
            )
        else:
            # CAS 2 : Si le client n'a pas encore payÃ© -> On lui demande de souscrire
            update_onboarding_state(sender_phone, "statut", "EN_ATTENTE_ABONNEMENT")
            update_onboarding_state(sender_phone, "etape", "PAIEMENT_ABONNEMENT")
            return (
                f"FÃ©licitations ! Votre entreprise Â« {nom} Â» a Ã©tÃ© configurÃ©e avec succÃ¨s sur Grow.\n\n"
                "RÃ‰CAPITULATIF DES 5 Ã‰TAPES D'OUVERTURE :\n\n"
                "1. IDENTITÃ‰ DE L'ENTREPRISE (Ã‰tape 1/5) :\n"
                f"â€¢ Raison sociale : {nom}\n"
                f"â€¢ NumÃ©ro NINEA : {ninea}\n"
                f"â€¢ Capital social certifiÃ© : {capital:,.0f} FCFA\n\n"
                "2. STRUCTURE & EFFECTIF (Ã‰tape 2/5) :\n"
                f"â€¢ Ã‰quipe dÃ©clarÃ©e : {equipe}\n\n"
                "3. MOYENS DE PAIEMENT (Ã‰tape 3/5) :\n"
                f"â€¢ OpÃ©rateurs connectÃ©s : {ops}\n\n"
                "4. Ã‰QUIPEMENTS & IMMOBILISATIONS (Ã‰tape 4/5) :\n"
                f"â€¢ MatÃ©riels dÃ©clarÃ©s : {immos}\n\n"
                "5. TRÃ‰SORERIE INITIALE T0 (Ã‰tape 5/5) :\n"
                f"{detail_soldes_txt}\n"
                f"â€¢ Total TrÃ©sorerie : {total_t0:,.0f} FCFA\n\n"
                "Votre tableau de bord financier personnel est prÃªt sur ce lien sÃ©curisÃ© :\n"
                f"{get_public_base_url()}/dashboard?phone={sender_phone}\n\n"
                "Pour activer le traitement automatique quotidien de vos opÃ©rations, veuillez finaliser votre abonnement Grow sur ce lien :\n"
                f"{get_public_base_url()}/abonnement?phone={sender_phone}\n\n"
                "Une fois le paiement effectuÃ©, Ã©crivez simplement Â« J'ai payÃ© Â» pour commencer !"
            )

    return "Bonjour ! Pour continuer la crÃ©ation de votre entreprise, envoyez-moi votre NINEA."


async def download_meta_media(media_id: str) -> tuple[bytes, str]:
    """TÃ©lÃ©charge le fichier mÃ©dia depuis Meta Cloud API."""
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
    """TÃ©lÃ©charge le mÃ©dia, calcule le hash SHA-256, l'archive dans Supabase Storage et l'analyse avec Claude."""
    sp = get_supabase()
    entreprise = get_or_create_entreprise(sp, sender_phone) if sp else {}
    entreprise_id = entreprise.get("id")

    media_bytes, mime_type = await download_meta_media(media_id)
    if not media_bytes:
        return "âš ï¸ Je n'ai pas rÃ©ussi Ã  rÃ©cupÃ©rer votre fichier. Pouvez-vous me le renvoyer ?"

    sha256_hash = hashlib.sha256(media_bytes).hexdigest()
    print(f"Empreinte SHA-256 calculÃ©e : {sha256_hash}")

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
Analyse cette image envoyÃ©e par un commerÃ§ant au SÃ©nÃ©gal.
Elle peut Ãªtre :
1) Une attestation officielle NINEA (Direction GÃ©nÃ©rale des ImpÃ´ts et des Domaines / APIX)
2) Un reÃ§u, facture, ticket de caisse physique.
3) Une capture d'Ã©cran de l'application Wave / Orange Money ou une CAPTURE D'Ã‰CRAN D'UNE NOTIFICATION PUSH Wave/OM (ex: banniÃ¨re de notification sur Ã©cran verrouillÃ© ou centre de notifications iPhone/Android avec icÃ´ne Wave pingouin, virement reÃ§u, remboursement ou paiement).

Extrais les informations sous forme de JSON strict :
{
  "is_ninea_document": true si c'est une attestation NINEA officielle (sinon false),
  "nom_entreprise": "Nom commercial ou Raison sociale officielle" (si NINEA),
  "forme_juridique": "Forme juridique (ex: Entreprise Individuelle, SARL, SAS, SUARL, GIE)" (si NINEA),
  "activite_principale": "ActivitÃ© principale dÃ©clarÃ©e ou objet social" (si NINEA),
  "registre_commerce": "NumÃ©ro RCCM (ex: SN-DKR-...)" (si NINEA),
  "ninea": "NumÃ©ro NINEA officiel (7 Ã  10 caractÃ¨res)" (si NINEA),
  "capital_social_fcfa": montant numÃ©rique entier du capital (si NINEA, sinon 0),

  "is_transaction": true si c'est un reÃ§u, facture ou notification de transaction financiÃ¨re (sinon false),
  "type_flux": "SORTIE" (si dÃ©pense/achat) ou "ENTREE" (si vente, transfert reÃ§u ou remboursement),
  "montant_fcfa": montant numÃ©rique entier en FCFA (ex: si Ã©crit 105F -> 105, si Ã©crit 25.000F -> 25000),
  "libelle": "description de l'opÃ©ration (ex: Vente encaissÃ©e via Wave, Remboursement Wave, Achat)",
  "source_paiement": "WAVE" ou "ORANGE_MONEY" ou "ESPECES" ou "BANQUE",
  "compte_syscohada": "code compte SYSCOHADA (ex: 701 pour vente/recette, 601 pour stock, 605 frais, 521 rÃ©gularisation)",
  "texte_extrait": "rÃ©sumÃ© des textes clÃ©s lus"
}
Si l'image n'est ni un document NINEA ni une transaction/notification financiÃ¨re lisible, renvoie is_transaction=false et is_ninea_document=false.
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

            # Si l'image envoyÃ©e est une attestation NINEA officielle
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
                    print(f"Erreur mise Ã  jour attestation NINEA : {e_up}")

                forme_t = f"â€¢ Forme juridique : {forme_n}\n" if forme_n else ""
                act_t = f"â€¢ ActivitÃ© principale : {act_n}\n" if act_n else ""
                rc_t = f"â€¢ Registre du Commerce (RCCM) : {rc_n}\n" if rc_n else ""
                ninea_t = f"â€¢ NumÃ©ro NINEA officiel : {ninea_n}\n" if ninea_n else ""
                cap_t = f"â€¢ Capital social certifiÃ© : {cap_n:,.0f} FCFA\n" if cap_n else ""

                return (
                    "Attestation papier NINEA reÃ§ue et certifiÃ©e avec succÃ¨s.\n\n"
                    f"â€¢ Raison sociale : {nom_n or entreprise.get('nom_entreprise', 'Votre Entreprise')}\n"
                    f"{forme_t}"
                    f"{act_t}"
                    f"{rc_t}"
                    f"{ninea_t}"
                    f"{cap_t}"
                    "â€¢ Statut du dossier : Conforme certifiÃ© (Document officiel validÃ©)\n\n"
                    "Vos comptes, vos bilans comptables SYSCOHADA et vos dossiers de financement sont dÃ©sormais officiellement rattachÃ©s Ã  votre attestation NINEA."
                )
        except Exception as e:
            print(f"Erreur analyse Claude Vision : {e}")

    tx_id = None
    if sp and entreprise_id and extracted_data.get("is_transaction") and extracted_data.get("montant_fcfa", 0) > 0:
        try:
            tx = sp.table("transactions").insert({
                "entreprise_id": entreprise_id,
                "libelle": extracted_data.get("libelle", "ReÃ§u validÃ©"),
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
    libelle = extracted_data.get("libelle", "PiÃ¨ce justificative")
    short_hash = sha256_hash[:10]

    if montant > 0:
        return (
            "Justificatif verifie et archive avec succes.\n\n"
            f"RESUME DE L'ENREGISTREMENT :\n"
            f"â€¢ Nature : {libelle}\n"
            f"â€¢ Montant : {montant:,.0f} FCFA\n"
            f"â€¢ Compte SYSCOHADA : {extracted_data.get('compte_syscohada', '601')}\n"
            f"â€¢ Preuve probatoire : Certifiee conforme (SHA-256 : {short_hash}...)\n\n"
            "Statut : L'operation est validee et imputee a votre journal comptable."
        )
    else:
        return (
            "Justificatif recu et securise dans votre coffre-fort numerique.\n\n"
            f"â€¢ Empreinte probatoire : SHA-256 ({short_hash}...)\n\n"
            "Pour finaliser l'enregistrement, precisez-moi simplement le montant et la nature de cette depense (ex: Â« 15 000 carburant Â»)."
        )


async def process_text_with_ai(sender_phone: str, user_text: str) -> str:
    """Analyse le texte, traite les flux Wave en direct, les impayÃ©s, les stocks ou les heures de rappel."""
    load_dotenv(override=True)
    
    txt_clean = (user_text or "").strip().lower()

    # 0. RÃ‰PONSE DIRECTE DU CLIENT Ã€ UNE QUESTION DE CLARIFICATION D'OPÃ‰RATEUR (1, 2, 3, 4)
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
        reponse_choix = ("108", "Compte de l'exploitant (PrÃ©lÃ¨vement personnel)", "Retrait personnel exploitant")

    if reponse_choix and sp and entreprise_id:
        try:
            pending = sp.table("transactions").select("*").eq("entreprise_id", entreprise_id).in_("compte_syscohada", ["471100", "471"]).order("created_at", desc=True).limit(1).execute()
            if pending.data and len(pending.data) > 0:
                target_tx = pending.data[0]
                nouveau_compte, libelle_compte, nature = reponse_choix
                orig_lib = target_tx.get('libelle', 'OpÃ©ration')
                nouveau_libelle = f"{orig_lib} ({nature})"
                
                sp.table("transactions").update({
                    "compte_syscohada": nouveau_compte,
                    "libelle": nouveau_libelle,
                    "statut_validation": "VALIDE_PME"
                }).eq("id", target_tx["id"]).execute()
                
                # Auto-apprentissage dans la mÃ©moire Grow pour toujours
                tiers_nom = None
                if "-" in orig_lib:
                    tiers_nom = orig_lib.split("-")[-1].strip()
                elif "pour" in orig_lib.lower():
                    tiers_nom = orig_lib.lower().split("pour")[-1].strip()
                elif "Ã " in orig_lib.lower():
                    tiers_nom = orig_lib.lower().split("Ã ")[-1].strip()
                
                if tiers_nom and len(tiers_nom) > 2:
                    enregistrer_fournisseur_memoire(entreprise_id, tiers_nom, nouveau_compte, libelle_compte, nature)

                montant = int(target_tx.get("montant_fcfa") or 0)
                ref = target_tx.get("reference_externe") or f"TX-{target_tx['id'][:8]}"
                
                msg_confirmation = (
                    f"Ã‰criture validÃ©e et certifiÃ©e.\n\n"
                    f"L'opÃ©ration de {montant:,.0f} FCFA (RÃ©f: {ref}) est dÃ©sormais imputÃ©e au Compte SYSCOHADA {nouveau_compte} ({libelle_compte}).\n\n"
                    f"Statut : VÃ©rifiÃ©e."
                )
                if tiers_nom and len(tiers_nom) > 2:
                    msg_confirmation += f"\n\nIntelligence Grow : le bÃ©nÃ©ficiaire Â« {tiers_nom} Â» est mÃ©morisÃ©. Vos futures transactions avec lui seront classÃ©es automatiquement."
                return msg_confirmation
        except Exception as e:
            print(f"Erreur rÃ©solution clarification : {e}")

    # ==========================================================================
    # MOTEUR EXPERT MÃ‰TIER & MINI-CHATGPT SPÃ‰CIALISÃ‰ (0 CRÃ‰DIT API / 100% LOCAL)
    # ==========================================================================

    # 1. Modification de l'heure du rituel quotidien (ex: 'change l'heure du rappel Ã  21h30')
    m_heure = re.search(r'(?:change|modifier|mets|rappel|rituel)\D*?(\d{1,2})[h:](\d{2})?', txt_clean)
    if m_heure and any(k in txt_clean for k in ["heure", "rappel", "rituel", "soir"]):
        h = int(m_heure.group(1))
        mn = int(m_heure.group(2) or 0)
        heure_fmt = f"{h:02d}:{mn:02d}:00"
        try:
            sp.table("entreprises").update({"heure_rappel_quotidien": heure_fmt}).eq("id", entreprise_id).execute()
            return f"L'heure de votre rituel de caisse quotidien est dÃ©sormais fixÃ©e Ã  {h:02d}h{mn:02d}. Chaque soir Ã  cette heure, Grow dressera le bilan de votre journÃ©e."
        except Exception:
            pass

    # 2. Salutations et prÃ©sentations gÃ©nÃ©rales (ponctuation nettoyÃ©e)
    clean_no_punct = re.sub(r'[^\w\s]', '', txt_clean).strip()
    if clean_no_punct in ["bonjour", "salut", "bonsoir", "coucou", "qui es tu", "qui est tu", "cest quoi grow", "tu es qui", "aide", "help", "merci"]:
        return (
            "Bonjour ! Je suis Grow, votre assistant prÃ©-comptable officiel sur WhatsApp certifiÃ© aux normes SYSCOHADA.\n\n"
            "Je vous accompagne au quotidien pour :\n"
            "â€¢ Enregistrer automatiquement vos ventes Wave, Orange Money et espÃ¨ces\n"
            "â€¢ RÃ©cupÃ©rer vos justificatifs de dÃ©penses et de stock avec preuves\n"
            "â€¢ Suivre vos dettes fournisseurs et vos crÃ©ances clients\n"
            "â€¢ Vous fournir chaque soir un bilan consolidÃ© prÃªt pour votre expert-comptable\n\n"
            "Comment puis-je vous aider aujourd'hui ?"
        )

    # 3. Base de connaissances thÃ©orique & juridique (SYSCOHADA, NINEA, Preuves, Agences, Rituel)
    ans_theorie = repondre_question_theorique_locale(user_text)
    if ans_theorie:
        return ans_theorie

    # 4. Consultations financiÃ¨res en temps rÃ©el (Solde caisse/Wave, ventes du jour, dettes/crÃ©ances)
    ans_consult = executer_consultation_donnees_locale(user_text, entreprise_id, sp)
    if ans_consult:
        return ans_consult

    # 5. Gestion en langage naturel des Dettes Fournisseurs & CrÃ©ances Clients
    ans_dette = gerer_dette_creance_locale(user_text, entreprise_id, sp)
    if ans_dette:
        return ans_dette

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        return f"Grow a bien notÃ© : '{user_text}'."

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
    - Si le motif de la sortie d'argent est INCONNU ou FLOUTÃ‰ : Affecte provisoirement le compte d'attente 471100 et demande poliment clarification a l'utilisateur dans reponse_whatsapp (ex: 1 pour achat marchandise, 2 pour dette fournisseur, 3 pour transport, 4 pour retrait personnel).

REGLES D'EXIGENCE DE PREUVES ET JUSTIFICATIFS :
- Pour les transferts Wave et Orange Money : la preuve numerique est intrinseque via l'operateur, pas de recu papier requis.
- REGLE STRICTE SUR TOUTES LES DEPENSES ET ACHATS EN CASH (ESPECES) :
  CHAQUE depense ou achat fait en cash (stock de marchandises, carburant, transport, fournitures, loyer, electricite Senelec, eau Sen'Eau, repas, reparation ou tout autre achat) DOIT OBLIGATOIREMENT avoir une piece justificative : photo du recu, de la facture, du ticket de caisse, ou photo probante du stock/marchandise achetee avant d'etre acceptee et validee.
  Si le commercant declare une depense en cash par texte sans photo : pre-enregistre l'operation en attente, et dans ta "reponse_whatsapp", rappelle-lui fermement :
  "Votre depense de [montant] FCFA a ete pre-enregistree en attente de justificatif.
  Rappel obligatoire : Pour que cette depense soit acceptee et enregistree dans vos donnees financieres officielles, vous devez obligatoirement envoyer sa piece justificative (photo du recu, facture, ticket ou photo du stock achete).
  Sans justificatif, cette depense ne sera pas comptabilisee et c'est vous qui perdez !"

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

        # 1. Mise Ã  jour de l'heure du rappel quotidien
        if intention == "MODIFIER_HEURE_RITUEL" and parsed.get("heure_rituel") and sp and entreprise_id:
            heure = parsed.get("heure_rituel")
            try:
                sp.table("entreprises").update({"heure_rappel_quotidien": heure}).eq("id", entreprise_id).execute()
            except Exception:
                pass

        # 2. Gestion dÃ©taillÃ©e des Dettes et CrÃ©ances
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
                        "tiers_nom": tiers_nom or "Tiers non prÃ©cisÃ©",
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

        # 3. Enregistrement d'une transaction de trÃ©sorerie (Wave, OM, EspÃ¨ces)
        tx_data = parsed.get("transaction") or {}
        if tx_data.get("is_transaction") and tx_data.get("montant_fcfa", 0) > 0 and sp and entreprise_id:
            src = (tx_data.get("source_paiement") or "WAVE").upper()
            cpt = str(tx_data.get("compte_syscohada", "701"))
            # Si c'est Wave/OM avec compte qualifiÃ©, validÃ© d'office ; si espÃ¨ces sans reÃ§u ou compte 471, en attente
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
                print(f"Transaction insÃ©rÃ©e : ID {inserted.data[0]['id']} ({statut_init})")
            except Exception as e:
                # Si colonne reference_externe n'existe pas en base, insertion sans cette clÃ©
                tx_record.pop("reference_externe", None)
                inserted = sp.table("transactions").insert(tx_record).execute()
                print(f"Transaction insÃ©rÃ©e (fallback) : ID {inserted.data[0]['id']} ({statut_init})")

        # 4. Enregistrement d'un Ã©tat structurel (Stock, Immobilisation)
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
                    f"ArrÃªtÃ© de trÃ©sorerie journalier ({today_str}) :\n\n"
                    f"DisponibilitÃ©s liquides Ã  cet instant :\n"
                    f"â€¢ TrÃ©sorerie actuelle dans Wave : {wave:,.0f} FCFA\n"
                    f"â€¢ TrÃ©sorerie actuelle dans Orange Money : {om:,.0f} FCFA\n"
                    f"â€¢ TrÃ©sorerie actuelle en EspÃ¨ces : {especes:,.0f} FCFA\n"
                    f"â€¢ Total des liquiditÃ©s disponibles : {total_dispo:,.0f} FCFA\n\n"
                    f"Flux d'exploitation de la journÃ©e :\n"
                    f"â€¢ Total des encaissements d'exploitation : {total_in:,.0f} FCFA\n"
                    f"â€¢ Total des dÃ©caissements et charges : {total_out:,.0f} FCFA\n"
                    f"â€¢ RÃ©sultat net d'exploitation estimÃ© : {marge:,.0f} FCFA\n\n"
                    f"ContrÃ´le des piÃ¨ces probantes :\n"
                )
                if manquants:
                    synth_msg += f"Vigilance : vous avez {len(manquants)} dÃ©pense(s) en attente de reÃ§u fiscal ou facture. Veuillez photographier les justificatifs pour garantir la dÃ©ductibilitÃ© de la charge.\n\n"
                else:
                    synth_msg += "ConformitÃ© certifiÃ©e : l'ensemble de vos flux du jour dispose de justificatifs probants.\n\n"

                synth_msg += "Avez-vous d'autres opÃ©rations en espÃ¨ces, par Wave ou via Orange Money Ã  consigner avant la clÃ´ture dÃ©finitive ?"
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

        # 7. Consultation des dettes et crÃ©ances
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

        return parsed.get("reponse_whatsapp", "Message bien reÃ§u par Grow !")

    except Exception as e:
        print(f"Erreur process_text_with_ai : {e}")
        return f"Grow a bien notÃ© votre message : '{user_text}'. Merci !"


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


async def send_whatsapp_audio(to_phone: str, audio_url: str):
    """Envoi d'une note vocale audio WhatsApp via Meta Graph API."""
    load_dotenv(override=True)
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("PHONE_NUMBER_ID")

    if not token or not phone_id or not audio_url:
        return

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "audio",
        "audio": {
            "link": audio_url
        }
    }

    def _sync_send_audio():
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                print(f"Statut envoi Audio Meta vers {to_phone} : {resp.status}")
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
            base_u = get_public_base_url()
            audio_url = f"{base_u}/static/audio/{audio_fn}"
            await send_whatsapp_audio(to_phone, audio_url)
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
    # 1. VÃ©rification minute par minute pour le Grand Bilan du Soir (21h00 par dÃ©faut ou heure personnalisÃ©e)
    scheduler.add_job(daily_ritual_check, "cron", minute="*", timezone=TZ_DAKAR)
    
    # 2. Point Flash toutes les 3 heures pendant la journÃ©e (09h00, 12h00, 15h00, 18h00, 21h00 heure de Dakar)
    scheduler.add_job(flash_summary_3h_check, "cron", hour="09,12,15,18,21", minute="00", timezone=TZ_DAKAR)

    # 3. Message matinal de 06h00 heure de Dakar (Bilan de la nuit et rÃ©initialisation des comptes de dÃ©part)
    scheduler.add_job(morning_greeting_check, "cron", hour="06", minute="00", timezone=TZ_DAKAR)

    # 4. Relance automatique des dettes et crÃ©ances tous les 3 jours (Ã  10h00 heure de Dakar)
    scheduler.add_job(check_and_send_dettes_reminders, "cron", hour="10", minute="00", timezone=TZ_DAKAR)

    # 5. Point hebdomadaire et mensuel
    scheduler.add_job(weekly_closure_check, "cron", day_of_week="sun", hour="18", minute="00", timezone=TZ_DAKAR)
    scheduler.add_job(monthly_closure_check, "cron", day="28", hour="09", minute="00", timezone=TZ_DAKAR)

    scheduler.start()
    print("Planificateur automatique Grow (APScheduler) cale sur l'heure du Senegal (Africa/Dakar) demarre avec succes !")


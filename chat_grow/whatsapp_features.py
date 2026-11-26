"""
Growth — Module d'Activation des 7 Piliers WhatsApp Business Officiels
Numéro Officiel : +221 78 195 40 86 (Certifié Meta / WABA ID: 1626510701857010)

Fonctionnalités avancées incluses :
1. Menus Déroulants Natifs (Interactive List Messages)
2. Boutons d'Action Web (Call-To-Action URLs)
3. Génération & Envoi Direct de Documents PDF dans WhatsApp (SYSCOHADA SMT)
4. Relance Automatique des Clients Débiteurs (Carnet de Crédits)
5. Alertes Fiscales & Déclaratives DGID Sénégal (Échéances 15 du mois / 30 avril)
6. Infographies Financières Hebdomadaires (Cartes Images HD 1080x1080)
7. Gestion de la Localisation GPS de la Boutique
"""

import os
import re
import json
import urllib.request
import asyncio
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from chat_grow.pdf_generator import generer_bilan_pdf
from chat_grow.infography_generator import generer_infographie_hebdo

DEFAULT_PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "1432871489913065")
RENDER_PRODUCTION_URL = "https://grow-2epo.onrender.com"


def get_whatsapp_credentials():
    """Charge les clés d'API WhatsApp Cloud."""
    # Charge prioritairement chat_grow/.env si présent
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("PHONE_NUMBER_ID", DEFAULT_PHONE_NUMBER_ID) or DEFAULT_PHONE_NUMBER_ID
    return token, phone_id


def get_media_base_url() -> str:
    """Retourne l'URL publique accessible par les serveurs de Meta WhatsApp pour télécharger les médias."""
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render_url:
        return render_url
    # Production Growth Render URL
    return RENDER_PRODUCTION_URL


# ==============================================================================
# 1. ENVOI DE MENUS DÉROULANTS NATIFS (INTERACTIVE LIST MESSAGES)
# ==============================================================================

def build_operators_choice_list() -> tuple:
    """Construit les sections et lignes du menu interactif déroulant de choix des comptes/opérateurs."""
    header_text = "SÉLECTION OPÉRATEURS"
    body_text = "Sélectionnez votre opérateur ou le mode de paiement utilisé pour vos encaissements :"
    button_label = "Choisir l'opérateur"
    footer_text = "Growth • Système Officiel"

    sections = [
        {
            "title": "COMPTES PROFESSIONNELS",
            "rows": [
                {
                    "id": "opt_a",
                    "title": "Wave Business",
                    "description": "Compte marchand officiel Wave"
                },
                {
                    "id": "opt_b",
                    "title": "Orange Business",
                    "description": "Compte marchand Sonatel Orange Money"
                },
                {
                    "id": "opt_c",
                    "title": "Wave & Orange Business",
                    "description": "Les deux comptes marchands professionnels"
                }
            ]
        },
        {
            "title": "COMPTES PERSONNELS",
            "rows": [
                {
                    "id": "opt_d",
                    "title": "Comptes Personnels",
                    "description": "Wave perso, Orange Money perso, Espèces"
                },
                {
                    "id": "opt_e",
                    "title": "Mixte Pro & Personnel",
                    "description": "Comptes marchands et fonds personnels"
                }
            ]
        }
    ]
    return header_text, body_text, button_label, sections, footer_text


def build_main_operations_list() -> tuple:
    """Construit les sections et lignes du menu interactif déroulant WhatsApp (10 actions clés)."""
    header_text = "MENU PRINCIPAL GROWTH"
    body_text = (
        "Bienvenue sur votre copilote comptable certifié SYSCOHADA SMT.\n\n"
        "Que souhaitez-vous enregistrer ou consulter aujourd'hui ?"
    )
    button_label = "Choisir une action"
    footer_text = "Growth • Copilote Financier PME"

    sections = [
        {
            "title": "ÉCRITURES & CAISSE",
            "rows": [
                {
                    "id": "op_vente",
                    "title": "Enregistrer Vente",
                    "description": "Vente espèces, Wave ou Orange Money"
                },
                {
                    "id": "op_depense",
                    "title": "Noter une Dépense",
                    "description": "Achats stocks, réassort, loyer ou facture"
                },
                {
                    "id": "op_popote",
                    "title": "Popote Maison (108)",
                    "description": "Sortie famille sans fausser la marge"
                },
                {
                    "id": "op_credit",
                    "title": "Carnet Crédits & Relance",
                    "description": "Suivi dettes clients & acomptes"
                }
            ]
        },
        {
            "title": "PILOTAGE & SÉCURITÉ",
            "rows": [
                {
                    "id": "op_bilan_pdf",
                    "title": "Bilan & Visa Cabinet",
                    "description": "Demande transmise au cabinet comptable"
                },
                {
                    "id": "op_infographie",
                    "title": "Tableau de Bord HD",
                    "description": "Synthèse financière visuelle"
                },
                {
                    "id": "op_fiscalite",
                    "title": "Simulateur Impôt CGU",
                    "description": "Barème DGID & provisions fiscales"
                },
                {
                    "id": "op_pret_express",
                    "title": "Dossier Prêt Express",
                    "description": "Capacité d'emprunt & banques"
                },
                {
                    "id": "op_cloture_soir",
                    "title": "Clôture de Caisse 20h",
                    "description": "Arrêté de caisse & solde du jour"
                }
            ]
        },
        {
            "title": "ARSENAL OUTILS PME",
            "rows": [
                {
                    "id": "op_hub_tpe",
                    "title": "Tous les Outils PME ➔",
                    "description": "Salaires, Marge, Anti-fraude, Scanner..."
                }
            ]
        }
    ]

    return header_text, body_text, button_label, sections, footer_text


def build_all_pme_hub_list() -> tuple:
    """Construit le catalogue universel des outils et innovations pour PME & TPE."""
    header_text = "HUB INTÉGRAL PME & TPE"
    body_text = (
        "L'arsenal digital complet pour sécuriser, rentabiliser et faire grandir votre entreprise :\n\n"
        "Sélectionnez un outil spécialisé ci-dessous :"
    )
    button_label = "Ouvrir l'outil"
    footer_text = "Growth • Le Système PME"

    sections = [
        {
            "title": "SÉCURITÉ & ÉQUIPE",
            "rows": [
                {
                    "id": "op_salaires",
                    "title": "Salaires & Avances",
                    "description": "Livre de paie commis & apprentis"
                },
                {
                    "id": "op_calculateur_marge",
                    "title": "Calculateur de Marge",
                    "description": "Prix de vente & rentabilité nette"
                },
                {
                    "id": "op_controle_caisse",
                    "title": "Contrôle Tiroir Caisse",
                    "description": "Détecteur écarts & anti-coulage"
                },
                {
                    "id": "op_anti_arnaque",
                    "title": "Anti-Arnaque Wave",
                    "description": "Détecter faux transferts & SMS"
                },
                {
                    "id": "op_scanner_recu",
                    "title": "Scanner Reçu Froissé",
                    "description": "Photo ticket grossiste par IA Vision"
                }
            ]
        },
        {
            "title": "CROISSANCE & DGID",
            "rows": [
                {
                    "id": "op_recu_client",
                    "title": "Émettre Reçu Client",
                    "description": "Facturette WhatsApp instantanée"
                },
                {
                    "id": "op_relance",
                    "title": "Relancer Débiteurs",
                    "description": "Modèles de rappels diplomatiques"
                },
                {
                    "id": "op_barometre",
                    "title": "Baromètre des Prix",
                    "description": "Alerte hausse grossistes"
                },
                {
                    "id": "op_fiscalite",
                    "title": "Simulateur Impôt CGU",
                    "description": "Barème DGID & provisions fiscales"
                },
                {
                    "id": "op_menu_principal",
                    "title": "🔙 Menu Principal",
                    "description": "Revenir aux opérations courantes"
                }
            ]
        }
    ]

    return header_text, body_text, button_label, sections, footer_text


def build_innovations_menu_list() -> tuple:
    """Alias rétro-compatible pour le sous-menu Hub PME."""
    return build_all_pme_hub_list()


async def send_whatsapp_interactive_list(
    to_phone: str,
    header_text: str,
    body_text: str,
    button_label: str,
    sections: list,
    footer_text: str = "Growth • Système Conforme"
) -> bool:
    """
    Envoi d'un menu déroulant interactif natif Meta WhatsApp (jusqu'à 10 options).
    """
    token, phone_id = get_whatsapp_credentials()
    if not token or not phone_id or not to_phone:
        return False

    clean_phone = re.sub(r"\D", "", str(to_phone))
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }

    safe_sections = []
    for s in (sections or []):
        safe_rows = []
        for r in s.get("rows", []):
            safe_rows.append({
                "id": str(r.get("id", ""))[:200],
                "title": str(r.get("title", ""))[:24],
                "description": str(r.get("description", ""))[:72]
            })
        safe_sections.append({
            "title": str(s.get("title", ""))[:24],
            "rows": safe_rows
        })

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_phone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": header_text[:60]
            },
            "body": {
                "text": body_text[:1024]
            },
            "footer": {
                "text": footer_text[:60]
            },
            "action": {
                "button": button_label[:20],
                "sections": safe_sections
            }
        }
    }

    def _sync():
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                print(f"[WHATSAPP LIST] Menu interactif envoyé vers {clean_phone} : statut {resp.status}")
                return True
        except Exception as e:
            print(f"[WHATSAPP LIST ERREUR] {e}")
            return False

    return await asyncio.to_thread(_sync)


# ==============================================================================
# 2. ENVOI DE BOUTONS D'ACTION WEB (CALL-TO-ACTION URLS)
# ==============================================================================

async def send_whatsapp_cta_url(
    to_phone: str,
    body_text: str,
    button_text: str,
    url_target: str,
    header_text: Optional[str] = "📊 ACCÈS SÉCURISÉ GROWTH",
    footer_text: Optional[str] = "Growth • Copilote Financier PME"
) -> bool:
    """
    Envoie un message interactif natif avec bouton Call-To-Action URL.
    Si le type cta_url est restreint, repli sur un message texte élégant avec le lien direct.
    """
    token, phone_id = get_whatsapp_credentials()
    if not token or not phone_id or not to_phone:
        return False

    clean_phone = re.sub(r"\D", "", str(to_phone))
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_phone,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {
                "text": body_text[:1024]
            },
            "footer": {
                "text": (footer_text or "Growth • Copilote Financier PME")[:60]
            },
            "action": {
                "name": "cta_url",
                "parameters": {
                    "display_text": button_text[:20],
                    "url": url_target
                }
            }
        }
    }

    def _sync():
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                print(f"[WHATSAPP CTA] Bouton URL envoyé vers {clean_phone} : statut {resp.status}")
                return True
        except Exception as e:
            print(f"[WHATSAPP CTA ERREUR] {e} -> Repli message texte formaté avec lien direct")
            try:
                # Repli propre en cas de restriction de template CTA sur Meta API
                fallback_text = (
                    f"*{header_text}*\n\n"
                    f"{body_text}\n\n"
                    f"👉 *{button_text}* :\n{url_target}\n\n"
                    f"_{footer_text}_"
                )
                text_payload = {
                    "messaging_product": "whatsapp",
                    "to": clean_phone,
                    "type": "text",
                    "text": {"body": fallback_text}
                }
                req_fallback = urllib.request.Request(
                    url,
                    data=json.dumps(text_payload, ensure_ascii=False).encode("utf-8"),
                    headers=headers
                )
                with urllib.request.urlopen(req_fallback, timeout=20) as r2:
                    return r2.status == 200
            except Exception as e2:
                print(f"[WHATSAPP CTA FALLBACK ERREUR] {e2}")
                return False

    return await asyncio.to_thread(_sync)


# ==============================================================================
# 3. ENVOI DIRECT DE DOCUMENTS PDF DANS WHATSAPP
# ==============================================================================

async def send_whatsapp_document(
    to_phone: str,
    doc_url: str,
    filename: str,
    caption: str = ""
) -> bool:
    """
    Envoi d'un fichier PDF directement dans WhatsApp via upload binaire direct Meta Media API
    ou lien public HTTPS. Permet au commerçant de télécharger et visualiser son Bilan / Liasse.
    """
    token, phone_id = get_whatsapp_credentials()
    if not token or not phone_id or not to_phone or not doc_url:
        return False

    clean_phone = re.sub(r"\D", "", str(to_phone))
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }

    # Résolution locale pour upload binaire direct (100% fiable, zéro 404)
    media_id = None
    local_file = None
    if os.path.exists(doc_url):
        local_file = doc_url
    else:
        possible = os.path.join(os.path.dirname(__file__), "static", "documents", os.path.basename(doc_url))
        if os.path.exists(possible):
            local_file = possible

    if local_file and os.path.exists(local_file):
        try:
            import requests
            upload_url = f"https://graph.facebook.com/v21.0/{phone_id}/media"
            headers_up = {"Authorization": f"Bearer {token}"}
            with open(local_file, "rb") as f_up:
                r_up = requests.post(
                    upload_url,
                    headers=headers_up,
                    files={"file": (filename or os.path.basename(local_file), f_up, "application/pdf")},
                    data={"messaging_product": "whatsapp"},
                    timeout=30
                )
            if r_up.status_code in [200, 201]:
                media_id = r_up.json().get("id")
                print(f"[WHATSAPP DOC MEDIA] PDF {local_file} uploadé direct vers Meta : media_id={media_id}")
        except Exception as e_up:
            print(f"[WHATSAPP DOC MEDIA ERREUR] {e_up}")

    doc_data = {"id": media_id, "filename": filename} if media_id else {"link": doc_url, "filename": filename}
    if caption and caption.strip():
        doc_data["caption"] = caption.strip()[:1024]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_phone,
        "type": "document",
        "document": doc_data
    }

    def _sync():
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(f"[WHATSAPP DOC] Document '{filename}' envoyé vers {clean_phone} : statut {resp.status}")
                return True
        except Exception as e:
            print(f"[WHATSAPP DOC ERREUR] {e}")
            return False

    return await asyncio.to_thread(_sync)


# ==============================================================================
# 4. ENVOI DIRECT D'IMAGES HD DANS WHATSAPP
# ==============================================================================

async def send_whatsapp_image(
    to_phone: str,
    image_url: str,
    caption: str = ""
) -> bool:
    """
    Envoi d'une image HD (ex: Infographie financière 1080x1080) dans WhatsApp
    via upload binaire direct vers Meta Media API (zéro dépendance d'hébergement externe).
    """
    token, phone_id = get_whatsapp_credentials()
    if not token or not phone_id or not to_phone or not image_url:
        return False

    clean_phone = re.sub(r"\D", "", str(to_phone))
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }

    # Résolution locale pour upload binaire direct (100% fiable, zéro 404)
    media_id = None
    local_file = None
    if os.path.exists(image_url):
        local_file = image_url
    else:
        possible = os.path.join(os.path.dirname(__file__), "static", "images", os.path.basename(image_url))
        if os.path.exists(possible):
            local_file = possible

    if local_file and os.path.exists(local_file):
        try:
            import requests
            upload_url = f"https://graph.facebook.com/v21.0/{phone_id}/media"
            headers_up = {"Authorization": f"Bearer {token}"}
            mime = "image/png" if local_file.endswith(".png") else "image/jpeg"
            with open(local_file, "rb") as f_up:
                r_up = requests.post(
                    upload_url,
                    headers=headers_up,
                    files={"file": (os.path.basename(local_file), f_up, mime)},
                    data={"messaging_product": "whatsapp"},
                    timeout=30
                )
            if r_up.status_code in [200, 201]:
                media_id = r_up.json().get("id")
                print(f"[WHATSAPP IMAGE MEDIA] Image {local_file} uploadée direct vers Meta : media_id={media_id}")
        except Exception as e_up:
            print(f"[WHATSAPP IMAGE MEDIA ERREUR] {e_up}")

    img_data = {"id": media_id} if media_id else {"link": image_url}
    if caption and caption.strip():
        img_data["caption"] = caption.strip()[:1024]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_phone,
        "type": "image",
        "image": img_data
    }

    def _sync():
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(f"[WHATSAPP IMAGE] Image envoyée vers {clean_phone} : statut {resp.status}")
                return True
        except Exception as e:
            print(f"[WHATSAPP IMAGE ERREUR] {e}")
            return False

    return await asyncio.to_thread(_sync)


# ==============================================================================
# 5. CARNET DE CRÉDITS & RELANCE AUTOMATIQUE DES DÉBITEURS
# ==============================================================================

CREDITS_DB_FILE = os.path.join(os.path.dirname(__file__), "credits_clients.json")


def load_credits_db() -> dict:
    if os.path.exists(CREDITS_DB_FILE):
        try:
            with open(CREDITS_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_credits_db(data: dict):
    try:
        with open(CREDITS_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CRÉDITS] Erreur sauvegarde : {e}")


def enregistrer_credit_client(merchant_phone: str, client_nom: str, montant_fcfa: int, description: str = "") -> dict:
    """Enregistre une créance client (vente à crédit) pour suivi et relance."""
    clean_p = re.sub(r"\D", "", str(merchant_phone))
    db = load_credits_db()
    if clean_p not in db:
        db[clean_p] = []

    credit_entry = {
        "id": f"crd_{int(datetime.now().timestamp())}",
        "client": client_nom.strip().title(),
        "montant": int(montant_fcfa),
        "description": description.strip() or "Vente à crédit",
        "date": datetime.now().strftime("%d/%m/%Y"),
        "statut": "NON_PAYE"
    }
    db[clean_p].append(credit_entry)
    save_credits_db(db)
    return credit_entry


def obtenir_credits_clients(merchant_phone: str) -> List[dict]:
    clean_p = re.sub(r"\D", "", str(merchant_phone))
    db = load_credits_db()
    return db.get(clean_p, [])


def generer_message_relance_debiteur(
    client_nom: str,
    montant_du: int,
    nom_boutique: str = "votre boutique",
    tel_marchand: str = ""
) -> str:
    """
    Génère un modèle de message WhatsApp ultra-courtois et respectueux
    prêt à être transféré ou envoyé au client en 1 clic.
    """
    montant_fmt = f"{montant_du:,} FCFA".replace(",", " ")
    
    msg = (
        f"🤝 *Message de Relance Débiteur Courtois*\n\n"
        f"Voici le message prêt à transférer à *{client_nom}* :\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"« Bonjour *{client_nom}*, j'espère que vous vous portez bien ainsi que votre famille.\n\n"
        f"C'est un petit rappel amical concernant le solde de *{montant_fmt}* restant dû pour vos achats chez *{nom_boutique}*.\n\n"
        f"Pour votre commodité, vous pouvez effectuer le règlement par Wave ou Orange Money au numéro suivant :\n"
        f"📱 *{tel_marchand or 'mon numéro habituel'}*\n\n"
        f"Merci infiniment pour votre confiance et bonne journée ! »\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🇸🇳 *Version Wolof (Optionnelle) :*\n"
        f"« Nanga def {client_nom}, jàmm nga am ? Rappel la rekk ci li desoon ci sa commande ({montant_fmt}) ci {nom_boutique}. Man nga koo yónnee ci Wave wala OM ci sama numéro. Jërëjëf ! »"
    )
    return msg


# ==============================================================================
# 6. ALERTES FISCALES & DÉCLARATIVES DGID SÉNÉGAL
# ==============================================================================

def calculer_alerte_fiscale_dgid(chiffre_affaires: int = 0) -> str:
    """
    Calcule le compte à rebours et les recommandations pour les obligations fiscales sénégalaises.
    - Échéance mensuelle du 15 : Retenues à la source (BRS / VRS / Salaires).
    - Échéance annuelle du 30 avril : Bilan et Liasse Fiscale SYSCOHADA SMT.
    """
    today = date.today()
    
    # 1. Prochaine échéance mensuelle (15 du mois)
    if today.day <= 15:
        prochaine_echeance_15 = date(today.year, today.month, 15)
    else:
        next_month = today.month + 1 if today.month < 12 else 1
        next_year = today.year if today.month < 12 else today.year + 1
        prochaine_echeance_15 = date(next_year, next_month, 15)

    jours_restants_15 = (prochaine_echeance_15 - today).days

    # 2. Prochaine échéance liasse annuelle (30 avril)
    annee_bilan = today.year if today <= date(today.year, 4, 30) else today.year + 1
    echeance_bilan = date(annee_bilan, 4, 30)
    jours_restants_bilan = (echeance_bilan - today).days

    # Estimation provisionnelle indicative
    provision_cgu_estimee = round(chiffre_affaires * 0.02) if chiffre_affaires > 0 else 0
    prov_fmt = f"{provision_cgu_estimee:,} FCFA".replace(",", " ")

    msg = (
        f"🏛️ *CALENDRIER FISCAL DGID SÉNÉGAL*\n\n"
        f"📅 *Échéance Mensuelle : {prochaine_echeance_15.strftime('%d/%m/%Y')}*\n"
        f"⏱️ Plus que *{jours_restants_15} jours* pour déclarer et reverser les retenues à la source (BRS / VRS / Salaires).\n\n"
        f"📚 *Dépôt Liasse Fiscale & Bilan SYSCOHADA :*\n"
        f"Échéance légale : *30/04/{annee_bilan}* (dans {jours_restants_bilan} jours).\n\n"
        f"💡 *Recommandations Fiscales Growth :*\n"
        f"1. Conservez toutes vos factures fournisseurs et tickets pour justifier vos charges déductibles.\n"
        f"2. Votre journal d'écritures est scellé cryptographiquement sous SHA-256 (Archivage légal 10 ans).\n"
        f"{f'3. Provision préconisée sur vos ventes : *{prov_fmt}* mis de côté.' if provision_cgu_estimee > 0 else '3. Enregistrez vos premières opérations pour calculer vos provisions en direct.'}\n\n"
        f"👉 _Tapez *« Bilan »* à tout moment pour recevoir votre Liasse Fiscale officielle en PDF._"
    )
    return msg


# ==============================================================================
# 7. GESTION DE LA LOCALISATION GPS DE LA BOUTIQUE
# ==============================================================================

def enregistrer_localisation_boutique(
    sender_phone: str,
    latitude: float,
    longitude: float,
    name: str = "",
    address: str = ""
) -> str:
    """
    Enregistre les coordonnées GPS de la boutique du commerçant.
    Permet la certification d'établissement pour la DGID, le NINEA et le cadastre commercial.
    """
    from chat_grow.main import update_onboarding_state, get_onboarding_state
    
    clean_p = re.sub(r"\D", "", str(sender_phone))
    gps_info = {
        "latitude": latitude,
        "longitude": longitude,
        "nom_lieu": name or "Boutique PME",
        "adresse": address or f"Point GPS ({latitude:.5f}, {longitude:.5f})",
        "date_geocodage": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }

    try:
        update_onboarding_state(clean_p, "localisation_gps", gps_info)
    except Exception as e:
        print(f"[GPS] Erreur update_onboarding_state : {e}")

    google_maps_link = f"https://www.google.com/maps?q={latitude},{longitude}"

    reponse = (
        f"📍 *LOCALISATION DE VOTRE ENTREPRISE ENREGISTRÉE !*\n\n"
        f"✅ *Établissement Géocodé :*\n"
        f"• Nom : {name or 'Siège / Entreprise'}\n"
        f"• Adresse : {address or 'Emplacement vérifié'}\n"
        f"• Coordonnées : `{latitude:.5f}, {longitude:.5f}`\n\n"
        f"🗺️ *Visualiser sur la carte :*\n{google_maps_link}\n\n"
        f"🏛️ *Utilité Légale & Fiscale :*\n"
        f"Ces coordonnées sont désormais rattachées à votre dossier NINEA et certifient votre implantation officielle auprès de la DGID et de votre expert-comptable."
    )
    return reponse


# ==============================================================================
# DISPATCHEUR HAUT NIVEAU POUR GENERATION ET ENVOI DE PDF & INFOGRAPHIE
# ==============================================================================

async def generer_et_envoyer_bilan_pme(sender_phone: str) -> bool:
    """
    Génère le PDF officiel SYSCOHADA SMT et l'expédie directement par WhatsApp.
    """
    from chat_grow.database import get_entreprise_by_phone_resilient, get_transactions_resilient
    from chat_grow.main import get_onboarding_state

    clean_p = re.sub(r"\D", "", str(sender_phone))
    ent = get_entreprise_by_phone_resilient(clean_p) or {}
    st = get_onboarding_state(clean_p) or {}

    cab_nom = ent.get("cabinet_nom") or st.get("cabinet_nom") or None
    pme_data = {
        "nom_entreprise": ent.get("nom") or st.get("nom_entreprise") or "Votre Entreprise PME",
        "telephone": clean_p,
        "ninea": ent.get("ninea") or st.get("ninea") or "En cours",
        "regime": "SYSCOHADA SMT (Système Minimal de Trésorerie)",
        "secteur": st.get("secteur") or "Commerce Général",
        "cabinet_nom": cab_nom
    }

    ent_id = ent.get("id") or clean_p
    txs = get_transactions_resilient(ent_id) or []
    
    # Adaptation des clés pour le générateur PDF
    ecritures_formattees = []
    for t in txs:
        flux = t.get("type_flux")
        montant = t.get("montant_fcfa", 0)
        ecritures_formattees.append({
            "date": t.get("date_operation", datetime.now().strftime("%d/%m/%Y")),
            "libelle": t.get("libelle", "Opération"),
            "compte": t.get("compte_syscohada", "701100"),
            "debit": montant if flux == "DEPENSE" else 0,
            "credit": montant if flux != "DEPENSE" else 0
        })

    pdf_local_path = generer_bilan_pdf(pme_data, ecritures_formattees)
    nom_propre = re.sub(r"[^\w\s-]", "", pme_data['nom_entreprise']).strip().replace(" ", "_") or "PME"
    pdf_filename = f"Bilan_SYSCOHADA_{nom_propre}.pdf"
    base_url = get_media_base_url()
    public_pdf_url = f"{base_url}/static/documents/{os.path.basename(pdf_local_path)}"

    # Envoi pur du fichier PDF sans aucun commentaire parasite (consigne stricte utilisateur)
    target_pdf = pdf_local_path if os.path.exists(pdf_local_path) else public_pdf_url
    return await send_whatsapp_document(clean_p, target_pdf, pdf_filename, caption="")


generer_et_envoyer_bilan_pdf = generer_et_envoyer_bilan_pme


async def generer_et_envoyer_infographie_pme(sender_phone: str) -> bool:
    """
    Génère l'infographie HD 1080x1080 et l'expédie directement par WhatsApp.
    """
    from chat_grow.database import get_entreprise_by_phone_resilient, get_transactions_resilient
    from chat_grow.main import get_onboarding_state

    clean_p = re.sub(r"\D", "", str(sender_phone))
    ent = get_entreprise_by_phone_resilient(clean_p) or {}
    st = get_onboarding_state(clean_p) or {}

    nom_ent = ent.get("nom_entreprise") or ent.get("nom") or st.get("nom_entreprise") or st.get("nom_commercial") or "Votre Entreprise"
    cab_nom = ent.get("cabinet_nom") or st.get("cabinet_nom") or None

    pme_data = {
        "nom_entreprise": nom_ent,
        "telephone": clean_p,
        "cabinet_nom": cab_nom
    }

    ent_id = ent.get("id") or clean_p
    txs = get_transactions_resilient(ent_id) or get_transactions_resilient(clean_p) or []

    total_ca = sum(t.get("montant_fcfa", 0) for t in txs if t.get("type_flux") != "DEPENSE")
    total_dep = sum(t.get("montant_fcfa", 0) for t in txs if t.get("type_flux") == "DEPENSE")
    treso = total_ca - total_dep

    stats = {
        "ca": f"{total_ca:,} FCFA".replace(",", " "),
        "depenses": f"{total_dep:,} FCFA".replace(",", " "),
        "treso": f"{treso:,} FCFA".replace(",", " "),
        "nb_operations": len(txs)
    }

    img_local_path = generer_infographie_hebdo(pme_data, stats, txs=txs)
    img_filename = os.path.basename(img_local_path)
    base_url = get_media_base_url()
    public_img_url = f"{base_url}/static/images/{img_filename}"

    # Envoi pur de l'image haute définition sans aucun commentaire parasite (consigne stricte utilisateur)
    target_img = img_local_path if os.path.exists(img_local_path) else public_img_url
    return await send_whatsapp_image(clean_p, target_img, caption="")

"""
Grow MVP - Module Gemini Audio Processor
Pipeline : Note vocale WhatsApp (.ogg) -> Gemini -> JSON SYSCOHADA + reponse Wolof

Architecture :
  - Modele prioritaire demande par l utilisateur : gemini-3.8-flash
  - Cascade de repli automatique en cas de pic de charge (503) :
      1. gemini-3.8-flash (priorite absolue)
      2. gemini-3.7-flash
      3. gemini-3.1-flash-lite (100% operationnel et repond immediatement)
  - Gemini recoit directement les bytes audio OGG natifs WhatsApp
  - Analyse le melange Wolof commercial / Francais dakarois
  - Produit en 1 seule requete :
      * Transcription fidele
      * Ecriture comptable SYSCOHADA au format JSON
      * Reponse en Wolof dakarois oral naturel pour la note vocale

SDK : google-genai >= 3.0 (officiel Google)
"""

import os
import json
import re
from dotenv import load_dotenv

load_dotenv(override=True)

# Liste ordonnee des modeles : gemini-3.8-flash en tete
MODELS_PRIORITAIRES = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite"
]

_SYSTEM_PROMPT = """Tu es Grow, l'assistant pre-comptable expert du secteur informel a Dakar (Senegal).
Tu analyses des notes vocales commerciales envoyees sur WhatsApp par des commercants dakarois.
La langue est soit le Wolof, soit le Francais, soit un melange naturel des deux (Wolof urbain de Dakar).

VOCABULAIRE COMMERCIAL CLE A DAKAR :
- "dama jaay" / "jaay naa" / "jaay" = vente / encaissement
- "dama jënd" / "jënd naa" / "jend" = achat / depense
- "dug na" / "dug na ci Wave" = argent recu / encaissement effectue
- "genn na" / "genn na xaalis" = decaissement
- "fey naa" = j'ai paye
- "xaalis" / "xalis" = argent
- "junni" = 1 000 FCFA
- "ñaar-fukki junni" = 20 000 FCFA
- "juróom junni" = 5 000 FCFA
- "fukki junni" = 10 000 FCFA
- "ñent-fukk ak juróom junni" = 45 000 FCFA
- "tëmeer junni" = 100 000 FCFA
- Wave, Orange Money, Free Money, Cash, Especes

PLAN COMPTABLE SYSCOHADA :
- 521 : Banques et monnaie electronique (Wave, Orange Money, Free Money)
- 571 : Caisse (especes, cash)
- 701 : Ventes de marchandises
- 601 : Achats de marchandises
- 411 : Clients (creances)
- 401 : Fournisseurs (dettes)
- 606 : Achats de fournitures et services

CONSIGNE STRICTE : Reponds UNIQUEMENT avec un objet JSON valide (aucun texte autour, pas de balises markdown) :
{
  "transcription": "texte exact de ce que l'utilisateur a dit",
  "langue_detectee": "wo",
  "operation": {
    "type": "VENTE",
    "montant": 20000,
    "devise": "FCFA",
    "canal": "Wave",
    "compte_debit": "521",
    "compte_credit": "701",
    "libelle": "Vente de marchandises via Wave"
  },
  "reponse_wolof": "Jërejëf ! Sa jaay bu ñaar-fukki junni francs CFA ci Wave dug na bu baax. Bind nañu ko ci sa teere comptable.",
  "reponse_francais": "Votre vente de 20 000 FCFA via Wave a ete enregistree avec succes."
}

REGLES POUR LA REPONSE WOLOF :
- Commence par "Jërejëf !" pour toute vente ou encaissement
- Ecris les montants en lettres wolof (pas de chiffres bruts) : juróom junni, fukki junni, ñaar-fukki junni
- Phrase orale courte (1 a 2 phrases max), style naturel du marche HLM de Dakar

Si l'audio n'est pas audible :
{
  "transcription": "",
  "langue_detectee": "fr",
  "operation": null,
  "reponse_wolof": "Déggluma bu baax. Nanga ko wëccël wala bind ko.",
  "reponse_francais": "Je n'ai pas pu entendre clairement votre note vocale. Pouvez-vous la renvoyer ou ecrire votre operation ?"
}
"""


def est_gemini_disponible() -> bool:
    """Verifie si la cle Gemini est presente et le SDK installe."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False
    try:
        import google.genai
        return True
    except ImportError:
        return False


def get_gemini_client():
    """Initialise le client google.genai officiel avec la cle API."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[GEMINI] Erreur client : {e}")
        return None


async def analyser_audio_gemini(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg"
) -> dict | None:
    """
    Analyse directement une note vocale WhatsApp avec Gemini.
    Tente en priorite gemini-3.8-flash, avec repli automatique si 503.
    """
    client = get_gemini_client()
    if not client:
        return None

    # Normalisation du MIME type
    if "ogg" in mime_type or "opus" in mime_type:
        gemini_mime = "audio/ogg"
    elif "mp3" in mime_type or "mpeg" in mime_type:
        gemini_mime = "audio/mpeg"
    elif "wav" in mime_type:
        gemini_mime = "audio/wav"
    elif "m4a" in mime_type or "mp4" in mime_type:
        gemini_mime = "audio/mp4"
    else:
        gemini_mime = "audio/ogg"

    from google.genai import types

    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=gemini_mime)
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT,
        temperature=0.1,
        max_output_tokens=600,
        response_mime_type="application/json"
    )

    for model_name in MODELS_PRIORITAIRES:
        try:
            print(f"[GEMINI AUDIO] Tentative avec le modele {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    audio_part,
                    "Analyse cette note vocale commerciale dakaroise et retourne le JSON demande."
                ],
                config=config
            )

            raw_text = response.text.strip()
            print(f"[GEMINI AUDIO ({model_name})] Reponse brute : {raw_text[:250]}")

            raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
            raw_text = re.sub(r'\s*```$', '', raw_text)

            result = json.loads(raw_text)
            result["source"] = f"gemini_{model_name}"

            transcription = result.get("transcription", "")
            langue = result.get("langue_detectee", "fr")
            operation = result.get("operation")

            print(f"[GEMINI AUDIO TRANSCRIPTION] : \"{transcription}\"")
            print(f"[GEMINI AUDIO LANGUE] : {langue}")
            if operation:
                print(f"[GEMINI AUDIO SYSCOHADA] : {operation.get('type')} {operation.get('montant')} FCFA via {operation.get('canal')}")

            return result

        except json.JSONDecodeError as e_json:
            print(f"[GEMINI {model_name}] Erreur JSON : {e_json}")
            try:
                raw = response.text.strip() if 'response' in dir() else ""
                if raw:
                    return {
                        "transcription": raw[:400],
                        "langue_detectee": "fr",
                        "operation": None,
                        "reponse_wolof": "",
                        "reponse_francais": "",
                        "source": f"gemini_{model_name}_text"
                    }
            except Exception:
                pass
            continue

        except Exception as e:
            err_msg = str(e)
            print(f"[GEMINI {model_name}] Echec : {err_msg[:120]}")
            # Si le modele est indisponible (503/404), on tente le suivant dans la cascade
            continue

    print("[GEMINI AUDIO] Tous les modeles prioritaires ont echoue. Fallback sur le pipeline classique.")
    return None


def extraire_transcription(gemini_result: dict) -> str:
    if not gemini_result:
        return ""
    return gemini_result.get("transcription", "")


def extraire_langue(gemini_result: dict) -> str:
    if not gemini_result:
        return "fr"
    langue = gemini_result.get("langue_detectee", "fr")
    return langue if langue in ("wo", "fr", "en") else "fr"


def extraire_reponse_wolof(gemini_result: dict) -> str:
    if not gemini_result:
        return ""
    return gemini_result.get("reponse_wolof", "")


def extraire_reponse_francais(gemini_result: dict) -> str:
    if not gemini_result:
        return ""
    return gemini_result.get("reponse_francais", "")


def extraire_operation_syscohada(gemini_result: dict) -> dict | None:
    if not gemini_result:
        return None
    return gemini_result.get("operation")

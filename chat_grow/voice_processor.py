"""
Growth MVP - Module Vocal Haute Précision (Speech-to-Text & Text-to-Speech Trilingue)
- Entrant : Groq Whisper ultra-rapide (Français, Wolof, Anglais) avec fallback OpenAI
- Sortant : Synthèse vocale phonétiquement adaptée pour une élocution 100% naturelle :
  * Wolof authentique (transcription phonétique dakaroise : "tchi", "djaaye", "Wèyve", etc.)
  * Anglais natif fluide (voix studio anglophone)
  * Français clair et chaleureux
"""

import io
import os
import re
import uuid
import asyncio
from dotenv import load_dotenv

# Patch de compatibilité PyAV 14+ / faster-whisper sous Python 3.14
try:
    import av
    _orig_av_open = av.open
    def _safe_av_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)
    av.open = _safe_av_open
except Exception:
    pass

load_dotenv(override=True)


# ---------------------------------------------------------------------------
# BIBLIOTHEQUE WOLOF NATURELLE DAKAROISE (0 FCFA, instantané)
# Templates certifiés en Wolof commercial dakarois parlé à Dakar.
# ---------------------------------------------------------------------------
_WOLOF_TEMPLATES = [
    # Encaissement / Vente Wave
    (r"encaissement\s+(?:wave)\s+de\s+([\d\s,.]+)\s*(?:fcfa|cfa|francs?)?.*valid",
     "Jërejëf ! Sa jaay bu {montant} FCFA ci Wave dug na bu baax."),
    # Encaissement / Vente Orange Money
    (r"encaissement\s+(?:orange\s*money|om)\s+de\s+([\d\s,.]+)\s*(?:fcfa|cfa|francs?)?.*valid",
     "Jërejëf ! Sa jaay bu {montant} FCFA ci Orange Money dug na bu baax."),
    # Vente générale avec opérateur
    (r"vente.*de\s+([\d\s,.]+)\s*(?:fcfa|cfa|francs?)?\s+(?:via|ci)\s+(wave|orange\s*money|free|espèces|especes|cash)",
     "Jërejëf ! Sa jaay bu {montant} FCFA ci {operateur} dug na bu baax."),
    # Dépense en attente de justificatif
    (r"d[ée]pense\s+de\s+([\d\s,.]+)\s*(?:fcfa|cfa|francs?)?.*attente",
     "Sa dépense bu {montant} FCFA bind nañu ko ci attente. Nanga def foto reçu bi."),
]


def traduire_wolof_statique(texte_fr: str) -> str | None:
    """
    Tente une traduction Wolof instantanée depuis les templates certifiés.
    Retourne la phrase wolof si un template correspond avec un montant valide, None sinon.
    """
    t = texte_fr.lower()
    for pattern, template in _WOLOF_TEMPLATES:
        m = re.search(pattern, t, re.IGNORECASE)
        if m:
            groupes = m.groups()
            montant = ""
            operateur = "Wave"
            for g in groupes:
                if g and re.search(r'\d', str(g)):
                    montant = re.sub(r'[^\d]', '', str(g))
                elif g and re.search(r'wave|orange|free|especes|cash', str(g), re.IGNORECASE):
                    op_map = {
                        'wave': 'Wave', 'orange': 'Orange Money', 'orange money': 'Orange Money',
                        'free': 'Free Money', 'especes': 'espèces', 'cash': 'espèces'
                    }
                    operateur = op_map.get(str(g).lower(), str(g).title())
            if montant and int(montant) > 0:
                result = template.replace('{montant}', f"{int(montant):,}".replace(',', ' ')).replace('{operateur}', operateur)
                print(f"[WOLOF STATIQUE CERTIFIÉ] : {result}")
                return result
    return None


def get_groq_client():
    """Initialise le client Groq officiel pour Whisper ultra-rapide."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except Exception as e:
        print(f"Erreur initialisation Groq : {e}")
        return None


def get_openai_client():
    """Initialise le client OpenAI officiel en fallback."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception as e:
        print(f"Erreur initialisation OpenAI : {e}")
        return None


def clean_transcription_text(text: str) -> str:
    """Nettoie le texte transcrit."""
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r'^(sous-titres|musique|bruit|applause)\b.*', '', t, flags=re.IGNORECASE).strip()
    return t


_local_whisper_model = None


def get_local_whisper_model():
    """Initialise le modèle Whisper local (0 FCFA, 100% autonome sur la machine)."""
    global _local_whisper_model
    if _local_whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            print("[WHISPER LOCAL] Chargement du moteur vocal local (INT8 CPU)...")
            # Utilise 'base' pour un excellent équilibre précision/vitesse sans aucun coût API
            _local_whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            print("[WHISPER LOCAL] Moteur vocal prêt !")
        except Exception as e:
            print(f"Erreur initialisation Whisper Local : {e}")
            try:
                from faster_whisper import WhisperModel
                _local_whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
            except Exception as e2:
                print(f"Erreur initialisation Whisper Tiny : {e2}")
                return None
    return _local_whisper_model


async def transcrire_note_vocale(media_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """
    Transcrit un fichier audio WhatsApp (OGG / OPUS / MP3 / M4A).
    Architecture résiliente à 3 niveaux :
    1. Groq Whisper Cloud (Ultra-rapide 200ms - si GROQ_API_KEY renseignée).
    2. Fallback OpenAI Whisper Cloud (si OPENAI_API_KEY avec quota).
    3. Fallback Whisper Local Haute Précision (100% gratuit, illimité, 0 FCFA, autonome sur PC).
    """
    ext = "ogg"
    if "mp3" in mime_type:
        ext = "mp3"
    elif "wav" in mime_type:
        ext = "wav"
    elif "m4a" in mime_type:
        ext = "m4a"
    elif "opus" in mime_type:
        ext = "opus"

    prompt_commerce = (
        "Note vocale commerciale à Dakar, Sénégal (Français et Wolof urbain dakarois). "
        "Expressions : Dama jaay 20000 ci Wave, jaay naa 15000, jënd naa marchandise, dug na, genn na, "
        "ana sama solde Wave, wax ma xaalis bi, am na ku ma lebal, fey naa, Wave, Orange Money, Free Money, "
        "FCFA, dërëm, junni, cash, espèces, facture, Senelec, Woyofal, Sen'Eau, boutique."
    )

    # 1. Tentative Groq Whisper (Prioritaire si clé présente - Vitesse 200ms)
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key and groq_api_key.strip():
        # Essai avec le SDK Groq officiel sur whisper-large-v3-turbo puis whisper-large-v3
        for groq_model in ["whisper-large-v3-turbo", "whisper-large-v3"]:
            try:
                groq_client = get_groq_client()
                if groq_client:
                    filename = f"voice_{uuid.uuid4().hex[:8]}.{ext}"
                    transcript = groq_client.audio.transcriptions.create(
                        file=(filename, media_bytes),
                        model=groq_model,
                        prompt=prompt_commerce,
                        temperature=0.0,
                        response_format="text"
                    )
                    res_text = clean_transcription_text(str(transcript))
                    if res_text:
                        print(f"[TRANSCRIPTION GROQ ({groq_model}) RÉUSSIE] : « {res_text} »")
                        return res_text
            except Exception as e_groq:
                print(f"Info Groq SDK ({groq_model}) : {e_groq}")

        # Fallback direct HTTP endpoint officiel Groq (https://api.groq.com/openai/v1/audio/transcriptions)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as http_client:
                files = {"file": (f"voice.{ext}", media_bytes, mime_type)}
                data = {
                    "model": "whisper-large-v3-turbo",
                    "prompt": prompt_commerce,
                    "response_format": "json"
                }
                headers = {"Authorization": f"Bearer {groq_api_key.strip()}"}
                resp = await http_client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    files=files,
                    data=data,
                    headers=headers
                )
                if resp.status_code == 200:
                    res_text = clean_transcription_text(resp.json().get("text", ""))
                    if res_text:
                        print(f"[TRANSCRIPTION GROQ HTTP DIRECT RÉUSSIE] : « {res_text} »")
                        return res_text
                else:
                    print(f"Erreur HTTP Groq ({resp.status_code}) : {resp.text}")
        except Exception as e_http:
            print(f"Erreur appel direct HTTP Groq : {e_http}")

    # 2. Fallback OpenAI Whisper
    openai_client = get_openai_client()
    if openai_client:
        try:
            audio_buffer = io.BytesIO(media_bytes)
            audio_buffer.name = f"whatsapp_voice.{ext}"
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_buffer,
                prompt=prompt_commerce,
                temperature=0.0
            )
            res_text = clean_transcription_text(transcript.text)
            if res_text:
                print(f"[TRANSCRIPTION OPENAI WHISPER RÉUSSIE] : « {res_text} »")
                return res_text
        except Exception as e:
            print(f"Info OpenAI Whisper fallback : {e}")

    # 3. Fallback Whisper Local INT8 (Autonome, 0 FCFA, fonctionne toujours)
    try:
        import tempfile
        model = get_local_whisper_model()
        if model:
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tf:
                tf.write(media_bytes)
                tmp_path = tf.name

            segments, info = model.transcribe(
                tmp_path,
                initial_prompt=prompt_commerce,
                beam_size=5,
                language=None
            )
            texte_segments = [s.text for s in segments]
            full_text = clean_transcription_text(" ".join(texte_segments))

            try:
                os.remove(tmp_path)
            except Exception:
                pass

            if full_text:
                print(f"[TRANSCRIPTION WHISPER LOCAL (0 FCFA) RÉUSSIE] ({info.language}) : « {full_text} »")
                return full_text
    except Exception as e_loc:
        print(f"Erreur transcription locale Whisper : {e_loc}")

    return None


# ---------------------------------------------------------------------------
# CONVERSION DES MONTANTS ET NOMBRES EN TOUTES LETTRES POUR TTS NATUREL
# Évite formellement que le synthétiseur épelle les chiffres un par un
# (ex: 50 000 FCFA -> cinquante mille francs CFA, au lieu de 'cinq zéro zéro...')
# ---------------------------------------------------------------------------
_UNITS_FR = ['', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf']
_TEENS_FR = ['dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf']
_TENS_FR = ['', 'dix', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante', 'soixante-dix', 'quatre-vingt', 'quatre-vingt-dix']


def _centaines_en_lettres(n: int) -> str:
    parts = []
    c = n // 100
    r = n % 100
    if c == 1:
        parts.append('cent')
    elif c > 1:
        parts.append(_UNITS_FR[c] + ' cent' + ('s' if r == 0 else ''))

    if r > 0:
        if r < 10:
            parts.append(_UNITS_FR[r])
        elif r < 20:
            parts.append(_TEENS_FR[r - 10])
        elif r < 70:
            d = r // 10
            u = r % 10
            if u == 1 and d < 8:
                parts.append(_TENS_FR[d] + ' et un')
            elif u > 0:
                parts.append(_TENS_FR[d] + '-' + _UNITS_FR[u])
            else:
                parts.append(_TENS_FR[d])
        elif r < 80:
            u = r - 60
            if u == 11:
                parts.append('soixante et onze')
            else:
                parts.append('soixante-' + (_TEENS_FR[u - 10] if u >= 10 else _UNITS_FR[u]))
        elif r < 90:
            u = r - 80
            if u == 0:
                parts.append('quatre-vingts')
            else:
                parts.append('quatre-vingt-' + _UNITS_FR[u])
        else:
            u = r - 80
            parts.append('quatre-vingt-' + _TEENS_FR[u - 10])
    return ' '.join(parts).strip()


def nombre_en_lettres_fr(n: int) -> str:
    """Convertit n'importe quel entier en français en toutes lettres naturel."""
    try:
        n = int(n)
    except Exception:
        return str(n)
    if n == 0:
        return 'zéro'
    if n < 0:
        return 'moins ' + nombre_en_lettres_fr(-n)

    parts = []
    # Milliards
    mrd = n // 1_000_000_000
    n %= 1_000_000_000
    if mrd == 1:
        parts.append('un milliard')
    elif mrd > 1:
        parts.append(_centaines_en_lettres(mrd) + ' milliards')

    # Millions
    mil = n // 1_000_000
    n %= 1_000_000
    if mil == 1:
        parts.append('un million')
    elif mil > 1:
        parts.append(_centaines_en_lettres(mil) + ' millions')

    # Milliers
    mille = n // 1_000
    r = n % 1_000
    if mille == 1:
        parts.append('mille')
    elif mille > 1:
        c_mille = _centaines_en_lettres(mille)
        if c_mille.endswith('cents'):
            c_mille = c_mille[:-1]
        parts.append(c_mille + ' mille')

    # Reste
    if r > 0:
        parts.append(_centaines_en_lettres(r))

    return ' '.join(parts).strip()


def normaliser_chiffres_en_lettres(texte: str) -> str:
    """
    Transforme les montants, les heures et les chiffres en mots en toutes lettres
    pour une élocution 100% humaine, fluide et naturelle par la voix Ava.
    """
    if not texte:
        return ""
    t = texte

    # 1. Heures usuelles
    t = re.sub(r'\b00[h:]00\b', 'minuit', t, flags=re.IGNORECASE)
    t = re.sub(r'\b06[h:]00\b', 'six heures', t, flags=re.IGNORECASE)
    t = re.sub(r'\b09[h:]00\b', 'neuf heures', t, flags=re.IGNORECASE)
    t = re.sub(r'\b11[h:]30\b', 'onze heures trente', t, flags=re.IGNORECASE)
    t = re.sub(r'\b12[h:]00\b', 'midi', t, flags=re.IGNORECASE)
    t = re.sub(r'\b15[h:]00\b', 'quinze heures', t, flags=re.IGNORECASE)
    t = re.sub(r'\b18[h:]00\b', 'dix-huit heures', t, flags=re.IGNORECASE)
    t = re.sub(r'\b20[h:]00\b', 'vingt heures', t, flags=re.IGNORECASE)
    t = re.sub(r'\b21[h:]00\b', 'vingt et une heures', t, flags=re.IGNORECASE)
    t = re.sub(r'\b23[h:]00\b', 'vingt-trois heures', t, flags=re.IGNORECASE)

    # 2. Montants avec devise (ex: 50 000 FCFA, 50,000 F, 10 000 FCFA, 330 F, 10k)
    def _remplacer_montant(m):
        raw_num = m.group(1).replace(' ', '').replace(',', '').replace('.', '').replace('\u00a0', '')
        if raw_num.isdigit():
            val = int(raw_num)
            lettres = nombre_en_lettres_fr(val)
            devise = m.group(2) or ''
            if re.search(r'fcfa|cfa|francs?', devise, re.IGNORECASE):
                devise_parlee = 'francs CFA'
            elif re.search(r'f\b', devise, re.IGNORECASE):
                devise_parlee = 'francs'
            else:
                devise_parlee = 'francs CFA'
            return f"{lettres} {devise_parlee}".strip()
        return m.group(0)

    t = re.sub(r'\b(\d+(?:[\s,.\u00a0]\d{3})*|\d+)\s*(fcfa|cfa|francs?\s*cfa|francs?|f)\b', _remplacer_montant, t, flags=re.IGNORECASE)

    # Notation k (ex: 10k -> dix mille francs CFA)
    def _remplacer_k(m):
        raw_num = m.group(1)
        if raw_num.isdigit():
            val = int(raw_num) * 1000
            return f"{nombre_en_lettres_fr(val)} francs CFA"
        return m.group(0)
    t = re.sub(r'\b(\d+)\s*k\b', _remplacer_k, t, flags=re.IGNORECASE)

    # 3. Nombres isolés (ex: 7 jours, 30 jours, 37 jours, 2 dépenses)
    def _remplacer_nombre_seul(m):
        raw = m.group(0)
        if raw.isdigit():
            val = int(raw)
            if val < 10_000_000:
                return nombre_en_lettres_fr(val)
        return raw

    t = re.sub(r'\b\d+\b', _remplacer_nombre_seul, t)
    return t


def extraire_phrase_orale(texte: str, langue: str = "fr") -> str:
    """
    Extrait ou compose une phrase orale concise, fluide et naturelle (1 à 2 phrases max)
    pour les notes vocales WhatsApp, en éliminant tout jargon technique, tableaux et puces.
    """
    if not texte:
        return ""

    # Éliminer le préfixe de transcription 'Note vocale comprise : ...'
    t = re.sub(r'Note vocale comprise\s*:\s*«[^»]*»\s*', '', texte, flags=re.IGNORECASE)
    t = re.sub(r'Note vocale comprise\s*:\s*[^\n]+\n*', '', t, flags=re.IGNORECASE)
    t = t.strip()

    # Détection des montants et natures pour formuler une réponse parlée impeccable
    m_vente = re.search(r'(?:vente|encaissement|jaay).*?([\d\s,.]+)\s*(?:fcfa|cfa|francs?)?.*?(wave|orange\s*money|free|espèces|cash)?', t, re.IGNORECASE)
    m_depense = re.search(r'(?:d[ée]pense|achat|j[ëe]nd).*?([\d\s,.]+)\s*(?:fcfa|cfa|francs?)?.*?(wave|orange\s*money|free|espèces|cash)?', t, re.IGNORECASE)

    def _fmt_amt(raw):
        clean = re.sub(r'[^\d]', '', str(raw or ""))
        if not clean:
            return ""
        return nombre_en_lettres_fr(int(clean))

    if langue == "wo":
        if m_vente and _fmt_amt(m_vente.group(1)):
            amt = _fmt_amt(m_vente.group(1))
            op = m_vente.group(2) or "Wave"
            return f"Jërejëf ! Sa jaay bu {amt} francs CFA ci {op} dug na bu baax te bind nañu ko."
        elif m_depense and _fmt_amt(m_depense.group(1)):
            amt = _fmt_amt(m_depense.group(1))
            return f"Sa dépense bu {amt} francs CFA bind nañu ko ci sa teere comptable."
    elif langue == "en":
        if m_vente and _fmt_amt(m_vente.group(1)):
            amt = _fmt_amt(m_vente.group(1))
            op = m_vente.group(2) or "Wave"
            return f"Your sale of {amt} CFA francs via {op} has been successfully recorded in your accounts."
        elif m_depense and _fmt_amt(m_depense.group(1)):
            amt = _fmt_amt(m_depense.group(1))
            return f"Your expense of {amt} CFA francs has been successfully recorded in your accounts."
    else:  # fr
        if m_vente and _fmt_amt(m_vente.group(1)):
            amt = _fmt_amt(m_vente.group(1))
            op = m_vente.group(2) or "Wave"
            return f"Votre vente de {amt} francs CFA sur {op} a bien été enregistrée dans vos comptes."
        elif m_depense and _fmt_amt(m_depense.group(1)):
            amt = _fmt_amt(m_depense.group(1))
            return f"Votre dépense de {amt} francs CFA a bien été enregistrée dans vos comptes."

    # Pour les réponses générales, phases d'onboarding ou explications :
    # Formater un texte oral naturel, complet (autoriser 1 à 2 minutes de parole, sans coupure artificielle)
    t_oral = t
    # Retrait des liens web
    t_oral = re.sub(r'https?://\S+', '', t_oral)
    # Remplacement des puces par des virgules ou pauses
    t_oral = re.sub(r'^[•\-\*]\s*', '', t_oral, flags=re.MULTILINE)
    # Nettoyage markdown
    t_oral = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', t_oral)
    t_oral = re.sub(r'#{1,6}\s*', '', t_oral)
    # Nettoyage des emojis
    t_oral = re.sub(r'[\U00010000-\U0010ffff]', '', t_oral)
    t_oral = re.sub(r'[\u2000-\u32ff]', '', t_oral)
    # Nettoyage des retours multiples
    t_oral = re.sub(r'\n+', '. ', t_oral)
    t_oral = re.sub(r'\s+', ' ', t_oral).strip()
    # Supprimer les répétitions de points
    t_oral = re.sub(r'\.{2,}', '.', t_oral)

    # Limite généreuse à 4000 caractères (environ 3 minutes de voix fluide et naturelle)
    return t_oral[:4000]


def adapter_phonetique_wolof(texte_wolof: str) -> str:
    """
    Rend le Wolof authentique parfaitement intelligible pour un synthétiseur vocal neural.
    Pas de distorsions agressives qui font épeler les mots lettre par lettre.
    """
    if not texte_wolof:
        return ""
    t = texte_wolof

    # Remplacements ciblés sur les mots usuels sans déformer les mots français
    t = re.sub(r'\bFCFA\b', 'francs CFA', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjërejëf\b', 'Jéréjéf', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjerejef\b', 'Jéréjéf', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjaay\b', 'diaye', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjënd\b', 'diènde', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjend\b', 'diènde', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdug na\b', 'doug na', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdugna\b', 'doug na', t, flags=re.IGNORECASE)
    t = re.sub(r'\bbu baax\b', 'bou bakh', t, flags=re.IGNORECASE)
    t = re.sub(r'\bbaax na\b', 'bakh na', t, flags=re.IGNORECASE)
    t = re.sub(r'\bci\b', 'tchi', t, flags=re.IGNORECASE)
    t = re.sub(r'\bca\b', 'tcha', t, flags=re.IGNORECASE)
    t = re.sub(r'\bxaalis\b', 'xaliss', t, flags=re.IGNORECASE)
    t = re.sub(r'\bxalis\b', 'xaliss', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdërëm\b', 'deureum', t, flags=re.IGNORECASE)
    t = re.sub(r'\bderem\b', 'deureum', t, flags=re.IGNORECASE)
    t = re.sub(r'\bñu\b', 'gnou', t, flags=re.IGNORECASE)
    t = re.sub(r'\bnañu\b', 'nagnou', t, flags=re.IGNORECASE)
    t = re.sub(r'\bbu\b', 'bou', t, flags=re.IGNORECASE)
    t = re.sub(r'\bleegi\b', 'léégi', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjunni\b', 'djiouni', t, flags=re.IGNORECASE)
    t = re.sub(r'\btollu\b', 'tollou', t, flags=re.IGNORECASE)

    return t


def adapter_texte_pour_oral(texte: str, langue: str = "fr") -> str:
    """Nettoie le texte pour l'élocution et remplace les acronymes pour éviter l'épellation."""
    if not texte:
        return ""
    t = re.sub(r'https?://\S+', '', texte)
    t = re.sub(r'[*_#`«»"~]', '', t)
    t = re.sub(r'^[•\-]\s*', '', t, flags=re.MULTILINE)
    t = re.sub(r'\n+', '. ', t).strip()

    # Remplacement systématique des acronymes comptables pour éviter qu'ils soient épelés lettre par lettre
    t = re.sub(r'\bSYSCOHADA\b', 'Siscohada', t, flags=re.IGNORECASE)
    t = re.sub(r'\bNINEA\b', 'Ninèya', t, flags=re.IGNORECASE)
    t = re.sub(r'\bRCCM\b', 'Registre de commerce', t, flags=re.IGNORECASE)
    t = re.sub(r'\bSMS\b', 'message', t, flags=re.IGNORECASE)
    t = re.sub(r'\bPME\b', 'P M E', t, flags=re.IGNORECASE)
    t = re.sub(r'\bTVA\b', 'T V A', t, flags=re.IGNORECASE)
    t = re.sub(r'\bHT\b', 'hors taxe', t)
    t = re.sub(r'\bTTC\b', 'toutes taxes comprises', t, flags=re.IGNORECASE)

    if langue in ["fr", "wo"]:
        t = re.sub(r'\bfrancs?\s*CFA\b', 'francs CFA', t, flags=re.IGNORECASE)
        t = re.sub(r'(?<!francs\s)\b(?:FCFA|CFA)\b', 'francs CFA', t, flags=re.IGNORECASE)
        t = re.sub(r'\bfrancs?\s+francs?\s*CFA\b', 'francs CFA', t, flags=re.IGNORECASE)
        # Normalisation automatique et systématique de TOUS les montants et nombres en lettres françaises
        # Empêche catégoriquement le synthétiseur vocal d'épeler les chiffres un à un
        t = normaliser_chiffres_en_lettres(t)
    elif langue == "en":
        t = re.sub(r'\bCFA\s*francs?\b', 'CFA francs', t, flags=re.IGNORECASE)
        t = re.sub(r'(?<!CFA\s)\b(?:FCFA|CFA)\b', 'CFA francs', t, flags=re.IGNORECASE)

    return t


MODEL_CLAUDE = "claude-haiku-4-5-20251001"
FALLBACK_CLAUDE = "claude-haiku-4-5-20251001"


def extraire_texte_message_claude(msg) -> str:
    """Extrait proprement le texte d'une réponse Claude en ignorant les ThinkingBlocks."""
    parts = []
    for block in getattr(msg, "content", []):
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
        elif hasattr(block, "text"):
            parts.append(block.text)
    return " ".join(parts).strip()


async def traduire_texte_en_wolof_oral(texte_francais: str) -> str:
    """
    Adapte un texte comptable français en wolof oral dakarois.
    Niveau 1 : Bibliotheque statique (0 FCFA, instantane).
    Niveau 2 : Claude Haiku (fallback si aucun template ne correspond).
    """
    # Niveau 1 : Traduction statique instantanee (0 FCFA)
    wolof_statique = traduire_wolof_statique(texte_francais)
    if wolof_statique:
        return wolof_statique

    # Niveau 2 : Claude Haiku (uniquement si necessite)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return texte_francais

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Tu es un commerçant sénégalais à Dakar.\n"
            "Traduis ce message comptable en Wolof dakarois authentique, simple et naturel (comme on parle au marché Sandaga ou HLM).\n"
            "Au Sénégal, les commerçants parlent wolof en gardant les termes techniques usuels (Wave, Orange Money, FCFA, solde, validé, etc.).\n"
            "Exemples exacts :\n"
            "- 'Votre encaissement Wave de 5 000 FCFA est validé.' -> 'Jërejëf ! Sa jaay bu 5 000 FCFA ci Wave dug na bu baax.'\n"
            "- 'Votre dépense de 10 000 FCFA en espèces est enregistrée en attente de reçu.' -> 'Sa dépense bu 10 000 FCFA ci espèces bind nañu ko ci attente. Nanga def foto reçu bi.'\n"
            "- 'Bonjour ! Comment puis-je vous aider aujourd'hui ?' -> 'Salaam alaikum ! Naka nga def tey ? Ban opération nga am ?'\n"
            "Réponds UNIQUEMENT avec la traduction wolof, sans guillemets ni explications.\n\n"
            f"Texte : {texte_francais}"
        )
        msg = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        wolof_text = extraire_texte_message_claude(msg)
        if wolof_text:
            print(f"[TRADUCTION WOLOF NATURELLE DAKAR] : {wolof_text}")
            return wolof_text
    except Exception as e:
        print(f"Info traduction Wolof Sonnet : {e}")

    return texte_francais


async def traduire_texte_en_anglais(texte_francais: str) -> str:
    """Traduit le texte en anglais fluide via Claude."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return texte_francais

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Translate this short financial accounting message into clean, friendly, professional African English. "
            "Keep CFA francs and amounts accurate. Reply with ONLY the English translation, no quotes, no extra text.\n\n"
            f"Text: {texte_francais}"
        )
        for m in [MODEL_CLAUDE, FALLBACK_CLAUDE]:
            try:
                msg = client.messages.create(
                    model=m,
                    max_tokens=250,
                    messages=[{"role": "user", "content": prompt}]
                )
                en_text = extraire_texte_message_claude(msg)
                if en_text:
                    print(f"[TRADUCTION ANGLAIS RÉUSSIE ({m})] : {en_text}")
                    return en_text
            except Exception as e_model:
                print(f"Erreur modèle {m} pour Anglais : {e_model}")
                continue
        return texte_francais
    except Exception as e:
        print(f"Info traduction Anglais : {e}")
        return texte_francais


_MMS_WOLOF_MODEL = None
_MMS_WOLOF_TOKENIZER = None


def get_mms_wolof_tts():
    """Charge ou retourne le modèle VITS Meta MMS Wolof en mémoire."""
    global _MMS_WOLOF_MODEL, _MMS_WOLOF_TOKENIZER
    if _MMS_WOLOF_MODEL is None or _MMS_WOLOF_TOKENIZER is None:
        try:
            from transformers import VitsModel, AutoTokenizer
            model_id = "rnjema-unima/mms-tts-wol-baseline"
            _MMS_WOLOF_TOKENIZER = AutoTokenizer.from_pretrained(model_id)
            _MMS_WOLOF_MODEL = VitsModel.from_pretrained(model_id)
            print("[META MMS WOLOF TTS CHARGÉ AVEC SUCCÈS]")
        except Exception as e_mms:
            print(f"Info chargement MMS Wolof : {e_mms}")
            return None, None
    return _MMS_WOLOF_MODEL, _MMS_WOLOF_TOKENIZER


def convertir_wav_en_ogg_opus(wav_path: str) -> str:
    """Convertit un WAV direct en OGG OPUS (Mono 48kHz natif WhatsApp)."""
    ogg_path = wav_path.rsplit(".", 1)[0] + ".ogg"
    try:
        import av
        in_container = av.open(wav_path)
        in_stream = in_container.streams.audio[0]

        out_container = av.open(ogg_path, "w", format="ogg")
        out_stream = out_container.add_stream("libopus", rate=48000)
        out_stream.layout = "mono"

        resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)

        for frame in in_container.decode(in_stream):
            frame.pts = None
            for resampled in resampler.resample(frame):
                for packet in out_stream.encode(resampled):
                    out_container.mux(packet)

        for packet in out_stream.encode():
            out_container.mux(packet)

        in_container.close()
        out_container.close()

        if os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 500:
            return os.path.basename(ogg_path)
    except Exception as e:
        print(f"Info conversion WAV vers OGG OPUS : {e}")

    return os.path.basename(wav_path)


def generer_note_vocale_mms_wolof(texte: str) -> str | None:
    """
    Synthèse vocale native Wolof via Meta MMS (mms-tts-wol).
    Normalise les montants bruts en mots en toutes lettres (ex: 45 000 FCFA -> ñent-fukk ak juróom junni francs CFA).
    Produit un fichier OGG OPUS avec la vraie prononciation native dakaroise.
    """
    try:
        from wolof_normalizer import normaliser_texte_wolof_pour_tts
        model, tokenizer = get_mms_wolof_tts()
        if not model or not tokenizer:
            return None

        # 1. Normalisation en Wolof intégral en toutes lettres
        texte_norm = normaliser_texte_wolof_pour_tts(texte)
        print(f"[META MMS WOLOF TEXTE NORMALISÉ] : « {texte_norm} »")

        import torch
        import soundfile as sf

        inputs = tokenizer(texte_norm, return_tensors="pt")
        with torch.no_grad():
            waveform = model(**inputs).waveform

        audio_dir = os.path.join(os.path.dirname(__file__), "static", "audio")
        os.makedirs(audio_dir, exist_ok=True)

        filename_wav = f"grow_mms_wo_{uuid.uuid4().hex[:8]}.wav"
        filepath_wav = os.path.join(audio_dir, filename_wav)

        output_np = waveform.squeeze().cpu().numpy()
        sf.write(filepath_wav, output_np, model.config.sampling_rate)

        if os.path.exists(filepath_wav) and os.path.getsize(filepath_wav) > 500:
            ogg_fn = convertir_wav_en_ogg_opus(filepath_wav)
            print(f"[NOTE VOCALE META MMS WOLOF GÉNÉRÉE] : {ogg_fn}")
            try:
                os.remove(filepath_wav)
            except Exception:
                pass
            return ogg_fn
    except Exception as e_mms_gen:
        print(f"Info génération Meta MMS Wolof : {e_mms_gen}")

    return None


async def generer_note_vocale_audio(texte: str, langue: str = "fr") -> str:
    """
    Génère une note vocale OGG OPUS (PTT) pour WhatsApp avec la voix officielle unique choisie :
    -> Ava (en-US-AvaMultilingualNeural) : Voix de femme de 25-30 ans, dynamique, chaleureuse, humaine.
    Ava est Multilingue et s'adapte à TOUS les vocaux sans exception (Français, Wolof, chiffres, bilans).
    """
    # 1. Extraction d'une phrase orale naturelle (concise, fluide, sans puces ni caractères bizarres)
    phrase_orale = extraire_phrase_orale(texte, langue="fr")
    if not phrase_orale:
        phrase_orale = texte

    try:
        import edge_tts
    except ImportError:
        print("Erreur : edge-tts n'est pas installé")
        return None

    # 2. Adaptation orale fluide pour un parlé naturel et sans hésitation
    texte_a_lire = adapter_texte_pour_oral(phrase_orale, langue="fr")

    # Si le texte contient des expressions en Wolof, on applique la phonétique dakaroise pour Ava
    if re.search(r'\b(jaay|diaye|jënd|diènde|dug|doug|jërejëf|jerejef|naka|xaalis|xaliss|waaw|deedet)\b', texte_a_lire, re.IGNORECASE):
        texte_a_lire = adapter_phonetique_wolof(texte_a_lire)

    # Nettoyage final des caractères spéciaux
    texte_a_lire = re.sub(r'[\"«»_~^]', '', texte_a_lire).strip()

    # 3. Voix officielle unique verrouillée pour 100% des vocaux Growth : Ava Multilingue
    voix_officielle = os.getenv("GROW_VOICE", "en-US-AvaMultilingualNeural")
    voix_candidates = [voix_officielle, "en-US-AvaMultilingualNeural", "fr-FR-VivienneMultilingualNeural"]
    print(f"[VOIX UNIQUE OFFICIELLE AVA SUR TOUS LES VOCAUX] : « {texte_a_lire} »")

    audio_dir = os.path.join(os.path.dirname(__file__), "static", "audio")
    os.makedirs(audio_dir, exist_ok=True)

    filename = f"grow_voice_ava_{uuid.uuid4().hex[:8]}.mp3"
    filepath = os.path.join(audio_dir, filename)

    speech_rate = os.getenv("GROW_VOICE_RATE", "-2%")

    for v in voix_candidates:
        try:
            communicate = edge_tts.Communicate(texte_a_lire, v, rate=speech_rate)
            await communicate.save(filepath)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 500:
                integrer_logo_mp3(filepath)
                ogg_fn = convertir_mp3_en_ogg_opus(filepath)
                print(f"[NOTE VOCALE OFFICIELLE GÉNÉRÉE (VOIX AVA)] : {ogg_fn}")
                return ogg_fn
        except Exception as e_v:
            print(f"Tentative voix {v} échouée : {e_v}")
            continue

    return None

    return None


def convertir_mp3_en_ogg_opus(mp3_path: str) -> str:
    """
    Convertit un MP3 en OGG OPUS (codec natif WhatsApp pour les vraies Notes Vocales).
    Sur WhatsApp, les fichiers MP3 affichent une icône générique casque jaune,
    alors que les fichiers OGG OPUS s'affichent comme de véritables Notes Vocales
    avec le logo officiel Growth du profil et l'onde sonore verte.
    """
    ogg_path = mp3_path.rsplit(".", 1)[0] + ".ogg"
    try:
        import av

        in_container = av.open(mp3_path)
        in_stream = in_container.streams.audio[0]

        out_container = av.open(ogg_path, "w", format="ogg")
        out_stream = out_container.add_stream("libopus", rate=48000)
        out_stream.layout = "mono"

        resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)

        for frame in in_container.decode(in_stream):
            frame.pts = None
            for resampled in resampler.resample(frame):
                for packet in out_stream.encode(resampled):
                    out_container.mux(packet)

        for packet in out_stream.encode():
            out_container.mux(packet)

        in_container.close()
        out_container.close()

        if os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 500:
            return os.path.basename(ogg_path)
    except Exception as e:
        print(f"Info conversion OGG OPUS : {e}")

    return os.path.basename(mp3_path)


def integrer_logo_mp3(filepath: str):
    """
    Intègre le logo officiel Growth dans les métadonnées ID3v2 (Cover Art APIC) du fichier MP3.
    """
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC, TIT2, TPE1

        logo_path = os.path.join(os.path.dirname(__file__), "static", "logo_cover_audio.jpg")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.path.dirname(__file__), "static", "logo_grow.jpg")

        if os.path.exists(logo_path):
            audio = MP3(filepath, ID3=ID3)
            try:
                audio.add_tags()
            except Exception:
                pass

            with open(logo_path, "rb") as f:
                logo_data = f.read()

            audio.tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,  # 3 = cover image front
                    desc="Growth Official Logo",
                    data=logo_data
                )
            )
            audio.tags.add(TIT2(encoding=3, text="Growth Assistant Comptable"))
            audio.tags.add(TPE1(encoding=3, text="Growth Dakar"))
            audio.save()
            print(f"[COVER ART LOGO GROWTH INTÉGRÉ] : {os.path.basename(filepath)}")
    except Exception as e:
        print(f"Info intégration logo MP3 : {e}")


def detecter_langue_texte(texte: str) -> str:
    """
    Détecte avec certitude la langue du texte (Wolof 'wo', Anglais 'en', ou Français 'fr').
    Ignore les citations et ne confond JAMAIS des termes financiers français comme 'cash' ou 'reçu' avec l'anglais.
    """
    if not texte:
        return "fr"

    # Nettoyage des citations éventuelles pour ne pas être pollué par du texte rapporté
    t_clean = re.sub(r'«[^»]*»', '', texte)
    t_clean = re.sub(r'"[^"]*"', '', t_clean)
    t_clean = re.sub(r'Note vocale comprise\s*:\s*[^\n]+', '', t_clean, flags=re.IGNORECASE)
    t_lower = t_clean.lower()

    # Mots et expressions caractéristiques du Wolof commercial dakarois
    wolof_patterns = [
        r'\bjaay\b', r'\bjaay na\b', r'\bdama jaay\b', r'\bjënd\b', r'\bjend\b',
        r'\bjënd na\b', r'\bdama jënd\b', r'\bxaalis\b', r'\bxalis\b', r'\bdug na\b',
        r'\bgenn na\b', r'\bfey na\b', r'\bam na\b', r'\bamna\b', r'\blebal\b',
        r'\bñata\b', r'\bnaka nga\b', r'\bsalaam alaikum\b', r'\bjërejëf\b',
        r'\bjerejef\b', r'\bwaaw\b', r'\bdeedet\b', r'\btiak tiak\b', r'\bkom-kom\b'
    ]
    if any(re.search(pat, t_lower) for pat in wolof_patterns):
        return "wo"

    # Mots et expressions caractéristiques de l'Anglais
    # Attention : 'cash', 'balance', 'receipt' sont d'usage courant en français à Dakar,
    # donc on n'utilise QUE de véritables marqueurs de phrases anglaises complètes !
    en_patterns = [
        r'\bhello\b', r'\bhi\b', r'\bplease\b', r'\bthank you\b', r'\bthanks\b',
        r'\bi sold\b', r'\bi bought\b', r'\bmy balance\b', r'\bgood morning\b',
        r'\bhow much\b', r'\bcan you\b', r'\brecord this\b', r'\bwhat is\b'
    ]
    if any(re.search(pat, t_lower) for pat in en_patterns):
        return "en"

    # Langue par défaut des affaires et de la comptabilité au Sénégal
    return "fr"

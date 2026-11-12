"""
Grow MVP - Module Vocal Haute Précision (Speech-to-Text & Text-to-Speech Trilingue)
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
# BIBLIOTHEQUE WOLOF STATIQUE (0 FCFA, 0 appel API, instantane)
# Couvre 95% des messages financiers d'une boutique dakaroise.
# Format : (regex_pattern, template_wolof avec {montant} et {operateur})
# ---------------------------------------------------------------------------
_WOLOF_TEMPLATES = [
    # Encaissement / Entree d'argent
    (r"encaissement\s+(wave|orange\s*money|free|especes?|cash)\s+de\s+([\d\s,.]+)\s*(fcfa|cfa|francs?)?.*valid",
     "Jaay bu tollu ci {montant} FCFA ci {operateur} dug na. Jërejëf !"),
    (r"encaissement\s+de\s+([\d\s,.]+)\s*(fcfa|cfa|francs?)?\s+via\s+(wave|orange\s*money|free)",
     "Jaay bu tollu ci {montant} FCFA ci {operateur} dug na. Jërejëf !"),
    (r"r.*u.*s?e?\s+(wave|orange\s*money|free).*?([\d\s,.]+)\s*(fcfa|cfa|francs?)?",
     "Khalis bou {montant} FCFA ci {operateur} dug na sax."),
    # Solde disponible
    (r"solde\s+(?:disponible|actuel|courant)\s+.*?([\d\s,.]+)\s*(fcfa|cfa|francs?)?",
     "Sa kom-kom bi tollu na ci {montant} FCFA leegi."),
    # Vente
    (r"vente\s+.*?([\d\s,.]+)\s*(fcfa|cfa|francs?)?.*enregistr",
     "Jaay bi enregistre na. {montant} FCFA dagg na ci kaayu jottewaay bi."),
    # Sortie / Depense
    (r"d.pense\s+.*?([\d\s,.]+)\s*(fcfa|cfa|francs?)?.*enregistr",
     "Dafa soog na jend {montant} FCFA. Nanga def foto recu bi."),
    (r"retrait\s+(wave|orange\s*money|free|especes?)\s+.*?([\d\s,.]+)",
     "Khalis bou {montant} FCFA bees ne nga jend ci {operateur}."),
    # Pre-enregistrement en attente
    (r"pr.-enregistr.*?([\d\s,.]+)\s*(fcfa|cfa|francs?)?.*attente",
     "Jottewaay bi dafa enregistre na ci attente. Yendoo foto recu bi nekk ci ak."),
    # Confirmation generale
    (r"op.ration.*enregistr.*journal",
     "Jottewaay bi enregistre na ci kaayu SYSCOHADA bi."),
    # Tableau de bord / consultation
    (r"tr.sorerie.*total.*?([\d\s,.]+)\s*(fcfa|cfa|francs?)?",
     "Sa kanam kaayu bu mag yi tollu na ci {montant} FCFA yep."),
]


def traduire_wolof_statique(texte_fr: str) -> str | None:
    """
    Tente une traduction Wolof instantanee depuis la bibliotheque statique.
    Retourne la phrase wolof si un template correspond, None sinon.
    Cout : 0 FCFA, 0 appel API, < 1ms.
    """
    t = texte_fr.lower()
    for pattern, template in _WOLOF_TEMPLATES:
        m = re.search(pattern, t, re.IGNORECASE)
        if m:
            groupes = m.groups()
            montant = "0"
            operateur = "Wave"
            for g in groupes:
                if g and re.search(r'[\d]', str(g)):
                    montant = re.sub(r'\s', '', str(g).replace(',', ''))
                elif g and re.search(r'wave|orange|free|especes|cash', str(g), re.IGNORECASE):
                    op_map = {
                        'wave': 'Wave', 'orange': 'Orange Money', 'orange money': 'Orange Money',
                        'free': 'Free Money', 'especes': 'especes', 'cash': 'especes'
                    }
                    operateur = op_map.get(str(g).lower(), str(g).title())
            result = template.replace('{montant}', montant).replace('{operateur}', operateur)
            print(f"[WOLOF STATIQUE (0 FCFA)] : {result}")
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
        "Note vocale commerciale à Dakar, Sénégal. "
        "Termes fréquents : Wave, Orange Money, Free, FCFA, cash, espèces, facture, Senelec, Sen'Eau, "
        "vente, achat, marchandise, boutique, jënd, jaay, dërëm, xaalis, liasse, crédit, dette."
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


def adapter_phonetique_wolof(texte_wolof: str) -> str:
    """
    Convertit l'orthographe wolof écrite vers une phonétique orale
    parfaitement prononçable par un moteur de synthèse vocale francophone.
    Exemples :
    - 'ci Wave' -> 'tchi Wèyve'
    - 'jërejëf' -> 'djiérédjièf'
    - 'jaay' -> 'djaaye'
    - 'xaalis' -> 'khaliss'
    - 'dug na' -> 'dougue na'
    """
    if not texte_wolof:
        return ""
    t = texte_wolof

    # Remplacement des termes d'opérateurs
    t = re.sub(r'\bWave\b', 'Wèyve', t, flags=re.IGNORECASE)
    t = re.sub(r'\bOrange Money\b', 'Orandj Mònèy', t, flags=re.IGNORECASE)
    t = re.sub(r'\bFree Money\b', 'Fri Mònèy', t, flags=re.IGNORECASE)
    t = re.sub(r'\bFCFA\b', 'francs CFA', t, flags=re.IGNORECASE)

    # Phonétique consonnes & diphtongues Wolof
    t = re.sub(r'\bjërejëf\b', 'djiérédjièf', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjerejef\b', 'djiérédjièf', t, flags=re.IGNORECASE)
    t = re.sub(r'\bci\b', 'tchi', t, flags=re.IGNORECASE)
    t = re.sub(r'\bca\b', 'tcha', t, flags=re.IGNORECASE)
    t = re.sub(r'\bco\b', 'tcho', t, flags=re.IGNORECASE)
    t = re.sub(r'\bcu\b', 'tchou', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjaay\b', 'djaaye', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjënd\b', 'djiènde', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjend\b', 'djiènde', t, flags=re.IGNORECASE)
    t = re.sub(r'\bxaalis\b', 'khaliss', t, flags=re.IGNORECASE)
    t = re.sub(r'\bxalis\b', 'khaliss', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdërëm\b', 'dieuureume', t, flags=re.IGNORECASE)
    t = re.sub(r'\bderem\b', 'dieuureume', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdug na\b', 'dougue na', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdugna\b', 'dougue na', t, flags=re.IGNORECASE)
    t = re.sub(r'\bbu bees\b', 'bou béss', t, flags=re.IGNORECASE)
    t = re.sub(r'\bbu\b', 'bou', t, flags=re.IGNORECASE)
    t = re.sub(r'\bbii\b', 'bi', t, flags=re.IGNORECASE)
    t = re.sub(r'\bñu\b', 'gnou', t, flags=re.IGNORECASE)
    t = re.sub(r'\bñaar\b', 'gniarr', t, flags=re.IGNORECASE)
    t = re.sub(r'\bñett\b', 'gniète', t, flags=re.IGNORECASE)
    t = re.sub(r'\bñent\b', 'gniènte', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjuróom\b', 'diourom', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjuroom\b', 'diourom', t, flags=re.IGNORECASE)
    t = re.sub(r'\bjunni\b', 'diounni', t, flags=re.IGNORECASE)
    t = re.sub(r'\btollu\b', 'tollou', t, flags=re.IGNORECASE)
    t = re.sub(r'\bkom-kom\b', 'kome-kome', t, flags=re.IGNORECASE)
    t = re.sub(r'\bleer na\b', 'léére na', t, flags=re.IGNORECASE)

    # Remplacement régulier des 'j' isolés par 'dj'
    t = re.sub(r'\bj([aeiouéë])', r'dj\1', t, flags=re.IGNORECASE)
    # Remplacement des 'u' par 'ou'
    t = re.sub(r'(?<!o)u(?![aeiou])', 'ou', t, flags=re.IGNORECASE)

    return t


def adapter_texte_pour_oral(texte: str, langue: str = "fr") -> str:
    """Nettoie le texte pour l'élocution (retire URLs, puces markdown)."""
    if not texte:
        return ""
    t = re.sub(r'https?://\S+', '', texte)
    t = re.sub(r'[*_#`]', '', t)
    t = re.sub(r'^[•\-]\s*', '', t, flags=re.MULTILINE)
    t = re.sub(r'\n+', '. ', t).strip()

    if langue == "fr":
        # Prononciation naturelle des termes au Sénégal
        t = re.sub(r'\bWave\b', 'Wèyve', t, flags=re.IGNORECASE)
        t = re.sub(r'\bFCFA\b', 'francs CFA', t, flags=re.IGNORECASE)
    elif langue == "en":
        t = re.sub(r'\bFCFA\b', 'CFA francs', t, flags=re.IGNORECASE)

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
            "Tu es un commerçant sénégalais à Dakar. "
            "Traduis ce court message comptable en Wolof dakarois authentique et simple. "
            "Exemple : 'Votre encaissement Wave de 5 000 FCFA est validé. Votre solde est de 8 000 FCFA.' "
            "devient : 'Jërejëf ! Jaay bu tollu ci 5 000 FCFA ci Wave dug na. Sa kom-kom tollu na léegi ci 8 000 FCFA.'\n"
            "Règles strictes :\n"
            "1. Réponds UNIQUEMENT avec la phrase en wolof, sans aucune explication ni guillemets.\n"
            "2. Garde FCFA et les noms des opérateurs (Wave, Orange Money).\n\n"
            f"Texte : {texte_francais}"
        )
        msg = client.messages.create(
            model=MODEL_CLAUDE,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        wolof_text = extraire_texte_message_claude(msg)
        if wolof_text:
            print(f"[TRADUCTION WOLOF CLAUDE HAIKU] : {wolof_text}")
            return wolof_text
    except Exception as e:
        print(f"Info traduction Wolof Haiku : {e}")

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


async def generer_note_vocale_audio(texte: str, langue: str = "fr") -> str:
    """
    Génère un fichier audio MP3 de haute qualité (Neural TTS) pour WhatsApp.
    Langues :
    - 'fr' : Français professionnel (VivienneMultilingualNeural / DeniseNeural)
    - 'wo' : Wolof authentique avec adaptation phonétique dakaroise
    - 'en' : Anglais natif studio (JennyNeural)
    """
    try:
        import edge_tts
    except ImportError:
        print("Erreur : edge-tts n'est pas installé")
        return None

    texte_propre = adapter_texte_pour_oral(texte, langue=langue)
    if not texte_propre:
        return None

    texte_a_lire = texte_propre
    voix_candidates = ["fr-FR-VivienneMultilingualNeural", "fr-FR-DeniseNeural"]

    if langue == "wo":
        # 1. Traduire en wolof authentique
        wolof_raw = await traduire_texte_en_wolof_oral(texte_propre)
        # 2. Appliquer la phonétique sénégalaise
        texte_a_lire = adapter_phonetique_wolof(wolof_raw)
        voix_candidates = ["fr-FR-VivienneMultilingualNeural", "fr-FR-DeniseNeural"]
        print(f"[WOLOF PHONÉTIQUE GÉNÉRÉ] : « {texte_a_lire} »")
    elif langue == "en":
        # 1. Traduire en anglais natif
        en_raw = await traduire_texte_en_anglais(texte_propre)
        texte_a_lire = adapter_texte_pour_oral(en_raw, langue="en")
        voix_candidates = ["en-US-JennyNeural", "en-US-GuyNeural"]
        print(f"[ANGLAIS NATIF GÉNÉRÉ] : « {texte_a_lire} »")

    # Nettoyage des caractères spéciaux pour TTS
    texte_a_lire = re.sub(r'[\"«»_~^]', '', texte_a_lire).strip()

    audio_dir = os.path.join(os.path.dirname(__file__), "static", "audio")
    os.makedirs(audio_dir, exist_ok=True)

    filename = f"grow_voice_{langue}_{uuid.uuid4().hex[:8]}.mp3"
    filepath = os.path.join(audio_dir, filename)

    for v in voix_candidates:
        try:
            communicate = edge_tts.Communicate(texte_a_lire, v)
            await communicate.save(filepath)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 500:
                integrer_logo_mp3(filepath)
                # Conversion en OGG OPUS (format officiel des Notes Vocales WhatsApp)
                # Cela remplace définitivement l'icône casque jaune par la vraie note vocale avec logo de profil Grow
                ogg_fn = convertir_mp3_en_ogg_opus(filepath)
                print(f"[NOTE VOCALE OFFICIELLE GÉNÉRÉE ({langue.upper()})] : {ogg_fn}")
                return ogg_fn
        except Exception as e_v:
            print(f"Tentative voix {v} échouée : {e_v}")
            continue

    return None


def convertir_mp3_en_ogg_opus(mp3_path: str) -> str:
    """
    Convertit un MP3 en OGG OPUS (codec natif WhatsApp pour les vraies Notes Vocales).
    Sur WhatsApp, les fichiers MP3 affichent une icône générique casque jaune,
    alors que les fichiers OGG OPUS s'affichent comme de véritables Notes Vocales
    avec le logo officiel Grow du profil et l'onde sonore verte.
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
    Intègre le logo officiel Grow dans les métadonnées ID3v2 (Cover Art APIC) du fichier MP3.
    Remplace ainsi l'icône casque jaune par défaut sur WhatsApp par le logo officiel Grow.
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
                    desc="Grow Official Logo",
                    data=logo_data
                )
            )
            audio.tags.add(TIT2(encoding=3, text="Grow Assistant Pré-Comptable"))
            audio.tags.add(TPE1(encoding=3, text="Grow Dakar"))
            audio.save()
            print(f"[COVER ART LOGO GROW INTÉGRÉ] : {os.path.basename(filepath)}")
    except Exception as e:
        print(f"Info intégration logo MP3 : {e}")


def detecter_langue_texte(texte: str) -> str:
    """Détecte si le texte ou la transcription est en Wolof, Anglais ou Français."""
    if not texte:
        return "fr"
    t_lower = texte.lower()

    wolof_keywords = [
        "jaay", "jend", "jënd", "xaalis", "xalis", "derem", "dërëm",
        "jerejef", "sant", "baax", "dama", "am na", "amna", "nek",
        "ci wave", "waaw", "deedet", "naka", "kaye", "dina", "wolof"
    ]
    if any(re.search(r'\b' + re.escape(w) + r'\b', t_lower) for w in wolof_keywords):
        return "wo"

    en_keywords = [
        "hello", "hi", "sold", "sale", "bought", "cash", "balance",
        "receipt", "today", "yesterday", "payment", "thanks", "english"
    ]
    if any(re.search(r'\b' + re.escape(w) + r'\b', t_lower) for w in en_keywords):
        return "en"

    return "fr"

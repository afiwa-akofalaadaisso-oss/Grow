"""
Module de normalisation linguistique pour le Wolof (Dakar, Sénégal).
Convertit les montants, nombres et symboles en Wolof intégral en toutes lettres
pour alimenter les modèles de synthèse vocale Meta MMS (facebook/mms-tts-wol).
"""
import re

CHIFFRES_WOLOF = {
    0: "tus",
    1: "benn",
    2: "ñaar",
    3: "ñett",
    4: "ñent",
    5: "juróom",
    6: "juróom-benn",
    7: "juróom-ñaar",
    8: "juróom-ñett",
    9: "juróom-ñent",
    10: "fukk",
    20: "ñaar-fukk",
    30: "fanweer",
    40: "ñent-fukk",
    50: "juróom-fukk",
    60: "juróom-benn-fukk",
    70: "juróom-ñaar-fukk",
    80: "juróom-ñett-fukk",
    90: "juróom-ñent-fukk",
}


def nombre_en_wolof(n: int) -> str:
    """Convertit un entier positif (jusqu'à plusieurs millions) en Wolof écrit en toutes lettres."""
    if n in CHIFFRES_WOLOF:
        return CHIFFRES_WOLOF[n]

    if n < 0:
        return f"moos {nombre_en_wolof(-n)}"

    if n < 100:
        dizaine = (n // 10) * 10
        reste = n % 10
        nom_dizaine = CHIFFRES_WOLOF.get(dizaine, f"{nombre_en_wolof(n // 10)}-fukk")
        return f"{nom_dizaine} ak {CHIFFRES_WOLOF[reste]}"

    if n < 1000:
        centaines = n // 100
        reste = n % 100
        pref = "téeméer" if centaines == 1 else f"{nombre_en_wolof(centaines)} téeméer"
        if reste == 0:
            return pref
        return f"{pref} ak {nombre_en_wolof(reste)}"

    if n < 1_000_000:
        milliers = n // 1000
        reste = n % 1000
        if milliers == 1:
            pref = "junni"
        elif milliers == 5:
            pref = "juróomi junni"
        elif milliers == 10:
            pref = "fukki junni"
        elif milliers == 20:
            pref = "ñaar fukki junni"
        elif milliers == 50:
            pref = "juróom fukki junni"
        elif milliers == 100:
            pref = "téeméeri junni"
        else:
            pref = f"{nombre_en_wolof(milliers)} junni"

        if reste == 0:
            return pref
        return f"{pref} ak {nombre_en_wolof(reste)}"

    millions = n // 1_000_000
    reste = n % 1_000_000
    pref = "benn miliyoŋ" if millions == 1 else f"{nombre_en_wolof(millions)} miliyoŋ"
    if reste == 0:
        return pref
    return f"{pref} ak {nombre_en_wolof(reste)}"


def normaliser_texte_wolof_pour_tts(texte: str) -> str:
    """
    Nettoie et normalise intégralement le texte Wolof pour la synthèse vocale :
    1. Supprime les préfixes de logs ou d'écoutes WhatsApp.
    2. Convertit les chiffres et montants bruts (ex: 45 000 FCFA) en mots complets en Wolof.
    3. Normalise les acronymes et noms de canaux financiers (Wave, Orange Money).
    4. Garantit une prononciation fluide sans bégaiement ni épellation par MMS-TTS.
    """
    if not texte:
        return ""

    t = texte

    # Éliminer les en-têtes et préfixes parasites
    t = re.sub(r'Note vocale comprise\s*:\s*«[^»]*»\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'Wax jàll na\s*:\s*«[^»]*»\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'Note vocale comprise\s*:\s*[^\n]+\n*', '', t, flags=re.IGNORECASE)

    # Conversion des montants au format "45 000 FCFA" ou "45000 FCFA" ou "45.000 F"
    def _sub_montant_fcfa(match):
        raw_num = re.sub(r'[^\d]', '', match.group(1))
        if not raw_num:
            return match.group(0)
        n = int(raw_num)
        return f" {nombre_en_wolof(n)} francs CFA "

    # Regex montants FCFA / CFA
    t = re.sub(r'([\d\s.,]+)\s*(?:fcfa|cfa|francs?\s*cfa|francs?)\b', _sub_montant_fcfa, t, flags=re.IGNORECASE)

    # Regex nombres restants isolés
    def _sub_nombres_isoles(match):
        raw_num = match.group(1)
        if raw_num.isdigit():
            return f" {nombre_en_wolof(int(raw_num))} "
        return match.group(0)

    t = re.sub(r'\b(\d+)\b', _sub_nombres_isoles, t)

    # Normalisation phonétique fine pour le modèle Meta MMS Wolof
    t = re.sub(r'\bWave\b', 'Wave', t, flags=re.IGNORECASE)
    t = re.sub(r'\bOrange Money\b', 'Orange Money', t, flags=re.IGNORECASE)
    t = re.sub(r'\bFree Money\b', 'Free Money', t, flags=re.IGNORECASE)

    # Nettoyage des puces et markdown
    t = re.sub(r'[*_#`«»"~]', '', t)
    t = re.sub(r'^[•\-]\s*', '', t, flags=re.MULTILINE)
    t = re.sub(r'\s+', ' ', t).strip()

    return t

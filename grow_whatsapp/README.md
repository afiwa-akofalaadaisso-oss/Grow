# 📱 Livrable 1 : Grow Copilote WhatsApp & Vocal IA (SYSCOHADA)

Bienvenue dans le code source du **Copilote Financier WhatsApp Grow**, conçu pour les PME et commerçants d'Afrique de l'Ouest (Sénégal / zone UEMOA).

---

## 🎯 Objectif du Livrable
Permettre à un entrepreneur sénégalais d'enregistrer instantanément ses recettes, dépenses et factures directement sur WhatsApp :
* **Par note vocale en Wolof ou en Français** (ex: *"Dafa ma jënd 50 000 FCFA tissus wax ci marché HLM"*).
* **Par message texte** (ex: *"Achat fournitures de bureau 25000 chez Papeterie Teranga par Wave"*).
* **Par photo de reçu ou capture de paiement Wave / Orange Money**.

Le moteur analyse le message, extrait le montant, catégorise automatiquement l'écriture dans le **Plan Comptable SYSCOHADA Révisé**, l'enregistre en base de données et répond à l'utilisateur par message et note vocale de confirmation.

---

## 🧩 Architecture des Fichiers

| Fichier | Rôle & Responsabilité |
|---|---|
| `voice_processor.py` | **Moteur Vocal Principal** : Synthèse vocale TTS (EdgeTTS / ElevenLabs) et transcription multilingue. |
| `gemini_audio_processor.py` | **Transcription IA Multimodale** : Utilise Google Gemini Flash pour comprendre les notes vocales avec bruits de fond de marché. |
| `wolof_normalizer.py` | **Normalisation Wolof / Français** : Dictionnaire phonétique convertissant le vocabulaire commercial wolof (*jënd*, *jaay*, *dërëm*, *wari*) en concepts SYSCOHADA. |
| `smart_classifier.py` | **Classificateur SYSCOHADA** : Détermine le compte exact (ex: `601` Achats, `701` Ventes, `622` Locations, `638` Frais télécoms). |
| `local_extractor.py` | **Moteur d'Extraction Regex & NLP Local** : Détection ultra-rapide des montants FCFA, dates, modes de règlement (Wave, OM, Espèces, Banque) et tiers. |
| `conversation_supervisor.py` | **Superviseur de Dialogue** : Gestionnaire de contexte pour les conversations multi-tours et demandes de clarification. |
| `expert_assistant.py` | **Assistant Pré-Comptable IA** : Répond aux questions financières posées par l'entrepreneur sur WhatsApp. |
| `onboarding_states.json` | État d'avancement du parcours d'onboarding WhatsApp des nouvelles PME. |
| `fournisseurs_memoire.json` | Mémoire locale des tiers habituels de chaque entreprise cliente. |
| `audio_samples/` | Échantillons audio de tests (notes vocales réelles en Wolof et Français). |

---

## 🔄 Flux de Traitement d'un Message WhatsApp

```
1. Utilisateur WhatsApp (Vocal ou Texte)
          │
          ▼
2. Webhook Récepteur (Twilio / Meta Cloud API)
          │
          ▼
3. Analyse Vocale (gemini_audio_processor.py / voice_processor.py)
          │
          ▼
4. Normalisation Linguistique (wolof_normalizer.py)
          │
          ▼
5. Extraction & Classification (local_extractor.py + smart_classifier.py)
   -> Montant Net FCFA
   -> Date d'opération
   -> Compte SYSCOHADA Révisé (ex: 601, 701, 5213 Wave)
          │
          ▼
6. Persistance Automatique (Supabase Cloud + SQLite Replica)
          │
          ▼
7. Réponse WhatsApp instantanée avec reçu numérique & note vocale de confirmation
```

---

## ⚙️ Configuration & Variables d'Environnement
Ce module s'appuie sur le fichier `.env` partagé :
* `GEMINI_API_KEY` : Clé d'API Google Gemini pour l'audio et la classification.
* `TWILIO_ACCOUNT_SID` & `TWILIO_AUTH_TOKEN` : Identifiants WhatsApp Twilio.
* `WHATSAPP_PHONE_NUMBER` : Numéro officiel du bot (ex: `+221 78 877 38 27`).

# 🚀 Grow MVP — Copilote Financier & Assistant Pré-Comptable SYSCOHADA (Dakar, Sénégal)

Grow est une solution fintech & pré-comptable conçue pour l'Afrique de l'Ouest (Sénégal / zone UEMOA), connectant les PME et commerçants à leurs experts-comptables via **WhatsApp** et un **Logiciel Web professionnel**.

---

## 🏗️ Architecture Globale en 2 Grands Livrables

Le projet est structuré en deux grands livrables autonomes partageant un socle de données unifié :

```mermaid
flowchart TD
    subgraph L1["📱 LIVRABLE 1 : grow_whatsapp/"]
        W1[Notes Vocales Wolof / FR]
        W2[Messages & Reçus WhatsApp]
        W3[Transcription IA Gemini Flash]
        W4[Moteur SYSCOHADA Révisé]
        W1 --> W3
        W2 --> W4
        W3 --> W4
    end

    subgraph Shared["🗄️ SOCLE COMMUN : grow_shared/"]
        DB1[(Supabase Cloud PostgreSQL)]
        DB2[(SQLite Replica Locale)]
        DB1 <--> DB2
    end

    subgraph L2["💻 LIVRABLE 2 : grow_logiciel_comptable/"]
        D1[Portail Accueil Scandinave]
        D2[Grand-Livre & Rapprochement]
        D3[Bilan & SIG SYSCOHADA]
        D4[Visa & Scellement ONECCA]
        D1 --> D2
        D2 --> D3
        D3 --> D4
    end

    W4 -->|Écritures instantanées| DB1
    DB1 -->|Synchronisation temps réel| D2
```

---

## 📂 Organisation des Dossiers du Projet

```
Grow-mvp/
│
├── 📁 grow_whatsapp/                # LIVRABLE 1 : Copilote Financier WhatsApp
│   ├── voice_processor.py           # Moteur vocal (MMS Wolof, EdgeTTS, ElevenLabs)
│   ├── gemini_audio_processor.py    # Transcription multimodale Google Gemini Flash
│   ├── wolof_normalizer.py          # Dictionnaire phonétique Wolof -> SYSCOHADA
│   ├── smart_classifier.py          # Règles d'imputation comptable SYSCOHADA
│   ├── local_extractor.py           # Extraction regex & parsing (montants FCFA, dates, tiers)
│   ├── conversation_supervisor.py   # Gestion de dialogue contextuel
│   ├── expert_assistant.py          # Assistant financier conversationnel
│   ├── audio_samples/               # Échantillons audio réels de tests (Wolof & Français)
│   └── README.md                    # Documentation complète du Livrable 1
│
├── 📁 grow_logiciel_comptable/      # LIVRABLE 2 : Logiciel Web Expert-Comptable
│   ├── templates/                   # Interfaces Utilisateur Web Jinja2
│   │   ├── dashboard.html           # Portail accueil, Grand-Livre, Bilan, SIG, Saisie, ONECCA
│   │   ├── agence.html              # Vue Cabinet multi-dossiers PME
│   │   └── abonnement.html          # Gestion des abonnements SaaS Wave / OM
│   ├── static/                      # Logos squircle, favicons, branding et styles
│   └── README.md                    # Documentation complète du Livrable 2
│
├── 📁 grow_shared/                  # SOCLE COMMUN PARTAGÉ
│   ├── database.py                  # Connecteur unifié Supabase PostgreSQL + SQLite
│   ├── grow_compta.db               # Base SQLite locale répliquée
│   ├── .env.example                 # Gabarit des variables d'environnement
│   └── README.md                    # Documentation de la base de données & schéma
│
└── 📁 chat_grow/                    # RUNTIME SERVEUR (FastAPI & Uvicorn)
    ├── main.py                      # Point d'entrée de l'application FastAPI
    └── ...
```

---

## ⚡ Démarrage Rapide pour un Développeur

### 1. Cloner et installer les dépendances
```bash
git clone https://github.com/ton-repo/Grow-mvp.git
cd Grow-mvp
pip install -r requirements.txt   # FastAPI, Uvicorn, Twilio, Supabase, Google-GenerativeAI
```

### 2. Configurer les variables d'environnement
Copiez `grow_shared/.env.example` vers `.env` et complétez vos clés :
```bash
cp grow_shared/.env.example chat_grow/.env
```

### 3. Lancer l'application
```bash
cd chat_grow
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

* **Logiciel Web Comptable** : Ouvrez [http://localhost:8000/dashboard?portal=1](http://localhost:8000/dashboard?portal=1)
* **Webhook WhatsApp** : L'URL est `http://localhost:8000/webhook` (exposable publiquement via Cloudflare Tunnel ou Ngrok).

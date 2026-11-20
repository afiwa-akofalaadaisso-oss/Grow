# 💻 Livrable 2 : Grow Logiciel Web Expert-Comptable & Dashboard

Bienvenue dans le code source du **Logiciel Web pour Experts-Comptables et Cabinets Grow**, connecté en direct aux flux WhatsApp des PME sénégalaises.

---

## 🎯 Objectif du Livrable
Offrir aux experts-comptables, auditeurs et dirigeants d'entreprises une interface web moderne, rapide et certifiée conforme aux normes **SYSCOHADA Révisé** et **ONECCA** :
* **Portail d'Accueil Scandinave** avec recherche multi-critères universelle (NINEA, Téléphone, Nom).
* **Grand-Livre & Journal Général** en temps réel avec filtres par classe comptable (1 à 8) et source de trésorerie (Wave, Orange Money, Caisse Espèces, Banque).
* **Contrôle de Conformité Bilantielle** avec vérification automatique de l'équilibre Actif Net = Passif Total.
* **Soldes Intermédiaires de Gestion (SIG)** : Marge commerciale, Valeur Ajoutée (VA), Excédent Brut d'Exploitation (EBE) et Résultat Net.
* **Scellement Numérique ONECCA** : Horodatage déterministe et empreinte SHA-256 infalsifiable pour télédéclaration DGID Sen-E-Tax.
* **Interface Responsive Hybride** : Optimisée pour grand écran (Poste Comptable) et smartphone (Dirigeant mobile).

---

## 🧩 Architecture des Fichiers

```
grow_logiciel_comptable/
├── templates/
│   ├── dashboard.html    # Application Web Principale (Portail, Grand-Livre, Bilan, Modales, Saisie)
│   ├── agence.html       # Espace Multi-Dossiers Cabinet (Gestion de portefeuille PME)
│   └── abonnement.html   # Portail Abonnements SaaS & Paiements Wave / Orange Money
│
└── static/               # Assets graphiques et multimédias
    ├── grow_icon_squircle.png     # Logo officiel squircle sombre
    ├── grow_brand_teal.png        # Logo horizontal vert d'eau
    ├── favicon_dark.png           # Icône d'onglet
    ├── audio/                     # Notes vocales générées en cache
    └── ...
```

---

## 🖥️ Fonctionnalités Clés de `dashboard.html`

1. **Portail d'Accueil (`#viewPortalComptable`)** :
   - Canevas de points interactifs animés en HTML5 Canvas à 60 FPS avec ondulation fluide et répulsion magnétique au curseur.
   - Barre de recherche sans contour bleu parasite, filtrage instantané sur la liste des entreprises du cabinet.
   - Scénario de vol cinématique du logo lors de la sélection d'un dossier.

2. **Journal des Écritures & Grand-Livre (`#viewJournal`)** :
   - Tableau Factoo avec numéros de pièces, libellés, comptes SYSCOHADA et montants colorés (Recette en vert, Dépense en sombre).
   - Menu déroulant sur-mesure pour filtrer par compte (Ventes `70`, Achats `60`, Services `62/63`, Trésorerie `52/57`, etc.).
   - Sélecteur de date moderne avec calendrier complet sur-mesure (non tronqué).

3. **Bilan & SIG SYSCOHADA Révisé (`#viewBilan`)** :
   - Double colonne Actif (Emplois) / Passif (Ressources).
   - Bannière blanche épurée affichant le statut d'équilibre et les écarts détectés en FCFA.
   - Calcul temps réel des SIG.

4. **Modale de Saisie Rapide Directe (`#modalQuickTx`)** :
   - Permet au comptable ou au dirigeant de saisir une transaction manuelle en quelques secondes avec affectation SYSCOHADA assistée.

5. **Scellement ONECCA (`#modalVisaOnecca`)** :
   - Génération de visa officiel d'expert-comptable avec empreinte cryptographique.

---

## 🚀 Lancement & Prérequis
Les templates Jinja2 s'appuient sur FastAPI et le socle partagé `grow_shared/database.py`.
Le style CSS est propulsé par Tailwind CSS et FontAwesome Pro.


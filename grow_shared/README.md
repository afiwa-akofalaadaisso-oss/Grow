# 🗄️ Socle Partagé : Données, Persistance & Configuration

Ce dossier contient les ressources transversales partagées entre le **Copilote WhatsApp** (Livrable 1) et le **Logiciel Web Comptable** (Livrable 2).

---

## 🎯 Rôle du Socle Partagé
Garantir une source de vérité unique pour les données financières des PME :
1. **Supabase Cloud PostgreSQL** : Base de données cloud de production en temps réel (accès rapide avec RLS, temps de réponse < 150ms).
2. **SQLite Replica Local (`grow_compta.db`)** : Réplique locale automatique assurant une résilience totale : si la connexion internet est instable, l'application continue de fonctionner en lecture et en écriture sans aucune interruption.

---

## 🧩 Fichiers

| Fichier | Rôle |
|---|---|
| `database.py` | **Moteur de Données Hybride** : Abstraction connectée à Supabase avec réplique SQLite transparente, méthodes CRUD pour les entreprises, transactions, pièces justificatives et abonnements. |
| `grow_compta.db` | Fichier de base de données SQLite local répliqué en continu. |
| `.env` | Variables d'environnement secrètes (clés d'API, tokens, URL de base de données). |
| `.env.example` | Gabarit de configuration pour déployer un nouvel environnement. |

---

## 📊 Schéma des Données Principales

* **`entreprises`** : ID, nom de l'entreprise, NINEA, numéro WhatsApp associé, solde net.
* **`transactions`** : ID, entreprise_id, date, libellé, montant, type (`ENTREE` / `SORTIE`), compte_syscohada (ex: `701`, `601`), mode_reglement (`WAVE`, `ORANGE_MONEY`, `ESPECES`, `BANQUE`), statut (`CERTIFIE`, `A_VERIFIER`).
* **`pieces_jointes`** : URL du reçu ou capture de paiement Wave/OM, transaction_id, type mime.
* **`abonnements`** : Statut d'abonnement SaaS de la PME, date d'échéance, plan choisi.

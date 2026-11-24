"""
Banc de test automatisé simulant l'intégralité du Scénario Client Growth de A à Z :
- Parcours standard (Bouton D Comptes perso, NINEA avec titulaire + nom boutique, comptage caisse tiroir 571, inventaire, paywall et routine active).
- Parcours multi-comptes (Bouton E : les 5 canaux en même temps).
"""
import asyncio
import os
import sys

# Ajout du dossier racine au path
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chat_grow.main import handle_incoming_message, get_onboarding_state, update_onboarding_state

async def tester_parcours_complet():
    print("=" * 70)
    print("🚀 DÉMARRAGE DU TEST DU GRAND SCÉNARIO CLIENT GROWTH SYSCOHADA")
    print("=" * 70)

    test_phone = "221770009988"
    
    # 0. Réinitialisation état de test
    update_onboarding_state(test_phone, "etape", "PHASE_1_ACCUEIL")
    update_onboarding_state(test_phone, "statut", "EN_COURS")
    update_onboarding_state(test_phone, "abonnement_valide", False)
    update_onboarding_state(test_phone, "premier_contact_effectue", False)

    # ÉTAPE 1 : Accueil
    print("\n--- [ÉTAPE 1] Accueil & Choix du mode ---")
    r1 = await handle_incoming_message(test_phone, "Bonjour Growth", None, contact_name="Modou")
    print(f"Commerçant: Bonjour Growth\nGrowth:\n{r1}\n")
    assert "vidéo tutoriel" in r1 or "Mode" in r1 or "vocal" in r1.lower()

    # Choix Vocal (1)
    print("\n--- [ÉTAPE 1 -> 2] Choix du mode Vocal (1) ---")
    r2 = await handle_incoming_message(test_phone, "1", None, contact_name="Modou")
    print(f"Commerçant: 1\nGrowth:\n{r2}\n")
    assert "Avertissement Légal" in r2
    assert "Bouton A" in r2 and "Bouton D" in r2 and "Bouton E" in r2

    # ÉTAPE 2 : Choix D (Comptes Personnels)
    print("\n--- [ÉTAPE 2] Choix Bouton D (Comptes Personnels) ---")
    r3 = await handle_incoming_message(test_phone, "D", None, contact_name="Modou")
    print(f"Commerçant: D\nGrowth:\n{r3}\n")
    assert "Étape Décisive pour Votre Commerce" in r3
    assert "Wave Business ou Orange Business" in r3
    assert "NINEA" in r3

    # ÉTAPE 3 : Envoi du NINEA
    print("\n--- [ÉTAPE 3] Envoi du numéro NINEA (00802996) ---")
    r4 = await handle_incoming_message(test_phone, "Mon NINEA est 00802996", None, contact_name="Modou")
    print(f"Commerçant: Mon NINEA est 00802996\nGrowth:\n{r4}\n")
    assert "00802996" in r4
    assert "nom commercial ou l'enseigne de votre boutique" in r4

    # ÉTAPE 3.1 : Précision du nom commercial de la boutique
    print("\n--- [ÉTAPE 3.1] Précision du Nom Commercial de la Boutique ---")
    r5 = await handle_incoming_message(test_phone, "Boutique Touba Sandaga", None, contact_name="Modou")
    print(f"Commerçant: Boutique Touba Sandaga\nGrowth:\n{r5}\n")
    assert "Touba Sandaga" in r5 and "Dossier scellé" in r5
    assert "Étape 4" in r5

    # ÉTAPE 4 : Solde de départ / Relevé
    print("\n--- [ÉTAPE 4] Solde de départ Wave Perso ---")
    r6 = await handle_incoming_message(test_phone, "J'ai 250 000 FCFA sur mon compte", None, contact_name="Modou")
    print(f"Commerçant: J'ai 250 000 FCFA sur mon compte\nGrowth:\n{r6}\n")
    assert "250,000" in r6 or "250 000" in r6
    assert "Comptage Obligatoire de votre Caisse Espèces" in r6
    assert "571" in r6

    # ÉTAPE 5.1 : Comptage caisse espèces physique (Tiroir Compte 571)
    print("\n--- [ÉTAPE 5.1] Comptage Espèces Tiroir 571 ---")
    r7 = await handle_incoming_message(test_phone, "J'ai 175 000 F en espèces dans mon tiroir", None, contact_name="Modou")
    print(f"Commerçant: J'ai 175 000 F en espèces dans mon tiroir\nGrowth:\n{r7}\n")
    assert "175,000" in r7 or "175 000" in r7
    assert "Immobilisations" in r7
    assert "amortissement" in r7.lower()

    # ÉTAPE 5.2 : Matériel & Amortissements
    print("\n--- [ÉTAPE 5.2] Immobilisations & Amortissements ---")
    r8 = await handle_incoming_message(test_phone, "2 congélateurs et 1 balance valant 600 000 FCFA", None, contact_name="Modou")
    print(f"Commerçant: 2 congélateurs et 1 balance valant 600 000 FCFA\nGrowth:\n{r8}\n")
    assert "600,000" in r8 or "600 000" in r8
    assert "Stock" in r8
    assert "grossiste" in r8.lower()

    # ÉTAPE 5.3 : Stock au coût grossiste
    print("\n--- [ÉTAPE 5.3] Stock au coût grossiste ---")
    r9 = await handle_incoming_message(test_phone, "Valeur stock grossiste 450 000 FCFA", None, contact_name="Modou")
    print(f"Commerçant: Valeur stock grossiste 450 000 FCFA\nGrowth:\n{r9}\n")
    assert "450,000" in r9 or "450 000" in r9
    assert "Créances" in r9 or "Dettes" in r9

    # ÉTAPE 5.4 : Dettes & Créances -> Scellage Bilan & Verrou d'Abonnement
    print("\n--- [ÉTAPE 5.4] Dettes & Créances -> Scellage Bilan & Paywall ---")
    r10 = await handle_incoming_message(test_phone, "Des clients me doivent 80 000 F et je dois 120 000 F au grossiste", None, contact_name="Modou")
    print(f"Commerçant: Des clients me doivent 80 000 F et je dois 120 000 F au grossiste\nGrowth:\n{r10}\n")
    assert "100% scellés" in r10 or "scellé" in r10.lower()
    assert "abonnement" in r10.lower()
    assert "/abonnement?phone=221770009988" in r10

    # ÉTAPE 6 : Tentative de saisie sans paiement -> Verrou
    print("\n--- [ÉTAPE 6] Tentative de saisie en attente d'abonnement ---")
    r11 = await handle_incoming_message(test_phone, "Vente 15 000 FCFA", None, contact_name="Modou")
    print(f"Commerçant: Vente 15 000 FCFA\nGrowth:\n{r11}\n")
    assert "abonnement" in r11.lower()
    assert "/abonnement?phone=221770009988" in r11

    # ÉTAPE 6 -> 7 : Validation du paiement par mot-clé "J'ai payé"
    print("\n--- [ÉTAPE 6 -> 7] Validation paiement 'J'ai payé' ---")
    r12 = await handle_incoming_message(test_phone, "J'ai payé", None, contact_name="Modou")
    print(f"Commerçant: J'ai payé\nGrowth:\n{r12}\n")
    assert "Paiement Validé" in r12 or "activé" in r12.lower()

    # ÉTAPE 7 : Routine Quotidienne Active (Saisie d'une vente en 1.5s)
    print("\n--- [ÉTAPE 7] Routine Quotidienne Active (Vente 15 000 FCFA) ---")
    r13 = await handle_incoming_message(test_phone, "Vente 15 000 FCFA sac de riz", None, contact_name="Modou")
    print(f"Commerçant: Vente 15 000 FCFA sac de riz\nGrowth:\n{r13}\n")
    assert "15" in r13 or "701" in r13 or "vente" in r13.lower() or "enregistr" in r13.lower()

    # TEST DU PARCOURS MULTI-COMPTES (BOUTON E - 5 CANAUX)
    print("\n" + "=" * 70)
    print("💼 TEST DU PARCOURS MULTI-COMPTES (BOUTON E : LES 5 EN MÊME TEMPS)")
    print("=" * 70)
    test_phone_e = "221780005544"
    update_onboarding_state(test_phone_e, "etape", "PHASE_2_CHOIX_OPERATEURS")
    r_e = await handle_incoming_message(test_phone_e, "E", None, contact_name="Amina")
    print(f"Commerçant: E (J'ai TOUT)\nGrowth:\n{r_e}\n")
    assert "5 canaux" in r_e
    assert "Wave Business (Compte 5211)" in r_e
    assert "Orange Business (Compte 5212)" in r_e
    assert "Caisse Espèces Tiroir (Compte 571)" in r_e

    # TEST DISSOCIATION NUMÉRO WHATSAPP ET WEBHOOK / NUMÉRO MARCHAND DU MAGASIN
    print("\n" + "=" * 70)
    print("🔗 TEST DISSOCIATION WHATSAPP & WEBHOOK / NUMÉRO MAGASIN DISTINCT")
    print("=" * 70)
    test_phone_remote = "221701112233"
    update_onboarding_state(test_phone_remote, "etape", "PHASE_2_CHOIX_OPERATEURS")
    # Le commerçant fournit le numéro ou webhook de son terminal magasin
    r_rem = await handle_incoming_message(test_phone_remote, "Mon Wave Business est sur le numéro 76 555 44 33", None, contact_name="Ousmane")
    print(f"Commerçant (WhatsApp 70...): Mon Wave Business est sur le 76 555 44 33\nGrowth:\n{r_rem}\n")
    assert "221765554433" in r_rem or "Compte Marchand Magasin" in r_rem

    # Test d'arrivée d'un webhook sur le numéro magasin 221765554433
    from chat_grow.main import process_payment_notification
    webhook_payload = {
        "amount": 25000,
        "merchant_phone": "221765554433",
        "client_name": "Fatou Fall",
        "txnid": "WV-REMOTE-TEST-99"
    }
    res_notif = await process_payment_notification(webhook_payload, operator="WAVE")
    print(f"Webhook reçu pour le magasin 221765554433 -> Résolution Growth:\n{res_notif}\n")
    # Vérification que Growth a bien résolu vers le WhatsApp du gérant (221701112233)
    assert res_notif.get("phone") == "221701112233"

    print("\n" + "=" * 70)
    print("✅ TOUS LES TESTS DU SCÉNARIO COMPLET SONT VALIDÉS AVEC SUCCÈS 100% !")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(tester_parcours_complet())

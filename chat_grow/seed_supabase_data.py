import uuid
import datetime
from main import get_supabase

sp = get_supabase()
if not sp:
    print("ERREUR: Impossible de se connecter a Supabase")
    exit(1)

# Verifier les entreprises existantes
existing_ents = sp.table('entreprises').select('id, nom_entreprise, telephone_whatsapp, ninea').execute().data or []
existing_phones = {e.get('telephone_whatsapp') for e in existing_ents}
print(f"Entreprises deja existantes: {len(existing_ents)}")

new_pme_data = [
    {
        "nom_entreprise": "Château de Gourmet",
        "telephone_whatsapp": "221768337400",
        "ninea": "00833740",
        "secteur_activite": "Restauration Gastronomique & Traiteur",
        "capital_initial_fcfa": 5000000,
        "adresse_siege": "Route des Almadies, Dakar, Sénégal",
        "nombre_employes": 12,
        "date_creation_officielle": "2021-04-15",
        "donnees_onboarding": {
            "forme_juridique": "SARL",
            "registre_commerce": "SN-DKR-2021-B-8421",
            "statut": "VALIDE",
            "soldes_initiaux_par_operateur": {"WAVE": 450000, "ORANGE": 280000, "CBAO": 2850000}
        },
        "transactions": [
            {"libelle": "Facture Traiteur Séminaire Ecobank", "compte_syscohada": "706", "type_flux": "ENTREE", "montant_fcfa": 246000, "source_paiement": "BANQUE", "statut_validation": "VALIDE_PME", "ref": "83374"},
            {"libelle": "Achat Viande & Poissons Marée Dakar", "compte_syscohada": "601", "type_flux": "SORTIE", "montant_fcfa": 75000, "source_paiement": "WAVE", "statut_validation": "VALIDE_PME", "ref": "83375"},
            {"libelle": "Dîner Gala Chambre de Commerce", "compte_syscohada": "706", "type_flux": "ENTREE", "montant_fcfa": 450000, "source_paiement": "BANQUE", "statut_validation": "VALIDE_PME", "ref": "83376"},
            {"libelle": "Recharge Gaz Fourneau Principal", "compte_syscohada": "605", "type_flux": "SORTIE", "montant_fcfa": 35000, "source_paiement": "ESPECES", "statut_validation": "VALIDE_PME", "ref": "83377"},
            {"libelle": "Encaissement Wave Restaurant Salle", "compte_syscohada": "701", "type_flux": "ENTREE", "montant_fcfa": 128500, "source_paiement": "WAVE", "statut_validation": "VALIDE_PME", "ref": "83378"},
            {"libelle": "Prime Primeur Légumes Frais Sangalkam", "compte_syscohada": "601", "type_flux": "SORTIE", "montant_fcfa": 42000, "source_paiement": "ORANGE_MONEY", "statut_validation": "VALIDE_PME", "ref": "83379"},
        ]
    },
    {
        "nom_entreprise": "Sérénité Assurances & Courtage",
        "telephone_whatsapp": "221704311200",
        "ninea": "00431120",
        "secteur_activite": "Courtage en Assurances & Gestion Risques",
        "capital_initial_fcfa": 10000000,
        "adresse_siege": "12 Avenue Léopold S. Senghor, Plateau, Dakar",
        "nombre_employes": 8,
        "date_creation_officielle": "2019-11-20",
        "donnees_onboarding": {
            "forme_juridique": "SARL",
            "registre_commerce": "SN-DKR-2019-B-1290",
            "statut": "VALIDE",
            "soldes_initiaux_par_operateur": {"CBAO": 4200000, "WAVE": 350000}
        },
        "transactions": [
            {"libelle": "Commission Flotte Automobile SARL Teranga", "compte_syscohada": "706", "type_flux": "ENTREE", "montant_fcfa": 171520, "source_paiement": "BANQUE", "statut_validation": "VALIDE_PME", "ref": "43112"},
            {"libelle": "Abonnement Logiciel Pro Courtage Assur", "compte_syscohada": "628", "type_flux": "SORTIE", "montant_fcfa": 65000, "source_paiement": "BANQUE", "statut_validation": "VALIDE_PME", "ref": "43113"},
            {"libelle": "Quittance Assurance Santé PME Dakar", "compte_syscohada": "706", "type_flux": "ENTREE", "montant_fcfa": 320000, "source_paiement": "WAVE", "statut_validation": "VALIDE_PME", "ref": "43114"},
            {"libelle": "Loyer Bureau Plateau Dakar Novembre", "compte_syscohada": "622", "type_flux": "SORTIE", "montant_fcfa": 250000, "source_paiement": "BANQUE", "statut_validation": "VALIDE_PME", "ref": "43115"},
            {"libelle": "Frais Honoraires Expert Évaluation Sinistre", "compte_syscohada": "632", "type_flux": "SORTIE", "montant_fcfa": 85000, "source_paiement": "WAVE", "statut_validation": "VALIDE_PME", "ref": "43116"},
        ]
    },
    {
        "nom_entreprise": "Innovatech Médical Sénégal",
        "telephone_whatsapp": "221786709800",
        "ninea": "00670980",
        "secteur_activite": "Fourniture & Maintenance Matériel Biomédical",
        "capital_initial_fcfa": 8000000,
        "adresse_siege": "Rue 10 x Boulevard Dial Diop, Point E, Dakar",
        "nombre_employes": 6,
        "date_creation_officielle": "2020-07-01",
        "donnees_onboarding": {
            "forme_juridique": "SUARL",
            "registre_commerce": "SN-DKR-2020-B-5534",
            "statut": "VALIDE",
            "soldes_initiaux_par_operateur": {"CBAO": 3100000, "WAVE": 500000}
        },
        "transactions": [
            {"libelle": "Maintenance Échographe Clinique de la Madeleine", "compte_syscohada": "706", "type_flux": "ENTREE", "montant_fcfa": 214270, "source_paiement": "BANQUE", "statut_validation": "VALIDE_PME", "ref": "67098"},
            {"libelle": "Achat Pièces Détachées Monitorage Philips", "compte_syscohada": "601", "type_flux": "SORTIE", "montant_fcfa": 145000, "source_paiement": "BANQUE", "statut_validation": "VALIDE_PME", "ref": "67099"},
            {"libelle": "Fourniture Consommables Labo CHU Fann", "compte_syscohada": "701", "type_flux": "ENTREE", "montant_fcfa": 480000, "source_paiement": "BANQUE", "statut_validation": "VALIDE_PME", "ref": "67100"},
            {"libelle": "Transport Express DHL Électrodes Cardiologie", "compte_syscohada": "612", "type_flux": "SORTIE", "montant_fcfa": 32000, "source_paiement": "ORANGE_MONEY", "statut_validation": "VALIDE_PME", "ref": "67101"},
        ]
    },
    {
        "nom_entreprise": "Savoir-Faire Culinaires",
        "telephone_whatsapp": "221778722400",
        "ninea": "00872240",
        "secteur_activite": "Boulangerie Artisanale & Pâtisserie Fine",
        "capital_initial_fcfa": 3500000,
        "adresse_siege": "Boulevard du Centenaire, Dakar",
        "nombre_employes": 9,
        "date_creation_officielle": "2022-01-10",
        "donnees_onboarding": {
            "forme_juridique": "SARL",
            "registre_commerce": "SN-DKR-2022-B-1102",
            "statut": "VALIDE",
            "soldes_initiaux_par_operateur": {"WAVE": 620000, "ORANGE": 310000}
        },
        "transactions": [
            {"libelle": "Commande Pâtisseries Mariage Radisson Blu", "compte_syscohada": "701", "type_flux": "ENTREE", "montant_fcfa": 94000, "source_paiement": "WAVE", "statut_validation": "VALIDE_PME", "ref": "87224"},
            {"libelle": "Achat Farine Moulins Sentenac 50 Sacs", "compte_syscohada": "601", "type_flux": "SORTIE", "montant_fcfa": 210000, "source_paiement": "BANQUE", "statut_validation": "VALIDE_PME", "ref": "87225"},
            {"libelle": "Encaissements Ventes Boutique Matin", "compte_syscohada": "701", "type_flux": "ENTREE", "montant_fcfa": 145000, "source_paiement": "ESPECES", "statut_validation": "VALIDE_PME", "ref": "87226"},
            {"libelle": "Achat Beurre Grand Cru & Chocolat Valrhona", "compte_syscohada": "601", "type_flux": "SORTIE", "montant_fcfa": 88000, "source_paiement": "ORANGE_MONEY", "statut_validation": "VALIDE_PME", "ref": "87227"},
        ]
    }
]

created_count = 0
tx_count = 0

for pme in new_pme_data:
    phone = pme["telephone_whatsapp"]
    if phone in existing_phones:
        print(f"PME deja presente: {pme['nom_entreprise']} ({phone})")
        continue

    ent_row = {
        "id": str(uuid.uuid4()),
        "nom_entreprise": pme["nom_entreprise"],
        "telephone_whatsapp": phone,
        "ninea": pme["ninea"],
        "secteur_activite": pme["secteur_activite"],
        "capital_initial_fcfa": pme["capital_initial_fcfa"],
        "adresse_siege": pme["adresse_siege"],
        "nombre_employes": pme["nombre_employes"],
        "date_creation_officielle": pme["date_creation_officielle"],
        "donnees_onboarding": pme["donnees_onboarding"],
        "date_inscription": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    res_ent = sp.table('entreprises').insert(ent_row).execute()
    if res_ent.data:
        ent_id = res_ent.data[0]['id']
        created_count += 1
        print(f"+ Cree PME: {pme['nom_entreprise']} (ID: {ent_id})")

        tx_rows = []
        for tx in pme["transactions"]:
            tx_rows.append({
                "id": str(uuid.uuid4()),
                "entreprise_id": ent_id,
                "date_operation": "2026-11-14",
                "libelle": tx["libelle"],
                "compte_syscohada": tx["compte_syscohada"],
                "type_flux": tx["type_flux"],
                "est_professionnel": True,
                "montant_fcfa": tx["montant_fcfa"],
                "source_paiement": tx["source_paiement"],
                "statut_validation": tx["statut_validation"],
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
        
        if tx_rows:
            res_tx = sp.table('transactions').insert(tx_rows).execute()
            if res_tx.data:
                tx_count += len(res_tx.data)
                print(f"  + Ajoute {len(res_tx.data)} transactions reelles")

print(f"BILAN: {created_count} PMEs creees et {tx_count} transactions inserees dans Supabase!")


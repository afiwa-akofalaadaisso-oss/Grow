"""Retire les 2 débits de test « Paiement abonnement mensuel Grow (Wave) » (10 000 F chacun)
insérés par erreur lors des clics de test sur /abonnement. Sauvegarde JSON avant suppression."""
import json
import main

sp = main.get_supabase()
ENT = 'af3f08b5-1c4a-4812-8e2d-23b7944f7b27'
IDS = ['c97ecb15-f17e-4ae6-becf-6234b522006f', '7f63e39f-e022-4163-b378-a29952ca7bec']

rows = sp.table('transactions').select('*').in_('id', IDS).eq('entreprise_id', ENT).execute().data
with open('backup_abonnement_tests.json', 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
print('Sauvegardé :', len(rows))

for r in rows:
    assert r['libelle'].startswith('Paiement abonnement mensuel Grow') and r['montant_fcfa'] == 10000
    sp.table('transactions').delete().eq('id', r['id']).eq('entreprise_id', ENT).execute()
    print('Supprimé :', r['id'])

tx = sp.table('transactions').select('type_flux,montant_fcfa').eq('entreprise_id', ENT).execute().data
e = sum(t['montant_fcfa'] for t in tx if t['type_flux'] == 'ENTREE')
s = sum(t['montant_fcfa'] for t in tx if t['type_flux'] == 'SORTIE')
print(f'{len(tx)} preuves | Entrées {e} | Sorties {s} | Solde {e - s}')


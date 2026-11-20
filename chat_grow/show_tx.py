import sys
sys.path.append('chat_grow')
import main

sp = main.get_supabase()
ent_id = 'af3f08b5-1c4a-4812-8e2d-23b7944f7b27'

res = sp.table('transactions').select('*').eq('entreprise_id', ent_id).order('created_at', desc=False).execute()
for r in res.data:
    print(f"ID: {r.get('id')} | Created: {r.get('created_at')} | Type: {r.get('type_flux')} | Montant: {r.get('montant_fcfa')} F | Libelle: {r.get('libelle')} | Compte: {r.get('compte_syscohada')}")


import urllib.request
import json

resp = urllib.request.urlopen('http://127.0.0.1:8000/api/dashboard-data?phone=221788773827')
data = json.loads(resp.read().decode('utf-8'))

print("Totals from API:", data.get('totals'))
print("Entreprise:", data.get('entreprise', {}).get('nom_entreprise'), "ID:", data.get('entreprise', {}).get('id'))

txs = data.get('transactions', [])
print(f"Total transactions: {len(txs)}")
tot_in = 0
tot_out = 0
for t in txs:
    flux = t.get('type_flux')
    m = t.get('montant_fcfa') or 0
    if flux == 'ENTREE':
        tot_in += m
    else:
        tot_out += m
    print(f"• [{flux}] {m} F | {t.get('libelle')} (compte {t.get('compte_syscohada')})")

print(f"\nSomme Entrées: {tot_in} F")
print(f"Somme Sorties: {tot_out} F")
print(f"Solde Net: {tot_in - tot_out} F")


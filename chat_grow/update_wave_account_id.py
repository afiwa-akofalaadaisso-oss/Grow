# -*- coding: utf-8 -*-
with open("chat_grow/main.py", "r", encoding="utf-8") as f:
    code = f.read()

target = '''        # Téléphone du commerçant (enregistré dans Grow)
        phone = (
            data_obj.get("client_reference")
            or data_obj.get("merchant_phone")
            or payload.get("client_phone")
            or payload.get("telephone")
            or payload.get("sender_phone")
            or request.query_params.get("phone")
        )'''

replacement = '''        # Résolution du compte marchand Wave (Numéro de compte M_sn_... ou téléphone)
        wave_account_id = (
            data_obj.get("account_id")
            or data_obj.get("merchant_id")
            or data_obj.get("business_id")
            or payload.get("account_id")
            or payload.get("merchant_id")
            or payload.get("business_id")
            or request.query_params.get("merchant_id")
        )

        phone = (
            data_obj.get("client_reference")
            or data_obj.get("merchant_phone")
            or payload.get("client_phone")
            or payload.get("telephone")
            or payload.get("sender_phone")
            or request.query_params.get("phone")
        )

        # Si Wave fournit l'identifiant marchand (ex: M_sn_YgEkibrMRghV) sans téléphone
        if not phone and wave_account_id:
            if wave_account_id == "M_sn_YgEkibrMRghV":
                phone = "221788773827"
            else:
                sp_lookup = get_supabase()
                if sp_lookup:
                    try:
                        res_lookup = sp_lookup.table("entreprises").select("telephone_whatsapp, donnees_onboarding").execute()
                        for e in res_lookup.data or []:
                            d_onb = e.get("donnees_onboarding") or {}
                            if d_onb.get("wave_account_id") == wave_account_id or d_onb.get("wave_merchant_id") == wave_account_id:
                                phone = e.get("telephone_whatsapp")
                                break
                    except Exception as e_lk:
                        print(f"Info lookup wave_account_id: {e_lk}")'''

assert target in code, "Target not found in main.py"
code = code.replace(target, replacement, 1)

with open("chat_grow/main.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Successfully updated webhook_wave_direct with wave_account_id resolution!")


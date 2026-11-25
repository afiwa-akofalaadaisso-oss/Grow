"""
Générateur d'Infographies Financières Hebdomadaires Growth
Crée une carte image HD au format carré (1080x1080) résumant la performance financière de la semaine
pour envoi direct par WhatsApp.
"""
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

def generer_infographie_hebdo(pme: dict, stats: dict = None, out_path: str = None) -> str:
    """
    Génère une image infographique HD de synthèse financière de la semaine.
    """
    nom_ent = (pme.get("nom_entreprise") or pme.get("nom") or "Votre Entreprise").upper()
    tel = pme.get("telephone_whatsapp") or pme.get("telephone") or ""
    date_jour = datetime.now().strftime("%d/%m/%Y")

    stats = stats or {}
    ca_str = stats.get("ca", "0 FCFA")
    dep_str = stats.get("depenses", "0 FCFA")
    treso_str = stats.get("treso", "0 FCFA")
    nb_ops = str(stats.get("nb_operations", 0))

    if not out_path:
        static_img = os.path.join(os.path.dirname(__file__), "static", "images")
        os.makedirs(static_img, exist_ok=True)
        safe_tel = "".join(filter(str.isdigit, tel))[-9:] or "pme"
        out_path = os.path.join(static_img, f"synthese_hebdo_{safe_tel}.png")

    # Dimensions carré HD
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), color="#0f172a")
    draw = ImageDraw.Draw(img)

    # Polices (fallback par défaut Pillow)
    try:
        font_header = ImageFont.truetype("arial.ttf", 36)
        font_title = ImageFont.truetype("arialbd.ttf", 52)
        font_kpi_val = ImageFont.truetype("arialbd.ttf", 64)
        font_kpi_lbl = ImageFont.truetype("arial.ttf", 30)
        font_meta = ImageFont.truetype("arial.ttf", 26)
    except:
        font_header = font_title = font_kpi_val = font_kpi_lbl = font_meta = ImageFont.load_default()

    # 1. Barre supérieure décorative Menthe Growth
    draw.rectangle([0, 0, W, 18], fill="#168078")

    # 2. En-tête Marque
    draw.text((70, 70), "GROWTH • COPILOTE FINANCIER & COMPTABLE", fill="#168078", font=font_header)
    draw.text((70, 125), f"BILAN HEBDOMADAIRE : {nom_ent}", fill="#ffffff", font=font_title)
    draw.text((70, 195), f"Arrêté au {date_jour} • Norme SYSCOHADA SMT • Supervision Cabinet Adaisso", fill="#94a3b8", font=font_meta)

    # 3. Séparateur
    draw.line([(70, 240), (W - 70, 240)], fill="#334155", width=2)

    # 4. Carte 1 : Chiffre d'Affaires Encaissé (Vert Menthe)
    draw.rounded_rectangle([70, 280, W - 70, 480], radius=24, fill="#132e29", outline="#168078", width=3)
    draw.text((110, 315), "CHIFFRE D'AFFAIRES ENCAISSÉ (VENTES COMPTE 701)", fill="#a0d9d2", font=font_kpi_lbl)
    draw.text((110, 370), ca_str, fill="#ffffff", font=font_kpi_val)

    # 5. Carte 2 : Dépenses & Achats (Rose/Gris)
    draw.rounded_rectangle([70, 520, W - 70, 720], radius=24, fill="#1e293b", outline="#475569", width=2)
    draw.text((110, 555), "DÉPENSES & ACHATS RÉASSORT (COMPTES 601 / 605)", fill="#cbd5e1", font=font_kpi_lbl)
    draw.text((110, 610), dep_str, fill="#fca5a5", font=font_kpi_val)

    # 6. Deux cartes côte à côte : Trésorerie Finale & Nombre d'opérations
    half_w = (W - 140 - 30) // 2
    # Trésorerie
    draw.rounded_rectangle([70, 760, 70 + half_w, 940], radius=24, fill="#1e293b", outline="#334155", width=2)
    draw.text((100, 795), "TRÉSORERIE DISPONIBLE", fill="#94a3b8", font=font_meta)
    draw.text((100, 845), treso_str, fill="#38bdf8", font=font_kpi_lbl)

    # Opérations
    draw.rounded_rectangle([70 + half_w + 30, 760, W - 70, 940], radius=24, fill="#1e293b", outline="#334155", width=2)
    draw.text((100 + half_w + 30, 795), "ÉCRITURES COMPTABLES", fill="#94a3b8", font=font_meta)
    draw.text((100 + half_w + 30, 845), f"{nb_ops} opérations scellées", fill="#4ade80", font=font_kpi_lbl)

    # 7. Footer de certification légale
    draw.line([(70, 980), (W - 70, 980)], fill="#334155", width=2)
    draw.text((70, 1010), "🔒 Données chiffrées & scellées SHA-256 • Conforme Acte Uniforme SYSCOHADA (UEMOA)", fill="#64748b", font=font_meta)

    img.save(out_path, format="PNG", quality=95)
    return out_path

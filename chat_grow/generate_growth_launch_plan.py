# -*- coding: utf-8 -*-
import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, hex_color):
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_cell_margins(cell, top=120, bottom=120, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def create_document():
    doc = docx.Document()
    
    # Page setup (A4, 2cm margins)
    for section in doc.sections:
        section.page_width = Inches(8.27)
        section.page_height = Inches(11.69)
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)
        
    # Styles definition
    COLOR_PRIMARY = RGBColor(34, 34, 34)      # #222222 (Anthracite de direction)
    COLOR_TEAL = RGBColor(22, 128, 120)       # #168078 (Vert signature Growth)
    COLOR_DARK = RGBColor(15, 23, 42)         # #0f172a
    COLOR_MUTED = RGBColor(100, 116, 139)     # #64748b
    COLOR_SUCCESS = RGBColor(16, 185, 129)    # #10b981
    
    # Header / Title Block
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(4)
    run_brand = title_p.add_run("GROWTH • COPILOTE COMPTABLE SYSCOHADA SMT")
    run_brand.font.size = Pt(11)
    run_brand.font.bold = True
    run_brand.font.color.rgb = COLOR_TEAL

    main_title = doc.add_paragraph()
    main_title.paragraph_format.space_before = Pt(4)
    main_title.paragraph_format.space_after = Pt(8)
    run_title = main_title.add_run("Plan d'Exploitation Financier, Roadmap de Lancement Commercial & Stratégie Vidéo WhatsApp")
    run_title.font.size = Pt(22)
    run_title.font.bold = True
    run_title.font.color.rgb = COLOR_PRIMARY

    sub_title = doc.add_paragraph()
    sub_title.paragraph_format.space_before = Pt(0)
    sub_title.paragraph_format.space_after = Pt(18)
    run_sub = sub_title.add_run("Document confidentiel de direction • Dakar, Sénégal • Novembre 2026")
    run_sub.font.size = Pt(10)
    run_sub.font.italic = True
    run_sub.font.color.rgb = COLOR_MUTED

    # Divider line
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_before = Pt(0)
    p_div.paragraph_format.space_after = Pt(16)
    p_div_border = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="12" w:space="1" w:color="E2E8F0"/></w:pBdr>')
    p_div._p.get_or_add_pPr().append(p_div_border)

    # -------------------------------------------------------------
    # 1. SYNTHÈSE EXÉCUTIVE
    # -------------------------------------------------------------
    h1 = doc.add_paragraph()
    h1.paragraph_format.space_before = Pt(14)
    h1.paragraph_format.space_after = Pt(6)
    r1 = h1.add_run("1. Synthèse Exécutive : Combien coûte Growth par mois ?")
    r1.font.size = Pt(14)
    r1.font.bold = True
    r1.font.color.rgb = COLOR_PRIMARY

    p1 = doc.add_paragraph()
    p1.paragraph_format.space_after = Pt(10)
    p1.paragraph_format.line_spacing = 1.25
    r_p1 = p1.add_run(
        "Pour faire tourner l'intégralité de la plateforme Growth 24h/24 et 7j/7 sans aucune interruption, "
        "votre budget d'infrastructure et d'intelligence artificielle est extrêmement léger. "
        "Grâce à l'architecture moderne mise en place (FastAPI asynchrone, Google Gemini Flash ultra-optimisé et WhatsApp Cloud API), "
        "le coût total de fonctionnement en phase de démarrage se situe entre "
    )
    r_p1.font.size = Pt(10)
    r_p1.font.color.rgb = COLOR_DARK
    
    r_highlight = p1.add_run("12 000 FCFA et 20 000 FCFA par mois (environ 18 € à 30 € / mois).")
    r_highlight.font.size = Pt(10)
    r_highlight.font.bold = True
    r_highlight.font.color.rgb = COLOR_TEAL

    # Callout box for Rentabilité
    callout_tbl = doc.add_table(rows=1, cols=1)
    callout_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    callout_cell = callout_tbl.cell(0, 0)
    callout_cell.width = Inches(6.67)
    set_cell_background(callout_cell, "F8FAFC")
    set_cell_margins(callout_cell, top=140, bottom=140, left=180, right=180)
    
    # Border left teal
    tcPr = callout_cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="0" w:color="168078"/><w:top w:val="none"/><w:right w:val="none"/><w:bottom w:val="none"/></w:tcBorders>')
    tcPr.append(borders)

    c_p = callout_cell.paragraphs[0]
    c_p.paragraph_format.space_before = Pt(0)
    c_p.paragraph_format.space_after = Pt(0)
    c_p.paragraph_format.line_spacing = 1.2
    c_run1 = c_p.add_run("💡 La Règle d'Or de la Rentabilité : ")
    c_run1.font.bold = True
    c_run1.font.size = Pt(10.5)
    c_run1.font.color.rgb = COLOR_PRIMARY
    c_run2 = c_p.add_run(
        "Votre forfait Starter étant fixé à 10 000 FCFA/mois et le forfait Pro à 25 000 FCFA/mois, "
        "il vous suffit de seulement 1 à 2 commerçants abonnés pour couvrir 100% de toutes vos charges mensuelles. "
        "Dès le 3ème commerçant, Growth génère du bénéfice net direct pour votre caisse de direction."
    )
    c_run2.font.size = Pt(10)
    c_run2.font.color.rgb = COLOR_DARK

    # -------------------------------------------------------------
    # 2. GRILLE DÉTAILLÉE DES CHARGES MENSUELLES
    # -------------------------------------------------------------
    h2 = doc.add_paragraph()
    h2.paragraph_format.space_before = Pt(20)
    h2.paragraph_format.space_after = Pt(6)
    r2 = h2.add_run("2. Détail Poste par Poste des Coûts Mensuels")
    r2.font.size = Pt(14)
    r2.font.bold = True
    r2.font.color.rgb = COLOR_PRIMARY

    # Cost table
    table = doc.add_table(rows=6, cols=5)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [Inches(1.8), Inches(1.8), Inches(1.1), Inches(1.1), Inches(0.87)]
    headers = ["Service / Poste", "Rôle dans le projet", "Coût Démarrage (0-50 PME)", "Coût Croissance (100-300 PME)", "Fournisseur"]

    # Header Row
    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].width = col_widths[i]
        set_cell_background(hdr_cells[i], "222222")
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=100, right=100)
        p = hdr_cells[i].paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(title)
        run.font.size = Pt(9)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    data = [
        ("Serveur & Hébergement Cloud", "Hébergement 24/7 du site, de l'API et des webhooks (sans mise en veille)", "4 600 FCFA ($7/m)", "4 600 FCFA ($7/m)", "Render Cloud"),
        ("Base de Données Souveraine", "Stockage sécurisé des écritures comptables SYSCOHADA et coffre-fort", "0 FCFA (Inclus/Gratuit)", "4 600 FCFA ($7/m)", "Supabase / Render"),
        ("Meta WhatsApp Cloud API", "Réception et envoi des messages, bilans, OTP et alertes instantanées", "0 FCFA (1000 convs offertes)", "3 000 à 6 000 FCFA", "Meta (Facebook)"),
        ("Intelligence Artificielle (IA)", "Transcription des vocaux Wolof/Français et pré-imputation SMT", "1 500 à 3 000 FCFA", "5 000 à 10 000 FCFA", "Google Gemini"),
        ("Nom de Domaine Professionnel", "Adresse web officielle sécurisée HTTPS (ex: growth.sn ou grow-compta.sn)", "1 250 FCFA (15 000 F/an)", "1 250 FCFA", "NIC Sénégal / Namecheap"),
    ]

    for row_idx, row_data in enumerate(data, start=1):
        row_cells = table.rows[row_idx].cells
        bg_col = "FFFFFF" if row_idx % 2 != 0 else "F8FAFC"
        for col_idx, text in enumerate(row_data):
            row_cells[col_idx].width = col_widths[col_idx]
            set_cell_background(row_cells[col_idx], bg_col)
            set_cell_margins(row_cells[col_idx], top=100, bottom=100, left=100, right=100)
            p = row_cells[col_idx].paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(text)
            r.font.size = Pt(8.5)
            r.font.color.rgb = COLOR_DARK
            if col_idx == 0:
                r.font.bold = True

    # Total Row
    total_row = table.add_row()
    t_cells = total_row.cells
    for i in range(5):
        t_cells[i].width = col_widths[i]
        set_cell_background(t_cells[i], "E2E8F0")
        set_cell_margins(t_cells[i], top=120, bottom=120, left=100, right=100)
        p = t_cells[i].paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        
    t_cells[0].paragraphs[0].add_run("TOTAL ESTIMÉ / MOIS").font.bold = True
    t_cells[0].paragraphs[0].runs[0].font.size = Pt(9)
    t_cells[1].paragraphs[0].add_run("Budget mensuel complet").font.size = Pt(8.5)
    
    r_tot1 = t_cells[2].paragraphs[0].add_run("~12 000 à 15 000 FCFA\n(18 à 23 € / mois)")
    r_tot1.font.bold = True
    r_tot1.font.size = Pt(9)
    r_tot1.font.color.rgb = COLOR_TEAL

    r_tot2 = t_cells[3].paragraphs[0].add_run("~20 000 à 28 000 FCFA\n(30 à 42 € / mois)")
    r_tot2.font.bold = True
    r_tot2.font.size = Pt(9)

    t_cells[4].paragraphs[0].add_run("Tous prestataires").font.size = Pt(8.5)

    # -------------------------------------------------------------
    # 3. CE QU'IL RESTE À FAIRE AVANT DE LANCER (ROADMAP MARCHE)
    # -------------------------------------------------------------
    doc.add_page_break()
    
    h3 = doc.add_paragraph()
    h3.paragraph_format.space_before = Pt(10)
    h3.paragraph_format.space_after = Pt(6)
    r3 = h3.add_run("3. Ce qu'il reste à faire pour lancer Growth sur le marché")
    r3.font.size = Pt(14)
    r3.font.bold = True
    r3.font.color.rgb = COLOR_PRIMARY

    p_intro_actions = doc.add_paragraph()
    p_intro_actions.paragraph_format.space_after = Pt(12)
    p_intro_actions.paragraph_format.line_spacing = 1.2
    p_intro_actions.add_run(
        "Le moteur comptable SYSCOHADA SMT, les connexions d'extraction, la caisse du créateur et les interfaces (Landing page, Portail comptable, Cockpit direction) "
        "sont prêts et 100% opérationnels. Voici la liste chronologique exacte des étapes restantes pour le lancement officiel :"
    ).font.size = Pt(10)

    actions = [
        ("Étape 1 : Acheter une carte SIM dédiée (1 000 FCFA)",
         "Acheter une puce physique Orange ou Free au Sénégal (environ 1 000 F). Cette puce servira uniquement à recevoir le SMS d'authentification de Meta pour certifier le numéro WhatsApp officiel de Growth."),
        
        ("Étape 2 : Activer le numéro définitif sur Meta Developer Console",
         "Aller sur developers.facebook.com > WhatsApp > Configuration de l'API. Cliquer sur 'Ajouter un numéro de téléphone', entrer le numéro de la SIM, valider le code reçu par SMS. Le numéro est immédiatement activé sur la Cloud API sans abonnement payant."),
        
        ("Étape 3 : Passer le serveur Render en formule 'Starter' ($7 / mois)",
         "Actuellement, Render s'endort après 15 minutes d'inactivité (temps de réveil de 50 secondes au premier clic). En activant le plan Starter à $7 (environ 4 600 FCFA), votre serveur ne dort plus jamais : les alertes Wave, les vocaux et les SMS arrivent en moins de 1 seconde."),
        
        ("Étape 4 : Déposer et connecter votre Nom de Domaine Pro (Optionnel mais recommandé)",
         "Associer un domaine du type 'growth-compta.sn' ou 'growth.sn' à votre instance Render pour que l'adresse affichée aux commerçants et aux experts-comptables soit 100% prestigieuse et institutionnelle."),
        
        ("Étape 5 : Tournage et Intégration des Vidéos Éducatives WhatsApp",
         "Enregistrer 3 à 4 vidéos ultra-courtes (30 à 45 secondes) capturées directement sur votre smartphone pour guider les commerçants pas à pas sans qu'ils aient besoin de lire de longs textes."),
        
        ("Étape 6 : Test Pilote avec 2 commerçants réels à Dakar",
         "Tester de bout en bout l'onboarding avec 2 commerces pilotes (ex: une boutique de prêt-à-porter et une alimentation générale) pour valider leur enthousiasme et collecter vos premiers témoignages clients.")
    ]

    for title, desc in actions:
        p_act = doc.add_paragraph()
        p_act.paragraph_format.space_before = Pt(6)
        p_act.paragraph_format.space_after = Pt(4)
        p_act.paragraph_format.line_spacing = 1.2
        r_title = p_act.add_run(f"📌 {title}\n")
        r_title.font.bold = True
        r_title.font.size = Pt(10.5)
        r_title.font.color.rgb = COLOR_TEAL
        
        r_desc = p_act.add_run(desc)
        r_desc.font.size = Pt(9.5)
        r_desc.font.color.rgb = COLOR_DARK

    # -------------------------------------------------------------
    # 4. STRATÉGIE VIDÉOS ÉDUCATIVES WHATSAPP (DEMANDE FONDATEUR)
    # -------------------------------------------------------------
    h4 = doc.add_paragraph()
    h4.paragraph_format.space_before = Pt(20)
    h4.paragraph_format.space_after = Pt(6)
    r4 = h4.add_run("4. Intégration des Vidéos Éducatives Envoyées par Growth")
    r4.font.size = Pt(14)
    r4.font.bold = True
    r4.font.color.rgb = COLOR_PRIMARY

    p_vid_intro = doc.add_paragraph()
    p_vid_intro.paragraph_format.space_after = Pt(10)
    p_vid_intro.paragraph_format.line_spacing = 1.2
    p_vid_intro.add_run(
        "Vous avez parfaitement raison d'intégrer des vidéos : les commerçants sénégalais préfèrent regarder 30 secondes de vidéo sur WhatsApp plutôt que de lire des notices d'instructions. "
        "WhatsApp Cloud API permet d'envoyer des vidéos MP4 natives ou des liens vidéo interactifs directement dans la discussion."
    ).font.size = Pt(10)

    # Videos Table
    vid_tbl = doc.add_table(rows=5, cols=4)
    vid_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    vid_tbl.autofit = False

    vid_col_widths = [Inches(1.5), Inches(1.8), Inches(2.2), Inches(1.17)]
    vid_headers = ["Nom de la Vidéo", "Moment du déclenchement", "Contenu de la vidéo (30-45 sec)", "Format Recommandé"]

    hdr_vid_cells = vid_tbl.rows[0].cells
    for i, title in enumerate(vid_headers):
        hdr_vid_cells[i].width = vid_col_widths[i]
        set_cell_background(hdr_vid_cells[i], "222222")
        set_cell_margins(hdr_vid_cells[i], top=120, bottom=120, left=100, right=100)
        p = hdr_vid_cells[i].paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(title)
        run.font.size = Pt(9)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    vid_data = [
        ("Vidéo 1 :\nExporter le Relevé Wave", "Quand le commerçant tape 'relevé', demande son bilan, ou lors du 1er onboarding.", "Capture d'écran smartphone : Ouvrir Wave Business > Historique > Exporter en PDF > Envoyer à Growth.", "MP4 Vertical 9:16 (Moins de 10 Mo)"),
        ("Vidéo 2 :\nActiver le Webhook Ventes", "Envoyée aux commerçants Pro pour automatiser la saisie sans exporter de PDF.", "Tutoriel visuel : Activer les notifications de paiement marchand pour que chaque vente s'inscrive seule.", "MP4 Vertical 9:16 (30 secondes)"),
        ("Vidéo 3 :\nDicter un Vocal Wolof/FR", "Envoyée dès qu'un nouvel utilisateur s'inscrit sur WhatsApp.", "Démonstration vivante : Le dirigeant dicte un vocal : 'Jend na 15 000 F carburant' et Growth répond avec l'écriture SYSCOHADA.", "MP4 Vertical 9:16 (25 secondes)"),
        ("Vidéo 4 :\nOuvrir son Espace PME", "Envoyée avec le code SMS/WhatsApp pour accéder au portail web.", "Montre comment entrer son numéro, taper le code de sécurité à 6 chiffres et consulter son journal scellé.", "MP4 Vertical 9:16 (35 secondes)")
    ]

    for row_idx, row_data in enumerate(vid_data, start=1):
        row_cells = vid_tbl.rows[row_idx].cells
        bg_col = "FFFFFF" if row_idx % 2 != 0 else "F8FAFC"
        for col_idx, text in enumerate(row_data):
            row_cells[col_idx].width = vid_col_widths[col_idx]
            set_cell_background(row_cells[col_idx], bg_col)
            set_cell_margins(row_cells[col_idx], top=100, bottom=100, left=100, right=100)
            p = row_cells[col_idx].paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(text)
            r.font.size = Pt(8.5)
            r.font.color.rgb = COLOR_DARK
            if col_idx == 0:
                r.font.bold = True

    # -------------------------------------------------------------
    # 5. CALENDRIER DE DÉPLOIEMENT CONSEILLÉ (J-7 À J-0)
    # -------------------------------------------------------------
    h5 = doc.add_paragraph()
    h5.paragraph_format.space_before = Pt(20)
    h5.paragraph_format.space_after = Pt(6)
    r5 = h5.add_run("5. Calendrier de Déploiement Recommandé (1 Semaine)")
    r5.font.size = Pt(14)
    r5.font.bold = True
    r5.font.color.rgb = COLOR_PRIMARY

    timeline = [
        ("Jour 1 (Aujourd'hui) :", "Passer Render en plan Starter ($7) pour que le serveur réponde instantanément 24h/24 sans mise en veille."),
        ("Jour 2 :", "Acheter la puce SIM et certifier le numéro officiel d'entreprise sur Meta Developer Console."),
        ("Jour 3 :", "Enregistrer les 2 vidéos prioritaires avec votre smartphone (Vidéo Relevé Wave + Vidéo Vocal Wolof)."),
        ("Jour 4 :", "Mettre en ligne les vidéos sur le serveur pour que Growth les envoie automatiquement aux commerçants."),
        ("Jour 5 & 6 :", "Tester l'onboarding réel avec 2 commerçants de votre entourage à Dakar."),
        ("Jour 7 :", "Lancement officiel : communication commerciale, prospection des cabinets comptables et des PME.")
    ]

    for j, desc in timeline:
        p_t = doc.add_paragraph()
        p_t.paragraph_format.space_before = Pt(3)
        p_t.paragraph_format.space_after = Pt(3)
        p_t.paragraph_format.line_spacing = 1.15
        r_j = p_t.add_run(f"🗓️ {j} ")
        r_j.font.bold = True
        r_j.font.size = Pt(9.5)
        r_j.font.color.rgb = COLOR_PRIMARY
        
        r_d = p_t.add_run(desc)
        r_d.font.size = Pt(9.5)
        r_d.font.color.rgb = COLOR_DARK

    # Signature block
    p_sig = doc.add_paragraph()
    p_sig.paragraph_format.space_before = Pt(25)
    p_sig.paragraph_format.space_after = Pt(0)
    p_sig.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_sig1 = p_sig.add_run("Direction Stratégique Growth • Sénégal\n")
    r_sig1.font.bold = True
    r_sig1.font.size = Pt(10)
    r_sig1.font.color.rgb = COLOR_PRIMARY
    
    r_sig2 = p_sig.add_run("Le copilote comptable et financier des 400 000 PME et cabinets sénégalais.")
    r_sig2.font.italic = True
    r_sig2.font.size = Pt(9)
    r_sig2.font.color.rgb = COLOR_MUTED

    # Save to disk
    output_path = os.path.abspath("PLAN_LANCEMENT_ET_COUTS_MENSUELS_GROWTH.docx")
    doc.save(output_path)
    print(f"Document Word generated successfully at: {output_path}")

if __name__ == "__main__":
    create_document()

"""
Générateur du Document Word Officiel : SCENARIO_OFFICIEL_CLIENT_GROWTH_SYSCOHADA.docx
Contient l'intégralité du scénario client de A à Z avec les plus hauts standards de mise en page.
"""

import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

DOC_PATH = "SCENARIO_OFFICIEL_CLIENT_GROWTH_SYSCOHADA.docx"

def set_cell_background(cell, hex_color):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=120, bottom=120, left=150, right=150):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def create_document():
    doc = docx.Document()
    
    # Marges 2 cm
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)
        section.different_first_page_header_footer = False
        header = section.header
        p_hdr = header.paragraphs[0]
        p_hdr.text = "GROWTH SYSCOHADA SMT • CHARTE OPÉRATIONNELLE DU PARCOURS CLIENT OFFICIEL"
        p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_hdr.runs[0].font.size = Pt(8.5)
        p_hdr.runs[0].font.color.rgb = RGBColor(148, 163, 184)

    # TITRE PRINCIPAL
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_sub = p_title.add_run("RÉPUBLIQUE DU SÉNÉGAL • PROTOCOLE FINTECH CONFORME SYSCOHADA SMT & DGID\n")
    r_sub.font.size = Pt(9.5)
    r_sub.font.bold = True
    r_sub.font.color.rgb = RGBColor(16, 185, 129)
    
    r_main = p_title.add_run("GROWTH • LE SCÉNARIO CLIENT OFFICIEL DE A À Z\n")
    r_main.font.size = Pt(22)
    r_main.font.bold = True
    r_main.font.color.rgb = RGBColor(15, 23, 42)

    r_desc = p_title.add_run("Guide d'Exécution Intégral : De la Découverte WhatsApp au Grand Rituel de Clôture et à la Certification Cabinet")
    r_desc.font.size = Pt(11)
    r_desc.font.italic = True
    r_desc.font.color.rgb = RGBColor(100, 116, 139)

    doc.add_paragraph()

    # ENCART DE DIRECTION
    table_dir = doc.add_table(rows=1, cols=1)
    table_dir.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell_dir = table_dir.rows[0].cells[0]
    set_cell_background(cell_dir, "0F172A")
    set_cell_margins(cell_dir, 160, 160, 200, 200)
    p_dir = cell_dir.paragraphs[0]
    r_dir = p_dir.add_run("⭐ VISION DIRECTRICE DE LA FONDATRICE (MME ADAISSO)\n")
    r_dir.font.bold = True
    r_dir.font.size = Pt(11.5)
    r_dir.font.color.rgb = RGBColor(160, 217, 210)
    r_dir_body = p_dir.add_run(
        "Ce document formalise à 100% l'expérience vécue par le commerçant sénégalais. "
        "Il allie la simplicité absolue du quotidien (WhatsApp, notes vocales en Wolof et Français, aucune installation de logiciel) "
        "à la plus haute rigueur financière et juridique (séparation des flux personnels et marchands, inventaire évalué au coût d'achat grossiste, "
        "calcul automatique des amortissements sur 5 et 10 ans, et verrouillage strict par lien de paiement professionnel sécurisé)."
    )
    r_dir_body.font.size = Pt(10)
    r_dir_body.font.color.rgb = RGBColor(241, 245, 249)

    doc.add_paragraph()

    # SOMMAIRE
    doc.add_heading("Table des Matières du Parcours", level=2)
    p_somm = doc.add_paragraph()
    p_somm.paragraph_format.line_spacing = 1.3
    sommaire_items = [
        "1. Étape 1 : Premier Contact & Accueil Personnalisé (Vidéo Démo Officielle de 28s)",
        "2. Étape 2 : Choix Opérateur Marchand & Avertissement Légal Preuves Financières",
        "3. Gestion Avancée du Multi-Comptes (Wave Business, Orange Business, Perso & Cash)",
        "4. Étape 3 : Fiche d'Identité de l'Entreprise (NINEA, RCCM, Nom Commercial & Verrou)",
        "5. Étape 4 : Historique Passé & Bilan d'Ouverture (Tutos Relevés & Règle Capture Solde)",
        "6. Étape 5 : Inventaire Initial Complet (Protocole d'Expert-Comptable ONECCA / SYSCOHADA)",
        "7. Étape 6 : Essai Gratuit 7 Jours Offert & Verrouillage Post-Essai par Lien Wave Officiel",
        "8. Étape 7 : Routine Quotidienne Active (Saisie Vocale 1.5s, Encaissement Silencieux & Clôture à 00h00)",
        "9. Synchronisation avec l'Espace Cabinet Comptable & Export DGID"
    ]
    for s in sommaire_items:
        r = p_somm.add_run(s + "\n")
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor(51, 65, 85)

    doc.add_page_break()

    # =========================================================================
    # ÉTAPE 1
    # =========================================================================
    doc.add_heading("ÉTAPE 1 : PREMIER CONTACT & ACCUEIL CHALEUREUX", level=1)
    
    p = doc.add_paragraph()
    p.add_run("1.1 Déclencheur du Commerçant :\n").bold = True
    p.add_run("Le commerçant enregistre le numéro officiel WhatsApp de Growth et envoie un premier message spontané (ex : « Salam », « Bonjour », « C'est quoi Growth ? »).\n\n")
    p.add_run("1.2 Réaction Instantanée de Growth (1,5 seconde chrono) :\n").bold = True
    p.add_run("Growth extrait automatiquement le prénom et le nom configurés sur le profil WhatsApp de l'expéditeur et lui répond de façon personnalisée :\n")

    # Message WhatsApp Block
    t_msg1 = doc.add_table(rows=1, cols=1)
    c1 = t_msg1.rows[0].cells[0]
    set_cell_background(c1, "F0FDF4")
    set_cell_margins(c1, 120, 120, 160, 160)
    p_m1 = c1.paragraphs[0]
    p_m1.add_run("« Salam [Prénom Commerçant] ! Bienvenue sur Growth, votre copilote financier officiel sur WhatsApp.\n\n"
                 "Fini les cahiers de brouillon, les reçus froissés et les calculs de tête : vous me dictez vos ventes et vos dépenses par message vocal ou texte (en Wolof ou en Français), et je tiens votre caisse et vos comptes au centime près.\n\n"
                 "🎬 Regardez d'abord cette courte vidéo de 28 secondes pour voir comment Growth fonctionne au quotidien. »").font.size = Pt(9.5)

    doc.add_paragraph()
    p_vid = doc.add_paragraph()
    p_vid.add_run("1.3 Délivrance de la Vidéo Démo Officielle n°1 :\n").bold = True
    p_vid.add_run("Growth envoie la vidéo MP4 native (540x960, format vertical 9:16 pour smartphone) avec voix off professionnelle, sous-titres émeraude, animation des bulles de messages WhatsApp et aperçu du rituel du soir.\n")
    p_vid.add_run("1.4 Transition :\n").bold = True
    p_vid.add_run("Le commerçant répond « OK », « Vu » ou clique sur le bouton interactif pour démarrer son onboarding.")

    doc.add_paragraph()

    # =========================================================================
    # ÉTAPE 2
    # =========================================================================
    doc.add_heading("ÉTAPE 2 : CHOIX DE L'OPÉRATEUR MARCHAND & AVERTISSEMENT LÉGAL", level=1)
    
    p_warn = doc.add_paragraph()
    p_warn.add_run("2.1 L'Avertissement Légal & Fiscale Solennel de Growth :\n").bold = True
    p_warn.add_run("Avant tout choix technique, Growth pose la règle fondamentale de conformité bancaire et fiscale sénégalaise :\n")

    t_msg2 = doc.add_table(rows=1, cols=1)
    c2 = t_msg2.rows[0].cells[0]
    set_cell_background(c2, "FEF2F2")
    set_cell_margins(c2, 120, 120, 160, 160)
    p_m2 = c2.paragraphs[0]
    p_m2.add_run("« ⚠️ Règle Légale & Preuves Financières :\n"
                 "Growth ne peut vous aider à certifier vos comptes et à constituer de véritables preuves financières officielles "
                 "(reconnues par les banques pour vos demandes de prêt et par la DGID/impôts) QUE si vous utilisez un compte Wave Business et/ou Orange Business, et JAMAIS un compte personnel.\n\n"
                 "Un compte personnel mélange vos dépenses de famille avec votre boutique et n'a aucune valeur juridique pour les banques. "
                 "Un compte Business sépare votre argent professionnel et donne une valeur légale à chacune de vos ventes. »").font.size = Pt(9.5)

    doc.add_paragraph()
    p_btn = doc.add_paragraph()
    p_btn.add_run("2.2 Le Menu de Sélection par Boutons Interactifs WhatsApp (1 Clic) :\n").bold = True
    p_btn.add_run("Growth affiche le menu à choix unique :\n"
                  "• [Bouton A : 🌊 Wave Business uniquement]\n"
                  "• [Bouton B : 🍊 Orange Business uniquement]\n"
                  "• [Bouton C : 🚀 Les deux (Wave Business + Orange Business)]\n"
                  "• [Bouton D : 📱 J'utilise des comptes Personnels (Wave perso / OM perso / Espèces)]\n"
                  "• [Bouton E : 🚀 J'ai TOUT (Wave Business + Orange Business + Perso + Espèces)]\n\n")

    p_btn.add_run("2.3 Traitement des Flux Business (Boutons A, B, C) :\n").bold = True
    p_btn.add_run("Pour chaque opérateur Business sélectionné, Growth délivre la vidéo tutoriel dédiée expliquant comment récupérer l'URL Webhook sur le portail marchand Wave ou Orange Partner Sonatel. Dès réception du lien, la passerelle webhook est scellée.\n")

    # =========================================================================
    # MULTI-COMPTES & GESTION DES 5 CANAUX
    # =========================================================================
    doc.add_heading("3. GESTION DU MULTI-COMPTES (LES 5 CANAUX SIMULTANÉS)", level=2)
    p_multi = doc.add_paragraph()
    p_multi.add_run("Dans la réalité dakaroise, un commerçant possède très souvent les 5 canaux en même temps dans sa boutique :\n"
                    "1. 🌊 Wave Business (Son QR code marchand officiel sur le comptoir)\n"
                    "2. 🍊 Orange Business (Sa ligne marchande Sonatel officielle)\n"
                    "3. 📱 Wave Personnel (Sa puce personnelle où des clients réguliers lui transfèrent)\n"
                    "4. 📲 Orange Money Personnel (Son compte personnel où des proches payent)\n"
                    "5. 💵 Caisse Espèces Physique (Les billets et pièces dans le tiroir du meuble de caisse)\n\n")
    p_multi.add_run("Protocole de Traitement Growth pour les 5 Canaux :\n").bold = True
    p_multi.add_run("• Pour les 2 comptes Business : Liaison des 2 Webhooks et téléchargement des 2 relevés marchands en PDF.\n"
                    "• Pour les 2 comptes Personnels : Capture d'écran obligatoire des soldes actuels comme preuve de départ.\n"
                    "• Pour la Caisse Espèces : Recensement immédiat du montant liquide en caisse.\n"
                    "• Au Rituel du Soir : Ventilation distincte des 5 soldes sans aucun mélange, avec mention claire de la part certifiée bancaire.")

    doc.add_paragraph()

    # =========================================================================
    # ÉTAPE 3
    # =========================================================================
    doc.add_heading("ÉTAPE 3 : IDENTIFICATION LÉGALE DE L'ENTREPRISE (NINEA & RCCM)", level=1)
    p_ent = doc.add_paragraph()
    p_ent.add_run("3.1 Demande des Documents Officiels :\n").bold = True
    p_ent.add_run("Growth demande : « Passons à l'identification officielle de votre commerce. Avez-vous un document NINEA ou un Registre de Commerce (RCCM) pour votre boutique ? »\n\n")
    
    p_ent.add_run("Branche 1 : Le commerçant A son NINEA / RCCM :\n").bold = True
    p_ent.add_run("1. Envoi de la photo nette du document. Stockage immédiat en base de données sécurisée comme pièce maîtresse légale.\n"
                  "2. L'IA analyse l'image et extrait : Le Nom & Prénom de la personne physique (propriétaire légal ANSD), le Numéro NINEA officiel, le Secteur d'activité et le Capital social.\n"
                  "3. Relevé du Nom Commercial : Comme le nom d'enseigne n'apparaît pas sur le document personnel, Growth demande explicitement : « Quel est le Nom Commercial ou l'Enseigne de votre boutique ? »\n"
                  "4. Scellage Final : Présentation du récapitulatif consolidé combinant le nom de boutique et les données extraites du NINEA.\n\n")
    
    p_ent.add_run("Branche 2 : Le commerçant N'A PAS de NINEA / RCCM :\n").bold = True
    p_ent.add_run("1. Conseil Officiel de l'État : Growth lui rappelle qu'il est vivement recommandé d'immatriculer son commerce auprès des services de l'État pour être crédible et accéder aux crédits bancaires.\n"
                  "2. Recueil manuel obligatoire : Nom commercial de la boutique, secteur d'activité exact et capital de départ estimé.\n\n")

    p_ent.add_run("⛔ VERROU STRICT DU TUNNEL (ÉTAPE 3) :\n").bold = True
    p_ent.add_run("Tant que l'identité de l'entreprise n'est pas scellée, Growth refuse catégoriquement de traiter toute autre opération ou question financière. Le commerçant est poliment recadré.")

    doc.add_paragraph()

    # =========================================================================
    # ÉTAPE 4
    # =========================================================================
    doc.add_heading("ÉTAPE 4 : HISTORIQUE PASSÉ & BILAN D'OUVERTURE DU PASSÉ", level=1)
    p_hist = doc.add_paragraph()
    p_hist.add_run("4.1 Collecte des Relevés pour les Comptes Marchands Business :\n").bold = True
    p_hist.add_run("Growth envoie les vidéos tutoriels pour exporter les relevés Wave Business et Orange Business en PDF depuis le portail, puis fusionne l'historique.\n\n")

    p_hist.add_run("4.2 Protocole Spécifique pour la Transition depuis Compte Personnel :\n").bold = True
    p_hist.add_run("Pour le commerçant qui ouvre son compte Business, Growth lui explique chronologiquement :\n")

    t_msg4 = doc.add_table(rows=1, cols=1)
    c4 = t_msg4.rows[0].cells[0]
    set_cell_background(c4, "EFF6FF")
    set_cell_margins(c4, 120, 120, 160, 160)
    p_m4 = c4.paragraphs[0]
    p_m4.add_run("« ℹ️ Pour votre Bilan de Départ :\n"
                 "Comme vous ouvrez votre nouveau compte Business, vous n'avez pas d'ancien historique marchand à télécharger sur le portail.\n\n"
                 "C'est la capture d'écran de votre solde actuel (sur vos comptes personnels Wave ou Orange Money) qui remplace l'ancien relevé "
                 "et constitue la preuve officielle de votre trésorerie de départ. Veuillez me l'envoyer ici. »").font.size = Pt(9.5)

    doc.add_paragraph()
    p_dcond = doc.add_paragraph()
    p_dcond.add_run("⛔ DOUBLE CONDITION & VERROU STRICT DU CHOIX PERSONNEL :\n").bold = True
    p_dcond.add_run("Tant que le commerçant n'a pas validé les deux conditions suivantes :\n"
                    "1️⃣ Avoir activé son compte Wave Business ou Orange Business.\n"
                    "2️⃣ Avoir envoyé la capture d'écran de son solde de départ.\n"
                    "Growth bloque la suite avec le message : « Dès que ces 2 éléments sont réunis, alors là oui, nous continuons immédiatement votre inscription ! »")

    doc.add_paragraph()

    # =========================================================================
    # ÉTAPE 5 : INVENTAIRE ET CAISSE
    # =========================================================================
    doc.add_heading("ÉTAPE 5 : INVENTAIRE INITIAL COMPLET (STANDARDS ONECCA / SYSCOHADA)", level=1)
    p_inv = doc.add_paragraph()
    p_inv.add_run("Growth déploie le protocole complet d'un cabinet d'audit dakarois en 5 piliers patrimoniaux avec pièces justificatives obligatoires et comptage physique des espèces :\n\n")

    p_cash_alert = doc.add_paragraph()
    p_cash_alert.add_run("💵 RAPPEL CAPITAL : LE COMPTAGE PHYSIQUE DES ESPÈCES (COMPTE 571) :\n").bold = True
    p_cash_alert.add_run("Au Sénégal, une part prépondérante du commerce tourne en liquide. Growth ne se contente pas des flux Mobile Money : il exige le recensement exact des billets et pièces en caisse physique :\n")

    t_msg_cash = doc.add_table(rows=1, cols=1)
    c_cash = t_msg_cash.rows[0].cells[0]
    set_cell_background(c_cash, "FEFCE8")
    set_cell_margins(c_cash, 120, 120, 160, 160)
    p_mcash = c_cash.paragraphs[0]
    p_mcash.add_run("« 💵 Comptage Obligatoire de votre Caisse Espèces (Tiroir) :\n"
                    "En dehors de vos comptes Wave et Orange Money, combien avez-vous physiquement en liquide (billets et pièces de monnaie) "
                    "dans votre tiroir-caisse, meuble ou coffre de boutique maintenant ?\n\n"
                    "👉 Dites-moi simplement le montant exact en FCFA (exemple : « J'ai 175 000 F en espèces dans ma caisse »). »").font.size = Pt(9.5)

    doc.add_paragraph()

    # Tableau Récapitulatif Inventaire
    t_inv = doc.add_table(rows=6, cols=3)
    t_inv.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Composante Patrimoniale", "Questions d'Audit & Méthode", "Justificatif & Règle SYSCOHADA"]
    for j, h in enumerate(headers):
        cell = t_inv.rows[0].cells[j]
        set_cell_background(cell, "1E293B")
        set_cell_margins(cell, 100, 100, 120, 120)
        p_h = cell.paragraphs[0]
        r = p_h.add_run(h)
        r.font.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(255, 255, 255)

    rows_data = [
        ("A. Immobilisations (Comptes 24 & 28)", "Désignation, date d'acquisition, valeur d'achat en FCFA.", "Facture ou photo. Calcul auto de la VNC et amortissement (5 ans à 20% machines, 10 ans à 10% mobilier)."),
        ("B. Stocks de Marchandises (Comptes 31 & 6031)", "Photos d'ensemble des rayons/magasin, 3 à 5 articles phares au prix d'achat grossiste (PUMP), avaries/pertes.", "Photo nette obligatoire. Évaluation stricte au coût d'achat hors marge."),
        ("C. Créances Clients / Crédits (Comptes 411 & 416)", "Photo du carnet de crédits, nom des débiteurs, montants dus, retards de plus de 60-90 jours.", "Photo du carnet. Calcul des provisions pour créances douteuses."),
        ("D. Dettes & Engagements (Comptes 401 & 162)", "Factures grossistes impayées, échéances de microfinance (CMS, PAMECAS, ACEP), tontines professionnelles.", "Photo des factures impayées. Recensement intégral du passif exigible."),
        ("E. Rapprochement de Caisse (Comptes 521 & 571)", "Comptage physique des espèces dans le tiroir + soldes certifiés Mobile Money.", "Procès-verbal de caisse de départ.")
    ]

    for i, row in enumerate(rows_data):
        r_cells = t_inv.rows[i+1].cells
        for j, val in enumerate(row):
            cell = r_cells[j]
            set_cell_background(cell, "F8FAFC" if i % 2 == 0 else "FFFFFF")
            set_cell_margins(cell, 80, 80, 100, 100)
            p_c = cell.paragraphs[0]
            r = p_c.add_run(val)
            r.font.size = Pt(8.5)

    doc.add_paragraph()
    p_eq = doc.add_paragraph()
    p_eq.add_run("Équilibre Fondamental du Bilan d'Ouverture :\n").bold = True
    p_eq.add_run("ACTIF (Immobilisations VNC + Stocks PUMP + Créances + Trésorerie) = PASSIF (Dettes Fournisseurs + Emprunts + Capitaux Propres 101).\n"
                 "Growth scelle et présente le Bilan d'Ouverture certifié au commerçant.")

    doc.add_paragraph()

    # =========================================================================
    # ÉTAPE 6
    # =========================================================================
    doc.add_heading("ÉTAPE 6 : ESSAI GRATUIT 7 JOURS OFFERT & VERROUILLAGE POST-ESSAI", level=1)
    p_pay = doc.add_paragraph()
    p_pay.add_run("6.1 Cadeau de Bienvenue : 7 Jours d'Essai Gratuit 100% Offerts :\n").bold = True
    p_pay.add_run("Dès que le Bilan d'Ouverture initial est scellé, Growth n'impose aucun blocage prématuré ni carte bancaire. "
                  "Le commerçant reçoit automatiquement un Pack Découverte de 7 jours complets d'accès illimité (statut ESSAI_7J) "
                  "pour tester l'assistant vocal en conditions réelles dans son commerce.\n\n")

    p_pay.add_run("6.2 Message de Scellage et Déblocage Immédiat :\n").bold = True
    
    t_msg6 = doc.add_table(rows=1, cols=1)
    c6 = t_msg6.rows[0].cells[0]
    set_cell_background(c6, "F0FDF4")
    set_cell_margins(c6, 120, 120, 160, 160)
    p_m6 = c6.paragraphs[0]
    p_m6.add_run("« 🎉 Félicitations [Nom Entreprise] ! Votre dossier d'entreprise et votre Bilan d'Ouverture initial sont 100% scellés conformes SYSCOHADA SMT !\n\n"
                 "📊 Votre Bilan d'Ouverture Certifié :\n"
                 "• 💵 Caisse Espèces Tiroir (571) : [Montant] FCFA\n"
                 "• 📱 Trésorerie Comptes Marchands (521) : [Montant] FCFA\n"
                 "• 📦 Stock de Marchandises Grossiste (311) : [Montant] FCFA\n"
                 "• 🛠️ Immobilisations & Équipements (241) : [Montant] FCFA (Amortissements programmés)\n"
                 "• 🤝 Créances Clients (411) : [Montant] FCFA\n"
                 "• 💼 Dettes Fournisseurs (401) : [Montant] FCFA\n\n"
                 "🎁 VOTRE CADEAU DE BIENVENUE : 7 JOURS D'ESSAI GRATUIT OFFERTS !\n"
                 "Pour vous permettre de vivre l'expérience Growth en situation réelle dans votre boutique, nous vous offrons 7 jours d'accès complet 100% gratuit jusqu'au [Date J+7] (aucun engagement, aucune carte requise).\n\n"
                 "⚡ Toutes vos fonctionnalités sont débloquées dès maintenant :\n"
                 "• Saisie vocale de vos ventes et dépenses en 1.5s chrono (Wolof ou Français)\n"
                 "• Encaissements numériques Wave Business silencieux et automatiques\n"
                 "• Grand Rituel de Clôture consolidé chaque soir à 00h00 (avec note vocale audio et Journal Web)\n\n"
                 "👉 Faites le test tout de suite : dictez-moi votre première vente, dépense ou envoyez votre premier reçu en note vocale 🎙️ !\n\n"
                 "💡 Pourquoi 10 000 F (seulement 330 F/jour) avec Growth ?\n"
                 "Là où un cabinet comptable classique vous demande plus de 50 000 FCFA/mois rien que pour récolter péniblement vos reçus et vous en redemande encore pour monter le bilan, chez Growth la collecte est 100% vocale et automatique avec une simplicité absolue pour seulement 330 F / jour ! Et en cas de besoin de bilan officiel (demande de prêt bancaire, visa fiscal DGID, etc.), rendez-vous directement chez nos cabinets comptables partenaires agréés avec vos données déjà 100% prêtes.\n\n"
                 "👉 Tranquillité d'esprit (Optionnel) : Si vous souhaitez régler votre abonnement dès aujourd'hui sans attendre, vos 30 jours s'ajouteront directement à vos 7 jours offerts (soit 37 jours de sérénité totale) :\n"
                 "👉 Lien de règlement Wave : https://grow-2epo.onrender.com/abonnement?phone=[Telephone] »").font.size = Pt(9.5)

    doc.add_paragraph()
    p_anti = doc.add_paragraph()
    p_anti.add_run("6.3 Liberté de Paiement Immédiat Anticipé (Cumul 7j + 30j = 37 Jours de Sérénité) :\n").bold = True
    p_anti.add_run("Si le commerçant est immédiatement convaincu lors de son inscription et souhaite régler sur-le-champ pour avoir l'esprit tranquille "
                   "et ne pas se soucier des relances, Growth lui offre cette liberté totale sans friction :\n"
                   "• Formule psychologique ultra-accessible : seulement 330 FCFA par jour (soit 10 000 FCFA / mois), soit moins qu'un café ou une miche de pain par jour pour s'offrir un expert comptable 24h/24.\n"
                   "• Le règlement de l'abonnement par le lien Wave est pris en compte instantanément.\n"
                   "• L'algorithme prolonge automatiquement l'échéance de 30 jours au-delà des 7 jours d'essai déjà offerts.\n"
                   "• Le commerçant bénéficie ainsi de 37 jours consécutifs d'assistance 24h/24 sans aucune interruption de service.\n\n")

    p_rel = doc.add_paragraph()
    p_rel.add_run("6.4 Relance Bienveillante à J-2 de l'Échéance (48h avant la Fin de l'Essai) :\n").bold = True
    p_rel.add_run("Pour les commerçants n'ayant pas payé d'avance, à 48 heures de la clôture des 7 jours, le système envoie une notification amicale avec une offre de bienvenue exclusive :\n"
                  "• 1 000 FCFA de réduction fidélité : seulement 300 FCFA par jour (soit 9 000 FCFA / mois au lieu de 10 000 FCFA) pour le premier mois si renouvelé avant la coupure.\n"
                  "• Les 30 jours payés s'ajoutent à la suite des jours d'essai restants (aucun jour offert n'est perdu).\n\n")

    p_paylock = doc.add_paragraph()
    p_paylock.add_run("6.5 Coupure Stricte à J+7 & Verrou de Paiement Wave Officiel :\n").bold = True
    p_paylock.add_run("• Dès que les 7 jours sont écoulés sans souscription, Growth suspend strictement tout enregistrement d'écriture.\n"
                      "• Le message de verrouillage annonce poliment la fin de l'essai et fournit le lien Wave officiel sécurisé (seulement 330 F par jour, soit 10 000 FCFA / mois) :\n"
                      "  https://grow-2epo.onrender.com/abonnement?phone=[Telephone]\n"
                      "• Dès le paiement validé (ou mot-clé « J'ai payé »), le compte est réactivé instantanément 24h/24 pour 30 jours.\n\n")

    # SOUS-SECTION COMPARATIF STRATÉGIQUE CABINET TRADITIONNEL VS GROWTH
    p_comp = doc.add_paragraph()
    p_comp.add_run("6.6 Modèle Économique Révolutionnaire : Comparatif Cabinet Traditionnel vs GROWTH :\n").bold = True
    p_comp.add_run("Pourquoi payer plus de 50 000 FCFA / mois pour collecter des reçus papier ? Growth propose une rupture totale sur le marché sénégalais :\n\n")

    t_comp = doc.add_table(rows=5, cols=3)
    t_comp.alignment = WD_TABLE_ALIGNMENT.CENTER
    comp_headers = ["Critère Opérationnel", "Cabinet Comptable Traditionnel", "Solution Hybride GROWTH"]
    for j, h in enumerate(comp_headers):
        cell = t_comp.rows[0].cells[j]
        set_cell_background(cell, "0F172A")
        set_cell_margins(cell, 100, 100, 120, 120)
        p_h = cell.paragraphs[0]
        r = p_h.add_run(h)
        r.font.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(255, 255, 255)

    comp_data = [
        ("Collecte & Saisie des Flux Quotidiens", 
         "+50 000 F à 100 000 F / mois rien que pour récolter et saisir à la main des factures froissées et carnets.", 
         "Seulement 330 F / jour (10 000 F / mois) avec une simplicité absolue : dictée vocale 1.5s Wolof/Français & encaissements Wave 100% automatiques."),
        ("Charge Mentale & Déplacements", 
         "Lourde : allers-retours physiques, reçus égarés, relances incessantes, saisie tardive.", 
         "Nulle : zéro déplacement, zéro logiciel à installer, caisse scellée et réconciliée chaque soir à 00h00 sur WhatsApp."),
        ("Bilans Officiels & Demandes de Prêt Bancaire", 
         "Surfacturation très élevée en fin d'année ou lors d'une demande de crédit bancaire pour reconstruire l'historique.", 
         "Données 100% conformes SYSCOHADA SMT en temps réel. Le commerçant se rend chez nos Cabinets Comptables Partenaires Agréés ONECCA qui certifient le bilan en 1 clic à tarif négocié !"),
        ("Rentabilité & Économies pour la PME", 
         "Coût prohibitif et réservé aux grandes structures.", 
         "Plus de 80% d'économies directes tout en offrant un dossier financier irréprochable aux banques.")
    ]

    for i, row in enumerate(comp_data):
        r_cells = t_comp.rows[i+1].cells
        for j, val in enumerate(row):
            cell = r_cells[j]
            set_cell_background(cell, "F8FAFC" if i % 2 == 0 else "FFFFFF")
            set_cell_margins(cell, 80, 80, 100, 100)
            p_c = cell.paragraphs[0]
            r = p_c.add_run(val)
            r.font.size = Pt(8.5)
            if j == 2:
                r.font.bold = True
                r.font.color.rgb = RGBColor(5, 150, 105)

    doc.add_paragraph()

    # =========================================================================
    # ÉTAPE 7
    # =========================================================================
    doc.add_heading("ÉTAPE 7 : ROUTINE QUOTIDIENNE ACTIVE & RITUELS DE CLÔTURE", level=1)
    p_rout = doc.add_paragraph()
    p_rout.add_run("Pendant l'essai gratuit de 7 jours et dès validation de l'abonnement mensuel, le compte fonctionne en régime de croisière actif :\n\n")

    p_rout.add_run("7.1 Enregistrement des Ventes et Dépenses en Journée :\n").bold = True
    p_rout.add_run("• Ventes/dépenses dictées en note vocale (Wolof ou Français dakarois) ou par texte -> Imputées au compte SYSCOHADA (701 Ventes, 601 Achats, 605 Charges) en 1.5 seconde chrono.\n"
                   "• Encaissements Wave Business reçus par webhook en direct -> Enregistrés 100% silencieusement sans notification intempestive en journée pour zéro saturation WhatsApp.\n"
                   "• Flux reçus exceptionnellement sur compte personnel -> Dictés par vocal avec conseil bienveillant de faire scanner le QR Wave Business officiel.\n\n")

    p_rout.add_run("7.2 Système des Relances Actives Toutes les 3 Heures :\n").bold = True
    p_rout.add_run("• ⏰ 11h30 (Point Espèces & Popote) : Rappel amical pour enregistrer les sorties liquides (repas midi, monnaie, déchargement).\n"
                   "• ⏰ 15h00 (Point Stocks & Grossistes) : Rappel pour noter les arrivages de marchandises et variations de prix d'achat grossistes.\n"
                   "• ⏰ 18h00 (Point Matériel & Grosses Dépenses) : Vérification des réparations, pannes ou achats d'équipements de l'après-midi.\n\n")

    p_rout.add_run("7.3 À 00h00 (Minuit pile) : Le Grand Rituel de Caisse Consolidé :\n").bold = True
    p_rout.add_run("Envoi automatique du bilan de la journée comprenant :\n"
                   "1. Le message texte synthétique avec ventilation des 5 poches de trésorerie (Wave Business, OM Business, Wave Perso, OM Perso, Cash tiroir).\n"
                   "2. La Note Vocale Audio officielle (Voix unique multilingue Ava) lue avec chaleur et clarté.\n"
                   "3. La consigne de repos : « Il est minuit, dormez en paix ! Vous pourrez valider votre caisse ou me répondre demain matin dès 06h00 à votre réveil... ».\n"
                   "4. Accueil matinal à 06h00 avec le point du jour et le rattrapage éventuel.\n\n")

    p_rout.add_run("7.4 Consultation Journal & Espace Cabinet :\n").bold = True
    p_rout.add_run("• Le commerçant accède à son journal scellé en direct sur https://grow-2epo.onrender.com/journal?phone=...\n"
                   "• L'expert-comptable supervise le dossier sur https://grow-2epo.onrender.com/comptable et télécharge en 1 clic la Liasse SYSCOHADA SMT et le fichier FEC officiel pour la DGID.")

    doc.save(DOC_PATH)
    print(f"✅ Document Word généré avec succès : {DOC_PATH} ({os.path.getsize(DOC_PATH)} octets)")

if __name__ == "__main__":
    create_document()

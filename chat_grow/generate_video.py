"""
Générateur de Vidéo Officielle de Démonstration Growth pour Commerçants et PME.
Génère une vidéo MP4 H.264 / AAC au format vertical 9:16 adaptée pour WhatsApp.
"""

import os
import sys
import asyncio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import edge_tts
import av

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
VIDEOS_DIR = os.path.join(STATIC_DIR, "videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

OUTPUT_MP4 = os.path.join(VIDEOS_DIR, "growth_demo_officielle.mp4")
TEMP_AUDIO = os.path.join(VIDEOS_DIR, "temp_voiceover.mp3")

WIDTH = 540
HEIGHT = 960
FPS = 24

VOICEOVER_TEXT = (
    "Bienvenue sur Growth, votre copilote financier sur WhatsApp ! "
    "Plus besoin de cahier ni de calculs compliqués : "
    "Vous dictez simplement vos ventes et vos dépenses par note vocale ou message. "
    "Growth analyse et enregistre automatiquement chaque opération au standard SYSCOHADA. "
    "Chaque soir à vingt heures, recevez votre clôture de caisse et votre bilan certifié. "
    "Et votre comptable exporte vos liasses en un clic. "
    "Rejoignez dès aujourd'hui les commerçants qui gèrent leur argent en toute sérénité !"
)

def get_fonts():
    try:
        font_title = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 32)
        font_h2 = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 24)
        font_body = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 18)
        font_body_bold = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 19)
        font_small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
        font_big_kpi = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 44)
    except Exception:
        font_title = ImageFont.load_default()
        font_h2 = font_title
        font_body = font_title
        font_body_bold = font_title
        font_small = font_title
        font_big_kpi = font_title
    return font_title, font_h2, font_body, font_body_bold, font_small, font_big_kpi

async def generer_audio():
    print("[1/3] Génération de la voix off avec edge-tts...")
    communicate = edge_tts.Communicate(VOICEOVER_TEXT, "fr-FR-HenriNeural", rate="+8%")
    await communicate.save(TEMP_AUDIO)
    print(f"Voix off générée : {TEMP_AUDIO}")

def get_audio_duration(audio_path):
    container = av.open(audio_path)
    stream = container.streams.audio[0]
    duration_sec = float(stream.duration * stream.time_base)
    container.close()
    return duration_sec

def draw_header(draw, logo_img, font_h2, font_small):
    # Barre supérieure WhatsApp
    draw.rectangle([(0, 0), (WIDTH, 90)], fill="#075E54")
    if logo_img:
        logo_thumb = logo_img.resize((50, 50))
        draw.bitmap((20, 20), logo_thumb)
    draw.text((80, 22), "Growth Officiel • Copilote SMT", fill="#FFFFFF", font=font_h2)
    draw.text((80, 54), "✅ Compte Professionnel Certifié • En ligne", fill="#A0D9D2", font=font_small)

def draw_phone_frame(draw):
    draw.rectangle([(0, 0), (WIDTH, HEIGHT)], fill="#0B111E")
    # Fond discret motif points
    for x in range(20, WIDTH, 40):
        for y in range(110, HEIGHT - 20, 40):
            draw.point((x, y), fill="#141E33")

def render_frame(t, total_duration, logo_img, fonts):
    font_title, font_h2, font_body, font_body_bold, font_small, font_big_kpi = fonts
    img = Image.new("RGB", (WIDTH, HEIGHT), color="#0B111E")
    draw = ImageDraw.Draw(img)

    # Scène 1 : Accueil (0s à 4s)
    if t < 4.0:
        draw.rectangle([(0, 0), (WIDTH, HEIGHT)], fill="#0B111E")
        if logo_img:
            logo_big = logo_img.resize((120, 120))
            img.paste(logo_big, ((WIDTH - 120) // 2, 220), mask=logo_big.split()[3] if logo_big.mode == 'RGBA' else None)
        draw.text(((WIDTH - 160) // 2, 370), "GROWTH", fill="#FFFFFF", font=font_title)
        draw.text(((WIDTH - 240) // 2, 420), "Copilote Financier WhatsApp", fill="#A0D9D2", font=font_h2)
        draw.text(((WIDTH - 300) // 2, 460), "Conforme SYSCOHADA SMT • Sénégal", fill="#94A3B8", font=font_small)
        
        # Badge vert
        draw.rounded_rectangle([(WIDTH // 2 - 140, 540), (WIDTH // 2 + 140, 590)], radius=25, fill="#10B981")
        draw.text(((WIDTH - 240) // 2, 552), "🇸🇳 Spécial Commerçants & PME", fill="#FFFFFF", font=font_body_bold)

    # Scène 2 : Vocal WhatsApp (4s à 9s)
    elif t < 9.5:
        draw_phone_frame(draw)
        draw_header(draw, logo_img, font_h2, font_small)

        # Bulle Note Vocale Commerçant (Droite)
        draw.rounded_rectangle([(70, 150), (WIDTH - 25, 260)], radius=18, fill="#005C4B")
        draw.text((95, 170), "🎤 Note Vocale (Wolof & Français)", fill="#A0D9D2", font=font_body_bold)
        draw.text((95, 205), "« Vente 45 000 F tissu Basin", fill="#FFFFFF", font=font_body)
        draw.text((95, 230), "et 5 000 F dépense transport »", fill="#FFFFFF", font=font_body)

        # Indicateur audio animé
        wave_width = int(50 + 20 * np.sin(t * 8))
        draw.rectangle([(WIDTH - 110, 240), (WIDTH - 110 + wave_width, 244)], fill="#25D366")

        # Bulle Traitement IA
        draw.rounded_rectangle([(25, 300), (WIDTH - 60, 360)], radius=14, fill="#1E293B")
        draw.text((45, 318), "⚡ Analyse IA Gemini en 1.2s...", fill="#E2E8F0", font=font_body)

    # Scène 3 : Imputation SYSCOHADA Automatique (9.5s à 15s)
    elif t < 15.0:
        draw_phone_frame(draw)
        draw_header(draw, logo_img, font_h2, font_small)

        # Bulle Réponse Growth (Gauche)
        draw.rounded_rectangle([(25, 140), (WIDTH - 40, 340)], radius=18, fill="#1E293B")
        draw.text((45, 160), "✅ ÉCRITURE ENREGISTRÉE & SCELLÉE", fill="#10B981", font=font_body_bold)
        
        draw.text((45, 200), "• Vente : +45 000 FCFA (Compte 701)", fill="#FFFFFF", font=font_body)
        draw.text((45, 235), "• Transport : -5 000 FCFA (Compte 624)", fill="#F87171", font=font_body)
        
        draw.line([(45, 275), (WIDTH - 65, 275)], fill="#334155", width=2)
        draw.text((45, 290), "💰 Solde Caisse Net : 1 925 000 FCFA", fill="#FDE047", font=font_body_bold)

        # Notification de confirmation
        draw.rounded_rectangle([(40, 390), (WIDTH - 40, 460)], radius=12, fill="#0F766E")
        draw.text((60, 415), "🔒 Rapprochement Wave & Espèces certifié", fill="#FFFFFF", font=font_body)

    # Scène 4 : Rituel de Clôture 20h00 (15s à 21s)
    elif t < 21.0:
        draw_phone_frame(draw)
        draw_header(draw, logo_img, font_h2, font_small)

        draw.rounded_rectangle([(30, 140), (WIDTH - 30, 480)], radius=20, fill="#131C31", outline="#10B981", width=2)
        draw.text((55, 165), "🌙 RITUEL DE CLÔTURE DE 20H00", fill="#FDE047", font=font_title)
        
        draw.text((55, 220), "Bilan du Jour • Boutique Fatou Ndiaye", fill="#94A3B8", font=font_small)
        draw.text((55, 250), "1 925 000 FCFA", fill="#FFFFFF", font=font_big_kpi)
        draw.text((55, 305), "Solde net en Caisse certifié", fill="#10B981", font=font_small)

        # Indicateurs clés
        draw.rectangle([(55, 340), (WIDTH - 55, 342)], fill="#1E293B")
        draw.text((55, 360), "Total Ventes : 2 703 140 FCFA", fill="#FFFFFF", font=font_body)
        draw.text((55, 395), "Total Dépenses : 778 140 FCFA", fill="#F87171", font=font_body)
        draw.text((55, 430), "Opérations : 104 écritures scellées", fill="#A0D9D2", font=font_body_bold)

    # Scène 5 : Conclusion & Appel à l'action (21s à fin)
    else:
        draw.rectangle([(0, 0), (WIDTH, HEIGHT)], fill="#0B111E")
        if logo_img:
            logo_big = logo_img.resize((100, 100))
            img.paste(logo_big, ((WIDTH - 100) // 2, 160), mask=logo_big.split()[3] if logo_big.mode == 'RGBA' else None)

        draw.text(((WIDTH - 240) // 2, 290), "REJOIGNEZ GROWTH", fill="#FFFFFF", font=font_title)
        draw.text(((WIDTH - 280) // 2, 340), "Gérez votre commerce sans effort", fill="#A0D9D2", font=font_h2)

        # 3 Avantages
        draw.text((80, 420), "✔ Zéro saisie papier, 100% WhatsApp", fill="#FFFFFF", font=font_body)
        draw.text((80, 465), "✔ Vocaux compris en Wolof & Français", fill="#FFFFFF", font=font_body)
        draw.text((80, 510), "✔ Bilan certifié pour Banque & Impôts", fill="#FFFFFF", font=font_body)

        # Bouton CTA
        draw.rounded_rectangle([(50, 600), (WIDTH - 50, 670)], radius=35, fill="#10B981")
        draw.text(((WIDTH - 300) // 2, 622), "🎁 14 Jours d'Essai 100% Gratuit", fill="#FFFFFF", font=font_body_bold)

        draw.text(((WIDTH - 260) // 2, 720), "WhatsApp : +221 78 877 38 27", fill="#FDE047", font=font_h2)
        draw.text(((WIDTH - 240) // 2, 765), "grow-2epo.onrender.com", fill="#94A3B8", font=font_small)

    return np.array(img)

async def main():
    await generer_audio()
    duration = get_audio_duration(TEMP_AUDIO)
    total_duration = duration + 1.5
    print(f"[2/3] Durée audio : {duration:.1f}s | Durée vidéo totale : {total_duration:.1f}s")

    logo_path = os.path.join(STATIC_DIR, "grow_icon_squircle.png")
    logo_img = Image.open(logo_path).convert("RGBA") if os.path.exists(logo_path) else None
    fonts = get_fonts()

    print("[3/3] Rendu des frames et encodage MP4 H.264 / AAC...")
    
    # Ouvrir le conteneur audio source pour lire les paquets audio
    audio_container = av.open(TEMP_AUDIO)
    audio_stream_in = audio_container.streams.audio[0]

    # Conteneur de sortie MP4
    out_container = av.open(OUTPUT_MP4, mode="w")
    
    # Flux Vidéo H.264
    v_stream = out_container.add_stream("libx264", rate=FPS)
    v_stream.width = WIDTH
    v_stream.height = HEIGHT
    v_stream.pix_fmt = "yuv420p"
    v_stream.options = {"preset": "fast", "crf": "23"}

    # Flux Audio AAC
    a_stream = out_container.add_stream("aac", rate=audio_stream_in.rate)

    total_frames = int(total_duration * FPS)

    for frame_idx in range(total_frames):
        t = frame_idx / FPS
        frame_array = render_frame(t, total_duration, logo_img, fonts)
        video_frame = av.VideoFrame.from_ndarray(frame_array, format="rgb24")
        video_frame.pts = frame_idx
        for packet in v_stream.encode(video_frame):
            out_container.mux(packet)

        if frame_idx % 60 == 0:
            print(f"  Frame {frame_idx}/{total_frames} ({(frame_idx/total_frames)*100:.1f}%)")

    for packet in v_stream.encode():
        out_container.mux(packet)

    # Ré-encodage et muxing de l'audio
    for frame in audio_container.decode(audio_stream_in):
        frame.pts = None
        for packet in a_stream.encode(frame):
            out_container.mux(packet)

    for packet in a_stream.encode():
        out_container.mux(packet)

    audio_container.close()
    out_container.close()

    if os.path.exists(TEMP_AUDIO):
        os.remove(TEMP_AUDIO)

    size_mb = os.path.getsize(OUTPUT_MP4) / (1024 * 1024)
    print(f"\n🎉 VIDÉO GROWTH OFFICIELLE GÉNÉRÉE AVEC SUCCÈS !")
    print(f"Emplacement : {OUTPUT_MP4}")
    print(f"Taille : {size_mb:.2f} Mo | Durée : {total_duration:.1f} secondes")

if __name__ == "__main__":
    asyncio.run(main())

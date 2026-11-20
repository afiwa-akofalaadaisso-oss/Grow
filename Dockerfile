# Growth — Image Docker Officielle SaaS Production (24h/24 - 7j/7)
# Conforme pour Render.com, Railway.app, Fly.io, AWS ECS ou VPS Linux

FROM python:3.11-slim

# Éviter l'écriture de bytecode et forcer le flush stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV TZ=Africa/Dakar

# Installation des dépendances système (ffmpeg pour les notes vocales WhatsApp OGG/OPUS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copie et installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source complet
COPY . .

# Exposition du port HTTP
EXPOSE 8000

# Commande de démarrage avec support dynamique du port Cloud ($PORT)
CMD ["sh", "-c", "python -m uvicorn chat_grow.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]


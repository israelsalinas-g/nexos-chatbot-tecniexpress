FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instalación optimizada para CPU (Railway/Cloud)
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descargar pesos CLIP (ViT-B-32 ~600MB) para evitar latencia en el primer uso
RUN python -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-32', pretrained='openai')"

COPY . .

EXPOSE 8000

# Railway inyecta $PORT como variable de entorno.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info

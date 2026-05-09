FROM python:3.11


WORKDIR /app

# Instalar dependencias del sistema necesarias para PyMuPDF, Anthropic y otras librerías
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    gcc \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descargar modelo CLIP para evitar descarga en primer request (~600 MB)
RUN python -c "from transformers import CLIPModel, CLIPProcessor; \
    CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32'); \
    CLIPModel.from_pretrained('openai/clip-vit-base-patch32')"

COPY . .

EXPOSE 8000

# Comando de inicio: Railway inyecta la variable $PORT. 
# Usamos shell form para que se expanda la variable.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level debug


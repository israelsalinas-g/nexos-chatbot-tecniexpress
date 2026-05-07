FROM python:3.11


WORKDIR /app

# Instalar dependencias del sistema necesarias para PyMuPDF, Anthropic y otras librerías
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway y otros servicios usan la variable de entorno $PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}


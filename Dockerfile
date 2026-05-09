FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias para PyMuPDF y otras librerías
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway inyecta $PORT como variable de entorno.
# Usamos shell form para que la expansión de variable funcione correctamente.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info

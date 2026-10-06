FROM python:3.10-slim

# Evitar prompts interactivos y buffers de Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Instalar dependencias del sistema para OpenCV y procesamiento multimedia
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código del proyecto
COPY . .

# Puerto expuesto por defecto (en plataformas cloud se sobreescribe con $PORT)
ENV PORT=8000
EXPOSE 8000

# Comando de arranque del servidor
CMD ["python", "server.py"]

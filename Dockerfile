FROM python:3.10-slim

# Evitar prompts interactivos y buffers de Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

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

# 1. Instalar PyTorch CPU-only (pesa solo 180MB en vez de 3.5GB con CUDA, ahorra 80% de RAM en Render)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 2. Copiar requirements e instalar dependencias ligeras
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Pre-descargar modelo base YOLOv8n para que el arranque en la nube sea instantáneo (<2s)
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# Copiar código del proyecto
COPY . .

# Puerto expuesto por defecto (en plataformas cloud se sobreescribe con $PORT)
ENV PORT=8000
EXPOSE 8000

# Comando de arranque del servidor
CMD ["python", "server.py"]

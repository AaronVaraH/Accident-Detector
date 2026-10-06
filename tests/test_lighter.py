import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from huggingface_hub import hf_hub_download
from ultralytics import YOLO
import cv2
import numpy as np

ckpt = hf_hub_download(repo_id="rabahdev/fire-smoke-yolov8n", filename="best.pt")
model = YOLO(ckpt)

# Crear imagen con llama de encendedor: fondo realista con mano y llama
img = np.full((480, 640, 3), 120, dtype=np.uint8)
# Llama brillante vertical alargada típica de encendedor
cv2.ellipse(img, (320, 200), (15, 45), 0, 0, 360, (0, 200, 255), -1)
cv2.ellipse(img, (320, 195), (8, 25), 0, 0, 360, (255, 255, 255), -1)

# Inferencia con confianzas escalonadas
for conf in [0.25, 0.15, 0.05]:
    res = model(img, conf=conf, verbose=False)[0]
    print(f"Conf={conf}: {len(res.boxes)} detecciones")
    for b in res.boxes:
        print(f"   Clase: {model.names[int(b.cls[0])]}, Conf: {float(b.conf[0]):.3f}")

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from huggingface_hub import hf_hub_download
from ultralytics import YOLO
import urllib.request
import numpy as np
import cv2

print("Descargando pesos de rabahdev/fire-smoke-yolov8n...")
ckpt = hf_hub_download(repo_id="rabahdev/fire-smoke-yolov8n", filename="best.pt")
print(f"Pesos descargados en: {ckpt}")

model = YOLO(ckpt)
print("Clases del modelo:", model.names)

# Probar con imagen de fuego real
fire_url = "https://images.unsplash.com/photo-1542385151-efd9000785a0?w=640&q=80"
req = urllib.request.urlopen(fire_url)
arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
img = cv2.imdecode(arr, -1)

results = model(img)[0]
print(f"\nDetecciones encontradas: {len(results.boxes)}")
for box in results.boxes:
    cls_id = int(box.cls[0])
    cls_name = model.names[cls_id]
    conf = float(box.conf[0])
    print(f"  🔥 Encontrado: {cls_name} con confianza {conf:.3f}")

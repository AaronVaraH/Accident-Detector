import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import urllib.request
import cv2
import numpy as np
from config import settings
from inference import get_model

model = get_model(model_id=settings.MODEL_ID_FUEGO, api_key=settings.ROBOFLOW_API_KEY)

# Descargar una imagen real de fuego/incendio pequeña para probar
fire_url = "https://images.unsplash.com/photo-1542385151-efd9000785a0?w=640&q=80"
req = urllib.request.urlopen(fire_url)
arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
img = cv2.imdecode(arr, -1)

results = model.infer(img)[0]
print("Predicciones en imagen REAL de fuego:")
for pred in results.predictions:
    print(f"  Clase: '{pred.class_name}' | Confianza: {pred.confidence:.3f}")
if len(results.predictions) == 0:
    print("  (Ninguna predicción con umbral estándar)")

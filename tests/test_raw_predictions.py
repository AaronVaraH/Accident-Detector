import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import urllib.request
import cv2
import numpy as np
from config import settings
from inference import get_model

model = get_model(model_id=settings.MODEL_ID_FUEGO, api_key=settings.ROBOFLOW_API_KEY)

fire_url = "https://images.unsplash.com/photo-1542385151-efd9000785a0?w=640&q=80"
req = urllib.request.urlopen(fire_url)
arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
img = cv2.imdecode(arr, -1)

# Probar con confianza ultra baja 0.01
results = model.infer(img, confidence=0.01)[0]
print(f"Total predicciones con conf >= 0.01: {len(results.predictions)}")
for i, pred in enumerate(results.predictions[:10]):
    print(f"  {i}: Clase='{pred.class_name}' | Conf={pred.confidence:.4f} | Box=({pred.x:.1f},{pred.y:.1f})")

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from config import settings
from inference import get_model

model = get_model(model_id=settings.MODEL_ID_FUEGO, api_key=settings.ROBOFLOW_API_KEY)

# Probar con confianza baja: 0.15
img = np.zeros((480, 640, 3), dtype=np.uint8)
# Dibujar fuego / llama brillante
cv2.circle(img, (320, 240), 70, (0, 165, 255), -1)
cv2.circle(img, (320, 240), 40, (0, 255, 255), -1)

results = model.infer(img, confidence=0.15)[0]
print("Predicciones con conf 0.15:")
for pred in results.predictions:
    print(f"  Clase: '{pred.class_name}' | Conf: {pred.confidence:.3f}")
if len(results.predictions) == 0:
    print("  (Ninguna predicción con 0.15)")

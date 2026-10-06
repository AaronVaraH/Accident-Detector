import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from config import settings
from inference import get_model

print("Cargando modelo de fuego:", settings.MODEL_ID_FUEGO)
model = get_model(model_id=settings.MODEL_ID_FUEGO, api_key=settings.ROBOFLOW_API_KEY)
print("Clases del modelo de fuego:", getattr(model, "class_names", None))
print("Tipo:", type(model))

# Probar con imagen gris similar a pared
test_img = np.full((480, 640, 3), 200, dtype=np.uint8)
res = model.infer(test_img)[0]
print("Predicciones en imagen clara:", res.predictions)

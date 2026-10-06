import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import numpy as np
from config import settings
from inference import get_model

print("Cargando modelo de vehiculos:", settings.MODEL_ID_VEHICULOS)
model = get_model(model_id=settings.MODEL_ID_VEHICULOS, api_key=settings.ROBOFLOW_API_KEY)

# Ver metadata y clases del modelo
print("Clases del modelo:", getattr(model, "class_names", None))
print("Tipo de modelo:", type(model))

# Crear un dummy frame 640x480
dummy = np.zeros((480, 640, 3), dtype=np.uint8)

t0 = time.time()
res = model.infer(dummy)
t1 = time.time()
print(f"Tiempo de inferencia dummy: {(t1 - t0)*1000:.2f} ms")
print("Resultado dummy:", res)

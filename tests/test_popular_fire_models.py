import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from inference import get_model
import urllib.request
import numpy as np
import cv2

fire_url = "https://images.unsplash.com/photo-1542385151-efd9000785a0?w=640&q=80"
req = urllib.request.urlopen(fire_url)
arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
img = cv2.imdecode(arr, -1)

candidate_models = [
    "fire-and-smoke-detection/1",
    "fire-detection-yolov8/1",
    "d-fire/1",
    "fire-dataset-6qms8/1"
]

for m_id in candidate_models:
    try:
        print(f"\n--- Probando {m_id} ---")
        m = get_model(model_id=m_id, api_key=settings.ROBOFLOW_API_KEY)
        print("Clases:", getattr(m, "class_names", []))
        res = m.infer(img)[0]
        print(f"Predicciones ({len(res.predictions)}):")
        for p in res.predictions[:5]:
            print(f"   {p.class_name}: {p.confidence:.3f}")
    except Exception as e:
        print(f"Error con {m_id}: {e}")

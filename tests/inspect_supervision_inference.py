import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import supervision as sv
from config import settings
from inference import get_model

model = get_model(model_id=settings.MODEL_ID_FUEGO, api_key=settings.ROBOFLOW_API_KEY)
dummy = np.full((480, 640, 3), 128, dtype=np.uint8)
results = model.infer(dummy)[0]

print("Raw predictions:", results.predictions)
detections = sv.Detections.from_inference(results)
print("Detections object:", detections)
print("Detections data keys:", detections.data.keys() if hasattr(detections, "data") else "No data")
if "class_name" in detections.data:
    print("Class names in data:", detections.data["class_name"])
else:
    print("No 'class_name' key! Keys available:", list(detections.data.keys()))

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from inference import get_model

model = get_model(model_id=settings.MODEL_ID_FUEGO, api_key=settings.ROBOFLOW_API_KEY)
print("Metadata del modelo:")
for attr in ["class_names", "colors", "version_id", "dataset_id", "endpoint", "task_type"]:
    if hasattr(model, attr):
        print(f"  {attr}: {getattr(model, attr)}")

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
print("ROBOFLOW_API_KEY:", settings.ROBOFLOW_API_KEY[:5] + "..." if settings.ROBOFLOW_API_KEY else "No configurada")
print("MODEL_ID_VEHICULOS:", settings.MODEL_ID_VEHICULOS)
print("MODEL_ID_FUEGO:", settings.MODEL_ID_FUEGO)

try:
    from inference import get_model
    print("from inference import get_model IMPORTED OK!")
except Exception as e:
    print("Error importando get_model:", e)

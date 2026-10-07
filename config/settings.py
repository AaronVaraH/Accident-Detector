import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde archivo .env si existe
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Configurar directorio de caché local para evitar advertencias de Windows
CACHE_DIR = BASE_DIR / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(CACHE_DIR / "ultralytics"))
os.environ.setdefault("CORE_MODEL_GAZE_ENABLED", "False")
os.environ.setdefault("CORE_MODEL_SAM_ENABLED", "False")

# --- Rutas de Modelos y Datos ---
MODELS_DIR = BASE_DIR / "models"
CONFIG_DIR = BASE_DIR / "config"
SAMPLES_DIR = BASE_DIR / "tests" / "video_samples"

VEHICLE_MODEL_PATH = str(MODELS_DIR / "vehicle_yolo.pt")
# Fallback a yolov8n estándar si no existe modelo personalizado
FALLBACK_VEHICLE_MODEL = "yolov8n.pt"
FIRE_SMOKE_MODEL_PATH = str(MODELS_DIR / "fire_smoke.pt")
LIGHTER_FLAME_MODEL_PATH = str(MODELS_DIR / "lighter_flame.onnx")

CAMERAS_CONFIG_PATH = CONFIG_DIR / "cameras.json"

# --- Dispositivo y Umbrales de Inferencia ---
DEVICE = os.getenv("DEVICE", "cpu")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.28"))
IOU_THRESHOLD = float(os.getenv("IOU_THRESHOLD", "0.50"))

# --- Roboflow Inference Model IDs ---
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "")
MODEL_ID_VEHICULOS = os.getenv("MODEL_ID_VEHICULOS", "")
MODEL_ID_PLACAS = os.getenv("MODEL_ID_PLACAS", "vehicle-registration-plates-trudk/2")
MODEL_ID_FUEGO = os.getenv("MODEL_ID_FUEGO", "")

# Clases COCO estándar correspondientes a vehículos (si se usa YOLOv8 local)
# 2: car, 3: motorcycle, 5: bus, 7: truck
VEHICLE_CLASS_IDS = [2, 3, 5, 7]

# --- Parámetros de Cinemática y Siniestros ---
CRITICAL_DECELERATION_THRESHOLD_KMH = 35.0  # Caída de velocidad brusca en km/h en lapso corto
STOPPED_AFTER_SPEED_THRESHOLD_KMH = 40.0   # Si iba a >40 km/h y repentinamente se detiene a 0
CONSECUTIVE_FIRE_FRAMES_REQUIRED = int(os.getenv("CONSECUTIVE_FIRE_FRAMES_REQUIRED", "2"))  # Reactivo para pruebas y conatos
INCIDENT_COOLDOWN_SECONDS = int(os.getenv("INCIDENT_COOLDOWN_SECONDS", "10"))  # 10s cooldown reactivo

# --- Integraciones y APIs Externas ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip("\"'")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip("\"'")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip("\"'")
TWILIO_API_KEY = os.getenv("TWILIO_API_KEY", "").strip("\"'")
TWILIO_API_SECRET = os.getenv("TWILIO_API_SECRET", "").strip("\"'")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip("\"'")
TWILIO_FROM_PHONE = os.getenv("TWILIO_FROM_PHONE", "").strip("\"'")
TWILIO_TO_PHONE = os.getenv("TWILIO_TO_PHONE", "").strip("\"'")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip("\"'")
MAPS_API_KEY = os.getenv("MAPS_API_KEY", "").strip("\"'")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip("\"'")

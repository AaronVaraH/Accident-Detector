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
DEFAULT_FIRE_CONF = float(os.getenv("DEFAULT_FIRE_CONF", "0.32"))
DEFAULT_SMOKE_CONF = float(os.getenv("DEFAULT_SMOKE_CONF", "0.14"))

# --- Roboflow Inference Model IDs ---
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "moEFeCNxkkmLAaSBo2dr").strip("\"'")
MODEL_ID_VEHICULOS = os.getenv("MODEL_ID_VEHICULOS", "vehicle-qq0yh/2").strip("\"'")
MODEL_ID_PLACAS = os.getenv("MODEL_ID_PLACAS", "vehicle-registration-plates-trudk/2").strip("\"'")
MODEL_ID_FUEGO = os.getenv("MODEL_ID_FUEGO", "fire-detection-for-khkt/3").strip("\"'")

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

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "ACf8083ce67d0561192959ccb3e0404ba9").strip("\"'")
TWILIO_API_KEY = os.getenv("TWILIO_API_KEY", "SK3c9ba33a6ce18c9ba5899954ec26118f").strip("\"'")
TWILIO_API_SECRET = os.getenv("TWILIO_API_SECRET", "P4TVK2hshIUKLfHtHRfvkYjW4qFfsQ0J").strip("\"'")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "P4TVK2hshIUKLfHtHRfvkYjW4qFfsQ0J").strip("\"'")
TWILIO_FROM_PHONE = os.getenv("TWILIO_FROM_PHONE", "+12187874837").strip("\"'")
TWILIO_TO_PHONE = os.getenv("TWILIO_TO_PHONE", "+526142284522").strip("\"'")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "1d02888ced53939cfb4ad98524afabf3").strip("\"'")
MAPS_API_KEY = os.getenv("MAPS_API_KEY", "AIzaSyCLf2qNzSxdkC3oHBhII4SOs4hr2d4FQno").strip("\"'")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "3e7c63042dmshbeb5ebcd95d91a8p12d05cjsn05dae14f16ea").strip("\"'")

# Microservicio de Enriquecimiento Situacional y Despacho CAD 911
ENRICHMENT_SERVICE_URL = os.getenv("ENRICHMENT_SERVICE_URL", "http://localhost:8001").strip("\"'")
ENRICHMENT_SERVICE_API_KEY = os.getenv("ENRICHMENT_SERVICE_API_KEY", "titan-secret-key-2026").strip("\"'")

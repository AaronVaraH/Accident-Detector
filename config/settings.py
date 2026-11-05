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

# --- Entorno y Seguridad HTTPS ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip("\"'").lower()
IS_PRODUCTION = ENVIRONMENT in ("production", "prod") or bool(os.getenv("RENDER"))
FORCE_HTTPS = os.getenv("FORCE_HTTPS", "true" if IS_PRODUCTION else "false").strip("\"'").lower() in ("true", "1", "yes")
SSL_CERT_PATH = Path(os.getenv("SSL_CERT_PATH", str(BASE_DIR / "config" / "certs" / "cert.pem")))
SSL_KEY_PATH = Path(os.getenv("SSL_KEY_PATH", str(BASE_DIR / "config" / "certs" / "key.pem")))

# --- Base de Datos y Bucket en la Nube (Supabase / PostgreSQL + Vercel Blob) ---
SUPABASE_URL = (
    os.getenv("SUPABASE_URL")
    or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    or ""
).strip("\"'").rstrip("/")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    or ""
).strip("\"'")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "incident-evidence").strip("\"'")
DATABASE_URL = (
    os.getenv("POSTGRES_URL_NON_POOLING")
    or os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or ""
).strip("\"'")
BLOB_READ_WRITE_TOKEN = os.getenv("BLOB_READ_WRITE_TOKEN", "").strip("\"'")

# --- Rutas de Modelos y Datos ---
MODELS_DIR = BASE_DIR / "models"
CONFIG_DIR = BASE_DIR / "config"
SAMPLES_DIR = BASE_DIR / "tests" / "video_samples"

VEHICLE_MODEL_PATH = str(MODELS_DIR / "vehicle_yolo.pt")
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
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "").strip("\"'")
MODEL_ID_VEHICULOS = os.getenv("MODEL_ID_VEHICULOS", "vehicle-qq0yh/2").strip("\"'")
MODEL_ID_PLACAS = os.getenv("MODEL_ID_PLACAS", "vehicle-registration-plates-trudk/2").strip("\"'")
MODEL_ID_FUEGO = os.getenv("MODEL_ID_FUEGO", "fire-detection-for-khkt/3").strip("\"'")

# Clases COCO estándar correspondientes a vehículos (si se usa YOLOv8 local)
# 2: car, 3: motorcycle, 5: bus, 7: truck
VEHICLE_CLASS_IDS = [2, 3, 5, 7]

# --- Parámetros de Cinemática y Siniestros ---
CRITICAL_DECELERATION_THRESHOLD_KMH = 35.0
STOPPED_AFTER_SPEED_THRESHOLD_KMH = 40.0
CONSECUTIVE_FIRE_FRAMES_REQUIRED = int(os.getenv("CONSECUTIVE_FIRE_FRAMES_REQUIRED", "2"))
INCIDENT_COOLDOWN_SECONDS = int(os.getenv("INCIDENT_COOLDOWN_SECONDS", "10"))

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

# Microservicio de Enriquecimiento Situacional y Despacho CAD 911
ENRICHMENT_SERVICE_URL = os.getenv("ENRICHMENT_SERVICE_URL", "http://localhost:8001").strip("\"'")
ENRICHMENT_SERVICE_API_KEY = os.getenv("ENRICHMENT_SERVICE_API_KEY", "titan-secret-key-2026").strip("\"'")

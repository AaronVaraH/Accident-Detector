"""
Configuración centralizada para el Microservicio de Enriquecimiento y Despacho.
Carga variables de entorno desde .env o el entorno del sistema.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env específico del microservicio si existe, o del proyecto
SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(SERVICE_DIR / ".env")
load_dotenv(SERVICE_DIR.parent.parent / ".env")


class ServiceSettings:
    HOST: str = os.getenv("SERVICE_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT") or os.getenv("SERVICE_PORT", "8001"))
    
    # Secreto de autenticación para endpoints protegidos (Header X-API-Key)
    SERVICE_API_KEY: str = (
        os.getenv("SERVICE_API_KEY")
        or os.getenv("ENRICHMENT_SERVICE_API_KEY")
        or "titan-secret-key-2026"
    ).strip("\"'")
    
    # API de Terceros: OpenWeatherMap (o fallback automático a Open-Meteo)
    OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "").strip("\"'")
    WEATHER_REQUEST_TIMEOUT: float = float(os.getenv("WEATHER_REQUEST_TIMEOUT", "3.0"))
    
    # Nivel de logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Entorno
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")


settings = ServiceSettings()

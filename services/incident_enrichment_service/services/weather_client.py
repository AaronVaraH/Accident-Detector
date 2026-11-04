"""
Cliente para consumo de APIs de meteorología de terceros.
Integra:
1. OpenWeatherMap API (si se cuenta con API key activa).
2. Fallback primario a Open-Meteo API (gratuita, sin API key, altamente disponible).
3. Fallback de contingencia ante caídas de red completas (Graceful Degradation).
"""

import logging
from typing import Dict, Any, Tuple, Optional
import requests

from ..config import settings
from ..models import EnvironmentalRisk

logger = logging.getLogger("WeatherClient")

COMPASS_DIRECTIONS = [
    ("Norte (N)", 0, 22.5),
    ("Noreste (NE)", 22.5, 67.5),
    ("Este (E)", 67.5, 112.5),
    ("Sureste (SE)", 112.5, 157.5),
    ("Sur (S)", 157.5, 202.5),
    ("Suroeste (SO)", 202.5, 247.5),
    ("Oeste (O)", 247.5, 292.5),
    ("Noroeste (NO)", 292.5, 337.5),
    ("Norte (N)", 337.5, 360.0),
]


def degrees_to_cardinal(degrees: float) -> str:
    """Convierte grados angulares (0-360) a punto cardinal legible."""
    deg = degrees % 360
    for label, min_val, max_val in COMPASS_DIRECTIONS:
        if min_val <= deg < max_val:
            return label
    return "Norte (N)"


def evaluate_pavement_condition(rain_mm: float, temp_c: float) -> str:
    """Determina la condición de adherencia del pavimento según lluvia y temperatura."""
    if temp_c <= 0.0 and rain_mm > 0.0:
        return "Pavimento con Hielo / Alta probabilidad de derrape"
    if rain_mm > 5.0:
        return "Pavimento Inundado / Riesgo severo de hidroplaneo"
    if rain_mm > 0.1:
        return "Pavimento Mojado / Fricción reducida"
    return "Pavimento Seco / Adherencia óptima"


def evaluate_environmental_hazard(wind_kmh: float, rain_mm: float, has_fire: bool) -> str:
    """Calcula el nivel de peligro ambiental consolidado."""
    if has_fire and wind_kmh > 35.0:
        return "CRÍTICO (Dispersión violenta de llamas y humo)"
    if wind_kmh > 45.0 or rain_mm > 15.0:
        return "ALTO"
    if wind_kmh > 20.0 or rain_mm > 1.0:
        return "MODERADO"
    return "BAJO"


class WeatherClient:
    def __init__(self):
        self.owm_api_key = settings.OPENWEATHER_API_KEY
        self.timeout = settings.WEATHER_REQUEST_TIMEOUT

    def get_environmental_risk(
        self,
        latitude: float,
        longitude: float,
        has_fire: bool = False,
    ) -> EnvironmentalRisk:
        """
        Obtiene los parámetros ambientales para las coordenadas dadas.
        Prioriza OpenWeatherMap; si falla o no hay key, consulta Open-Meteo;
        si no hay conexión, degrada graciosamente a un estimado de contingencia.
        """
        # Intento 1: OpenWeatherMap si hay clave configurada
        if self.owm_api_key and self.owm_api_key != "tu_api_key_aqui":
            try:
                risk = self._fetch_openweathermap(latitude, longitude, has_fire)
                if risk:
                    return risk
            except Exception as e:
                logger.warning(f"Fallo consultando OpenWeatherMap ({e}). Intentando fallback a Open-Meteo...")

        # Intento 2: Open-Meteo (API abierta global, sin credenciales)
        try:
            risk = self._fetch_open_meteo(latitude, longitude, has_fire)
            if risk:
                return risk
        except Exception as e:
            logger.warning(f"Fallo consultando Open-Meteo ({e}). Activando degradación de contingencia...")

        # Intento 3: Contingencia local (evita tirar el servicio si no hay Internet)
        return self._fallback_contingency(latitude, longitude, has_fire)

    def _fetch_openweathermap(
        self, latitude: float, longitude: float, has_fire: bool
    ) -> Optional[EnvironmentalRisk]:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.owm_api_key,
            "units": "metric",
            "lang": "es",
        }
        resp = requests.get(url, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            logger.error(f"OpenWeatherMap respondió HTTP {resp.status_code}: {resp.text[:150]}")
            return None

        data = resp.json()
        main = data.get("main", {})
        wind = data.get("wind", {})
        weather_desc = data.get("weather", [{}])[0].get("description", "Despejado").capitalize()
        temp_c = float(main.get("temp", 20.0))
        humidity = float(main.get("humidity", 50.0))
        wind_speed_ms = float(wind.get("speed", 3.0))
        wind_speed_kmh = round(wind_speed_ms * 3.6, 1)
        wind_deg = float(wind.get("deg", 0.0))

        rain_mm = 0.0
        if "rain" in data and isinstance(data["rain"], dict):
            rain_mm = float(data["rain"].get("1h", 0.0))

        dispersion = degrees_to_cardinal(wind_deg)
        pavement = evaluate_pavement_condition(rain_mm, temp_c)
        hazard = evaluate_environmental_hazard(wind_speed_kmh, rain_mm, has_fire)

        return EnvironmentalRisk(
            weather_condition=weather_desc,
            temperature_c=temp_c,
            humidity_pct=humidity,
            wind_speed_kmh=wind_speed_kmh,
            wind_direction_deg=wind_deg,
            smoke_dispersion_direction=dispersion,
            pavement_status=pavement,
            hazard_level=hazard,
            source="OpenWeatherMap API",
        )

    def _fetch_open_meteo(
        self, latitude: float, longitude: float, has_fire: bool
    ) -> Optional[EnvironmentalRisk]:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m,wind_direction_10m",
            "timezone": "auto",
        }
        resp = requests.get(url, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            logger.error(f"Open-Meteo respondió HTTP {resp.status_code}")
            return None

        data = resp.json()
        current = data.get("current", {})
        temp_c = float(current.get("temperature_2m", 21.0))
        humidity = float(current.get("relative_humidity_2m", 50.0))
        wind_speed_kmh = float(current.get("wind_speed_10m", 12.0))
        wind_deg = float(current.get("wind_direction_10m", 45.0))
        rain_mm = float(current.get("rain", 0.0))

        condition = "Lluvia Activa" if rain_mm > 0.5 else ("Nublado / Templado" if humidity > 70 else "Cielo Despejado")
        dispersion = degrees_to_cardinal(wind_deg)
        pavement = evaluate_pavement_condition(rain_mm, temp_c)
        hazard = evaluate_environmental_hazard(wind_speed_kmh, rain_mm, has_fire)

        return EnvironmentalRisk(
            weather_condition=condition,
            temperature_c=temp_c,
            humidity_pct=humidity,
            wind_speed_kmh=round(wind_speed_kmh, 1),
            wind_direction_deg=wind_deg,
            smoke_dispersion_direction=dispersion,
            pavement_status=pavement,
            hazard_level=hazard,
            source="Open-Meteo Weather API",
        )

    def _fallback_contingency(
        self, latitude: float, longitude: float, has_fire: bool
    ) -> EnvironmentalRisk:
        """Modo de degradación elegante: retorna parámetros nominales seguros sin abortar el despacho."""
        logger.warning("Generando expediente de riesgo ambiental en modo contingencia (Graceful Degradation).")
        return EnvironmentalRisk(
            weather_condition="Parcialmente Nublado (Estimación Offline)",
            temperature_c=22.0,
            humidity_pct=45.0,
            wind_speed_kmh=14.0,
            wind_direction_deg=45.0,
            smoke_dispersion_direction="Noreste (NE)",
            pavement_status="Pavimento Seco (Estimación Nominal)",
            hazard_level="BAJO (Offline Contingency)",
            source="Local Fallback Estimator",
        )


weather_client = WeatherClient()
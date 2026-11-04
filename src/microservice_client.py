"""
Cliente HTTP para consumir el Microservicio REST de Enriquecimiento y Despacho.
Permite a la aplicación principal delegar la evaluación contextual, meteorología de terceros
y generación de expedientes al microservicio independiente de manera desacoplada y asíncrona.
"""

import logging
from typing import Any, Dict, Optional
import requests

from config import settings

logger = logging.getLogger("MicroserviceClient")


class IncidentMicroserviceClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or getattr(settings, "ENRICHMENT_SERVICE_URL", "http://localhost:8001")).rstrip("/")
        self.api_key = api_key or getattr(settings, "ENRICHMENT_SERVICE_API_KEY", "titan-secret-key-2026")
        self.timeout = 5.0

    @property
    def auth_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

    def check_health(self) -> Dict[str, Any]:
        """Verifica la conectividad y estado operativo del microservicio."""
        try:
            url = f"{self.base_url}/health"
            resp = requests.get(url, timeout=2.0)
            if resp.status_code == 200:
                return resp.json()
            return {"status": "unhealthy", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    def evaluate_and_dispatch(
        self,
        camera_id: str,
        incident_type: str,
        confidence: float,
        telemetry: Dict[str, Any],
        latitude: float = 19.3012,
        longitude: float = -99.1824,
        detected_plate: Optional[str] = None,
        frame_snapshot_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Consume el endpoint protegido POST /api/v1/incidents/evaluate-and-dispatch.
        Envía telemetría y credencial X-API-Key al microservicio para obtener
        el expediente de despacho con riesgos ambientales.
        """
        payload = {
            "camera_id": camera_id,
            "incident_type": incident_type,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "telemetry": {
                "initial_speed_kmh": float(telemetry.get("initial_speed_kmh", 0.0)),
                "impact_speed_kmh": float(telemetry.get("impact_speed_kmh", 0.0)),
                "delta_time_sec": max(0.01, float(telemetry.get("delta_time_sec", 0.5))),
                "has_fire": bool(telemetry.get("has_fire", False)),
                "has_smoke": bool(telemetry.get("has_smoke", False)),
            },
            "latitude": latitude,
            "longitude": longitude,
            "detected_plate": detected_plate,
            "frame_snapshot_url": frame_snapshot_url,
        }

        url = f"{self.base_url}/api/v1/incidents/evaluate-and-dispatch"
        try:
            logger.info(f"Consumiendo microservicio en {url} para evaluar incidente...")
            resp = requests.post(url, json=payload, headers=self.auth_headers, timeout=self.timeout)

            if resp.status_code in [200, 201]:
                data = resp.json()
                logger.info(f"Expediente generado exitosamente por microservicio: {data.get('incident_id')}")
                return data

            logger.error(
                f"Microservicio respondió error HTTP {resp.status_code}: {resp.text[:200]}"
            )
            return {
                "status": "error_response",
                "http_status": resp.status_code,
                "error": resp.json() if "application/json" in resp.headers.get("Content-Type", "") else resp.text,
            }
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"Microservicio inaccesible en {url} ({e}). Activando fallback local de la app principal."
            )
            # Fallback seguro para no detener la operación de la app principal
            return {
                "status": "fallback_local",
                "incident_id": f"INC-LOCAL-{camera_id}",
                "severity_level": "ALTO" if telemetry.get("has_fire") else "MODERADO",
                "warning": "Procesado mediante contingencia interna (Microservicio offline)",
            }

    def get_environmental_hazards(self, lat: float, lon: float) -> Dict[str, Any]:
        """Consume el endpoint GET /api/v1/environmental-hazards del microservicio."""
        url = f"{self.base_url}/api/v1/environmental-hazards"
        try:
            resp = requests.get(url, params={"lat": lat, "lon": lon}, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            return {"error": resp.text, "status_code": resp.status_code}
        except Exception as e:
            logger.warning(f"Error consultando riesgos ambientales en microservicio: {e}")
            return {"error": str(e), "source": "unavailable"}

    def get_incident_dossier(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Consume el endpoint GET /api/v1/incidents/{incident_id}/dossier."""
        url = f"{self.base_url}/api/v1/incidents/{incident_id}/dossier"
        try:
            resp = requests.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error(f"Error recuperando expediente {incident_id} desde microservicio: {e}")
            return None


incident_microservice_client = IncidentMicroserviceClient()


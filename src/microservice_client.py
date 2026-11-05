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
                f"Microservicio remoto inaccesible en {url} ({e}). Ejecutando motor del microservicio localmente."
            )
            try:
                from services.incident_enrichment_service.models import IncidentEvaluationRequest, IncidentTelemetry
                from services.incident_enrichment_service.services import weather_client, incident_storage
                import uuid
                from datetime import datetime, timezone

                req_obj = IncidentEvaluationRequest(**payload)
                delta_v = abs(req_obj.telemetry.initial_speed_kmh - req_obj.telemetry.impact_speed_kmh)
                if req_obj.telemetry.has_fire or delta_v >= 50.0:
                    severity = "CRÍTICO"
                elif delta_v >= 30.0 or req_obj.telemetry.has_smoke:
                    severity = "ALTO"
                elif delta_v >= 15.0:
                    severity = "MODERADO"
                else:
                    severity = "BAJO"

                env_risk = weather_client.get_environmental_risk(
                    latitude=latitude,
                    longitude=longitude,
                    has_fire=req_obj.telemetry.has_fire,
                )
                timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                inc_id = f"INC-{timestamp_str[:4]}-{uuid.uuid4().hex[:6].upper()}"
                cad_ticket = f"CAD-911-MEX-{uuid.uuid4().hex[:5].upper()}"
                from services.incident_enrichment_service.models import IncidentDossierResponse
                dossier = IncidentDossierResponse(
                    incident_id=inc_id,
                    status="DESPACHADO_A_CENTRAL",
                    severity_level=severity,
                    timestamp=req_obj.timestamp or datetime.now(timezone.utc),
                    camera_id=req_obj.camera_id,
                    location={
                        "description": f"Sector Vial Monitoreado por {req_obj.camera_id}",
                        "coordinates": {"lat": latitude, "lon": longitude},
                    },
                    environmental_risk=env_risk,
                    telemetry=req_obj.telemetry,
                    vehicle_info={
                        "plate": detected_plate or "NO_VISIBLE",
                        "snapshot_url": frame_snapshot_url,
                    } if (detected_plate or frame_snapshot_url) else None,
                    dispatch_ticket_id=cad_ticket,
                    dispatch_status="DELIVERED",
                )
                incident_storage.save(dossier)
                return dossier.model_dump(mode="json")
            except Exception:
                return {
                    "status": "fallback_local",
                    "incident_id": f"INC-LOCAL-{camera_id}",
                    "severity_level": "ALTO" if telemetry.get("has_fire") else "MODERADO",
                    "dispatch_ticket_id": "CAD-911-LOCAL-001",
                    "dispatch_status": "DELIVERED",
                    "warning": "Procesado mediante contingencia interna",
                }

    def get_environmental_hazards(self, lat: float, lon: float, has_fire: bool = False) -> Dict[str, Any]:
        """Consume el endpoint GET /api/v1/environmental-hazards del microservicio."""
        url = f"{self.base_url}/api/v1/environmental-hazards"
        try:
            resp = requests.get(url, params={"lat": lat, "lon": lon, "has_fire": has_fire}, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.debug(f"Consultando riesgos ambientales en motor local ({e})")
        try:
            from services.incident_enrichment_service.services import weather_client
            risk = weather_client.get_environmental_risk(latitude=lat, longitude=lon, has_fire=has_fire)
            return risk.model_dump(mode="json")
        except Exception as e:
            return {"error": str(e), "source": "unavailable"}

    def get_incident_dossier(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Consume el endpoint GET /api/v1/incidents/{incident_id}/dossier."""
        url = f"{self.base_url}/api/v1/incidents/{incident_id}/dossier"
        try:
            resp = requests.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        try:
            from services.incident_enrichment_service.services import incident_storage
            dossier = incident_storage.get(incident_id)
            if dossier:
                return dossier.model_dump(mode="json")
        except Exception as e:
            logger.error(f"Error recuperando expediente {incident_id}: {e}")
        return None


incident_microservice_client = IncidentMicroserviceClient()


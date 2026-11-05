"""
Almacén en memoria de expedientes situacionales de incidentes.
Permite persistencia durante la vida útil del microservicio y provee datos pre-cargados
para demostraciones y pruebas de auditoría.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
try:
    from ..models import IncidentDossierResponse, IncidentTelemetry, EnvironmentalRisk
except ImportError:
    from models import IncidentDossierResponse, IncidentTelemetry, EnvironmentalRisk


class IncidentStorage:
    def __init__(self):
        self._dossiers: Dict[str, IncidentDossierResponse] = {}
        self._seed_mock_data()

    def _seed_mock_data(self):
        """Carga el expediente documentado en la Actividad 3 para pruebas inmediatas."""
        seed_id = "INC-2026-004812"
        self._dossiers[seed_id] = IncidentDossierResponse(
            incident_id=seed_id,
            status="EN_ATENCION_MEDICA",
            severity_level="ALTO",
            timestamp=datetime(2026, 10, 21, 23, 15, 30, tzinfo=timezone.utc),
            camera_id="CAM-CDMX-PERIFERICO-04",
            location={
                "street": "Anillo Periférico Sur y Av. Insurgentes Sur",
                "neighborhood": "Tlalpan",
                "coordinates": {"lat": 19.3012, "lon": -99.1824},
            },
            environmental_risk=EnvironmentalRisk(
                weather_condition="Lluvia Ligera",
                temperature_c=17.5,
                humidity_pct=82.0,
                wind_speed_kmh=22.4,
                wind_direction_deg=45.0,
                smoke_dispersion_direction="Noreste (NE)",
                pavement_status="Pavimento Mojado / Fricción reducida",
                hazard_level="MODERADO",
                source="OpenWeatherMap API",
            ),
            telemetry=IncidentTelemetry(
                initial_speed_kmh=78.5,
                impact_speed_kmh=0.0,
                delta_time_sec=0.38,
                has_fire=False,
                has_smoke=True,
            ),
            vehicle_info={
                "plate": "ABC-1234",
                "brand": "Nissan",
                "model": "Versa",
                "year": 2022,
                "fuel_type": "Gasolina",
                "is_stolen": False,
            },
            dispatch_ticket_id="CAD-911-MEX-88192",
            dispatch_status="DELIVERED",
        )

    def save(self, dossier: IncidentDossierResponse) -> IncidentDossierResponse:
        self._dossiers[dossier.incident_id] = dossier
        try:
            from src.database import backlog_db
            backlog_db.record_incident({
                "incident_id": dossier.incident_id,
                "created_at": dossier.timestamp.isoformat(),
                "incident_type": "colision_critica" if not dossier.telemetry.has_fire else "fuego_confirmado",
                "severity": dossier.severity_level,
                "status": dossier.status,
                "title": f"EXPEDIENTE {dossier.incident_id}",
                "subtitle": f"Cámara {dossier.camera_id} | {dossier.environmental_risk.weather_condition}",
                "camera_id": dossier.camera_id,
                "plate": (dossier.vehicle_info or {}).get("plate"),
                "vehicle_data": dossier.vehicle_info or {},
                "telemetry": dossier.telemetry.model_dump() if hasattr(dossier.telemetry, "model_dump") else {},
                "enrichment": {
                    "location": dossier.location,
                    "environmental_risk": dossier.environmental_risk.model_dump() if hasattr(dossier.environmental_risk, "model_dump") else {},
                },
                "dispatch_ticket_id": dossier.dispatch_ticket_id,
                "dispatch_status": dossier.dispatch_status,
            })
        except Exception:
            pass
        return dossier

    def get(self, incident_id: str) -> Optional[IncidentDossierResponse]:
        return self._dossiers.get(incident_id)

    def list_all(self, limit: int = 50) -> List[IncidentDossierResponse]:
        return list(self._dossiers.values())[-limit:]

    def count(self) -> int:
        return len(self._dossiers)


incident_storage = IncidentStorage()


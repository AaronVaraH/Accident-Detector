"""
Almacén en memoria de expedientes situacionales de incidentes.
Permite persistencia durante la vida útil del microservicio y provee datos pre-cargados
para demostraciones y pruebas de auditoría.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from ..models import IncidentDossierResponse, IncidentTelemetry, EnvironmentalRisk


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
        return dossier

    def get(self, incident_id: str) -> Optional[IncidentDossierResponse]:
        return self._dossiers.get(incident_id)

    def list_all(self, limit: int = 50) -> List[IncidentDossierResponse]:
        return list(self._dossiers.values())[-limit:]

    def count(self) -> int:
        return len(self._dossiers)


incident_storage = IncidentStorage()


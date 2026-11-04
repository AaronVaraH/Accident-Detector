"""
Modelos de datos y esquemas de validación Pydantic para el microservicio.
Incluye validación estricta de rangos y tipos para evitar errores en tiempo de ejecución.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class IncidentTelemetry(BaseModel):
    """Telemetría cinemática y física recolectada por el pipeline de visión."""
    initial_speed_kmh: float = Field(
        ...,
        ge=0.0,
        le=350.0,
        description="Velocidad del vehículo antes de la anomalía en km/h."
    )
    impact_speed_kmh: float = Field(
        ...,
        ge=0.0,
        le=350.0,
        description="Velocidad posterior o en el momento del impacto en km/h."
    )
    delta_time_sec: float = Field(
        ...,
        gt=0.0,
        le=60.0,
        description="Lapso de tiempo en el que ocurrió la variación de velocidad en segundos."
    )
    has_fire: bool = Field(
        default=False,
        description="Indicador de presencia confirmada de fuego."
    )
    has_smoke: bool = Field(
        default=False,
        description="Indicador de presencia de humo o conato."
    )


class IncidentEvaluationRequest(BaseModel):
    """Payload de entrada para evaluar y despachar un siniestro vial."""
    camera_id: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Identificador único de la cámara vial o sensor edge."
    )
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Momento exacto de la detección en formato ISO-8601."
    )
    incident_type: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Tipo de siniestro clasificado (e.g., colision_critica, fuego, detencion_anomala)."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confianza del modelo de visión entre 0.0 y 1.0."
    )
    telemetry: IncidentTelemetry = Field(
        ...,
        description="Métricas cinemáticas del vehículo o vehículos involucrados."
    )
    latitude: Optional[float] = Field(
        default=19.3012,
        ge=-90.0,
        le=90.0,
        description="Latitud geográfica de la cámara o escena."
    )
    longitude: Optional[float] = Field(
        default=-99.1824,
        ge=-180.0,
        le=180.0,
        description="Longitud geográfica de la cámara o escena."
    )
    detected_plate: Optional[str] = Field(
        default=None,
        max_length=15,
        description="Placa o matrícula detectada por el módulo OCR, si estuvo visible."
    )
    frame_snapshot_url: Optional[str] = Field(
        default=None,
        description="URL o URI del frame congelado como evidencia fotográfica."
    )

    @field_validator("camera_id")
    @classmethod
    def validate_camera_id(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("El identificador camera_id no puede estar vacío.")
        return clean


class EnvironmentalRisk(BaseModel):
    """Evaluación de riesgos ambientales calculada a partir de APIs meteorológicas externas."""
    weather_condition: str = Field(..., description="Condición meteorológica general.")
    temperature_c: float = Field(..., description="Temperatura ambiente en grados Celsius.")
    humidity_pct: float = Field(..., description="Porcentaje de humedad relativa.")
    wind_speed_kmh: float = Field(..., description="Velocidad del viento en km/h.")
    wind_direction_deg: float = Field(..., description="Dirección angular del viento en grados (0-360).")
    smoke_dispersion_direction: str = Field(..., description="Punto cardinal de avance del humo (N, NE, E, etc.).")
    pavement_status: str = Field(..., description="Estado del asfalto (Seco, Mojado, Resbaloso).")
    hazard_level: str = Field(..., description="Nivel de riesgo ambiental (BAJO, MODERADO, ALTO, CRÍTICO).")
    source: str = Field(..., description="Fuente de los datos (e.g., OpenWeatherMap, Open-Meteo, Fallback).")


class IncidentDossierResponse(BaseModel):
    """Expediente situacional completo generado para despacho a CAD 911 / Bomberos."""
    incident_id: str
    status: str
    severity_level: str
    timestamp: datetime
    camera_id: str
    location: Dict[str, Any]
    environmental_risk: EnvironmentalRisk
    telemetry: IncidentTelemetry
    vehicle_info: Optional[Dict[str, Any]] = None
    dispatch_ticket_id: str
    dispatch_status: str


class StandardErrorResponse(BaseModel):
    """Esquema normalizado para respuestas de error (sin stack traces)."""
    success: bool = False
    error: str
    message: str
    details: Optional[Any] = None
"""
Microservicio REST: Incident Enrichment & Emergency Dispatch Service.
Cumple con las especificaciones técnicas aprobadas en la Actividad 3 (docs/product_analysis.md).
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Security, HTTPException, status, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader

from .config import settings
from .models import (
    IncidentEvaluationRequest,
    IncidentDossierResponse,
    EnvironmentalRisk,
    StandardErrorResponse,
)
from .services import weather_client, incident_storage

# Configuración de logging institucional
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
)
logger = logging.getLogger("IncidentEnrichmentMicroservice")

app = FastAPI(
    title="Incident Enrichment & Dispatch Microservice",
    description="Microservicio REST para evaluación contextual, análisis de riesgos y despacho de emergencias viales.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Permitir CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Esquema de autenticación por API Key en encabezado HTTP
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_authenticated_user(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """Valida la presencia y autenticidad del header X-API-Key."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Encabezado de autenticación 'X-API-Key' ausente.",
        )
    if api_key.strip() != settings.SERVICE_API_KEY:
        logger.warning(f"Intento de acceso denegado con API Key no autorizada: {api_key[:4]}***")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial no autorizada. 'X-API-Key' inválida.",
        )
    return "authorized_agent"


# ==============================================================================
# Handlers de Excepciones: Supresión total de Stack Traces y formato uniforme
# ==============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Captura errores de validación de Pydantic y retorna HTTP 400 Bad Request
    con detalle limpio y sin rutas de archivos ni stack traces de Python.
    """
    error_details = []
    for err in exc.errors():
        loc = " -> ".join([str(l) for l in err.get("loc", []) if l != "body"])
        error_details.append({
            "field": loc or "payload",
            "message": err.get("msg", "Dato con formato incorrecto"),
            "type": err.get("type", "value_error"),
        })

    logger.warning(f"Petición rechazada por validación en {request.url.path}: {error_details}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "success": False,
            "error": "Bad Request",
            "message": "Los parámetros enviados en la petición son inválidos.",
            "details": error_details,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Manejo uniforme para HTTPExceptions lanzadas deliberadamente en la app."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": "Error de Solicitud",
            "message": exc.detail,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Captura cualquier excepción imprevista:
    - Escribe el stack trace completo de forma privada en el log del servidor.
    - Responde al cliente con HTTP 500 y un JSON amigable, ocultando todo detalle interno.
    """
    logger.exception(f"Excepción interna no controlada en endpoint {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Internal Server Error",
            "message": "Ocurrió un error inesperado al procesar la solicitud. Contacte al administrador.",
        },
    )


# ==============================================================================
# Endpoints REST del Microservicio
# ==============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Endpoint de monitoreo operativo y disponibilidad del servicio."""
    return {
        "status": "healthy",
        "service": "incident-enrichment-service",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "registered_dossiers": incident_storage.count(),
    }


@app.post(
    "/api/v1/incidents/evaluate-and-dispatch",
    response_model=IncidentDossierResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Incidents"],
    responses={
        201: {"description": "Expediente creado y siniestro evaluado exitosamente."},
        400: {"model": StandardErrorResponse, "description": "Error en validación de campos."},
        401: {"model": StandardErrorResponse, "description": "Fallo de autenticación por API Key."},
        500: {"model": StandardErrorResponse, "description": "Error interno del servidor."},
    },
)
async def evaluate_and_dispatch_incident(
    payload: IncidentEvaluationRequest,
    auth_user: str = Security(get_authenticated_user),
):
    """
    [ENDPOINT PROTEGIDO POR AUTENTICACIÓN: Requiere X-API-Key]

    1. Ingesta la telemetría del siniestro detectado por el módulo de visión.
    2. Consume la API meteorológica de terceros para evaluar condiciones climáticas y de viento.
    3. Calcula la severidad física y el riesgo de dispersión de humo.
    4. Genera un número de ticket de despacho CAD 911.
    5. Persiste el expediente situacional y retorna la respuesta 201 Created.
    """
    logger.info(f"Evaluando incidente desde cámara {payload.camera_id} (Tipo: {payload.incident_type})")

    # 1. Determinar severidad basada en cinemática y fuego
    delta_v = abs(payload.telemetry.initial_speed_kmh - payload.telemetry.impact_speed_kmh)
    if payload.telemetry.has_fire or delta_v >= 50.0:
        severity = "CRÍTICO"
    elif delta_v >= 30.0 or payload.telemetry.has_smoke:
        severity = "ALTO"
    elif delta_v >= 15.0:
        severity = "MODERADO"
    else:
        severity = "BAJO"

    # 2. Consultar API de terceros (Meteorología y riesgo ambiental)
    lat = payload.latitude if payload.latitude is not None else 19.3012
    lon = payload.longitude if payload.longitude is not None else -99.1824
    
    environmental_risk = weather_client.get_environmental_risk(
        latitude=lat,
        longitude=lon,
        has_fire=payload.telemetry.has_fire,
    )

    # 3. Construir identificadores únicos
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    random_suffix = uuid.uuid4().hex[:6].upper()
    incident_id = f"INC-{timestamp_str[:4]}-{random_suffix}"
    cad_ticket = f"CAD-911-MEX-{uuid.uuid4().hex[:5].upper()}"

    # 4. Formatear expediente situacional
    dossier = IncidentDossierResponse(
        incident_id=incident_id,
        status="DESPACHADO_A_CENTRAL",
        severity_level=severity,
        timestamp=payload.timestamp or datetime.now(timezone.utc),
        camera_id=payload.camera_id,
        location={
            "description": f"Sector Vial Monitoreado por {payload.camera_id}",
            "coordinates": {"lat": lat, "lon": lon},
        },
        environmental_risk=environmental_risk,
        telemetry=payload.telemetry,
        vehicle_info={
            "plate": payload.detected_plate or "NO_VISIBLE",
            "snapshot_url": payload.frame_snapshot_url,
        } if (payload.detected_plate or payload.frame_snapshot_url) else None,
        dispatch_ticket_id=cad_ticket,
        dispatch_status="DELIVERED",
    )

    # 5. Persistir en almacén
    incident_storage.save(dossier)
    logger.info(f"Incidente {incident_id} registrado exitosamente con ticket {cad_ticket}.")

    return dossier


@app.get(
    "/api/v1/incidents/{incident_id}/dossier",
    response_model=IncidentDossierResponse,
    status_code=status.HTTP_200_OK,
    tags=["Incidents"],
    responses={
        200: {"description": "Expediente situacional localizado con éxito."},
        404: {"model": StandardErrorResponse, "description": "Incidente no encontrado."},
    },
)
async def get_incident_dossier(incident_id: str):
    """
    [ENDPOINT PÚBLICO / AUDITORÍA]

    Consulta el expediente situacional consolidado y estado de atención médica/policial
    asociado a un identificador único de incidente.
    """
    dossier = incident_storage.get(incident_id)
    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró ningún expediente con el ID '{incident_id}'.",
        )
    return dossier


@app.get(
    "/api/v1/environmental-hazards",
    response_model=EnvironmentalRisk,
    status_code=status.HTTP_200_OK,
    tags=["Environmental"],
    responses={
        200: {"description": "Condiciones y riesgos ambientales obtenidos con éxito."},
        400: {"model": StandardErrorResponse, "description": "Coordenadas fuera de rango."},
    },
)
async def get_environmental_hazards(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitud en formato decimal (-90 a 90)"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitud en formato decimal (-180 a 180)"),
    has_fire: bool = Query(default=False, description="Indica si existe fuego activo en la zona"),
):
    """
    [ENDPOINT PÚBLICO / TELEMETRÍA]

    Consulta en tiempo real la meteorología de terceros para unas coordenadas específicas,
    calculando la dirección de dispersión de humo y el estado de adherencia del pavimento.
    """
    return weather_client.get_environmental_risk(
        latitude=lat,
        longitude=lon,
        has_fire=has_fire,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)

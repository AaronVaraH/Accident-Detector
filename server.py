"""
Servidor FastAPI para la PWA de Detección de Incidentes Viales y Fuego.
Provee:
- Streaming de video en tiempo real MJPEG (/api/stream)
- WebSocket bidireccional de telemetría y control (/ws/telemetry)
- WebSocket de enlace de subida para cámara de smartphone (/ws/uplink)
- Validación de ruta segura HTTPS para cámara (/api/camera/validate)
- Gestión y exportación del Backlog persistente en Supabase PostgreSQL + Storage (/api/backlog/*)
- Endpoints REST para configuración y auditoría de incidentes
- Servidor estático y manifest para Progressive Web App (PWA)
"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Response
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel

from config import settings
from src.pipeline_manager import pipeline_manager
from src.plate_detector import license_plate_detector
from src.enrichment import vehicle_service, weather_service, location_service, enrichment_aggregator
from src.dispatcher import alert_dispatcher
from src.microservice_client import incident_microservice_client
from src.database import backlog_db
from src.ssl_manager import ensure_ssl_certificates, evaluate_request_security, get_local_lan_ip
from services.incident_enrichment_service.main import (
    evaluate_and_dispatch_incident,
    get_incident_dossier as ms_get_incident_dossier,
    get_environmental_hazards as ms_get_environmental_hazards,
)

import warnings
warnings.filterwarnings("ignore")

# Filtro para suprimir el spam continuo de peticiones de polling en terminal
class NoisyEndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(ep in msg for ep in ["/api/status", "/api/client-frame", "/api/stream", "/api/health"])

logging.getLogger("uvicorn.access").addFilter(NoisyEndpointFilter())
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("PWAServer")

app = FastAPI(title="Accident & Fire Detector PWA", version="2.0.0")

# Permitir CORS para desarrollo o consumo multiplataforma
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


class HTTPSAndSecurityHeadersMiddleware:
    """
    Middleware ASGI puro de alta velocidad (sin bloqueo de StreamingResponse MJPEG ni WebSockets):
    1. Redirige HTTP -> HTTPS cuando hay Reverse Proxy TLS (Render) y FORCE_HTTPS=true.
    2. Inyecta cabeceras Permissions-Policy y HSTS para autorizar el uso seguro de la cámara.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers_dict = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        forwarded_proto = headers_dict.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        scheme = scope.get("scheme", "http").lower()
        is_https = (scheme == "https") or (forwarded_proto == "https")
        path = scope.get("path", "/")

        if settings.FORCE_HTTPS and forwarded_proto == "http" and path not in ("/api/health", "/api/status"):
            host = headers_dict.get("host", "localhost")
            qs = scope.get("query_string", b"").decode("latin1")
            target_url = f"https://{host}{path}" + (f"?{qs}" if qs else "")
            redirect = RedirectResponse(url=target_url, status_code=307)
            await redirect(scope, receive, send)
            return

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                raw_headers.append((b"permissions-policy", b"camera=(self), geolocation=(self), microphone=()"))
                raw_headers.append((b"x-content-type-options", b"nosniff"))
                if is_https:
                    raw_headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = raw_headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


app.add_middleware(HTTPSAndSecurityHeadersMiddleware)


PWA_DIR = Path(__file__).resolve().parent / "pwa"
PWA_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DIR = Path(__file__).resolve().parent / "public"


class ControlPayload(BaseModel):
    source: Optional[str] = None
    lang: Optional[str] = None
    paused: Optional[bool] = None
    vehicle_conf: Optional[float] = None
    fire_conf: Optional[float] = None
    smoke_conf: Optional[float] = None


class PlateLookupPayload(BaseModel):
    plate: Optional[str] = None
    query: Optional[str] = None


class PlateRegisterPayload(BaseModel):
    plate: str
    brand: str
    model: str
    year: int
    color: str
    vehicle_type: str = "Sedán"
    fuel_type: str = "Gasolina"
    stolen_status: str = "SIN REPORTE DE ROBO"
    is_stolen: bool = False
    owner_type: str = "Particular"
    jurisdiction: str = "Ciudad de México"


class DispatchSimulationPayload(BaseModel):
    incident_type: str = "colision_critica"
    title: str = "COLISIÓN VEHICULAR DETECTADA"
    subtitle: str = "Desaceleración brusca 65 -> 0 km/h"
    plate: Optional[str] = "ABC-1234"


class BacklogStatusUpdatePayload(BaseModel):
    status: str = "EN_ATENCION"
    notes: Optional[str] = None


class BacklogIncidentCreatePayload(BaseModel):
    incident_type: str = "colision_critica"
    severity: str = "CRITICO"
    status: str = "PENDIENTE"
    title: str = "COLISIÓN VEHICULAR DETECTADA"
    subtitle: str = "Reporte registrado en backlog"
    camera_id: str = "camera_01"
    plate: Optional[str] = None
    notes: Optional[str] = ""


class SupabaseConfigPayload(BaseModel):
    supabase_url: str
    supabase_key: str
    bucket_name: Optional[str] = "incident-evidence"


@app.on_event("startup")
async def startup_event():
    logger.info("Iniciando Pipeline de IA en segundo plano...")
    ensure_ssl_certificates()
    pipeline_manager.start()


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Deteniendo Pipeline de IA...")
    pipeline_manager.stop()


async def generate_mjpeg_stream():
    """Generador HTTP multipart asíncrono para streaming continuo de video con Content-Length y sin bloquear el event loop."""
    last_frame_bytes = None
    try:
        while True:
            frame_bytes = pipeline_manager.get_latest_jpeg()
            if frame_bytes and frame_bytes != last_frame_bytes:
                last_frame_bytes = frame_bytes
                header = (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame_bytes)).encode("ascii") + b"\r\n\r\n"
                )
                yield header + frame_bytes + b"\r\n"
                await asyncio.sleep(0.04)  # ~25 FPS máximo
            else:
                await asyncio.sleep(0.045)  # Espera activa no bloqueante sin retransmitir datos duplicados
    except (GeneratorExit, asyncio.CancelledError):
        pass


@app.get("/api/stream")
async def video_stream():
    """Endpoint de transmisión MJPEG para navegadores y apps móviles."""
    return StreamingResponse(
        generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def numpy_safe_json(obj):
    if hasattr(obj, "item"):
        return obj.item()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """WebSocket de telemetría táctica y control remoto en tiempo real."""
    await websocket.accept()
    logger.info("Cliente WebSocket de telemetría conectado.")
    try:
        async def send_telemetry_loop():
            while True:
                telemetry = pipeline_manager.get_latest_telemetry()
                await websocket.send_text(json.dumps(telemetry, default=numpy_safe_json))
                await asyncio.sleep(0.1)

        async def receive_control_loop():
            while True:
                msg = await websocket.receive_text()
                data = json.loads(msg)
                action = data.get("action")
                if action == "set_source":
                    pipeline_manager.change_source(data.get("source", "vehicles.mp4"))
                elif action == "set_lang":
                    pipeline_manager.set_language(data.get("lang", "es"))
                elif action == "set_pause":
                    pipeline_manager.set_pause(bool(data.get("paused", False)))
                elif action == "set_sensitivity":
                    if "vehicle_conf" in data:
                        pipeline_manager.vehicle_conf = float(data["vehicle_conf"])
                    if "fire_conf" in data:
                        pipeline_manager.fire_conf = float(data["fire_conf"])
                    if "smoke_conf" in data:
                        pipeline_manager.smoke_conf = float(data["smoke_conf"])

        await asyncio.gather(send_telemetry_loop(), receive_control_loop())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass


@app.websocket("/ws/uplink")
async def websocket_uplink(websocket: WebSocket):
    """
    Enlace de subida para cámara de smartphone:
    La PWA móvil captura video local mediante navigator.mediaDevices.getUserMedia
    en ruta segura HTTPS/WSS y envía los frames al backend para procesarlos con YOLOv8.
    """
    await websocket.accept()
    forwarded_proto = websocket.headers.get("x-forwarded-proto", "").lower()
    scheme = websocket.url.scheme.lower()
    is_secure_ws = scheme == "wss" or forwarded_proto == "https"
    logger.info(f"Dispositivo móvil enlazado como sensor de cámara remota vía WebSocket (Seguro WSS={is_secure_ws}).")
    pipeline_manager.change_source("client_cam")
    try:
        while True:
            frame_bytes = await websocket.receive_bytes()
            pipeline_manager.push_client_frame(frame_bytes)
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info("Enlace WebSocket de cámara móvil cerrado (esperando reconexión o HTTPS fallback).")


@app.post("/api/client-frame")
async def post_client_frame(request: Request):
    """
    Ingesta de frames de cámara móvil mediante HTTPS POST:
    Permite a smartphones enviar video incluso a través de túneles o proxies
    donde WebSockets estén bloqueados o no disponibles.
    """
    body = await request.body()
    if not body:
        return JSONResponse(status_code=400, content={"error": "Frame vacío"})

    if pipeline_manager.source != "client_cam":
        pipeline_manager.change_source("client_cam")

    pipeline_manager.push_client_frame(body)
    return {"status": "ok", "bytes": len(body), "source": "client_cam"}


# --- Endpoints de Validación de Ruta Segura HTTPS para Cámara y Salud del Servicio ---

@app.get("/api/camera/validate")
def validate_camera_https_route(request: Request):
    """
    Valida que la conexión de la cámara se realice a través de una ruta segura HTTPS
    (TLS directo o Reverse Proxy HTTPS en producción como Render) y entrega las URLs seguras WSS/HTTPS.
    """
    host = request.headers.get("host", "localhost:8000")
    headers_dict = {k.lower(): v for k, v in request.headers.items()}
    security_info = evaluate_request_security(request.url.scheme, headers_dict, host)
    return JSONResponse(content={
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **security_info,
    })


@app.get("/api/ssl/cert.pem")
def download_local_ssl_cert():
    """Permite descargar el certificado público autofirmado para pruebas HTTPS en red local."""
    cert_path, _ = ensure_ssl_certificates()
    if not cert_path.exists():
        raise HTTPException(status_code=404, detail="Certificado SSL local no disponible.")
    return FileResponse(
        cert_path,
        media_type="application/x-pem-file",
        filename="titan-vision-local-ca.pem",
    )


@app.get("/api/health")
def get_health(request: Request):
    """Healthcheck para producción (Render CI/CD y balanceadores de carga)."""
    host = request.headers.get("host", "localhost:8000")
    headers_dict = {k.lower(): v for k, v in request.headers.items()}
    security_info = evaluate_request_security(request.url.scheme, headers_dict, host)
    return JSONResponse(content={
        "status": "healthy",
        "service": "TITAN Vision Accident & Fire Detector",
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT,
        "pipeline_running": pipeline_manager.is_running,
        "https_verified": security_info["is_https"],
        "camera_secure_context": security_info["camera_secure_context_valid"],
        "database": backlog_db.get_status(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/status")
def get_status():
    return JSONResponse(
        content=json.loads(json.dumps(pipeline_manager.get_latest_telemetry(), default=numpy_safe_json))
    )


# --- Endpoints de Backlog Persistente (Supabase PostgreSQL + Bucket) ---

@app.get("/api/incidents")
def get_incidents(limit: int = 50):
    """Retorna el historial unificado de siniestros desde el backlog en Supabase y memoria activa."""
    backlog_items = backlog_db.get_incidents(limit=limit)
    if backlog_items:
        return JSONResponse(content=backlog_items)
    return JSONResponse(content=pipeline_manager.incidents_history[:limit])


@app.get("/api/backlog/status")
def get_backlog_status():
    """Estado de la conexión con Supabase PostgreSQL y el Bucket de evidencias."""
    return JSONResponse(content=backlog_db.get_status())


@app.post("/api/backlog/config")
def post_backlog_config(payload: SupabaseConfigPayload):
    """Configura en caliente las credenciales de Supabase y sincroniza el backlog."""
    status = backlog_db.configure(
        supabase_url=payload.supabase_url,
        supabase_key=payload.supabase_key,
        bucket_name=payload.bucket_name,
    )
    return JSONResponse(content={"status": "configured", "database": status})


@app.get("/api/backlog")
def get_backlog(
    limit: int = 100,
    status: Optional[str] = None,
    incident_type: Optional[str] = None,
    sync: bool = False,
):
    """Consulta el registro completo del backlog de incidentes y placas detectadas."""
    if sync and backlog_db.is_configured:
        backlog_db.sync_from_cloud(limit=limit)
    return JSONResponse(content={
        "database": backlog_db.get_status(),
        "incidents": backlog_db.get_incidents(limit=limit, status=status, incident_type=incident_type),
        "plates": backlog_db.get_plates(limit=limit),
    })


@app.post("/api/backlog/incidents")
def post_create_backlog_incident(payload: BacklogIncidentCreatePayload):
    """Permite registrar manualmente un incidente en el backlog de Supabase."""
    norm_plate = vehicle_service.normalize_plate(payload.plate) if payload.plate else ""
    vehicle_info = vehicle_service.cache.get(norm_plate) or (
        vehicle_service._generate_deterministic_record(norm_plate) if norm_plate else {}
    )
    frame_bytes = pipeline_manager.get_latest_jpeg()
    record = backlog_db.record_incident(
        {
            "incident_type": payload.incident_type,
            "severity": payload.severity,
            "status": payload.status,
            "title": payload.title,
            "subtitle": payload.subtitle,
            "camera_id": payload.camera_id,
            "plate": payload.plate,
            "vehicle": vehicle_info,
            "enrichment": {"vehicle": vehicle_info},
            "notes": payload.notes or "",
        },
        frame_jpeg=frame_bytes,
    )
    pipeline_manager.incidents_history.insert(0, record)
    return JSONResponse(status_code=201, content={"status": "recorded", "incident": record})


@app.patch("/api/backlog/incidents/{incident_id}")
def patch_backlog_incident(incident_id: str, payload: BacklogStatusUpdatePayload):
    """Actualiza el estado de seguimiento o notas de un siniestro en el backlog."""
    updated = backlog_db.update_incident_status(
        incident_id=incident_id,
        status=payload.status,
        notes=payload.notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Incidente '{incident_id}' no encontrado en el backlog.")
    return JSONResponse(content={"status": "updated", "incident": updated})


@app.get("/api/backlog/export")
def export_backlog_data(format: str = "csv", target: str = "incidents"):
    """
    Descarga el registro del backlog para análisis externo o auditoría en formato CSV o JSON.
    """
    fmt = format.lower().strip()
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "json":
        data = backlog_db.export_json()
        return Response(
            content=json.dumps(data, indent=2, ensure_ascii=False, default=numpy_safe_json),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="titan_backlog_{ts_str}.json"'},
        )

    csv_content = backlog_db.export_csv(target=target)
    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="titan_backlog_{target}_{ts_str}.csv"'},
    )


@app.post("/api/control")
def post_control(payload: ControlPayload):
    if payload.source is not None:
        pipeline_manager.change_source(payload.source)
    if payload.lang is not None:
        pipeline_manager.set_language(payload.lang)
    if payload.paused is not None:
        pipeline_manager.set_pause(payload.paused)
    if payload.vehicle_conf is not None:
        pipeline_manager.vehicle_conf = payload.vehicle_conf
    if payload.fire_conf is not None:
        pipeline_manager.fire_conf = payload.fire_conf
    if payload.smoke_conf is not None:
        pipeline_manager.smoke_conf = payload.smoke_conf
    return {"status": "ok", "telemetry": pipeline_manager.get_latest_telemetry()}


@app.post("/api/upload-video")
async def post_upload_video(request: Request):
    """
    Permite subir un archivo de video arbitrario (MP4, AVI, MOV) elegido por el juez
    y cambiar automáticamente el pipeline para procesarlo en vivo con cero errores.
    """
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo de video vacío.")

    samples_dir = Path("tests/video_samples")
    samples_dir.mkdir(parents=True, exist_ok=True)
    filename = request.headers.get("x-filename", "judge_test_video.mp4")
    target_path = samples_dir / filename

    with open(target_path, "wb") as f:
        f.write(content)

    pipeline_manager.change_source(str(target_path))
    logger.info(f"Video del juez subido y cargado como fuente activa: {target_path}")

    return {
        "status": "ok",
        "filename": filename,
        "source": str(target_path),
        "message": "Video cargado con éxito en el pipeline de análisis en vivo.",
    }


# --- Endpoints de Placas y Registro Vehicular ---

@app.get("/api/plates")
def get_recent_plates(limit: int = 50):
    """Retorna las placas recientemente detectadas con sus expedientes vehiculares."""
    return JSONResponse(content=license_plate_detector.get_recent_plates(limit=limit))


@app.get("/api/plates/active")
def get_active_plates():
    """Retorna las placas asociadas a los vehículos que se encuentran activos en escena."""
    return JSONResponse(content=license_plate_detector.get_active_plates_dict())


@app.get("/api/plates/{plate}")
def get_plate_details(plate: str):
    """Consulta la ficha técnica vehicular por placa o VIN específico."""
    data = vehicle_service.lookup(plate)
    return JSONResponse(content=data)


@app.post("/api/plates/lookup")
def post_plate_lookup(payload: PlateLookupPayload):
    """Consulta los datos del vehículo por número de placa o VIN (JSON POST)."""
    search_term = payload.query or payload.plate or ""
    if not search_term:
        raise HTTPException(status_code=400, detail="Parámetro 'plate' o 'query' es requerido.")
    data = vehicle_service.lookup(search_term)
    return JSONResponse(content=data)


@app.post("/api/plates/register")
def post_plate_register(payload: PlateRegisterPayload):
    """Registra o actualiza un vehículo en la base de datos del sistema y en Supabase."""
    data = vehicle_service.register_custom_vehicle(payload.plate, payload.model_dump())
    return JSONResponse(content={"status": "registered", "vehicle": data})


class PlateDetectPayload(BaseModel):
    image_base64: Optional[str] = None


@app.post("/api/plates/detect")
async def post_detect_plate(request: Request, payload: Optional[PlateDetectPayload] = None):
    """
    Recibe una imagen (JSON con 'image_base64' o payload binario directo JPEG/PNG)
    y ejecuta la detección de placas con Roboflow 'vehicle-registration-plates-trudk/2' + OCR + consulta de datos.
    """
    frame = None
    content_type = request.headers.get("content-type", "")

    if payload and payload.image_base64:
        b64_str = payload.image_base64
        if "," in b64_str:
            b64_str = b64_str.split(",")[1]
        try:
            decoded = base64.b64decode(b64_str)
            np_arr = np.frombuffer(decoded, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error decodificando base64: {e}")
    elif "application/json" in content_type:
        try:
            body = await request.json()
            b64_str = body.get("image_base64", "")
            if "," in b64_str:
                b64_str = b64_str.split(",")[1]
            decoded = base64.b64decode(b64_str)
            np_arr = np.frombuffer(decoded, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error procesando JSON base64: {e}")
    else:
        raw_body = await request.body()
        if raw_body:
            np_arr = np.frombuffer(raw_body, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(
            status_code=400,
            detail="No se pudo decodificar la imagen proporcionada. Envíe JSON con 'image_base64' o bytes de imagen en el body.",
        )

    detected_records = license_plate_detector.scan_full_frame(frame)
    return JSONResponse(content={
        "status": "ok",
        "plates_found": len(detected_records),
        "plates": [r.to_dict() for r in detected_records],
    })


# --- Endpoints de Enriquecimiento y Contexto Situacional ---

@app.get("/api/enrichment/weather")
def get_weather(lat: Optional[float] = None, lon: Optional[float] = None):
    """Consulta la meteorología de la zona donde está ubicada la cámara."""
    kwargs = {}
    if lat is not None and lon is not None:
        kwargs = {"lat": lat, "lon": lon}
    data = weather_service.get_weather(**kwargs)
    return JSONResponse(content=data)


@app.get("/api/enrichment/location")
def get_location(lat: Optional[float] = None, lon: Optional[float] = None):
    """Consulta la ubicación física y geocodificación inversa de la cámara."""
    kwargs = {}
    if lat is not None and lon is not None:
        kwargs = {"lat": lat, "lon": lon}
    data = location_service.get_location(**kwargs)
    return JSONResponse(content=data)


@app.get("/api/enrichment/context")
def get_situational_context(lat: Optional[float] = None, lon: Optional[float] = None):
    """Consulta el expediente situacional consolidado (clima, ubicación, riesgos del microservicio y placas detectadas)."""
    kwargs = {}
    if lat is not None and lon is not None:
        kwargs = {"lat": lat, "lon": lon}
    weather = weather_service.get_weather(**kwargs)
    location = location_service.get_location(**kwargs)
    hazards = incident_microservice_client.get_environmental_hazards(
        lat=lat if lat is not None else 19.3012,
        lon=lon if lon is not None else -99.1824,
    )
    recent_plates = license_plate_detector.get_recent_plates(limit=10)
    ms_health = incident_microservice_client.check_health()
    return JSONResponse(content={
        "timestamp": datetime.now().isoformat(),
        "weather": weather,
        "location": location,
        "environmental_hazards": hazards,
        "microservice_status": ms_health.get("status", "connected"),
        "microservice_url": incident_microservice_client.base_url,
        "active_plates_count": len(recent_plates),
        "recent_plates": recent_plates,
    })


@app.get("/api/enrichment/hazards")
def get_enrichment_hazards(lat: float = 19.3012, lon: float = -99.1824, has_fire: bool = False):
    """Consume los riesgos ambientales y dispersión de humo desde el microservicio de enriquecimiento."""
    data = incident_microservice_client.get_environmental_hazards(lat=lat, lon=lon, has_fire=has_fire)
    return JSONResponse(content=data)


@app.get("/api/enrichment/dossier/{incident_id}")
def get_enrichment_dossier(incident_id: str):
    """Recupera el expediente situacional completo desde el microservicio o el backlog."""
    dossier = incident_microservice_client.get_incident_dossier(incident_id)
    if dossier:
        return JSONResponse(content=dossier)
    for inc in backlog_db.get_incidents(limit=200):
        if str(inc.get("incident_id")) == incident_id:
            return JSONResponse(content=inc)
    raise HTTPException(status_code=404, detail=f"Expediente '{incident_id}' no encontrado.")


# Exponer también directamente los endpoints v1 del microservicio para interoperabilidad
app.add_api_route(
    "/api/v1/incidents/evaluate-and-dispatch",
    evaluate_and_dispatch_incident,
    methods=["POST"],
    status_code=201,
    tags=["Microservice v1"],
)
app.add_api_route(
    "/api/v1/incidents/{incident_id}/dossier",
    ms_get_incident_dossier,
    methods=["GET"],
    tags=["Microservice v1"],
)
app.add_api_route(
    "/api/v1/environmental-hazards",
    ms_get_environmental_hazards,
    methods=["GET"],
    tags=["Microservice v1"],
)


@app.post("/api/enrichment/dispatch")
def post_simulate_dispatch(payload: DispatchSimulationPayload):
    """
    Genera un paquete de despacho de emergencia enriquecido para CAD/911/Bomberos,
    lo registra en el backlog de Supabase y envía la alerta por SMS mediante Twilio.
    """
    dispatch = enrichment_aggregator.enrich_incident(
        incident_type=payload.incident_type,
        title=payload.title,
        subtitle=payload.subtitle,
        plate=payload.plate,
    )

    # Consumir el Microservicio REST de Enriquecimiento y Despacho
    ms_dossier = incident_microservice_client.evaluate_and_dispatch(
        camera_id="CAM-CDMX-PERIFERICO-04",
        incident_type=payload.incident_type,
        confidence=0.92,
        telemetry={
            "initial_speed_kmh": 65.0,
            "impact_speed_kmh": 0.0,
            "delta_time_sec": 0.45,
            "has_fire": "fuego" in payload.incident_type.lower(),
            "has_smoke": "humo" in payload.incident_type.lower() or "fuego" in payload.incident_type.lower(),
        },
        detected_plate=payload.plate,
    )
    dispatch["microservice_dossier"] = ms_dossier

    sms_result = alert_dispatcher.dispatch_incident_alert(dispatch)
    dispatch["dispatch_status"] = sms_result

    # Persistir también en el backlog de Supabase
    backlog_db.record_incident(
        {
            "incident_id": (ms_dossier or {}).get("incident_id"),
            "incident_type": payload.incident_type,
            "severity": "CRITICO",
            "status": "EN_ATENCION",
            "title": payload.title,
            "subtitle": payload.subtitle,
            "camera_id": "CAM-CDMX-PERIFERICO-04",
            "plate": payload.plate,
            "vehicle": dispatch.get("vehicle"),
            "enrichment": dispatch,
            "dispatch_ticket_id": (ms_dossier or {}).get("dispatch_ticket_id"),
            "dispatch_status": str(sms_result.get("status", "DELIVERED")) if isinstance(sms_result, dict) else "SENT",
        },
        frame_jpeg=pipeline_manager.get_latest_jpeg(),
    )

    return JSONResponse(content=dispatch)


# --- Rutas de la PWA ---

@app.get("/manifest.json")
def get_manifest():
    return FileResponse(PWA_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def get_service_worker():
    return FileResponse(
        PWA_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/favicon.ico")
def get_favicon():
    fav_file = PWA_DIR / "favicon" / "favicon.ico"
    if not fav_file.exists():
        fav_file = PUBLIC_DIR / "favicon" / "favicon.ico"
    if fav_file.exists():
        return FileResponse(fav_file, media_type="image/x-icon")
    return Response(status_code=404)


# Servir assets estáticos y la aplicación principal
if PUBLIC_DIR.exists():
    app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")
app.mount("/static", StaticFiles(directory=str(PWA_DIR)), name="static")


@app.get("/")
def get_index():
    return FileResponse(PWA_DIR / "index.html")


@app.get("/historial")
def get_historial_page():
    """Vista dedicada para el Historial / Backlog Forense, Expedientes del Microservicio y Placas."""
    historial_path = PWA_DIR / "historial.html"
    if historial_path.exists():
        return FileResponse(historial_path)
    return FileResponse(PWA_DIR / "index.html")


if __name__ == "__main__":
    import argparse
    import os
    import uvicorn

    default_port = int(os.environ.get("PORT", 8000))
    default_ssl = os.environ.get("ENABLE_LOCAL_SSL", "false").lower() in ("true", "1", "yes")

    parser = argparse.ArgumentParser(description="TITAN Vision PWA Server")
    parser.add_argument("--port", type=int, default=default_port, help="Puerto HTTP/HTTPS (por defecto 8000 o $PORT)")
    parser.add_argument("--ssl", action="store_true", default=default_ssl, help="Habilitar HTTPS nativo para acceso seguro a cámara")
    args = parser.parse_args()

    local_ip = get_local_lan_ip()
    ssl_kwargs = {}

    if args.ssl and not settings.IS_PRODUCTION:
        cert_path, key_path = ensure_ssl_certificates()
        if cert_path.exists() and key_path.exists():
            ssl_kwargs = {
                "ssl_certfile": str(cert_path),
                "ssl_keyfile": str(key_path),
            }
        else:
            logger.warning("No se encontraron certificados SSL en config/certs. Iniciando en HTTP...")

    protocol = "https" if ssl_kwargs else "http"
    print(f"\n========================================================")
    print(f"🚀 TITAN Vision - Servidor PWA en línea ({settings.ENVIRONMENT.upper()})")
    print(f"💻 Acceso Desktop:  {protocol}://localhost:{args.port}")
    print(f"📱 Acceso Móvil:    {protocol}://{local_ip}:{args.port}")
    if not ssl_kwargs and not settings.IS_PRODUCTION:
        print(f"🔒 Para ruta segura HTTPS directa en red local (cámara móvil):")
        print(f"   python server.py --ssl")
    print(f"========================================================\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
        **ssl_kwargs,
    )

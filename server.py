"""
Servidor FastAPI para la PWA de Detección de Incidentes Viales y Fuego.
Provee:
- Streaming de video en tiempo real MJPEG (/api/stream)
- WebSocket bidireccional de telemetría y control (/ws/telemetry)
- WebSocket de enlace de subida para cámara de smartphone (/ws/uplink)
- Endpoints REST para configuración y auditoría de incidentes
- Servidor estático y manifest para Progressive Web App (PWA)
"""

import asyncio
import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.pipeline_manager import pipeline_manager
from src.plate_detector import license_plate_detector
from src.enrichment import vehicle_service, weather_service, location_service, enrichment_aggregator
from src.dispatcher import alert_dispatcher

import warnings
warnings.filterwarnings("ignore")

# Filtro para suprimir el spam continuo de peticiones de polling en terminal
class NoisyEndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(ep in msg for ep in ["/api/status", "/api/client-frame", "/api/stream"])

logging.getLogger("uvicorn.access").addFilter(NoisyEndpointFilter())
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("PWAServer")

app = FastAPI(title="Accident & Fire Detector PWA", version="1.0.0")

# Permitir CORS para desarrollo o consumo multiplataforma
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PWA_DIR = Path(__file__).resolve().parent / "pwa"
PWA_DIR.mkdir(parents=True, exist_ok=True)


class ControlPayload(BaseModel):
    source: Optional[str] = None
    lang: Optional[str] = None
    paused: Optional[bool] = None
    vehicle_conf: Optional[float] = None
    fire_conf: Optional[float] = None
    smoke_conf: Optional[float] = None


class PlateLookupPayload(BaseModel):
    plate: str


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


@app.on_event("startup")
async def startup_event():
    logger.info("Iniciando Pipeline de IA en segundo plano...")
    pipeline_manager.start()


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Deteniendo Pipeline de IA...")
    pipeline_manager.stop()


async def generate_mjpeg_stream():
    """Generador HTTP multipart asíncrono para streaming continuo de video con Content-Length y sin bloquear el event loop."""
    try:
        while True:
            frame_bytes = pipeline_manager.get_latest_jpeg()
            if frame_bytes:
                header = (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame_bytes)).encode("ascii") + b"\r\n\r\n"
                )
                yield header + frame_bytes + b"\r\n"
            await asyncio.sleep(0.033)  # ~30 FPS asíncrono no bloqueante
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
                await asyncio.sleep(0.04)  # ~25 actualizaciones/segundo

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
    y envía los frames al backend para procesarlos con YOLOv8 en el servidor.
    """
    await websocket.accept()
    logger.info("Dispositivo móvil enlazado como sensor de cámara remota vía WebSocket.")
    pipeline_manager.change_source("client_cam")
    try:
        while True:
            frame_bytes = await websocket.receive_bytes()
            pipeline_manager.push_client_frame(frame_bytes)
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info("Enlace WebSocket de cámara móvil cerrado (esperando reconexión o HTTP fallback).")


@app.post("/api/client-frame")
async def post_client_frame(request: Request):
    """
    Ingesta de frames de cámara móvil mediante HTTP POST:
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


@app.get("/api/status")
def get_status():
    return JSONResponse(
        content=json.loads(json.dumps(pipeline_manager.get_latest_telemetry(), default=numpy_safe_json))
    )


@app.get("/api/incidents")
def get_incidents():
    return JSONResponse(content=pipeline_manager.incidents_history)


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
    """Consulta la ficha técnica vehicular de una placa específica."""
    data = vehicle_service.lookup(plate)
    return JSONResponse(content=data)


@app.post("/api/plates/lookup")
def post_plate_lookup(payload: PlateLookupPayload):
    """Consulta los datos del vehículo por número de placa (JSON POST)."""
    data = vehicle_service.lookup(payload.plate)
    return JSONResponse(content=data)


@app.post("/api/plates/register")
def post_plate_register(payload: PlateRegisterPayload):
    """Registra o actualiza un vehículo en la base de datos del sistema."""
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
        # Intento de lectura directa de bytes (Content-Type: image/jpeg o raw)
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
def get_weather():
    """Consulta la meteorología de la zona donde está ubicada la cámara."""
    data = weather_service.get_weather()
    return JSONResponse(content=data)


@app.get("/api/enrichment/location")
def get_location():
    """Consulta la ubicación física y geocodificación inversa de la cámara."""
    data = location_service.get_location()
    return JSONResponse(content=data)


@app.get("/api/enrichment/context")
def get_situational_context():
    """Consulta el expediente situacional consolidado (clima, ubicación y placas detectadas)."""
    weather = weather_service.get_weather()
    location = location_service.get_location()
    recent_plates = license_plate_detector.get_recent_plates(limit=10)
    return JSONResponse(content={
        "timestamp": datetime.now().isoformat(),
        "weather": weather,
        "location": location,
        "active_plates_count": len(recent_plates),
        "recent_plates": recent_plates,
    })


@app.post("/api/enrichment/dispatch")
def post_simulate_dispatch(payload: DispatchSimulationPayload):
    """
    Genera un paquete de despacho de emergencia enriquecido para CAD/911/Bomberos
    cruzando tipo de siniestro, placa vehicular involucrada, condiciones de viento/clima y geolocalización,
    y envía la alerta por SMS mediante Twilio.
    """
    dispatch = enrichment_aggregator.enrich_incident(
        incident_type=payload.incident_type,
        title=payload.title,
        subtitle=payload.subtitle,
        plate=payload.plate,
    )
    sms_result = alert_dispatcher.dispatch_incident_alert(dispatch)
    dispatch["dispatch_status"] = sms_result
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


# Servir assets estáticos y la aplicación principal
app.mount("/static", StaticFiles(directory=str(PWA_DIR)), name="static")


@app.get("/")
def get_index():
    return FileResponse(PWA_DIR / "index.html")


if __name__ == "__main__":
    import argparse
    import os
    import socket
    import uvicorn

    default_port = int(os.environ.get("PORT", 8000))
    parser = argparse.ArgumentParser(description="TITAN Vision PWA Server")
    parser.add_argument("--port", type=int, default=default_port, help="Puerto HTTP/HTTPS (por defecto 8000 o $PORT)")
    parser.add_argument("--ssl", action="store_true", help="Habilitar HTTPS para acceso directo a cámara móvil")
    args = parser.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()

    protocol = "https" if args.ssl else "http"
    print(f"\n========================================================")
    print(f"🚀 TITAN Vision - Servidor PWA en línea")
    print(f"💻 Acceso Desktop:  {protocol}://localhost:{args.port}")
    print(f"📱 Acceso Móvil:    {protocol}://{local_ip}:{args.port}")
    if not args.ssl:
        print(f"ℹ️  Para habilitar la cámara en el navegador del celular con HTTPS:")
        print(f"   python server.py --ssl")
    print(f"========================================================\n")

    ssl_kwargs = {}
    if args.ssl:
        cert_path = Path("config/certs/cert.pem")
        key_path = Path("config/certs/key.pem")
        if cert_path.exists() and key_path.exists():
            ssl_kwargs = {
                "ssl_certfile": str(cert_path),
                "ssl_keyfile": str(key_path),
            }
        else:
            print("⚠️ No se encontraron certificados en config/certs. Arrancando en HTTP...")

    uvicorn.run("server:app", host="0.0.0.0", port=args.port, reload=False, log_level="warning", **ssl_kwargs)

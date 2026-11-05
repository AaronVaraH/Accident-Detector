"""
Pipeline Manager desacoplado para servidor Web y PWA.
Ejecuta la analítica de visión por computadora en segundo plano (subprocesos/hilo dedicado)
y expone buffers de video JPEG y telemetría en tiempo real para WebSockets y Streaming HTTP.
"""

import base64
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
import cv2
import numpy as np
sv = None

from config import settings
from src.stream import VideoStream
VehicleDetector = Any; FireDetector = Any
VehicleKinematicsTracker = Any
IncidentRuleEngine = Any; IncidentEvent = Any
from src.ui_hud import TacticalHUD
from src.motion import MotionAnalyzer
from src.i18n import i18n
from src.plate_detector import license_plate_detector
from src.enrichment import enrichment_aggregator, vehicle_service
from src.database import backlog_db

logger = logging.getLogger("PipelineManager")


class PipelineManager:
    def __init__(
        self,
        default_source: str = "client_cam",
        camera_id: str = "camera_01",
        lang: str = "es",
        fire_conf: float = settings.DEFAULT_FIRE_CONF,
        smoke_conf: float = settings.DEFAULT_SMOKE_CONF,
        vehicle_conf: float = settings.CONFIDENCE_THRESHOLD,
        track_persons: bool = True,
    ):
        self.source = default_source
        self.camera_id = camera_id
        self.lang = lang
        self.fire_conf = fire_conf
        self.smoke_conf = smoke_conf
        self.vehicle_conf = vehicle_conf
        self.track_persons = track_persons

        i18n.set_language(lang)

        # Estados de ejecución
        self.is_running = False
        self.is_paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Buffers compartidos con frame de espera táctico inicial
        standby_canvas = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(
            standby_canvas,
            "TITAN VISION - CONECTANDO CAMARA...",
            (70, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 240, 255),
            2,
            cv2.LINE_AA,
        )
        _, init_jpeg = cv2.imencode(".jpg", standby_canvas)
        self._latest_frame_jpeg: Optional[bytes] = init_jpeg.tobytes()

        self._latest_telemetry: Dict[str, Any] = {
            "status": "idle",
            "fps": 0.0,
            "frame_idx": 0,
            "source": str(self.source),
            "lang": self.lang,
            "counts": {"vehicles": 0, "persons": 0, "fire": 0, "smoke": 0, "incidents": 0, "plates": 0},
            "entities": [],
            "fire_smoke": [],
            "plates": [],
            "active_alert": None,
            "motion_energy": 0.0,
            "timestamp": datetime.now().isoformat(),
        }
        self.incidents_history: List[Dict[str, Any]] = []
        self._subscribers: List[Any] = []

        # Soporte para ingesta de cámara móvil o computadora
        self.is_client_camera = (default_source == "client_cam")
        self._client_frame_buffer: Optional[np.ndarray] = None
        self._client_frame_event = threading.Event()
        self._last_client_frame_time: float = 0.0

        # Componentes analíticos persistentes (se cargan una sola vez en memoria)
        logger.info("Precargando detectores de IA persistentes en memoria...")
        self.vehicle_detector: Optional[VehicleDetector] = None
        self.fire_detector: Optional[FireDetector] = None
        if False:
            self.vehicle_detector = VehicleDetector(
            conf_threshold=self.vehicle_conf,
            detect_persons=self.track_persons or True,
        )
        if False:
            self.fire_detector = FireDetector(
            fire_conf=self.fire_conf,
            smoke_conf=self.smoke_conf,
            enable_focal_lighter=True,
        )
        self.motion_analyzer = MotionAnalyzer(history_weight=0.85, motion_threshold=22)
        self.hud = TacticalHUD(source_name=str(self.source))

    def start(self):
        """Inicia el hilo del pipeline si no está activo."""
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            self.is_paused = False
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("PipelineManager iniciado en hilo secundario.")

    def stop(self):
        """Detiene el hilo del pipeline."""
        with self._lock:
            self.is_running = False
            self._client_frame_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("PipelineManager detenido.")

    def set_pause(self, paused: bool):
        self.is_paused = paused

    def set_language(self, lang: str):
        if lang in ["es", "en"]:
            self.lang = lang
            i18n.set_language(lang)

    def change_source(self, new_source: str):
        """Cambia dinámicamente la fuente (0, 1, archivo de video, o 'client_cam')."""
        with self._lock:
            if self.source == new_source:
                return
            if new_source == "client_cam":
                self.is_client_camera = True
                self.source = "client_cam"
            else:
                self.is_client_camera = False
                self.source = new_source
            self.hud.source_name = str(self.source)
            logger.info(f"Fuente cambiada a: {self.source}")

    def push_client_frame(self, image_data: bytes):
        """Recibe un frame JPG/PNG o crudo enviado por la cámara del smartphone."""
        np_arr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is not None:
            self._client_frame_buffer = frame
            self._last_client_frame_time = time.time()
            self._client_frame_event.set()

    def get_latest_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_frame_jpeg

    def get_latest_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._latest_telemetry)

    def _run_loop(self):
        while self.is_running:
            try:
                self._execute_pipeline()
            except Exception as e:
                logger.error(f"Excepción en ciclo del pipeline: {e}", exc_info=True)
                time.sleep(1.0)

    def _execute_pipeline(self):
        import supervision as sv
        from src.inference import VehicleDetector, FireDetector
        from src.kinematics import VehicleKinematicsTracker
        from src.incident_rules import IncidentRuleEngine, IncidentEvent
        is_webcam = str(self.source) in ["0", "1"] or str(self.source).isdigit()
        is_client = (self.source == "client_cam")
        should_detect_persons = self.track_persons or is_webcam or is_client

        # Sincronizar configuraciones dinámicas en detectores persistentes
        if self.vehicle_detector is None:
            self.vehicle_detector = VehicleDetector(
                conf_threshold=self.vehicle_conf,
                detect_persons=self.track_persons or True,
            )
        if self.fire_detector is None:
            self.fire_detector = FireDetector(
                fire_conf=self.fire_conf,
                smoke_conf=self.smoke_conf,
                enable_focal_lighter=True,
            )
        self.vehicle_detector.conf_threshold = self.vehicle_conf
        self.fire_detector.fire_conf = self.fire_conf
        self.fire_detector.smoke_conf = self.smoke_conf

        stream_fps = 30.0
        stream = None
        if not is_client:
            try:
                stream = VideoStream(source=self.source)
                stream_fps = stream.fps if stream.fps > 0 else 30.0
            except Exception as e:
                logger.error(f"Error abriendo VideoStream ({self.source}): {e}")
                # Fallback a video de muestra
                if self.source != "vehicles.mp4":
                    self.source = "vehicles.mp4"
                    stream = VideoStream(source="vehicles.mp4")

        kinematics_tracker = VehicleKinematicsTracker(
            fps=stream_fps,
            distance_meters=15.0,
            is_webcam=is_webcam or is_client,
        )
        rule_engine = IncidentRuleEngine(
            cooldown_seconds=settings.INCIDENT_COOLDOWN_SECONDS,
            fire_persistence_frames=max(3, settings.CONSECUTIVE_FIRE_FRAMES_REQUIRED),
            smoke_persistence_frames=2,
        )
        trace_annotator = sv.TraceAnnotator(
            thickness=2,
            trace_length=int(stream_fps * 1.5),
            color=sv.Color(r=0, g=215, b=255),
        )

        fps_time = time.time()
        fps_counter = 0
        current_fps = stream_fps
        frame_idx = 0
        confirmed_incidents_count = 0
        active_incident_banner = None
        banner_expiry_time = 0.0

        cached_fire_detections = sv.Detections.empty()
        cached_fire_labels = []
        cached_entity_detections = None

        current_source_cached = self.source
        stream_gen = stream.read_frames() if stream else None

        def get_next_frame():
            nonlocal frame_idx, stream_gen
            if self.is_client_camera:
                signaled = self._client_frame_event.wait(timeout=0.30)
                if not signaled:
                    # Timeout esperando nuevo frame del cliente: no reprocesar el frame anterior para no anular la energía de movimiento
                    return None, None
                self._client_frame_event.clear()
                now = time.time()
                if self._client_frame_buffer is not None and (now - self._last_client_frame_time < 3.0):
                    frame_idx += 1
                    return frame_idx, self._client_frame_buffer
                return None, None
            else:
                if stream_gen is None:
                    return None, None
                try:
                    f_idx, f = next(stream_gen)
                    frame_idx = f_idx
                    return f_idx, f
                except (StopIteration, Exception):
                    return None, None

        while self.is_running and (self.source == current_source_cached):
            if self.is_paused:
                time.sleep(0.05)
                continue

            f_idx, frame = get_next_frame()
            if frame is None:
                # Si es cámara móvil y no hay frames recientes, mostrar pantalla de espera limpia
                if is_client:
                    # Solo mostrar standby si pasaron más de 4 segundos sin recibir frames del cliente
                    if time.time() - self._last_client_frame_time > 4.0:
                        standby = np.zeros((480, 640, 3), dtype=np.uint8)
                        cv2.putText(
                            standby,
                            "CAMARA REMOTA EN ESPERA",
                            (140, 220),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.75,
                            (0, 240, 255),
                            2,
                            cv2.LINE_AA,
                        )
                        cv2.putText(
                            standby,
                            "Presiona 'ACTIVAR CAMARA' en tu smartphone o dispositivo",
                            (80, 265),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.50,
                            (180, 200, 220),
                            1,
                            cv2.LINE_AA,
                        )
                        ret, s_buf = cv2.imencode(".jpg", standby, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                        if ret:
                            with self._lock:
                                self._latest_frame_jpeg = s_buf.tobytes()
                    time.sleep(0.02)
                    continue

                # Si es un video local terminado, reiniciar bucle
                if stream and not is_webcam and not is_client:
                    stream.release()
                    try:
                        stream = VideoStream(source=self.source)
                        stream_gen = stream.read_frames()
                    except Exception as loop_err:
                        logger.warning(f"Error reiniciando video {self.source}: {loop_err}")
                        time.sleep(1.0)
                    continue
                time.sleep(0.03)
                continue

            # Cálculo de FPS de inferencia
            fps_counter += 1
            now = time.time()
            if now - fps_time >= 1.0:
                current_fps = fps_counter / (now - fps_time)
                fps_counter = 0
                fps_time = now

            # Sincronización dinámica de umbrales ajustados en tiempo real por el usuario
            self.vehicle_detector.conf_threshold = self.vehicle_conf
            self.fire_detector.fire_conf = self.fire_conf
            self.fire_detector.smoke_conf = self.smoke_conf

            # 1. Movimiento Óptico Dinámico
            raw_energy, motion_boxes = self.motion_analyzer.update(frame)
            motion_energy = float(raw_energy)

            # 2. Detección vehicular y humana con motion gate adaptativo
            if motion_energy < 0.035 and f_idx % 2 != 0 and cached_entity_detections is not None:
                entity_detections = cached_entity_detections
            else:
                entity_detections = self.vehicle_detector.detect(frame)
                cached_entity_detections = entity_detections

            # 3. Tracking y cinemática
            tracked_entities, kinematic_anomalies = kinematics_tracker.update(
                entity_detections, f_idx, timestamp=now
            )

            # 4. Fuego y Humo (Inferencia cadenciada cada 3 frames para alta velocidad en CPU)
            if f_idx % 3 == 0 or cached_fire_detections is None:
                cached_fire_detections, cached_fire_labels = self.fire_detector.detect(frame)
            fire_detections, fire_labels = cached_fire_detections, cached_fire_labels

            # 5. Motor de reglas de siniestro
            incident: Optional[IncidentEvent] = rule_engine.evaluate(
                frame_idx=f_idx,
                kinematic_anomalies=kinematic_anomalies,
                fire_detections=fire_detections,
                frame=frame,
            )

            if incident:
                confirmed_incidents_count += 1
                is_only_smoke = (incident.incident_type == "humo_detectado")
                active_incident_banner = {
                    "title": incident.title,
                    "subtitle": incident.subtitle,
                    "type": incident.incident_type,
                    "is_smoke": is_only_smoke,
                    "is_critical": True,
                }
                banner_expiry_time = now + 4.5

                # Registro histórico enriquecido con contexto vehicular y APIs
                active_plates_dict = license_plate_detector.get_active_plates_dict()
                incident_plate = None
                if len(active_plates_dict) > 0:
                    incident_plate = list(active_plates_dict.values())[0].get("plate")

                enriched_payload = enrichment_aggregator.enrich_incident(
                    incident_type=incident.incident_type,
                    title=incident.title,
                    subtitle=incident.subtitle,
                    plate=incident_plate,
                    camera_id=self.camera_id,
                )

                incident_record = {
                    "id": confirmed_incidents_count,
                    "title": incident.title,
                    "subtitle": incident.subtitle,
                    "type": incident.incident_type,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "frame_idx": f_idx,
                    "plate": incident_plate,
                    "vehicle": enriched_payload.get("vehicle"),
                    "enrichment": enriched_payload,
                }
                ret_snap, snap_buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                snap_bytes = snap_buf.tobytes() if ret_snap else None
                saved_record = backlog_db.record_incident(
                    {
                        **incident_record,
                        "camera_id": self.camera_id,
                        "source": str(self.source),
                        "telemetry": {"motion_energy": motion_energy, "fps": current_fps},
                    },
                    frame_jpeg=snap_bytes,
                )
                self.incidents_history.insert(0, saved_record)
                if len(self.incidents_history) > 50:
                    self.incidents_history.pop()

            if now > banner_expiry_time:
                active_incident_banner = None

            # 6. Renderizado LIMPIO sobre el frame (SOLO recuadros tácticos de detección, sin HUD invasivo)
            annotated_frame = frame.copy()

            telemetry_entities = []
            vehicles_count = 0
            persons_count = 0
            active_plates_dict = license_plate_detector.get_active_plates_dict()

            if tracked_entities.tracker_id is not None:
                raw_classes = tracked_entities.data.get("raw_class_name", ["entity"] * len(tracked_entities))
                for box, tracker_id, raw_cls in zip(
                    tracked_entities.xyxy,
                    tracked_entities.tracker_id,
                    raw_classes,
                ):
                    tid = int(tracker_id)
                    is_person = raw_cls.lower() in ["persona", "person"]
                    
                    # Encolar recorte de vehículo para detección de placas y OCR solo si tiene tamaño suficiente
                    if not is_person:
                        vehicles_count += 1
                        vw = box[2] - box[0]
                        vh = box[3] - box[1]
                        if vw >= 85 and vh >= 55:
                            if (tid not in active_plates_dict and f_idx % 8 == 0) or (f_idx % 30 == 0):
                                license_plate_detector.enqueue_detection(frame, box, tid)
                    else:
                        persons_count += 1

                    speed = kinematics_tracker.get_speed(tracker_id)
                    class_name = i18n.get_class_name(raw_cls)
                    if is_person:
                        box_color = (130, 230, 0)
                    else:
                        box_color = (0, 165, 255) if speed > 50.0 else (0, 220, 255)

                    plate_record = active_plates_dict.get(tid)
                    plate_str = plate_record.get("plate") if plate_record else None

                    label_text = f"#{tracker_id} {class_name} | {speed:.1f} km/h"
                    annotated_frame = self.hud.render_tactical_box(
                        frame=annotated_frame,
                        box=box,
                        label=label_text,
                        color=box_color,
                        plate_text=plate_str,
                    )

                    entity_info = {
                        "id": int(tid),
                        "class": str(class_name),
                        "raw_class": str(raw_cls),
                        "speed": float(round(float(speed), 1)),
                        "box": [float(round(float(coord), 1)) for coord in box],
                        "is_fast": bool(speed > 50.0),
                    }
                    if plate_record:
                        entity_info["plate"] = plate_record.get("plate")
                        entity_info["vehicle_data"] = plate_record.get("vehicle_data", {})
                    telemetry_entities.append(entity_info)

            # Escaneo periódico directo de placas si no hay vehículos o es cámara móvil/webcam
            if (vehicles_count == 0 or is_client or is_webcam) and (f_idx % 45 == 0 or f_idx <= 2):
                license_plate_detector.enqueue_full_frame(frame)

            # Dibujar placas detectadas en la escena general
            if -1 in active_plates_dict:
                gen_plate = active_plates_dict[-1]
                gbox = gen_plate.get("box")
                gplate = gen_plate.get("plate")
                if gbox and len(gbox) == 4 and gplate:
                    annotated_frame = self.hud.render_tactical_box(
                        frame=annotated_frame,
                        box=gbox,
                        label=f"PLACA: {gplate}",
                        color=(0, 255, 140),
                        plate_text=gplate,
                    )
                    telemetry_entities.append({
                        "id": 999,
                        "class": "Placa",
                        "raw_class": "plate",
                        "speed": 0.0,
                        "box": [float(c) for c in gbox],
                        "is_fast": False,
                        "plate": gplate,
                        "vehicle_data": gen_plate.get("vehicle_data", {}),
                    })

            # Dibujar recuadros tácticos de movimiento activo en escena
            if motion_energy >= 0.06 and motion_boxes:
                for mx1, my1, mx2, my2 in motion_boxes[:3]:
                    cv2.rectangle(annotated_frame, (mx1, my1), (mx2, my2), (0, 180, 255), 1)

            telemetry_fire_smoke = []
            fires_count = 0
            smokes_count = 0

            if len(fire_detections) > 0 and fire_detections.class_id is not None:
                for box, flabel, cid in zip(fire_detections.xyxy, fire_labels, fire_detections.class_id):
                    is_fuego = (int(cid) == 1)
                    is_humo = (int(cid) == 0)
                    if is_fuego:
                        fires_count += 1
                    if is_humo:
                        smokes_count += 1

                    annotated_frame = self.hud.render_tactical_box(
                        frame=annotated_frame,
                        box=box,
                        label=flabel,
                        is_fire=is_fuego,
                        is_smoke=is_humo,
                    )

                    telemetry_fire_smoke.append({
                        "label": str(flabel),
                        "class_id": int(cid),
                        "type": "fire" if is_fuego else "smoke",
                        "box": [float(round(float(coord), 1)) for coord in box],
                    })

            # La cámara se mantiene 100% limpia sin barras superiores ni inferiores que tapen el video.
            # Toda la telemetría, FPS y alertas se proyectan en el dashboard web y WebSocket.

            # Codificación a JPEG comprimido para streaming HTTP
            ret, buffer = cv2.imencode(
                ".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75]
            )

            if ret:
                jpeg_bytes = buffer.tobytes()
                recent_plates = license_plate_detector.get_recent_plates(limit=10)
                with self._lock:
                    self._latest_frame_jpeg = jpeg_bytes
                    self._latest_telemetry = {
                        "status": "running",
                        "fps": float(round(float(current_fps), 1)),
                        "frame_idx": int(f_idx),
                        "source": str(self.source),
                        "lang": str(self.lang),
                        "counts": {
                            "vehicles": int(vehicles_count),
                            "persons": int(persons_count),
                            "fire": int(fires_count),
                            "smoke": int(smokes_count),
                            "incidents": int(confirmed_incidents_count),
                            "plates": int(len(recent_plates)),
                        },
                        "entities": telemetry_entities,
                        "fire_smoke": telemetry_fire_smoke,
                        "plates": recent_plates,
                        "active_alert": active_incident_banner,
                        "motion_energy": float(round(float(motion_energy), 2)),
                        "timestamp": datetime.now().isoformat(),
                    }

        if stream:
            stream.release()


# Instancia singleton del pipeline lista para ser consumida por el servidor
pipeline_manager = PipelineManager()

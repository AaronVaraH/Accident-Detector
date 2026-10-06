import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional
import cv2
import numpy as np
import supervision as sv

from config import settings
from src.stream import VideoStream
from src.inference import VehicleDetector, FireDetector
from src.kinematics import VehicleKinematicsTracker
from src.incident_rules import IncidentRuleEngine, IncidentEvent
from src.ui_hud import TacticalHUD
from src.motion import MotionAnalyzer
from src.i18n import i18n

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AccidentDetector")


def load_camera_config(camera_id: str = "camera_01") -> dict:
    """Carga los parámetros de calibración y geolocalización de la cámara."""
    config_path = settings.CAMERAS_CONFIG_PATH
    if not config_path.exists():
        logger.warning(f"No se encontró archivo de cámaras en {config_path}. Usando valores por defecto.")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        cameras = json.load(f)
    return cameras.get(camera_id, {})


def run_pipeline(
    source: str,
    camera_id: str = "camera_01",
    view: bool = True,
    output_path: str = None,
    show_lines: bool = False,
    track_persons: bool = False,
    lang: str = "es",
    fire_conf: float = 0.18,
    smoke_conf: float = 0.40,
):
    """
    Bucle principal de ejecución del detector de incidentes con Interfaz Táctica HUD:
    - Ingesta de video con OpenCV
    - Soporte multilingüe en alertas y telemetría (ESP/ENG)
    - Detección vehicular y humana en tiempo real
    - Analítica de movimiento óptico continuo (Motion Energy)
    - Detección dual y discriminada de fuego y humo
    - Ventana redimensionable y pantalla completa sin distorsión
    - Motor de reglas y alertas dinámicas
    - HUD Táctico Cyber-Security
    """
    i18n.set_language(lang)
    camera_data = load_camera_config(camera_id)
    calib = camera_data.get("calibration", {})
    dist_meters = calib.get("distance_meters", 15.0)

    # Coordenadas de líneas virtuales si existen
    line_a_pts = None
    line_b_pts = None
    if "line_a" in calib and "line_b" in calib:
        line_a_pts = (tuple(calib["line_a"]["start"]), tuple(calib["line_a"]["end"]))
        line_b_pts = (tuple(calib["line_b"]["start"]), tuple(calib["line_b"]["end"]))

    logger.info(f"Iniciando ingesta de video desde: {source}")
    stream = VideoStream(source=source)

    # 1. Detector de Entidades Móviles (Vehículos y Personas para pruebas en webcam)
    is_webcam = str(source) in ["0", "1"] or str(source).isdigit()
    should_detect_persons = track_persons or is_webcam

    vehicle_detector = VehicleDetector(
        conf_threshold=settings.CONFIDENCE_THRESHOLD,
        detect_persons=should_detect_persons,
    )

    # 2. Detector Dual de Fuego y Humo (Llamas en luz/oscuridad + Incendios macro)
    fire_detector = FireDetector(
        fire_conf=fire_conf,
        smoke_conf=smoke_conf,
    )

    # 3. Analizador de Movimiento Óptico y HUD Táctico
    motion_analyzer = MotionAnalyzer(history_weight=0.85, motion_threshold=22)
    hud = TacticalHUD(source_name=str(source))

    # 4. Tracker de cinemática y motor de reglas
    kinematics_tracker = VehicleKinematicsTracker(
        fps=stream.fps,
        distance_meters=dist_meters,
        line_a_pts=line_a_pts,
        line_b_pts=line_b_pts,
        is_webcam=is_webcam,
    )
    rule_engine = IncidentRuleEngine(
        cooldown_seconds=settings.INCIDENT_COOLDOWN_SECONDS,
        fire_persistence_frames=settings.CONSECUTIVE_FIRE_FRAMES_REQUIRED,
        smoke_persistence_frames=3,
    )

    # Anotador de trayectorias (trazas de movimiento)
    trace_annotator = sv.TraceAnnotator(
        thickness=2,
        trace_length=int(stream.fps * 1.5),
        color=sv.Color(r=0, g=215, b=255),
    )

    # Grabador de video opcional
    video_writer = None
    if output_path:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        video_writer = cv2.VideoWriter(
            output_path, fourcc, stream.fps, (stream.width, stream.height)
        )
        logger.info(f"Guardando video anotado en: {output_path}")

    # Configuración de ventana de visualización redimensionable (escala al maximizar o pantalla completa)
    window_name = i18n.get("window_title")
    is_fullscreen = False
    if view:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    fps_time = time.time()
    fps_counter = 0
    current_fps = 0.0
    confirmed_incidents_count = 0
    active_incident_banner = None
    banner_expiry_time = 0.0

    logger.info("Pipeline en ejecución con HUD Táctico. Presione 'Q' para salir, 'P' para pausar, 'F' pantalla completa, 'L' alternar idioma.")

    try:
        for frame_idx, frame in stream.read_frames():
            # Cálculo de FPS de renderizado
            fps_counter += 1
            now = time.time()
            if now - fps_time >= 1.0:
                current_fps = fps_counter / (now - fps_time)
                fps_counter = 0
                fps_time = now

            # A. Analizador de Dinámica de Movimiento Óptico
            motion_energy, motion_boxes = motion_analyzer.update(frame)

            # B. Detección de entidades móviles (autos/motos/personas)
            entity_detections = vehicle_detector.detect(frame)

            # C. Tracking con ByteTrack y cinemática de velocidad
            tracked_entities, kinematic_anomalies = kinematics_tracker.update(
                entity_detections, frame_idx
            )

            # D. Detección dual de fuego y humo
            fire_detections, fire_labels = fire_detector.detect(frame)

            # E. Evaluación en motor de reglas
            incident: Optional[IncidentEvent] = rule_engine.evaluate(
                frame_idx=frame_idx,
                kinematic_anomalies=kinematic_anomalies,
                fire_detections=fire_detections,
                frame=frame,
            )

            if incident:
                confirmed_incidents_count += 1
                logger.critical(f"⚠️ {incident}")
                is_only_smoke = (incident.incident_type == "humo_detectado")
                active_incident_banner = (incident.title, incident.subtitle, is_only_smoke)
                banner_expiry_time = now + 4.5

            # F. Renderizado Gráfico HUD Táctico
            annotated_frame = frame.copy()

            # 1. Trazas de desplazamiento cinemático
            annotated_frame = trace_annotator.annotate(
                scene=annotated_frame, detections=tracked_entities
            )

            # 2. Cajas Tácticas con esquinas reforzadas para Entidades Rastreadas
            if tracked_entities.tracker_id is not None:
                raw_classes = tracked_entities.data.get("raw_class_name", ["entity"] * len(tracked_entities))
                for box, tracker_id, raw_cls in zip(
                    tracked_entities.xyxy,
                    tracked_entities.tracker_id,
                    raw_classes,
                ):
                    speed = kinematics_tracker.get_speed(tracker_id)
                    class_name = i18n.get_class_name(raw_cls)
                    label_text = f"#{tracker_id} {class_name} | {speed:.1f} km/h"
                    
                    # Distinguir colores por tipo de entidad
                    box_color = (0, 220, 255)  # Cian/Ámbar estándar
                    if raw_cls.lower() in ["persona", "person"]:
                        box_color = (130, 230, 0)  # Verde esmeralda para personas
                    elif speed > 50.0:
                        box_color = (0, 165, 255)  # Naranja velocidad

                    annotated_frame = hud.render_tactical_box(
                        frame=annotated_frame,
                        box=box,
                        label=label_text,
                        color=box_color,
                        is_fire=False,
                        is_smoke=False,
                    )

            # 3. Cajas Tácticas diferenciadas para Fuego y Humo
            if len(fire_detections) > 0 and fire_detections.class_id is not None:
                for box, flabel, cid in zip(fire_detections.xyxy, fire_labels, fire_detections.class_id):
                    is_fuego = (cid == 1)
                    is_humo = (cid == 0)
                    annotated_frame = hud.render_tactical_box(
                        frame=annotated_frame,
                        box=box,
                        label=flabel,
                        is_fire=is_fuego,
                        is_smoke=is_humo,
                    )

            # 4. Líneas virtuales de cruce si están activas
            if show_lines and line_a_pts and line_b_pts:
                cv2.line(annotated_frame, line_a_pts[0], line_a_pts[1], (0, 255, 255), 2)
                cv2.line(annotated_frame, line_b_pts[0], line_b_pts[1], (255, 128, 0), 2)

            # 5. Banner de Alerta Específico (Diferenciación 100% precisa: Humo vs Fuego vs Ambos)
            has_fire_vis = len(fire_detections) > 0 and any(cid == 1 for cid in fire_detections.class_id)
            has_smoke_vis = len(fire_detections) > 0 and any(cid == 0 for cid in fire_detections.class_id)

            if has_fire_vis and has_smoke_vis:
                annotated_frame = hud.render_incident_banner(
                    frame=annotated_frame,
                    title=i18n.get("fire_smoke_detected_title"),
                    subtitle=i18n.get("fire_smoke_detected_sub"),
                    is_critical=True,
                    is_smoke=False,
                )
            elif has_fire_vis:
                annotated_frame = hud.render_incident_banner(
                    frame=annotated_frame,
                    title=i18n.get("fire_detected_title"),
                    subtitle=i18n.get("fire_detected_sub"),
                    is_critical=True,
                    is_smoke=False,
                )
            elif has_smoke_vis:
                annotated_frame = hud.render_incident_banner(
                    frame=annotated_frame,
                    title=i18n.get("smoke_detected_title"),
                    subtitle=i18n.get("smoke_detected_sub"),
                    is_critical=False,
                    is_smoke=True,
                )
            elif active_incident_banner and now < banner_expiry_time:
                b_title, b_sub, b_is_smoke = active_incident_banner
                sub_truncated = b_sub[:72] + "..." if len(b_sub) > 72 else b_sub
                annotated_frame = hud.render_incident_banner(
                    frame=annotated_frame,
                    title=b_title,
                    subtitle=sub_truncated,
                    is_critical=not b_is_smoke,
                    is_smoke=b_is_smoke,
                )

            # 6. Barra Superior de Encabezado HUD (Telemetría, FPS, Movimiento)
            annotated_frame = hud.render_header(
                frame=annotated_frame,
                fps=current_fps,
                frame_idx=frame_idx,
                object_count=len(tracked_entities),
                motion_energy=motion_energy,
                has_fire=len(fire_detections) > 0,
            )

            # 7. Barra Inferior de Estado HUD
            has_incident_active = len(fire_detections) > 0 or (active_incident_banner and now < banner_expiry_time)
            status_desc = i18n.get("status_alert") if has_incident_active else i18n.get("status_active")
            annotated_frame = hud.render_footer(
                frame=annotated_frame,
                incident_count=confirmed_incidents_count,
                status_text=status_desc,
            )

            # Grabar frame si corresponde
            if video_writer:
                video_writer.write(annotated_frame)

            # Visualización interactiva con soporte de Pantalla Completa y Cambio de Idioma
            if view:
                cv2.imshow(window_name, annotated_frame)
                key = cv2.waitKey(1) & 0xFF
                if key in [ord("q"), ord("Q")]:
                    logger.info("Detención solicitada (tecla Q).")
                    break
                elif key in [ord("p"), ord("P")]:
                    cv2.waitKey(-1)
                elif key in [ord("f"), ord("F")]:
                    is_fullscreen = not is_fullscreen
                    if is_fullscreen:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                        logger.info("📺 Pantalla completa activada (tecla F).")
                    else:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                        logger.info("🪟 Ventana normal activada (tecla F).")
                elif key in [ord("l"), ord("L")]:
                    new_lang = i18n.toggle_language()
                    logger.info(f"🌐 Idioma alternado a: {new_lang.upper()} (tecla L)")
                    old_title = window_name
                    window_name = i18n.get("window_title")
                    if old_title != window_name:
                        cv2.destroyWindow(old_title)
                        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
                        if is_fullscreen:
                            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    except KeyboardInterrupt:
        logger.info("Interrupción por teclado.")
    finally:
        stream.release()
        if video_writer:
            video_writer.release()
        if view:
            cv2.destroyAllWindows()
        logger.info("Pipeline finalizado con éxito.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sistema Inteligente de Detección de Incidentes Viales")
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Ruta a video (.mp4/.avi), stream RTSP o '0' para webcam",
    )
    parser.add_argument(
        "--camera",
        type=str,
        default="camera_01",
        help="ID de cámara en config/cameras.json",
    )
    parser.add_argument(
        "--show-lines",
        action="store_true",
        help="Muestra las líneas virtuales de calibración de cruce (Línea A y B)",
    )
    parser.add_argument(
        "--track-persons",
        action="store_true",
        help="Habilita el rastreo de personas además de vehículos (activado automáticamente en webcam)",
    )
    parser.add_argument(
        "--no-view",
        action="store_true",
        help="Desactiva la ventana visual",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ruta para guardar el video resultante",
    )
    parser.add_argument(
        "--lang",
        "--language",
        type=str,
        default="es",
        choices=["es", "en", "esp", "eng"],
        help="Idioma de las alertas y telemetría HUD (es/esp o en/eng). Default: es",
    )
    parser.add_argument(
        "--fire-conf",
        type=float,
        default=0.18,
        help="Umbral de confianza para detección de fuego (default: 0.18)",
    )
    parser.add_argument(
        "--smoke-conf",
        type=float,
        default=0.40,
        help="Umbral de confianza para detección de humo (default: 0.40)",
    )
    parser.add_argument(
        "--web",
        "--pwa",
        action="store_true",
        help="Inicia el servidor Web & PWA en lugar de la ventana de escritorio",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Puerto para el servidor Web & PWA (default: 8000)",
    )

    args = parser.parse_args()
    src_input = int(args.source) if args.source.isdigit() else args.source

    if args.web:
        import uvicorn
        from src.pipeline_manager import pipeline_manager
        pipeline_manager.source = src_input
        pipeline_manager.set_language(args.lang)
        pipeline_manager.fire_conf = args.fire_conf
        pipeline_manager.smoke_conf = args.smoke_conf
        logger.info(f"Iniciando Servidor Web & PWA en http://localhost:{args.port}")
        uvicorn.run("server:app", host="0.0.0.0", port=args.port, reload=False)
        sys.exit(0)

    run_pipeline(
        source=src_input,
        camera_id=args.camera,
        view=not args.no_view,
        output_path=args.output,
        show_lines=args.show_lines,
        track_persons=args.track_persons,
        lang=args.lang,
        fire_conf=args.fire_conf,
        smoke_conf=args.smoke_conf,
    )

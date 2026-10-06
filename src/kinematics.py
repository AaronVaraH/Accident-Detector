import logging
from collections import deque
from typing import Dict, List, Optional, Tuple
import numpy as np
import supervision as sv

from config import settings

logger = logging.getLogger(__name__)


class KinematicAnomaly:
    """Representa una anomalía de frenado brusco o colisión detectada por cinemática."""

    def __init__(
        self,
        tracker_id: int,
        frame_idx: int,
        initial_speed_kmh: float,
        final_speed_kmh: float,
        delta_v: float,
        delta_t_seconds: float,
        bbox: np.ndarray,
    ):
        self.tracker_id = tracker_id
        self.frame_idx = frame_idx
        self.initial_speed_kmh = initial_speed_kmh
        self.final_speed_kmh = final_speed_kmh
        self.delta_v = delta_v
        self.delta_t_seconds = delta_t_seconds
        self.bbox = bbox

    def __str__(self) -> str:
        return (
            f"Anomalía Cinemática [ID {self.tracker_id}]: "
            f"Velocidad inicial: {self.initial_speed_kmh:.1f} km/h -> "
            f"Final: {self.final_speed_kmh:.1f} km/h | "
            f"Δv: {self.delta_v:.1f} km/h en {self.delta_t_seconds:.2f}s"
        )


class VehicleKinematicsTracker:
    """
    Gestiona el seguimiento continuo de entidades (vehículos y personas) con ByteTrack,
    cálculo de velocidades con filtrado de jitter (Deadband / Zero-Motion Filter)
    y detección de desaceleraciones críticas exclusivas para vehículos.
    """

    def __init__(
        self,
        fps: float = 30.0,
        distance_meters: float = 15.0,
        line_a_pts: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
        line_b_pts: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
        critical_decel_kmh: float = settings.CRITICAL_DECELERATION_THRESHOLD_KMH,
        is_webcam: bool = False,
    ):
        self.fps = fps if fps > 0 else 30.0
        self.distance_meters = distance_meters
        self.critical_decel_kmh = critical_decel_kmh
        self.is_webcam = is_webcam

        # ByteTrack de Supervision
        self.tracker = sv.ByteTrack(
            track_activation_threshold=0.25,
            lost_track_buffer=30,
            minimum_matching_threshold=0.8,
            frame_rate=int(self.fps),
        )

        # Configuración de líneas virtuales para estimación de velocidad
        self.line_a = None
        self.line_b = None
        # Escala base: en webcam la cámara está a corta distancia (~280 px/m)
        self.px_per_meter: float = 280.0 if is_webcam else 30.0

        if line_a_pts and line_b_pts and not is_webcam:
            self.setup_lines(line_a_pts, line_b_pts, distance_meters)

        # Historial de seguimiento por tracker_id
        self.vehicle_data: Dict[int, dict] = {}

    def setup_lines(
        self,
        line_a_pts: Tuple[Tuple[int, int], Tuple[int, int]],
        line_b_pts: Tuple[Tuple[int, int], Tuple[int, int]],
        distance_meters: float,
    ) -> None:
        """Inicializa las zonas de líneas virtuales y calcula la escala px/metro."""
        self.distance_meters = distance_meters
        start_a = sv.Point(line_a_pts[0][0], line_a_pts[0][1])
        end_a = sv.Point(line_a_pts[1][0], line_a_pts[1][1])
        start_b = sv.Point(line_b_pts[0][0], line_b_pts[0][1])
        end_b = sv.Point(line_b_pts[1][0], line_b_pts[1][1])

        self.line_a = sv.LineZone(start=start_a, end=end_a)
        self.line_b = sv.LineZone(start=start_b, end=end_b)

        avg_y_a = (line_a_pts[0][1] + line_a_pts[1][1]) / 2.0
        avg_y_b = (line_b_pts[0][1] + line_b_pts[1][1]) / 2.0
        pixel_distance = abs(avg_y_b - avg_y_a)
        if pixel_distance > 10 and self.distance_meters > 0:
            self.px_per_meter = pixel_distance / self.distance_meters
            logger.info(f"Escala calibrada: {self.px_per_meter:.2f} píxeles/metro")

    def update(
        self, detections: sv.Detections, frame_idx: int, timestamp: Optional[float] = None
    ) -> Tuple[sv.Detections, List[KinematicAnomaly]]:
        """
        Actualiza el tracker con las nuevas detecciones y analiza cinemática robusta.
        Elimina por completo el falso movimiento en personas u objetos estáticos.
        """
        tracked_detections = self.tracker.update_with_detections(detections)
        anomalies: List[KinematicAnomaly] = []

        if tracked_detections.tracker_id is None or len(tracked_detections) == 0:
            return tracked_detections, anomalies

        if self.line_a and self.line_b:
            self.line_a.trigger(tracked_detections)
            self.line_b.trigger(tracked_detections)

        raw_classes = tracked_detections.data.get(
            "raw_class_name", ["vehicle"] * len(tracked_detections)
        )

        now_ts = timestamp if timestamp is not None else None

        for i, tracker_id in enumerate(tracked_detections.tracker_id):
            bbox = tracked_detections.xyxy[i]
            raw_cls = str(raw_classes[i]).lower() if i < len(raw_classes) else "vehicle"
            is_person = (raw_cls in ["person", "persona"])

            # 1. Punto de anclaje geométrico estable
            # Para personas: el centroide es infinitamente más estable ante ligeros gestos de cabeza/pies
            if is_person:
                ref_x = (bbox[0] + bbox[2]) / 2.0
                ref_y = (bbox[1] + bbox[3]) / 2.0
                h_person_px = max(35.0, bbox[3] - bbox[1])
                # Referencia antropométrica (~1.65m estatura estándar)
                effective_px_per_m = max(80.0, h_person_px / 1.65)
                # Umbral de zona muerta para personas (elimina temblor de bbox YOLO)
                w_person_px = max(20.0, bbox[2] - bbox[0])
                min_motion_px = max(5.0, w_person_px * 0.08)
                min_speed_kmh = 2.0
            else:
                ref_x = (bbox[0] + bbox[2]) / 2.0
                ref_y = (bbox[1] + 3.0 * bbox[3]) / 4.0
                effective_px_per_m = self.px_per_meter
                min_motion_px = 3.5
                min_speed_kmh = 2.5

            if tracker_id not in self.vehicle_data:
                self.vehicle_data[tracker_id] = {
                    "history": deque(maxlen=int(self.fps * 2)),
                    "crossed_a": None,
                    "crossed_b": None,
                    "line_speed_kmh": None,
                    "smoothed_speed_kmh": 0.0,
                    "still_frames_count": 0,
                }

            v_info = self.vehicle_data[tracker_id]
            history = v_info["history"]

            # 2. Ventana temporal con Stride (5-6 frames ~ 180ms)
            # Evita amplificar x30 el ruido cuadro a cuadro adyacente (dt=0.033s)
            stride = min(len(history), max(4, int(self.fps * 0.20)))
            instant_speed_kmh = 0.0

            if stride >= 3:
                past_item = history[-stride]
                past_frame, past_x, past_y = past_item[0], past_item[1], past_item[2]
                past_ts = past_item[4] if len(past_item) > 4 else None

                delta_frames = frame_idx - past_frame
                if delta_frames > 0:
                    if now_ts is not None and past_ts is not None and (now_ts - past_ts) > 0.01:
                        dt = now_ts - past_ts
                    else:
                        dt = delta_frames / self.fps

                    dist_px = float(np.hypot(ref_x - past_x, ref_y - past_y))

                    # 3. FILTRO DE ZONA MUERTA (DEADBAND / ZERO-MOTION):
                    # Si el desplazamiento está por debajo del ruido de detección, es exactamente 0.0 km/h
                    if dist_px >= min_motion_px:
                        dist_meters = dist_px / effective_px_per_m
                        calculated_speed = (dist_meters / dt) * 3.6
                        if calculated_speed >= min_speed_kmh:
                            instant_speed_kmh = calculated_speed

            # Capping fisiológico para personas caminando/corriendo (máximo 25 km/h)
            if is_person and instant_speed_kmh > 25.0:
                instant_speed_kmh = 25.0

            # 4. Histéresis y decaimiento inmediato a cero
            if instant_speed_kmh == 0.0:
                v_info["still_frames_count"] += 1
                if v_info["still_frames_count"] >= 3 or v_info["smoothed_speed_kmh"] < 2.5:
                    v_info["smoothed_speed_kmh"] = 0.0
                else:
                    v_info["smoothed_speed_kmh"] *= 0.45
            else:
                v_info["still_frames_count"] = 0
                alpha = 0.35
                v_info["smoothed_speed_kmh"] = (
                    alpha * instant_speed_kmh + (1 - alpha) * v_info["smoothed_speed_kmh"]
                )

            # Si la velocidad suavizada resultante es residual (< 1.0 km/h), forzar a 0.0
            if v_info["smoothed_speed_kmh"] < 1.0:
                v_info["smoothed_speed_kmh"] = 0.0

            history.append((frame_idx, ref_x, ref_y, v_info["smoothed_speed_kmh"], now_ts))

            # 5. Detección de Desaceleración Crítica (Frenados / Colisiones)
            # CRÍTICO: Exclusivo para VEHÍCULOS. Una persona quieta o sentándose NUNCA es un choque.
            if not is_person:
                window_size = max(4, int(self.fps * 0.5))
                if len(history) >= window_size:
                    past_item_w = history[-window_size]
                    past_frame, past_speed = past_item_w[0], past_item_w[3]
                    curr_frame, curr_speed = history[-1][0], history[-1][3]
                    past_ts_w = past_item_w[4] if len(past_item_w) > 4 else None

                    if now_ts is not None and past_ts_w is not None and (now_ts - past_ts_w) > 0.01:
                        dt = now_ts - past_ts_w
                    else:
                        dt = (curr_frame - past_frame) / self.fps

                    delta_v = curr_speed - past_speed

                    is_sudden_drop = delta_v <= -self.critical_decel_kmh
                    is_high_speed_stop = (
                        past_speed >= settings.STOPPED_AFTER_SPEED_THRESHOLD_KMH
                        and curr_speed < 8.0
                    )

                    if (is_sudden_drop or is_high_speed_stop) and dt <= 0.6:
                        anomaly = KinematicAnomaly(
                            tracker_id=int(tracker_id),
                            frame_idx=frame_idx,
                            initial_speed_kmh=past_speed,
                            final_speed_kmh=curr_speed,
                            delta_v=delta_v,
                            delta_t_seconds=dt,
                            bbox=bbox,
                        )
                        anomalies.append(anomaly)

        return tracked_detections, anomalies

    def get_speed(self, tracker_id: int) -> float:
        """Retorna la velocidad actual estimada en km/h del vehículo o entidad."""
        if tracker_id in self.vehicle_data:
            return self.vehicle_data[tracker_id]["smoothed_speed_kmh"]
        return 0.0

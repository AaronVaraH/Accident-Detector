import logging
import time
from typing import List, Optional
import numpy as np
import supervision as sv

from config import settings
from src.i18n import i18n
from src.kinematics import KinematicAnomaly

logger = logging.getLogger(__name__)


class IncidentEvent:
    """Representa un siniestro vial confirmado listo para enriquecimiento y despacho."""

    def __init__(
        self,
        incident_type: str,
        frame_idx: int,
        timestamp: float,
        description: str,
        title: str = "",
        subtitle: str = "",
        kinematic_anomaly: Optional[KinematicAnomaly] = None,
        fire_detections: Optional[sv.Detections] = None,
        frame_snapshot: Optional[np.ndarray] = None,
    ):
        self.incident_type = incident_type
        self.frame_idx = frame_idx
        self.timestamp = timestamp
        self.description = description
        self.title = title or incident_type.replace("_", " ").upper()
        self.subtitle = subtitle or description
        self.kinematic_anomaly = kinematic_anomaly
        self.fire_detections = fire_detections
        self.frame_snapshot = frame_snapshot

    def to_dict(self) -> dict:
        return {
            "incident_type": self.incident_type,
            "title": self.title,
            "subtitle": self.subtitle,
            "frame_idx": self.frame_idx,
            "timestamp": self.timestamp,
            "description": self.description,
            "vehicle_id": self.kinematic_anomaly.tracker_id if self.kinematic_anomaly else None,
            "delta_v": self.kinematic_anomaly.delta_v if self.kinematic_anomaly else None,
            "has_fire": bool(self.fire_detections and any(cid == 1 for cid in self.fire_detections.class_id)),
            "has_smoke": bool(self.fire_detections and any(cid == 0 for cid in self.fire_detections.class_id)),
        }

    def __str__(self) -> str:
        return f"🚨 [{i18n.get('incidents_count')}] {self.title}: {self.description}"


class IncidentRuleEngine:
    """
    Motor de reglas para correlacionar anomalías de cinemática (frenado violento / impacto)
    con presencia de fuego y/o humo sostenido (N frames consecutivos).
    Distingue de forma precisa y 100% independiente entre humo, fuego o eventos combinados.
    """

    def __init__(
        self,
        cooldown_seconds: float = settings.INCIDENT_COOLDOWN_SECONDS,
        fire_persistence_frames: int = settings.CONSECUTIVE_FIRE_FRAMES_REQUIRED,
        smoke_persistence_frames: Optional[int] = None,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.fire_persistence_frames = fire_persistence_frames
        self.smoke_persistence_frames = (
            smoke_persistence_frames
            if smoke_persistence_frames is not None
            else fire_persistence_frames
        )

        self._consecutive_fire_count = 0
        self._consecutive_smoke_count = 0
        self._last_alert_time = 0.0

    def evaluate(
        self,
        frame_idx: int,
        kinematic_anomalies: List[KinematicAnomaly],
        fire_detections: Optional[sv.Detections],
        frame: Optional[np.ndarray] = None,
    ) -> Optional[IncidentEvent]:
        """
        Evalúa el estado del frame actual y determina si se declara un siniestro.
        """
        current_time = time.time()

        # 1. Contabilizar persistencia temporal separada para fuego (1) y humo (0)
        has_fire_now = False
        has_smoke_now = False
        if fire_detections is not None and len(fire_detections) > 0 and fire_detections.class_id is not None:
            has_fire_now = any(cid == 1 for cid in fire_detections.class_id)
            has_smoke_now = any(cid == 0 for cid in fire_detections.class_id)

        if has_fire_now:
            self._consecutive_fire_count += 1
        else:
            self._consecutive_fire_count = 0

        if has_smoke_now:
            self._consecutive_smoke_count += 1
        else:
            self._consecutive_smoke_count = 0

        fire_confirmed = self._consecutive_fire_count >= self.fire_persistence_frames
        smoke_confirmed = self._consecutive_smoke_count >= self.smoke_persistence_frames

        # 2. Verificar Cooldown para no saturar con el mismo evento
        if (current_time - self._last_alert_time) < self.cooldown_seconds:
            return None

        # 3. Regla 1: Colisión con Fuego y/o Humo
        if len(kinematic_anomalies) > 0 and (fire_confirmed or smoke_confirmed):
            anomaly = kinematic_anomalies[0]
            self._last_alert_time = current_time

            if fire_confirmed and smoke_confirmed:
                inc_type = "colision_con_fuego_humo"
                title = f"{i18n.get('collision_fire_title')} & {i18n.get('smoke')}"
                sub = i18n.get("collision_fire_sub", id=anomaly.tracker_id)
            elif fire_confirmed:
                inc_type = "colision_con_incendio"
                title = i18n.get("collision_fire_title")
                sub = i18n.get("collision_fire_sub", id=anomaly.tracker_id)
            else:
                inc_type = "colision_con_humo"
                title = i18n.get("collision_smoke_title")
                sub = i18n.get("collision_smoke_sub", id=anomaly.tracker_id)

            event = IncidentEvent(
                incident_type=inc_type,
                frame_idx=frame_idx,
                timestamp=current_time,
                description=f"{title}. Δv: {anomaly.delta_v:.1f} km/h.",
                title=title,
                subtitle=sub,
                kinematic_anomaly=anomaly,
                fire_detections=fire_detections,
                frame_snapshot=frame.copy() if frame is not None else None,
            )
            logger.critical(str(event))
            return event

        # 4. Regla 2: Fuego y/o Humo Sostenido en Vía (Detección Específica)
        if fire_confirmed or smoke_confirmed:
            self._last_alert_time = current_time

            if fire_confirmed and smoke_confirmed:
                inc_type = "fuego_humo_detectado"
                title = i18n.get("fire_smoke_detected_title")
                sub = i18n.get("fire_smoke_detected_sub")
                desc = f"{title}: {sub}"
            elif fire_confirmed:
                inc_type = "fuego_detectado"
                title = i18n.get("fire_detected_title")
                sub = i18n.get("fire_detected_sub")
                desc = f"{title}: {sub}"
            else:
                inc_type = "humo_detectado"
                title = i18n.get("smoke_detected_title")
                sub = i18n.get("smoke_detected_sub")
                desc = f"{title}: {sub}"

            event = IncidentEvent(
                incident_type=inc_type,
                frame_idx=frame_idx,
                timestamp=current_time,
                description=desc,
                title=title,
                subtitle=sub,
                kinematic_anomaly=None,
                fire_detections=fire_detections,
                frame_snapshot=frame.copy() if frame is not None else None,
            )
            logger.warning(str(event))
            return event

        # 5. Regla 3: Colisión o Frenado Brusco Crítico
        if len(kinematic_anomalies) > 0:
            anomaly = kinematic_anomalies[0]
            self._last_alert_time = current_time
            title = i18n.get("critical_brake_title")
            sub = i18n.get("critical_brake_sub", id=anomaly.tracker_id)
            desc = (
                f"{sub} ({anomaly.initial_speed_kmh:.1f} -> {anomaly.final_speed_kmh:.1f} km/h, "
                f"Δv: {anomaly.delta_v:.1f} km/h en {anomaly.delta_t_seconds:.2f}s)"
            )
            event = IncidentEvent(
                incident_type="frenado_critico_colision",
                frame_idx=frame_idx,
                timestamp=current_time,
                description=desc,
                title=title,
                subtitle=sub,
                kinematic_anomaly=anomaly,
                fire_detections=None,
                frame_snapshot=frame.copy() if frame is not None else None,
            )
            logger.warning(str(event))
            return event

        return None

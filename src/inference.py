import logging
from pathlib import Path
from typing import List, Optional, Tuple
import cv2
import numpy as np
import supervision as sv
from ultralytics import YOLO

from config import settings
from src.i18n import i18n

logger = logging.getLogger(__name__)


class VehicleDetector:
    """
    Detector de vehículos optimizado para 30+ FPS en tiempo real.
    Utiliza YOLOv8 local con filtrado estricto de clases COCO (autos, motos, buses, camiones),
    evitando falsos positivos de personas o peatones si no está habilitado.
    """

    def __init__(
        self,
        conf_threshold: float = settings.CONFIDENCE_THRESHOLD,
        model_path: str = settings.FALLBACK_VEHICLE_MODEL,
        detect_persons: bool = False,
    ):
        self.conf_threshold = conf_threshold
        self.detect_persons = detect_persons
        self.classes = [0, 2, 3, 5, 7] if detect_persons else settings.VEHICLE_CLASS_IDS
        logger.info(f"Cargando detector vehicular YOLOv8 (detectar personas={detect_persons})...")
        self.yolo_model = YOLO(model_path)

    def detect(self, frame) -> sv.Detections:
        """Inferencia de alta velocidad sobre el frame actual."""
        results = self.yolo_model(
            source=frame,
            conf=self.conf_threshold,
            classes=self.classes,
            device=settings.DEVICE,
            imgsz=480,
            verbose=False,
        )[0]

        detections = sv.Detections.from_ultralytics(results)
        if len(detections) > 0 and detections.class_id is not None:
            detections.data["raw_class_name"] = [
                results.names[int(cls_id)].lower() for cls_id in detections.class_id
            ]
            detections.data["class_name"] = [
                i18n.get_class_name(results.names[int(cls_id)])
                for cls_id in detections.class_id
            ]
        return detections


class FireDetector:
    """
    Detector inteligente de fuego y humo en tiempo real con arquitectura dual:
    1. Modelo Primario (YOLOv8 'fire_smoke.pt'): Especializado en incendios vehiculares, conatos,
       llamas directas y columnas/penachos de humo.
       - Humo calibrado (>= 0.25 por defecto) para detectar humo tenue y en desarrollo sin retrasos.
       - Fuego altamente sensible (>= 0.15) para captar llamas vivas en cualquier iluminación.
    2. Localizador de Llamas Focalizadas ('lighter_flame.onnx'):
       - Para llamas pequeñas o conatos puntuales a distancia.
    """



    @staticmethod
    def _is_human_skin_or_colorful_object(crop: np.ndarray) -> bool:
        """
        Determina si una caja candidata a humo es en realidad una mano humana en movimiento
        rápido (motion blur) o ropa/objeto de alta saturación.
        El humo real es acromático (gris/blanco/cenizo con muy baja saturación).
        """
        if crop.size == 0 or crop.shape[0] < 6 or crop.shape[1] < 6:
            return False

        # 1. Filtro YCrCb para tono de piel humana
        ycrcb = cv2.cvtColor(crop, cv2.COLOR_BGR2YCrCb)
        skin_mask = (
            (ycrcb[:, :, 1] >= 133)
            & (ycrcb[:, :, 1] <= 173)
            & (ycrcb[:, :, 2] >= 77)
            & (ycrcb[:, :, 2] <= 127)
        )
        skin_ratio = np.count_nonzero(skin_mask) / float(crop.shape[0] * crop.shape[1])
        # Solo descartar si la mayor parte del recorte es piel humana pura sin presencia de humo
        if skin_ratio >= 0.55:
            return True  # Es piel humana (mano/brazo/cara) pura

        # 2. Filtro HSV para alta saturación (ropa u objetos plásticos intensos sin humo)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        high_sat_ratio = np.count_nonzero(sat > 110) / float(crop.shape[0] * crop.shape[1])
        if high_sat_ratio >= 0.45:
            return True  # Ropa o plástico de saturación extrema, no humo

        return False

    @staticmethod
    def _is_valid_flame_chroma(crop: np.ndarray) -> bool:
        """
        Determina si una región candidata a fuego tiene el perfil cromático y térmico de una llama real
        (alta luminancia, gradiente cálido) tolerante a la compresión JPEG de cámaras móviles y navegadores.
        """
        if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 4:
            return False

        b, g, r = cv2.split(crop)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hue = hsv[:, :, 0]
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]

        # 1. Región cálida incandescente/brillante
        incandescent_mask = (val >= 180) & (r >= 150) & (g >= 60)
        incandescent_ratio = np.count_nonzero(incandescent_mask) / float(crop.shape[0] * crop.shape[1])

        # 2. Píxeles cálidos de espectro de llama (amarillo/naranja/rojo)
        warm_flame_mask = (
            (r.astype(np.int16) - b.astype(np.int16) >= 10)
            & (r >= 110)
            & (sat >= 15)
            & ((hue <= 45) | (hue >= 150))
        )
        warm_ratio = np.count_nonzero(warm_flame_mask) / float(crop.shape[0] * crop.shape[1])

        # Descarte de objetos neutros (ropa/pared blanca) sin presencia de espectro térmico
        white_glare_mask = (
            (val >= 210)
            & (np.abs(r.astype(np.int16) - b.astype(np.int16)) < 15)
            & (sat < 20)
        )
        white_count = np.count_nonzero(white_glare_mask)
        warm_count = np.count_nonzero(warm_flame_mask)

        # Si no hay absolutamente ningún píxel cálido ni núcleo incandescente, descartar
        if warm_count == 0 and incandescent_ratio < 0.01:
            return False

        # Si es un objeto completamente blanco plano sin gradiente cálido en bordes
        if warm_count < 2 and white_count > 15:
            return False

        return warm_ratio >= 0.015 or incandescent_ratio >= 0.008

    def __init__(
        self,
        model_path: str = settings.FIRE_SMOKE_MODEL_PATH,
        lighter_model_path: str = settings.LIGHTER_FLAME_MODEL_PATH,
        fire_conf: float = 0.12,
        smoke_conf: float = 0.18,
        enable_focal_lighter: bool = True,
    ):
        self.fire_conf = fire_conf
        self.smoke_conf = smoke_conf
        self.enable_focal_lighter = enable_focal_lighter
        self.model_path = model_path
        self.lighter_model_path = lighter_model_path

        if not Path(model_path).exists():
            logger.warning(f"⚠️ No se encontró el modelo de fuego en {model_path}. Detección de fuego desactivada temporalmente.")
            self.model = None
        else:
            try:
                logger.info(f"Cargando detector de fuego/humo primario desde: {model_path}")
                self.model = YOLO(model_path)
            except Exception as e:
                logger.error(f"Error cargando modelo de fuego {model_path}: {e}")
                self.model = None

        self.lighter_model = None
        if Path(lighter_model_path).exists():
            try:
                logger.info(f"Cargando modelo focalizado de llamas desde: {lighter_model_path}")
                self.lighter_model = YOLO(lighter_model_path, task="detect")
                _ = self.lighter_model(np.zeros((64, 64, 3), dtype=np.uint8), verbose=False)
            except Exception as e:
                logger.warning(f"No se pudo cargar el modelo focalizado: {e}")

        logger.info(f"Detector de fuego listo. Filtros: Fuego >= {self.fire_conf}, Humo >= {self.smoke_conf}")

    def detect(self, frame) -> Tuple[sv.Detections, List[str]]:
        """
        Ejecuta la inferencia dual con rechazo de falsos positivos ópticos:
        - Descarta motion blur de manos mediante análisis cromático de piel humana.
        - Descarta reflejos de luz blanca en objetos claros mediante validación térmica (R vs B).
        """
        if self.model is None:
            return sv.Detections.empty(), []

        h, w = frame.shape[:2]
        boxes_list = []
        conf_list = []
        labels_list = []
        class_ids_list = []

        # 1. Inferencia del Modelo Primario
        min_conf = min(self.fire_conf, self.smoke_conf)
        results = self.model(
            source=frame,
            conf=min_conf,
            device=settings.DEVICE,
            imgsz=480,
            verbose=False,
        )[0]

        for b in results.boxes:
            cls_name = results.names[int(b.cls[0])].lower()
            conf = float(b.conf[0])
            bx1, by1, bx2, by2 = [max(0, round(x)) for x in b.xyxy[0].tolist()]
            bx1, by1 = min(w - 1, bx1), min(h - 1, by1)
            bx2, by2 = min(w, max(bx1 + 1, bx2)), min(h, max(by1 + 1, by2))
            crop_cand = frame[by1:by2, bx1:bx2]

            # Filtro para HUMO: Rechaza motion blur de manos y ropa
            if cls_name == "smoke" and conf >= self.smoke_conf:
                if self._is_human_skin_or_colorful_object(crop_cand):
                    logger.debug(f"Descartado falso humo por motion blur de piel (conf: {conf:.2f})")
                    continue

                boxes_list.append([bx1, by1, bx2, by2])
                conf_list.append(conf)
                labels_list.append(f"HUMO ({conf:.2f})")
                class_ids_list.append(0)

            # Filtro para FUEGO: Rechaza ropa naranja/roja y reflejos de luz
            elif cls_name == "fire" and conf >= self.fire_conf:
                if not self._is_valid_flame_chroma(crop_cand):
                    logger.debug(f"Descartado falso fuego por falta de incandescencia (conf: {conf:.2f})")
                    continue

                boxes_list.append([bx1, by1, bx2, by2])
                conf_list.append(conf)
                labels_list.append(f"FUEGO ({conf:.2f})")
                class_ids_list.append(1)

        # 2. Localizador de Llamas y Encendedores (ONNX especializado en cuerpo y llama)
        has_fire = any(cid == 1 for cid in class_ids_list)
        if not has_fire and self.enable_focal_lighter and self.lighter_model is not None:
            l_conf_thresh = min(0.25, self.fire_conf)
            l_res = self.lighter_model(frame, conf=l_conf_thresh, imgsz=640, verbose=False)[0]
            for lb in l_res.boxes:
                lname = self.lighter_model.names[int(lb.cls[0])].lower()
                lconf = float(lb.conf[0])
                if lname in ["ates", "fire"] and lconf >= l_conf_thresh:
                    bx1, by1, bx2, by2 = [max(0, round(x)) for x in lb.xyxy[0].tolist()]
                    bx1, by1 = min(w - 1, bx1), min(h - 1, by1)
                    bx2, by2 = min(w, max(bx1 + 1, bx2)), min(h, max(by1 + 1, by2))
                    flame_patch = frame[by1:by2, bx1:bx2]
                    if not self._is_valid_flame_chroma(flame_patch):
                        continue

                    boxes_list.append([bx1, by1, bx2, by2])
                    conf_list.append(lconf)
                    labels_list.append(f"FUEGO ({lconf:.2f})")
                    class_ids_list.append(1)
                    logger.info(f"🔥 Llama detectada por modelo de encendedor/fuego: {lconf:.2f}")

        if len(boxes_list) == 0:
            return sv.Detections.empty(), []

        # NMS / Fusión para evitar cajas duplicadas en la misma llama
        detections = sv.Detections(
            xyxy=np.array(boxes_list, dtype=np.float32),
            confidence=np.array(conf_list, dtype=np.float32),
            class_id=np.array(class_ids_list, dtype=int),
        )
        detections = detections.with_nms(threshold=0.3)

        # Reconstruir etiquetas correspondientes a las cajas filtradas según idioma actual
        final_labels = []
        raw_names = []
        for conf, cls_id in zip(detections.confidence, detections.class_id):
            raw = "smoke" if cls_id == 0 else "fire"
            name = i18n.get("smoke") if cls_id == 0 else i18n.get("fire")
            raw_names.append(raw)
            final_labels.append(f"{name} ({conf:.2f})")

        detections.data["raw_class_name"] = raw_names
        detections.data["class_name"] = [
            i18n.get("smoke") if cid == 0 else i18n.get("fire") for cid in detections.class_id
        ]

        return detections, final_labels



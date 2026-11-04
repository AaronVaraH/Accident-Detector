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
            imgsz=384,
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
        Determina si una caja candidata a humo es puramente una mano humana en movimiento
        rápido (motion blur) o ropa/objeto sin ninguna presencia de humo.
        Si la persona sostiene una hoja/papel quemándose, la caja contiene la mano Y el humo:
        en ese caso NO se descarta porque hay humo real presente (área acromática difusa).
        """
        if crop.size == 0 or crop.shape[0] < 6 or crop.shape[1] < 6:
            return False

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]

        # Verificar si hay una nube acromática compatible con humo (baja saturación, brillo medio-alto)
        smoke_pixels = (sat <= 45) & (val >= 50) & (val <= 245)
        smoke_ratio = np.count_nonzero(smoke_pixels) / float(crop.shape[0] * crop.shape[1])

        # Si hay al menos un 15% de nube acromática difusa (humo visible), NO descartar aunque esté la mano presente
        if smoke_ratio >= 0.15:
            return False

        # 1. Filtro YCrCb para tono de piel humana pura sin humo
        ycrcb = cv2.cvtColor(crop, cv2.COLOR_BGR2YCrCb)
        skin_mask = (
            (ycrcb[:, :, 1] >= 133)
            & (ycrcb[:, :, 1] <= 173)
            & (ycrcb[:, :, 2] >= 77)
            & (ycrcb[:, :, 2] <= 127)
        )
        skin_ratio = np.count_nonzero(skin_mask) / float(crop.shape[0] * crop.shape[1])
        if skin_ratio >= 0.70:
            return True  # Es piel humana pura sin dispersión de humo

        # 2. Filtro HSV para alta saturación pura (ropa u objeto plástico sin humo)
        high_sat_ratio = np.count_nonzero(sat > 110) / float(crop.shape[0] * crop.shape[1])
        if high_sat_ratio >= 0.65:
            return True  # Ropa o plástico de saturación extrema sin humo

        return False

    @staticmethod
    def _is_valid_flame_chroma(crop: np.ndarray) -> bool:
        """
        Determina si una región candidata a fuego tiene el perfil cromático y térmico de una llama real
        (alta luminancia, gradiente cálido, halo de combustión) y descarta reflejos especulares,
        luces blancas sobreexpuestas, lámparas uniformes y destellos de faros/pantallas.
        """
        if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 4:
            return False

        b, g, r = cv2.split(crop)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hue = hsv[:, :, 0]
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]

        total_pixels = float(crop.shape[0] * crop.shape[1])

        # 1. Píxeles de halo de combustión activo (Rojo/Naranja/Amarillo intenso característico de fuego vivo)
        # R supera a B y G, con saturación y tono de combustión
        combustion_mask = (
            (r.astype(np.int16) - b.astype(np.int16) >= 40)
            & (r.astype(np.int16) - g.astype(np.int16) >= 12)
            & (r >= 135)
            & (sat >= 35)
            & ((hue <= 30) | (hue >= 165))
        )
        combustion_ratio = np.count_nonzero(combustion_mask) / total_pixels

        # 2. Píxeles cálidos incandescentes (centro de llama ámbar/amarillo brillante)
        warm_core_mask = (
            (r.astype(np.int16) - b.astype(np.int16) >= 25)
            & (r >= 160)
            & (g >= 90)
            & (sat >= 20)
            & (hue <= 35)
        )
        warm_core_ratio = np.count_nonzero(warm_core_mask) / total_pixels

        # 3. Detección de reflejos especulares / luces blancas / sobreexposición plana
        # Reflejo desaturado donde R, G y B son muy similares (blanco/gris plano de foco o brillo)
        white_glare_mask = (
            (val >= 195)
            & (np.abs(r.astype(np.int16) - b.astype(np.int16)) < 25)
            & (sat < 25)
        )
        glare_ratio = np.count_nonzero(white_glare_mask) / total_pixels

        # Si el recorte está dominado por reflejo blanco/desaturado sin suficiente combustión
        if glare_ratio >= 0.40 and combustion_ratio < 0.08:
            return False

        # Si es un parche plano sin gradiente térmico espacial (lámpara, foco o superficie uniforme)
        # Las llamas reales tienen varianza espacial por turbulencia, excepto si es un recorte puro
        # de llama roja/naranja extrema (R - G >= 70 y R - B >= 100).
        std_r = float(np.std(r))
        std_g = float(np.std(g))
        if std_r < 8.0 and std_g < 8.0:
            mean_rg = float(np.mean(r.astype(np.int16) - g.astype(np.int16)))
            mean_rb = float(np.mean(r.astype(np.int16) - b.astype(np.int16)))
            if mean_rg < 70 or mean_rb < 100:
                return False  # Luz artificial o superficie plana uniforme

        # Para ser considerada llama real:
        # Debe tener un porcentaje sólido de combustión cálida o núcleo cálido con halo
        if combustion_ratio >= 0.04:
            return True
        if warm_core_ratio >= 0.10 and combustion_ratio >= 0.015:
            return True

        return False

    def __init__(
        self,
        model_path: str = settings.FIRE_SMOKE_MODEL_PATH,
        lighter_model_path: str = settings.LIGHTER_FLAME_MODEL_PATH,
        fire_conf: float = settings.DEFAULT_FIRE_CONF,
        smoke_conf: float = settings.DEFAULT_SMOKE_CONF,
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
        - Descarta motion blur de manos y ropa pura, pero conserva humo sostenido con manos.
        - Descarta reflejos de luz blanca, lámparas y focos mediante validación espectral y gradiente térmico.
        - Aplica realce adaptativo local CLAHE en fondos claros para resaltar humo translúcido tenue.
        """
        if self.model is None:
            return sv.Detections.empty(), []

        h, w = frame.shape[:2]
        boxes_list = []
        conf_list = []
        labels_list = []
        class_ids_list = []

        # Si el fondo promedio es claro, el humo blanco/gris pierde contraste con el fondo.
        # CLAHE adaptativo local permite revelar la textura y contornos del humo sobre fondos claros.
        inference_frame = frame
        mean_val = cv2.mean(frame)[:3]
        avg_lum = (mean_val[0] + mean_val[1] + mean_val[2]) / 3.0
        if avg_lum >= 125:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l_ch, a_ch, b_ch = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
            cl = clahe.apply(l_ch)
            inference_frame = cv2.cvtColor(cv2.merge((cl, a_ch, b_ch)), cv2.COLOR_LAB2BGR)

        # 1. Inferencia del Modelo Primario
        min_conf = min(self.fire_conf, self.smoke_conf)
        results = self.model(
            source=inference_frame,
            conf=min_conf,
            device=settings.DEVICE,
            imgsz=384,
            verbose=False,
        )[0]

        for b in results.boxes:
            cls_name = results.names[int(b.cls[0])].lower()
            conf = float(b.conf[0])
            bx1, by1, bx2, by2 = [max(0, round(x)) for x in b.xyxy[0].tolist()]
            bx1, by1 = min(w - 1, bx1), min(h - 1, by1)
            bx2, by2 = min(w, max(bx1 + 1, bx2)), min(h, max(by1 + 1, by2))
            crop_cand = frame[by1:by2, bx1:bx2]

            # Filtro para HUMO: Admite humo tenue sobre fondo claro y con manos presentes
            if cls_name == "smoke" and conf >= self.smoke_conf:
                if self._is_human_skin_or_colorful_object(crop_cand):
                    logger.debug(f"Descartado falso humo por motion blur de piel pura (conf: {conf:.2f})")
                    continue

                boxes_list.append([bx1, by1, bx2, by2])
                conf_list.append(conf)
                labels_list.append(f"HUMO ({conf:.2f})")
                class_ids_list.append(0)

            # Filtro para FUEGO: Rechaza luces fuertes, reflejos y ropa
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
            l_conf_thresh = max(0.30, self.fire_conf)
            l_res = self.lighter_model(frame, conf=l_conf_thresh, imgsz=384, verbose=False)[0]
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



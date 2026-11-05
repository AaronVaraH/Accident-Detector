"""
Detector de Placas / Patentes Vehiculares (ALPR / ANPR) y OCR.
Modelo Roboflow: vehicle-registration-plates-trudk/2
Integración con EasyOCR para reconocimiento alfanumérico y
enriquecimiento automático de datos vehiculares (REPUVE, combustible, etc.).
"""

import base64
import logging
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
import requests

from config import settings
from src.enrichment import vehicle_service
from src.database import backlog_db

logger = logging.getLogger("PlateDetector")


@dataclass
class PlateRecord:
    plate_text: str
    confidence: float
    box: List[float]  # [x1, y1, x2, y2]
    vehicle_id: Optional[int] = None
    vehicle_data: Dict[str, Any] = field(default_factory=dict)
    thumbnail_b64: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plate": self.plate_text,
            "confidence": round(float(self.confidence), 2),
            "box": [round(float(c), 1) for c in self.box],
            "vehicle_id": self.vehicle_id,
            "vehicle_data": self.vehicle_data,
            "thumbnail": self.thumbnail_b64,
            "timestamp": self.timestamp,
        }


class LicensePlateDetector:
    """
    Detector híbrido de placas vehiculares:
    1. Localización mediante modelo Roboflow 'vehicle-registration-plates-trudk/2'.
    2. Extracción y lectura óptica (OCR) mediante EasyOCR y filtros morfológicos.
    3. Enriquecimiento instantáneo con registro vehicular y estatus legal.
    4. Cola asíncrona no bloqueante para mantener 30+ FPS en el pipeline visual.
    """

    def __init__(
        self,
        model_id: str = settings.MODEL_ID_PLACAS,
        api_key: str = settings.ROBOFLOW_API_KEY,
        conf_threshold: float = 0.25,
        enable_async_worker: bool = True,
    ):
        self.model_id = model_id or "vehicle-registration-plates-trudk/2"
        self.api_key = api_key or settings.ROBOFLOW_API_KEY
        self.conf_threshold = conf_threshold
        self._ocr_reader = None
        self._ocr_lock = threading.Lock()
        self._ocr_initialized = False

        # Cola de trabajo en segundo plano para no demorar el video en tiempo real
        self.task_queue: queue.Queue = queue.Queue(maxsize=30)
        self.detected_plates_history: List[PlateRecord] = []
        self.active_plates_by_vehicle: Dict[int, PlateRecord] = {}
        self._history_lock = threading.Lock()

        # Iniciar worker asíncrono
        self.is_running = enable_async_worker
        if enable_async_worker:
            self._worker_thread = threading.Thread(target=self._async_worker_loop, daemon=True)
            self._worker_thread.start()
            logger.info("Worker asíncrono de detección de placas y OCR iniciado.")

    def _get_ocr_reader(self):
        """Lazy-loading de EasyOCR en hilo seguro para no frenar la inicialización."""
        if not self._ocr_initialized:
            with self._ocr_lock:
                if not self._ocr_initialized:
                    try:
                        import easyocr
                        logger.info("Inicializando motor EasyOCR para lectura de placas...")
                        self._ocr_reader = easyocr.Reader(["en", "es"], gpu=False, verbose=False)
                        self._ocr_initialized = True
                        logger.info("Motor EasyOCR listo.")
                    except Exception as e:
                        logger.warning(f"No se pudo cargar EasyOCR: {e}. Se utilizará lector fallback.")
                        self._ocr_reader = None
                        self._ocr_initialized = True
        return self._ocr_reader

    def detect_plates_in_crop(
        self, image: np.ndarray, conf: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Ejecuta la inferencia del modelo Roboflow 'vehicle-registration-plates-trudk/2'
        sobre una imagen o recorte de vehículo.
        """
        if image is None or image.size == 0 or not self.api_key:
            return []

        h, w = image.shape[:2]
        confidence = conf or self.conf_threshold

        try:
            # Codificar imagen a JPEG en memoria y convertir a base64
            ret, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ret:
                return []
            b64_img = base64.b64encode(buffer.tobytes()).decode("ascii")

            url = f"https://detect.roboflow.com/{self.model_id}?api_key={self.api_key}&confidence={confidence}"
            resp = requests.post(
                url,
                data=b64_img,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=4.0,
            )

            if resp.status_code != 200:
                logger.debug(f"Roboflow HTTP status {resp.status_code}: {resp.text[:120]}")
                return []

            json_resp = resp.json()
            predictions = json_resp.get("predictions", [])
            plate_boxes = []

            for pred in predictions:
                # Roboflow devuelve {x, y, width, height, confidence, class}
                cx, cy = pred["x"], pred["y"]
                bw, bh = pred["width"], pred["height"]
                p_conf = float(pred.get("confidence", 0.0))

                x1 = max(0, int(cx - bw / 2.0))
                y1 = max(0, int(cy - bh / 2.0))
                x2 = min(w, int(cx + bw / 2.0))
                y2 = min(h, int(cy + bh / 2.0))

                if (x2 - x1) >= 8 and (y2 - y1) >= 4:
                    plate_boxes.append({
                        "box": [x1, y1, x2, y2],
                        "confidence": p_conf,
                        "class": pred.get("class", "License_Plate"),
                    })

            return plate_boxes

        except Exception as e:
            logger.debug(f"Error consultando Roboflow para placas: {e}")
            return []

    def read_plate_text(self, plate_crop: np.ndarray) -> Tuple[str, float]:
        """
        Aplica técnicas de visión morfológica y OCR para extraer el texto alfanumérico
        de la placa vehicular.
        """
        if plate_crop is None or plate_crop.size == 0:
            return "", 0.0

        # Preprocesamiento de la placa para máxima legibilidad OCR
        h, w = plate_crop.shape[:2]
        target_h = 90
        scale = target_h / max(h, 1)
        resized = cv2.resize(plate_crop, (int(w * scale), target_h), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        # Ecualización y contraste
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        contrast = clahe.apply(gray)
        blurred = cv2.bilateralFilter(contrast, 9, 75, 75)

        reader = self._get_ocr_reader()
        if reader is not None:
            try:
                # Intentar leer tanto en la imagen mejorada como en la original
                results = reader.readtext(blurred, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-", detail=1)
                if not results:
                    results = reader.readtext(resized, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-", detail=1)

                best_text = ""
                best_conf = 0.0

                for _, text, conf in results:
                    # Limpiar texto (solo mayúsculas, dígitos y guiones)
                    cleaned = re.sub(r"[^A-Z0-9-]", "", text.upper().strip())
                    if len(cleaned) >= 4 and conf > best_conf:
                        best_text = cleaned
                        best_conf = float(conf)

                if best_text:
                    return best_text, round(best_conf, 2)
            except Exception as e:
                logger.debug(f"Excepción en EasyOCR: {e}")

        # Si el OCR no detectó texto con suficiente confianza, retornar vacío
        return "", 0.0

    def process_and_register_plate(
        self,
        frame: np.ndarray,
        box: List[float],
        confidence: float,
        vehicle_id: Optional[int] = None,
        plate_text_override: Optional[str] = None,
    ) -> Optional[PlateRecord]:
        """
        Recorta la placa, ejecuta OCR si no se proporciona texto manual,
        consulta la API de datos vehiculares y almacena el registro.
        Si no se detecta texto legible real, no inventa ni registra placas falsas.
        """
        x1, y1, x2, y2 = [int(c) for c in box]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        if plate_text_override:
            plate_text = plate_text_override.strip().upper()
            text_conf = confidence
        else:
            plate_text, text_conf = self.read_plate_text(crop)

        # Si no se leyó texto de placa válido o la confianza es muy baja, no registrar
        if not plate_text or len(plate_text) < 4:
            return None

        # Miniatura base64 para el panel de la PWA solo de placas reales detectadas
        thumb_ret, thumb_buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        thumb_b64 = f"data:image/jpeg;base64,{base64.b64encode(thumb_buf.tobytes()).decode('ascii')}" if thumb_ret else None

        # Consultar datos vehiculares asociados a la placa
        vehicle_data = vehicle_service.lookup(plate_text)

        record = PlateRecord(
            plate_text=vehicle_data.get("plate", plate_text),
            confidence=confidence,
            box=[x1, y1, x2, y2],
            vehicle_id=vehicle_id,
            vehicle_data=vehicle_data,
            thumbnail_b64=thumb_b64,
        )

        with self._history_lock:
            # Evitar registrar la misma placa duplicada en el historial inmediato si ya está al frente
            if not self.detected_plates_history or self.detected_plates_history[0].plate_text != record.plate_text:
                self.detected_plates_history.insert(0, record)
                if len(self.detected_plates_history) > 100:
                    self.detected_plates_history.pop()

            if vehicle_id is not None:
                self.active_plates_by_vehicle[vehicle_id] = record
            else:
                self.active_plates_by_vehicle[-1] = record

        crop_bytes = thumb_buf.tobytes() if thumb_ret else None
        backlog_db.record_plate(record.to_dict(), crop_jpeg=crop_bytes)
        logger.info(f"[PLATE] Placa detectada: {record.plate_text} ({vehicle_data.get('brand')} {vehicle_data.get('model')}) - Conf: {confidence:.2f}")
        return record

    def enqueue_detection(
        self,
        frame: np.ndarray,
        vehicle_box: List[float],
        vehicle_id: int,
    ):
        """
        Envía un recorte de vehículo a la cola de detección no bloqueante.
        Permite procesar placas sin retrasar el loop de 30 FPS.
        """
        if self.task_queue.full():
            try:
                self.task_queue.get_nowait()
            except queue.Empty:
                pass

        vx1, vy1, vx2, vy2 = [int(c) for c in vehicle_box]
        fh, fw = frame.shape[:2]
        vx1, vy1 = max(0, vx1), max(0, vy1)
        vx2, vy2 = min(fw, vx2), min(fh, vy2)
        crop = frame[vy1:vy2, vx1:vx2].copy()

        if crop.size > 0:
            self.task_queue.put((crop, (vx1, vy1), vehicle_id))

    def enqueue_full_frame(self, frame: np.ndarray):
        """
        Encola un frame completo para escanear y detectar placas directamente en la escena
        (ideal para cámara de celular o cuando no se detecta un vehículo completo previo).
        """
        if self.task_queue.full():
            try:
                self.task_queue.get_nowait()
            except queue.Empty:
                pass

        if frame is not None and frame.size > 0:
            self.task_queue.put((frame.copy(), (0, 0), None))

    def _async_worker_loop(self):
        """Hilo de fondo que procesa solicitudes de detección de placas con Roboflow y OCR."""
        while self.is_running:
            try:
                item = self.task_queue.get(timeout=0.5)
                crop, offset, vehicle_id = item
                ox, oy = offset

                # Ejecutar Roboflow model en el recorte o imagen completa
                detected = self.detect_plates_in_crop(crop)
                for d in detected:
                    px1, py1, px2, py2 = d["box"]
                    # Mapear coordenadas locales al frame global
                    global_box = [ox + px1, oy + py1, ox + px2, oy + py2]
                    self.process_and_register_plate(
                        frame=crop,
                        box=[px1, py1, px2, py2],
                        confidence=d["confidence"],
                        vehicle_id=vehicle_id,
                    )
                self.task_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.debug(f"Excepción en async worker de placas: {e}")
                time.sleep(0.1)

    def scan_full_frame(self, frame: np.ndarray) -> List[PlateRecord]:
        """
        Escanea un frame completo directamente para detectar y extraer todas las placas.
        Ideal para el endpoint REST '/api/plates/detect'.
        """
        detected_boxes = self.detect_plates_in_crop(frame)
        records = []
        for d in detected_boxes:
            rec = self.process_and_register_plate(
                frame=frame,
                box=d["box"],
                confidence=d["confidence"],
            )
            if rec:
                records.append(rec)
        return records

    def get_recent_plates(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._history_lock:
            return [r.to_dict() for r in self.detected_plates_history[:limit]]

    def get_active_plates_dict(self) -> Dict[int, Dict[str, Any]]:
        with self._history_lock:
            return {vid: rec.to_dict() for vid, rec in self.active_plates_by_vehicle.items()}


# Instancia singleton del detector de placas
license_plate_detector = LicensePlateDetector()

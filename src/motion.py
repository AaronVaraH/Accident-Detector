"""
Módulo de Análisis de Movimiento Óptico y Dinámica de Escena.
Calcula en tiempo real la energía de movimiento, velocidad de cambio y contornos activos.
"""

from typing import List, Tuple
import cv2
import numpy as np


class MotionAnalyzer:
    """
    Analizador de movimiento visual ultraligero (<1.5 ms por frame).
    Detecta si la escena tiene dinamismo, movimientos rápidos o está estática.
    """

    def __init__(self, history_weight: float = 0.75, motion_threshold: int = 24):
        self.history_weight = history_weight
        self.motion_threshold = motion_threshold
        self._prev_gray = None
        self._smoothed_energy = 0.0

    def update(self, frame: np.ndarray) -> Tuple[float, List[np.ndarray]]:
        """
        Calcula la energía de movimiento (0.0 a 1.0) y retorna los contornos activos.
        """
        # Reducir resolución para cálculo ultrarrápido
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (320, 240), interpolation=cv2.INTER_NEAREST)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (11, 11), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return 0.0, []

        # Diferencia absoluta entre frames
        frame_diff = cv2.absdiff(self._prev_gray, gray)
        _, thresh = cv2.threshold(frame_diff, self.motion_threshold, 255, cv2.THRESH_BINARY)

        # Dilatar para agrupar manchas de movimiento
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thresh = cv2.dilate(thresh, kernel, iterations=1)

        # Porcentaje de píxeles en movimiento con umbral de reposo
        active_pixels = cv2.countNonZero(thresh)
        if active_pixels < 90:
            raw_energy = 0.0
        else:
            raw_energy = min(1.0, (active_pixels / (320.0 * 240.0)) * 4.0)

        # Suavizado exponencial para evitar saltos bruscos
        self._smoothed_energy = (
            self.history_weight * self._smoothed_energy + (1.0 - self.history_weight) * raw_energy
        )
        if self._smoothed_energy < 0.015:
            self._smoothed_energy = 0.0

        # Extraer contornos de movimiento principales (escalados al frame original)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        scale_x = w / 320.0
        scale_y = h / 240.0

        motion_boxes = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 100:  # Filtrar ruido menor
                x, y, bw, bh = cv2.boundingRect(cnt)
                # Escalar a resolución original
                orig_box = (
                    int(x * scale_x),
                    int(y * scale_y),
                    int((x + bw) * scale_x),
                    int((y + bh) * scale_y),
                )
                motion_boxes.append(orig_box)

        self._prev_gray = gray
        return self._smoothed_energy, motion_boxes

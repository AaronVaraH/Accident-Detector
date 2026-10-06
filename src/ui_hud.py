"""
Módulo de Interfaz Táctica HUD (Cyber-Security Video Analytics).
Renderiza una interfaz gráfica moderna, profesional y de alto impacto sobre los frames de OpenCV.
"""

import time
from typing import List, Optional, Tuple
import cv2
import numpy as np
import supervision as sv

from src.i18n import i18n


class TacticalHUD:
    """
    Renderizador HUD estilo centro de comando táctico para analítica de video en tiempo real.
    Diseñado con estética dark glassmorphism, tipografía nítida, badges de telemetría y soporte i18n.
    """

    def __init__(self, source_name: str = "0"):
        self.raw_source = str(source_name)
        self._last_pulse_time = time.time()
        self._pulse_state = True

    @property
    def source_display(self) -> str:
        if self.raw_source in ["0", "1"]:
            return i18n.get("webcam_source")
        return i18n.get("video_source")

    def draw_glass_panel(
        self,
        frame: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        bg_color: Tuple[int, int, int] = (15, 20, 28),
        alpha: float = 0.82,
    ) -> np.ndarray:
        """Dibuja un rectángulo semi-transparente estilo glassmorphism."""
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return frame

        sub_img = frame[y1:y2, x1:x2]
        rect = np.full_like(sub_img, bg_color)
        cv2.addWeighted(rect, alpha, sub_img, 1.0 - alpha, 0, sub_img)
        frame[y1:y2, x1:x2] = sub_img
        return frame

    def render_header(
        self,
        frame: np.ndarray,
        fps: float,
        frame_idx: int,
        object_count: int,
        motion_energy: float = 0.0,
        has_fire: bool = False,
    ) -> np.ndarray:
        """Renderiza la barra superior de estado y telemetría con soporte multiidioma."""
        h, w = frame.shape[:2]

        # 1. Panel de encabezado glassmorphism
        header_h = 56
        self.draw_glass_panel(frame, 0, 0, w, header_h, bg_color=(12, 16, 24), alpha=0.88)
        # Línea divisoria cian/azul moderno
        cv2.line(frame, (0, header_h), (w, header_h), (50, 75, 105), 1)

        # 2. Indicador pulsante 'EN VIVO / LIVE'
        now = time.time()
        if now - self._last_pulse_time >= 0.5:
            self._pulse_state = not self._pulse_state
            self._last_pulse_time = now

        dot_color = (0, 230, 115) if self._pulse_state else (0, 160, 80)
        cv2.circle(frame, (20, 28), 6, dot_color, -1, cv2.LINE_AA)
        cv2.putText(
            frame,
            i18n.get("live_badge"),
            (34, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 230, 115),
            1,
            cv2.LINE_AA,
        )

        # 3. Título del Sistema
        cv2.putText(
            frame,
            i18n.get("system_title"),
            (115, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (240, 240, 245),
            1,
            cv2.LINE_AA,
        )

        # 4. Badge de Fuente
        source_label = self.source_display
        (sw_w, _), _ = cv2.getTextSize(source_label, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
        src_x1 = 345
        src_x2 = src_x1 + sw_w + 18
        cv2.rectangle(frame, (src_x1, 16), (src_x2, 40), (28, 38, 52), -1)
        cv2.rectangle(frame, (src_x1, 16), (src_x2, 40), (60, 85, 115), 1)
        cv2.putText(
            frame,
            source_label,
            (src_x1 + 9, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (180, 210, 240),
            1,
            cv2.LINE_AA,
        )

        # 5. Barra Dinámica de Movimiento (Motion Gauge)
        meter_x = max(src_x2 + 15, w - 240)
        meter_w = 110
        meter_y = 18
        meter_h = 20

        # Texto de movimiento
        motion_pct = int(min(1.0, max(0.0, motion_energy)) * 100)
        motion_color = (0, 230, 115)  # Verde tranquilo
        motion_label = i18n.get("motion_calm")
        if motion_pct > 12:
            motion_color = (0, 210, 255)  # Amarillo/Ámbar activo
            motion_label = i18n.get("motion_dynamic")
        if motion_pct > 30:
            motion_color = (0, 120, 255)  # Naranja rápido
            motion_label = i18n.get("motion_fast")
        if motion_pct > 55:
            motion_color = (60, 60, 255)  # Rojo intenso
            motion_label = i18n.get("motion_high")

        cv2.putText(
            frame,
            f"{i18n.get('motion_label')}: {motion_pct}%",
            (meter_x - 76, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.40,
            motion_color,
            1,
            cv2.LINE_AA,
        )

        # Barra de progreso
        cv2.rectangle(frame, (meter_x, meter_y), (meter_x + meter_w, meter_y + meter_h), (25, 32, 45), -1)
        fill_w = int(meter_w * (motion_pct / 100.0))
        if fill_w > 0:
            cv2.rectangle(frame, (meter_x, meter_y), (meter_x + fill_w, meter_y + meter_h), motion_color, -1)
        cv2.rectangle(frame, (meter_x, meter_y), (meter_x + meter_w, meter_y + meter_h), (65, 85, 110), 1)

        # 6. FPS en píldora derecha
        fps_x = w - 75
        cv2.putText(
            frame,
            f"{fps:.1f} FPS",
            (fps_x, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (0, 255, 128),
            1,
            cv2.LINE_AA,
        )

        return frame

    def render_tactical_box(
        self,
        frame: np.ndarray,
        box: Tuple[int, int, int, int],
        label: str,
        color: Tuple[int, int, int] = (0, 210, 255),
        is_fire: bool = False,
        is_smoke: bool = False,
        plate_text: Optional[str] = None,
    ) -> np.ndarray:
        """Dibuja recuadros con esquinas tácticas (corner brackets) y etiquetas elegantes."""
        x1, y1, x2, y2 = map(int, box)
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        bw = x2 - x1
        bh = y2 - y1
        corner_len = max(6, min(18, int(min(bw, bh) * 0.25)))

        # Color principal según tipo
        if is_fire:
            c = (0, 0, 255)  # Rojo vivo para fuego
        elif is_smoke:
            c = (220, 220, 230)  # Humo plateado / slate
        else:
            c = color

        # 1. Caja sutil
        cv2.rectangle(frame, (x1, y1), (x2, y2), c, 1, cv2.LINE_AA)

        # 2. Esquinas reforzadas (Tactical Brackets)
        thick = 2
        # Top-Left
        cv2.line(frame, (x1, y1), (x1 + corner_len, y1), c, thick)
        cv2.line(frame, (x1, y1), (x1, y1 + corner_len), c, thick)
        # Top-Right
        cv2.line(frame, (x2, y1), (x2 - corner_len, y1), c, thick)
        cv2.line(frame, (x2, y1), (x2, y1 + corner_len), c, thick)
        # Bottom-Left
        cv2.line(frame, (x1, y2), (x1 + corner_len, y2), c, thick)
        cv2.line(frame, (x1, y2), (x1, y2 - corner_len), c, thick)
        # Bottom-Right
        cv2.line(frame, (x2, y2), (x2 - corner_len, y2), c, thick)
        cv2.line(frame, (x2, y2), (x2, y2 - corner_len), c, thick)

        # 3. Badge de Etiqueta
        (txt_w, txt_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        badge_y1 = max(header_h := 60, y1 - txt_h - 10)
        badge_y2 = badge_y1 + txt_h + 8
        badge_x2 = x1 + txt_w + 12

        badge_bg = (25, 10, 10) if is_fire else ((35, 42, 50) if is_smoke else (15, 20, 30))
        cv2.rectangle(frame, (x1, badge_y1), (badge_x2, badge_y2), badge_bg, -1)
        cv2.rectangle(frame, (x1, badge_y1), (badge_x2, badge_y2), c, 1)
        cv2.putText(
            frame,
            label,
            (x1 + 6, badge_y2 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

        # 4. Badge adicional para Placa Vehicular si fue detectada
        if plate_text:
            p_label = f"PLACA: {plate_text}"
            (pt_w, pt_h), _ = cv2.getTextSize(p_label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            p_y1 = badge_y2 + 2
            p_y2 = p_y1 + pt_h + 6
            p_x2 = x1 + pt_w + 10
            cv2.rectangle(frame, (x1, p_y1), (p_x2, p_y2), (18, 24, 32), -1)
            cv2.rectangle(frame, (x1, p_y1), (p_x2, p_y2), (0, 215, 255), 1)
            cv2.putText(
                frame,
                p_label,
                (x1 + 5, p_y2 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (0, 235, 255),
                1,
                cv2.LINE_AA,
            )

        return frame

    def render_incident_banner(
        self,
        frame: np.ndarray,
        title: str,
        subtitle: str = "",
        is_critical: bool = True,
        is_smoke: bool = False,
    ) -> np.ndarray:
        """Dibuja un banner de alerta con estilo visual y color según severidad y tipo."""
        h, w = frame.shape[:2]
        banner_h = 58
        banner_y1 = 62
        banner_y2 = banner_y1 + banner_h

        if is_smoke and not is_critical:
            bg_color = (55, 65, 80)  # Slate / Ceniza para humo aislado
            border_color = (210, 210, 225)
        elif is_critical:
            bg_color = (0, 0, 180)  # Rojo carmesí para fuego / impacto crítico
            border_color = (0, 0, 255)
        else:
            bg_color = (0, 100, 200)  # Ámbar/naranja advertencia
            border_color = (0, 165, 255)

        self.draw_glass_panel(frame, 15, banner_y1, w - 15, banner_y2, bg_color=bg_color, alpha=0.92)
        cv2.rectangle(frame, (15, banner_y1), (w - 15, banner_y2), border_color, 2)

        # Icono y Texto
        header_text = title.upper()
        if not header_text.startswith("ALERTA") and not header_text.startswith("ALERT"):
            header_text = f"ALERTA / ALERT: {header_text}"

        cv2.putText(
            frame,
            header_text,
            (35, banner_y1 + 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        if subtitle:
            cv2.putText(
                frame,
                subtitle,
                (35, banner_y1 + 46),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.44,
                (230, 230, 240),
                1,
                cv2.LINE_AA,
            )

        return frame

    def render_footer(
        self,
        frame: np.ndarray,
        incident_count: int = 0,
        status_text: Optional[str] = None,
    ) -> np.ndarray:
        """Renderiza la barra de estado inferior con atajos y telemetría internacionalizada."""
        h, w = frame.shape[:2]
        footer_h = 32
        footer_y = h - footer_h

        self.draw_glass_panel(frame, 0, footer_y, w, h, bg_color=(10, 14, 20), alpha=0.85)
        cv2.line(frame, (0, footer_y), (w, footer_y), (40, 55, 75), 1)

        display_status = status_text or i18n.get("status_active")
        status_color = (0, 70, 255) if ("ALERT" in display_status.upper() or "ALERTA" in display_status.upper()) else (0, 230, 115)

        cv2.putText(
            frame,
            display_status,
            (15, h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            status_color,
            1,
            cv2.LINE_AA,
        )

        cv2.putText(
            frame,
            f"{i18n.get('incidents_count')}: {incident_count}",
            (215, h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (200, 200, 210),
            1,
            cv2.LINE_AA,
        )

        # Teclas de atajo dinámicas
        shortcuts_text = i18n.get("footer_shortcuts", lang=i18n.get("language_name"))
        (sc_w, _), _ = cv2.getTextSize(shortcuts_text, cv2.FONT_HERSHEY_SIMPLEX, 0.36, 1)
        sc_x = max(390, w - sc_w - 15)
        cv2.putText(
            frame,
            shortcuts_text,
            (sc_x, h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (145, 170, 195),
            1,
            cv2.LINE_AA,
        )

        return frame

    def render_telemetry_footer(
        self,
        frame: np.ndarray,
        incidents_count: int = 0,
        motion_energy: float = 0.0,
        lang: str = "es",
        status_text: Optional[str] = None,
    ) -> np.ndarray:
        """Alias compatible para renderizado de pie de página."""
        return self.render_footer(
            frame=frame,
            incident_count=incidents_count,
            status_text=status_text,
        )

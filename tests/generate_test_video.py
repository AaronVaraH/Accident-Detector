"""
Generador de video sintético de tráfico para pruebas de detección, tracking y frenado brusco.
Crea un video MP4 con fondo de carretera y rectángulos simulando vehículos con movimiento y frenado.
"""
from pathlib import Path
import cv2
import numpy as np


def create_traffic_simulation(
    output_path: str = "tests/video_samples/sample_traffic.mp4",
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    duration_sec: int = 8,
):
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_file), fourcc, fps, (width, height))

    total_frames = fps * duration_sec

    # Vehículo 1: Velocidad constante normal (carril izquierdo)
    # Vehículo 2: Velocidad rápida que luego frena bruscamente (carril derecho)
    # Posiciones iniciales (x, y, w, h, v_px_per_frame)
    v1 = {"x": 350, "y": 100, "w": 80, "h": 120, "speed": 6.0}
    v2 = {"x": 750, "y": 50, "w": 90, "h": 140, "speed": 12.0}

    for frame_idx in range(total_frames):
        # Fondo tipo asfalto gris oscuro
        frame = np.full((height, width, 3), (45, 45, 45), dtype=np.uint8)

        # Líneas divisorias de carril (blanco / amarillo discontinuo)
        cv2.line(frame, (550, 0), (550, height), (255, 255, 255), 3)
        cv2.line(frame, (650, 0), (650, height), (0, 220, 255), 3)

        # Línea de arcén
        cv2.line(frame, (200, 0), (200, height), (200, 200, 200), 4)
        cv2.line(frame, (1000, 0), (1000, height), (200, 200, 200), 4)

        # Actualizar vehículo 1 (velocidad uniforme)
        v1["y"] += v1["speed"]
        if v1["y"] > height:
            v1["y"] = -100

        # Actualizar vehículo 2 (acelera y luego frena bruscamente entre frame 70 y 90)
        if 70 <= frame_idx <= 95:
            # Desaceleración violenta
            v2["speed"] = max(0.5, v2["speed"] - 0.5)
        elif frame_idx > 95:
            # Casi detenido
            v2["speed"] = 0.2

        v2["y"] += v2["speed"]

        # Dibujar vehículo 1 (azul metálico)
        p1 = (int(v1["x"]), int(v1["y"]))
        p2 = (int(v1["x"] + v1["w"]), int(v1["y"] + v1["h"]))
        cv2.rectangle(frame, p1, p2, (180, 80, 30), -1)
        cv2.rectangle(frame, p1, p2, (255, 255, 255), 2)
        cv2.putText(
            frame,
            "Auto 1",
            (p1[0], p1[1] - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

        # Dibujar vehículo 2 (rojo / anaranjado)
        p3 = (int(v2["x"]), int(v2["y"]))
        p4 = (int(v2["x"] + v2["w"]), int(v2["y"] + v2["h"]))
        # Color rojo de stop si está frenando
        car_color = (0, 0, 220) if frame_idx >= 70 else (30, 80, 200)
        cv2.rectangle(frame, p3, p4, car_color, -1)
        cv2.rectangle(frame, p3, p4, (255, 255, 255), 2)
        txt = "Auto 2 [Frenado]" if frame_idx >= 70 else "Auto 2"
        cv2.putText(
            frame,
            txt,
            (p3[0], p3[1] - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

        out.write(frame)

    out.release()
    print(f"Video sintético generado en: {output_path} ({total_frames} frames, {duration_sec}s)")


if __name__ == "__main__":
    create_traffic_simulation()

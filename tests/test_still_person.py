"""
Test de validación para personas estáticas y filtrado de jitter en cinemática.
Verifica que el ruido del sensor o pequeñas fluctuaciones de bounding box
no generen velocidad > 0 ni falsas alarmas de choque.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import supervision as sv
from src.kinematics import VehicleKinematicsTracker


def test_static_person_zero_speed():
    print("--- Test: Persona Quieta con Jitter de Detección ---")
    tracker = VehicleKinematicsTracker(fps=30.0, is_webcam=True)

    # Simular 30 frames de una persona sentada frente a la webcam
    # Bounding box base: [200, 100, 440, 460] (~240x360 px)
    # Con fluctuación de +- 2 a 3 píxeles (jitter típico de YOLO)
    np.random.seed(42)
    speeds_recorded = []
    anomalies_recorded = []

    for frame_idx in range(1, 40):
        jitter_x = np.random.uniform(-2.5, 2.5)
        jitter_y = np.random.uniform(-2.5, 2.5)
        box = np.array([[200 + jitter_x, 100 + jitter_y, 440 + jitter_x, 460 + jitter_y]])
        
        detections = sv.Detections(
            xyxy=box,
            confidence=np.array([0.88]),
            class_id=np.array([0]),
        )
        detections.data["raw_class_name"] = ["person"]
        detections.data["class_name"] = ["Persona"]

        tracked, anomalies = tracker.update(detections, frame_idx)
        if tracked.tracker_id is not None and len(tracked.tracker_id) > 0:
            tid = tracked.tracker_id[0]
            spd = tracker.get_speed(tid)
            speeds_recorded.append(spd)
        if len(anomalies) > 0:
            anomalies_recorded.append(anomalies)

    print(f"Velocidades en los últimos 20 frames: {speeds_recorded[-20:]}")
    # Debe ser 0.0 km/h en reposo
    final_speed = speeds_recorded[-1]
    assert final_speed == 0.0, f"Error: La velocidad de la persona quieta debería ser 0.0 km/h, pero dio {final_speed} km/h"
    assert len(anomalies_recorded) == 0, f"Error: No deberían generarse anomalías de choque para personas, se registraron {len(anomalies_recorded)}"
    print("[OK] Persona estatica marca exactamente 0.0 km/h y cero falsas alarmas.")


def test_moving_vehicle_detection():
    print("--- Test: Vehiculo en Movimiento Real ---")
    tracker = VehicleKinematicsTracker(fps=30.0, is_webcam=False)
    speeds = []

    # Simular vehículo moviéndose hacia abajo a paso constante
    for frame_idx in range(1, 30):
        y_pos = 100 + frame_idx * 12.0  # 12 px por frame
        box = np.array([[300, y_pos, 450, y_pos + 80]])
        detections = sv.Detections(
            xyxy=box,
            confidence=np.array([0.90]),
            class_id=np.array([2]),
        )
        detections.data["raw_class_name"] = ["car"]
        detections.data["class_name"] = ["Auto"]

        tracked, _ = tracker.update(detections, frame_idx)
        if tracked.tracker_id is not None and len(tracked.tracker_id) > 0:
            tid = tracked.tracker_id[0]
            speeds.append(tracker.get_speed(tid))

    assert speeds[-1] > 10.0, f"Error: El auto en movimiento debería tener velocidad > 10 km/h, dio {speeds[-1]}"
    print(f"[OK] Vehiculo en movimiento detecta velocidad real correctamente: {speeds[-1]:.1f} km/h")


if __name__ == "__main__":
    test_static_person_zero_speed()
    test_moving_vehicle_detection()
    print("\n[SUCCESS] Todos los tests de cinemática pasaron exitosamente.")

"""
Test de validación para las 3 mejoras solicitadas:
1. Soporte multilingüe (ESP/ENG) y alternancia dinámica.
2. Detección y discriminación 100% precisa de Humo vs Fuego (sin alertas genéricas).
3. Renderizado de ventana redimensionable con soporte de pantalla completa.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import supervision as sv
from src.i18n import i18n
from src.incident_rules import IncidentRuleEngine, IncidentEvent
from src.ui_hud import TacticalHUD
from src.kinematics import KinematicAnomaly


def test_i18n():
    print("--- 1. Test i18n (Soporte multilingüe) ---")
    i18n.set_language("es")
    assert i18n.get("live_badge") == "EN VIVO"
    assert i18n.get("fire_detected_title") == "FUEGO DETECTADO"
    assert i18n.get("smoke_detected_title") == "HUMO DETECTADO"
    assert i18n.get_class_name("car") == "Auto"
    assert i18n.get_class_name("person") == "Persona"

    # Cambiar a inglés
    i18n.set_language("en")
    assert i18n.get("live_badge") == "LIVE"
    assert i18n.get("fire_detected_title") == "FIRE DETECTED"
    assert i18n.get("smoke_detected_title") == "SMOKE DETECTED"
    assert i18n.get_class_name("car") == "Car"
    assert i18n.get_class_name("person") == "Person"

    # Alternar dinámicamente con toggle
    new_lang = i18n.toggle_language()
    assert new_lang == "es"
    assert i18n.get("live_badge") == "EN VIVO"
    print("[OK] i18n funciona correctamente en ESP y ENG con alternancia dinamica.")


def test_smoke_vs_fire_rules():
    print("--- 2. Test Discriminación Humo vs Fuego en Reglas ---")
    i18n.set_language("es")
    engine = IncidentRuleEngine(cooldown_seconds=0.0, fire_persistence_frames=2)

    # Detección simulada de solo HUMO (class_id = 0)
    smoke_dets = sv.Detections(
        xyxy=np.array([[10, 10, 100, 100]]),
        confidence=np.array([0.45]),
        class_id=np.array([0]),
    )
    # Frame 1
    ev1 = engine.evaluate(1, [], smoke_dets)
    assert ev1 is None  # Requiere persistencia (2 frames)
    # Frame 2
    ev2 = engine.evaluate(2, [], smoke_dets)
    assert ev2 is not None
    assert ev2.incident_type == "humo_detectado"
    assert "HUMO DETECTADO" in ev2.title
    print(f"[OK] Alerta especifica de HUMO generada: {ev2.title} - {ev2.subtitle}")

    # Detección simulada de solo FUEGO (class_id = 1)
    engine2 = IncidentRuleEngine(cooldown_seconds=0.0, fire_persistence_frames=2)
    fire_dets = sv.Detections(
        xyxy=np.array([[20, 20, 120, 120]]),
        confidence=np.array([0.80]),
        class_id=np.array([1]),
    )
    engine2.evaluate(1, [], fire_dets)
    ev_fire = engine2.evaluate(2, [], fire_dets)
    assert ev_fire is not None
    assert ev_fire.incident_type == "fuego_detectado"
    assert "FUEGO DETECTADO" in ev_fire.title
    print(f"[OK] Alerta especifica de FUEGO generada: {ev_fire.title} - {ev_fire.subtitle}")

    # Detección simulada de FUEGO Y HUMO simultáneos (class_id = 0 y 1)
    engine3 = IncidentRuleEngine(cooldown_seconds=0.0, fire_persistence_frames=2)
    both_dets = sv.Detections(
        xyxy=np.array([[10, 10, 50, 50], [60, 60, 120, 120]]),
        confidence=np.array([0.75, 0.40]),
        class_id=np.array([1, 0]),
    )
    engine3.evaluate(1, [], both_dets)
    ev_both = engine3.evaluate(2, [], both_dets)
    assert ev_both is not None
    assert ev_both.incident_type == "fuego_humo_detectado"
    assert "FUEGO Y HUMO" in ev_both.title
    print(f"[OK] Alerta COMBINADA generada: {ev_both.title} - {ev_both.subtitle}")


def test_tactical_hud_rendering():
    print("--- 3. Test Renderizado HUD Tactico con Humo e Idioma ---")
    hud = TacticalHUD(source_name="0")
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Test Header
    f_hdr = hud.render_header(dummy_frame.copy(), fps=30.0, frame_idx=10, object_count=2, motion_energy=0.25)
    assert f_hdr.shape == dummy_frame.shape

    # Test Caja Táctica de Humo
    f_box = hud.render_tactical_box(
        dummy_frame.copy(),
        box=(50, 50, 200, 200),
        label="HUMO (0.45)",
        is_smoke=True,
    )
    assert f_box.shape == dummy_frame.shape

    # Test Banner de Humo
    f_banner = hud.render_incident_banner(
        dummy_frame.copy(),
        title="HUMO DETECTADO",
        subtitle="Emision de humo en la zona",
        is_critical=False,
        is_smoke=True,
    )
    assert f_banner.shape == dummy_frame.shape

    # Test Footer
    f_footer = hud.render_footer(dummy_frame.copy(), incident_count=3)
    assert f_footer.shape == dummy_frame.shape
    print("[OK] Renderizado de HUD Tactico validado sin errores.")


def test_fire_smoke_chroma_filters():
    print("--- 4. Test Filtros Cromáticos Humo (Piel/Motion Blur) y Fuego (Reflejos) ---")
    from src.inference import FireDetector

    # 1. Parche de piel humana (BGR: B=110, G=140, R=200) -> Tono caucásico/latino común
    skin_patch = np.full((50, 50, 3), [110, 140, 200], dtype=np.uint8)
    assert FireDetector._is_human_skin_or_colorful_object(skin_patch) is True
    print("[OK] Piel humana/motion blur de manos descartado correctamente para humo.")

    # 2. Parche de humo real (grisáceo neutro: B=130, G=132, R=135)
    smoke_patch = np.full((50, 50, 3), [130, 132, 135], dtype=np.uint8)
    assert FireDetector._is_human_skin_or_colorful_object(smoke_patch) is False
    print("[OK] Humo grisáceo neutro admitido correctamente.")

    # 3. Reflejo de luz blanca / objeto claro (taza blanca, pared: B=235, G=235, R=238)
    white_reflection = np.full((30, 30, 3), [235, 235, 238], dtype=np.uint8)
    assert FireDetector._is_valid_flame_chroma(white_reflection) is False
    print("[OK] Reflejo blanco desaturado descartado correctamente para fuego.")

    # 4. Llama real (R=245, G=120, B=20)
    flame_patch = np.full((30, 30, 3), [20, 120, 245], dtype=np.uint8)
    assert FireDetector._is_valid_flame_chroma(flame_patch) is True
    print("[OK] Llama real (cálida con alta saturación) aceptada correctamente para fuego.")


    # 5. Parche mixto: mano sosteniendo hoja con humo tenue (B=130, G=132, R=135 en 50% y piel en 50%)
    mixed_crop = np.full((60, 60, 3), [110, 140, 200], dtype=np.uint8) # fondo con mano
    mixed_crop[:30, :] = [130, 132, 135] # humo en mitad superior
    assert FireDetector._is_human_skin_or_colorful_object(mixed_crop) is False
    print("[OK] Mano sosteniendo hoja quemándose con humo admitida correctamente (no descartada).")

    # 6. Luz de foco/lámpara cálida uniforme (B=180, G=230, R=255)
    warm_lamp = np.full((40, 40, 3), [180, 230, 255], dtype=np.uint8)
    assert FireDetector._is_valid_flame_chroma(warm_lamp) is False
    print("[OK] Foco/lámpara cálida uniforme descartado correctamente.")

    # 7. Test persistencia suave de humo frente a titileo
    from src.incident_rules import IncidentRuleEngine
    engine = IncidentRuleEngine(fire_persistence_frames=3, smoke_persistence_frames=2)
    smoke_det = sv.Detections(
        xyxy=np.array([[10, 10, 50, 50]]),
        confidence=np.array([0.16]),
        class_id=np.array([0]),
    )
    # Frame 1: humo presente
    engine.evaluate(1, [], smoke_det)
    assert engine._consecutive_smoke_count == 1
    # Frame 2: humo parpadea (frame sin detección)
    engine.evaluate(2, [], sv.Detections.empty())
    assert engine._consecutive_smoke_count == 0 or engine._consecutive_smoke_count == 0  # decae a 0 o 1
    # Frame 3: humo presente de nuevo
    engine.evaluate(3, [], smoke_det)
    assert engine._consecutive_smoke_count >= 1
    print("[OK] Persistencia temporal adaptativa contra titileo de humo validada.")


if __name__ == "__main__":
    test_i18n()
    test_smoke_vs_fire_rules()
    test_tactical_hud_rendering()
    test_fire_smoke_chroma_filters()
    print("\n[SUCCESS] Todos los tests pasaron exitosamente.")


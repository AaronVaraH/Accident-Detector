"""
Unit tests for the core Accident-Detector rule engine and kinematics tracker.
Covers normal, edge, and invalid input cases without requiring video files or network access.
"""

import numpy as np
import supervision as sv

from src.incident_rules import IncidentEvent, IncidentRuleEngine
from src.kinematics import KinematicAnomaly, VehicleKinematicsTracker


def _make_anomaly(tracker_id: int = 7, delta_v: float = 55.0) -> KinematicAnomaly:
    return KinematicAnomaly(
        tracker_id=tracker_id,
        frame_idx=42,
        initial_speed_kmh=75.0,
        final_speed_kmh=20.0,
        delta_v=delta_v,
        delta_t_seconds=0.4,
        bbox=np.array([100.0, 100.0, 220.0, 200.0]),
    )


def _make_fire_detections(class_ids: list[int]) -> sv.Detections:
    n = len(class_ids)
    xyxy = np.array([[10.0, 10.0, 50.0, 50.0] for _ in range(n)], dtype=float)
    return sv.Detections(
        xyxy=xyxy,
        confidence=np.full(n, 0.85, dtype=float),
        class_id=np.array(class_ids, dtype=int),
    )


def test_rule_engine_normal_critical_braking():
    """Normal case: a kinematic anomaly alone triggers a critical braking incident."""
    engine = IncidentRuleEngine(cooldown_seconds=60.0, fire_persistence_frames=3)
    event = engine.evaluate(
        frame_idx=10,
        kinematic_anomalies=[_make_anomaly(tracker_id=12, delta_v=60.0)],
        fire_detections=None,
    )
    assert event is not None
    assert event.incident_type == "frenado_critico_colision"
    assert event.kinematic_anomaly is not None
    assert event.kinematic_anomaly.tracker_id == 12


def test_rule_engine_fire_persistence_edge_case():
    """Edge case: fire must persist for N consecutive frames before triggering."""
    engine = IncidentRuleEngine(cooldown_seconds=0.0, fire_persistence_frames=3, smoke_persistence_frames=3)
    fire_only = _make_fire_detections([1])

    assert engine.evaluate(1, [], fire_only) is None
    assert engine.evaluate(2, [], fire_only) is None

    confirmed = engine.evaluate(3, [], fire_only)
    assert confirmed is not None
    assert confirmed.incident_type == "fuego_detectado"


def test_rule_engine_combined_collision_fire_and_smoke():
    """Normal case: simultaneous kinematic anomaly, fire, and smoke triggers combined incident."""
    engine = IncidentRuleEngine(cooldown_seconds=60.0, fire_persistence_frames=2, smoke_persistence_frames=2)
    fire_and_smoke = _make_fire_detections([0, 1])

    # Frame 1 builds persistence; Frame 2 confirms both fire and smoke with collision
    assert engine.evaluate(1, [], fire_and_smoke) is None
    event = engine.evaluate(2, [_make_anomaly(tracker_id=5)], fire_and_smoke)

    assert event is not None
    assert event.incident_type == "colision_con_fuego_humo"
    payload = event.to_dict()
    assert payload["has_fire"] is True
    assert payload["has_smoke"] is True
    assert payload["vehicle_id"] == 5


def test_rule_engine_cooldown_suppresses_duplicate_alerts():
    """Edge case: repeated anomalies inside cooldown window are suppressed."""
    engine = IncidentRuleEngine(cooldown_seconds=60.0, fire_persistence_frames=2)
    first = engine.evaluate(1, [_make_anomaly()], None)
    second = engine.evaluate(2, [_make_anomaly()], None)

    assert first is not None
    assert second is None


def test_rule_engine_empty_and_none_inputs():
    """Invalid/empty case: no anomalies and None/empty detections return None safely."""
    engine = IncidentRuleEngine(cooldown_seconds=0.0, fire_persistence_frames=2)
    empty_det = sv.Detections.empty()

    assert engine.evaluate(0, [], None) is None
    assert engine.evaluate(1, [], empty_det) is None


def test_kinematics_tracker_invalid_fps_defaults_to_30():
    """Invalid input case: non-positive FPS safely falls back to 30.0."""
    tracker_zero = VehicleKinematicsTracker(fps=0.0)
    tracker_negative = VehicleKinematicsTracker(fps=-15.0)

    assert tracker_zero.fps == 30.0
    assert tracker_negative.fps == 30.0


def test_incident_event_to_dict_without_anomaly_or_fire():
    """Edge case: IncidentEvent serializes cleanly when optional fields are None."""
    event = IncidentEvent(
        incident_type="humo_detectado",
        frame_idx=99,
        timestamp=1700000000.0,
        description="Smoke detected on highway",
    )
    data = event.to_dict()

    assert data["incident_type"] == "humo_detectado"
    assert data["vehicle_id"] is None
    assert data["delta_v"] is None
    assert data["has_fire"] is False
    assert data["has_smoke"] is False


def test_rule_engine_smoke_only_detection():
    """Normal case: sustained smoke without fire or collision triggers smoke incident."""
    engine = IncidentRuleEngine(cooldown_seconds=0.0, fire_persistence_frames=3, smoke_persistence_frames=2)
    smoke_only = _make_fire_detections([0])

    assert engine.evaluate(1, [], smoke_only) is None
    event = engine.evaluate(2, [], smoke_only)
    assert event is not None
    assert event.incident_type == "humo_detectado"

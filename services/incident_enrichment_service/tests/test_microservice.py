"""
Suite de Pruebas Automatizadas para el Microservicio de Enriquecimiento y Despacho.
Valida:
1. Endpoints públicos y protegidos.
2. Autenticación con Header X-API-Key (éxito, ausencia y token inválido).
3. Validación de entradas (HTTP 400 y formato limpio sin stack traces).
4. Verbos HTTP y códigos de estado (200, 201, 400, 401, 404).
5. Resiliencia ante fallos de la API de terceros (Weather fallback).
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from services.incident_enrichment_service.main import app
from services.incident_enrichment_service.config import settings

client = TestClient(app)

VALID_PAYLOAD = {
    "camera_id": "CAM-CDMX-PERIFERICO-04",
    "incident_type": "colision_critica",
    "confidence": 0.94,
    "telemetry": {
        "initial_speed_kmh": 78.5,
        "impact_speed_kmh": 0.0,
        "delta_time_sec": 0.38,
        "has_fire": False,
        "has_smoke": True,
    },
    "latitude": 19.3012,
    "longitude": -99.1824,
    "detected_plate": "ABC-1234",
    "frame_snapshot_url": "https://storage.incidentdetector.io/snapshots/snap_test.jpg",
}


def test_health_endpoint():
    """Valida el endpoint de verificación de salud."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "registered_dossiers" in data


def test_evaluate_and_dispatch_success():
    """Valida creación exitosa con autenticación válida (HTTP 201 Created)."""
    headers = {"X-API-Key": settings.SERVICE_API_KEY}
    response = client.post(
        "/api/v1/incidents/evaluate-and-dispatch",
        json=VALID_PAYLOAD,
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "DESPACHADO_A_CENTRAL"
    assert "INC-" in data["incident_id"]
    assert data["severity_level"] in ["CRÍTICO", "ALTO", "MODERADO", "BAJO"]
    assert "environmental_risk" in data
    assert "wind_speed_kmh" in data["environmental_risk"]
    assert "pavement_status" in data["environmental_risk"]
    assert data["dispatch_ticket_id"].startswith("CAD-911-MEX-")


def test_evaluate_and_dispatch_missing_auth():
    """Valida que la ausencia de X-API-Key retorne HTTP 401 Unauthorized."""
    response = client.post(
        "/api/v1/incidents/evaluate-and-dispatch",
        json=VALID_PAYLOAD,
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert "ausente" in data["message"].lower() or "unauthorized" in data["error"].lower()


def test_evaluate_and_dispatch_invalid_auth():
    """Valida que una X-API-Key incorrecta retorne HTTP 401 Unauthorized."""
    headers = {"X-API-Key": "clave_falsa_invalida"}
    response = client.post(
        "/api/v1/incidents/evaluate-and-dispatch",
        json=VALID_PAYLOAD,
        headers=headers,
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert "inválida" in data["message"].lower() or "unauthorized" in data["error"].lower()


def test_evaluate_and_dispatch_validation_error():
    """Valida que un payload con datos no válidos retorne HTTP 400 Bad Request y JSON limpio."""
    headers = {"X-API-Key": settings.SERVICE_API_KEY}
    invalid_payload = {
        "camera_id": "",  # Vacío (violación de validación)
        "incident_type": "x",  # Demasiado corto
        "confidence": 2.5,  # Fuera de rango [0.0, 1.0]
        "telemetry": {
            "initial_speed_kmh": -50.0,  # Velocidad negativa inválida
            "impact_speed_kmh": 0.0,
            "delta_time_sec": 0.0,  # Debe ser > 0
        },
    }
    response = client.post(
        "/api/v1/incidents/evaluate-and-dispatch",
        json=invalid_payload,
        headers=headers,
    )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Bad Request"
    assert "details" in data
    assert len(data["details"]) > 0
    # Comprobar que no hay stack traces ni rutas internas de Python
    response_text = response.text
    assert "Traceback" not in response_text
    assert ".py\", line" not in response_text


def test_get_dossier_success():
    """Valida la consulta de un expediente existente (HTTP 200 OK)."""
    response = client.get("/api/v1/incidents/INC-2026-004812/dossier")
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-2026-004812"
    assert data["status"] == "EN_ATENCION_MEDICA"
    assert "environmental_risk" in data


def test_get_dossier_not_found():
    """Valida que consultar un ID inexistente retorne HTTP 404 Not Found."""
    response = client.get("/api/v1/incidents/INC-9999-INEXISTENTE/dossier")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert "no se encontró" in data["message"].lower()


def test_environmental_hazards_success():
    """Valida consulta climática en vivo (HTTP 200 OK)."""
    response = client.get("/api/v1/environmental-hazards?lat=19.4326&lon=-99.1332")
    assert response.status_code == 200
    data = response.json()
    assert "weather_condition" in data
    assert "wind_speed_kmh" in data
    assert "pavement_status" in data
    assert "smoke_dispersion_direction" in data


def test_environmental_hazards_invalid_coordinates():
    """Valida que coordenadas inválidas retornen HTTP 400 Bad Request."""
    response = client.get("/api/v1/environmental-hazards?lat=999.0&lon=-99.1332")
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Bad Request"


def test_weather_fallback_on_third_party_failure():
    """Valida que si la API de terceros falla, el microservicio degrade graciosamente sin fallar."""
    headers = {"X-API-Key": settings.SERVICE_API_KEY}
    with patch("requests.get", side_effect=Exception("API de clima temporalmente inaccesible")):
        response = client.post(
            "/api/v1/incidents/evaluate-and-dispatch",
            json=VALID_PAYLOAD,
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "environmental_risk" in data
        assert "Fallback" in data["environmental_risk"]["source"] or "Offline" in data["environmental_risk"]["weather_condition"]


"""
Suite de pruebas de preparación para Producción:
1. Validación de ruta segura HTTPS para cámara (/api/camera/validate) y cabeceras TLS/HSTS/Permissions-Policy.
2. Generación automática de certificados SSL con SANs (localhost + IP LAN).
3. Gestión del Backlog persistente (Supabase PostgreSQL + Bucket mirror) y exportación CSV/JSON.
4. Healthcheck de producción (/api/health).
"""

import json
from starlette.requests import Request
from server import (
    BacklogIncidentCreatePayload,
    BacklogStatusUpdatePayload,
    export_backlog_data,
    get_backlog,
    get_backlog_status,
    get_enrichment_dossier,
    get_enrichment_hazards,
    get_health,
    get_historial_page,
    patch_backlog_incident,
    post_create_backlog_incident,
    validate_camera_https_route,
)
from src.ssl_manager import ensure_ssl_certificates, get_local_lan_ip


def _make_request(path: str, scheme: str = "http", headers: dict | None = None) -> Request:
    raw_headers = [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "scheme": scheme,
        "headers": raw_headers,
        "query_string": b"",
    }
    return Request(scope)


def test_ssl_certificate_generation_with_san():
    cert_path, key_path = ensure_ssl_certificates(force_regenerate=True)
    assert cert_path.exists()
    assert key_path.exists()
    assert cert_path.stat().st_size > 200
    assert key_path.stat().st_size > 200


def test_camera_https_validation_endpoint():
    # 1. Petición detrás de Reverse Proxy HTTPS (ej. Render en producción)
    req_https = _make_request(
        "/api/camera/validate",
        scheme="http",
        headers={"X-Forwarded-Proto": "https", "Host": "accident-detector.onrender.com"},
    )
    res_https = validate_camera_https_route(req_https)
    assert res_https.status_code == 200
    data = json.loads(res_https.body)
    assert data["is_https"] is True
    assert data["strict_https_verified"] is True
    assert data["camera_secure_context_valid"] is True
    assert data["websocket_uplink_url"] == "wss://accident-detector.onrender.com/ws/uplink"

    # 2. Petición en IP remota sin HTTPS -> debe indicar ruta recomendada https://
    req_http = _make_request(
        "/api/camera/validate",
        scheme="http",
        headers={"Host": f"{get_local_lan_ip()}:8000"},
    )
    res_http = validate_camera_https_route(req_http)
    assert res_http.status_code == 200
    data_http = json.loads(res_http.body)
    assert data_http["recommended_https_url"].startswith("https://")


def test_backlog_lifecycle_and_exports():
    # 1. Crear un registro de incidente en el backlog
    payload = BacklogIncidentCreatePayload(
        incident_type="colision_critica",
        severity="CRITICO",
        status="PENDIENTE",
        title="IMPACTO VEHICULAR EN PERIFÉRICO",
        subtitle="Desaceleración 72 -> 0 km/h",
        camera_id="CAM-NORTE-01",
        plate="ABC-1234",
        notes="Prueba de integración para backlog",
    )
    create_res = post_create_backlog_incident(payload)
    assert create_res.status_code == 201
    created = json.loads(create_res.body)["incident"]
    inc_id = created["incident_id"]
    assert inc_id.startswith("INC-")
    assert created["status"] == "PENDIENTE"

    # 2. Consultar backlog general y estado de base de datos
    list_res = get_backlog(limit=20)
    assert list_res.status_code == 200
    backlog_data = json.loads(list_res.body)
    assert any(i["incident_id"] == inc_id for i in backlog_data["incidents"])

    status_res = get_backlog_status()
    assert status_res.status_code == 200
    assert "PostgreSQL" in json.loads(status_res.body)["provider"]

    # 3. Actualizar estatus del incidente en el backlog (PENDIENTE -> RESUELTO)
    patch_res = patch_backlog_incident(
        inc_id,
        BacklogStatusUpdatePayload(status="RESUELTO", notes="Unidad médica despachada y cerrada"),
    )
    assert patch_res.status_code == 200
    assert json.loads(patch_res.body)["incident"]["status"] == "RESUELTO"

    # 4. Exportar en CSV y JSON
    csv_res = export_backlog_data(format="csv", target="incidents")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.media_type
    assert inc_id in csv_res.body.decode("utf-8-sig")

    json_res = export_backlog_data(format="json")
    assert json_res.status_code == 200
    assert "application/json" in json_res.media_type
    exported_json = json.loads(json_res.body)
    assert "incidents_backlog" in exported_json


def test_production_health_endpoint():
    req = _make_request("/api/health", scheme="https", headers={"X-Forwarded-Proto": "https"})
    res = get_health(req)
    assert res.status_code == 200
    body = json.loads(res.body)
    assert body["status"] == "healthy"
    assert body["https_verified"] is True
    assert "database" in body


def test_historial_view_and_microservice_enrichment():
    # 1. Vista dedicada /historial
    hist_res = get_historial_page()
    assert hist_res.path.name == "historial.html"

    # 2. Consulta de expediente del microservicio
    dossier_res = get_enrichment_dossier("INC-2026-004812")
    assert dossier_res.status_code == 200
    dossier_data = json.loads(dossier_res.body)
    assert dossier_data["incident_id"] == "INC-2026-004812"
    assert "dispatch_ticket_id" in dossier_data

    # 3. Consulta de riesgos ambientales y dispersión de humo
    hazards_res = get_enrichment_hazards(lat=19.3012, lon=-99.1824, has_fire=True)
    assert hazards_res.status_code == 200
    hazards_data = json.loads(hazards_res.body)
    assert "smoke_dispersion_direction" in hazards_data
    assert "hazard_level" in hazards_data

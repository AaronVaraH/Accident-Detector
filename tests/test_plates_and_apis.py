"""
Suite de pruebas integrales para:
1. Detección de placas con modelo Roboflow: vehicle-registration-plates-trudk/2
2. Motor OCR y extracción alfanumérica
3. APIs de consulta vehicular (REPUVE, fichas técnicas, alerta Hazmat/EV)
4. APIs de enriquecimiento contextual (clima, viento, geocodificación inversa)
5. Endpoints REST de FastAPI
"""

import base64
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from fastapi.testclient import TestClient
from server import app
from src.plate_detector import license_plate_detector
from src.enrichment import vehicle_service, weather_service, location_service, enrichment_aggregator
from src.pipeline_manager import pipeline_manager


def test_plate_detection_roboflow_and_ocr():
    print("\n--- 1. Test Detección de Placas Roboflow & OCR ---")
    # Crear imagen sintética con formato y apariencia de placa vehicular
    img = np.full((300, 500, 3), 170, dtype=np.uint8)
    cv2.rectangle(img, (40, 40), (460, 260), (35, 35, 35), -1)
    cv2.rectangle(img, (140, 110), (360, 190), (255, 255, 255), -1)
    cv2.rectangle(img, (140, 110), (360, 190), (0, 0, 0), 2)
    cv2.putText(img, "ABC-1234", (160, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2)

    # 1. Probar OCR y registro directamente sobre el recorte de placa
    crop = img[110:190, 140:360]
    plate_text, ocr_conf = license_plate_detector.read_plate_text(crop)
    print(f"[OK] Lectura OCR directa: '{plate_text}' (Confianza: {ocr_conf})")
    assert len(plate_text) >= 3 or "ABC" in plate_text or "1234" in plate_text

    # 2. Registrar placa y verificar generación de expediente
    rec = license_plate_detector.process_and_register_plate(
        frame=img,
        box=[140, 110, 360, 190],
        confidence=0.96,
        plate_text_override=plate_text if plate_text else "ABC-1234",
    )
    assert rec is not None, "El registro de placa no debió ser nulo."
    print(f"[OK] Placa registrada y procesada: {rec.plate_text} (Vehículo: {rec.vehicle_data.get('brand')})")
    assert rec.vehicle_data["brand"] == "Nissan"


def test_vehicle_lookup_service():
    print("\n--- 2. Test Servicio de Consulta Vehicular (APIs & Base de Datos) ---")
    # Consulta de vehículo de combustión registrado
    v1 = vehicle_service.lookup("ABC-1234")
    assert v1["brand"] == "Nissan"
    assert v1["model"] == "Versa Advance"
    assert v1["is_stolen"] is False
    print(f"[OK] Ficha Nissan: {v1['brand']} {v1['model']} ({v1['fuel_type']}) - {v1['stolen_status']}")

    # Consulta de vehículo eléctrico (EV) con alerta HAZMAT
    v2 = vehicle_service.lookup("XYZ-789-A")
    assert v2["brand"] == "Tesla"
    assert "Eléctrico" in v2["fuel_type"]
    assert "hazmat_alert" in v2
    print(f"[OK] Ficha Tesla EV: {v2['brand']} - {v2['hazmat_alert']}")

    # Consulta de vehículo con reporte de robo
    v3 = vehicle_service.lookup("ROB-404-X")
    assert v3["is_stolen"] is True
    print(f"[OK] Ficha Alerta Robo: {v3['brand']} - {v3['stolen_status']}")

    # Consulta determinista de placa desconocida
    v_new = vehicle_service.lookup("JAL-9988")
    assert "brand" in v_new
    assert "model" in v_new
    assert "fuel_type" in v_new
    print(f"[OK] Consulta determinista de nueva placa 'JAL-9988': {v_new['brand']} {v_new['model']} ({v_new['year']})")


def test_enrichment_services():
    print("\n--- 3. Test Servicios de Clima, Ubicación y Despacho ---")
    w = weather_service.get_weather()
    assert "temperature_c" in w
    assert "wind_speed_kmh" in w
    print(f"[OK] Clima: {w['temperature_c']}°C, Viento: {w['wind_speed_kmh']} km/h, Asfalto: {w['pavement_risk']}")

    loc = location_service.get_location()
    assert "city" in loc or "address" in loc
    print(f"[OK] Ubicación Geocodificada: {loc.get('street') or loc.get('address')}")

    # Despacho consolidado de emergencia
    dispatch = enrichment_aggregator.enrich_incident(
        incident_type="fuego_detectado",
        title="INCENDIO EN VANO MOTOR",
        subtitle="Llamas vivas detectadas",
        plate="XYZ-789-A",
    )
    assert dispatch["incident"]["urgency"] == "CRÍTICO"
    assert dispatch["vehicle"]["brand"] == "Tesla"
    assert len(dispatch["emergency_recommendations"]) > 0
    print(f"[OK] Expediente de despacho consolidado generado con éxito. Recomendaciones: {len(dispatch['emergency_recommendations'])}")


def test_fastapi_rest_endpoints():
    print("\n--- 4. Test Endpoints REST en FastAPI ---")
    client = TestClient(app)

    # Status
    r_status = client.get("/api/status")
    assert r_status.status_code == 200

    # Lookup vía POST
    r_lookup = client.post("/api/plates/lookup", json={"plate": "ABC-1234"})
    assert r_lookup.status_code == 200
    assert r_lookup.json()["brand"] == "Nissan"
    print(f"[OK] POST /api/plates/lookup: {r_lookup.json()['brand']}")

    # Registro de nuevo vehículo
    r_reg = client.post("/api/plates/register", json={
        "plate": "CUSTOM-99",
        "brand": "Mazda",
        "model": "Mazda 3",
        "year": 2024,
        "color": "Soul Red",
        "vehicle_type": "Sedán",
        "fuel_type": "Gasolina",
        "stolen_status": "SIN REPORTE DE ROBO",
        "is_stolen": False,
        "owner_type": "Particular",
        "jurisdiction": "Nuevo León"
    })
    assert r_reg.status_code == 200
    assert r_reg.json()["vehicle"]["brand"] == "Mazda"
    print(f"[OK] POST /api/plates/register: Registrado Mazda con éxito.")

    # Detalle vía GET
    r_detail = client.get("/api/plates/CUSTOM-99")
    assert r_detail.status_code == 200
    assert r_detail.json()["brand"] == "Mazda"
    print(f"[OK] GET /api/plates/CUSTOM-99: Recuperado correctamente.")

    # Detección de placas en imagen vía POST /api/plates/detect
    dummy_img = np.full((250, 400, 3), 190, dtype=np.uint8)
    cv2.rectangle(dummy_img, (50, 80), (350, 170), (255, 255, 255), -1)
    cv2.rectangle(dummy_img, (50, 80), (350, 170), (0, 0, 0), 2)
    cv2.putText(dummy_img, "XYZ-789-A", (70, 135), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    _, buf = cv2.imencode(".jpg", dummy_img)
    b64_str = base64.b64encode(buf.tobytes()).decode("ascii")

    r_detect = client.post("/api/plates/detect", json={"image_base64": b64_str})
    assert r_detect.status_code == 200
    assert "plates" in r_detect.json()
    print(f"[OK] POST /api/plates/detect: {r_detect.json()['plates_found']} placas encontradas.")

    # Contexto situacional
    r_ctx = client.get("/api/enrichment/context")
    assert r_ctx.status_code == 200
    assert "weather" in r_ctx.json()
    assert "location" in r_ctx.json()
    print(f"[OK] GET /api/enrichment/context: Retorna clima y ubicación en tiempo real.")


if __name__ == "__main__":
    test_plate_detection_roboflow_and_ocr()
    test_vehicle_lookup_service()
    test_enrichment_services()
    test_fastapi_rest_endpoints()
    print("\n✅ TODAS LAS PRUEBAS DE PLACAS Y APIS COMPLETADAS CON ÉXITO.")

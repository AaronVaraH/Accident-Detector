# Microservicio de Enriquecimiento Situacional y Despacho de Incidentes
## (*Incident Enrichment & Emergency Dispatch Service*)

Servicio REST autónomo y desacoplado para el sistema **Accident-Detector**, diseñado y aprobado en la **Actividad 3** ([`docs/product_analysis.md`](../../docs/product_analysis.md)).

Este microservicio se encarga de:
1. Ingestar eventos de colisión, frenado brusco o fuego detectados por los módulos de visión por computadora.
2. Consumir APIs de meteorología de terceros (**OpenWeatherMap** y fallback automático a **Open-Meteo**) para calcular factores de riesgo ambiental (dirección de dispersión de humo y adherencia del pavimento).
3. Evaluar el nivel de severidad y emitir un expediente normalizado para su despacho hacia centrales de emergencia (**CAD 911 / Bomberos**).
4. Proteger operaciones críticas mediante autenticación con API Key.
5. Garantizar resiliencia y seguridad operacional (validación estricta de entradas y supresión de stack traces en errores HTTP).

---

## 🏗️ Arquitectura e Integración con la Aplicación Principal

```text
┌──────────────────────────────────────────────┐
│  Accident-Detector (Aplicación Principal)    │
│  - server.py (FastAPI, Puerto 8000)          │
│  - Pipeline IA (YOLOv8 + ByteTrack)          │
│  - src/microservice_client.py (Consumidor)   │
└──────────────────────┬───────────────────────┘
                       │
                       │ Petición HTTP POST (X-API-Key)
                       ▼
┌──────────────────────────────────────────────┐
│  Microservicio de Enriquecimiento            │
│  - services/incident_enrichment_service      │
│  - Puerto 8001 (Independiente)               │
│  - FastAPI + Pydantic v2                     │
└──────────────────────┬───────────────────────┘
                       │
                       │ Consulta REST (lat, lon)
                       ▼
┌──────────────────────────────────────────────┐
│  API de Terceros: OpenWeatherMap / OpenMeteo │
│  (Velocidad de viento, lluvia, temperatura)  │
└──────────────────────────────────────────────┘
```

---

## 📋 Tabla de Endpoints REST

| Método | URL | Autenticación | Códigos de Estado | Descripción |
| :--- | :--- | :---: | :---: | :--- |
| `POST` | `/api/v1/incidents/evaluate-and-dispatch` | **Sí** (`X-API-Key`) | `201 Created`<br>`400 Bad Request`<br>`401 Unauthorized`<br>`500 Internal Error` | Ingesta la telemetría del siniestro, consulta la meteorología externa, evalúa dispersión de humo, calcula severidad y genera el expediente con ticket CAD-911. |
| `GET` | `/api/v1/incidents/{incident_id}/dossier` | No (Público) | `200 OK`<br>`404 Not Found`<br>`500 Internal Error` | Consulta el expediente consolidado y el estatus situacional de un incidente por su identificador único. |
| `GET` | `/api/v1/environmental-hazards` | No (Público) | `200 OK`<br>`400 Bad Request`<br>`500 Internal Error` | Consulta meteorológica en tiempo real en coordenadas `(lat, lon)` para evaluar adherencia del asfalto y dirección de viento. |
| `GET` | `/health` | No (Público) | `200 OK` | Verificación de salud y disponibilidad del microservicio. |

---

## 🔒 Autenticación y Seguridad

El endpoint crítico `/api/v1/incidents/evaluate-and-dispatch` requiere el encabezado:
```http
X-API-Key: titan-secret-key-2026
```

- Si el encabezado está ausente o la clave no coincide, el microservicio rechaza la petición con **HTTP `401 Unauthorized`** y un mensaje JSON estructurado.
- La clave se configura en la variable de entorno `SERVICE_API_KEY`.

---

## 🛡️ Validación de Entradas y Supresión de Stack Traces

- **Validación Estricta:** Todas las entradas se validan mediante esquemas de Pydantic. Si un parámetro es inválido (por ejemplo, velocidad negativa, confianza fuera del rango `[0.0, 1.0]`, o coordenadas geográficas fuera de rango), el microservicio responde con **HTTP `400 Bad Request`**:
  ```json
  {
    "success": false,
    "error": "Bad Request",
    "message": "Los parámetros enviados en la petición son inválidos.",
    "details": [
      {
        "field": "telemetry -> initial_speed_kmh",
        "message": "Input should be greater than or equal to 0",
        "type": "greater_than_equal"
      }
    ]
  }
  ```
- **Sin Stack Traces hacia el Cliente:** Cualquier excepción no controlada en el servidor es capturada por el handler global, devolviendo **HTTP `500 Internal Server Error`** con un mensaje seguro. Las trazas completas (*tracebacks*) únicamente se registran en los logs del servidor para auditoría interna.

---

## 🌐 Consumo de API de Terceros y Tolerancia a Fallos

El microservicio se comunica con servicios meteorológicos globales para calcular el vector de dispersión de humo y la pérdida de adherencia en el asfalto:
1. **OpenWeatherMap API:** Se utiliza si se proporciona `OPENWEATHER_API_KEY` en el archivo `.env`.
2. **Open-Meteo API (Fallback Primario):** Si no hay clave de OpenWeatherMap o si ésta agota su cuota, el microservicio consulta de manera transparente la API pública de Open-Meteo.
3. **Modo Contingencia (*Graceful Degradation*):** Si la red externa se encuentra completamente caída, el microservicio activa un modelo de estimación nominal local. El despacho de la ambulancia o patrulla **nunca se bloquea**.

---

## ⚙️ Instalación y Puesta en Marcha

### 1. Requisitos Previos
- Python 3.10 o superior.
- Entorno virtual activado.

### 2. Configurar Variables de Entorno
Copia la plantilla `.env.example` para generar tu archivo `.env`:

```powershell
# En Windows PowerShell:
Copy-Item services\incident_enrichment_service\.env.example services\incident_enrichment_service\.env
```

Contenido de `.env`:
```env
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8001
LOG_LEVEL=INFO
SERVICE_API_KEY=titan-secret-key-2026
OPENWEATHER_API_KEY=tu_api_key_aqui
WEATHER_REQUEST_TIMEOUT=3.0
```

> **Nota:** El archivo `.env` está expresamente excluido del repositorio mediante `.gitignore`.

### 3. Ejecutar el Microservicio

```powershell
# Desde la raíz del proyecto:
python -m uvicorn services.incident_enrichment_service.main:app --port 8001 --reload
```

El servicio estará disponible en:
- **API Base:** `http://localhost:8001`
- **Documentación Interactiva Swagger UI:** `http://localhost:8001/docs`
- **Documentación ReDoc:** `http://localhost:8001/redoc`

---

## 🧪 Pruebas y Evidencias de Funcionamiento

### Opción A: Pruebas Automatizadas con Pytest
El microservicio cuenta con una suite completa de 10 pruebas automatizadas que validan:
- Autenticación válida e inválida.
- Manejo de HTTP 200, 201, 400, 401, 404.
- Supresión de stack traces en errores.
- Degradación elegante ante fallos de la API externa.

Para ejecutarlas:
```powershell
python -m pytest services/incident_enrichment_service/tests/test_microservice.py -v
```

### Opción B: Colección de Peticiones HTTP (`requests.http`)
Se incluye el archivo interactivo [`requests.http`](requests.http) listo para ejecutarse con la extensión **REST Client** de VS Code o importarse en Postman/Insomnia.

Ejemplo de petición con `curl`:
```bash
curl -X POST "http://localhost:8001/api/v1/incidents/evaluate-and-dispatch" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: titan-secret-key-2026" \
  -d '{
    "camera_id": "CAM-CDMX-PERIFERICO-04",
    "incident_type": "colision_critica",
    "confidence": 0.94,
    "telemetry": {
      "initial_speed_kmh": 78.5,
      "impact_speed_kmh": 0.0,
      "delta_time_sec": 0.38,
      "has_fire": false,
      "has_smoke": true
    },
    "latitude": 19.3012,
    "longitude": -99.1824,
    "detected_plate": "ABC-1234"
  }'
```

---

## 🔗 Consumo desde la Aplicación Principal

La aplicación principal consume este microservicio a través del módulo [`src/microservice_client.py`](../../src/microservice_client.py).

Cuando el despachador o la consola táctica en [`server.py`](../../server.py) evalúa un incidente:
```python
from src.microservice_client import incident_microservice_client

# Llamada HTTP REST al microservicio
dossier = incident_microservice_client.evaluate_and_dispatch(
    camera_id="CAM-CDMX-PERIFERICO-04",
    incident_type="colision_critica",
    confidence=0.92,
    telemetry={
        "initial_speed_kmh": 65.0,
        "impact_speed_kmh": 0.0,
        "delta_time_sec": 0.45,
        "has_fire": False,
        "has_smoke": True,
    },
    detected_plate="ABC-1234",
)
```
Si el microservicio no estuviese en línea, el cliente activa automáticamente un fallback local para asegurar la continuidad del monitoreo vial.

# 🚀 Guía de Despliegue en Producción: Servidor Principal + Microservicio en Cuentas Separadas de Render + PostgreSQL/Blob en Vercel

Esta guía documenta paso a paso cómo desplegar y conectar **Accident-Detector (TITAN Vision)** en producción utilizando:
1. **Cuenta 1 de Render (Servidor Principal + PWA + Motor IA):** Ejecuta [`server.py`](server.py), expone el Dashboard táctico en `/` y la vista dedicada de auditoría en `/historial`.
2. **Cuenta 2 de Render (Capa de Microservicios):** Ejecuta el microservicio REST independiente [`services/incident_enrichment_service`](services/incident_enrichment_service/main.py) para evaluación contextual, cálculo de dispersión de humo y generación de tickets **CAD-911**.
3. **Vercel Storage (PostgreSQL + Vercel Blob):** Almacena automáticamente el historial forense de incidentes, placas detectadas y fotografías de evidencia.

---

## 🏗️ Arquitectura de Comunicación en Producción

```
┌─────────────────────────────────────────────────────────────┐
│ CUENTA 1 DE RENDER (Servidor Principal + PWA)               │
│ URL: https://accident-detector.onrender.com                 │
│  ├─ /          -> Dashboard Táctico en Vivo (Cámara + IA)   │
│  ├─ /historial -> Vista Dedicada de Historial y Expedientes │
│  └─ Consume vía HTTP (X-API-Key) ───────────────────────────┼───┐
└───────────────┬─────────────────────────────────────────────┘   │
                │                                                 ▼
                │                             ┌──────────────────────────────────────────────┐
                │                             │ CUENTA 2 DE RENDER (Microservicio REST)      │
                │                             │ Root Dir: services/incident_enrichment_service│
                │                             │ URL: https://titan-enrichment-ms.onrender.com│
                │                             │  ├─ POST /api/v1/incidents/evaluate-and-dispatch
                │                             │  ├─ GET  /api/v1/incidents/{id}/dossier      │
                │                             │  └─ GET  /api/v1/environmental-hazards       │
                │                             └──────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────┐
│ VERCEL STORAGE (Base de Datos + Almacenamiento de Objetos)  │
│  ├─ Vercel Postgres (SQLAlchemy ORM crea las 3 tablas solo) │
│  └─ Vercel Blob (Sube las capturas JPEG de choques y placas)│
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ PARTE 1: Desplegar el Microservicio en la Cuenta 2 de Render

1. Inicia sesión en tu **segunda cuenta de Render** (o en un nuevo servicio dentro de tu cuenta) y haz clic en **New +** -> **Web Service**.
2. Conecta el mismo repositorio de GitHub (`Accident-Detector`).
3. Configura los siguientes campos exactos en el formulario de Render:
   - **Name:** `titan-enrichment-microservice`
   - **Branch:** `main`
   - **Root Directory:** `services/incident_enrichment_service` *(¡Muy importante! Esto le indica a Render que despliegue únicamente la carpeta del microservicio)*.
   - **Runtime / Environment:** `Docker` (usará el [`services/incident_enrichment_service/Dockerfile`](services/incident_enrichment_service/Dockerfile) que es ultraligero, ~45 MB de RAM, ideal para el **Plan Free**) o `Python 3` con:
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. En la sección **Environment Variables** del Microservicio (Cuenta 2), agrega:

| Variable | Valor |
| :--- | :--- |
| `ENVIRONMENT` | `production` |
| `SERVICE_API_KEY` | `titan-secret-key-2026` *(o tu clave secreta personalizada)* |
| `OPENWEATHER_API_KEY` | Tu API Key de OpenWeatherMap *(la misma de tu `.env`)* |

5. Haz clic en **Create Web Service**.
6. Una vez desplegado, copia la URL pública que te asignó Render (ejemplo: `https://titan-enrichment-microservice.onrender.com`) y verifica que responda entrando a:
   - `https://titan-enrichment-microservice.onrender.com/health`
   - `https://titan-enrichment-microservice.onrender.com/docs`

---

## 🔗 PARTE 2: Conectar el Servidor Principal (Cuenta 1 de Render) con el Microservicio y Vercel

En tu **Cuenta 1 de Render** (donde ya tienes arriba el proyecto principal), ve a tu servicio -> pestaña **Environment** y asegúrate de tener configuradas estas variables (puedes copiarlas directamente de tu archivo [`.env`](.env)):

### 1. Conexión con el Microservicio (Cuenta 2)
| Variable | Valor |
| :--- | :--- |
| `ENRICHMENT_SERVICE_URL` | `https://titan-enrichment-microservice.onrender.com` *(sin `/` al final)* |
| `ENRICHMENT_SERVICE_API_KEY` | `titan-secret-key-2026` *(debe coincidir exactamente con `SERVICE_API_KEY` de la Cuenta 2)* |

### 2. Conexión con Base de Datos y Blob de Vercel
| Variable | Valor |
| :--- | :--- |
| `POSTGRES_URL_NON_POOLING` | Tu URL `postgres://...` de Vercel Postgres |
| `DATABASE_URL` | Tu URL `postgres://...` de Vercel Postgres |
| `BLOB_READ_WRITE_TOKEN` | Tu token `vercel_blob_rw_...` de Vercel Blob |

*(Nota: Al arrancar [`server.py`](server.py), SQLAlchemy ORM ejecuta `Base.metadata.create_all()` automáticamente y crea las tablas `incidents_backlog`, `plates_backlog` y `vehicles_registry` en tu base de datos de Vercel sin necesidad de correr scripts SQL).*

### 3. Variables de IA y Despacho SMS (Twilio / APIs)
| Variable | Valor |
| :--- | :--- |
| `ENVIRONMENT` | `production` |
| `FORCE_HTTPS` | `true` |
| `ROBOFLOW_API_KEY` | Tu clave de Roboflow |
| `OPENWEATHER_API_KEY` | Tu clave de OpenWeatherMap |
| `MAPS_API_KEY` | Tu clave de Google Maps |
| `RAPIDAPI_KEY` | Tu clave de RapidAPI (`car-api2`) |
| `TWILIO_ACCOUNT_SID` | Tu Account SID de Twilio |
| `TWILIO_AUTH_TOKEN` | Tu Auth Token de Twilio |
| `TWILIO_FROM_PHONE` | Número remitente de Twilio |
| `TWILIO_TO_PHONE` | Número destino de emergencias |

---

## 🖥️ PARTE 3: Validación Visual en el Dashboard (`/`) y en la Vista `/historial`

Ya no verás respuestas JSON estáticas: toda la información del microservicio y de la base de datos se consume y presenta en componentes visuales interactivos:

1. **En el Dashboard Principal (`/`):**
   - **Panel "CONTEXTO SITUACIONAL (APIs)":** Muestra en tiempo real el estado del microservicio (`MS: REMOTO ACTIVO`), la dirección de **Dispersión de Humo** (`Noreste (NE)`), el **Riesgo Ambiental** (`BAJO / MODERADO / CRÍTICO`), el estado del pavimento y el botón **`EVALUAR & DESPACHAR CAD-911`**, que invoca el microservicio y despliega la tarjeta visual con el folio `CAD-911-MEX-...` y el estado del SMS.
   - **Botón Superior `HISTORIAL`:** Enlaza directamente a la vista dedicada `/historial`.

2. **En la Vista Dedicada (`/historial`):**
   - Muestra las tarjetas de métricas globales del backlog (Total Siniestros, Pendientes/En Atención, Resueltos y Placas en Backlog).
   - Permite filtrar incidentes por estado (`PENDIENTE`, `EN_ATENCION`, `RESUELTO`) y por tipo (`colision_critica`, `fuego_confirmado`, `humo_detectado`), cambiar el estado con un clic y abrir la fotografía de evidencia guardada en **Vercel Blob**.
   - Incluye el **Inspector de Expediente Situacional del Microservicio REST**, donde al hacer clic en cualquier incidente de la lista (o buscar su ID como `INC-2026-004812`) se visualizan todos los datos cruzados del microservicio (Ticket CAD-911, Cinemática de Impacto, Dispersión de Humo, Clima y Vehículo).
   - Incluye botones de descarga directa para exportar a **CSV (Excel)** y **JSON**.

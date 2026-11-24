# Accident-Detector: Sistema Inteligente de Detección de Incidentes Viales

Sistema de visión computacional y análisis cinemático para la detección temprana de incidentes de tráfico (frenados bruscos, colisiones potenciales) y siniestros con fuego o humo en transmisiones de video vial.

---

## 🚀 Arquitectura y Fases

- **Fase 1: Pipeline Visual y Tracking Local** (Completada):
  - Ingesta de video con OpenCV (`src/stream.py`).
  - Detección de vehículos con YOLOv8 (`src/inference.py`).
  - Seguimiento persistente con ByteTrack y cálculo de velocidad / desaceleración crítica (`src/kinematics.py`).
  - Anotaciones dinámicas con Supervision (`main.py`).
- **Fase 2: Detección de Fuego/Humo y Motor de Reglas** (Siguiente).
- **Fase 3: Módulo de Enriquecimiento (APIs de Clima y Mapas)**.
- **Fase 4: Despacho y Notificaciones (Telegram / Twilio)**.

---

## 🛠️ Instalación y Uso (Clean Clone)

### 1. Clonar e instalar dependencias
```bash
git clone https://github.com/AaronVaraH/Accident-Detector.git
cd Accident-Detector
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno
Copia `.env.example` a `.env` y completa tus claves locales (nunca subas `.env` al repositorio):
```powershell
Copy-Item .env.example .env
```

### 3. Ejecutar el proyecto
- **Iniciar Servidor Web & Aplicación PWA (Recomendado):**
  ```powershell
  python server.py
  # O alternativamente:
  python main.py --web
  ```
  Accede desde cualquier navegador en: `http://localhost:8000` (o la IP local de tu PC) e instálala con el botón **"INSTALAR PWA"**.

- **Iniciar Microservicio REST de Enriquecimiento y Despacho:**
  ```powershell
  python -m uvicorn services.incident_enrichment_service.main:app --port 8001 --reload
  ```
  Documentación de endpoints: 👉 **[services/incident_enrichment_service/README.md](services/incident_enrichment_service/README.md)**

- **Ejecutar pipeline CLI con video de prueba o cámara web:**
  ```powershell
  python main.py --source tests/video_samples/sample_traffic.mp4
  # Con cámara web:
  python main.py --source 0
  ```

---

## 🧪 Pruebas Automatizadas (Unit Tests & CI)

El proyecto cuenta con **17 pruebas unitarias** (`pytest`) que cubren casos normales, de borde (*edge cases*) y entradas inválidas tanto para el motor de reglas/cinemática (`tests/test_core_unit.py`) como para el microservicio REST (`services/incident_enrichment_service/tests/test_microservice.py`).

Ejecutar toda la suite desde un clon limpio:
```bash
pytest tests/test_core_unit.py services/incident_enrichment_service/tests/test_microservice.py -v
```

Las pruebas se ejecutan automáticamente en **GitHub Actions** (`.github/workflows/ci.yml`) en cada `pull_request` y `push` hacia `main`. La rama `main` está protegida y requiere que el check `unit-tests` pase antes de hacer merge.

---

## 📱 Progressive Web App (PWA) Táctica
La PWA incluye:
- **Streaming de video MJPEG a 30 FPS** con overlays tácticos y HUD estilo Cyber-Security.
- **Telemetría WebSocket en tiempo real**: Conteos en vivo, velocidades, estados de alarma y flujo óptico.
- **Enlace de Subida de Smartphone (Uplink)**: Permite usar la cámara de tu propio teléfono móvil como sensor remoto transmitiendo en vivo al pipeline de IA del servidor.
- **Alerta Sonora Táctica**: Sirena dual sintetizada con Web Audio API (sin archivos de audio externos) y vibración háptica.
- **Soporte Multilingüe**: Alternancia instantánea entre Español e Inglés (ES / EN).
- **Service Worker & Manifest**: Instalable como app nativa en Android, iOS, Windows y macOS con funcionamiento offline de la shell.

---

## ⚙️ Configuración
- Configurar coordenadas y líneas virtuales de calibración en `config/cameras.json`.
- Configurar credenciales de Telegram/Twilio y umbrales en `.env` (a partir de `.env.example`).

---

## ☁️ Despliegue en la Nube (Render CI/CD) y Documentación
El proyecto cuenta con despliegue automatizado en la nube mediante **Docker** y **Render**:
- Servidor web FastAPI, streaming en vivo y PWA empaquetados en un solo contenedor optimizado.
- Auto-deploy al hacer `git push origin main` (protegido por Pull Requests y CI).
- **Proceso formal de despliegue (Before, Deploy, Verify, Roll back, Record):** 👉 **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**
- **Guía técnica detallada de Render + Vercel:** 👉 **[DEPLOYMENT.md](DEPLOYMENT.md)**
- **Bitácora de desarrollo (Development Log):** 👉 **[docs/DEVELOPMENT_LOG.md](docs/DEVELOPMENT_LOG.md)**


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

## 🛠️ Instalación y Uso

### 1. Activar entorno virtual
En Windows PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

### 2. Generar video sintético de prueba
```powershell
python tests/generate_test_video.py
```

### 3. Ejecutar el monitor principal
- **Con video de prueba:**
  ```powershell
  python main.py --source tests/video_samples/sample_traffic.mp4
  ```

- **Con cámara web:**
  ```powershell
  python main.py --source 0
  ```

- **Iniciar como Servidor Web & Aplicación PWA (Móvil, Tablet y Escritorio):**
  ```powershell
  python main.py --web
  # O alternativamente:
  python server.py
  ```
  Accede desde cualquier navegador o teléfono en tu red local en: `http://localhost:8000` (o la IP local de tu PC) e instálala con el botón **"INSTALAR PWA"**.

- **Guardando salida anotada:**
  ```powershell
  python main.py --source tests/video_samples/sample_traffic.mp4 --output tests/video_samples/output_annotated.mp4
  ```

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

## ☁️ Despliegue en la Nube (Render CI/CD)
El proyecto cuenta con despliegue automatizado en la nube mediante **Docker** y **Render**:
- Servidor web FastAPI, streaming en vivo y PWA empaquetados en un solo contenedor optimizado.
- Auto-deploy al hacer `git push origin main`.
- Para consultar estándares de desarrollo, límites de memoria RAM (512 MB Free), configuración de variables de entorno y prevención de cold starts, consulta la guía completa:
  👉 **[Guía de Despliegue y Ciclo de Desarrollo (DEPLOYMENT.md)](DEPLOYMENT.md)**


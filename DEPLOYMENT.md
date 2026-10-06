# 🚀 Guía de Despliegue y Ciclo de Desarrollo Continuo en Render

Este documento establece los estándares de desarrollo, pruebas y despliegue continuo (CI/CD) para **Accident-Detector** utilizando **Docker** y **Render**.

---

## 🏗️ 1. Arquitectura de Despliegue

La solución está empaquetada como un microservicio autónomo en un contenedor Docker con **Linux Debian (Python 3.10-slim)**:
- **FastAPI / Uvicorn**: Provee la API REST, streaming MJPEG y WebSockets en tiempo real.
- **Frontend PWA**: Servido directamente desde la carpeta `pwa/` por FastAPI en la raíz `/` con soporte para instalación offline, manifest y service workers.
- **Pipeline de IA**: Ejecución optimizada en CPU con soporte para YOLOv8 (nano) y modelos remotos vía Roboflow API.

---

## 🔄 2. Flujo de Trabajo de Desarrollo (Workflow)

Render está configurado con **Auto-Deploy** enlazado a la rama `main` de GitHub. El flujo recomendado para trabajar es:

### Paso 1: Desarrollo y Pruebas Locales
Trabaja con el entorno virtual activo:
```powershell
# En Windows PowerShell
.venv\Scripts\Activate.ps1

# Ejecutar el servidor en local
python server.py
```
Accede a `http://localhost:8000` para probar los cambios en la PWA y en el backend.

### Paso 2: Validación Previa al Commit
Antes de subir cambios, verifica que:
1. Si instalaste nuevas librerías, estén registradas en `requirements.txt`:
   ```powershell
   pip freeze > requirements.txt  # o agregarla manualmente
   ```
2. Si la librería requiere paquetes nativos de C/C++ o Linux (ej. `libsndfile`, `tesseract`), deben agregarse a `apt-get install` en el `Dockerfile`.
3. Ningún archivo `.env`, llaves SSL ni pesos (`.pt`, `.onnx`) se encuentren en el staging de Git (`git status`).

### Paso 3: Publicación y Auto-Deploy
Haz commit y push a la rama `main`:
```powershell
git add .
git commit -m "feat: descripción clara de la mejora"
git push origin main
```
**Render detectará el push de inmediato, construirá la nueva imagen Docker y pondrá la versión actualizada en línea de forma automática.**

---

## 🛡️ 3. Reglas de Oro para Desarrollo Enfocado a Render

### ⚠️ A. Gestión Estricta de Memoria RAM (Límite: 512 MB Free Tier)
El plan gratuito de Render otorga 512 MB de memoria RAM. Superar este límite provocará un reinicio por **Out of Memory (OOM)**:
- **Modelos de IA**: Utiliza siempre variantes **Nano** (`yolov8n.pt`) o delega la inferencia pesada a APIs externas (Roboflow Inference).
- **Procesamiento de Video**: Procesa fotogramas al vuelo; **nunca acumules buffers de imágenes o arrays NumPy en listas globales**.
- **Liberación de Memoria**: Deja que el recolector de basura de Python limpie las variables temporales tras procesar cada fotograma.

### 🌐 B. Puerto Dinámico (`$PORT`)
Render asigna un puerto dinámico mediante la variable de entorno `$PORT` (generalmente el puerto `10000`):
- `server.py` ya lee automáticamente `int(os.environ.get("PORT", 8000))`.
- Nunca fijes un puerto estático en el código del servidor.

### 🔐 C. Seguridad y Variables de Entorno
Todos los secretos deben registrarse en el panel de Render (**Environment Tab**), nunca en el código fuente:
- `ROBOFLOW_API_KEY`: Llave de inferencia de Roboflow.
- `MODEL_ID_VEHICULOS`: `vehicle-qq0yh/2`
- `MODEL_ID_FUEGO`: `fire-detection-for-khkt/3`
- `MODEL_ID_PLACAS`: `vehicle-registration-plates-trudk/2`
- `DEVICE`: `cpu`
- `CONFIDENCE_THRESHOLD`: `0.45`
- `IOU_THRESHOLD`: `0.50`

---

## 🐳 4. Prueba Local con Docker (Simulación Idéntica a Render)

Si tienes Docker instalado y deseas validar exactamente lo que correrá Render antes de hacer push:

```powershell
# 1. Construir la imagen localmente
docker build -t accident-detector .

# 2. Correr el contenedor pasando las variables de entorno
docker run -p 8000:8000 --env-file .env accident-detector
```
Abre `http://localhost:8000` en tu navegador para confirmar el correcto funcionamiento.

---

## ⏱️ 5. Manejo de "Cold Start" y Mantener el Servicio Activo

En el plan gratuito, Render apaga el servicio tras **15 minutos de inactividad**. La siguiente petición tardará ~40 segundos en levantar el contenedor.

**Solución para mantenerlo 24/7 despierto (Opcional & Gratuito):**
1. Crea una cuenta gratuita en [cron-job.org](https://cron-job.org) o [uptimerobot.com](https://uptimerobot.com).
2. Configura un monitor tipo **HTTP(s)** apuntando al endpoint de estado:
   `https://tu-app-render.onrender.com/api/status`
3. Configura el intervalo cada **10 minutos**.
4. Con esto, el servidor recibirá un ping continuo y permanecerá siempre despierto sin entrar en modo reposo.

---

## 🩺 6. Solución de Problemas (Troubleshooting)

| Síntoma en Render | Causa Probable | Solución |
| :--- | :--- | :--- |
| **Build Error: `No module named cv2`** | Falta alguna biblioteca C de Linux en el sistema. | Verificar que `libgl1` y `libglib2.0-0` estén en `apt-get` en el `Dockerfile`. |
| **Exit Code 137 / Out of Memory** | La carga de modelos excedió los 512 MB de RAM. | Verificar que `DEVICE=cpu` y que solo se cargue el modelo Nano o Roboflow. |
| **Web Service Failed to Bind to Port** | El servidor no escuchó en `0.0.0.0` o no usó `$PORT`. | Asegurar que `uvicorn` escuche en `host="0.0.0.0"` y `port=int(os.environ.get("PORT", 8000))`. |
| **WebSocket Connection Failed** | El cliente PWA intenta conectar a HTTP en lugar de WSS. | `app.js` detecta `wss://` automáticamente cuando corre bajo HTTPS en Render. |

# Plan de Implementación: Sistema Inteligente de Detección de Incidentes Viales

## 1. Resumen Ejecutivo
El sistema analiza transmisiones de video vial en tiempo real mediante visión computacional para detectar anomalías de tráfico (frenados bruscos/colisiones) y presencia de fuego o humo. Al confirmarse un siniestro, un orquestador backend enriquece el evento consultando APIs de clima, geolocalización y datos vehiculares para despachar una alerta estructurada inmediata a los servicios de emergencia.

---

## 2. Arquitectura del Sistema

[ Fuente de Video (RTSP / MP4 / Webcam) ]
│
▼
[ OpenCV (Frame Stream) ]
│
▼
[ Inferencia Local YOLO ]
(Vehículos, Humo, Fuego)
│
▼
[ ByteTrack + Cinemática ]
(Tracking de IDs y km/h)
│
▼
[ Motor de Reglas de Siniestro ]
¿Desaceleración crítica + Fuego/Humo?
│
┌───────────┴───────────┐
│ No                    │ Sí
▼                       ▼
[Descartar]       [ Despachador Asíncrono ]
│
┌───────────────────────────┼───────────────────────────┐
▼                           ▼                           ▼
[API Clima]               [API Mapas]               [API Vehicular / OCR]
(Viento, Lluvia)        (Dirección legible)          (Datos del rodado)
└───────────────────────────┬───────────────────────────┘
│
▼
[ Notificación / Alerta ]
(Telegram / Twilio / SMS)


---

## 3. Stack Tecnológico

| Capa | Herramienta / Servicio | Función |
| :--- | :--- | :--- |
| **Ingesta de Video** | `opencv-python` | Lectura de frames continuos y control de stream. |
| **Inferencia** | `ultralytics` / `inference` (Roboflow) | Ejecución de modelos YOLOv8/YOLO11 locales. |
| **Seguimiento y Métricas** | `supervision` | ByteTrack para IDs persistentes y líneas de cruce. |
| **Consultas Externas** | `requests` | Consumo de endpoints REST (RapidAPI). |
| **Clima** | OpenWeatherMap / WeatherAPI | Datos meteorológicos (ráfagas de viento, visibilidad). |
| **Geolocalización** | Google Maps / Geoapify | Reverse geocoding de coordenadas fijas de cámara. |
| **Datos Vehiculares** | RapidAPI (CarAPI / REPUVE scraper) | Tipología del vehículo (gasolina, diésel, eléctrico). |
| **Despacho de Alertas** | Telegram Bot API / Twilio | Notificación con metadata e imagen del evento. |

---

## 4. Fases de Ejecución

### Fase 1: Pipeline Visual y Tracking Local
* **Objetivo:** Ingestar video y detectar vehículos junto con su vector de desplazamiento sin latencia de red.
* **Acciones:**
  1. Configurar entorno Python e instalar dependencias (`opencv-python`, `supervision`, `ultralytics`).
  2. Descargar pesos preentrenados para vehículos (`yolov8n.pt` o modelo Roboflow).
  3. Integrar `ByteTrack` para mantener IDs únicos por vehículo en cada frame.
  4. Configurar dos líneas virtuales en la escena para medir el tiempo transcurrido ($\Delta t$) y estimar velocidad en base a una distancia calibrada en metros.

### Fase 2: Detección de Fuego/Humo y Motor de Reglas
* **Objetivo:** Identificar la coexistencia de anomalías físicas y fuego/humo, evitando falsos positivos.
* **Acciones:**
  1. Integrar modelo de detección de fuego y humo (descarga de pesos de Roboflow Universe).
  2. Implementar regla de desaceleración crítica: $\Delta v$ extrema en $< 0.5$ s o detención total tras trayectoria a alta velocidad.
  3. Implementar persistencia temporal de fuego/humo: la detección debe sostenerse por al menos $N$ frames consecutivos ($N \ge 8$) con confianza $> 0.65$.
  4. Diseñar un mecanismo de *cooldown / debounce* (e.g., 60 segundos) para impedir que el mismo siniestro dispare alertas repetitivas en cada frame subsecuente.

### Fase 3: Módulo de Enriquecimiento (APIs)
* **Objetivo:** Construir el payload contextual sin frenar el bucle principal de procesamiento visual.
* **Acciones:**
  1. Crear llamadas no bloqueantes (hilo secundario o función asíncrona) que reciban las coordenadas GPS fijas de la cámara.
  2. Consultar API de clima: extraer velocidad del viento, dirección y estado del pavimento (lluvia/hielo).
  3. Consultar API de mapas: transformar `(lat, lon)` en calle e intersección más próxima.
  4. Extraer frame congelado del siniestro y almacenarlo temporalmente en buffer de memoria.

### Fase 4: Despacho y Notificación
* **Objetivo:** Transmitir la información consolidada al canal de respuesta correspondiente.
* **Acciones:**
  1. Estructurar el payload final en formato JSON estándar.
  2. Configurar webhook de Telegram para desarrollo/pruebas (envío del reporte detallado junto con la captura fotográfica del frame).
  3. Diseñar fallback con Twilio para despacho de SMS o llamada sintetizada en casos de alta prioridad.

---

## 5. Estructura del Repositorio

```text
incident-monitor/
├── config/
│   ├── cameras.json           # Ubicación, calibración px/m y zonas virtuales
│   └── settings.py            # API Keys y umbrales de detección
├── models/
│   ├── fire_smoke.pt          # Pesos locales para fuego y humo
│   └── vehicle_yolo.pt        # Pesos locales para vehículos
├── src/
│   ├── __init__.py
│   ├── stream.py              # Ingesta y captura con OpenCV
│   ├── inference.py           # Envoltura de inferencia sobre frames
│   ├── kinematics.py          # Cálculo de trayectoria y velocidad
│   ├── incident_rules.py      # Lógica de detección de colisión y fuego
│   ├── enrichment.py          # Consultas a APIs externas
│   └── dispatcher.py          # Despacho a Telegram / Twilio
├── tests/
│   └── video_samples/         # Videos cortos de prueba
├── requirements.txt
├── Plan_implementation.md
└── main.py                    # Loop de ejecución principal
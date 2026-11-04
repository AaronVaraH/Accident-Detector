# Historias de Usuario (User Stories) - Accident-Detector

Este documento recopila las historias de usuario clave para el sistema **Accident-Detector**, cubriendo tanto las capacidades operativas actuales como su evolución hacia una plataforma SaaS distribuida de asistencia a emergencias viales.

---

## 📋 Resumen de Historias de Usuario

| ID | Título | Actor / Rol | Prioridad | Módulo Asociado |
| :--- | :--- | :--- | :--- | :--- |
| **US-01** | Detección Automática de Colisiones por Cinemática en Tiempo Real | Operador de Monitoreo Vial (C5 / Tráfico) | **Alta** (Must Have) | Inferencia & Cinemática (`src/kinematics.py`) |
| **US-02** | Detección de Fuego/Humo y Disparo de Alerta Sonora Táctica | Despachador de Bomberos / Protección Civil | **Alta** (Must Have) | Reglas de Siniestro & HUD (`src/incident_rules.py`) |
| **US-03** | Despacho Automatizado de Emergencias con Enriquecimiento Contextual | Coordinador de Cabina 911 / CAD | **Alta** (Must Have) | Microservicio de Enriquecimiento (`src/enrichment.py`) |
| **US-04** | Identificación Vehicular Forense y Evaluación de Riesgo de Propulsión | Primer Respondiente / Rescatista de Campo | **Media** (Should Have) | Detector de Placas & Registro (`src/plate_detector.py`) |

---

### US-01: Detección Automática de Colisiones por Cinemática en Tiempo Real

* **ID:** `US-01`
* **Épica:** Detección Temprana de Incidentes y Visión Computacional
* **Prioridad:** Alta (Must Have)
* **Estimación:** 8 Story Points

#### Narrativa:
> **Como** operador de un centro de control y comando vial (C5 / Concesionaria de Autopista),  
> **quiero** que el sistema analice automáticamente las cámaras de tráfico para detectar frenados extremos y colisiones vehiculares mediante análisis de aceleración y vectores de trayectoria,  
> **para** identificar incidentes viales en menos de un segundo sin depender de llamadas de testigos oculares o de la vigilancia humana permanente de cientos de pantallas.

#### Criterios de Aceptación (Acceptance Criteria):
- [ ] **AC-01.1 (Tracking persistente):** El sistema debe asignar un identificador numérico único (Tracking ID con ByteTrack) a cada vehículo detectado dentro de la zona de interés de la cámara.
- [ ] **AC-01.2 (Cálculo de velocidad):** La velocidad estimada debe calcularse a partir del desplazamiento en píxeles calibrado contra metros reales en la escena.
- [ ] **AC-01.3 (Detección de colisión crítica):** Se debe disparar un estado de alerta de colisión si un vehículo experimenta una desaceleración drástica ($\Delta v > 40\text{ km/h}$ en $\Delta t < 0.5\text{ s}$) o un choque seguido de detención súbita en carril de alta velocidad.
- [ ] **AC-01.4 (Alerta en interfaz):** El vehículo involucrado debe ser resaltado visualmente en el HUD de la PWA con un cuadro delimitador rojo intermitente y el texto `COLISIÓN DETECTADA`.

---

### US-02: Detección de Fuego/Humo y Disparo de Alerta Sonora Táctica

* **ID:** `US-02`
* **Épica:** Seguridad Integral y Mitigación de Riesgos Catastróficos
* **Prioridad:** Alta (Must Have)
* **Estimación:** 5 Story Points

#### Narrativa:
> **Como** despachador del cuerpo de bomberos y protección civil,  
> **quiero** que el sistema reconozca la aparición sostenida de humo o llamas en el entorno vial y emita alarmas tácticas acústicas y hápticas en la aplicación de monitoreo,  
> **para** movilizar unidades contra incendios de manera anticipada antes de que el fuego se propague a otros vehículos o infraestructura vial.

#### Criterios de Aceptación (Acceptance Criteria):
- [ ] **AC-02.1 (Persistencia temporal):** La detección de fuego o humo debe persistir durante al menos 8 frames consecutivos con una confianza mayor a 0.65 para evitar falsos positivos producidos por reflejos solares o vapor de escape.
- [ ] **AC-02.2 (Alerta sonora sintetizada):** Al confirmarse el fuego o humo, la PWA debe activar una sirena táctica mediante la Web Audio API y generar vibración háptica en dispositivos móviles compatibles sin requerir descargas pesadas de audio.
- [ ] **AC-02.3 (Cooldown de alertas):** El sistema debe implementar un periodo de enfriamiento (*debounce/cooldown*) configurable (ej. 60 segundos) para no saturar al operador con avisos repetidos por el mismo evento activo.
- [ ] **AC-02.4 (Clasificación de riesgo):** Si coinciden desaceleración crítica y fuego simultáneamente, el siniestro debe catalogarse como `RIESGO EXTREMO / INCENDIO ACTIVO`.

---

### US-03: Despacho Automatizado de Emergencias con Enriquecimiento Contextual

* **ID:** `US-03`
* **Épica:** Integración de Microservicios y Respuesta a Emergencias
* **Prioridad:** Alta (Must Have)
* **Estimación:** 13 Story Points

#### Narrativa:
> **Como** coordinador de cabina 911 / CAD (Computer-Aided Dispatch),  
> **quiero** que cuando ocurra un accidente el sistema consulte automáticamente las APIs de meteorología, geocodificación inversa y notificación SMS/Webhooks,  
> **para** recibir un expediente digital listo para despacho con la dirección exacta, estado del pavimento y condiciones climáticas sin perder tiempo en transcripciones manuales.

#### Criterios de Aceptación (Acceptance Criteria):
- [ ] **AC-03.1 (Geocodificación legible):** El microservicio de enriquecimiento debe convertir las coordenadas GPS de la cámara en una dirección física en texto (calle principal, intersección y colonia).
- [ ] **AC-03.2 (Condiciones meteorológicas):** El paquete de despacho debe incluir temperatura, ráfagas de viento (para predecir dispersión de humo) y estado del pavimento (seco, mojado o con hielo).
- [ ] **AC-03.3 (Canales de alerta redundantes):** El sistema debe enviar la alerta estructurada a través de webhook REST a sistemas CAD y, de forma paralela, despachar un SMS crítico a los comandantes de guardia vía Twilio.
- [ ] **AC-03.4 (Evidencia fotográfica):** El reporte debe contener una URL segura o captura fotográfica del frame congelado en el momento exacto del siniestro.

---

### US-04: Identificación Vehicular Forense y Evaluación de Riesgo de Propulsión

* **ID:** `US-04`
* **Épica:** Analítica Forense y Seguridad de Rescate (Desarrollo Futuro)
* **Prioridad:** Media (Should Have)
* **Estimación:** 8 Story Points

#### Narrativa:
> **Como** paramédico o rescatista de campo (primer respondiente),  
> **quiero** consultar la placa del vehículo involucrado para conocer su tipo de motorización (gasolina, diésel, híbrido o 100% eléctrico) y reporte legal,  
> **para** aplicar el protocolo de extricación seguro (evitando descargas de alto voltaje en baterías de vehículos eléctricos) y alertar a la policía si el vehículo cuenta con reporte de robo vigente.

#### Criterios de Aceptación (Acceptance Criteria):
- [ ] **AC-04.1 (Reconocimiento OCR):** El subsistema de detección de matrículas debe extraer el texto alfanumérico de las placas vehiculares visibles en el siniestro con un umbral de confianza mínimo del 75%.
- [ ] **AC-04.2 (Ficha técnica del vehículo):** A partir de la placa o VIN, el sistema debe devolver marca, submarca, año modelo y tipo de combustible del rodado.
- [ ] **AC-04.3 (Alerta de vehículo eléctrico):** Si el vehículo siniestrado es eléctrico (EV) o híbrido, la ficha de despacho debe incluir una advertencia destacada sobre riesgo de fuga térmica y la ubicación recomendada de desconexión del circuito de alto voltaje.
- [ ] **AC-04.4 (Estatus legal):** El sistema debe verificar si el vehículo tiene reporte de robo activo y notificarlo de manera discreta a las autoridades policiales.

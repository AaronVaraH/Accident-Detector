/**
 * TITAN // Tactical Incident & Fire Detector - PWA Core Controller
 * Manejo de WebSockets, Telemetría Táctica, Audio Sintetizado,
 * Enlace de Cámara de Smartphone (Uplink), PWA Install y Service Worker.
 */

// --- 1. Textos Multilingües (i18n) ---
const I18N_DICTIONARY = {
  es: {
    sub: "CENTRO TÁCTICO DE DETECCIÓN VIAL & INCENDIOS",
    status_live: "EN VIVO",
    src_label: "FUENTE",
    install: "INSTALAR PWA",
    pause: "PAUSAR",
    resume: "REANUDAR",
    upload_video: "SUBIR VIDEO",
    camera_active: "DETENER CÁMARA",
    camera_stopped: "ACTIVAR CÁMARA",
    motion_lbl: "ENERGÍA:",
    card_veh: "VEHÍCULOS",
    card_ped: "PEATONES",
    card_fire: "FUEGO",
    card_smoke: "HUMO",
    card_inc: "SINIESTROS",
    card_plates: "PLACAS (ALPR)",
    plates_title: "CONSULTA VEHICULAR & PLACAS",
    enrich_title: "CONTEXTO SITUACIONAL (APIs)",
    ctrl_title: "CONFIGURACIÓN & SENSIBILIDAD",
    vehicle_sens: "Sensibilidad de Vehículos:",
    fire_sens: "Sensibilidad de Fuego:",
    smoke_sens: "Sensibilidad de Humo:",
    tracking_title: "ENTIDADES EN RASTREO ACTIVO",
    blackbox_title: "REGISTRO DE SINIESTROS & ALARMAS",
    no_entities: "Buscando entidades en el campo visual...",
    no_incidents: "Sin anomalías críticas registradas. Sistema seguro.",
    safe: "SEGURO",
    alert: "ALERTA",
    connecting: "INICIANDO CÁMARA & MOTOR DE INFERENCIA IA...",
  },
  en: {
    sub: "TACTICAL ROAD INCIDENT & FIRE DETECTION HUB",
    status_live: "LIVE",
    src_label: "SOURCE",
    install: "INSTALL PWA",
    pause: "PAUSE",
    resume: "RESUME",
    upload_video: "UPLOAD VIDEO",
    camera_active: "STOP CAMERA",
    camera_stopped: "START CAMERA",
    motion_lbl: "MOTION:",
    card_veh: "VEHICLES",
    card_ped: "PEDESTRIANS",
    card_fire: "FIRE",
    card_smoke: "SMOKE",
    card_inc: "INCIDENTS",
    card_plates: "PLATES (ALPR)",
    plates_title: "VEHICLE & PLATE LOOKUP",
    enrich_title: "SITUATIONAL CONTEXT (APIs)",
    ctrl_title: "SETTINGS & SENSITIVITY",
    vehicle_sens: "Vehicle Sensitivity:",
    fire_sens: "Fire Sensitivity:",
    smoke_sens: "Smoke Sensitivity:",
    tracking_title: "ACTIVE TRACKED ENTITIES",
    blackbox_title: "INCIDENTS & FLIGHT RECORDER",
    no_entities: "Scanning for entities in viewport...",
    no_incidents: "No critical anomalies logged. Perimeter safe.",
    safe: "SAFE",
    alert: "ALERT",
    connecting: "INITIALIZING CAMERA & AI INFERENCE CORE...",
  }
};

let currentLang = localStorage.getItem("titan_lang") || "es";
let isAudioEnabled = localStorage.getItem("titan_audio") !== "false";
let isPaused = false;
let deferredPrompt = null;
let wsTelemetry = null;
let wsUplink = null;
let clientVideoStream = null;
let uplinkInterval = null;
let lastIncidentId = 0;
let audioContext = null;

// --- 2. Registro del Service Worker y PWA Install Prompt ---
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((reg) => console.log('[PWA] Service Worker registrado:', reg.scope))
      .catch((err) => console.warn('[PWA] Fallo al registrar Service Worker:', err));
  });
}

const btnInstall = document.getElementById('btn-pwa-install');
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  if (btnInstall) btnInstall.style.display = 'inline-flex';
});

if (btnInstall) {
  btnInstall.addEventListener('click', async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      console.log('[PWA] Opción de instalación seleccionada:', outcome);
      deferredPrompt = null;
      btnInstall.style.display = 'none';
    }
  });
}

// --- 3. Motor de Audio Sintetizado (Web Audio API) ---
function initAudio() {
  if (!audioContext) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (AudioCtx) {
      audioContext = new AudioCtx();
    }
  }
  if (audioContext && audioContext.state === 'suspended') {
    audioContext.resume();
  }
}

function playTacticalChirp() {
  if (!isAudioEnabled) return;
  initAudio();
  if (!audioContext) return;

  const osc = audioContext.createOscillator();
  const gain = audioContext.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(800, audioContext.currentTime);
  osc.frequency.exponentialRampToValueAtTime(1400, audioContext.currentTime + 0.08);

  gain.gain.setValueAtTime(0.12, audioContext.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.08);

  osc.connect(gain);
  gain.connect(audioContext.destination);

  osc.start();
  osc.stop(audioContext.currentTime + 0.09);
}

function playEmergencySiren() {
  if (!isAudioEnabled) return;
  initAudio();
  if (!audioContext) return;

  const osc = audioContext.createOscillator();
  const gain = audioContext.createGain();
  osc.type = 'sawtooth';
  const now = audioContext.currentTime;

  // Modulación dual de sirena táctica (800Hz a 1200Hz)
  osc.frequency.setValueAtTime(750, now);
  osc.frequency.linearRampToValueAtTime(1150, now + 0.25);
  osc.frequency.linearRampToValueAtTime(750, now + 0.5);

  gain.gain.setValueAtTime(0.2, now);
  gain.gain.exponentialRampToValueAtTime(0.02, now + 0.5);

  osc.connect(gain);
  gain.connect(audioContext.destination);

  osc.start();
  osc.stop(now + 0.52);

  // Vibración háptica en móviles si está disponible
  if ('vibrate' in navigator) {
    navigator.vibrate([200, 100, 200]);
  }
}

// --- 4. Enlace de Telemetría Táctica (WebSocket + HTTP Polling Fallback) ---
let httpTelemetryInterval = null;
let pendingTelemetry = null;
let telemetryRafId = null;

function handleTelemetryIncoming(data) {
  pendingTelemetry = data;
  if (!telemetryRafId) {
    telemetryRafId = requestAnimationFrame(() => {
      telemetryRafId = null;
      if (pendingTelemetry) {
        updateTelemetryUI(pendingTelemetry);
        pendingTelemetry = null;
      }
    });
  }
}

function startHttpTelemetryPolling() {
  if (httpTelemetryInterval) return;
  httpTelemetryInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        handleTelemetryIncoming(data);
        document.getElementById('stream-loader').classList.add('hidden');
      }
    } catch (e) {
      console.debug('[HTTP Telemetry] Esperando enlace...');
    }
  }, 1000); // 1000ms evita saturar la red mientras se conecta el WebSocket
}

function stopHttpTelemetryPolling() {
  if (httpTelemetryInterval) {
    clearInterval(httpTelemetryInterval);
    httpTelemetryInterval = null;
  }
}

function connectTelemetryWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

  // Arrancar polling HTTP inmediato como salvaguarda
  startHttpTelemetryPolling();

  try {
    wsTelemetry = new WebSocket(wsUrl);

    wsTelemetry.onopen = () => {
      console.log('[WS] Enlace de telemetría conectado.');
      stopHttpTelemetryPolling();
      document.getElementById('stream-loader').classList.add('hidden');
      // Sincronizar idioma actual con el servidor
      sendControl({ action: 'set_lang', lang: currentLang });
    };

    wsTelemetry.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleTelemetryIncoming(data);
      } catch (err) {
        console.error('[WS] Error parseando telemetría:', err);
      }
    };

    wsTelemetry.onclose = () => {
      console.warn('[WS] Telemetría desconectada. Activando polling HTTP de respaldo...');
      startHttpTelemetryPolling();
      setTimeout(connectTelemetryWebSocket, 3000);
    };

    wsTelemetry.onerror = (err) => {
      console.warn('[WS] Advertencia de socket:', err);
      startHttpTelemetryPolling();
    };
  } catch (err) {
    console.warn('[WS] No se pudo inicializar WebSocket, usando HTTP fallback:', err);
    startHttpTelemetryPolling();
  }
}

async function sendControl(payload) {
  if (wsTelemetry && wsTelemetry.readyState === WebSocket.OPEN) {
    wsTelemetry.send(JSON.stringify(payload));
  } else {
    try {
      await fetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      console.warn('[HTTP Control] Error enviando control:', err);
    }
  }
}

// --- 5. Actualización de Interfaz y Telemetría en Vivo ---
function updateTelemetryUI(data) {
  // Ocultar pantalla de carga al recibir cualquier telemetría válida
  const loader = document.getElementById('stream-loader');
  if (loader) loader.classList.add('hidden');

  // FPS y Fuente
  const fpsElem = document.getElementById('metric-fps');
  if (fpsElem) fpsElem.textContent = data.fps ? data.fps.toFixed(1) : '0.0';
  const srcElem = document.getElementById('metric-source');
  if (srcElem) srcElem.textContent = (data.source || '0').toUpperCase();

  // Contadores
  const counts = data.counts || {};
  const vehElem = document.getElementById('metric-vehicles-count');
  if (vehElem) vehElem.textContent = counts.vehicles || 0;
  const pedElem = document.getElementById('metric-persons-count');
  if (pedElem) pedElem.textContent = counts.persons || 0;
  const incElem = document.getElementById('metric-incidents-count');
  if (incElem) incElem.textContent = counts.incidents || 0;

  // Estado Fuego (Independiente)
  const fireCount = counts.fire || 0;
  const cardFire = document.getElementById('card-fire');
  const fireStatus = document.getElementById('metric-fire-status');
  if (cardFire && fireStatus) {
    if (fireCount > 0) {
      cardFire.classList.add('danger-active');
      fireStatus.textContent = `${fireCount} DETECTADO`;
    } else {
      cardFire.classList.remove('danger-active');
      fireStatus.textContent = '0';
    }
  }

  // Estado Humo (Independiente)
  const smokeCount = counts.smoke || 0;
  const cardSmoke = document.getElementById('card-smoke');
  const smokeStatus = document.getElementById('metric-smoke-status');
  if (cardSmoke && smokeStatus) {
    if (smokeCount > 0) {
      cardSmoke.classList.add('smoke-active');
      smokeStatus.textContent = `${smokeCount} DETECTADO`;
    } else {
      cardSmoke.classList.remove('smoke-active');
      smokeStatus.textContent = '0';
    }
  }

  // Placas Detectadas
  const platesCountElem = document.getElementById('metric-plates-count');
  if (platesCountElem) {
    platesCountElem.textContent = counts.plates || (data.plates ? data.plates.length : 0);
  }

  // Feed de Placas en Vivo
  if (data.plates) {
    renderRecentPlatesFeed(data.plates);
  }

  // Energía Óptica (0% a 100%)
  const motionEnergy = data.motion_energy || 0.0;
  const motionPct = Math.min(100, Math.round(motionEnergy * 100));
  const motionValElem = document.getElementById('motion-val');
  if (motionValElem) motionValElem.textContent = `${motionPct}%`;
  const motionBarElem = document.getElementById('motion-bar-fill');
  if (motionBarElem) motionBarElem.style.width = `${Math.max(5, motionPct)}%`;

  // Banner de Alerta Activa con control de estado (evita re-renderizado repetitivo)
  const banner = document.getElementById('emergency-banner');
  if (banner) {
    if (data.active_alert) {
      const alertKey = `${data.active_alert.title}|${data.active_alert.subtitle}|${data.active_alert.is_smoke}`;
      if (banner.dataset.lastAlert !== alertKey) {
        banner.dataset.lastAlert = alertKey;
        banner.style.display = 'flex';
        const titleElem = document.getElementById('banner-title');
        if (titleElem) titleElem.textContent = data.active_alert.title || "ALERTA CONFIRMADA";
        const subElem = document.getElementById('banner-subtitle');
        if (subElem) subElem.textContent = data.active_alert.subtitle || "";
        const bannerIcon = document.getElementById('banner-icon-lucide');
        if (bannerIcon) {
          bannerIcon.setAttribute('data-lucide', data.active_alert.is_smoke ? 'wind' : 'alert-triangle');
          if (window.lucide && typeof lucide.createIcons === 'function') {
            lucide.createIcons({ root: banner });
          }
        }
        if (data.active_alert.is_smoke) {
          banner.classList.add('smoke-only');
        } else {
          banner.classList.remove('smoke-only');
        }
        playEmergencySiren();
      }
    } else {
      if (banner.dataset.lastAlert) {
        banner.style.display = 'none';
        delete banner.dataset.lastAlert;
      }
    }
  }

  // Lista de Entidades en Tránsito
  renderEntitiesList(data.entities || []);

  // Dibujar cajas y alertas de IA sobre la cámara local en vivo
  drawTacticalOverlay(data);
}

// Iconos SVG inline ultra-ligeros (0ms de overhead, cero layout thrashing)
const SVG_ICONS = {
  user: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  car: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px"><path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/></svg>`,
  scan: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/></svg>`,
};

let lastEntitiesSignature = null;
function renderEntitiesList(entities) {
  const container = document.getElementById('entities-list');
  if (!container) return;
  const activeCount = document.getElementById('active-tracked-count');
  if (activeCount) activeCount.textContent = `${entities.length} activas`;

  if (entities.length === 0) {
    if (lastEntitiesSignature !== "empty") {
      lastEntitiesSignature = "empty";
      container.innerHTML = `<div class="empty-state">${I18N_DICTIONARY[currentLang].no_entities}</div>`;
    }
    return;
  }

  // Comprobar si el estado cambió antes de tocar el DOM
  const sig = entities.map((e) => `${e.id}:${e.speed}:${e.plate || ''}`).join('|');
  if (sig === lastEntitiesSignature) return;
  lastEntitiesSignature = sig;

  let html = '';
  entities.forEach((ent) => {
    const isPerson = (ent.raw_class || '').toLowerCase() in { persona: 1, person: 1 };
    const isSpeeding = ent.speed > 50.0;
    const typeClass = isPerson ? 'person' : (isSpeeding ? 'speeding' : '');
    const iconSvg = isPerson ? SVG_ICONS.user : SVG_ICONS.car;
    const plateHtml = ent.plate ? `<span class="chip-plate-tag">[${ent.plate}]</span>` : '';

    html += `
      <div class="entity-chip ${typeClass}">
        <span>${iconSvg} #${ent.id} ${ent.class} ${plateHtml}</span>
        <span class="speed-tag">${ent.speed} km/h</span>
      </div>
    `;
  });
  container.innerHTML = html;
}

// Render del Feed de Placas Detectadas en Vivo con diffing
let lastPlatesSignature = null;
function renderRecentPlatesFeed(plates) {
  const container = document.getElementById('recent-plates-feed');
  const countBadge = document.getElementById('plates-live-count');
  if (countBadge) countBadge.textContent = plates.length;

  if (!plates || plates.length === 0) {
    if (lastPlatesSignature !== "empty") {
      lastPlatesSignature = "empty";
      container.innerHTML = `<div class="empty-state">No se han detectado placas aún en la escena.</div>`;
    }
    return;
  }

  const sig = plates.map((p) => `${p.plate}:${p.confidence}`).join('|');
  if (sig === lastPlatesSignature) return;
  lastPlatesSignature = sig;

  let html = '';
  plates.forEach((p) => {
    const v = p.vehicle_data || {};
    const thumbHtml = p.thumbnail
      ? `<img src="${p.thumbnail}" class="plate-feed-thumb" alt="${p.plate}">`
      : `<span class="thumb-placeholder">${SVG_ICONS.scan}</span>`;

    html += `
      <div class="plate-feed-item" onclick="lookupPlate('${p.plate}')" title="Click para ver expediente completo">
        <div class="plate-feed-left">
          ${thumbHtml}
          <div>
            <div class="plate-feed-tag">${p.plate}</div>
            <div class="plate-feed-veh">${v.brand || 'Vehículo'} ${v.model || ''}</div>
          </div>
        </div>
        <span class="alpr-model-tag">${Math.round(p.confidence * 100)}%</span>
      </div>
    `;
  });
  container.innerHTML = html;
}

// Consulta de Placa vía API REST
async function lookupPlate(plateNumber) {
  playTacticalChirp();
  const input = document.getElementById('plate-search-input');
  if (input) input.value = plateNumber;

  try {
    const res = await fetch('/api/plates/lookup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plate: plateNumber }),
    });

    if (res.ok) {
      const data = await res.json();
      renderVehicleDossier(data);
    }
  } catch (err) {
    console.warn('Error consultando placa:', err);
  }
}

// Renderizado del Expediente de Vehículo (Dossier)
function renderVehicleDossier(data) {
  const dossier = document.getElementById('vehicle-dossier');
  if (!dossier) return;

  dossier.style.display = 'flex';
  document.getElementById('dossier-plate').textContent = data.plate || data.raw_plate || '---';

  const stolenBadge = document.getElementById('dossier-stolen');
  if (data.is_stolen) {
    stolenBadge.innerHTML = `<i data-lucide="shield-alert"></i> REPORTE DE ROBO ACTIVO`;
    stolenBadge.classList.add('stolen-alert');
  } else {
    stolenBadge.innerHTML = `<i data-lucide="shield-check"></i> ` + (data.stolen_status || "SIN REPORTE DE ROBO");
    stolenBadge.classList.remove('stolen-alert');
  }

  document.getElementById('dossier-make-model').textContent = `${data.brand || '---'} ${data.model || ''}`;
  document.getElementById('dossier-year-color').textContent = `${data.year || '---'} | ${data.color || '---'}`;
  document.getElementById('dossier-fuel').textContent = data.fuel_type || 'Gasolina';
  document.getElementById('dossier-jurisdiction').textContent = data.jurisdiction || 'México';

  const hazmatAlert = document.getElementById('dossier-hazmat-alert');
  if (data.hazmat_alert) {
    hazmatAlert.style.display = 'block';
    hazmatAlert.textContent = data.hazmat_alert;
  } else {
    hazmatAlert.style.display = 'none';
  }
  if (window.lucide) lucide.createIcons();
}

// Variable global para coordenadas obtenidas por GPS en el navegador
let userCoords = null;

function requestUserLocation() {
  // Carga inicial inmediata de contexto situacional sin esperar al GPS
  loadSituationalContext();

  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        userCoords = {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude
        };
        console.log('[GPS] Ubicación física autorizada por usuario:', userCoords);
        loadSituationalContext();
      },
      (err) => {
        console.debug('[GPS] Ubicación no concedida:', err.message);
      },
      { timeout: 3000, enableHighAccuracy: false, maximumAge: 60000 }
    );
  }
}

// Consulta de Contexto Situacional (Clima & Ubicación)
async function loadSituationalContext() {
  try {
    const query = userCoords ? `?lat=${userCoords.lat}&lon=${userCoords.lon}` : '';
    const res = await fetch(`/api/enrichment/context${query}`);
    if (res.ok) {
      const data = await res.json();
      const w = data.weather || {};
      const loc = data.location || {};

      const locElem = document.getElementById('enrich-location');
      if (locElem) {
        locElem.textContent = loc.street || loc.city || loc.address || 'Ubicación activa';
        locElem.title = loc.address || '';
      }

      const tempElem = document.getElementById('enrich-temp');
      if (tempElem && w.temperature_c !== undefined) tempElem.textContent = `${w.temperature_c}°C (${w.description || 'Despejado'})`;

      const windElem = document.getElementById('enrich-wind');
      if (windElem && w.wind_speed_kmh !== undefined) windElem.textContent = `${w.wind_speed_kmh} km/h`;

      const pavElem = document.getElementById('enrich-pavement');
      if (pavElem && w.pavement_risk) pavElem.textContent = w.pavement_risk;
    }
  } catch (err) {
    console.warn('Error cargando contexto situacional:', err);
  }
}

// Carga inicial y actualización de bitácora histórica
async function loadIncidentsHistory() {
  try {
    const res = await fetch('/api/incidents');
    if (res.ok) {
      const list = await res.json();
      renderIncidentTimeline(list);
    }
  } catch (e) {
    console.warn('No se pudo obtener bitácora:', e);
  }
}

function renderIncidentTimeline(incidents) {
  const container = document.getElementById('incident-timeline');
  if (!incidents || incidents.length === 0) {
    container.innerHTML = `<div class="empty-state">${I18N_DICTIONARY[currentLang].no_incidents}</div>`;
    return;
  }

  let html = '';
  incidents.forEach((item) => {
    const isSmoke = item.type === 'humo_detectado';
    const plateHtml = item.plate
      ? `<span class="chip-plate-tag" style="display:inline-flex; align-items:center; gap:3px; margin-left:6px;"><i data-lucide="scan-line"></i> ${item.plate}</span>`
      : '';
    html += `
      <div class="timeline-item ${isSmoke ? 'smoke-item' : ''}">
        <div class="item-main">
          <span class="item-title">${item.title} ${plateHtml}</span>
          <span class="item-sub">${item.subtitle}</span>
        </div>
        <span class="item-time">${item.timestamp}</span>
      </div>
    `;
  });
  container.innerHTML = html;
  if (window.lucide) lucide.createIcons();
}

function showSystemToast(msg) {
  let toast = document.getElementById('tactical-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'tactical-toast';
    toast.className = 'tactical-toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add('show');
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => {
    toast.classList.remove('show');
  }, 5000);
}

// --- 6. Enlace de Subida de Cámara del Dispositivo (Uplink Dual: WebSocket + HTTP POST) ---
let currentFacingMode = 'environment';
let isCameraActive = false;
let isFlippingCamera = false;

function drawTacticalOverlay(data) {
  const overlayCanvas = document.getElementById('tactical-canvas-overlay');
  if (!overlayCanvas) return;
  const ctx = overlayCanvas.getContext('2d');
  if (!ctx) return;

  if (!isCameraActive) {
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    return;
  }

  const videoElem = document.getElementById('client-webcam');
  if (!videoElem) return;

  const rect = videoElem.getBoundingClientRect();
  const width = Math.round(rect.width) || overlayCanvas.clientWidth || 640;
  const height = Math.round(rect.height) || overlayCanvas.clientHeight || 480;

  if (overlayCanvas.width !== width || overlayCanvas.height !== height) {
    overlayCanvas.width = width;
    overlayCanvas.height = height;
  }

  ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

  const scaleX = width / 640;
  const scaleY = height / 480;

  // 1. Entidades (vehículos, personas)
  const entities = data.entities || [];
  entities.forEach((ent) => {
    if (!ent.box || ent.box.length < 4) return;
    const [x1, y1, x2, y2] = ent.box;
    const bx = x1 * scaleX;
    const by = y1 * scaleY;
    const bw = (x2 - x1) * scaleX;
    const bh = (y2 - y1) * scaleY;

    const isPerson = (ent.raw_class || '').toLowerCase() in { persona: 1, person: 1 };
    const isSpeeding = ent.speed > 50.0;
    const boxColor = isPerson ? '#00ffd5' : (isSpeeding ? '#ff3b30' : '#00f0ff');

    // Recuadro táctico con esquinas reforzadas
    ctx.lineWidth = 2;
    ctx.strokeStyle = boxColor;
    ctx.strokeRect(bx, by, bw, bh);

    // Etiqueta superior
    const labelText = isPerson
      ? `PEATÓN #${ent.id}`
      : `${(ent.class || 'VEHÍCULO').toUpperCase()} ${ent.speed ? ent.speed + ' km/h' : ''}`;

    ctx.font = 'bold 11px "JetBrains Mono", monospace';
    const textWidth = ctx.measureText(labelText).width;
    ctx.fillStyle = 'rgba(8, 14, 26, 0.85)';
    ctx.fillRect(bx, Math.max(0, by - 18), textWidth + 10, 18);
    ctx.strokeStyle = boxColor;
    ctx.strokeRect(bx, Math.max(0, by - 18), textWidth + 10, 18);

    ctx.fillStyle = boxColor;
    ctx.fillText(labelText, bx + 5, Math.max(12, by - 5));
  });

  // 2. Fuego y Humo
  const fireSmoke = data.fire_smoke || [];
  fireSmoke.forEach((fs) => {
    if (!fs.box || fs.box.length < 4) return;
    const [x1, y1, x2, y2] = fs.box;
    const bx = x1 * scaleX;
    const by = y1 * scaleY;
    const bw = (x2 - x1) * scaleX;
    const bh = (y2 - y1) * scaleY;

    const isFire = fs.type === 'fire';
    const boxColor = isFire ? '#ff2a5f' : '#ff9800';

    ctx.lineWidth = 2.5;
    ctx.strokeStyle = boxColor;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(bx, by, bw, bh);
    ctx.setLineDash([]);

    const labelText = isFire ? '🔥 FUEGO' : '💨 HUMO';
    ctx.font = 'bold 11px "JetBrains Mono", monospace';
    const textWidth = ctx.measureText(labelText).width;
    ctx.fillStyle = 'rgba(255, 42, 95, 0.9)';
    ctx.fillRect(bx, Math.max(0, by - 18), textWidth + 10, 18);

    ctx.fillStyle = '#ffffff';
    ctx.fillText(labelText, bx + 5, Math.max(12, by - 5));
  });
}

function startHttpUplinkFallback(videoElem, canvas, ctx) {
  if (uplinkInterval) clearInterval(uplinkInterval);
  let isSending = false;
  uplinkInterval = setInterval(() => {
    if (!clientVideoStream || isSending || !isCameraActive || isFlippingCamera) return;
    if (videoElem.readyState < 2 || videoElem.videoWidth === 0) return;

    try {
      ctx.drawImage(videoElem, 0, 0, canvas.width, canvas.height);
      isSending = true;
      canvas.toBlob(async (blob) => {
        if (!blob || !clientVideoStream || !isCameraActive || isFlippingCamera) {
          isSending = false;
          return;
        }
        try {
          await fetch('/api/client-frame', {
            method: 'POST',
            body: blob,
            headers: { 'Content-Type': 'image/jpeg' },
          });
        } catch (err) {
          console.debug('[HTTP Uplink] Esperando backend...');
        } finally {
          isSending = false;
        }
      }, 'image/jpeg', 0.60);
    } catch (e) {
      isSending = false;
    }
  }, 80); // ~12 FPS
}

async function startDeviceCamera() {
  const loader = document.getElementById('stream-loader');
  const videoElem = document.getElementById('client-webcam');
  const mainStream = document.getElementById('main-stream');
  const tacticalOverlay = document.getElementById('tactical-canvas-overlay');
  const cameraBadge = document.getElementById('camera-live-badge');
  const canvas = document.getElementById('client-canvas');
  const ctx = canvas.getContext('2d');

  if (loader) loader.classList.remove('hidden');

  try {
    if (clientVideoStream) {
      clientVideoStream.getTracks().forEach((track) => track.stop());
      clientVideoStream = null;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      let errDetail = "Cámara no disponible en este dispositivo.";
      if (!isLocal && window.location.protocol !== 'https:') {
        errDetail = "El navegador bloquea la cámara en HTTP móvil. Conéctate vía HTTPS o habilita la bandera en chrome://flags/#unsafely-treat-insecure-origin-as-secure. Se activa modo demostración.";
      }
      console.warn(errDetail);
      showSystemToast(errDetail);
      sendControl({ action: 'set_source', source: 'vehicles.mp4' });
      stopDeviceCamera(false);
      return;
    }

    let stream = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: currentFacingMode },
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
        audio: false,
      });
    } catch (camErr) {
      console.warn("Fallo con facingMode, intentando cualquier cámara:", camErr);
      stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });
    }

    clientVideoStream = stream;

    // Configuración robusta para navegadores móviles y desktop
    videoElem.muted = true;
    videoElem.playsInline = true;
    videoElem.autoplay = true;
    videoElem.setAttribute('playsinline', '');
    videoElem.setAttribute('webkit-playsinline', '');
    videoElem.srcObject = stream;

    // Mantener visible el stream con los recuadros de IA (peatones en verde, fuego en rojo, placas)
    if (mainStream) {
      mainStream.style.display = 'block';
      mainStream.src = `/api/stream?t=${Date.now()}`;
    }
    // videoElem opera en segundo plano para captura y envío de frames
    videoElem.style.display = 'none';
    videoElem.classList.remove('active');
    if (tacticalOverlay) {
      tacticalOverlay.style.display = 'none';
      tacticalOverlay.classList.remove('active');
    }
    if (cameraBadge) cameraBadge.style.display = 'flex';

    await videoElem.play().catch((playErr) => {
      console.warn("Auto-play requirió interacción:", playErr);
    });

    // Esperar a que el hardware de video inicialice dimensiones reales
    if (videoElem.readyState < 2 || videoElem.videoWidth === 0) {
      await new Promise((resolve) => {
        const onReady = () => {
          videoElem.removeEventListener('loadeddata', onReady);
          videoElem.removeEventListener('canplay', onReady);
          resolve();
        };
        videoElem.addEventListener('loadeddata', onReady, { once: true });
        videoElem.addEventListener('canplay', onReady, { once: true });
        setTimeout(resolve, 500);
      });
    }

    isCameraActive = true;
    if (loader) loader.classList.add('hidden');

    const btnCam = document.getElementById('btn-toggle-camera');
    const btnText = document.getElementById('camera-btn-text');
    const iconElem = document.getElementById('camera-icon-lucide');
    if (btnCam) btnCam.classList.add('danger-active');
    if (btnText) btnText.textContent = I18N_DICTIONARY[currentLang].camera_active || "DETENER CÁMARA";
    if (iconElem) iconElem.setAttribute('data-lucide', 'camera-off');
    if (window.lucide) lucide.createIcons();

    canvas.width = 640;
    canvas.height = 480;

    const selSource = document.getElementById('select-video-source');
    if (selSource) selSource.value = 'client_cam';

    sendControl({ action: 'set_source', source: 'client_cam' });

    // WebSocket Uplink
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUplinkUrl = `${protocol}//${window.location.host}/ws/uplink`;

    try {
      if (wsUplink) {
        wsUplink.close();
        wsUplink = null;
      }
      wsUplink = new WebSocket(wsUplinkUrl);
      wsUplink.binaryType = 'arraybuffer';

      wsUplink.onopen = () => {
        console.log('[Uplink] Cámara conectada vía WebSocket.');
        if (uplinkInterval) clearInterval(uplinkInterval);
        uplinkInterval = setInterval(() => {
          if (
            wsUplink &&
            wsUplink.readyState === WebSocket.OPEN &&
            clientVideoStream &&
            isCameraActive &&
            !isFlippingCamera
          ) {
            if (videoElem.readyState < 2 || videoElem.videoWidth === 0) return;
            // Throttling adaptativo
            if (wsUplink.bufferedAmount > 0) return;

            ctx.drawImage(videoElem, 0, 0, canvas.width, canvas.height);
            canvas.toBlob((blob) => {
              if (
                blob &&
                wsUplink &&
                wsUplink.readyState === WebSocket.OPEN &&
                isCameraActive &&
                !isFlippingCamera
              ) {
                blob.arrayBuffer().then((buf) => wsUplink.send(buf));
              }
            }, 'image/jpeg', 0.60);
          }
        }, 55); // ~18 FPS estable
      };

      wsUplink.onclose = () => {
        if (clientVideoStream && isCameraActive && !isFlippingCamera) {
          startHttpUplinkFallback(videoElem, canvas, ctx);
        }
      };

      wsUplink.onerror = () => {
        if (clientVideoStream && isCameraActive && !isFlippingCamera) {
          startHttpUplinkFallback(videoElem, canvas, ctx);
        }
      };
    } catch (wsErr) {
      startHttpUplinkFallback(videoElem, canvas, ctx);
    }
  } catch (err) {
    console.warn("No se pudo iniciar la cámara del dispositivo:", err);
    let errMsg = "No se pudo acceder a la cámara.";
    if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
      errMsg = "Permiso de cámara denegado en el navegador.";
    } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
      errMsg = "No se detectó cámara física conectada.";
    } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
      errMsg = "La cámara ya está siendo usada por otra aplicación.";
    }
    showSystemToast(errMsg + " Activando modo demostración...");
    stopDeviceCamera(true);
  }
}

function stopDeviceCamera(fallbackToDemo = true) {
  isCameraActive = false;
  isFlippingCamera = false;
  if (uplinkInterval) {
    clearInterval(uplinkInterval);
    uplinkInterval = null;
  }
  if (wsUplink) {
    wsUplink.close();
    wsUplink = null;
  }
  if (clientVideoStream) {
    clientVideoStream.getTracks().forEach((track) => track.stop());
    clientVideoStream = null;
  }

  const videoElem = document.getElementById('client-webcam');
  const mainStream = document.getElementById('main-stream');
  const tacticalOverlay = document.getElementById('tactical-canvas-overlay');
  const cameraBadge = document.getElementById('camera-live-badge');

  if (videoElem) {
    videoElem.srcObject = null;
    videoElem.style.display = 'none';
    videoElem.classList.remove('active');
  }

  if (tacticalOverlay) {
    tacticalOverlay.style.display = 'none';
    tacticalOverlay.classList.remove('active');
    const ctx = tacticalOverlay.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, tacticalOverlay.width, tacticalOverlay.height);
  }

  if (cameraBadge) cameraBadge.style.display = 'none';

  // Reanudar visualización del video stream del servidor
  if (mainStream) {
    mainStream.style.display = 'block';
    mainStream.src = `/api/stream?t=${Date.now()}`;
  }

  const btnCam = document.getElementById('btn-toggle-camera');
  const btnText = document.getElementById('camera-btn-text');
  const iconElem = document.getElementById('camera-icon-lucide');
  if (btnCam) btnCam.classList.remove('danger-active');
  if (btnText) btnText.textContent = I18N_DICTIONARY[currentLang].camera_stopped || "ACTIVAR CÁMARA";
  if (iconElem) iconElem.setAttribute('data-lucide', 'camera');
  if (window.lucide) lucide.createIcons();

  if (fallbackToDemo) {
    const selSource = document.getElementById('select-video-source');
    if (selSource) selSource.value = 'vehicles.mp4';
    sendControl({ action: 'set_source', source: 'vehicles.mp4' });
  }
}

async function flipDeviceCamera() {
  if (!isCameraActive || isFlippingCamera) return;
  isFlippingCamera = true;
  playTacticalChirp();
  currentFacingMode = currentFacingMode === 'environment' ? 'user' : 'environment';
  showSystemToast(`Cambiando a cámara ${currentFacingMode === 'environment' ? 'trasera' : 'frontal'}...`);

  const videoElem = document.getElementById('client-webcam');
  try {
    if (clientVideoStream) {
      clientVideoStream.getTracks().forEach((track) => track.stop());
      clientVideoStream = null;
    }
    await new Promise((resolve) => setTimeout(resolve, 180));

    const newStream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: currentFacingMode },
        width: { ideal: 640 },
        height: { ideal: 480 },
      },
      audio: false,
    });

    clientVideoStream = newStream;
    videoElem.muted = true;
    videoElem.playsInline = true;
    videoElem.autoplay = true;
    videoElem.srcObject = newStream;
    videoElem.style.display = 'none';
    videoElem.classList.remove('active');
    if (mainStream) {
      mainStream.style.display = 'block';
    }
    await videoElem.play().catch(() => {});
    showSystemToast(`Cámara lista: ${currentFacingMode === 'environment' ? 'Trasera' : 'Frontal'}`);
  } catch (err) {
    console.warn("Fallo alternando sensor de cámara:", err);
    showSystemToast("No se pudo alternar el sensor físico de cámara.");
  } finally {
    isFlippingCamera = false;
  }
}

// --- 7. Eventos de Controles e Interacción ---
function setupEventListeners() {
  // Botón Activar / Detener Cámara
  const btnToggleCamera = document.getElementById('btn-toggle-camera');
  if (btnToggleCamera) {
    btnToggleCamera.addEventListener('click', () => {
      playTacticalChirp();
      if (isCameraActive) {
        stopDeviceCamera(true);
      } else {
        startDeviceCamera();
      }
    });
  }

  // Selector de Fuente de Video
  const selectVideoSource = document.getElementById('select-video-source');
  if (selectVideoSource) {
    selectVideoSource.addEventListener('change', async (e) => {
      playTacticalChirp();
      const val = e.target.value;
      if (val === 'client_cam') {
        await startDeviceCamera();
      } else {
        stopDeviceCamera(false);
        sendControl({ action: 'set_source', source: val });
        showSystemToast(`Fuente cambiada a: ${val === '0' ? 'Cámara USB Servidor (0)' : 'Video Demo'}`);
      }
    });
  }

  // Botón Cambiar Cámara Frontal / Trasera
  const btnFlipCamera = document.getElementById('btn-flip-camera');
  if (btnFlipCamera) {
    btnFlipCamera.addEventListener('click', () => {
      playTacticalChirp();
      flipDeviceCamera();
    });
  }

  // Botón Pausa/Reanudar
  const btnPause = document.getElementById('btn-pause-play');
  if (btnPause) {
    btnPause.addEventListener('click', () => {
      playTacticalChirp();
      isPaused = !isPaused;
      sendControl({ action: 'set_pause', paused: isPaused });
      const pauseIcon = document.getElementById('pause-icon-lucide');
      if (pauseIcon) {
        pauseIcon.setAttribute('data-lucide', isPaused ? 'play' : 'pause');
        if (window.lucide && typeof lucide.createIcons === 'function') lucide.createIcons();
      }
      const pauseText = document.getElementById('i18n-pause');
      if (pauseText) {
        pauseText.textContent = isPaused
          ? I18N_DICTIONARY[currentLang].resume
          : I18N_DICTIONARY[currentLang].pause;
      }
    });
  }

  // Sliders de Sensibilidad
  const vehicleSlider = document.getElementById('slider-vehicle-conf');
  const fireSlider = document.getElementById('slider-fire-conf');
  const smokeSlider = document.getElementById('slider-smoke-conf');

  if (vehicleSlider) {
    vehicleSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      const valDisplay = document.getElementById('vehicle-conf-val');
      if (valDisplay) valDisplay.textContent = val.toFixed(2);
      sendControl({ action: 'set_sensitivity', vehicle_conf: val });
    });
  }

  if (fireSlider) {
    fireSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      const valDisplay = document.getElementById('fire-conf-val');
      const tag = val <= 0.20 ? ' (Alta)' : (val <= 0.45 ? ' (Media)' : ' (Baja)');
      if (valDisplay) valDisplay.textContent = val.toFixed(2) + tag;
      sendControl({ action: 'set_sensitivity', fire_conf: val });
    });
  }

  if (smokeSlider) {
    smokeSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      const valDisplay = document.getElementById('smoke-conf-val');
      const tag = val <= 0.20 ? ' (Alta)' : (val <= 0.45 ? ' (Media)' : ' (Baja)');
      if (valDisplay) valDisplay.textContent = val.toFixed(2) + tag;
      sendControl({ action: 'set_sensitivity', smoke_conf: val });
    });
  }

  // Idioma
  const btnToggleLang = document.getElementById('btn-toggle-lang');
  if (btnToggleLang) {
    btnToggleLang.addEventListener('click', () => {
      playTacticalChirp();
      currentLang = currentLang === 'es' ? 'en' : 'es';
      localStorage.setItem("titan_lang", currentLang);
      applyLanguage(currentLang);
      sendControl({ action: 'set_lang', lang: currentLang });
    });
  }

  // Audio Toggle (Lucide)
  const updateAudioIcon = () => {
    const audioIcon = document.getElementById('audio-icon-lucide');
    if (audioIcon) {
      audioIcon.setAttribute('data-lucide', isAudioEnabled ? 'volume-2' : 'volume-x');
      if (window.lucide && typeof lucide.createIcons === 'function') lucide.createIcons();
    }
  };

  const btnAudio = document.getElementById('btn-toggle-audio');
  if (btnAudio) {
    btnAudio.addEventListener('click', () => {
      initAudio();
      isAudioEnabled = !isAudioEnabled;
      localStorage.setItem("titan_audio", isAudioEnabled);
      updateAudioIcon();
      playTacticalChirp();
    });
  }
  updateAudioIcon();

  // Pantalla Completa
  const btnFullscreen = document.getElementById('btn-fullscreen');
  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', () => {
      playTacticalChirp();
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen().catch(() => {});
      }
    });
  }

  // Reconocer banner de alerta
  const btnDismiss = document.getElementById('banner-dismiss');
  if (btnDismiss) {
    btnDismiss.addEventListener('click', () => {
      const banner = document.getElementById('emergency-banner');
      if (banner) banner.style.display = 'none';
    });
  }

  // Limpiar bitácora
  const btnClear = document.getElementById('btn-clear-log');
  if (btnClear) {
    btnClear.addEventListener('click', () => {
      const timeline = document.getElementById('incident-timeline');
      if (timeline) {
        timeline.innerHTML = `<div class="empty-state">${I18N_DICTIONARY[currentLang].no_incidents}</div>`;
      }
    });
  }

  // Consulta manual de Placa
  const btnSearchPlate = document.getElementById('btn-search-plate');
  const plateInput = document.getElementById('plate-search-input');
  if (btnSearchPlate && plateInput) {
    btnSearchPlate.addEventListener('click', () => {
      const val = plateInput.value.trim();
      if (val) lookupPlate(val);
    });
    plateInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const val = plateInput.value.trim();
        if (val) lookupPlate(val);
      }
    });
  }

  // Detección de Placas por subida de foto (Roboflow + OCR)
  const fileInput = document.getElementById('plate-file-input');
  if (fileInput) {
    fileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;

      playTacticalChirp();
      const reader = new FileReader();
      reader.onload = async (ev) => {
        const b64 = ev.target.result;
        try {
          const res = await fetch('/api/plates/detect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_base64: b64 }),
          });
          if (res.ok) {
            const data = await res.json();
            if (data.plates && data.plates.length > 0) {
              renderRecentPlatesFeed(data.plates);
              renderVehicleDossier(data.plates[0].vehicle_data);
              const pInput = document.getElementById('plate-search-input');
              if (pInput) pInput.value = data.plates[0].plate;
            } else {
              alert("No se detectaron placas legibles en la imagen.");
            }
          }
        } catch (err) {
          console.error("Error en detección de placa por imagen:", err);
        }
      };
      reader.readAsDataURL(file);
    });
  }

  // Carga de Video Nuevo en Vivo (Elegido por el juez)
  const videoInput = document.getElementById('video-file-input');
  if (videoInput) {
    videoInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;

      playTacticalChirp();
      showSystemToast(`Cargando video del juez: ${file.name}...`);

      try {
        const res = await fetch('/api/upload-video', {
          method: 'POST',
          headers: {
            'Content-Type': file.type || 'video/mp4',
            'X-Filename': file.name,
          },
          body: file,
        });
        if (res.ok) {
          const data = await res.json();
          stopDeviceCamera(false);
          showSystemToast(`✅ ${data.message || 'Video cargado en vivo.'}`);
          // Refrescar stream
          const mainStream = document.getElementById('main-stream');
          if (mainStream) {
            mainStream.src = `/api/stream?t=${Date.now()}`;
          }
        } else {
          showSystemToast('❌ Error subiendo video. Verifique formato.');
        }
      } catch (err) {
        console.error('Error subiendo video del juez:', err);
        showSystemToast('❌ Error de conexión al subir video.');
      }
    });
  }
}

function updateActiveSourceBtn(source) {
  document.querySelectorAll('.source-btn').forEach((btn) => {
    if (btn.getAttribute('data-source') === source) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

function applyLanguage(lang) {
  const dict = I18N_DICTIONARY[lang] || I18N_DICTIONARY.es;
  const langText = document.getElementById('current-lang-text');
  if (langText) langText.textContent = lang.toUpperCase();

  const sub = document.getElementById('i18n-sub');
  if (sub) sub.textContent = dict.sub;

  const pause = document.getElementById('i18n-pause');
  if (pause) pause.textContent = isPaused ? dict.resume : dict.pause;

  const uploadVid = document.getElementById('i18n-upload-video');
  if (uploadVid) uploadVid.textContent = dict.upload_video;

  const motionLbl = document.getElementById('i18n-motion-lbl');
  if (motionLbl) motionLbl.textContent = dict.motion_lbl;

  const cardVeh = document.getElementById('i18n-card-veh');
  if (cardVeh) cardVeh.textContent = dict.card_veh;

  const cardPed = document.getElementById('i18n-card-ped');
  if (cardPed) cardPed.textContent = dict.card_ped;

  const cardFire = document.getElementById('i18n-card-fire');
  if (cardFire) cardFire.textContent = dict.card_fire;

  const cardSmoke = document.getElementById('i18n-card-smoke');
  if (cardSmoke) cardSmoke.textContent = dict.card_smoke;

  const cardInc = document.getElementById('i18n-card-inc');
  if (cardInc) cardInc.textContent = dict.card_inc;

  const cardPlates = document.getElementById('i18n-card-plates');
  if (cardPlates) cardPlates.textContent = dict.card_plates;

  const platesTitle = document.getElementById('i18n-plates-title');
  if (platesTitle) platesTitle.textContent = dict.plates_title;

  const enrichTitle = document.getElementById('i18n-enrich-title');
  if (enrichTitle) enrichTitle.textContent = dict.enrich_title;

  const ctrlTitle = document.getElementById('i18n-ctrl-title');
  if (ctrlTitle) ctrlTitle.textContent = dict.ctrl_title;

  const vehSens = document.getElementById('i18n-vehicle-sens');
  if (vehSens) vehSens.textContent = dict.vehicle_sens;

  const fireSens = document.getElementById('i18n-fire-sens');
  if (fireSens) fireSens.textContent = dict.fire_sens;

  const smokeSens = document.getElementById('i18n-smoke-sens');
  if (smokeSens) smokeSens.textContent = dict.smoke_sens;

  const trackingTitle = document.getElementById('i18n-tracking-title');
  if (trackingTitle) trackingTitle.textContent = dict.tracking_title;

  const blackboxTitle = document.getElementById('i18n-blackbox-title');
  if (blackboxTitle) blackboxTitle.textContent = dict.blackbox_title;

  const connecting = document.getElementById('i18n-connecting');
  if (connecting) connecting.textContent = dict.connecting;

  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}

// Inicialización de la aplicación (Mobile-First)
document.addEventListener('DOMContentLoaded', () => {
  applyLanguage(currentLang);
  setupEventListeners();

  const mainStream = document.getElementById('main-stream');
  if (mainStream) {
    mainStream.addEventListener('load', () => {
      const loader = document.getElementById('stream-loader');
      if (loader) loader.classList.add('hidden');
    });
    mainStream.addEventListener('error', () => {
      // Reintentar stream tras breve espera si la red móvil reconecta
      setTimeout(() => {
        if (mainStream) mainStream.src = `/api/stream?t=${Date.now()}`;
      }, 2000);
    });
  }

  // Salvaguarda: ocultar loader inicial si la cámara o telemetría tardan unos segundos
  setTimeout(() => {
    const loader = document.getElementById('stream-loader');
    if (loader) loader.classList.add('hidden');
  }, 2200);

  // Inicializar estado del botón de cámara (manual para no interferir entre desktop y móvil)
  const btnCam = document.getElementById('btn-toggle-camera');
  const btnText = document.getElementById('camera-btn-text');
  if (btnCam) btnCam.classList.remove('danger-active');
  if (btnText) btnText.textContent = I18N_DICTIONARY[currentLang].camera_stopped || "ACTIVAR CÁMARA";

  connectTelemetryWebSocket();
  requestUserLocation();
  setInterval(loadIncidentsHistory, 5000);
  setInterval(loadSituationalContext, 30000);
  // Cargar una placa de demostración en el expediente
  lookupPlate('ABC-1234');

  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
});

/**
 * TITAN // Tactical Incident & Fire Detector - PWA Core Controller
 * Manejo de WebSockets, Telemetría Táctica, Audio Sintetizado,
 * Navegación por Sidebar (Home, Enriquecimiento, Historial),
 * Enlace de Cámara de Smartphone (Uplink) y Service Worker.
 */

// --- 1. Textos Multilingües (i18n) ---
const I18N_DICTIONARY = {
  es: {
    sub: "CENTRO TÁCTICO DE DETECCIÓN VIAL & INCENDIOS",
    view_home: "MONITOR TÁCTICO EN VIVO",
    view_enrich: "ENRIQUECIMIENTO & CONSULTA ALPR",
    view_history: "HISTORIAL FORENSE & BACKLOG",
    nav_home: "Home",
    nav_enrich: "Enriquecimiento",
    nav_history: "Historial",
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
    card_plates: "PLACAS",
    sidebar_plates_title: "PLACAS DETECTADAS",
    no_plates: "Sin placas en escena",
    plates_title: "CONSULTA VEHICULAR & PLACAS (ALPR)",
    enrich_title: "CONTEXTO SITUACIONAL & AMBIENTAL",
    ctrl_title: "CONFIGURACIÓN & SENSIBILIDAD",
    vehicle_sens: "Sensibilidad de Vehículos:",
    fire_sens: "Sensibilidad de Fuego:",
    smoke_sens: "Sensibilidad de Humo:",
    tracking_title: "ENTIDADES EN RASTREO ACTIVO",
    blackbox_title: "BITÁCORA FORENSE DE SINIESTROS",
    no_entities: "Buscando entidades en el campo visual...",
    no_incidents: "Sin anomalías críticas registradas. Sistema seguro.",
    safe: "SEGURO",
    alert: "ALERTA",
    connecting: "INICIANDO CÁMARA & MOTOR DE INFERENCIA IA...",
  },
  en: {
    sub: "TACTICAL ROAD INCIDENT & FIRE DETECTION HUB",
    view_home: "LIVE TACTICAL MONITOR",
    view_enrich: "ENRICHMENT & ALPR LOOKUP",
    view_history: "FORENSIC HISTORY & BACKLOG",
    nav_home: "Home",
    nav_enrich: "Enrichment",
    nav_history: "History",
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
    card_plates: "PLATES",
    sidebar_plates_title: "DETECTED PLATES",
    no_plates: "No plates in scene",
    plates_title: "VEHICLE & PLATE LOOKUP (ALPR)",
    enrich_title: "SITUATIONAL & ENVIRONMENTAL CONTEXT",
    ctrl_title: "SETTINGS & SENSITIVITY",
    vehicle_sens: "Vehicle Sensitivity:",
    fire_sens: "Fire Sensitivity:",
    smoke_sens: "Smoke Sensitivity:",
    tracking_title: "ACTIVE TRACKED ENTITIES",
    blackbox_title: "FORENSIC INCIDENT BACKLOG",
    no_entities: "Scanning for entities in viewport...",
    no_incidents: "No critical anomalies logged. Perimeter safe.",
    safe: "SAFE",
    alert: "ALERT",
    connecting: "INITIALIZING CAMERA & AI INFERENCE CORE...",
  }
};

let currentLang = localStorage.getItem("titan_lang") || "es";
let currentView = "home";
let isAudioEnabled = localStorage.getItem("titan_audio") !== "false";
let isPaused = false;
let deferredPrompt = null;
let wsTelemetry = null;
let wsUplink = null;
let clientVideoStream = null;
let uplinkInterval = null;
let lastIncidentId = 0;
let audioContext = null;
let latestTelemetryState = null;

// --- 2. Registro del Service Worker y PWA Install Prompt ---
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js?v=13')
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

// --- 2b. Navegación por Vistas en Sidebar (Home, Enriquecimiento, Historial) ---
function switchAppView(viewName, updateHash = true) {
  const validViews = ['home', 'enriquecimiento', 'historial'];
  const targetView = validViews.includes(viewName) ? viewName : 'home';
  currentView = targetView;

  document.body.setAttribute('data-active-view', targetView);

  const footerControls = document.querySelector('.footer-controls-left');
  if (footerControls) {
    footerControls.style.display = targetView === 'home' ? 'flex' : 'none';
  }

  document.querySelectorAll('.sidebar-nav-item[data-view]').forEach((btn) => {
    const isMatch = btn.getAttribute('data-view') === targetView;
    btn.classList.toggle('active', isMatch);
  });

  document.querySelectorAll('.view-section[data-view-panel]').forEach((panel) => {
    const isMatch = panel.getAttribute('data-view-panel') === targetView;
    panel.classList.toggle('active', isMatch);
  });

  if (updateHash && window.location.pathname === '/') {
    const newHash = targetView === 'home' ? '' : `#${targetView}`;
    if (window.location.hash !== newHash) {
      history.replaceState(null, '', newHash || window.location.pathname);
    }
  }

  // Cerrar drawer en móvil al elegir sección
  const sidebar = document.getElementById('app-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (sidebar) sidebar.classList.remove('open');
  if (backdrop) backdrop.classList.remove('active');

  if (targetView === 'enriquecimiento') {
    loadSituationalContext();
  } else if (targetView === 'historial') {
    loadFullBacklog(false);
  }
}

// --- 3. Motor de Audio (Alarma Sonora Personalizada & Web Audio Fallback) ---
let alarmAudio = null;

function initAudio() {
  if (!alarmAudio) {
    try {
      alarmAudio = new Audio('/static/alarma.mp3');
      alarmAudio.preload = 'auto';
    } catch (e) {
      console.warn("[Audio] Error instanciando Audio:", e);
    }
  }
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

window.addEventListener('click', () => { initAudio(); }, { once: true });
window.addEventListener('touchstart', () => { initAudio(); }, { once: true });

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

function playSynthesizedSirenFallback() {
  if (!audioContext) return;
  const osc = audioContext.createOscillator();
  const gain = audioContext.createGain();
  osc.type = 'sawtooth';
  const now = audioContext.currentTime;

  osc.frequency.setValueAtTime(750, now);
  osc.frequency.linearRampToValueAtTime(1150, now + 0.25);
  osc.frequency.linearRampToValueAtTime(750, now + 0.5);

  gain.gain.setValueAtTime(0.2, now);
  gain.gain.exponentialRampToValueAtTime(0.02, now + 0.5);

  osc.connect(gain);
  gain.connect(audioContext.destination);

  osc.start();
  osc.stop(now + 0.52);
}

function playEmergencySiren() {
  if (!isAudioEnabled) return;
  initAudio();

  let playedCustom = false;
  if (alarmAudio) {
    try {
      alarmAudio.currentTime = 0;
      const playPromise = alarmAudio.play();
      if (playPromise !== undefined) {
        playedCustom = true;
        playPromise.catch((err) => {
          console.warn("[Audio] Falló reproducción de Alarma.mp3, usando sintetizador fallback:", err);
          playSynthesizedSirenFallback();
        });
      }
    } catch (e) {
      console.warn("[Audio] Error al reproducir Alarma.mp3:", e);
    }
  }

  if (!playedCustom) {
    playSynthesizedSirenFallback();
  }

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
        const loader = document.getElementById('stream-loader');
        if (loader) loader.classList.add('hidden');
      }
    } catch (e) {
      console.debug('[HTTP Telemetry] Esperando enlace...');
    }
  }, 1000);
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

  startHttpTelemetryPolling();

  try {
    wsTelemetry = new WebSocket(wsUrl);

    wsTelemetry.onopen = () => {
      console.log('[WS] Enlace de telemetría conectado.');
      stopHttpTelemetryPolling();
      const loader = document.getElementById('stream-loader');
      if (loader) loader.classList.add('hidden');
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
  latestTelemetryState = data;

  const loader = document.getElementById('stream-loader');
  if (loader) loader.classList.add('hidden');

  const fpsElem = document.getElementById('metric-fps');
  if (fpsElem) fpsElem.textContent = data.fps ? data.fps.toFixed(1) : '0.0';
  const srcElem = document.getElementById('metric-source');
  if (srcElem) srcElem.textContent = (data.source || 'STREAM').toUpperCase();

  const videoSelect = document.getElementById('select-video-sample');
  if (videoSelect && data.source && document.activeElement !== videoSelect) {
    const normalizedSrc = String(data.source).replace(/^.*[\\/]/, '');
    const matchingOption = Array.from(videoSelect.options).find(
      (opt) => opt.value.toLowerCase() === normalizedSrc.toLowerCase() || opt.value === data.source
    );
    if (matchingOption && videoSelect.value !== matchingOption.value) {
      videoSelect.value = matchingOption.value;
    }
  }

  const counts = data.counts || {};
  const vehElem = document.getElementById('metric-vehicles-count');
  if (vehElem) vehElem.textContent = counts.vehicles || 0;
  const pedElem = document.getElementById('metric-persons-count');
  if (pedElem) pedElem.textContent = counts.persons || 0;
  const incElem = document.getElementById('metric-incidents-count');
  if (incElem) incElem.textContent = counts.incidents || 0;

  // Estado Fuego
  const fireCount = counts.fire || 0;
  const cardFire = document.getElementById('card-fire');
  const fireStatus = document.getElementById('metric-fire-status');
  if (cardFire && fireStatus) {
    if (fireCount > 0) {
      cardFire.classList.add('danger-active');
      fireStatus.textContent = `${fireCount}`;
    } else {
      cardFire.classList.remove('danger-active');
      fireStatus.textContent = '0';
    }
  }

  // Estado Humo
  const smokeCount = counts.smoke || 0;
  const cardSmoke = document.getElementById('card-smoke');
  const smokeStatus = document.getElementById('metric-smoke-status');
  if (cardSmoke && smokeStatus) {
    if (smokeCount > 0) {
      cardSmoke.classList.add('smoke-active');
      smokeStatus.textContent = `${smokeCount}`;
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

  // Banner de Alerta Activa
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

  renderEntitiesList(data.entities || []);
  drawTacticalOverlay(data);
}

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

  const sig = entities.map((e) => `${e.raw_class || e.class}:${e.speed}:${e.plate || ''}`).join('|');
  if (sig === lastEntitiesSignature) return;
  lastEntitiesSignature = sig;

  const persons = entities.filter((ent) => (ent.raw_class || '').toLowerCase() in { persona: 1, person: 1 });
  const vehicles = entities.filter((ent) => !((ent.raw_class || '').toLowerCase() in { persona: 1, person: 1 }));

  let html = '';

  // Agrupar peatones en un único indicador limpio sin velocidad ni ID innecesario
  if (persons.length > 0) {
    const label = persons.length === 1 ? 'Peatón en escena' : `Peatones (${persons.length})`;
    html += `
      <div class="entity-chip person">
        <span>${SVG_ICONS.user} ${label}</span>
      </div>
    `;
  }

  // Mostrar máximo 2 vehículos en tiempo real y resumir el resto para evitar scrollbars en el sidebar
  const maxVisibleVehicles = persons.length > 0 ? 2 : 3;
  const visibleVehicles = vehicles.slice(0, maxVisibleVehicles);
  const extraVehiclesCount = vehicles.length - visibleVehicles.length;

  visibleVehicles.forEach((ent) => {
    const isSpeeding = ent.speed > 50.0;
    const typeClass = isSpeeding ? 'speeding' : '';
    const plateHtml = ent.plate ? `<span class="chip-plate-tag">[${ent.plate}]</span>` : '';

    html += `
      <div class="entity-chip ${typeClass}">
        <span>${SVG_ICONS.car} ${ent.class} ${plateHtml}</span>
        <span class="speed-tag">${ent.speed} km/h</span>
      </div>
    `;
  });

  if (extraVehiclesCount > 0) {
    html += `
      <div class="entity-chip">
        <span>+${extraVehiclesCount} más</span>
      </div>
    `;
  }

  container.innerHTML = html;
}

let lastPlatesSignature = null;
function renderRecentPlatesFeed(plates) {
  const enrichContainer = document.getElementById('recent-plates-feed');
  const enrichCountBadge = document.getElementById('plates-live-count');
  const sidebarContainer = document.getElementById('sidebar-plates-feed');
  const sidebarCountBadge = document.getElementById('sidebar-plates-count');

  const count = (plates && plates.length) || 0;
  if (enrichCountBadge) enrichCountBadge.textContent = count;
  if (sidebarCountBadge) sidebarCountBadge.textContent = count;

  if (!plates || plates.length === 0) {
    if (lastPlatesSignature !== "empty") {
      lastPlatesSignature = "empty";
      const emptyText = (window.I18N_DICTIONARY && I18N_DICTIONARY[currentLang] && I18N_DICTIONARY[currentLang].no_plates)
        || "Sin placas en escena";
      if (enrichContainer) {
        enrichContainer.innerHTML = `<div class="empty-state">No se han detectado placas aún en la escena.</div>`;
      }
      if (sidebarContainer) {
        sidebarContainer.innerHTML = `<div class="empty-state" id="sidebar-no-plates">${emptyText}</div>`;
      }
    }
    return;
  }

  const sig = plates.map((p) => `${p.plate}:${p.confidence}:${p.thumbnail ? 'thumb' : 'nothumb'}`).join('|');
  if (sig === lastPlatesSignature) return;
  lastPlatesSignature = sig;

  // 1. Render para la sección de Enriquecimiento (Panel ALPR)
  if (enrichContainer) {
    let enrichHtml = '';
    plates.forEach((p) => {
      const v = p.vehicle_data || {};
      const thumbHtml = p.thumbnail
        ? `<img src="${p.thumbnail}" class="plate-feed-thumb" alt="${p.plate}">`
        : `<span class="thumb-placeholder">${SVG_ICONS.scan}</span>`;

      enrichHtml += `
        <div class="plate-feed-item" onclick="lookupPlate('${p.plate}')" title="Clic para consultar expediente vehicular">
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
    enrichContainer.innerHTML = enrichHtml;
  }

  // 2. Render para la Card persistente en el Sidebar (Siempre a la vista de la cámara)
  if (sidebarContainer) {
    let sidebarHtml = '';
    plates.forEach((p) => {
      const v = p.vehicle_data || {};
      const brandModel = (v.brand ? `${v.brand} ${v.model || ''}` : 'Vehículo detectado').trim();
      const thumbHtml = p.thumbnail
        ? `<img src="${p.thumbnail}" class="sidebar-plate-thumb" alt="${p.plate}">`
        : `<span class="sidebar-plate-thumb-placeholder">${SVG_ICONS.scan}</span>`;

      sidebarHtml += `
        <div class="sidebar-plate-item" onclick="selectPlateAndEnrich('${p.plate}')" title="Clic para ver expediente completo en Enriquecimiento">
          <div class="sidebar-plate-left">
            ${thumbHtml}
            <div class="sidebar-plate-meta">
              <span class="sidebar-plate-tag">${p.plate}</span>
              <span class="sidebar-plate-sub">${brandModel}</span>
            </div>
          </div>
          <div class="sidebar-plate-right">
            <span class="sidebar-plate-badge">${Math.round(p.confidence * 100)}%</span>
            <i data-lucide="chevron-right" class="sidebar-plate-arrow"></i>
          </div>
        </div>
      `;
    });
    sidebarContainer.innerHTML = sidebarHtml;
    if (window.lucide && typeof lucide.createIcons === 'function') {
      lucide.createIcons({ root: sidebarContainer });
    }
  }
}

// Navegar a la vista de Enriquecimiento y abrir el expediente de la placa seleccionada
window.selectPlateAndEnrich = async function(plate) {
  playTacticalChirp();
  switchAppView('enriquecimiento', true);
  await lookupPlate(plate);
};

// Consulta de Placa o VIN vía API REST
async function lookupPlate(plateOrVin, switchTab = false) {
  if (!plateOrVin || !plateOrVin.trim()) return;
  const cleanQuery = plateOrVin.trim();
  const input = document.getElementById('plate-search-input');

  playTacticalChirp();
  if (input) input.value = cleanQuery;
  if (switchTab) switchAppView('enriquecimiento', true);

  try {
    const res = await fetch('/api/plates/lookup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: cleanQuery, plate: cleanQuery }),
    });

    if (res.ok) {
      const data = await res.json();
      renderVehicleDossier(data);
    }
  } catch (err) {
    console.warn('Error consultando placa o VIN:', err);
  }
}

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
  const vinElem = document.getElementById('dossier-vin');
  if (vinElem) {
    vinElem.textContent = data.vin || '---';
  }
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

let userCoords = null;

function requestUserLocation() {
  loadSituationalContext();

  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        userCoords = {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude
        };
        loadSituationalContext();
      },
      (err) => {
        console.debug('[GPS] Ubicación no concedida:', err.message);
      },
      { timeout: 3000, enableHighAccuracy: false, maximumAge: 60000 }
    );
  }
}

async function loadSituationalContext() {
  try {
    const query = userCoords ? `?lat=${userCoords.lat}&lon=${userCoords.lon}` : '';
    const res = await fetch(`/api/enrichment/context${query}`);
    if (res.ok) {
      const data = await res.json();
      const w = data.weather || {};
      const loc = data.location || {};
      const hz = data.environmental_hazards || {};

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
      if (pavElem) pavElem.textContent = hz.pavement_status || w.pavement_risk || 'SECO';

      const dispElem = document.getElementById('enrich-dispersion');
      if (dispElem && hz.smoke_dispersion_direction) {
        dispElem.textContent = hz.smoke_dispersion_direction;
      }

      const hazElem = document.getElementById('enrich-hazard');
      if (hazElem && hz.hazard_level) {
        hazElem.textContent = hz.hazard_level;
        const hl = String(hz.hazard_level).toUpperCase();
        hazElem.style.color = hl.includes('CRÍT') || hl.includes('ALTO') ? '#ff285d' : (hl.includes('MOD') ? '#ffb700' : '#00ff9d');
      }

      const msBadge = document.getElementById('ms-status-badge');
      if (msBadge) {
        const isHealthy = data.microservice_status === 'healthy';
        msBadge.textContent = isHealthy ? 'MS: REMOTO ACTIVO' : 'MS: INTEGRADO ACTIVO';
        msBadge.style.color = '#00ff9d';
        msBadge.style.borderColor = 'rgba(0, 255, 157, 0.45)';
      }
    }
  } catch (err) {
    console.warn('Error cargando contexto situacional:', err);
  }
}

async function triggerMicroserviceCadDispatch() {
  playTacticalChirp();
  const plateInput = document.getElementById('plate-search-input');
  const activePlates = (latestTelemetryState && latestTelemetryState.plates) || [];
  const detectedPlate = activePlates.length > 0 ? activePlates[0].plate : null;
  const currentPlate = (plateInput && plateInput.value.trim()) ? plateInput.value.trim() : detectedPlate;

  const activeAlert = latestTelemetryState && latestTelemetryState.active_alert;
  const counts = (latestTelemetryState && latestTelemetryState.counts) || {};
  let incType = 'colision_critica';
  let incTitle = 'INCIDENTE VIAL REPORTADO EN MONITOR';
  let incSubtitle = 'Evaluado por Microservicio de Enriquecimiento & Despacho';

  if (activeAlert) {
    incType = activeAlert.is_smoke ? 'humo_detectado' : 'colision_critica';
    incTitle = activeAlert.title || incTitle;
    incSubtitle = activeAlert.subtitle || incSubtitle;
  } else if ((counts.fire || 0) > 0) {
    incType = 'fuego_confirmado';
    incTitle = 'CONATO DE INCENDIO DETECTADO';
  } else if ((counts.smoke || 0) > 0) {
    incType = 'humo_detectado';
    incTitle = 'COLUMNA DE HUMO DETECTADA';
  }

  showSystemToast(`Evaluando contexto situacional y despachando alerta CAD-911${currentPlate ? ' (' + currentPlate + ')' : ''}...`);

  try {
    const res = await fetch('/api/enrichment/dispatch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        incident_type: incType,
        title: incTitle,
        subtitle: incSubtitle,
        plate: currentPlate,
      }),
    });

    if (res.ok) {
      const data = await res.json();
      const ms = data.microservice_dossier || {};
      const envRisk = ms.environmental_risk || {};
      const sms = data.dispatch_status || {};

      const card = document.getElementById('ms-dossier-card');
      if (card) {
        card.style.display = 'flex';
        const ticketEl = document.getElementById('ms-ticket-id');
        if (ticketEl) ticketEl.textContent = ms.dispatch_ticket_id || 'CAD-911-MEX';
        const sevEl = document.getElementById('ms-severity-badge');
        if (sevEl) sevEl.textContent = ms.severity_level || 'CRÍTICO';
        const incIdEl = document.getElementById('ms-incident-id');
        if (incIdEl) incIdEl.textContent = ms.incident_id || data.event_id || '---';
        const dispStatusEl = document.getElementById('ms-dispatch-status');
        if (dispStatusEl) dispStatusEl.textContent = ms.dispatch_status || 'DELIVERED';
        const smokeDirEl = document.getElementById('ms-smoke-dir');
        if (smokeDirEl) smokeDirEl.textContent = envRisk.smoke_dispersion_direction || '---';
        const smsEl = document.getElementById('ms-sms-status');
        if (smsEl) smsEl.textContent = sms.sms_sent ? `ENVIADO (${sms.destination || 'Twilio'})` : 'REGISTRADO';
      }

      showSystemToast(`Ticket ${ms.dispatch_ticket_id || 'CAD-911'} registrado en el Historial.`);
      loadIncidentsHistory();
      loadFullBacklog(false);
    } else {
      showSystemToast('Error al procesar el despacho en el microservicio.');
    }
  } catch (err) {
    console.error('Error despachando incidente:', err);
    showSystemToast('Error de red al contactar servicio de despacho.');
  }
}

// --- 5b. Validación HTTPS, Backlog & Historial Forense ---
let latestHttpsValidation = null;

async function validateCameraHttpsRoute() {
  try {
    const res = await fetch('/api/camera/validate');
    if (res.ok) {
      const data = await res.json();
      latestHttpsValidation = data;
      const pill = document.getElementById('https-security-pill');
      const txt = document.getElementById('https-status-text');
      if (pill && txt) {
        const isBrowserHttps = window.location.protocol === 'https:' || data.is_https;
        if (isBrowserHttps) {
          pill.style.borderColor = 'rgba(0, 255, 157, 0.5)';
          pill.style.color = '#00ff9d';
          txt.textContent = 'HTTPS SEGURO';
          pill.title = 'Ruta HTTPS validada para transmisión segura de cámara (WSS/TLS)';
        } else if (data.is_localhost) {
          pill.style.borderColor = 'rgba(0, 240, 255, 0.45)';
          pill.style.color = '#00f0ff';
          txt.textContent = 'LOCAL SEGURO';
          pill.title = 'Contexto local seguro. En red móvil o producción se utiliza HTTPS';
        } else {
          pill.style.borderColor = 'rgba(255, 170, 0, 0.7)';
          pill.style.color = '#ffaa00';
          txt.textContent = 'IR A HTTPS';
          pill.title = 'Haz clic para cambiar a la ruta segura HTTPS requerida por la cámara';
          pill.onclick = () => {
            if (data.recommended_https_url) {
              window.location.href = data.recommended_https_url;
            }
          };
        }
      }
      return data;
    }
  } catch (e) {
    console.debug('Error validando ruta HTTPS:', e);
  }
  return null;
}

async function loadBacklogStatus() {
  try {
    const res = await fetch('/api/backlog/status');
    if (res.ok) {
      const st = await res.json();
      const count = (st.backlog_counts && st.backlog_counts.incidents) || 0;
      const navBadge = document.getElementById('nav-incidents-badge');
      if (navBadge) navBadge.textContent = count;

      const badge = document.getElementById('supabase-status-badge');
      if (badge) {
        if (st.connected) {
          badge.textContent = `SUPABASE CLOUD (${count})`;
          badge.style.color = '#00ff9d';
          badge.style.borderColor = 'rgba(0, 255, 157, 0.4)';
        } else if (st.configured) {
          badge.textContent = `SUPABASE SYNC (${count})`;
          badge.style.color = '#00f0ff';
        } else {
          badge.textContent = `BACKLOG (${count})`;
        }
      }
    }
  } catch (e) {
    console.debug('No se pudo consultar estatus de Supabase:', e);
  }
}

window.cycleIncidentBacklogStatus = async function(incidentId, currentStatus) {
  const order = ['PENDIENTE', 'EN_ATENCION', 'RESUELTO'];
  const nextStatus = order[(order.indexOf(currentStatus) + 1) % order.length] || 'EN_ATENCION';
  try {
    const res = await fetch(`/api/backlog/incidents/${encodeURIComponent(incidentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: nextStatus }),
    });
    if (res.ok) {
      showSystemToast(`Incidente ${incidentId}: ${nextStatus}`);
      loadIncidentsHistory();
      loadFullBacklog(false);
    }
  } catch (e) {
    console.warn('Error actualizando estatus en backlog:', e);
  }
};

async function loadIncidentsHistory() {
  try {
    const res = await fetch('/api/incidents');
    if (res.ok) {
      const list = await res.json();
      renderIncidentTimeline(list);
      loadBacklogStatus();
    }
  } catch (e) {
    console.warn('No se pudo obtener bitácora:', e);
  }
}

function renderIncidentTimeline(incidents) {
  const container = document.getElementById('incident-timeline');
  if (!container) return;
  if (!incidents || incidents.length === 0) {
    container.innerHTML = `<div class="empty-state">${I18N_DICTIONARY[currentLang].no_incidents}</div>`;
    return;
  }

  let html = '';
  incidents.slice(0, 6).forEach((item) => {
    const isSmoke = item.type === 'humo_detectado';
    const incId = item.incident_id || item.id || '';
    const incStatus = (item.status || 'PENDIENTE').toUpperCase();
    const statusColor = incStatus === 'RESUELTO' ? '#00ff9d' : (incStatus === 'EN_ATENCION' ? '#00f0ff' : '#ffaa00');
    const statusBadge = incId
      ? `<span class="chip-plate-tag" onclick="window.cycleIncidentBacklogStatus('${incId}', '${incStatus}')" title="Clic para cambiar estado" style="cursor:pointer; border-color:${statusColor}; color:${statusColor}; margin-left:6px;">${incStatus}</span>`
      : '';
    const plateHtml = item.plate
      ? `<span class="chip-plate-tag" style="display:inline-flex; align-items:center; gap:3px; margin-left:6px;"><i data-lucide="scan-line"></i> ${item.plate}</span>`
      : '';
    html += `
      <div class="timeline-item ${isSmoke ? 'smoke-item' : ''}">
        <div class="item-main">
          <span class="item-title">${item.title} ${plateHtml}${statusBadge}</span>
          <span class="item-sub">${item.subtitle}</span>
        </div>
        <span class="item-time">${item.timestamp || ''}</span>
      </div>
    `;
  });
  container.innerHTML = html;
  if (window.lucide) lucide.createIcons();
}

// Funciones de la vista Historial integrada
async function loadFullBacklog(syncCloud = false) {
  const listContainer = document.getElementById('history-incidents-list');
  if (!listContainer) return;

  const statusFilterEl = document.getElementById('filter-status');
  const typeFilterEl = document.getElementById('filter-type');
  const statusFilter = statusFilterEl ? statusFilterEl.value : '';
  const typeFilter = typeFilterEl ? typeFilterEl.value : '';

  const params = new URLSearchParams({ limit: '150' });
  if (statusFilter) params.set('status', statusFilter);
  if (typeFilter) params.set('incident_type', typeFilter);
  if (syncCloud) params.set('sync', 'true');

  try {
    const res = await fetch(`/api/backlog?${params.toString()}`);
    if (!res.ok) return;
    const data = await res.json();
    const incidents = data.incidents || [];

    const totalEl = document.getElementById('stat-total-incidents');
    const pendingEl = document.getElementById('stat-pending-incidents');
    const resolvedEl = document.getElementById('stat-resolved-incidents');
    if (totalEl) totalEl.textContent = incidents.length;
    if (pendingEl) pendingEl.textContent = incidents.filter(i => (i.status || '').toUpperCase() !== 'RESUELTO').length;
    if (resolvedEl) resolvedEl.textContent = incidents.filter(i => (i.status || '').toUpperCase() === 'RESUELTO').length;

    const navBadge = document.getElementById('nav-incidents-badge');
    if (navBadge && !statusFilter && !typeFilter) {
      navBadge.textContent = incidents.length;
    }

    renderHistoryIncidents(incidents);
  } catch (err) {
    console.error('Error cargando backlog en vista historial:', err);
  }
}

function renderHistoryIncidents(incidents) {
  const container = document.getElementById('history-incidents-list');
  if (!container) return;
  if (!incidents || incidents.length === 0) {
    container.innerHTML = `<div class="empty-state">No hay incidentes registrados con los filtros actuales.</div>`;
    return;
  }

  let html = '';
  incidents.forEach((inc) => {
    const incId = inc.incident_id || `ID-${inc.id || ''}`;
    const status = (inc.status || 'PENDIENTE').toUpperCase();
    const statusClass = `status-${status.toLowerCase()}`;
    const statusColor = status === 'RESUELTO' ? '#00ff88' : (status === 'EN_ATENCION' ? '#00f0ff' : '#ffb700');
    const veh = inc.vehicle_data || inc.vehicle || {};
    const vehDesc = veh.brand ? `${veh.brand} ${veh.model || ''}` : '';
    const plateBadge = inc.plate ? `<span class="chip-plate-tag"><i data-lucide="scan-line"></i> ${inc.plate} ${vehDesc}</span>` : '';
    const ticketBadge = inc.dispatch_ticket_id ? `<span class="chip-plate-tag" style="border-color:#00ff88;color:#00ff88;"><i data-lucide="file-check-2"></i> ${inc.dispatch_ticket_id}</span>` : '';
    const snapBadge = inc.snapshot_url ? `<a href="${inc.snapshot_url}" target="_blank" onclick="event.stopPropagation();" class="chip-plate-tag" style="text-decoration:none;"><i data-lucide="image"></i> EVIDENCIA</a>` : '';

    html += `
      <div class="history-card ${statusClass}" onclick="window.inspectIncidentDossier('${incId}')">
        <div class="history-card-top">
          <span class="history-card-id">${incId}</span>
          <div style="display:flex; gap:6px; align-items:center;">
            <span class="chip-plate-tag" onclick="event.stopPropagation(); window.cycleIncidentBacklogStatus('${incId}', '${status}')" style="cursor:pointer; border-color:${statusColor}; color:${statusColor};" title="Clic para cambiar estado">
              ${status}
            </span>
            <span class="item-time">${inc.created_at ? inc.created_at.replace('T', ' ').slice(0, 19) : (inc.timestamp || '')}</span>
          </div>
        </div>
        <div class="history-card-title">${inc.title || 'SINIESTRO VIAL'}</div>
        <div class="item-sub">${inc.subtitle || ''}</div>
        <div class="history-card-meta">
          <span><i data-lucide="video"></i> ${inc.camera_id || 'camera_01'}</span>
          <span>Severidad: <strong>${inc.severity || 'ALTO'}</strong></span>
          ${plateBadge}
          ${ticketBadge}
          ${snapBadge}
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
  if (window.lucide) lucide.createIcons();
}

window.inspectIncidentDossier = async function(incidentId) {
  if (!incidentId) return;
  const input = document.getElementById('dossier-id-input');
  if (input) input.value = incidentId;
  playTacticalChirp();

  try {
    const res = await fetch(`/api/enrichment/dossier/${encodeURIComponent(incidentId)}`);
    if (!res.ok) {
      showSystemToast(`Expediente ${incidentId} no encontrado.`);
      return;
    }
    const d = await res.json();
    renderDossierDetails(d);
  } catch (e) {
    console.error('Error consultando dossier:', e);
  }
};

function renderDossierDetails(d) {
  const emptyPrompt = document.getElementById('dossier-empty-prompt');
  const dossierView = document.getElementById('detailed-dossier-view');
  if (emptyPrompt) emptyPrompt.style.display = 'none';
  if (dossierView) dossierView.style.display = 'flex';

  const enr = d.enrichment || {};
  const ms = enr.microservice_dossier || d;
  const envRisk = ms.environmental_risk || enr.weather || {};
  const tel = ms.telemetry || d.telemetry || {};
  const veh = d.vehicle_data || d.vehicle || ms.vehicle_info || {};

  const setTxt = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  setTxt('det-inc-id', d.incident_id || ms.incident_id || '---');
  setTxt('det-inc-severity', d.severity || ms.severity_level || 'CRÍTICO');
  setTxt('det-cad-ticket', d.dispatch_ticket_id || ms.dispatch_ticket_id || 'PENDIENTE');
  setTxt('dossier-ticket-tag', d.dispatch_ticket_id || ms.dispatch_ticket_id || 'VERIFICADO');
  setTxt('det-status', d.status || ms.status || 'PENDIENTE');
  setTxt('det-camera', d.camera_id || ms.camera_id || 'camera_01');

  const plateStr = d.plate || veh.plate || 'NO VISIBLE';
  const brandModel = `${veh.brand || ''} ${veh.model || ''}`.trim();
  setTxt('det-vehicle', brandModel ? `${plateStr} (${brandModel})` : plateStr);

  if (tel.initial_speed_kmh !== undefined) {
    setTxt('det-kinematics', `${tel.initial_speed_kmh} km/h → ${tel.impact_speed_kmh || 0} km/h (${tel.delta_time_sec || 0.4}s)`);
  } else {
    setTxt('det-kinematics', `Energía óptica: ${tel.motion_energy || 0} | FPS: ${tel.fps || 25}`);
  }

  const temp = envRisk.temperature_c !== undefined ? `${envRisk.temperature_c}°C` : '--°C';
  const wind = envRisk.wind_speed_kmh !== undefined ? `${envRisk.wind_speed_kmh} km/h` : '-- km/h';
  setTxt('det-weather', `${temp} | ${wind} (${envRisk.weather_condition || envRisk.description || 'Normal'})`);
  setTxt('det-smoke', envRisk.smoke_dispersion_direction || '---');
  setTxt('det-pavement', envRisk.pavement_status || envRisk.pavement_risk || 'Pavimento Seco');

  const snapContainer = document.getElementById('det-snapshot-container');
  const snapImg = document.getElementById('det-snapshot-img');
  const snapUrl = d.snapshot_url || veh.snapshot_url;
  if (snapContainer && snapImg) {
    if (snapUrl) {
      snapContainer.style.display = 'block';
      snapImg.src = snapUrl;
    } else {
      snapContainer.style.display = 'none';
    }
  }
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

    ctx.lineWidth = 2;
    ctx.strokeStyle = boxColor;
    ctx.strokeRect(bx, by, bw, bh);

    const labelText = isPerson
      ? 'PEATÓN'
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

    const labelText = isFire ? 'FUEGO' : 'HUMO';
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
  }, 80);
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

    const secCheck = await validateCameraHttpsRoute();
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (!isLocal && window.location.protocol !== 'https:' && !(secCheck && secCheck.is_https)) {
      const targetHttps = (secCheck && secCheck.recommended_https_url) || `https://${window.location.host}${window.location.pathname}`;
      showSystemToast(`Redirigiendo a ruta segura HTTPS para cámara: ${targetHttps}`);
      setTimeout(() => { window.location.href = targetHttps; }, 1200);
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      let errDetail = "Cámara no disponible en este navegador.";
      if (!isLocal && window.location.protocol !== 'https:') {
        errDetail = "El navegador requiere conexión segura HTTPS para acceder a la cámara.";
      }
      console.warn(errDetail);
      showSystemToast(errDetail);
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
      stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });
    }

    clientVideoStream = stream;

    videoElem.muted = true;
    videoElem.playsInline = true;
    videoElem.autoplay = true;
    videoElem.setAttribute('playsinline', '');
    videoElem.setAttribute('webkit-playsinline', '');
    videoElem.srcObject = stream;

    if (mainStream) {
      mainStream.style.display = 'block';
      mainStream.src = `/api/stream?t=${Date.now()}`;
    }
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

    sendControl({ action: 'set_source', source: 'client_cam' });

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
        }, 55);
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
    showSystemToast(errMsg + " Manteniendo fuente del servidor.");
    stopDeviceCamera(true);
  }
}

function stopDeviceCamera(restoreServerStream = true) {
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

  if (restoreServerStream) {
    const videoSelect = document.getElementById('select-video-sample');
    const fallbackVideo = (videoSelect && videoSelect.value && videoSelect.value !== 'client_cam')
      ? videoSelect.value
      : 'Test1.mp4';
    if (videoSelect) videoSelect.value = fallbackVideo;
    sendControl({ action: 'set_source', source: fallbackVideo });
  }
}

async function flipDeviceCamera() {
  if (!isCameraActive || isFlippingCamera) return;
  isFlippingCamera = true;
  playTacticalChirp();
  currentFacingMode = currentFacingMode === 'environment' ? 'user' : 'environment';
  showSystemToast(`Cambiando a cámara ${currentFacingMode === 'environment' ? 'trasera' : 'frontal'}...`);

  const videoElem = document.getElementById('client-webcam');
  const mainStream = document.getElementById('main-stream');
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
    showSystemToast(`Cámara activa: ${currentFacingMode === 'environment' ? 'Trasera' : 'Frontal'}`);
  } catch (err) {
    console.warn("Fallo alternando sensor de cámara:", err);
    showSystemToast("No se pudo alternar el sensor físico de cámara.");
  } finally {
    isFlippingCamera = false;
  }
}

// --- 7. Eventos de Controles e Interacción ---
function setupEventListeners() {
  // Navegación del Sidebar
  document.querySelectorAll('.sidebar-nav-item[data-view]').forEach((btn) => {
    btn.addEventListener('click', () => {
      playTacticalChirp();
      const target = btn.getAttribute('data-view');
      switchAppView(target, true);
    });
  });

  // Trigger del Sidebar en el Header (colapsa en desktop / abre drawer en móvil)
  const toggleSidebarBtn = document.getElementById('btn-toggle-sidebar');
  const closeSidebarBtn = document.getElementById('btn-close-sidebar');
  const appShell = document.getElementById('app-shell');
  const sidebar = document.getElementById('app-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');

  const toggleMobileSidebar = (open) => {
    if (!sidebar || !backdrop) return;
    sidebar.classList.toggle('open', open);
    backdrop.classList.toggle('active', open);
  };

  if (toggleSidebarBtn) {
    toggleSidebarBtn.addEventListener('click', () => {
      playTacticalChirp();
      if (window.innerWidth <= 900) {
        const isOpen = sidebar ? !sidebar.classList.contains('open') : true;
        toggleMobileSidebar(isOpen);
      } else if (appShell) {
        appShell.classList.toggle('sidebar-collapsed');
      }
    });
  }
  if (closeSidebarBtn) closeSidebarBtn.addEventListener('click', () => toggleMobileSidebar(false));
  if (backdrop) backdrop.addEventListener('click', () => toggleMobileSidebar(false));

  // Selector de Video Samples (Test1 - Test6) en el Header
  const selectVideoSample = document.getElementById('select-video-sample');
  if (selectVideoSample) {
    selectVideoSample.addEventListener('change', (e) => {
      playTacticalChirp();
      const selectedSource = e.target.value;
      if (selectedSource === 'client_cam') {
        startDeviceCamera();
      } else {
        stopDeviceCamera(false);
        sendControl({ action: 'set_source', source: selectedSource });
        if (currentView !== 'home') {
          switchAppView('home', true);
        }
        const mainStream = document.getElementById('main-stream');
        if (mainStream) {
          mainStream.style.display = 'block';
          mainStream.src = `/api/stream?t=${Date.now()}`;
        }
        showSystemToast(`Analizando muestra de video: ${selectedSource}`);
      }
    });
  }

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

  // Sliders de Sensibilidad en el Sidebar
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
      const tag = val <= 0.22 ? ' (Alta)' : (val <= 0.40 ? ' (Calibrado)' : ' (Estricta)');
      if (valDisplay) valDisplay.textContent = val.toFixed(2) + tag;
      sendControl({ action: 'set_sensitivity', fire_conf: val });
    });
  }

  if (smokeSlider) {
    smokeSlider.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      const valDisplay = document.getElementById('smoke-conf-val');
      const tag = val <= 0.16 ? ' (Alta)' : (val <= 0.30 ? ' (Media)' : ' (Estricta)');
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

  // Audio Toggle
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

  // Reconocer banner de alerta
  const btnDismiss = document.getElementById('banner-dismiss');
  if (btnDismiss) {
    btnDismiss.addEventListener('click', () => {
      const banner = document.getElementById('emergency-banner');
      if (banner) banner.style.display = 'none';
    });
  }

  // Actualizar contexto ambiental
  const btnRefreshContext = document.getElementById('btn-refresh-context');
  if (btnRefreshContext) {
    btnRefreshContext.addEventListener('click', () => {
      playTacticalChirp();
      requestUserLocation();
      showSystemToast('Actualizando telemetría ambiental...');
    });
  }

  // Despacho CAD-911
  const btnDispatchCad = document.getElementById('btn-dispatch-cad');
  if (btnDispatchCad) {
    btnDispatchCad.addEventListener('click', () => {
      triggerMicroserviceCadDispatch();
    });
  }

  // Consulta manual de Placa o VIN
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
              showSystemToast("No se detectaron placas legibles en la imagen.");
            }
          }
        } catch (err) {
          console.error("Error en detección de placa por imagen:", err);
        }
      };
      reader.readAsDataURL(file);
    });
  }

  // Carga de Video en Vivo
  const videoInput = document.getElementById('video-file-input');
  if (videoInput) {
    videoInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;

      playTacticalChirp();
      showSystemToast(`Cargando video para análisis: ${file.name}...`);

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
          showSystemToast(data.message || 'Video cargado en vivo.');
          const mainStream = document.getElementById('main-stream');
          if (mainStream) {
            mainStream.src = `/api/stream?t=${Date.now()}`;
          }
        } else {
          showSystemToast('Error subiendo video. Verifique formato.');
        }
      } catch (err) {
        console.error('Error subiendo video:', err);
        showSystemToast('Error de conexión al subir video.');
      }
    });
  }

  // Controles de la vista Historial
  const filterStatus = document.getElementById('filter-status');
  const filterType = document.getElementById('filter-type');
  const btnSyncCloud = document.getElementById('btn-sync-cloud');
  const btnFetchDossier = document.getElementById('btn-fetch-dossier');
  const dossierIdInput = document.getElementById('dossier-id-input');

  if (filterStatus) filterStatus.addEventListener('change', () => loadFullBacklog(false));
  if (filterType) filterType.addEventListener('change', () => loadFullBacklog(false));
  if (btnSyncCloud) {
    btnSyncCloud.addEventListener('click', () => {
      playTacticalChirp();
      loadFullBacklog(true);
      showSystemToast('Sincronizando registros del historial...');
    });
  }
  if (btnFetchDossier && dossierIdInput) {
    btnFetchDossier.addEventListener('click', () => {
      const val = dossierIdInput.value.trim();
      if (val) window.inspectIncidentDossier(val);
    });
    dossierIdInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const val = dossierIdInput.value.trim();
        if (val) window.inspectIncidentDossier(val);
      }
    });
  }
}

function applyLanguage(lang) {
  const dict = I18N_DICTIONARY[lang] || I18N_DICTIONARY.es;
  const setTxt = (id, text) => {
    const el = document.getElementById(id);
    if (el && text) el.textContent = text;
  };

  setTxt('current-lang-text', lang.toUpperCase());
  setTxt('i18n-sub', dict.sub);
  setTxt('i18n-nav-home', dict.nav_home);
  setTxt('i18n-nav-enrich', dict.nav_enrich);
  setTxt('i18n-nav-history', dict.nav_history);
  setTxt('i18n-pause', isPaused ? dict.resume : dict.pause);
  setTxt('i18n-upload-video', dict.upload_video);
  setTxt('i18n-motion-lbl', dict.motion_lbl);
  setTxt('i18n-card-veh', dict.card_veh);
  setTxt('i18n-card-ped', dict.card_ped);
  setTxt('i18n-card-fire', dict.card_fire);
  setTxt('i18n-card-smoke', dict.card_smoke);
  setTxt('i18n-card-inc', dict.card_inc);
  setTxt('i18n-card-plates', dict.card_plates);
  setTxt('sidebar-plates-title', dict.sidebar_plates_title);
  setTxt('i18n-plates-title', dict.plates_title);
  setTxt('i18n-enrich-title', dict.enrich_title);
  setTxt('i18n-ctrl-title', dict.ctrl_title);
  setTxt('i18n-vehicle-sens', dict.vehicle_sens);
  setTxt('i18n-fire-sens', dict.fire_sens);
  setTxt('i18n-smoke-sens', dict.smoke_sens);
  setTxt('i18n-tracking-title', dict.tracking_title);
  setTxt('i18n-blackbox-title', dict.blackbox_title);
  setTxt('i18n-connecting', dict.connecting);

  // Actualizar título de la vista activa en el navbar
  switchAppView(currentView, false);

  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}

// Inicialización de la aplicación
document.addEventListener('DOMContentLoaded', () => {
  const hashView = (window.location.hash || '').replace('#', '').toLowerCase();
  if (['home', 'enriquecimiento', 'historial'].includes(hashView)) {
    currentView = hashView;
  }

  applyLanguage(currentLang);
  setupEventListeners();
  switchAppView(currentView, false);

  window.addEventListener('hashchange', () => {
    const h = (window.location.hash || '').replace('#', '').toLowerCase();
    if (['home', 'enriquecimiento', 'historial'].includes(h)) {
      switchAppView(h, false);
    }
  });

  const mainStream = document.getElementById('main-stream');
  if (mainStream) {
    mainStream.addEventListener('load', () => {
      const loader = document.getElementById('stream-loader');
      if (loader) loader.classList.add('hidden');
    });
    mainStream.addEventListener('error', () => {
      setTimeout(() => {
        if (mainStream) mainStream.src = `/api/stream?t=${Date.now()}`;
      }, 2000);
    });
  }

  setTimeout(() => {
    const loader = document.getElementById('stream-loader');
    if (loader) loader.classList.add('hidden');
  }, 2200);

  const btnCam = document.getElementById('btn-toggle-camera');
  const btnText = document.getElementById('camera-btn-text');
  if (btnCam) btnCam.classList.remove('danger-active');
  if (btnText) btnText.textContent = I18N_DICTIONARY[currentLang].camera_stopped || "ACTIVAR CÁMARA";

  validateCameraHttpsRoute();
  loadBacklogStatus();
  connectTelemetryWebSocket();
  requestUserLocation();
  loadIncidentsHistory();
  setInterval(loadIncidentsHistory, 5000);
  setInterval(loadSituationalContext, 30000);

  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
});

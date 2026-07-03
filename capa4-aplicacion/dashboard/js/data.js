/*
 * data.js — Capa de datos del dashboard. TODO viene de la BD vía API (nada demo).
 *
 *   - loadNodes():      GET /api/nodes   → NODES (con riesgo, sensores, conteos)
 *   - applyRealAlerts(): GET /api/alerts → ALERTS (todas; el mapa filtra las ocultas)
 *
 * Sesión: todas las APIs exigen login (cookie). fetchJSON() redirige a
 * /login.html ante un 401. El shape de una alerta:
 *
 *   { id, nodeId, nodeName, district, lat, lon, ts, confidence, source,
 *     detClass, detCount, videoUrl, status, riskLevel, isSynthetic,
 *     createdAt, respondedAt,
 *     sensors: { temp_c, turb_v, humedad, ph, nivel_agua,
 *                audio_rms, audio_peak, sats } }
 */

const LIMA_CENTER = [-12.046, -77.043];

/* Nodos REALES (de la BD). Se llenan con loadNodes(); nada hardcodeado. */
const NODES = [];
let NODE_BY_ID = {};

/* Alertas reales (de /api/alerts). El array mantiene la MISMA referencia. */
const ALERTS = [];

/* Usuario de la sesión actual ({id, username, role, full_name}) — lo setea app.js */
let CURRENT_USER = null;

/* ---------------- fetch con manejo de sesión ---------------- */
async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, { cache: 'no-store', credentials: 'same-origin', ...opts });
  if (res.status === 401) {
    // sesión vencida o inexistente → al login (conservando a dónde iba)
    window.location.href = 'login.html';
    throw new Error('sesión requerida');
  }
  if (!res.ok) {
    let msg = 'HTTP ' + res.status;
    try { msg = (await res.json()).error || msg; } catch (e) { /* no-json */ }
    throw new Error(msg);
  }
  return res.json();
}

/* ---------------- carga de NODOS reales (BD vía /api/nodes) ---------------- */
async function loadNodes() {
  try {
    const rows = await fetchJSON('/api/nodes');
    NODES.length = 0;
    for (const r of rows) {
      NODES.push({
        id: r.node_name,                          // node_id real ("esp32-01")
        name: r.display_name || r.node_name,      // nombre legible
        district: r.district || 'sin distrito',
        lat: r.lat, lon: r.lon, alt: r.alt,
        status: r.status,
        riskLevel: r.risk_level, riskScore: r.risk_score,
        alertCount: r.alert_count, alertVisible: r.alert_visible,
        sensors: r.sensors_installed || [],
        lastHeartbeat: r.last_heartbeat, lastReading: r.last_reading,
        lastReadingData: r.last_reading_data,
        isSimulated: r.is_simulated,
        battery: r.battery_pct, chipTemp: r.chip_temp_c,
        threshold: r.threshold, uptime: r.uptime_s,
        firstSeen: r.first_seen, lastSeen: r.last_seen,
      });
    }
    NODE_BY_ID = Object.fromEntries(NODES.map(n => [n.id, n]));
    console.info(`[data] ${NODES.length} nodo(s) reales cargados de la BD.`);
    return NODES.length;
  } catch (e) {
    console.warn('[data] /api/nodes no disponible:', e.message);
    return false;
  }
}

/* ---------------- carga de ALERTAS reales (BD vía /api/alerts) -------------- */
async function applyRealAlerts(url = '/api/alerts') {
  try {
    const real = await fetchJSON(url);
    if (!Array.isArray(real)) throw new Error('respuesta no es un array');
    ALERTS.length = 0;
    ALERTS.push(...real.sort((a, b) => b.ts - a.ts));
    console.info(`[data] ${real.length} alertas reales cargadas (confirmadas por el detector).`);
    return real.length;
  } catch (e) {
    console.warn('[data] /api/alerts no disponible:', e.message);
    return false;
  }
}

/* Recarga completa (la usan los flujos de respuesta para refrescar todo). */
async function reloadData() {
  await Promise.all([loadNodes(), applyRealAlerts()]);
}

/* ---------------- helpers de consulta ---------------- */

/* Estados que NO se muestran en el mapa (limpieza automática, req.5). El
 * historial completo sigue en la tabla de detecciones y en la BD (auditoría). */
const HIDDEN_ON_MAP = ['falsa-alarma', 'descartada'];

function visibleAlerts() {
  return ALERTS.filter(a => !HIDDEN_ON_MAP.includes(a.status));
}

/** Última alerta (más reciente) por cada nodo → para el dashboard principal. */
function latestAlertPerNode() {
  const latest = {};
  for (const a of ALERTS) {
    if (!latest[a.nodeId] || a.ts > latest[a.nodeId].ts) latest[a.nodeId] = a;
  }
  return Object.values(latest).sort((x, y) => y.ts - x.ts);
}

/** Todas las alertas de un nodo (historial completo, más reciente primero). */
function alertsForNode(nodeId) {
  return ALERTS.filter(a => a.nodeId === nodeId).sort((a, b) => b.ts - a.ts);
}

/** Conteo de alertas VISIBLES por nodo → para gráficos y heatmap. */
function alertCountsByNode() {
  const counts = {};
  for (const n of NODES) counts[n.id] = 0;
  for (const a of visibleAlerts()) counts[a.nodeId] = (counts[a.nodeId] || 0) + 1;
  return counts;
}

/** Conteo por estado del workflow → para el gráfico de estados. */
function alertCountsByStatus() {
  const counts = {};
  for (const a of ALERTS) counts[a.status] = (counts[a.status] || 0) + 1;
  return counts;
}

/** Alertas agrupadas por día (últimos 7 días) → para gráfico temporal. */
function alertsByDay(days = 7) {
  const DAY = 24 * 60 * 60 * 1000;
  const now = Date.now();
  const buckets = [];
  for (let d = days - 1; d >= 0; d--) {
    const dayStart = now - d * DAY;
    const label = new Date(dayStart).toLocaleDateString('es-PE', { weekday: 'short', day: 'numeric' });
    buckets.push({ label, start: dayStart - DAY / 2, end: dayStart + DAY / 2, count: 0 });
  }
  for (const a of visibleAlerts()) {
    for (const b of buckets) {
      if (a.ts >= b.start && a.ts < b.end) { b.count++; break; }
    }
  }
  return buckets;
}

/* ---------------- helpers de formato ---------------- */

function formatTime(ts) {
  return new Date(ts).toLocaleString('es-PE', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function timeAgo(ts) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return 'hace ' + s + 's';
  const m = Math.floor(s / 60);
  if (m < 60) return 'hace ' + m + ' min';
  const h = Math.floor(m / 60);
  if (h < 24) return 'hace ' + h + ' h';
  const d = Math.floor(h / 24);
  return 'hace ' + d + ' d';
}

const SOURCE_LABEL = {
  'edge-ml': 'Edge ML (audio)',
  'camera':  'Cámara IP (video)',
  'gpio':    'Sensor GPIO',
};

/* Workflow de estados. Los 3 vivos del flujo son pendiente / en-revision /
 * respondida (= "En atención", la cola de operadores); resuelta cierra el
 * ciclo desde la pestaña Atención. falsa-alarma/descartada solo pueden
 * existir en filas viejas de la BD (hoy "falsa alarma" ELIMINA la alerta). */
const STATUS_LABEL = {
  'pendiente':    'Pendiente',
  'en-revision':  'Por revisar',
  'respondida':   'En atención',
  'resuelta':     'Atendida',
  'falsa-alarma': 'Falsa alarma',
  'descartada':   'Descartada',
};

/* Acciones del plan de acción (modal de gestión) → SOLO 3:
 *   falsa-alarma → DELETE /api/alerts/<id> (se elimina de la BD, no vuelve)
 *   atender      → pasa a "En atención": entra a la cola de la pestaña Atención
 *   revisar      → queda "Por revisar" (pendiente de verificación) */
const ALERT_ACTIONS_UI = [
  { action: 'atender',      label: '✅ Atender (enviar a la cola de atención)' },
  { action: 'revisar',      label: '🔍 Por revisar' },
  { action: 'falsa-alarma', label: '🚫 Falsa alarma (eliminar definitivamente)' },
];

/** Cola de atención: alertas que un operador debe atender (pestaña Atención). */
function attentionQueue() {
  return ALERTS.filter(a => a.status === 'respondida').sort((a, b) => b.ts - a.ts);
}

/* Niveles de riesgo (motor risk.py). */
const RISK_LABEL = { bajo: 'Bajo', medio: 'Medio', alto: 'Alto', critico: 'Crítico' };
const RISK_EMOJI = { bajo: '🟢', medio: '🟡', alto: '🟠', critico: '🔴' };
const RISK_COLOR = {
  bajo: '#34d399', medio: '#fbbf24', alto: '#fb923c', critico: '#f5616e',
};

function riskBadge(level, score) {
  if (!level) return '<span class="risk-badge bajo">—</span>';
  const s = (score != null) ? ' · ' + Math.round(score) : '';
  return '<span class="risk-badge ' + level + '">' + (RISK_EMOJI[level] || '') + ' ' +
         (RISK_LABEL[level] || level) + s + '</span>';
}

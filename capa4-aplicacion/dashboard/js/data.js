/*
 * data.js — Datos DEMO del dashboard de alertas de mosquitos.
 *
 * Proyecto paralelo (independiente del firmware/backend de project_02).
 * Aquí TODO es simulado para poder ver el dashboard funcionando sin servidor.
 *
 * Para conectar a datos reales más adelante:
 *   - Reemplazar `generateAlerts()` por una llamada al backend Go
 *     (ej. GET /api/alerts) o por una suscripción Socket.IO / MQTT.
 *   - Mantener el MISMO shape de objeto Alert (ver abajo) y el resto
 *     del dashboard sigue funcionando sin cambios.
 *
 * Shape de un Nodo:
 *   { id, name, district, lat, lon }
 *
 * Shape de una Alerta (lo que "envía" un nodo cuando detecta mosquito):
 *   {
 *     id, nodeId, nodeName, district, lat, lon,
 *     ts,                      // epoch ms
 *     confidence,              // 0..1  (score del Edge ML / cámara)
 *     source,                  // 'edge-ml' | 'camera' | 'gpio'
 *     status,                  // 'nueva' | 'atendida' | 'falso-positivo' | 'fumigacion'
 *     sensors: { temp_c, turb_v, audio_rms, audio_peak, sats }
 *   }
 */

const LIMA_CENTER = [-12.046, -77.043];

/* Nodos ubicados en distritos reales de Lima con incidencia de dengue.
 * Las coordenadas vienen del GPS de cada nodo (sentencia GGA del módulo). */
const NODES = [
  { id: 'esp32-01', name: 'Nodo SJL-01',  district: 'San Juan de Lurigancho', lat: -11.9620, lon: -77.0000 },
  { id: 'esp32-02', name: 'Nodo COM-01',  district: 'Comas',                  lat: -11.9490, lon: -77.0610 },
  { id: 'esp32-03', name: 'Nodo VES-01',  district: 'Villa El Salvador',      lat: -12.2130, lon: -76.9370 },
  { id: 'esp32-04', name: 'Nodo CER-01',  district: 'Cercado de Lima',        lat: -12.0460, lon: -77.0430 },
  { id: 'esp32-05', name: 'Nodo ATE-01',  district: 'Ate',                    lat: -12.0260, lon: -76.9180 },
  { id: 'esp32-06', name: 'Nodo LOS-01',  district: 'Los Olivos',             lat: -12.0000, lon: -77.0830 },
  { id: 'esp32-07', name: 'Nodo CAR-01',  district: 'Carabayllo',             lat: -11.8970, lon: -77.0330 },
  { id: 'esp32-08', name: 'Nodo LUR-01',  district: 'Lurín',                  lat: -12.2740, lon: -76.8720 },
];

const NODE_BY_ID = Object.fromEntries(NODES.map(n => [n.id, n]));

/* ---- generador pseudo-aleatorio determinista (para datos demo estables) ---- */
let _seed = 1337;
function rnd() {
  // xorshift simple — siempre genera la misma secuencia => demo reproducible
  _seed ^= _seed << 13; _seed ^= _seed >> 17; _seed ^= _seed << 5;
  return Math.abs(_seed % 100000) / 100000;
}
function rndRange(a, b) { return a + (b - a) * rnd(); }
function rndInt(a, b) { return Math.floor(rndRange(a, b + 1)); }
function pick(arr) { return arr[rndInt(0, arr.length - 1)]; }

const SOURCES = ['edge-ml', 'edge-ml', 'edge-ml', 'camera', 'gpio']; // edge-ml más probable

/* Cuántas alertas tiene cada nodo (algunos son "más críticos" que otros). */
const NODE_WEIGHT = {
  'esp32-01': 14, // SJL — zona caliente
  'esp32-02': 9,
  'esp32-03': 11, // VES — zona caliente
  'esp32-04': 4,
  'esp32-05': 7,
  'esp32-06': 6,
  'esp32-07': 3,
  'esp32-08': 5,
};

function generateAlerts() {
  const alerts = [];
  const now = Date.now();
  const DAY = 24 * 60 * 60 * 1000;
  let id = 1;

  for (const node of NODES) {
    const count = NODE_WEIGHT[node.id] || 5;
    for (let i = 0; i < count; i++) {
      // repartidas en los últimos 7 días
      const ts = Math.round(now - rndRange(0, 7 * DAY));
      alerts.push({
        id: id++,
        nodeId: node.id,
        nodeName: node.name,
        district: node.district,
        lat: node.lat + rndRange(-0.004, 0.004), // leve jitter para el heatmap
        lon: node.lon + rndRange(-0.004, 0.004),
        ts,
        confidence: Math.round(rndRange(0.62, 0.99) * 1000) / 1000,
        source: pick(SOURCES),
        status: 'nueva',
        sensors: {
          temp_c:     Math.round(rndRange(22, 31) * 10) / 10,
          turb_v:     Math.round(rndRange(0.4, 2.8) * 100) / 100,
          audio_rms:  Math.round(rndRange(800, 4200)),
          audio_peak: rndInt(20000, 90000),
          sats:       rndInt(4, 11),
        },
      });
    }
  }
  // ordenadas de la más reciente a la más antigua
  return alerts.sort((a, b) => b.ts - a.ts);
}

// Arranca VACIO: solo se llena con alertas REALES de /api/alerts (sin datos falsos).
const ALERTS = [];

/* ---------------- helpers de consulta ---------------- */

/** Última alerta (más reciente) por cada nodo → para el dashboard principal. */
function latestAlertPerNode() {
  const latest = {};
  for (const a of ALERTS) {
    if (!latest[a.nodeId] || a.ts > latest[a.nodeId].ts) latest[a.nodeId] = a;
  }
  // devuelve en orden de más reciente primero
  return Object.values(latest).sort((x, y) => y.ts - x.ts);
}

/** Todas las alertas de un nodo (historial completo, más reciente primero). */
function alertsForNode(nodeId) {
  return ALERTS.filter(a => a.nodeId === nodeId).sort((a, b) => b.ts - a.ts);
}

/** Conteo de alertas por nodo → para gráficos y heatmap. */
function alertCountsByNode() {
  const counts = {};
  for (const n of NODES) counts[n.id] = 0;
  for (const a of ALERTS) counts[a.nodeId]++;
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
  for (const a of ALERTS) {
    for (const b of buckets) {
      if (a.ts >= b.start && a.ts < b.end) { b.count++; break; }
    }
  }
  return buckets;
}

/* ---------------- carga de nodos resueltos (nodes.json) ---------------- */
/*
 * Sobrepone los datos REALES generados por tools/resolve_district.py
 * (device_id → name, lat, lon, district) encima de los nodos demo.
 * Si el archivo no está disponible (ej. abriendo con file://), el dashboard
 * sigue funcionando con los datos demo. Esto es lo que conecta el paso 1
 * (resolución de distrito) con la visualización.
 */
async function applyResolvedNodes(url = 'tools/nodes.json') {
  try {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const resolved = await res.json();

    for (const [id, info] of Object.entries(resolved)) {
      const node = NODE_BY_ID[id];
      if (!node) continue;
      if (info.name) node.name = info.name;
      if (info.district) node.district = info.district;
      if (typeof info.lat === 'number') node.lat = info.lat;
      if (typeof info.lon === 'number') node.lon = info.lon;
    }
    // re-sincronizar las alertas ya generadas con los nombres/distritos resueltos
    for (const a of ALERTS) {
      const node = NODE_BY_ID[a.nodeId];
      if (node) { a.nodeName = node.name; a.district = node.district; }
    }
    console.info('[data] Distritos cargados desde nodes.json (resolución real).');
    return true;
  } catch (e) {
    console.warn('[data] nodes.json no disponible, usando datos demo:', e.message);
    return false;
  }
}

/* ---------------- carga de ALERTAS REALES (BD vía /api/alerts) ----------------
 *
 * serve.py expone en /api/alerts las alertas CONFIRMADAS por el detector de
 * movimiento (MOG2 + flujo óptico) + audio, con el mismo shape de arriba. Si
 * responde, se reemplaza el contenido del array ALERTS por los datos reales; si
 * no, el tablero queda vacío. NODES sigue resolviéndose con nodes.json.
 */
async function applyRealAlerts(url = '/api/alerts') {
  try {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const real = await res.json();
    if (!Array.isArray(real)) throw new Error('respuesta no es un array');

    // Sin datos falsos: si la BD no tiene alertas, el tablero queda vacío.
    if (real.length === 0) {
      ALERTS.length = 0;
      console.info('[data] /api/alerts vacío; tablero sin alertas (sin datos demo).');
      return 0;
    }

    // Reemplazar en sitio el contenido de ALERTS (mantener la misma referencia).
    ALERTS.length = 0;
    ALERTS.push(...real.sort((a, b) => b.ts - a.ts));
    console.info(`[data] ${real.length} alertas reales cargadas desde ${url} (confirmadas por el detector).`);
    return real.length;
  } catch (e) {
    console.warn('[data] /api/alerts no disponible, usando datos demo:', e.message);
    return false;
  }
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

const STATUS_LABEL = {
  'nueva':          'Nueva',
  'atendida':       'Atendida',
  'falso-positivo': 'Falso positivo',
  'fumigacion':     'Fumigación enviada',
};

/*
 * map.js — Mapa de Lima con Leaflet. SOLO nodos reales de la BD.
 *
 * Dos capas que se alternan:
 *   - "marcadores": un pin por nodo REGISTRADO con posición conocida; el color
 *     es su NIVEL DE RIESGO (motor risk.py): 🟢 bajo · 🟡 medio · 🟠 alto · 🔴 crítico.
 *   - "calor": heatmap de densidad de alertas VISIBLES (las falsas/descartadas
 *     desaparecen del mapa automáticamente, pero siguen en BD para auditoría).
 */

let _map = null;
let _markersLayer = null;
let _heatLayer = null;
let _mapMode = 'marcadores';
let _legend = null;

function initMap() {
  _map = L.map('map', { zoomControl: true, attributionControl: false })
          .setView(LIMA_CENTER, 11);

  // Tiles oscuros (CartoDB dark) para combinar con el tema del dashboard
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    subdomains: 'abcd',
  }).addTo(_map);

  _legend = _buildLegend();
  _legend.addTo(_map);

  refreshMapLayers();
  setMapMode('marcadores');

  // si solo hay un nodo con posición, centrar ahí
  const located = NODES.filter(n => n.lat != null && n.lon != null);
  if (located.length === 1) _map.setView([located[0].lat, located[0].lon], 13);
  else if (located.length > 1) {
    _map.fitBounds(located.map(n => [n.lat, n.lon]), { padding: [40, 40], maxZoom: 13 });
  }
}

/** Reconstruye ambas capas con los datos actuales (se llama tras responder
 * una alerta o al refrescar datos: el mapa SIEMPRE refleja la BD). */
function refreshMapLayers() {
  if (!_map) return;
  const active = _mapMode;
  buildMarkersLayer();
  buildHeatLayer();
  setMapMode(active);
}

function _sensorIcons(sensors) {
  const icons = {
    temp_ds18b20: '🌡️', turbidez: '💧', gps: '🛰️', audio: '🎤',
    humedad: '💦', ph: '⚗️', nivel_agua: '🌊',
  };
  return (sensors || []).map(s => `<span title="${s}">${icons[s] || '🔧'}</span>`).join(' ');
}

function buildMarkersLayer() {
  if (_markersLayer && _map.hasLayer(_markersLayer)) _map.removeLayer(_markersLayer);
  _markersLayer = L.layerGroup();

  for (const node of NODES) {
    if (node.lat == null || node.lon == null) continue;   // sin posición conocida

    const color = RISK_COLOR[node.riskLevel] || RISK_COLOR.bajo;
    const score = node.riskScore || 0;
    const radius = 10 + (score / 100) * 14;               // más riesgo = pin más grande
    const last = alertsForNode(node.id)[0];

    const marker = L.circleMarker([node.lat, node.lon], {
      radius, color, weight: 2, fillColor: color, fillOpacity: 0.4,
    });

    // Req.7: TODOS los datos del popup salen de la BD (nada fijo en el código).
    marker.bindPopup(
      '<div class="map-popup">' +
        '<strong>' + node.name + '</strong>' +
        (node.isSimulated ? ' <span class="sim-tag">SIM</span>' : '') + '<br>' +
        '<span class="muted">' + node.district + '</span><br>' +
        riskBadge(node.riskLevel, node.riskScore) + '<br>' +
        'Estado: <b>' + (node.status || '?') + '</b><br>' +
        '<b>' + (node.alertVisible ?? 0) + '</b> alertas activas' +
        ((node.alertCount ?? 0) > (node.alertVisible ?? 0)
          ? ' <span class="muted small">(' + node.alertCount + ' total con descartadas)</span>' : '') + '<br>' +
        'Sensores: ' + (_sensorIcons(node.sensors) || '<span class="muted">?</span>') + '<br>' +
        (node.lastReading ? 'Última lectura: ' + timeAgo(Date.parse(node.lastReading)) + '<br>' : '') +
        (last ? 'Última alerta: ' + timeAgo(last.ts) + '<br>' : 'Sin alertas<br>') +
        '<a href="#" onclick="renderNodeDetail(\'' + node.id + '\');return false;">Ver historial →</a>' +
      '</div>'
    );
    marker.on('click', () => marker.openPopup());
    _markersLayer.addLayer(marker);
  }
}

function buildHeatLayer() {
  if (_heatLayer && _map.hasLayer(_heatLayer)) _map.removeLayer(_heatLayer);
  // Un punto de calor por alerta VISIBLE (req.5: falsas/descartadas no pintan),
  // ponderado por la confianza de detección.
  const points = visibleAlerts()
    .filter(a => a.lat != null && a.lon != null)
    .map(a => [a.lat, a.lon, a.confidence || 0.5]);
  _heatLayer = L.heatLayer(points, {
    radius: 30,
    blur: 22,
    maxZoom: 13,
    gradient: { 0.2: '#2b6cb0', 0.4: '#38a169', 0.6: '#d69e2e', 0.8: '#dd6b20', 1.0: '#e53e3e' },
  });
}

function _buildLegend() {
  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = function () {
    const div = L.DomUtil.create('div', 'map-legend');
    div.innerHTML =
      '<strong>Nivel de riesgo</strong>' +
      ['bajo', 'medio', 'alto', 'critico'].map(l =>
        `<div><span class="dot-legend" style="background:${RISK_COLOR[l]}"></span> ` +
        `${RISK_EMOJI[l]} ${RISK_LABEL[l]}</div>`).join('');
    return div;
  };
  return legend;
}

function setMapMode(mode) {
  _mapMode = mode;
  if (!_map) return;
  if (mode === 'calor') {
    if (_markersLayer && _map.hasLayer(_markersLayer)) _map.removeLayer(_markersLayer);
    _heatLayer.addTo(_map);
  } else {
    if (_heatLayer && _map.hasLayer(_heatLayer)) _map.removeLayer(_heatLayer);
    _markersLayer.addTo(_map);
  }
  // sincronizar botones del toggle
  document.querySelectorAll('[data-mapmode]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mapmode === mode);
  });
}

/** Centra el mapa en un nodo concreto (se usa desde el detalle). */
function focusNodeOnMap(nodeId) {
  const node = NODE_BY_ID[nodeId];
  if (node && _map && node.lat != null) {
    _map.setView([node.lat, node.lon], 14, { animate: true });
  }
}

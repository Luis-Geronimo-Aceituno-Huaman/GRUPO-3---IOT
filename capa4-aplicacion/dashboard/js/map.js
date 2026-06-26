/*
 * map.js — Mapa de Lima con Leaflet.
 *
 * Dos capas que se alternan:
 *   - "marcadores": un pin por nodo, con popup (nombre, distrito, # alertas, GPS/sats).
 *   - "calor":      heatmap de densidad de alertas → mapa de riesgo de dengue por zona.
 *
 * El GPS de cada nodo (lat/lon de la sentencia GGA) es lo que posiciona todo.
 */

let _map = null;
let _markersLayer = null;
let _heatLayer = null;
let _mapMode = 'marcadores';

function initMap() {
  _map = L.map('map', { zoomControl: true, attributionControl: false })
          .setView(LIMA_CENTER, 11);

  // Tiles oscuros (CartoDB dark) para combinar con el tema del dashboard
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    subdomains: 'abcd',
  }).addTo(_map);

  buildMarkersLayer();
  buildHeatLayer();
  setMapMode('marcadores');
}

function buildMarkersLayer() {
  if (_markersLayer) _map.removeLayer(_markersLayer);
  _markersLayer = L.layerGroup();

  const counts = alertCountsByNode();
  const maxCount = Math.max(1, ...Object.values(counts));

  for (const node of NODES) {
    const c = counts[node.id] || 0;
    const last = alertsForNode(node.id)[0];
    // tamaño/color del pin según cantidad de alertas (más alertas = más crítico)
    const ratio = c / maxCount;
    const radius = 8 + ratio * 16;
    const color = ratio > 0.66 ? '#ff4d4f' : ratio > 0.33 ? '#faad14' : '#52c41a';

    const marker = L.circleMarker([node.lat, node.lon], {
      radius, color, weight: 2, fillColor: color, fillOpacity: 0.35,
    });

    marker.bindPopup(
      '<div class="map-popup">' +
        '<strong>' + node.name + '</strong><br>' +
        '<span class="muted">' + node.district + '</span><br>' +
        '<b>' + c + '</b> alertas registradas<br>' +
        (last
          ? 'Última: ' + timeAgo(last.ts) + '<br>GPS sats: ' + last.sensors.sats
          : 'Sin alertas') +
        '<br><a href="#" onclick="renderNodeDetail(\'' + node.id + '\');return false;">Ver historial →</a>' +
      '</div>'
    );
    marker.on('click', () => marker.openPopup());
    _markersLayer.addLayer(marker);
  }
}

function buildHeatLayer() {
  if (_heatLayer) _map.removeLayer(_heatLayer);
  // un punto de calor por alerta, ponderado por la confianza de detección
  const points = ALERTS.map(a => [a.lat, a.lon, a.confidence]);
  _heatLayer = L.heatLayer(points, {
    radius: 30,
    blur: 22,
    maxZoom: 13,
    gradient: { 0.2: '#2b6cb0', 0.4: '#38a169', 0.6: '#d69e2e', 0.8: '#dd6b20', 1.0: '#e53e3e' },
  });
}

function setMapMode(mode) {
  _mapMode = mode;
  if (!_map) return;
  if (mode === 'calor') {
    if (_markersLayer) _map.removeLayer(_markersLayer);
    _heatLayer.addTo(_map);
  } else {
    if (_heatLayer) _map.removeLayer(_heatLayer);
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
  if (node && _map) _map.setView([node.lat, node.lon], 14, { animate: true });
}

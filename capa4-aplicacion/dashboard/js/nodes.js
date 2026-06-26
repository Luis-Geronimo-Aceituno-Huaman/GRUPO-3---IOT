/*
 * nodes.js — Pestañas de MONITOREO DE NODOS del dashboard unificado.
 *
 * Consume las APIs que sirve serve.py desde monitor.db:
 *   /api/nodes
 *   /api/node/<name>            (incluye anomalies + status_history)
 *   /api/node/<name>/detections?page=&size=
 *   /api/node/<name>/heartbeats
 *   /api/videos?node=&order=&desc=
 *
 * Pinta: Nodos (tarjetas + última alerta), Estado (tabla con color, auto-refresh
 * 60s) y Video Log (tabla ordenable/filtrable). El detalle de un nodo se abre en
 * el modal #nodeModal (reutilizado).
 */

/* ------------------------------ helpers ------------------------------ */
async function _getJSON(url) {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

function _isoRel(iso) {
  if (!iso) return 'nunca';
  const t = Date.parse(iso);
  if (isNaN(t)) return iso;
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 0) return 'ahora';
  if (s < 60) return `hace ${s} s`;
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  return `hace ${Math.floor(s / 86400)} d`;
}

function _isoShort(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString('es-PE',
    { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function _uptime(s) {
  if (s == null) return '—';
  s = Math.floor(s);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return (d ? d + 'd ' : '') + (h ? h + 'h ' : '') + m + 'm';
}

function _battery(p) { return (p == null || p < 0) ? 'N/A' : Math.round(p) + '%'; }
function _temp(t) { return (t == null) ? '—' : (Math.round(t * 10) / 10) + ' °C'; }
function _statusBadge(st) {
  const s = st || 'UNKNOWN';
  return `<span class="status-badge st-${s}">${s}</span>`;
}
function _esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

/* ------------------------------ contadores en las pestañas ------------------------------ */
function updateTabCounts(nodes) {
  const online = nodes.filter(n => n.status === 'ONLINE').length;
  const elN = document.getElementById('cntNodos');
  const elO = document.getElementById('cntOnline');
  if (elN) elN.textContent = nodes.length;
  if (elO) elO.textContent = online;
}

async function loadInitialCounts() {
  try {
    const [nodes, vids] = await Promise.all([
      _getJSON('/api/nodes').catch(() => []),
      _getJSON('/api/videos').catch(() => []),
    ]);
    updateTabCounts(nodes);
    const elV = document.getElementById('cntVideos');
    if (elV) elV.textContent = vids.length;
  } catch (_) {}
}

/* ------------------------------ PESTAÑA NODOS ------------------------------ */
async function renderNodesTab() {
  const grid = document.getElementById('nodeCards');
  const lastWrap = document.getElementById('lastAlertCards');
  const count = document.getElementById('nodosCount');
  try {
    const nodes = await _getJSON('/api/nodes');
    count.textContent = `(${nodes.length})`;
    updateTabCounts(nodes);
    if (!nodes.length) {
      grid.innerHTML = '<div class="empty-state"><div class="big">📡</div>Aún no hay nodos registrados.<br>' +
        '<span class="small">Aparecerán automáticamente cuando un ESP32 publique su primer mensaje.</span></div>';
      lastWrap.innerHTML = '';
      return;
    }
    grid.innerHTML = nodes.map(n => `
      <div class="node-card st-${n.status || 'UNKNOWN'}" onclick="openNodeMonitorDetail('${_esc(n.node_name)}')">
        <h3>${_esc(n.node_name)} ${_statusBadge(n.status)}</h3>
        <div class="node-kv"><span>Batería</span><span>${_battery(n.battery_pct)}</span></div>
        <div class="node-kv"><span>Temp chip</span><span>${_temp(n.chip_temp_c)}</span></div>
        <div class="node-kv"><span>Último heartbeat</span><span>${_isoRel(n.last_heartbeat)}</span></div>
        <div class="node-kv"><span>Umbral</span><span>${n.threshold ?? '—'}</span></div>
        <div class="node-actions">
          <button class="btn-sm accent" onclick="event.stopPropagation(); recalibrateNode('${_esc(n.node_name)}')">🎚 Recalibrar</button>
        </div>
      </div>`).join('');

    // última alerta (detección) por nodo: 1 petición liviana por nodo
    const lasts = await Promise.all(nodes.map(n =>
      _getJSON(`/api/node/${encodeURIComponent(n.node_name)}/detections?size=1`)
        .then(r => ({ node: n.node_name, det: r.rows[0] || null }))
        .catch(() => ({ node: n.node_name, det: null }))));
    lastWrap.innerHTML = lasts.map(({ node, det }) => `
      <div class="node-card" onclick="openNodeMonitorDetail('${_esc(node)}')">
        <h3>${_esc(node)} · última alerta</h3>
        ${det ? `
          <div class="node-kv"><span>Score</span><span>${det.score ?? '—'}</span></div>
          <div class="node-kv"><span>Umbral usado</span><span>${det.threshold_used ?? '—'}</span></div>
          <div class="node-kv"><span>Cuándo</span><span>${_isoRel(det.timestamp)}</span></div>
          <div class="muted small">${_isoShort(det.timestamp)}</div>`
        : '<div class="muted small">Sin detecciones todavía</div>'}
      </div>`).join('');
  } catch (e) {
    grid.innerHTML = `<p class="muted">No se pudo cargar /api/nodes: ${_esc(e.message)}</p>`;
  }
}

/* ------------------------------ PESTAÑA ESTADO ------------------------------ */
async function renderStatusTab() {
  const body = document.getElementById('statusBody');
  try {
    const nodes = await _getJSON('/api/nodes');
    if (!nodes.length) {
      body.innerHTML = '<tr class="empty-row"><td colspan="7">No hay nodos registrados.</td></tr>';
      return;
    }
    body.innerHTML = nodes.map(n => `
      <tr onclick="openNodeMonitorDetail('${_esc(n.node_name)}')" style="cursor:pointer">
        <td>${_esc(n.node_name)}</td>
        <td>${_statusBadge(n.status)}</td>
        <td>${_isoShort(n.last_heartbeat)}<div class="muted small">${_isoRel(n.last_heartbeat)}</div></td>
        <td>${_battery(n.battery_pct)}</td>
        <td>${_temp(n.chip_temp_c)}</td>
        <td>${_uptime(n.uptime_s)}</td>
        <td><button class="btn-sm" onclick="event.stopPropagation(); requestHeartbeat('${_esc(n.node_name)}')">💓 Pedir heartbeat</button></td>
      </tr>`).join('');
  } catch (e) {
    body.innerHTML = `<tr class="empty-row"><td colspan="7">Error: ${_esc(e.message)}</td></tr>`;
  }
}

/* Pide al nodo que publique su heartbeat YA (sin esperar el intervalo de 10 min).
 * El server publica "heartbeat" en devices/<name>/cmd; el firmware (smRequestHeartbeat)
 * vence el temporizador y el proximo smLoop() lo envia con su umbral/seq actuales. */
async function requestHeartbeat(name) {
  try {
    const res = await fetch(`/api/node/${encodeURIComponent(name)}/cmd`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'heartbeat' }),
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.error || ('HTTP ' + res.status));
    }
    alert(`Heartbeat solicitado a ${name}.\n\n` +
      `Si el nodo está online, en unos segundos verás actualizado su "Último ` +
      `heartbeat" (refrescá la pestaña Estado).`);
  } catch (e) {
    alert(`No se pudo pedir el heartbeat a ${name}: ${e.message}`);
  }
}

/* ------------------------------ PESTAÑA VIDEO LOG ------------------------------ */
const _videoState = { node: '', order: 'received_at', desc: true };

async function renderVideosTab() {
  const body = document.getElementById('videosBody');
  // poblar el filtro de nodos (una vez)
  const sel = document.getElementById('videoNodeFilter');
  if (sel.options.length <= 1) {
    try {
      const nodes = await _getJSON('/api/nodes');
      nodes.forEach(n => {
        const o = document.createElement('option');
        o.value = n.node_name; o.textContent = n.node_name;
        sel.appendChild(o);
      });
    } catch (_) {}
  }
  try {
    const q = `/api/videos?node=${encodeURIComponent(_videoState.node)}` +
              `&order=${_videoState.order}&desc=${_videoState.desc ? 1 : 0}`;
    const vids = await _getJSON(q);
    const elV = document.getElementById('cntVideos');
    if (elV && !_videoState.node) elV.textContent = vids.length;
    if (!vids.length) {
      body.innerHTML = '<tr class="empty-row"><td colspan="4">No hay videos para este filtro.</td></tr>';
      return;
    }
    body.innerHTML = vids.map(v => `
      <tr id="video-row-${v.id}">
        <td>${_esc(v.node_name)}</td>
        <td>${_isoShort(v.received_at)}</td>
        <td>${v.file_size_kb} KB</td>
        <td><a href="/${_esc(v.file_path)}" download>Descargar</a> ·
            <a href="/${_esc(v.file_path)}" target="_blank">Ver</a> ·
            <button class="btn-sm danger" onclick="deleteVideo(${v.id}, '${_esc(v.node_name)}')">🗑 Eliminar</button></td>
      </tr>`).join('');
  } catch (e) {
    body.innerHTML = `<tr class="empty-row"><td colspan="4">Error: ${_esc(e.message)}</td></tr>`;
  }
}

/* Eliminar un video del log (borra la fila en la BD y el archivo del disco). */
async function deleteVideo(id, nodeName) {
  if (!confirm(`¿Eliminar este video de ${nodeName}?\n\nSe borrará el clip del disco de forma permanente.`)) return;
  try {
    const res = await fetch(`/api/video/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const row = document.getElementById('video-row-' + id);
    if (row) row.remove();
    // refrescar el contador de la pestaña (solo cuando no hay filtro de nodo)
    const elV = document.getElementById('cntVideos');
    if (elV && !_videoState.node) elV.textContent = Math.max(0, (parseInt(elV.textContent, 10) || 1) - 1);
  } catch (e) {
    alert('No se pudo eliminar el video: ' + e.message);
  }
}

/* Pide al nodo que recalibre su umbral de audio. El server publica "recalib" en
 * devices/<name>/cmd; el ESP32 (suscrito) re-mide el ruido de fondo ~10 s. */
async function recalibrateNode(name) {
  if (!confirm(`¿Recalibrar el nodo ${name}?\n\n` +
    `Medirá el ruido de fondo ~10 s y reajustará su umbral de detección. ` +
    `No dispara alertas durante ese lapso.`)) return;
  try {
    const res = await fetch(`/api/node/${encodeURIComponent(name)}/cmd`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'recalib' }),
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.error || ('HTTP ' + res.status));
    }
    alert(`Orden de recalibración enviada a ${name}.\n\n` +
      `Se aplicará en cuanto el nodo reciba el comando por MQTT (si está online).`);
  } catch (e) {
    alert(`No se pudo enviar la recalibración a ${name}: ${e.message}`);
  }
}

/* ------------------------------ DETALLE DE NODO (modal) ------------------------------ */
let _monNodeChart = null;

async function openNodeMonitorDetail(name) {
  const modal = document.getElementById('nodeModal');
  const body = document.getElementById('nodeModalBody');
  body.innerHTML = `<h2>${_esc(name)}</h2><p class="muted">Cargando…</p>`;
  modal.classList.add('open');
  try {
    const [node, dets, hbs] = await Promise.all([
      _getJSON(`/api/node/${encodeURIComponent(name)}`),
      _getJSON(`/api/node/${encodeURIComponent(name)}/detections?size=50`),
      _getJSON(`/api/node/${encodeURIComponent(name)}/heartbeats`),
    ]);

    const detRows = dets.rows.length ? dets.rows.map(d => `
      <tr><td>${_isoShort(d.timestamp)}</td><td>${d.score ?? '—'}</td>
          <td>${d.threshold_used ?? '—'}</td><td>${d.seq ?? '—'}</td></tr>`).join('')
      : '<tr class="empty-row"><td colspan="4">Sin detecciones.</td></tr>';

    const anomRows = (node.anomalies || []).length ? node.anomalies.map(a => `
      <tr><td>${_isoShort(a.timestamp)}</td><td>${_esc(a.type)}</td><td>${_esc(a.detail)}</td></tr>`).join('')
      : '<tr class="empty-row"><td colspan="3">Sin anomalías.</td></tr>';

    body.innerHTML = `
      <div class="modal-head">
        <h2>${_esc(name)} ${_statusBadge(node.status)}</h2>
      </div>
      <div class="node-detail-grid">
        <div class="node-kv"><span>Primera vez</span><span>${_isoShort(node.first_seen)}</span></div>
        <div class="node-kv"><span>Última vez</span><span>${_isoRel(node.last_seen)}</span></div>
        <div class="node-kv"><span>Último heartbeat</span><span>${_isoRel(node.last_heartbeat)}</span></div>
        <div class="node-kv"><span>Batería</span><span>${_battery(node.battery_pct)}</span></div>
        <div class="node-kv"><span>Temp chip</span><span>${_temp(node.chip_temp_c)}</span></div>
        <div class="node-kv"><span>Umbral</span><span>${node.threshold ?? '—'}</span></div>
        <div class="node-kv"><span>Uptime</span><span>${_uptime(node.uptime_s)}</span></div>
      </div>

      <h3>Tendencia de temperatura (heartbeat)</h3>
      <div class="mini-chart"><canvas id="monNodeChart"></canvas></div>

      <h3>Historial de detecciones (${dets.total})</h3>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Timestamp</th><th>Score</th><th>Umbral usado</th><th>Seq</th></tr></thead>
        <tbody>${detRows}</tbody></table></div>

      <h3 style="margin-top:18px">Anomalías</h3>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>Timestamp</th><th>Tipo</th><th>Detalle</th></tr></thead>
        <tbody>${anomRows}</tbody></table></div>`;

    // gráfico de temperatura con Chart.js (ya cargado)
    if (_monNodeChart) { _monNodeChart.destroy(); _monNodeChart = null; }
    const labels = hbs.map(h => _isoShort(h.timestamp));
    const temps = hbs.map(h => h.chip_temp_c);
    if (temps.length >= 2 && window.Chart) {
      _monNodeChart = new Chart(document.getElementById('monNodeChart'), {
        type: 'line',
        data: { labels, datasets: [{ label: 'Temp chip °C', data: temps,
          borderColor: '#d08770', tension: 0.3, pointRadius: 2 }] },
        options: { responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#8b92a5' } } },
          scales: { x: { ticks: { color: '#8b92a5' } }, y: { ticks: { color: '#8b92a5' } } } },
      });
    } else {
      document.getElementById('monNodeChart').parentElement.innerHTML =
        '<p class="muted small">Sin datos suficientes para graficar.</p>';
    }
  } catch (e) {
    body.innerHTML = `<h2>${_esc(name)}</h2><p class="muted">Error: ${_esc(e.message)}</p>`;
  }
}

/* ------------------------------ navegación de pestañas ------------------------------ */
let _statusTimer = null;

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p =>
    p.classList.toggle('active', p.id === 'tab-' + name));

  // refleja la pestaña en la URL (#nodos, #estado…) para que sea enlazable/recargable
  if (('#' + name) !== location.hash) history.replaceState(null, '', '#' + name);

  // refresco automático del Estado solo mientras esa pestaña está visible
  if (_statusTimer) { clearInterval(_statusTimer); _statusTimer = null; }

  if (name === 'nodos') renderNodesTab();
  else if (name === 'estado') { renderStatusTab(); _statusTimer = setInterval(renderStatusTab, 60000); }
  else if (name === 'videos') renderVideosTab();
  // 'resumen' y 'detecciones' los pinta app.js al cargar (KPIs/gráficos/tabla)

  // el mapa vive en su propia pestaña; Leaflet necesita recalcular tamaño al mostrarse
  if (name === 'mapa' && typeof _map !== 'undefined' && _map)
    setTimeout(() => _map.invalidateSize(), 50);
}

function initNodesTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn =>
    btn.addEventListener('click', () => switchTab(btn.dataset.tab)));

  // ordenar Video Log por cabecera
  document.querySelectorAll('#tab-videos th[data-sort]').forEach(th =>
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      _videoState.desc = (_videoState.order === col) ? !_videoState.desc : true;
      _videoState.order = col;
      renderVideosTab();
    }));

  // filtrar Video Log por nodo
  const sel = document.getElementById('videoNodeFilter');
  if (sel) sel.addEventListener('change', () => { _videoState.node = sel.value; renderVideosTab(); });

  // contadores iniciales en las pestañas (sin tener que entrar a cada una)
  loadInitialCounts();

  // deep-link: abrir la pestaña indicada en la URL (#mapa/#detecciones/#nodos…)
  const TABS = ['resumen', 'mapa', 'detecciones', 'nodos', 'estado', 'videos'];
  const initial = (location.hash || '').replace('#', '');
  if (TABS.includes(initial) && initial !== 'resumen') switchTab(initial);
  // soportar navegación atrás/adelante del navegador
  window.addEventListener('hashchange', () => {
    const t = (location.hash || '').replace('#', '') || 'resumen';
    if (TABS.includes(t)) switchTab(t);
  });
}

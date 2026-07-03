/*
 * alerts.js — Renderizado y WORKFLOW de alertas (persistente en BD).
 *
 *   - renderMainAlerts(): tabla de detecciones (todas, incluidas las descartadas
 *     — la limpieza automática aplica solo al MAPA; aquí queda la auditoría).
 *   - renderNodeDetail(nodeId): modal con el historial de alarmas de un nodo.
 *   - openResponseModal(alertId): flujo de atención REAL → PATCH /api/alerts/<id>/status
 *     con comentario; cada cambio queda en alert_history (quién, cuándo, por qué).
 */

/* badge de confianza con color según nivel */
function confidenceBadge(conf) {
  const pct = Math.round((conf || 0) * 100);
  const cls = conf >= 0.85 ? 'high' : conf >= 0.7 ? 'mid' : 'low';
  return '<span class="conf ' + cls + '">' + pct + '%</span>';
}

function statusBadge(status) {
  return '<span class="status-pill ' + status + '">' + (STATUS_LABEL[status] || status) + '</span>';
}

/* Resumen de sensores: muestra SIEMPRE los campos del nodo real; los extra
 * (humedad/pH — del simulador o nodos futuros) solo si llegaron. Los null se
 * marcan "N/D" en gris. -127°C = sonda DS18B20 sin conectar. */
function sensorSummary(s) {
  s = s || {};
  const na = '<i class="na">N/D</i>';
  const temp = (s.temp_c == null) ? na
    : (s.temp_c <= -100 ? '<i class="na" title="DS18B20 sin conectar">sin sonda</i>' : s.temp_c + '°C');
  const turb = (s.turb_v == null) ? na : s.turb_v + 'V';
  const sats = (s.sats   == null) ? na : s.sats;
  const parts = [
    '<span title="Temperatura (DS18B20)">🌡️ ' + temp + '</span>',
    '<span title="Turbidez del agua">💧 ' + turb + '</span>',
  ];
  if (s.humedad != null)    parts.push('<span title="Humedad relativa">💦 ' + s.humedad + '%</span>');
  if (s.ph != null)         parts.push('<span title="pH del agua">⚗️ ' + s.ph + '</span>');
  if (s.nivel_agua != null) parts.push('<span title="Nivel de agua">🌊 ' + s.nivel_agua + 'cm</span>');
  if (s.audio_rms != null)  parts.push('<span title="Audio RMS (aleteo)">🔊 ' + s.audio_rms + '</span>');
  parts.push('<span title="Satélites GPS">🛰️ ' + sats + '</span>');
  // Los chips van en un contenedor flex PROPIO: si el flex se aplicara al <td>
  // este deja de comportarse como celda de tabla y las columnas se desalinean.
  return '<div class="sensor-chips">' + parts.join('') + '</div>';
}

/* Badge del tipo de deteccion (Mosquito / Enjambre) segun la clase del detector. */
function classBadge(a) {
  const c = a.detClass || 'Mosquito';
  const swarm = /swarm|enjambre/i.test(c);
  const sim = a.isSynthetic ? ' <span class="sim-tag" title="alerta sintética de prueba">SIM</span>' : '';
  return '<span class="src-pill camera">' + (swarm ? '🦟🦟 Enjambre' : '🦟 Mosquito') + '</span>' + sim;
}

/* ---------------- Tabla principal: TODAS las detecciones (feed) ---------------- */
function renderMainAlerts() {
  const list = [...ALERTS].sort((a, b) => b.ts - a.ts);
  const tbody = document.getElementById('mainAlertsBody');
  const count = document.getElementById('detCount');
  if (count) count.textContent = list.length ? (list.length + ' detecciones') : '';
  const tabCount = document.getElementById('cntDet');
  if (tabCount) tabCount.textContent = list.length;

  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted" style="text-align:center;padding:28px">
      Aún no hay detecciones. Cuando el nodo confirme un mosquito, aparecerá aquí con su video.</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(a => `
    <tr class="${HIDDEN_ON_MAP.includes(a.status) ? 'row-dim' : ''}">
      <td><div>${formatTime(a.ts)}</div><div class="muted small">${timeAgo(a.ts)}</div></td>
      <td>${classBadge(a)}</td>
      <td>${confidenceBadge(a.confidence)}</td>
      <td>${riskBadge(a.riskLevel)}</td>
      <td class="sensors">${sensorSummary(a.sensors)}</td>
      <td>${statusBadge(a.status)}</td>
      <td class="actions">
        ${a.videoUrl ? `<button class="btn-sm video" onclick="openVideoModal(${a.id})">▶ Video</button>` : '<span class="muted small">sin video</span>'}
        <button class="btn-sm accent" onclick="openResponseModal(${a.id})">Gestionar</button>
      </td>
    </tr>
  `).join('');
}

/* ---------------- Detalle de un nodo: todas sus alarmas ---------------- */
function renderNodeDetail(nodeId) {
  const node = NODE_BY_ID[nodeId];
  if (!node) return;
  const list = alertsForNode(nodeId);
  const modal = document.getElementById('nodeModal');
  const body = document.getElementById('nodeModalBody');

  const totalConf = list.reduce((s, a) => s + (a.confidence || 0), 0);
  const avgConf = list.length ? Math.round((totalConf / list.length) * 100) : 0;
  const gps = (node.lat != null && node.lon != null)
    ? `GPS ${node.lat.toFixed(4)}, ${node.lon.toFixed(4)}` : 'sin posición GPS';

  body.innerHTML = `
    <div class="modal-head">
      <div>
        <h2>${node.name} ${riskBadge(node.riskLevel, node.riskScore)}</h2>
        <div class="muted">${node.district} · ${gps}</div>
      </div>
      <div class="modal-kpis">
        <div class="kpi-mini"><span>${list.length}</span><label>alertas</label></div>
        <div class="kpi-mini"><span>${avgConf}%</span><label>confianza prom.</label></div>
      </div>
    </div>

    <div class="modal-chart"><canvas id="chartNodeDetail"></canvas></div>

    <h3>Historial completo de alarmas</h3>
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr><th>Fecha/Hora</th><th>Confianza</th><th>Riesgo</th><th>Sensores</th><th>Estado</th><th></th></tr>
        </thead>
        <tbody>
          ${list.map(a => `
            <tr class="${HIDDEN_ON_MAP.includes(a.status) ? 'row-dim' : ''}">
              <td>${formatTime(a.ts)}<div class="muted small">${timeAgo(a.ts)}</div></td>
              <td>${confidenceBadge(a.confidence)}</td>
              <td>${riskBadge(a.riskLevel)}</td>
              <td class="sensors">${sensorSummary(a.sensors)}</td>
              <td>${statusBadge(a.status)}</td>
              <td>
                ${a.videoUrl ? `<button class="btn-sm video" onclick="openVideoModal(${a.id})">▶ Video</button>` : ''}
                <button class="btn-sm accent" onclick="openResponseModal(${a.id})">Gestionar</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;

  modal.classList.add('open');
  renderChartNodeDetail(nodeId);
  focusNodeOnMap(nodeId);
}

function closeNodeModal() {
  document.getElementById('nodeModal').classList.remove('open');
}

/* ---------------- Flujo de atención (persistente en BD) ---------------- */
async function openResponseModal(alertId) {
  const a = ALERTS.find(x => x.id === alertId);
  if (!a) return;
  const modal = document.getElementById('responseModal');
  const terminal = (a.status === 'descartada');

  // historial de transiciones (auditoría) — se pinta debajo del formulario
  let historyHtml = '<div class="muted small">cargando historial…</div>';
  document.getElementById('responseBody').innerHTML = `
    <h2>Gestionar alerta #${a.id}</h2>
    <p class="muted">${a.nodeName} · ${a.district} · ${formatTime(a.ts)} ·
      estado actual: ${statusBadge(a.status)}</p>

    ${terminal ? `<div class="banner-info">🔒 Esta alerta está <b>descartada</b>
      (estado final): solo se conserva para auditoría.</div>` : `
    <label class="form-label">Plan de acción</label>
    <select id="responseAction" class="form-input">
      ${ALERT_ACTIONS_UI.map(o => `<option value="${o.action}">${o.label}</option>`).join('')}
    </select>
    <p class="muted small" style="margin:6px 0 0">
      🚫 <b>Falsa alarma</b> elimina la alerta de la base de datos y no se vuelve a
      mostrar · ✅ <b>Atender</b> la envía a la pestaña <b>Atención</b> para que un
      operador la trabaje · 🔍 <b>Por revisar</b> la deja pendiente de verificación.</p>

    <label class="form-label">Comentario</label>
    <textarea id="responseNote" class="form-input" rows="3"
      placeholder="Qué se hizo / por qué (queda en el historial de auditoría)..."></textarea>

    <div class="modal-actions">
      <button class="btn" onclick="closeResponseModal()">Cancelar</button>
      <button class="btn accent" id="responseSubmit" onclick="submitResponse(${a.id})">Confirmar</button>
    </div>`}

    <h3 style="margin-top:18px">Historial de cambios</h3>
    <div id="responseHistory">${historyHtml}</div>
  `;
  modal.classList.add('open');

  try {
    const hist = await fetchJSON(`/api/alerts/${alertId}/history`);
    document.getElementById('responseHistory').innerHTML = hist.length ? `
      <ul class="history-list">
        ${hist.map(h => `
          <li>
            <span class="history-when">${new Date(h.ts).toLocaleString('es-PE')}</span>
            ${h.old_status ? statusBadge(h.old_status) + ' →' : ''} ${statusBadge(h.new_status)}
            ${h.username ? '<span class="history-user">👤 ' + h.username + '</span>' : ''}
            ${h.comment ? '<div class="history-comment">💬 ' + h.comment + '</div>' : ''}
          </li>`).join('')}
      </ul>` : '<div class="muted small">sin cambios registrados</div>';
  } catch (e) {
    document.getElementById('responseHistory').innerHTML =
      '<div class="muted small">no se pudo cargar el historial: ' + e.message + '</div>';
  }
}

/* Recarga desde la BD y repinta TODAS las vistas que muestran alertas. */
async function refreshAlertViews() {
  await reloadData();
  renderMainAlerts();
  renderAttentionQueue();
  renderKpis();
  refreshMapLayers();
  renderAllCharts();
}

async function submitResponse(alertId) {
  const action = document.getElementById('responseAction').value;
  const comment = (document.getElementById('responseNote').value || '').trim();
  const btn = document.getElementById('responseSubmit');

  // Falsa alarma = borrado DEFINITIVO de la BD (no vuelve a mostrarse).
  if (action === 'falsa-alarma' &&
      !confirm(`¿Marcar la alerta #${alertId} como FALSA ALARMA?\n\n` +
               'Se eliminará de la base de datos de forma definitiva y no se ' +
               'volverá a mostrar en el dashboard.')) return;

  if (btn) { btn.disabled = true; btn.textContent = 'Guardando…'; }
  try {
    let msg;
    if (action === 'falsa-alarma') {
      await fetchJSON(`/api/alerts/${alertId}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment }),
      });
      msg = `Alerta #${alertId} eliminada (falsa alarma) ✓`;
    } else {
      const r = await fetchJSON(`/api/alerts/${alertId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, comment }),
      });
      msg = `Alerta #${alertId}: ${STATUS_LABEL[r.old] || r.old} → ${STATUS_LABEL[r.new] || r.new} ✓`;
    }
    closeResponseModal();
    closeNodeModal();
    await refreshAlertViews();
    toast(msg);
  } catch (e) {
    toast('No se pudo actualizar: ' + e.message, true);
    if (btn) { btn.disabled = false; btn.textContent = 'Confirmar'; }
  }
}

/* ---------------- Pestaña ATENCIÓN: cola de trabajo de los operadores -------- */
/* Aquí caen las alertas marcadas con "Atender": cada operador las ve y las
 * cierra con "Marcar atendida" (→ estado final 'resuelta' en la BD). */
function renderAttentionQueue() {
  const list = attentionQueue();
  const tbody = document.getElementById('attentionBody');
  const tabCount = document.getElementById('cntAtencion');
  if (tabCount) tabCount.textContent = list.length;
  if (!tbody) return;

  const sub = document.getElementById('attentionCount');
  if (sub) sub.textContent = list.length ? (list.length + ' por atender') : '';

  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="muted" style="text-align:center;padding:28px">
      No hay alertas en la cola de atención. Cuando alguien marque una detección
      como “Atender”, aparecerá aquí para los operadores.</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(a => `
    <tr>
      <td><div>${formatTime(a.ts)}</div><div class="muted small">${timeAgo(a.ts)}</div></td>
      <td>${attentionLocationCell(a)}</td>
      <td>${classBadge(a)}</td>
      <td>${riskBadge(a.riskLevel)}</td>
      <td class="sensors">${sensorSummary(a.sensors)}</td>
      <td class="actions">
        ${a.videoUrl ? `<button class="btn-sm video" onclick="openVideoModal(${a.id})">▶ Video</button>` : ''}
        <button class="btn-sm accent" onclick="resolveAttention(${a.id})">🏁 Marcar atendida</button>
      </td>
    </tr>
  `).join('');
}

/* Celda "Nodo / Ubicación" de la cola: todo lo que el encargado necesita para
 * saber A DÓNDE ir — nodo, distrito, coordenadas GPS, ver en el mapa del panel
 * y ruta en Google Maps desde su posición actual. */
function attentionLocationCell(a) {
  const node = NODE_BY_ID[a.nodeId];
  const lat = a.lat ?? node?.lat;
  const lon = a.lon ?? node?.lon;
  const hasGps = (lat != null && lon != null);
  const gps = hasGps
    ? `<div class="muted small" title="Coordenadas GPS del nodo">📡 GPS ${(+lat).toFixed(5)}, ${(+lon).toFixed(5)}</div>`
    : '<div class="muted small">📡 sin posición GPS</div>';
  const estado = node
    ? `<div class="muted small">nodo ${node.status || '?'} · batería ${node.battery == null || node.battery < 0 ? 'N/A' : Math.round(node.battery) + '%'}</div>`
    : '';
  const links = hasGps ? `
    <div class="loc-links">
      <button class="btn-sm" onclick="showAlertOnMap('${a.nodeId}')" title="Centrar el mapa del panel en este nodo">📍 Ver en mapa</button>
      <a class="btn-sm btn-link" target="_blank" rel="noopener"
         href="https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}"
         title="Ruta en Google Maps hasta el nodo">🧭 Cómo llegar</a>
    </div>` : '';
  return `
    <div class="loc-cell">
      <div><b>${a.nodeName || a.nodeId}</b></div>
      <div class="muted small">📌 ${a.district || 'distrito sin registrar'}</div>
      ${gps}
      ${estado}
      ${links}
    </div>`;
}

/* Abre la pestaña Mapa centrada en el nodo de la alerta. */
function showAlertOnMap(nodeId) {
  switchTab('mapa');
  // Leaflet recalcula tamaño al mostrarse (ver switchTab); centramos después.
  setTimeout(() => focusNodeOnMap(nodeId), 120);
}

/* El operador terminó de atender la alerta → 'resuelta' (sale de la cola). */
async function resolveAttention(alertId) {
  const comment = prompt('Comentario de cierre (qué se hizo en campo):', '');
  if (comment === null) return;           // canceló
  try {
    await fetchJSON(`/api/alerts/${alertId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'resolver', comment: comment.trim() }),
    });
    await refreshAlertViews();
    toast(`Alerta #${alertId} atendida ✓`);
  } catch (e) {
    toast('No se pudo cerrar la alerta: ' + e.message, true);
  }
}

function closeResponseModal() {
  document.getElementById('responseModal').classList.remove('open');
}

/* Aviso flotante no bloqueante (reemplaza a alert()). */
function toast(msg, isError = false) {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = 'show' + (isError ? ' error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.className = ''; }, 3500);
}

/* ---------------- Ver video del clip confirmado por el detector ---------------- */
function openVideoModal(alertId) {
  const a = ALERTS.find(x => x.id === alertId);
  if (!a) return;
  const modal = document.getElementById('videoModal');
  const body = document.getElementById('videoBody');

  if (a.videoUrl) {
    const cls = a.detClass || '—';
    const dets = a.detCount != null ? a.detCount : 0;
    body.innerHTML = `
      <h2>Video de la alerta</h2>
      <p class="muted">${a.nodeName} · ${a.district} · ${formatTime(a.ts)}</p>
      <div class="video-verdict">
        ✅ Confirmado por detector de movimiento — <strong>${cls}</strong>
        ${confidenceBadge(a.confidence)}
        <span class="muted small">${dets} detecciones</span>
      </div>
      <video class="alert-video" src="${a.videoUrl}" controls autoplay muted playsinline></video>
      <p class="muted small">Clip grabado por la cámara al dispararse el nodo y analizado por
        el detector de movimiento (MOG2 + flujo optico). Solo se guardan las alertas confirmadas.</p>
    `;
  } else {
    body.innerHTML = `
      <h2>Video de la alerta</h2>
      <p class="muted">${a.nodeName} · ${formatTime(a.ts)}</p>
      <div class="banner-info">Esta alerta no tiene clip de video asociado
        ${a.isSynthetic ? '(es una alerta sintética de prueba).' : '.'}</div>
    `;
  }
  modal.classList.add('open');
}

function closeVideoModal() {
  const v = document.querySelector('#videoBody video');
  if (v) v.pause();
  document.getElementById('videoModal').classList.remove('open');
}

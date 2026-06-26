/*
 * alerts.js — Renderizado de alarmas.
 *
 *   - renderMainAlerts(): dashboard principal → UNA alerta (la más reciente) por nodo.
 *   - renderNodeDetail(nodeId): modal con TODO el historial de alarmas de ese nodo.
 *   - openResponseModal(alertId): modal para "responder" una alerta (flujo placeholder).
 */

/* badge de confianza con color según nivel */
function confidenceBadge(conf) {
  const pct = Math.round(conf * 100);
  const cls = conf >= 0.85 ? 'high' : conf >= 0.7 ? 'mid' : 'low';
  return '<span class="conf ' + cls + '">' + pct + '%</span>';
}

function statusBadge(status) {
  return '<span class="status-pill ' + status + '">' + (STATUS_LABEL[status] || status) + '</span>';
}

/* Resumen de sensores: muestra SIEMPRE todos los campos. Los que no llegaron
 * (null en la BD) se marcan "N/D" en gris para que quede claro que faltó el dato
 * y no que el dashboard lo esconde. -127°C = sonda DS18B20 sin conectar. */
function sensorSummary(s) {
  s = s || {};
  const na = '<i class="na">N/D</i>';
  const temp = (s.temp_c == null) ? na
    : (s.temp_c <= -100 ? '<i class="na" title="DS18B20 sin conectar">sin sonda</i>' : s.temp_c + '°C');
  const turb = (s.turb_v     == null) ? na : s.turb_v + 'V';
  const arms = (s.audio_rms  == null) ? na : s.audio_rms;
  const peak = (s.audio_peak == null) ? na : s.audio_peak;
  const sats = (s.sats       == null) ? na : s.sats;
  return [
    '<span title="Temperatura (DS18B20)">🌡️ ' + temp + '</span>',
    '<span title="Turbidez del agua">💧 ' + turb + '</span>',
    '<span title="Audio RMS (aleteo)">🔊 ' + arms + '</span>',
    '<span title="Audio pico">📈 ' + peak + '</span>',
    '<span title="Satélites GPS">🛰️ ' + sats + '</span>',
  ].join('');
}

/* Badge del tipo de deteccion (Mosquito / Enjambre) segun la clase del detector. */
function classBadge(a) {
  const c = a.detClass || 'Mosquito';
  const swarm = /swarm|enjambre/i.test(c);
  return '<span class="src-pill camera">' + (swarm ? '🦟🦟 Enjambre' : '🦟 Mosquito') + '</span>';
}

/* ---------------- Dashboard principal: TODAS las detecciones (feed) ---------------- */
function renderMainAlerts() {
  const list = [...ALERTS].sort((a, b) => b.ts - a.ts);
  const tbody = document.getElementById('mainAlertsBody');
  const count = document.getElementById('detCount');
  if (count) count.textContent = list.length ? (list.length + ' detecciones') : '';
  const tabCount = document.getElementById('cntDet');
  if (tabCount) tabCount.textContent = list.length;

  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="muted" style="text-align:center;padding:28px">
      Aún no hay detecciones. Cuando el nodo confirme un mosquito, aparecerá aquí con su video.</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(a => `
    <tr>
      <td><div>${formatTime(a.ts)}</div><div class="muted small">${timeAgo(a.ts)}</div></td>
      <td>${classBadge(a)}</td>
      <td>${confidenceBadge(a.confidence)}</td>
      <td class="sensors">${sensorSummary(a.sensors)}</td>
      <td>${statusBadge(a.status)}</td>
      <td class="actions">
        ${a.videoUrl ? `<button class="btn-sm video" onclick="openVideoModal(${a.id})">▶ Video</button>` : '<span class="muted small">sin video</span>'}
        <button class="btn-sm accent" onclick="openResponseModal(${a.id})">Responder</button>
      </td>
    </tr>
  `).join('');
}

/* ---------------- Detalle de un nodo: todas sus alarmas ---------------- */
function renderNodeDetail(nodeId) {
  const node = NODE_BY_ID[nodeId];
  const list = alertsForNode(nodeId);
  const modal = document.getElementById('nodeModal');
  const body = document.getElementById('nodeModalBody');

  const totalConf = list.reduce((s, a) => s + a.confidence, 0);
  const avgConf = list.length ? Math.round((totalConf / list.length) * 100) : 0;

  body.innerHTML = `
    <div class="modal-head">
      <div>
        <h2>${node.name}</h2>
        <div class="muted">${node.district} · GPS ${node.lat.toFixed(4)}, ${node.lon.toFixed(4)}</div>
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
          <tr><th>Fecha/Hora</th><th>Confianza</th><th>Origen</th><th>Sensores</th><th>Estado</th><th></th></tr>
        </thead>
        <tbody>
          ${list.map(a => `
            <tr>
              <td>${formatTime(a.ts)}<div class="muted small">${timeAgo(a.ts)}</div></td>
              <td>${confidenceBadge(a.confidence)}</td>
              <td><span class="src-pill ${a.source}">${SOURCE_LABEL[a.source]}</span></td>
              <td class="sensors">${sensorSummary(a.sensors)}</td>
              <td>${statusBadge(a.status)}</td>
              <td>
                ${a.videoUrl ? `<button class="btn-sm video" onclick="openVideoModal(${a.id})">▶ Video</button>` : ''}
                <button class="btn-sm accent" onclick="openResponseModal(${a.id})">Responder</button>
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

/* ---------------- Responder alerta (placeholder, flujo pendiente) ---------------- */
function openResponseModal(alertId) {
  const a = ALERTS.find(x => x.id === alertId);
  if (!a) return;
  const modal = document.getElementById('responseModal');
  document.getElementById('responseBody').innerHTML = `
    <h2>Responder alerta</h2>
    <p class="muted">${a.nodeName} · ${a.district} · ${formatTime(a.ts)}</p>

    <div class="banner-info">
      ⚠️ El flujo de respuesta aún no está definido. Por ahora solo se cambia el
      estado de la alerta de forma local (demo).
    </div>

    <label class="form-label">Acción</label>
    <select id="responseAction" class="form-input">
      <option value="atendida">Marcar como atendida</option>
      <option value="fumigacion">Enviar brigada de fumigación</option>
      <option value="falso-positivo">Marcar como falso positivo</option>
    </select>

    <label class="form-label">Nota (opcional)</label>
    <textarea id="responseNote" class="form-input" rows="3" placeholder="Comentario del operador..."></textarea>

    <div class="modal-actions">
      <button class="btn" onclick="closeResponseModal()">Cancelar</button>
      <button class="btn accent" onclick="submitResponse(${a.id})">Confirmar</button>
    </div>
  `;
  modal.classList.add('open');
}

function submitResponse(alertId) {
  const a = ALERTS.find(x => x.id === alertId);
  const action = document.getElementById('responseAction').value;
  if (a) a.status = action;
  closeResponseModal();
  // refrescar vistas que muestran estado
  renderMainAlerts();
  renderKpis();
  closeNodeModal();
}

function closeResponseModal() {
  document.getElementById('responseModal').classList.remove('open');
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
        (probablemente es un dato de demostración, no del pipeline real).</div>
    `;
  }
  modal.classList.add('open');
}

function closeVideoModal() {
  const v = document.querySelector('#videoBody video');
  if (v) v.pause();
  document.getElementById('videoModal').classList.remove('open');
}

/*
 * app.js — Punto de entrada. Sesión + inicialización + KPIs.
 *
 * Orden de carga (ver index.html): data.js → charts.js → map.js → alerts.js
 *                                  → nodes.js → admin.js → app.js
 *
 * Flujo de arranque:
 *   1. GET /api/auth/me → si 401, redirige a login.html (nada se pinta sin sesión).
 *   2. loadNodes() + applyRealAlerts() → TODO desde la BD (cero datos demo).
 *   3. Render de KPIs, tablas, mapa y gráficos.
 */

function renderKpis() {
  const DAY = 24 * 60 * 60 * 1000;
  const vis = visibleAlerts();
  const today = vis.filter(a => Date.now() - a.ts < DAY).length;
  const counts = alertCountsByNode();
  const activeNodes = Object.values(counts).filter(c => c > 0).length;

  // nodo más crítico = el de MAYOR RIESGO (motor risk.py); empata por alertas
  const orden = { critico: 3, alto: 2, medio: 1, bajo: 0 };
  const crit = [...NODES].sort((a, b) =>
    (orden[b.riskLevel] || 0) - (orden[a.riskLevel] || 0) ||
    (b.riskScore || 0) - (a.riskScore || 0) ||
    (counts[b.id] || 0) - (counts[a.id] || 0))[0];

  const avgConf = vis.length
    ? Math.round((vis.reduce((s, a) => s + (a.confidence || 0), 0) / vis.length) * 100)
    : 0;
  const pending = ALERTS.filter(a => a.status === 'pendiente' || a.status === 'en-revision').length;

  document.getElementById('kpiTotal').textContent = ALERTS.length;
  document.getElementById('kpiToday').textContent = today;
  document.getElementById('kpiNodes').textContent = activeNodes + ' / ' + NODES.length;
  document.getElementById('kpiCritical').innerHTML = crit
    ? crit.name + ' ' + (RISK_EMOJI[crit.riskLevel] || '') : '—';
  document.getElementById('kpiCriticalSub').textContent = crit
    ? `riesgo ${RISK_LABEL[crit.riskLevel] || '?'} (${Math.round(crit.riskScore || 0)}) · ${counts[crit.id] || 0} alertas`
    : '';
  document.getElementById('kpiConf').textContent = avgConf + '%';
  document.getElementById('kpiPending').textContent = pending;
}

function startClock() {
  const el = document.getElementById('clock');
  function tick() {
    el.textContent = new Date().toLocaleString('es-PE', {
      weekday: 'long', day: '2-digit', month: 'short',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  }
  tick();
  setInterval(tick, 1000);
}

/* ---------------- sesión ---------------- */
async function bootstrapSession() {
  const res = await fetch('/api/auth/me', { credentials: 'same-origin' });
  if (!res.ok) {
    window.location.href = 'login.html';
    throw new Error('sin sesión');
  }
  CURRENT_USER = await res.json();

  // chip de usuario + logout en el header
  const chip = document.getElementById('userChip');
  if (chip) {
    chip.innerHTML = `
      <span class="user-name" title="${CURRENT_USER.full_name || ''}">
        👤 ${CURRENT_USER.username}
        <span class="role-tag ${CURRENT_USER.role}">${CURRENT_USER.role}</span>
      </span>
      <button class="btn-sm" id="logoutBtn" title="Cerrar sesión">Salir</button>`;
    document.getElementById('logoutBtn').addEventListener('click', async () => {
      try { await fetchJSON('/api/auth/logout', { method: 'POST' }); } catch (e) { /* igual salimos */ }
      window.location.href = 'login.html';
    });
  }

  // controles solo-admin (pestaña Admin)
  if (CURRENT_USER.role === 'admin') {
    document.querySelectorAll('.admin-only').forEach(el => { el.hidden = false; });
  }
}

/* refresco periódico suave: riesgo/estados cambian solos (job cada 5 min) */
function startAutoRefresh(intervalMs = 60000) {
  setInterval(async () => {
    try {
      await reloadData();
      renderKpis();
      renderMainAlerts();
      renderAttentionQueue();
      refreshMapLayers();
      renderAllCharts();
    } catch (e) { /* sin red: se reintenta al siguiente tick */ }
  }, intervalMs);
}

document.addEventListener('DOMContentLoaded', async () => {
  await bootstrapSession();          // redirige a login.html si no hay sesión

  // TODO viene de la BD: nodos (con riesgo/sensores) + alertas confirmadas
  const [nodeCount, realCount] = await Promise.all([loadNodes(), applyRealAlerts()]);
  const badge = document.querySelector('.badge-live');
  if (badge) {
    badge.textContent = realCount !== false
      ? `EN VIVO · ${realCount} alertas · ${nodeCount || 0} nodos`
      : 'SIN CONEXIÓN · /api/alerts';
    badge.classList.toggle('off', realCount === false);
  }

  // KPIs + tabla principal + cola de atención
  renderKpis();
  renderMainAlerts();
  renderAttentionQueue();

  // mapa + gráficos
  initMap();
  renderAllCharts();

  // toggle de modo de mapa
  document.querySelectorAll('[data-mapmode]').forEach(btn => {
    btn.addEventListener('click', () => setMapMode(btn.dataset.mapmode));
  });

  // pestañas de monitoreo de nodos (Nodos · Estado · Video Log) — ver nodes.js
  initNodesTabs();

  // cerrar modales al hacer click en el fondo o en la X
  document.querySelectorAll('.modal').forEach(m => {
    m.addEventListener('click', e => { if (e.target === m) m.classList.remove('open'); });
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open'));
  });

  startClock();
  startAutoRefresh();
});

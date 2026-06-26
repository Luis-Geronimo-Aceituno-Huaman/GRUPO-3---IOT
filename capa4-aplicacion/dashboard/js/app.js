/*
 * app.js — Punto de entrada. Inicializa todo y conecta los controles.
 *
 * Orden de carga (ver index.html): data.js → charts.js → map.js → alerts.js → app.js
 */

function renderKpis() {
  const DAY = 24 * 60 * 60 * 1000;
  const today = ALERTS.filter(a => Date.now() - a.ts < DAY).length;
  const counts = alertCountsByNode();
  const activeNodes = Object.values(counts).filter(c => c > 0).length;

  // nodo más crítico = el de más alertas
  let critId = null, critMax = -1;
  for (const [id, c] of Object.entries(counts)) if (c > critMax) { critMax = c; critId = id; }
  const critNode = NODE_BY_ID[critId];

  const avgConf = ALERTS.length
    ? Math.round((ALERTS.reduce((s, a) => s + a.confidence, 0) / ALERTS.length) * 100)
    : 0;
  const pending = ALERTS.filter(a => a.status === 'nueva').length;

  document.getElementById('kpiTotal').textContent = ALERTS.length;
  document.getElementById('kpiToday').textContent = today;
  document.getElementById('kpiNodes').textContent = activeNodes + ' / ' + NODES.length;
  document.getElementById('kpiCritical').textContent = critNode ? critNode.name : '—';
  document.getElementById('kpiCriticalSub').textContent = critNode ? critMax + ' alertas · ' + critNode.district : '';
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

document.addEventListener('DOMContentLoaded', async () => {
  // cargar distritos reales resueltos (paso 1) antes de pintar; si falla usa demo
  await applyResolvedNodes();

  // cargar alertas REALES confirmadas por el detector; si no hay API, queda vacío
  const realCount = await applyRealAlerts();
  const badge = document.querySelector('.badge-live');
  if (badge) {
    badge.textContent = realCount !== false
      ? `EN VIVO · ${realCount} alertas confirmadas`
      : 'SIN CONEXIÓN · /api/alerts';
    badge.classList.toggle('off', realCount === false);
  }

  // KPIs + tabla principal
  renderKpis();
  renderMainAlerts();

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
});

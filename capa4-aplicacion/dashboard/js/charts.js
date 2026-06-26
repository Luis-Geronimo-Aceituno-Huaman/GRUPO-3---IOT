/*
 * charts.js — Gráficos con Chart.js.
 *
 *   - Alertas por nodo (barras horizontales).
 *   - Alertas en el tiempo (línea, últimos 7 días).
 *   - Gráfico de detalle por nodo (sensores en sus últimas alertas).
 */

const CHART_FONT = "Segoe UI, system-ui, sans-serif";
Chart.defaults.color = '#8b92a5';
Chart.defaults.font.family = CHART_FONT;
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';

let _chartByNode = null;
let _chartByDay = null;
let _chartNodeDetail = null;

function renderChartByNode() {
  const counts = alertCountsByNode();
  const labels = NODES.map(n => n.name);
  const data = NODES.map(n => counts[n.id] || 0);
  const colors = data.map(c => {
    const max = Math.max(1, ...data);
    const r = c / max;
    return r > 0.66 ? '#ff4d4f' : r > 0.33 ? '#faad14' : '#52c41a';
  });

  const ctx = document.getElementById('chartByNode');
  if (_chartByNode) _chartByNode.destroy();
  _chartByNode = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ label: 'Alertas', data, backgroundColor: colors, borderRadius: 4 }] },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { precision: 0 } },
        y: { grid: { display: false } },
      },
    },
  });
}

function renderChartByDay() {
  const buckets = alertsByDay(7);
  const ctx = document.getElementById('chartByDay');
  if (_chartByDay) _chartByDay.destroy();
  _chartByDay = new Chart(ctx, {
    type: 'line',
    data: {
      labels: buckets.map(b => b.label),
      datasets: [{
        label: 'Alertas / día',
        data: buckets.map(b => b.count),
        borderColor: '#5e81ac',
        backgroundColor: 'rgba(94,129,172,0.18)',
        fill: true, tension: 0.35, pointRadius: 4, pointBackgroundColor: '#5e81ac',
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { precision: 0 } },
      },
    },
  });
}

/** Gráfico para el modal de detalle: temperatura y audio_rms de las alertas del nodo. */
function renderChartNodeDetail(nodeId) {
  const list = alertsForNode(nodeId).slice().reverse(); // cronológico
  const ctx = document.getElementById('chartNodeDetail');
  if (!ctx) return;
  if (_chartNodeDetail) _chartNodeDetail.destroy();
  _chartNodeDetail = new Chart(ctx, {
    type: 'line',
    data: {
      labels: list.map(a => formatTime(a.ts)),
      datasets: [
        {
          label: 'Temp (°C)', yAxisID: 'y',
          data: list.map(a => a.sensors.temp_c),
          borderColor: '#d08770', backgroundColor: 'rgba(208,135,112,0.15)',
          tension: 0.3, pointRadius: 3, fill: false,
        },
        {
          label: 'Audio RMS', yAxisID: 'y1',
          data: list.map(a => a.sensors.audio_rms),
          borderColor: '#a3be8c', backgroundColor: 'rgba(163,190,140,0.15)',
          tension: 0.3, pointRadius: 3, fill: false,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { boxWidth: 12 } } },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 6 } },
        y:  { position: 'left',  grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: '°C' } },
        y1: { position: 'right', grid: { display: false }, title: { display: true, text: 'RMS' } },
      },
    },
  });
}

function renderAllCharts() {
  renderChartByNode();
  renderChartByDay();
}

"""
views.py — Render del dashboard (HTML server-side, sin frameworks ni JS externo).

Cuatro pestanas del spec (WEB DASHBOARD):
  TAB 1  /            Inicio: una tarjeta AISLADA por nodo + ultima alerta de cada uno.
  TAB 2  /node/<name> Detalle: historial de detecciones (paginado) + tendencias
                       (graficas SVG simples) + status + anomalias.
  TAB 3  /status      Tabla de todos los nodos con color por status; auto-refresh 60s.
  TAB 4  /videos      Video Log: tabla ordenable por fecha y filtrable por nodo.

Las graficas son SVG inline (no se descargan librerias). Cada nodo se renderiza en
su propia tarjeta/seccion: nunca comparten espacio ni se mezclan datos.
"""

from __future__ import annotations

import html
from datetime import datetime

STATUS_COLOR = {
    "ONLINE": "#1f9d55",       # verde
    "OFFLINE": "#d9a300",      # amarillo
    "COMPROMISED": "#cc1f1a",  # rojo
    "UNKNOWN": "#777",         # gris
}

CSS = """
:root{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
*{box-sizing:border-box}
body{margin:0;background:#0f1420;color:#e7ecf3}
a{color:#6fb1ff;text-decoration:none}
a:hover{text-decoration:underline}
header{background:#141b2b;padding:14px 22px;border-bottom:1px solid #243049}
header h1{margin:0;font-size:18px;display:inline-block}
nav{display:inline-block;margin-left:24px}
nav a{margin-right:18px;font-weight:600;color:#aab7cc}
nav a.active{color:#fff;border-bottom:2px solid #6fb1ff;padding-bottom:6px}
main{padding:22px;max-width:1100px;margin:0 auto}
h2{font-size:16px;color:#aab7cc;margin:26px 0 12px;text-transform:uppercase;letter-spacing:.04em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.card{background:#1a2235;border:1px solid #283450;border-radius:10px;padding:16px}
.card h3{margin:0 0 10px;font-size:16px}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;color:#fff;font-size:12px;font-weight:700}
.kv{display:flex;justify-content:space-between;font-size:13px;margin:4px 0;color:#c4cede}
.kv span:first-child{color:#8a98ad}
table{width:100%;border-collapse:collapse;font-size:13px;background:#1a2235;border-radius:10px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid #283450}
th{background:#202a40;color:#aab7cc;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
th a{color:#aab7cc}
tr:last-child td{border-bottom:none}
.muted{color:#8a98ad;font-size:12px}
.pager{margin:14px 0;display:flex;gap:10px;align-items:center}
.pager a,.btn{background:#202a40;border:1px solid #2f3c5a;border-radius:6px;padding:6px 12px;color:#cdd9ec}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}
svg{background:#141b2b;border:1px solid #283450;border-radius:8px}
form.filter{margin:0 0 14px}
select,input{background:#202a40;color:#e7ecf3;border:1px solid #2f3c5a;border-radius:6px;padding:6px}
.empty{color:#8a98ad;padding:24px;text-align:center;background:#1a2235;border-radius:10px}
"""


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _rel_age(iso_ts: str | None) -> str:
    if not iso_ts:
        return "nunca"
    try:
        dt = datetime.fromisoformat(iso_ts)
    except ValueError:
        return _esc(iso_ts)
    secs = (datetime.now(dt.tzinfo) - dt).total_seconds()
    if secs < 0:
        secs = 0
    if secs < 60:
        return f"hace {int(secs)} s"
    if secs < 3600:
        return f"hace {int(secs // 60)} min"
    if secs < 86400:
        return f"hace {int(secs // 3600)} h"
    return f"hace {int(secs // 86400)} d"


def _fmt_uptime(s) -> str:
    if s is None:
        return "—"
    s = int(s)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    out = []
    if d: out.append(f"{d}d")
    if h: out.append(f"{h}h")
    out.append(f"{m}m")
    return " ".join(out)


def _battery(pct) -> str:
    # El hardware actual no tiene bateria: el firmware envia -1 = desconocido.
    if pct is None or int(pct) < 0:
        return "N/A"
    return f"{int(pct)}%"


def _badge(status: str) -> str:
    color = STATUS_COLOR.get(status, "#777")
    return f'<span class="badge" style="background:{color}">{_esc(status)}</span>'


def _layout(title: str, active: str, body: str, *, refresh: int | None = None) -> str:
    refresh_tag = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    def nav(href, label, key):
        cls = ' class="active"' if key == active else ""
        return f'<a href="{href}"{cls}>{label}</a>'
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{refresh_tag}
<title>{_esc(title)}</title><style>{CSS}</style></head>
<body>
<header>
  <h1>Monitor de Nodos IoT</h1>
  <nav>
    {nav('/', 'Inicio', 'home')}
    {nav('/status', 'Estado', 'status')}
    {nav('/videos', 'Video Log', 'videos')}
  </nav>
</header>
<main>{body}</main>
</body></html>"""


# ----------------------------------------------------------------- TAB 1
def page_home(nodes: list[dict], last_alerts: dict[str, dict]) -> str:
    if not nodes:
        body = '<div class="empty">Aun no se ha registrado ningun nodo. ' \
               'En cuanto un ESP32 publique algo, aparecera aqui.</div>'
        return _layout("Inicio · Monitor IoT", "home", body)

    cards = []
    for n in nodes:
        name = n["node_name"]
        cards.append(f"""
        <div class="card">
          <h3><a href="/node/{_esc(name)}">{_esc(name)}</a></h3>
          <div>{_badge(n['status'])}</div>
          <div class="kv" style="margin-top:10px"><span>Bateria</span><span>{_battery(n['battery_pct'])}</span></div>
          <div class="kv"><span>Temp chip</span><span>{_esc(n['chip_temp_c'])} °C</span></div>
          <div class="kv"><span>Ultimo heartbeat</span><span>{_rel_age(n['last_heartbeat'])}</span></div>
          <div class="kv"><span>Umbral</span><span>{_esc(n['threshold'])}</span></div>
        </div>""")

    alert_cards = []
    for n in nodes:
        name = n["node_name"]
        a = last_alerts.get(name)
        if a:
            inner = f"""
          <div class="kv"><span>Score</span><span>{_esc(a['score'])}</span></div>
          <div class="kv"><span>Umbral usado</span><span>{_esc(a['threshold_used'])}</span></div>
          <div class="kv"><span>Cuando</span><span>{_rel_age(a['timestamp'])}</span></div>
          <div class="muted">{_esc(a['timestamp'])}</div>"""
        else:
            inner = '<div class="muted">Sin detecciones todavia</div>'
        alert_cards.append(f"""
        <div class="card">
          <h3>{_esc(name)} · ultima alerta</h3>{inner}
          <div style="margin-top:10px"><a href="/node/{_esc(name)}">Ver historial →</a></div>
        </div>""")

    body = (f'<h2>Nodos registrados ({len(nodes)})</h2>'
            f'<div class="grid">{"".join(cards)}</div>'
            f'<h2>Ultima alerta por nodo</h2>'
            f'<div class="grid">{"".join(alert_cards)}</div>')
    return _layout("Inicio · Monitor IoT", "home", body)


# ----------------------------------------------------------------- TAB 2
def _svg_line(points: list[float], width=520, height=120, color="#6fb1ff", label="") -> str:
    vals = [p for p in points if p is not None]
    if len(vals) < 2:
        return f'<div class="muted">Sin datos suficientes para graficar {_esc(label)}.</div>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(points)
    pad = 8
    def x(i): return pad + i * (width - 2 * pad) / (n - 1)
    def y(v): return height - pad - (v - lo) / rng * (height - 2 * pad)
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(points) if v is not None)
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'
            f'<text x="{pad}" y="14" fill="#8a98ad" font-size="11">{_esc(label)} '
            f'(min {lo:.2f} / max {hi:.2f})</text></svg>')


def page_node(node: dict, dets: list[dict], total: int, page: int, size: int,
              heartbeats: list[dict], anomalies: list[dict],
              status_hist: list[dict]) -> str:
    name = node["node_name"]
    pages = max(1, (total + size - 1) // size)

    # tabla de detecciones
    if dets:
        rows = "".join(
            f"<tr><td>{_esc(d['timestamp'])}</td><td>{_esc(d['score'])}</td>"
            f"<td>{_esc(d['threshold_used'])}</td><td>{_esc(d['seq'])}</td></tr>"
            for d in dets)
        det_table = (f'<table><tr><th>Timestamp</th><th>Score</th>'
                     f'<th>Umbral usado</th><th>Seq</th></tr>{rows}</table>')
        prev = f'<a href="/node/{_esc(name)}?page={page-1}">← Anterior</a>' if page > 1 else ""
        nxt = f'<a href="/node/{_esc(name)}?page={page+1}">Siguiente →</a>' if page < pages else ""
        pager = f'<div class="pager">{prev}<span class="muted">Pagina {page}/{pages} · {total} detecciones</span>{nxt}</div>'
    else:
        det_table = '<div class="empty">Sin detecciones registradas.</div>'
        pager = ""

    # graficas de tendencia
    temps = [h["chip_temp_c"] for h in heartbeats]
    bats = [h["battery_pct"] if (h["battery_pct"] is not None and h["battery_pct"] >= 0) else None
            for h in heartbeats]
    temp_chart = _svg_line(temps, color="#ff8c42", label="Temp chip °C")
    bat_chart = (_svg_line(bats, color="#1f9d55", label="Bateria %")
                 if any(b is not None for b in bats)
                 else '<div class="muted">Bateria: N/A (el hardware actual no la mide).</div>')

    # anomalias
    if anomalies:
        arows = "".join(f"<tr><td>{_esc(a['timestamp'])}</td><td>{_esc(a['type'])}</td>"
                        f"<td>{_esc(a['detail'])}</td></tr>" for a in anomalies)
        anom = f'<table><tr><th>Timestamp</th><th>Tipo</th><th>Detalle</th></tr>{arows}</table>'
    else:
        anom = '<div class="empty">Sin anomalias.</div>'

    # historial de status
    if status_hist:
        srows = "".join(f"<tr><td>{_esc(s['timestamp'])}</td><td>{_esc(s['old_status'])}</td>"
                        f"<td>{_badge(s['new_status'])}</td></tr>" for s in status_hist)
        shist = f'<table><tr><th>Timestamp</th><th>Anterior</th><th>Nuevo</th></tr>{srows}</table>'
    else:
        shist = '<div class="muted">Sin cambios de estado registrados.</div>'

    body = f"""
    <p><a href="/">← Inicio</a></p>
    <div class="card">
      <h3>{_esc(name)} {_badge(node['status'])}</h3>
      <div class="kv"><span>Visto por primera vez</span><span>{_esc(node['first_seen'])}</span></div>
      <div class="kv"><span>Visto por ultima vez</span><span>{_esc(node['last_seen'])} ({_rel_age(node['last_seen'])})</span></div>
      <div class="kv"><span>Ultimo heartbeat</span><span>{_esc(node['last_heartbeat'])} ({_rel_age(node['last_heartbeat'])})</span></div>
      <div class="kv"><span>Bateria</span><span>{_battery(node['battery_pct'])}</span></div>
      <div class="kv"><span>Temp chip</span><span>{_esc(node['chip_temp_c'])} °C</span></div>
      <div class="kv"><span>Umbral</span><span>{_esc(node['threshold'])}</span></div>
      <div class="kv"><span>Uptime</span><span>{_fmt_uptime(node['uptime_s'])}</span></div>
    </div>

    <h2>Historial de detecciones</h2>
    {det_table}{pager}

    <h2>Tendencias (heartbeat)</h2>
    <div style="display:flex;gap:16px;flex-wrap:wrap">{temp_chart}{bat_chart}</div>

    <h2>Anomalias</h2>
    {anom}

    <h2>Historial de estado</h2>
    {shist}
    """
    return _layout(f"{name} · Monitor IoT", "node", body)


# ----------------------------------------------------------------- TAB 3
def page_status(nodes: list[dict]) -> str:
    if not nodes:
        body = '<div class="empty">No hay nodos registrados.</div>'
        return _layout("Estado · Monitor IoT", "status", body, refresh=60)
    rows = []
    for n in nodes:
        color = STATUS_COLOR.get(n["status"], "#777")
        rows.append(
            f"<tr><td><a href='/node/{_esc(n['node_name'])}'>{_esc(n['node_name'])}</a></td>"
            f"<td><span class='dot' style='background:{color}'></span>{_badge(n['status'])}</td>"
            f"<td>{_esc(n['last_heartbeat'])}<div class='muted'>{_rel_age(n['last_heartbeat'])}</div></td>"
            f"<td>{_battery(n['battery_pct'])}</td>"
            f"<td>{_esc(n['chip_temp_c'])} °C</td>"
            f"<td>{_fmt_uptime(n['uptime_s'])}</td></tr>")
    body = (f'<h2>Estado de los nodos</h2>'
            f'<p class="muted">Se actualiza solo cada 60 s.</p>'
            f'<table><tr><th>Nodo</th><th>Status</th><th>Ultimo heartbeat</th>'
            f'<th>Bateria</th><th>Temp chip</th><th>Uptime</th></tr>{"".join(rows)}</table>')
    return _layout("Estado · Monitor IoT", "status", body, refresh=60)


# ----------------------------------------------------------------- TAB 4
def page_videos(videos: list[dict], node_filter: str, node_list: list[str],
                order: str, desc: bool) -> str:
    def sort_link(col, label):
        new_desc = not desc if order == col else True
        arrow = (" ▼" if desc else " ▲") if order == col else ""
        q = f"?order={col}&desc={'1' if new_desc else '0'}"
        if node_filter:
            q += f"&node={_esc(node_filter)}"
        return f'<a href="{q}">{label}{arrow}</a>'

    opts = ['<option value="">Todos los nodos</option>']
    for nm in node_list:
        sel = " selected" if nm == node_filter else ""
        opts.append(f'<option value="{_esc(nm)}"{sel}>{_esc(nm)}</option>')
    filt = (f'<form class="filter" method="get">'
            f'<input type="hidden" name="order" value="{_esc(order)}">'
            f'<input type="hidden" name="desc" value="{"1" if desc else "0"}">'
            f'Filtrar por nodo: <select name="node" onchange="this.form.submit()">'
            f'{"".join(opts)}</select> <button class="btn">Aplicar</button></form>')

    if videos:
        rows = "".join(
            f"<tr><td><a href='/node/{_esc(v['node_name'])}'>{_esc(v['node_name'])}</a></td>"
            f"<td>{_esc(v['received_at'])}</td><td>{_esc(v['file_size_kb'])} KB</td>"
            f"<td><a href='/{_esc(v['file_path'])}' download>Descargar</a> · "
            f"<a href='/{_esc(v['file_path'])}' target='_blank'>Ver</a></td></tr>"
            for v in videos)
        table = (f'<table><tr><th>{sort_link("node_name","Nodo")}</th>'
                 f'<th>{sort_link("received_at","Recibido")}</th>'
                 f'<th>{sort_link("file_size_kb","Tamano")}</th>'
                 f'<th>Descarga</th></tr>{rows}</table>')
    else:
        table = '<div class="empty">No hay videos registrados todavia.</div>'

    body = (f'<h2>Video Log <span class="muted">(temporal, se quitara mas adelante)</span></h2>'
            f'{filt}{table}')
    return _layout("Video Log · Monitor IoT", "videos", body)

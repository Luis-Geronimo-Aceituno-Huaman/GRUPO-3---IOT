"""
web.py — Servidor HTTP del dashboard de monitoreo (stdlib http.server).

Rutas:
  GET  /                     TAB1 Inicio (tarjetas de nodo + ultima alerta)
  GET  /node/<name>?page=N   TAB2 Detalle del nodo
  GET  /status               TAB3 Estado (auto-refresh 60s)
  GET  /videos?node=&order=&desc=   TAB4 Video Log (ordenable/filtrable)
  GET  /clips/<node>/<file>  Sirve el .webm (con soporte de Range 206 para <video>)
  POST /upload?device=&fmt=jpegseq&seconds=  Receptor de video (spec: HTTP POST)

  API JSON:
  GET  /api/nodes
  GET  /api/node/<name>/detections?page=&size=
  GET  /api/node/<name>/heartbeats
  GET  /api/videos?node=

Un solo ThreadingHTTPServer; cada peticion en su hilo. La BD es thread-safe.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import config as cfg
import views
from db import now_iso
from video_indexer import jpegseq_to_webm


def make_handler(db):
    """Fabrica el handler con la BD inyectada (no hay estado global)."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "NodeMonitor/1.0"

        def log_message(self, *a):
            pass  # silencioso; los hilos de ingest/job ya loguean lo importante

        # ---- helpers de respuesta ----
        def _send(self, code, body: bytes, ctype="text/html; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _html(self, html_str: str, code=200):
            self._send(code, html_str.encode("utf-8"))

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       ctype="application/json; charset=utf-8")

        def _not_found(self):
            self._html(views._layout("404", "", '<div class="empty">No encontrado.</div>'), 404)

        # ---- GET ----
        def do_GET(self):
            self._route(write_body=True)

        def do_HEAD(self):
            self._route(write_body=True)  # _send respeta HEAD y no escribe el cuerpo

        def _route(self, write_body):
            u = urlparse(self.path)
            path = unquote(u.path)
            q = parse_qs(u.query)

            try:
                if path == "/":
                    return self._page_home()
                if path == "/status":
                    return self._page_status()
                if path == "/videos":
                    return self._page_videos(q)
                m = re.fullmatch(r"/node/([^/]+)", path)
                if m:
                    return self._page_node(unquote(m.group(1)), q)

                # API
                if path == "/api/nodes":
                    return self._json(db.all_nodes())
                m = re.fullmatch(r"/api/node/([^/]+)/detections", path)
                if m:
                    page = int(q.get("page", ["1"])[0]); size = int(q.get("size", ["50"])[0])
                    rows, total = db.detections(unquote(m.group(1)), page, size)
                    return self._json({"total": total, "page": page, "size": size, "rows": rows})
                m = re.fullmatch(r"/api/node/([^/]+)/heartbeats", path)
                if m:
                    return self._json(db.heartbeats(unquote(m.group(1))))
                if path == "/api/videos":
                    node = q.get("node", [None])[0]
                    return self._json(db.videos(node))

                # estaticos: /clips/<node>/<file>
                if path.startswith("/clips/"):
                    return self._serve_clip(path)

                return self._not_found()
            except Exception as e:
                self._html(views._layout("Error", "",
                           f'<div class="empty">Error: {views._esc(e)}</div>'), 500)

        # ---- paginas ----
        def _page_home(self):
            nodes = db.all_nodes()
            last = {n["node_name"]: db.last_detection(n["node_name"]) for n in nodes}
            last = {k: v for k, v in last.items() if v}
            self._html(views.page_home(nodes, last))

        def _page_status(self):
            self._html(views.page_status(db.all_nodes()))

        def _page_node(self, name, q):
            node = db.get_node(name)
            if not node:
                return self._not_found()
            page = max(1, int(q.get("page", ["1"])[0]))
            size = 50
            dets, total = db.detections(name, page, size)
            hbs = db.heartbeats(name)
            anom = db.anomalies(name)
            shist = db.status_history(name)
            self._html(views.page_node(node, dets, total, page, size, hbs, anom, shist))

        def _page_videos(self, q):
            node = q.get("node", [""])[0] or None
            order = q.get("order", ["received_at"])[0]
            desc = q.get("desc", ["1"])[0] != "0"
            vids = db.videos(node, order=order, desc=desc)
            node_list = [n["node_name"] for n in db.all_nodes()]
            self._html(views.page_videos(vids, node or "", node_list, order, desc))

        # ---- servir clip con Range (HTML5 <video> lo necesita) ----
        def _serve_clip(self, path):
            rel = path.lstrip("/")                       # "clips/<node>/<file>"
            full = (cfg.DATOS / rel).resolve()
            clips_base = cfg.CLIPS_DIR.resolve()
            # anti path-traversal: el archivo DEBE quedar dentro de la carpeta de clips
            if not full.is_relative_to(clips_base) or not full.is_file():
                return self._not_found()
            size = full.stat().st_size
            ctype = "video/webm" if full.suffix == ".webm" else "application/octet-stream"
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                try:
                    s, _, e = rng[6:].partition("-")
                    start = int(s) if s else 0
                    end = int(e) if e else size - 1
                    end = min(end, size - 1)
                    start = max(0, min(start, end))
                except ValueError:
                    start, end = 0, size - 1
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.end_headers()
                if self.command != "HEAD":
                    with open(full, "rb") as f:
                        f.seek(start)
                        self.wfile.write(f.read(length))
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(full.read_bytes())

        # ---- POST /upload (receptor de video del spec) ----
        def do_POST(self):
            u = urlparse(self.path)
            if u.path != "/upload":
                return self._not_found()
            q = parse_qs(u.query)
            device = q.get("device", ["desconocido"])[0]
            fmt = q.get("fmt", ["jpegseq"])[0]
            seconds = float(q.get("seconds", ["6"])[0])
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length) if length else b""
            self._send(200, b"ok", ctype="text/plain")

            if not data:
                return
            db.register_node(device)
            try:
                if fmt == "jpegseq":
                    out = jpegseq_to_webm(device, data, seconds)
                else:
                    name = Path(q.get("name", ["clip.webm"])[0]).name
                    out_dir = Path(cfg.UPLOAD_DIR) / device
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out = out_dir / name
                    out.write_bytes(data)
                if out:
                    rel = str(Path(out).resolve().relative_to(cfg.DATOS.resolve()))
                    db.insert_video(device, now_iso(), rel, max(1, Path(out).stat().st_size // 1024))
                    print(f"[UPLOAD] video de {device} guardado: {rel}")
            except Exception as e:
                print(f"[UPLOAD] error guardando video de {device}: {e}")

    return Handler


def serve(db):
    handler = make_handler(db)
    srv = ThreadingHTTPServer((cfg.HTTP_HOST, cfg.HTTP_PORT), handler)
    print(f"[WEB ] dashboard en http://{cfg.HTTP_HOST}:{cfg.HTTP_PORT}  "
          f"(Inicio / · Estado /status · Video Log /videos)")
    srv.serve_forever()

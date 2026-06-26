"""
serve.py — Servidor UNIFICADO de la Capa de Aplicacion (FastAPI / ASGI).

Un solo proceso, un solo puerto (:8000) y una sola SPA con pestanas
(Alertas · Nodos · Estado · Video Log). Este server:

  1. Sirve la SPA estatica (../dashboard) con fallback al index (SPA).
  2. Expone /api/alerts            -> alertas confirmadas (alerts.db).
  3. Expone /api/nodes, /api/node/<name>/{detections,heartbeats}, /api/videos
                                    -> datos de monitoreo de nodos (monitor.db).
  4. Sirve /clips/<node>/<file>     -> los videos (Range/206 via FileResponse).
  5. Acepta POST /upload           -> receptor de video (jpegseq) del spec.
  6. DELETE /api/video/<id>        -> borra un clip del log + del disco.
  7. Arranca en su 'lifespan' los 3 servicios de fondo del monitor (ingest MQTT,
     job de liveness, indexador de videos): el MISMO proceso llena monitor.db.

El backend de monitoreo vive como libreria en capa3/monitor; aqui solo se importa
y se orquesta. No toca el gateway ni el detector. Bonus de FastAPI: /docs (Swagger).

Uso:
  python serve.py            # http://localhost:8000   (+ /docs)
  python serve.py 8080       # puerto custom
  uvicorn serve:app --host 0.0.0.0 --port 8000   # servidor ASGI directo
"""

from __future__ import annotations

import sys
import sqlite3
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse

BASE = Path(__file__).resolve().parent                       # capa4-aplicacion/
DASHBOARD_DIR = BASE / "dashboard"

# Igual que serve.py: el backend de monitoreo (capa3/monitor) se importa como
# libreria; ponemos SOLO esa carpeta en el path para que sus 'import config' /
# 'from db import ...' internos resuelvan al monitor (no a las alertas de capa3).
MONITOR_DIR = BASE.parent / "capa3-procesamiento-servidor" / "monitor"
sys.path.insert(0, str(MONITOR_DIR))

import config as cfg                       # = capa3/monitor/config.py
from db import MonitorDB, now_iso          # = capa3/monitor/db.py
from mqtt_ingest import MqttIngest
from heartbeat_monitor import HeartbeatMonitor
from video_indexer import VideoIndexer, jpegseq_to_webm

CLIPS_DIR = Path(cfg.CLIPS_DIR).resolve()                    # datos/clips
ALERTS_DB = Path(cfg.DATOS) / "alerts.db"                    # alertas confirmadas


# ───────────────────────────── alertas (alerts.db) ──────────────────────────
def clip_url(video_url):
    """Ruta de disco del clip -> URL servible /clips/<device>/<archivo>."""
    if not video_url:
        return None
    s = str(video_url).replace("\\", "/")
    if s.startswith(("http://", "https://", "/clips/")):
        return s
    try:
        rel = Path(video_url).resolve().relative_to(CLIPS_DIR)
        return "/clips/" + rel.as_posix()
    except Exception:
        p = Path(s)
        return "/clips/" + p.parent.name + "/" + p.name if p.name else None


def _alert_row_to_dict(r) -> dict:
    """Mismo shape que consume la SPA (igual que serve.py / capa3 AlertStore)."""
    return {
        "id": r["id"], "nodeId": r["node_id"], "nodeName": r["node_name"],
        "district": r["district"], "lat": r["lat"], "lon": r["lon"],
        "ts": r["ts"], "confidence": r["confidence"], "source": r["source"],
        "detClass": r["det_class"], "detCount": r["det_count"],
        "videoUrl": clip_url(r["video_url"]), "status": r["status"],
        "sensors": {
            "temp_c": r["temp_c"], "turb_v": r["turb_v"], "audio_rms": r["audio_rms"],
            "audio_peak": r["audio_peak"], "sats": r["sats"],
        },
    }


def read_alerts() -> list[dict]:
    if not ALERTS_DB.exists():
        return []
    con = sqlite3.connect(str(ALERTS_DB))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM alerts ORDER BY ts DESC").fetchall()
        return [_alert_row_to_dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []                       # la tabla aun no existe
    finally:
        con.close()


# ───────────── ciclo de vida: arrancar/parar los servicios de fondo ─────────
# Reemplaza el bloque de main() de serve.py. El MISMO proceso llena monitor.db.
services: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 64)
    print(" DASHBOARD UNIFICADO — FastAPI/ASGI (alertas + monitoreo de nodos)")
    print(f"   broker  : {cfg.MQTT_HOST}:{cfg.MQTT_PORT}")
    print(f"   alertas : {ALERTS_DB}")
    print(f"   monitor : {cfg.DB_PATH}")
    print(f"   clips   : {CLIPS_DIR}")
    print(f"   docs    : /docs")
    print("=" * 64)
    db = MonitorDB(cfg.DB_PATH)
    ingest = MqttIngest(db); ingest.start()
    hb = HeartbeatMonitor(db); hb.start()
    vidx = VideoIndexer(db); vidx.start()
    services.update(db=db, ingest=ingest, hb=hb, vidx=vidx)
    try:
        yield
    finally:
        print("\n[RUN] apagando...")
        ingest.stop(); hb.stop(); vidx.stop(); db.close()


app = FastAPI(title="Dashboard IoT unificado", version="1.0-poc", lifespan=lifespan)


def DB() -> MonitorDB:
    return services["db"]


# ───────────────────────────── APIs de alertas ──────────────────────────────
@app.get("/api/alerts")
def api_alerts():
    return read_alerts()


# ───────────────────────────── APIs de monitoreo ────────────────────────────
@app.get("/api/nodes")
def api_nodes():
    return DB().all_nodes()


@app.get("/api/node/{name}/detections")
def api_detections(name: str, page: int = 1, size: int = 50):
    rows, total = DB().detections(name, page, size)
    return {"total": total, "page": page, "size": size, "rows": rows}


@app.get("/api/node/{name}/heartbeats")
def api_heartbeats(name: str):
    return DB().heartbeats(name)


@app.get("/api/node/{name}")
def api_node(name: str):
    node = DB().get_node(name)
    if not node:
        return JSONResponse({"error": "no existe"}, status_code=404)
    node["anomalies"] = DB().anomalies(node["node_name"])
    node["status_history"] = DB().status_history(node["node_name"])
    return node


# Comandos que el firmware entiende (ver onMqttMessage en nodo_iot_autocalib.ino):
#   "recalib"   -> detectorForceRecalibration() (re-mide el ruido de fondo ~10 s)
#   "heartbeat" -> smRequestHeartbeat() (publica su estado al instante)
#   "restart"   -> ESP.restart()
CMD_ALLOWED = {"recalib", "heartbeat", "restart"}


@app.post("/api/node/{name}/cmd")
async def api_node_cmd(name: str, request: Request):
    """Publica una orden al nodo por MQTT en 'devices/<name>/cmd' (QoS1, sin retener:
    un comando retenido se re-aplicaria en cada reconexion). Reusa el cliente MQTT
    del ingest (ya autenticado y conectado). El ESP32 esta suscrito a ese topic."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    command = str(body.get("command", "")).strip().lower()
    if command not in CMD_ALLOWED:
        return JSONResponse(
            {"error": f"comando no permitido; usa uno de {sorted(CMD_ALLOWED)}"},
            status_code=400)
    if not DB().get_node(name):
        return JSONResponse({"error": "no existe"}, status_code=404)
    client = services["ingest"].client
    topic = f"devices/{name}/cmd"
    info = client.publish(topic, command, qos=1, retain=False)
    print(f"[CMD] -> {topic}: '{command}' (rc={info.rc})")
    if info.rc != 0:                       # 0 == MQTT_ERR_SUCCESS
        return JSONResponse(
            {"error": f"el broker rechazo el publish (rc={info.rc}); ¿esta arriba?"},
            status_code=502)
    return {"ok": True, "node": name, "command": command, "topic": topic}


@app.get("/api/videos")
def api_videos(node: str | None = None, order: str = "received_at",
               desc: str = "1"):
    return DB().videos(node, order=order, desc=(desc != "0"))


# ───────────────────────── clips (.webm con Range 206) ──────────────────────
# FileResponse trae el soporte de Range/206 y Accept-Ranges integrado:
# reemplaza ~80 lineas de manejo manual de bytes en serve.py.
@app.get("/clips/{rel_path:path}")
def serve_clip(rel_path: str):
    full = (cfg.DATOS / "clips" / rel_path).resolve()
    if not full.is_relative_to(CLIPS_DIR) or not full.is_file():
        return PlainTextResponse("clip no encontrado", status_code=404)
    ctype = "video/webm" if full.suffix == ".webm" else "application/octet-stream"
    return FileResponse(full, media_type=ctype)     # Range/206 automatico


# ───────────────────────── POST /upload (receptor jpegseq) ──────────────────
@app.post("/upload")
async def upload(request: Request,
                 device: str = "desconocido", fmt: str = "jpegseq",
                 seconds: float = 6, name: str = "clip.webm"):
    data = await request.body()
    db = DB()
    if not data:
        return PlainTextResponse("ok")
    db.register_node(device)
    try:
        if fmt == "jpegseq":
            out = jpegseq_to_webm(device, data, seconds)
        else:
            out_dir = Path(cfg.UPLOAD_DIR) / device
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / Path(name).name
            out.write_bytes(data)
        if out:
            rel = str(Path(out).resolve().relative_to(cfg.DATOS.resolve()))
            db.insert_video(device, now_iso(), rel,
                            max(1, Path(out).stat().st_size // 1024))
            print(f"[UPLOAD] video de {device} guardado: {rel}")
    except Exception as e:
        print(f"[UPLOAD] error guardando video de {device}: {e}")
    return PlainTextResponse("ok")


# ───────────────────────── DELETE /api/video/<id> ───────────────────────────
@app.delete("/api/video/{vid}")
def delete_video(vid: int):
    rel = DB().delete_video(vid)
    if rel is None:
        return JSONResponse({"error": "no existe"}, status_code=404)
    removed = False
    try:
        full = (cfg.DATOS / rel).resolve()
        if full.is_relative_to(cfg.DATOS.resolve()) and full.is_file():
            full.unlink()
            removed = True
    except Exception as e:
        print(f"[DELETE] no se pudo borrar el archivo {rel}: {e}")
    print(f"[DELETE] video id={vid} eliminado ({rel}), archivo={'si' if removed else 'no'}")
    return {"ok": True, "id": vid, "file_removed": removed}


# ───────────────────────── estatico (SPA) — catch-all final ─────────────────
# Se registra al final: solo atrapa lo que no casaron las rutas de arriba.
# Cualquier ruta desconocida cae al index.html (navegacion por pestanas).
@app.get("/{full_path:path}")
def serve_static(full_path: str):
    rel = full_path or "index.html"
    full = (DASHBOARD_DIR / rel).resolve()
    if not full.is_relative_to(DASHBOARD_DIR.resolve()) or not full.is_file():
        full = DASHBOARD_DIR / "index.html"
    return FileResponse(full)


if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(app, host="0.0.0.0", port=port)

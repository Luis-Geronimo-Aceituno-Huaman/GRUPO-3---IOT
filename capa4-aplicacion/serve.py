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
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse

BASE = Path(__file__).resolve().parent                       # capa4-aplicacion/
DASHBOARD_DIR = BASE / "dashboard"

# Igual que serve.py: el backend de monitoreo (capa3/monitor) se importa como
# libreria; ponemos SOLO esa carpeta en el path para que sus 'import config' /
# 'from db import ...' internos resuelvan al monitor (no a las alertas de capa3).
MONITOR_DIR = BASE.parent / "capa3-procesamiento-servidor" / "monitor"
sys.path.insert(0, str(MONITOR_DIR))

import config as cfg                       # = capa3/monitor/config.py
from db import MonitorDB, now_iso          # = capa3/monitor/db.py (PostgreSQL)
from mqtt_ingest import MqttIngest
from heartbeat_monitor import HeartbeatMonitor
from video_indexer import VideoIndexer, jpegseq_to_webm

# capa3/ quedó en sys.path (lo añade monitor/db.py para llegar a database.py);
# el AlertStore de capa3/db.py NO se puede importar por nombre porque 'db' ya
# resuelve al del monitor — se carga explícito por ruta de archivo.
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "alerts_db", BASE.parent / "capa3-procesamiento-servidor" / "db.py")
_alerts_db = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_alerts_db)
AlertStore = _alerts_db.AlertStore

import database as pgdb                    # capa3/database.py (pool global)
import risk                                # capa3/risk.py (motor de riesgo)
import auth                                # capa4/auth.py (sesiones + roles)
from auth import current_user, require_admin

CLIPS_DIR = Path(cfg.CLIPS_DIR).resolve()                    # datos/clips


# ───────────────────────────── alertas (PostgreSQL) ─────────────────────────
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


def _with_clip_url(alert: dict) -> dict:
    """El AlertStore devuelve la ruta de disco del clip; aquí se vuelve URL servible."""
    alert["videoUrl"] = clip_url(alert.get("videoUrl"))
    return alert


# ───────────── ciclo de vida: arrancar/parar los servicios de fondo ─────────
# Reemplaza el bloque de main() de serve.py. El MISMO proceso llena la BD.
services: dict = {}


class RiskJob:
    """Job periódico: recalcula y persiste nodes.risk_level/risk_score cada
    `interval_s`. Corre en hilo daemon (mismo patrón que HeartbeatMonitor)."""

    def __init__(self, interval_s: int = 300):
        import threading
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        print(f"[RISK] job de riesgo cada {self.interval_s}s")

    def _run(self):
        while not self._stop.wait(2):          # primer cálculo casi inmediato
            try:
                risk.refresh_all()
            except Exception as e:
                print(f"[RISK] fallo recalculando riesgo: {e}")
            if self._stop.wait(self.interval_s):
                break

    def stop(self):
        self._stop.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 64)
    print(" DASHBOARD UNIFICADO — FastAPI/ASGI (alertas + monitoreo de nodos)")
    print(f"   broker  : {cfg.MQTT_HOST}:{cfg.MQTT_PORT}")
    print(f"   BD      : postgresql://{pgdb.PG_HOST}:{pgdb.PG_PORT}/{pgdb.PG_DB}")
    print(f"   clips   : {CLIPS_DIR}")
    print(f"   docs    : /docs")
    print("=" * 64)
    # Arranque DEGRADADO si PostgreSQL no responde: el server web sube igual
    # (las APIs devuelven 503 con mensaje claro) y NO crashea.
    try:
        db = MonitorDB()
        store = AlertStore()
        ingest = MqttIngest(db); ingest.start()
        hb = HeartbeatMonitor(db); hb.start()
        vidx = VideoIndexer(db); vidx.start()
        rj = RiskJob(); rj.start()
        services.update(db=db, store=store, ingest=ingest, hb=hb, vidx=vidx, rj=rj)
        print("[RUN] PostgreSQL OK: monitoreo + alertas + riesgo en marcha.")
    except Exception as e:
        services.clear()
        print(f"[RUN] *** MODO DEGRADADO: PostgreSQL no responde ({e}).")
        print("[RUN] *** Levanta la BD (docker compose up -d postgres) y reinicia.")
    try:
        yield
    finally:
        print("\n[RUN] apagando...")
        if services:
            services["ingest"].stop(); services["hb"].stop()
            services["vidx"].stop(); services["rj"].stop(); services["db"].close()


app = FastAPI(title="Dashboard IoT unificado", version="1.0-poc", lifespan=lifespan)


from fastapi import HTTPException


def DB() -> MonitorDB:
    if "db" not in services:
        raise HTTPException(503, "base de datos no disponible (modo degradado); "
                                 "levanta postgres y reinicia el servidor")
    return services["db"]


def STORE() -> "AlertStore":
    if "store" not in services:
        raise HTTPException(503, "base de datos no disponible (modo degradado); "
                                 "levanta postgres y reinicia el servidor")
    return services["store"]


# ───────────────────────────── autenticación ────────────────────────────────
@app.post("/api/auth/login")
async def api_login(request: Request):
    """Body: {username, password}. Crea sesión y setea la cookie firmada."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        return JSONResponse({"error": "usuario y contraseña requeridos"}, status_code=400)
    try:
        user = auth.verify_login(username, password)
    except Exception:
        return JSONResponse({"error": "base de datos no disponible"}, status_code=503)
    if not user:
        auth.log_event("login.failed", detail={"username": username},
                       ip=request.client.host if request.client else None)
        return JSONResponse({"error": "credenciales inválidas"}, status_code=401)
    cookie = auth.create_session(
        user["id"], request.client.host if request.client else None,
        request.headers.get("user-agent"))
    resp = JSONResponse({"ok": True, "user": user})
    auth.set_session_cookie(resp, cookie)
    auth.log_event("login", user=user, ip=request.client.host if request.client else None)
    return resp


@app.post("/api/auth/logout")
def api_logout(request: Request, user: dict = Depends(current_user)):
    auth.destroy_session(request.cookies.get(auth.COOKIE_NAME))
    resp = JSONResponse({"ok": True})
    auth.clear_session_cookie(resp)
    auth.log_event("logout", user=user)
    return resp


@app.get("/api/auth/me")
def api_me(user: dict = Depends(current_user)):
    return user


# ─────────────────────────── usuarios (solo admin) ──────────────────────────
@app.get("/api/users")
def api_users(admin: dict = Depends(require_admin)):
    with pgdb.get_pool().connection() as conn:
        return conn.execute(
            """SELECT id, username, role, full_name, active, created_at, last_login
               FROM users ORDER BY id"""
        ).fetchall()


@app.post("/api/users")
async def api_users_create(request: Request, admin: dict = Depends(require_admin)):
    body = await request.json()
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    role = body.get("role", "operador")
    if not username or len(password) < 6:
        return JSONResponse({"error": "username y password (mín. 6) requeridos"}, 400)
    if role not in auth.ROLES:
        return JSONResponse({"error": f"rol inválido; usa uno de {auth.ROLES}"}, 400)
    with pgdb.get_pool().connection() as conn:
        dup = conn.execute("SELECT 1 FROM users WHERE username=%s", (username,)).fetchone()
        if dup:
            return JSONResponse({"error": "ese usuario ya existe"}, 409)
        row = conn.execute(
            """INSERT INTO users (username, password_hash, role, full_name)
               VALUES (%s,%s,%s,%s) RETURNING id, username, role, full_name, active""",
            (username, auth.hash_password(password), role, body.get("full_name")),
        ).fetchone()
    auth.log_event("user.create", user=admin, entity="user", entity_id=row["id"],
                   detail={"username": username, "role": role})
    return row


@app.patch("/api/users/{uid}")
async def api_users_edit(uid: int, request: Request,
                         admin: dict = Depends(require_admin)):
    body = await request.json()
    sets, vals = [], []
    if "role" in body:
        if body["role"] not in auth.ROLES:
            return JSONResponse({"error": "rol inválido"}, 400)
        sets.append("role=%s"); vals.append(body["role"])
    if "active" in body:
        sets.append("active=%s"); vals.append(bool(body["active"]))
    if "full_name" in body:
        sets.append("full_name=%s"); vals.append(body["full_name"])
    if body.get("password"):
        if len(str(body["password"])) < 6:
            return JSONResponse({"error": "password mínimo 6 caracteres"}, 400)
        sets.append("password_hash=%s"); vals.append(auth.hash_password(str(body["password"])))
    if not sets:
        return JSONResponse({"error": "nada que actualizar"}, 400)
    vals.append(uid)
    with pgdb.get_pool().connection() as conn:
        row = conn.execute(
            f"UPDATE users SET {', '.join(sets)} WHERE id=%s "
            "RETURNING id, username, role, full_name, active", vals).fetchone()
    if not row:
        return JSONResponse({"error": "no existe"}, 404)
    auth.log_event("user.update", user=admin, entity="user", entity_id=uid,
                   detail={k: body[k] for k in body if k != "password"})
    return row


@app.delete("/api/users/{uid}")
def api_users_delete(uid: int, admin: dict = Depends(require_admin)):
    """Soft-delete: desactiva (la auditoría de events/alert_history lo referencia)."""
    if uid == admin["id"]:
        return JSONResponse({"error": "no puedes desactivarte a ti mismo"}, 400)
    with pgdb.get_pool().connection() as conn:
        row = conn.execute(
            "UPDATE users SET active=FALSE WHERE id=%s RETURNING id", (uid,)).fetchone()
        conn.execute("DELETE FROM sessions WHERE user_id=%s", (uid,))
    if not row:
        return JSONResponse({"error": "no existe"}, 404)
    auth.log_event("user.deactivate", user=admin, entity="user", entity_id=uid)
    return {"ok": True, "id": uid, "active": False}


# ───────────────────────────── APIs de alertas ──────────────────────────────
@app.get("/api/alerts")
def api_alerts(status: str | None = None, node: str | None = None,
               include_synthetic: str = "1", for_map: str = "0",
               user: dict = Depends(current_user)):
    """Alertas confirmadas, con filtros del workflow:
      ?status=pendiente          solo un estado
      ?node=esp32-01             solo un nodo
      ?include_synthetic=0       oculta las del generador de pruebas
      ?for_map=1                 excluye falsa-alarma/descartada (limpieza del mapa)
    """
    alerts = STORE().alerts(status=status, node=node,
                            include_synthetic=(include_synthetic != "0"),
                            for_map=(for_map == "1"))
    return [_with_clip_url(a) for a in alerts]


# Acciones del flujo de atención (req.9) -> estado destino del workflow.
ALERT_ACTIONS = {
    "atender": "respondida",
    "responder": "respondida",
    "revisar": "en-revision",
    "en-revision": "en-revision",
    "resolver": "resuelta",
    "resuelta": "resuelta",
    "falsa-alarma": "falsa-alarma",
    "falso-positivo": "falsa-alarma",     # alias del PoC viejo
    "descartar": "descartada",
    "descartada": "descartada",
    "reabrir": "pendiente",
    "pendiente": "pendiente",
}


@app.get("/api/alerts/{alert_id}")
def api_alert_detail(alert_id: int, user: dict = Depends(current_user)):
    a = STORE().get_alert(alert_id)
    if not a:
        return JSONResponse({"error": "no existe"}, status_code=404)
    a = _with_clip_url(a)
    a["history"] = STORE().history(alert_id)
    return a


@app.get("/api/alerts/{alert_id}/history")
def api_alert_history(alert_id: int, user: dict = Depends(current_user)):
    return STORE().history(alert_id)


@app.patch("/api/alerts/{alert_id}/status")
async def api_alert_status(alert_id: int, request: Request,
                           user: dict = Depends(current_user)):
    """Body: {action, comment?}. Transición del workflow con auditoría:
    UPDATE + alert_history + events en una transacción (db.py update_status)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = str(body.get("action", "")).strip().lower()
    comment = (body.get("comment") or "").strip() or None
    new_status = ALERT_ACTIONS.get(action)
    if not new_status:
        return JSONResponse(
            {"error": f"acción inválida; usa una de {sorted(set(ALERT_ACTIONS))}"},
            status_code=400)
    result = STORE().update_status(alert_id, new_status, user_id=user["id"],
                                   username=user["username"], comment=comment)
    if not result["ok"]:
        return JSONResponse({"error": result["error"]}, status_code=409)
    return {"ok": True, "id": alert_id, "old": result["old"], "new": result["new"],
            "by": user["username"]}


@app.delete("/api/alerts/{alert_id}")
async def api_alert_delete(alert_id: int, request: Request,
                           user: dict = Depends(current_user)):
    """Falsa alarma (flujo del dashboard): ELIMINA la alerta de la BD de forma
    definitiva — deja de mostrarse en tabla, mapa, KPIs y gráficos. El borrado
    queda registrado en `events` (quién y cuándo). Body opcional: {comment}."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    comment = (body.get("comment") or "").strip() or None
    result = STORE().delete_alert(alert_id, user_id=user["id"],
                                  username=user["username"], comment=comment)
    if not result["ok"]:
        return JSONResponse({"error": result["error"]}, status_code=404)
    return {"ok": True, "id": alert_id, "old": result["old"], "by": user["username"]}


@app.post("/api/alerts/synthetic")
async def api_alerts_synthetic(request: Request,
                               admin: dict = Depends(require_admin)):
    """Generador de alertas SINTÉTICAS (req.6): pobla dashboard/mapa para pruebas,
    sin video ni detector. Body:
      { node_id, count?=1, days?=0 (repartir hacia atrás), status?, confidence?,
        det_class?, lat?, lon?, sensors?: {temp_c, turb_v, humedad, ph, ...} }"""
    import random as _rnd
    import time as _time
    body = await request.json()
    node_id = str(body.get("node_id", "")).strip()
    if not node_id:
        return JSONResponse({"error": "node_id requerido"}, 400)
    count = max(1, min(int(body.get("count", 1)), 500))
    days = max(0.0, float(body.get("days", 0)))
    sensors = body.get("sensors") or {}
    ids = []
    now_ms = int(_time.time() * 1000)
    store = STORE()
    node = DB().get_node(node_id) or {}
    for i in range(count):
        ts = now_ms - int(_rnd.uniform(0, days * 86400 * 1000)) if days else now_ms
        s = dict(sensors)
        conf = body.get("confidence")
        try:
            _, risk_level, _ = risk.evaluate_node(node_id, sensores=s)
        except Exception:
            risk_level = None
        ids.append(store.insert_alert({
            "nodeId": node_id,
            "nodeName": body.get("node_name") or node.get("display_name") or node_id,
            "district": body.get("district") or node.get("district"),
            "lat": body.get("lat", node.get("lat")),
            "lon": body.get("lon", node.get("lon")),
            "ts": ts,
            "confidence": float(conf) if conf is not None else round(_rnd.uniform(0.7, 0.99), 3),
            "source": body.get("source", "camera"),
            "detClass": body.get("det_class", "Mosquito"),
            "detCount": int(body.get("det_count", _rnd.randint(1, 12))),
            "videoUrl": None,
            "status": body.get("status", "pendiente"),
            "riskLevel": risk_level,
            "isSynthetic": True,
            "sensors": s,
        }))
    auth.log_event("alerts.synthetic", user=admin, entity="alert",
                   detail={"node_id": node_id, "count": count})
    return {"ok": True, "created": len(ids), "ids": ids[:20]}


# ───────────────────────────── APIs de monitoreo ────────────────────────────
def _node_sensors_map() -> dict[str, list[str]]:
    """{node_id: [sensores instalados]} desde la tabla node_sensors."""
    with pgdb.get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT node_id, sensor FROM node_sensors WHERE installed ORDER BY sensor"
        ).fetchall()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["node_id"], []).append(r["sensor"])
    return out


def _enrich_node(node: dict, sensors_map: dict, counts: dict) -> dict:
    """Req.7: TODO lo que el mapa/dashboard muestra de un nodo sale de la BD."""
    nid = node["node_name"]                     # alias de node_id (contrato viejo)
    c = counts.get(nid, {"total": 0, "visibles": 0})
    node["sensors_installed"] = sensors_map.get(nid, [])
    node["alert_count"] = c["total"]
    node["alert_visible"] = c["visibles"]
    node["last_reading_data"] = DB().last_reading(nid)
    return node


@app.get("/api/nodes")
def api_nodes(user: dict = Depends(current_user)):
    """Nodos enriquecidos: estado + riesgo + sensores instalados + nº de alertas
    + última lectura. Nada viene hardcodeado: todo sale de la BD."""
    sensors_map = _node_sensors_map()
    counts = STORE().counts_by_node()
    return [_enrich_node(n, sensors_map, counts) for n in DB().all_nodes()]


@app.get("/api/node/{name}/detections")
def api_detections(name: str, page: int = 1, size: int = 50,
                   user: dict = Depends(current_user)):
    rows, total = DB().detections(name, page, size)
    return {"total": total, "page": page, "size": size, "rows": rows}


@app.get("/api/node/{name}/heartbeats")
def api_heartbeats(name: str, user: dict = Depends(current_user)):
    return DB().heartbeats(name)


@app.get("/api/node/{name}/risk")
def api_node_risk(name: str, user: dict = Depends(current_user)):
    """Desglose del score de riesgo por factor (tooltip/depuración)."""
    if not DB().get_node(name):
        return JSONResponse({"error": "no existe"}, status_code=404)
    score, level, detalle = risk.evaluate_node(name)
    return {"node": name, "score": score, "level": level, **detalle}


@app.get("/api/node/{name}")
def api_node(name: str, user: dict = Depends(current_user)):
    node = DB().get_node(name)
    if not node:
        return JSONResponse({"error": "no existe"}, status_code=404)
    node = _enrich_node(node, _node_sensors_map(), STORE().counts_by_node())
    node["anomalies"] = DB().anomalies(node["node_name"])
    node["status_history"] = DB().status_history(node["node_name"])
    return node


# Comandos que el firmware entiende (ver onMqttMessage en nodo_iot_autocalib.ino):
#   "recalib"   -> detectorForceRecalibration() (re-mide el ruido de fondo ~10 s)
#   "heartbeat" -> smRequestHeartbeat() (publica su estado al instante)
#   "restart"   -> ESP.restart()
CMD_ALLOWED = {"recalib", "heartbeat", "restart"}


@app.post("/api/node/{name}/cmd")
async def api_node_cmd(name: str, request: Request,
                       user: dict = Depends(current_user)):
    """Publica una orden al nodo por MQTT en 'devices/<name>/cmd' (QoS1, sin retener:
    un comando retenido se re-aplicaria en cada reconexion). Reusa el cliente MQTT
    del ingest (ya autenticado y conectado). El ESP32 esta suscrito a ese topic.
    Requiere sesión (operador o admin): es una acción administrativa del dashboard."""
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
               desc: str = "1", user: dict = Depends(current_user)):
    return DB().videos(node, order=order, desc=(desc != "0"))


# ─────────────────── configuración (detector + riesgo, admin) ───────────────
@app.get("/api/config/detector")
def api_config_detector_get(admin: dict = Depends(require_admin)):
    """Parámetros del detector de visión (tabla detector_params, con rangos)."""
    with pgdb.get_pool().connection() as conn:
        return conn.execute(
            """SELECT key, value_num, value_txt, value_type, min_num, max_num,
                      description, updated_at
               FROM detector_params ORDER BY key"""
        ).fetchall()


@app.put("/api/config/detector")
async def api_config_detector_put(request: Request,
                                  admin: dict = Depends(require_admin)):
    """Body: {clave: valor, ...}. Valida el rango [min_num, max_num] de cada
    clave. El detector recarga estos valores al inicio de CADA análisis de clip
    (hot-reload sin reiniciar el gateway)."""
    body = await request.json()
    if not isinstance(body, dict) or not body:
        return JSONResponse({"error": "body debe ser {clave: valor}"}, 400)
    errores, aplicados = {}, {}
    with pgdb.get_pool().connection() as conn:
        for key, value in body.items():
            row = conn.execute(
                "SELECT min_num, max_num FROM detector_params WHERE key=%s", (key,)
            ).fetchone()
            if not row:
                errores[key] = "clave desconocida"
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                errores[key] = "debe ser numérico"
                continue
            if row["min_num"] is not None and v < row["min_num"]:
                errores[key] = f"mínimo {row['min_num']}"
                continue
            if row["max_num"] is not None and v > row["max_num"]:
                errores[key] = f"máximo {row['max_num']}"
                continue
            conn.execute(
                """UPDATE detector_params
                   SET value_num=%s, updated_at=now(), updated_by=%s WHERE key=%s""",
                (v, admin["id"], key))
            aplicados[key] = v
    if aplicados:
        auth.log_event("config.detector", user=admin, entity="detector_params",
                       detail=aplicados)
    status = 200 if not errores else (207 if aplicados else 400)
    return JSONResponse({"ok": not errores, "aplicados": aplicados,
                         "errores": errores}, status_code=status)


@app.get("/api/config/risk")
def api_config_risk_get(admin: dict = Depends(require_admin)):
    return risk.load_config()


@app.put("/api/config/risk")
async def api_config_risk_put(request: Request,
                              admin: dict = Depends(require_admin)):
    """Reemplaza (merge) la config del motor de riesgo en system_config['risk'].
    El job de riesgo la relee en cada ciclo (efecto en <=5 min, o al instante
    en /api/node/<id>/risk)."""
    import json as _json
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"error": "body debe ser un objeto"}, 400)
    nueva = {**risk.load_config(), **body}
    # sanity: los pesos deben ser numéricos
    try:
        for k, v in nueva.get("pesos", {}).items():
            float(v)
    except (TypeError, ValueError):
        return JSONResponse({"error": "pesos inválidos"}, 400)
    with pgdb.get_pool().connection() as conn:
        conn.execute(
            """INSERT INTO system_config (key, value, description)
               VALUES ('risk', %s, 'pesos y umbrales del motor de riesgo')
               ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()""",
            (_json.dumps(nueva),))
    auth.log_event("config.risk", user=admin, detail=body)
    return {"ok": True, "config": nueva}


# ───────────────────────── clips (.webm con Range 206) ──────────────────────
# FileResponse trae el soporte de Range/206 y Accept-Ranges integrado:
# reemplaza ~80 lineas de manejo manual de bytes en serve.py.
# Requiere sesión: los <video> del dashboard mandan la cookie solos (same-origin).
@app.get("/clips/{rel_path:path}")
def serve_clip(rel_path: str, user: dict = Depends(current_user)):
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
def delete_video(vid: int, user: dict = Depends(current_user)):
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
# Cache-Control: no-cache => el navegador REVALIDA los js/css en cada carga y
# las actualizaciones del dashboard llegan sin Ctrl+Shift+R (son archivos chicos).
@app.get("/{full_path:path}")
def serve_static(full_path: str):
    rel = full_path or "index.html"
    full = (DASHBOARD_DIR / rel).resolve()
    if not full.is_relative_to(DASHBOARD_DIR.resolve()) or not full.is_file():
        full = DASHBOARD_DIR / "index.html"
    return FileResponse(full, headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(app, host="0.0.0.0", port=port)

"""
app.py — SIMULADOR DE NODO ESP32 + GENERADOR DE ALERTAS SINTÉTICAS (web :8200).

Herramienta de PRUEBAS independiente (no corre en producción). Dos pestañas:

  1) Simulador de nodo — un "ESP32 virtual" INDISTINGUIBLE del real para el
     backend: publica por MQTT exactamente los mismos topics/payloads del
     firmware (capa2-red/MQTT_SPEC.md), responde a devices/<id>/cmd
     (recalib|heartbeat|restart), mantiene LWT en availability, y al disparar
     una alerta puede subir una ráfaga jpegseq SINTÉTICA (mosquitos dibujados
     con trayectoria errática) al gateway :8090 — ejercita el detector REAL
     end-to-end. Sensores extra (humedad/pH/nivel_agua) viajan como claves
     ADITIVAS en el JSON de sensors: el protocolo no cambia.

  2) Generador de alertas sintéticas — inserta alertas directamente en la BD
     (is_synthetic=TRUE), sin video ni detector, para poblar dashboard y mapa.

Uso:
    python3 app.py            # http://localhost:8200
"""

from __future__ import annotations

import json
import random
import struct
import sys
import threading
import time
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                              # raíz del proyecto
CAPA3 = ROOT / "capa3-procesamiento-servidor"
sys.path.insert(0, str(CAPA3))

import config as cfg                                # capa3/config.py (MQTT_*)
from database import get_pool                       # pool PostgreSQL
from db import AlertStore                           # alertas (para sintéticas)
import risk                                         # riesgo estampado en sintéticas

GATEWAY_UPLOAD = f"http://localhost:{cfg.GATEWAY_HTTP_PORT}/upload"

app = FastAPI(title="Simulador de nodo ESP32", version="1.0")

_log: list[str] = []
_log_lock = threading.Lock()


def log(msg: str):
    line = time.strftime("%H:%M:%S ") + msg
    print("[SIM]", line)
    with _log_lock:
        _log.append(line)
        del _log[:-300]


# ─────────────────────────── jpegseq sintético ───────────────────────────────
def gen_jpegseq(n_mosquitos: int = 1, frames: int = 60, w: int = 640,
                h: int = 480, con_mosquito: bool = True) -> bytes:
    """Ráfaga [4B len big-endian][JPEG]... IDÉNTICA a la del firmware
    (nodo_iot_autocalib.ino líneas 447-451). Los "mosquitos" son puntos oscuros
    de 3 px con trayectoria errática — disparan el detector real de capa 3."""
    import numpy as np
    import cv2

    base = np.full((h, w, 3), 190, np.uint8)
    noise = np.random.RandomState(3).randint(-12, 12, (h, w, 3)).astype(np.int16)
    base = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    mosquitos = []
    for _ in range(max(0, n_mosquitos) if con_mosquito else 0):
        mosquitos.append({
            "x": random.uniform(60, w - 60), "y": random.uniform(60, h - 60),
            "vx": random.uniform(-4, 4), "vy": random.uniform(-4, 4),
        })

    chunks = []
    for _ in range(frames):
        f = base.copy()
        tn = np.random.randint(-4, 4, (h, w, 1)).astype(np.int16)
        f = np.clip(f.astype(np.int16) + tn, 0, 255).astype(np.uint8)
        for m in mosquitos:
            m["vx"] += random.uniform(-1.8, 1.8)
            m["vy"] += random.uniform(-1.8, 1.8)
            sp = (m["vx"] ** 2 + m["vy"] ** 2) ** 0.5
            if sp > 7:
                m["vx"], m["vy"] = m["vx"] / sp * 7, m["vy"] / sp * 7
            if sp < 2.5:
                m["vx"], m["vy"] = m["vx"] * 1.6 + 0.5, m["vy"] * 1.6 + 0.5
            m["x"] = min(max(m["x"] + m["vx"], 30), w - 30)
            m["y"] = min(max(m["y"] + m["vy"], 30), h - 30)
            cv2.circle(f, (int(m["x"]), int(m["y"])), 3, (25, 25, 25), -1)
        ok, jpg = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            chunks.append(struct.pack(">I", len(jpg)) + jpg.tobytes())
    return b"".join(chunks)


# ───────────────────────────── nodo simulado ─────────────────────────────────
class SimNode:
    """Un ESP32 virtual. Reproduce el comportamiento del firmware real:
    heartbeat periódico, sensores al disparar, cmd por MQTT, LWT."""

    def __init__(self, node_id: str, conf: dict):
        self.node_id = node_id
        self.conf = {
            "temp_c": 26.0, "humedad": None, "turb_v": 1.0, "ph": None,
            "nivel_agua": None, "n_mosquitos": 1, "movimiento": True,
            "lat": -12.046 + random.uniform(-0.05, 0.05),
            "lon": -77.043 + random.uniform(-0.05, 0.05),
            "sats": 7, "intervalo_s": 0, "heartbeat_s": 60,
            "auto_video": True, "confidence": 0.85,
        }
        self.conf.update({k: v for k, v in (conf or {}).items() if k in self.conf})
        self.seq = 0
        self.boot = time.time()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"sim-{node_id}")
        if cfg.MQTT_USER:
            self.client.username_pw_set(cfg.MQTT_USER, cfg.MQTT_PASS)
        # LWT idéntico al firmware: availability retained
        self.client.will_set(f"devices/{node_id}/availability",
                             json.dumps({"online": False}), qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    # ------------------------------------------------------------- ciclo
    def start(self):
        self.client.connect_async(cfg.MQTT_HOST, cfg.MQTT_PORT, keepalive=30)
        self.client.loop_start()
        t = threading.Thread(target=self._auto_loop, daemon=True)
        t.start()
        self._threads.append(t)
        self._mark_simulated()
        log(f"{self.node_id}: nodo simulado INICIADO")

    def stop(self):
        self._stop.set()
        try:
            self.client.publish(f"devices/{self.node_id}/availability",
                                json.dumps({"online": False}), qos=1, retain=True)
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        log(f"{self.node_id}: nodo simulado DETENIDO")

    def _mark_simulated(self):
        """Deja constancia en la BD de que este nodo es de pruebas."""
        try:
            with get_pool().connection() as conn:
                conn.execute(
                    """INSERT INTO nodes (node_id, node_name, district, lat, lon, is_simulated)
                       VALUES (%s,%s,'Simulado',%s,%s,TRUE)
                       ON CONFLICT (node_id) DO UPDATE SET is_simulated=TRUE""",
                    (self.node_id, f"Nodo SIM {self.node_id}",
                     self.conf["lat"], self.conf["lon"]),
                )
                for s in ("temp_ds18b20", "turbidez", "gps", "audio",
                          "humedad", "ph", "nivel_agua"):
                    conn.execute(
                        """INSERT INTO node_sensors (node_id, sensor) VALUES (%s,%s)
                           ON CONFLICT (node_id, sensor) DO NOTHING""",
                        (self.node_id, s))
        except Exception as e:
            log(f"{self.node_id}: no se pudo marcar is_simulated: {e}")

    # ------------------------------------------------------------- MQTT
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            log(f"{self.node_id}: error MQTT rc={rc}")
            return
        # availability online (retained) + suscripción a cmd, como el firmware
        client.publish(f"devices/{self.node_id}/availability",
                       json.dumps({"online": True}), qos=1, retain=True)
        client.subscribe(f"devices/{self.node_id}/cmd", qos=1)
        log(f"{self.node_id}: conectado al broker; escuchando cmd")
        self.publish_heartbeat()

    def _on_message(self, client, userdata, msg):
        cmd = msg.payload.decode(errors="replace").strip().lower()
        log(f"{self.node_id}: cmd recibido -> '{cmd}'")
        if cmd == "heartbeat":
            self.publish_heartbeat()
        elif cmd == "recalib":
            log(f"{self.node_id}: (sim) recalibrando ~10 s...")
        elif cmd in ("restart", "reboot"):
            self.boot = time.time()
            self.seq = 0
            log(f"{self.node_id}: (sim) reiniciado — uptime/seq a cero")
            self.publish_heartbeat()

    # ------------------------------------------------------------- payloads
    # Idénticos al firmware (nodo_iot_autocalib.ino / self_monitor.h).
    def publish_heartbeat(self):
        self.seq += 1
        payload = {
            "node_name": self.node_id,
            "status": "alive",
            "uptime_s": int(time.time() - self.boot),
            "battery_pct": -1,
            "chip_temp_c": round(40 + random.uniform(-2, 4), 1),
            "threshold": 0.45,
            "timestamp": int(time.time()),
            "seq": self.seq,
        }
        self.client.publish(f"nodes/{self.node_id}/heartbeat", json.dumps(payload))
        log(f"{self.node_id}: heartbeat seq={self.seq}")

    def publish_sensors(self):
        c = self.conf
        turb_v = float(c["turb_v"])
        sensors = {
            "turb_raw": int(turb_v / 3.3 * 4095),
            "turb_v": round(turb_v, 3),
            "temp_c": round(float(c["temp_c"]), 2),
        }
        # ADITIVO: campos que el ESP32 real no manda (el gateway los pasa tal cual)
        for extra in ("humedad", "ph", "nivel_agua"):
            if c.get(extra) is not None:
                sensors[extra] = round(float(c[extra]), 2)
        self.client.publish(f"devices/{self.node_id}/sensors", json.dumps(sensors))

        gps = {"lat": round(c["lat"], 6), "lon": round(c["lon"], 6),
               "alt": 150.0, "sats": int(c["sats"])}
        self.client.publish(f"devices/{self.node_id}/gps", json.dumps(gps),
                            qos=0, retain=True)

        conf = float(c["confidence"])
        self.client.publish(f"devices/{self.node_id}/audio",
                            json.dumps({"mosquito_conf": round(conf, 2)}))
        self.client.publish(
            f"devices/{self.node_id}/status",
            json.dumps({"uptime_ms": int((time.time() - self.boot) * 1000),
                        "rssi": random.randint(-70, -40),
                        "heap_free": random.randint(180000, 260000)}),
            qos=0, retain=True)

    def trigger_alert(self, with_video: bool | None = None):
        """Secuencia EXACTA del firmware al detectar: alert -> sensores -> video."""
        c = self.conf
        self.seq += 1
        alert = {
            "node_name": self.node_id,
            "source": "audio",
            "confidence": round(float(c["confidence"]), 2),
            "ts": int((time.time() - self.boot) * 1000),
            "timestamp": int(time.time()),
            "seq": self.seq,
        }
        self.client.publish(f"devices/{self.node_id}/alert", json.dumps(alert), qos=1)
        self.publish_sensors()
        log(f"{self.node_id}: ALERTA disparada (conf={alert['confidence']}, seq={self.seq})")

        use_video = c["auto_video"] if with_video is None else with_video
        if use_video:
            threading.Thread(target=self._upload_burst, daemon=True).start()

    def _upload_burst(self):
        c = self.conf
        try:
            n = int(c["n_mosquitos"]) if c["movimiento"] else 0
            data = gen_jpegseq(n_mosquitos=n, con_mosquito=bool(c["movimiento"]))
            url = (f"{GATEWAY_UPLOAD}?device={self.node_id}"
                   f"&fmt=jpegseq&seconds=6")
            req = urllib.request.Request(
                url, data=data, method="POST",
                headers={"Content-Type": "application/octet-stream"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                log(f"{self.node_id}: ráfaga jpegseq subida "
                    f"({len(data)} B, {n} mosquito(s)) -> {resp.status}")
        except Exception as e:
            log(f"{self.node_id}: fallo subiendo la ráfaga: {e}")

    # ------------------------------------------------------------- auto
    def _auto_loop(self):
        """Publica sensores/heartbeat periódicamente; si intervalo_s>0 también
        dispara alertas solas (modo auto)."""
        last_hb = last_alert = last_sensors = time.time()
        while not self._stop.wait(1):
            now = time.time()
            if now - last_hb >= float(self.conf["heartbeat_s"]):
                self.publish_heartbeat()
                last_hb = now
            if now - last_sensors >= 30:          # lectura periódica de sensores
                self.publish_sensors()
                last_sensors = now
            iv = float(self.conf["intervalo_s"])
            if iv > 0 and now - last_alert >= iv:
                self.trigger_alert()
                last_alert = now


SIM_NODES: dict[str, SimNode] = {}
_nodes_lock = threading.Lock()


# ─────────────────────────────── API web ─────────────────────────────────────
@app.get("/")
def home():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/api/state")
def state():
    with _nodes_lock:
        nodes = {nid: {"conf": n.conf, "seq": n.seq,
                       "uptime_s": int(time.time() - n.boot)}
                 for nid, n in SIM_NODES.items()}
    with _log_lock:
        tail = _log[-60:]
    return {"nodes": nodes, "log": tail,
            "broker": f"{cfg.MQTT_HOST}:{cfg.MQTT_PORT}",
            "gateway": GATEWAY_UPLOAD}


@app.post("/api/node/start")
async def node_start(request: Request):
    body = await request.json()
    node_id = str(body.get("node_id", "")).strip() or "esp32-99"
    with _nodes_lock:
        if node_id in SIM_NODES:
            return JSONResponse({"error": f"{node_id} ya está corriendo"}, 409)
        node = SimNode(node_id, body.get("conf") or {})
        SIM_NODES[node_id] = node
    node.start()
    return {"ok": True, "node_id": node_id, "conf": node.conf}


@app.post("/api/node/stop")
async def node_stop(request: Request):
    body = await request.json()
    node_id = str(body.get("node_id", ""))
    with _nodes_lock:
        node = SIM_NODES.pop(node_id, None)
    if not node:
        return JSONResponse({"error": "ese nodo no está corriendo"}, 404)
    node.stop()
    return {"ok": True}


@app.post("/api/node/update")
async def node_update(request: Request):
    body = await request.json()
    node_id = str(body.get("node_id", ""))
    with _nodes_lock:
        node = SIM_NODES.get(node_id)
    if not node:
        return JSONResponse({"error": "ese nodo no está corriendo"}, 404)
    cambios = {k: v for k, v in (body.get("conf") or {}).items() if k in node.conf}
    node.conf.update(cambios)
    return {"ok": True, "conf": node.conf}


@app.post("/api/node/trigger")
async def node_trigger(request: Request):
    body = await request.json()
    node_id = str(body.get("node_id", ""))
    with _nodes_lock:
        node = SIM_NODES.get(node_id)
    if not node:
        return JSONResponse({"error": "ese nodo no está corriendo"}, 404)
    node.trigger_alert(with_video=body.get("with_video"))
    return {"ok": True}


# ───────────────── pestaña 2: alertas sintéticas (BD directa) ────────────────
@app.post("/api/synthetic")
async def synthetic(request: Request):
    """Inserta alertas sintéticas DIRECTO en la BD (herramienta local de pruebas;
    equivale al POST /api/alerts/synthetic del dashboard, sin pasar por su login).
    Body: {node_id, count, days, status, confidence, sensors{...}, lat?, lon?}"""
    body = await request.json()
    node_id = str(body.get("node_id", "")).strip()
    if not node_id:
        return JSONResponse({"error": "node_id requerido"}, 400)
    count = max(1, min(int(body.get("count", 1)), 500))
    days = max(0.0, float(body.get("days", 0)))
    sensors = {k: v for k, v in (body.get("sensors") or {}).items() if v is not None}
    status = body.get("status", "pendiente")

    store = AlertStore()
    with get_pool().connection() as conn:
        node = conn.execute(
            "SELECT node_name, district, lat, lon FROM nodes WHERE node_id=%s",
            (node_id,)).fetchone() or {}

    lat = body.get("lat", node.get("lat"))
    lon = body.get("lon", node.get("lon"))
    now_ms = int(time.time() * 1000)
    ids = []
    for _ in range(count):
        try:
            _, risk_level, _ = risk.evaluate_node(node_id, sensores=sensors)
        except Exception:
            risk_level = None
        conf = body.get("confidence")
        ids.append(store.insert_alert({
            "nodeId": node_id,
            "nodeName": node.get("node_name") or f"Nodo SIM {node_id}",
            "district": node.get("district") or "Simulado",
            "lat": (lat + random.uniform(-0.004, 0.004)) if lat is not None else None,
            "lon": (lon + random.uniform(-0.004, 0.004)) if lon is not None else None,
            "ts": now_ms - int(random.uniform(0, days * 86400 * 1000)) if days else now_ms,
            "confidence": float(conf) if conf is not None else round(random.uniform(0.7, 0.99), 3),
            "source": "camera",
            "detClass": body.get("det_class", "Mosquito"),
            "detCount": random.randint(1, 12),
            "videoUrl": None,
            "status": status,
            "riskLevel": risk_level,
            "isSynthetic": True,
            "sensors": sensors,
        }))
    log(f"sintéticas: {len(ids)} alerta(s) para {node_id} (estado={status})")
    return {"ok": True, "created": len(ids)}


@app.get("/api/db-nodes")
def db_nodes():
    """Nodos existentes en la BD (para el <select> del generador)."""
    with get_pool().connection() as conn:
        return conn.execute(
            "SELECT node_id, node_name, is_simulated FROM nodes ORDER BY node_id"
        ).fetchall()


if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8200
    print(f"Simulador de nodo ESP32 -> http://localhost:{port}")
    print(f"  broker : {cfg.MQTT_HOST}:{cfg.MQTT_PORT}")
    print(f"  gateway: {GATEWAY_UPLOAD}")
    uvicorn.run(app, host="127.0.0.1", port=port)   # SOLO local: es una herramienta de pruebas

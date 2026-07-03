"""
gateway.py — EL CORAZON de la Capa de Aplicacion (project_iot_2).

Orquesta el flujo event-driven y aplica la COMPUERTA DE VISION (por movimiento):
   nodo dispara alert --> camara graba clip 5-10s --> gateway analiza el movimiento
   detecta movimiento tipo mosquito?  SI -> GUARDAR en BD + avisar dashboard
                                      NO -> DESCARTAR (falso positivo)
   (en paralelo) cachea sensors/gps/status de cada nodo para enriquecer la alerta

Modos:
  python gateway.py            # real: requiere broker + OpenCV + clips reales
  python gateway.py --sim      # demo: no analiza video; simula el veredicto
"""

from __future__ import annotations

import sys
import json
import time
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import paho.mqtt.client as mqtt

import config as cfg          # mismo directorio: config.py, db.py, detector.py
from db import AlertStore

SIM = "--sim" in sys.argv


def load_nodes() -> dict:
    try:
        return json.loads(cfg.NODES_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[GATEWAY] nodes.json no disponible ({e}); se usara info minima.")
        return {}


class Gateway:
    def __init__(self):
        self.nodes = load_nodes()
        self.store = None          # AlertStore (PostgreSQL); se abre con _get_store()
        self.cache = {}
        self.gate = None

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if cfg.MQTT_USER:
            self.client.username_pw_set(cfg.MQTT_USER, cfg.MQTT_PASS)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def _get_store(self, retries: int = 5) -> AlertStore | None:
        """AlertStore sobre PostgreSQL, con reintento y backoff exponencial.
        Se llama desde los hilos de clip (NO desde el hilo de red MQTT), así que
        esperar aquí no bloquea la recepción de mensajes. Devuelve None si PG
        sigue caído tras los reintentos (la alerta se pierde con un log claro)."""
        if self.store is not None:
            return self.store
        wait = 1.0
        for intento in range(1, retries + 1):
            try:
                self.store = AlertStore()
                print("[GATEWAY] Conectado a PostgreSQL.")
                return self.store
            except Exception as e:
                print(f"[GATEWAY] PostgreSQL no responde (intento {intento}/{retries}): {e}")
                time.sleep(wait)
                wait = min(wait * 2, 30)
        return None

    def run(self):
        mode = "SIMULACION (sin analisis real)" if SIM else "REAL (vision por movimiento + broker)"
        print(f"[GATEWAY] Iniciando en modo {mode}")
        from database import PG_HOST, PG_PORT, PG_DB
        print(f"[GATEWAY] Broker {cfg.MQTT_HOST}:{cfg.MQTT_PORT}  -  "
              f"BD postgresql://{PG_HOST}:{PG_PORT}/{PG_DB}")
        self._get_store(retries=1)     # intento temprano (no fatal si PG aún no está)
        self._start_upload_server()
        self.client.connect(cfg.MQTT_HOST, cfg.MQTT_PORT, keepalive=60)
        self.client.loop_forever()

    def _start_upload_server(self):
        """Receptor HTTP de clips (modo DISTRIBUIDO). La camara remota hace POST con
        el .webm en el cuerpo; aqui se guarda en CLIPS_DIR y se analiza igual que un
        clip local. Convive con el modo local (clip por MQTT): ambos llaman handle_clip."""
        gw = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):   # silencia el log HTTP por defecto
                pass

            def do_POST(self):
                if not urlparse(self.path).path.startswith("/upload"):
                    self.send_response(404); self.end_headers(); return
                q = parse_qs(urlparse(self.path).query)
                device = q.get("device", ["desconocido"])[0]
                fmt = q.get("fmt", ["file"])[0]
                seconds = float(q.get("seconds", ["8"])[0])
                length = int(self.headers.get("Content-Length", 0))
                data = self.rfile.read(length) if length else b""
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

                if fmt == "jpegseq":
                    # Rafaga de JPEGs del ESP32: [4B len][jpeg][4B len][jpeg]...
                    print(f"[GATEWAY] Rafaga JPEG recibida de {device}: {len(data)} bytes")
                    threading.Thread(target=gw.handle_jpegseq,
                                     args=(device, data, seconds), daemon=True).start()
                else:
                    name = Path(q.get("name", ["clip.webm"])[0]).name   # anti path-traversal
                    out_dir = Path(cfg.CLIPS_DIR) / device
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / name
                    out_path.write_bytes(data)
                    print(f"[GATEWAY] Clip recibido por HTTP de {device}: {name} ({len(data)} bytes)")
                    threading.Thread(target=gw.handle_clip,
                                     args=(device, {"video_path": str(out_path)}),
                                     daemon=True).start()

        try:
            srv = ThreadingHTTPServer((cfg.GATEWAY_HTTP_HOST, cfg.GATEWAY_HTTP_PORT), _Handler)
        except OSError as e:
            print(f"[GATEWAY] No se pudo abrir el receptor HTTP {cfg.GATEWAY_HTTP_PORT}: {e}")
            return
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"[GATEWAY] Receptor HTTP de clips en "
              f"{cfg.GATEWAY_HTTP_HOST}:{cfg.GATEWAY_HTTP_PORT}/upload")

    def handle_jpegseq(self, device, data, seconds):
        """Recibe una rafaga de JPEGs del ESP32 ([4B len][jpeg]...), la arma como
        .webm (para el dashboard) y la pasa por el mismo analisis de movimiento."""
        import cv2
        import numpy as np
        frames = []
        i, n = 0, len(data)
        while i + 4 <= n:
            ln = int.from_bytes(data[i:i + 4], "big")
            i += 4
            if ln <= 0 or i + ln > n:
                break
            img = cv2.imdecode(np.frombuffer(data[i:i + ln], dtype=np.uint8),
                               cv2.IMREAD_COLOR)
            i += ln
            if img is not None:
                frames.append(img)
        if not frames:
            print(f"[GATEWAY] {device}: rafaga sin frames validos; descartada.")
            return
        out_dir = Path(cfg.CLIPS_DIR) / device
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_path = out_dir / f"{stamp}.webm"
        h, w = frames[0].shape[:2]
        fps = max(1.0, len(frames) / seconds) if seconds > 0 else 10.0
        wr = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"VP80"), fps, (w, h))
        for f in frames:
            if f.shape[1] != w or f.shape[0] != h:
                f = cv2.resize(f, (w, h))
            wr.write(f)
        wr.release()
        print(f"[GATEWAY] {device}: rafaga -> {out_path.name} "
              f"({len(frames)} frames @ {fps:.1f}fps)")
        self.handle_clip(device, {"video_path": str(out_path)})

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            print(f"[GATEWAY] Error de conexion MQTT rc={rc}")
            return
        print("[GATEWAY] Conectado al broker. Suscribiendo...")
        for topic in (cfg.TOPIC_ALERT_WILDCARD, cfg.TOPIC_SENSORS_WILDCARD,
                      cfg.TOPIC_GPS_WILDCARD, cfg.TOPIC_STATUS_WILDCARD,
                      cfg.TOPIC_CLIP_WILDCARD):
            client.subscribe(topic, qos=1)
            print(f"[GATEWAY]   -> {topic}")

    def on_message(self, client, userdata, msg):
        device = cfg.device_from_topic(msg.topic)
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            payload = {"raw": msg.payload.decode(errors="replace")}

        if msg.topic.endswith("/camera/clip"):
            threading.Thread(target=self.handle_clip, args=(device, payload), daemon=True).start()
        elif msg.topic.endswith("/alert"):
            print(f"[GATEWAY] Disparo de {device}: {payload} (esperando clip...)")
        elif msg.topic.endswith("/sensors"):
            self.cache.setdefault(device, {})["sensors"] = payload
        elif msg.topic.endswith("/gps"):
            self.cache.setdefault(device, {})["gps"] = payload
        elif msg.topic.endswith("/status"):
            self.cache.setdefault(device, {})["status"] = payload

    def handle_clip(self, device: str, payload: dict):
        video = payload.get("video_path") or payload.get("video_url")
        if not video:
            print(f"[GATEWAY] clip de {device} sin video_path; ignorado.")
            return
        print(f"[GATEWAY] Clip de {device}: {video} -> analizando movimiento...")

        verdict = self.analyze(video)
        print(f"[GATEWAY] Veredicto {device}: {verdict_summary(verdict)}")

        if not verdict["detected"]:
            print(f"[GATEWAY] DESCARTADO: sin movimiento tipo mosquito. No se guarda en BD ({device}).")
            return

        store = self._get_store()
        if store is None:
            print(f"[GATEWAY] PERDIDA: PostgreSQL caído, no se pudo guardar la alerta de {device}.")
            return

        alert = self.build_alert(device, video, verdict)
        new_id = store.insert_alert(alert)
        top = verdict["top_class"]
        conf = verdict["max_confidence"]
        print(f"[GATEWAY] GUARDADO en BD (id={new_id}): {top} conf={conf} - {alert['district']}")

        meta = {
            "video_url": video,
            "ts": alert["ts"],
            "confidence": conf,
            "det_class": top,
            "detections": verdict["total_detections"],
            "model": "motion-mog2+flow",
        }
        self.client.publish(cfg.topic_detection(device), json.dumps(meta), qos=1)

    def analyze(self, video: str) -> dict:
        if SIM:
            return self._sim_verdict(video)
        if self.gate is None:
            from detector import VisionGate
            self.gate = VisionGate()
        v = self.gate.analyze_video(video)
        return {
            "detected": v.detected,
            "top_class": v.top_class,
            "total_detections": v.total_detections,
            "max_confidence": v.max_confidence,
            "per_class": v.per_class,
        }

    @staticmethod
    def _sim_verdict(video: str) -> dict:
        if "neg" in Path(video).stem.lower():
            return {"detected": False, "top_class": None, "total_detections": 0,
                    "max_confidence": 0.0, "per_class": {}}
        return {"detected": True, "top_class": "Mosquito", "total_detections": 9,
                "max_confidence": 0.93, "per_class": {"Mosquito": {"count": 9, "avg_conf": 0.9}}}

    def build_alert(self, device: str, video: str, verdict: dict) -> dict:
        node = self.nodes.get(device, {})
        c = self.cache.get(device, {})
        gps = c.get("gps", {})
        sensors_msg = c.get("sensors", {})
        status_msg = c.get("status", {}) or {}

        # Nivel de riesgo del nodo EN EL MOMENTO de la alerta (queda estampado).
        risk_level = None
        try:
            import risk
            _, risk_level, _ = risk.evaluate_node(device, sensores=sensors_msg)
        except Exception as e:
            print(f"[GATEWAY] riesgo no calculado para {device}: {e}")

        return {
            "riskLevel": risk_level,
            "nodeId": device,
            "nodeName": node.get("name", device),
            "district": node.get("district", "desconocido"),
            "lat": gps.get("lat", node.get("lat")),
            "lon": gps.get("lon", node.get("lon")),
            "ts": int(time.time() * 1000),
            "confidence": verdict["max_confidence"],
            "source": "camera",
            "detClass": verdict["top_class"],
            "detCount": verdict["total_detections"],
            "videoUrl": video,
            "status": "pendiente",
            "sensors": {
                "temp_c": sensors_msg.get("temp_c"),
                "turb_v": sensors_msg.get("turb_v"),
                # Campos ADITIVOS: el ESP32 real no los manda (quedan None); el
                # simulador y nodos futuros sí. El protocolo no cambia.
                "humedad": sensors_msg.get("humedad"),
                "ph": sensors_msg.get("ph"),
                "nivel_agua": sensors_msg.get("nivel_agua"),
                "audio_rms": status_msg.get("audio_rms") or sensors_msg.get("audio_rms"),
                "audio_peak": sensors_msg.get("audio_peak"),
                "sats": gps.get("sats"),
            },
        }


def verdict_summary(v: dict) -> str:
    if v["detected"]:
        return f"POSITIVO - {v['top_class']} ({v['total_detections']} det, conf {v['max_confidence']})"
    return "NEGATIVO - sin detecciones"


if __name__ == "__main__":
    Gateway().run()

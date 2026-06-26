"""
config.py — Parametros del SERVIDOR DE MONITOREO DE NODOS (spec "server prmpt.txt").

Este subsistema es INDEPENDIENTE del gateway/serve existentes: tiene su propia BD
(datos/monitor.db), su propio cliente MQTT y su propio puerto HTTP (:8100). Convive
con el pipeline de vision (gateway.py :8090 + serve.py :8000) sin tocarlo: en MQTT
varios suscriptores pueden leer los mismos topics sin conflicto.

────────────────────────────────────────────────────────────────────────────
MAPEO SPEC  ->  TOPICS REALES DEL ESP32 (firmware nodo_iot_autocalib)
────────────────────────────────────────────────────────────────────────────
El "server prmpt.txt" asume topics nodes/{name}/{detection,heartbeat,video,status}.
El firmware real NO usa todos esos. Aqui se implementa contra lo que el ESP32
PUBLICA de verdad (ver capa1-percepcion-dispositivo/nodo_iot_autocalib/):

  spec nodes/+/detection  ->  devices/+/alert      (QoS1; el disparo del nodo)
  spec nodes/+/heartbeat  ->  nodes/+/heartbeat    (igual; self_monitor.h)
  spec nodes/+/video      ->  HTTP POST /upload?fmt=jpegseq  (rafaga JPEG, no MQTT)
  spec nodes/+/status     ->  devices/+/status (telemetria/online) + nodes/+/status

Identidad: en el firmware actual node_name == device_id (== "esp32-01"), porque
self_monitor.h provisiona node_name = DEVICE_ID. Por eso el id que aparece en
'devices/<id>/...' y el name de 'nodes/<name>/...' son la MISMA clave de nodo.
"""

import os
from pathlib import Path

# Carga sistema_integrado/.env (igual que capa3/config.py) para tomar las
# credenciales del broker (MQTT_USER/MQTT_PASS) ahora que exige autenticación.
# Sin depender de python-dotenv: parser mínimo de respaldo (funciona en la VM con
# PEP 668, donde 'pip install' global está bloqueado).
def _load_env(p: Path) -> None:
    if not p.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(p)
        return
    except ImportError:
        pass
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env(Path(__file__).resolve().parents[2] / ".env")     # sistema_integrado/.env

# --- Broker MQTT (mismo broker que el resto del sistema) ---
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")        # con .env: esp32 (broker ya no es anonimo)
MQTT_PASS = os.getenv("MQTT_PASS", "")
MQTT_CLIENT_ID = os.getenv("MONITOR_MQTT_ID", "node-monitor")

# --- Servidor HTTP del dashboard + receptor de video ---
HTTP_HOST = os.getenv("MONITOR_HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("MONITOR_HTTP_PORT", "8100"))

# --- Rutas (todo vive dentro de Sistema-Integrado-IOT/) ---
HERE = Path(__file__).resolve().parent                       # .../monitor/
CAPA3 = HERE.parent                                          # capa3-procesamiento-servidor/
ROOT = CAPA3.parent                                          # Sistema-Integrado-IOT/
DATOS = ROOT / "datos"
DB_PATH = Path(os.getenv("MONITOR_DB_PATH", DATOS / "monitor.db"))

# Carpeta de clips que el GATEWAY ya escribe (datos/clips/<node>/*.webm). El
# indexador la recorre para llenar la tabla 'videos' con los videos REALES que
# subio el ESP32, sin tocar el firmware ni chocar con el puerto del gateway.
CLIPS_DIR = Path(os.getenv("CLIPS_DIR", DATOS / "clips"))
# Carpeta propia donde el monitor guarda los videos que reciba por SU /upload.
UPLOAD_DIR = Path(os.getenv("MONITOR_UPLOAD_DIR", DATOS / "clips"))

# --- Topics reales (ver mapeo arriba) ---
TOPIC_ALERT     = "devices/+/alert"        # = "detection" del spec
TOPIC_HEARTBEAT = "nodes/+/heartbeat"
TOPIC_DEV_STATUS = "devices/+/status"      # telemetria/online + LWT
TOPIC_NODE_STATUS = "nodes/+/status"       # eventos de self_monitor (reservado)
TOPIC_SENSORS   = "devices/+/sensors"
TOPIC_GPS       = "devices/+/gps"
TOPIC_AUDIO     = "devices/+/audio"

SUBSCRIPTIONS = [
    TOPIC_ALERT, TOPIC_HEARTBEAT, TOPIC_DEV_STATUS, TOPIC_NODE_STATUS,
    TOPIC_SENSORS, TOPIC_GPS, TOPIC_AUDIO,
]

# --- Reglas de liveness (spec: HEARTBEAT MONITORING) ---
HEARTBEAT_CHECK_INTERVAL_S = int(os.getenv("HB_CHECK_INTERVAL_S", "300"))   # cada 5 min
OFFLINE_AFTER_S    = int(os.getenv("OFFLINE_AFTER_S", str(30 * 60)))        # >30 min -> OFFLINE
COMPROMISED_AFTER_S = int(os.getenv("COMPROMISED_AFTER_S", str(24 * 3600))) # >24 h  -> COMPROMISED

# Cada cuanto re-indexar la carpeta de clips para detectar videos nuevos.
VIDEO_INDEX_INTERVAL_S = int(os.getenv("VIDEO_INDEX_INTERVAL_S", "30"))


def node_from_topic(topic: str) -> str:
    """Extrae la clave del nodo del 2o segmento: 'devices/<id>/...' o 'nodes/<name>/...'."""
    parts = topic.split("/")
    return parts[1] if len(parts) >= 2 else "desconocido"

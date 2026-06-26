"""
config.py — Parametros del servidor (Capa 3) del sistema_integrado.

Rutas SELF-CONTAINED dentro de sistema_integrado/ (no dependen del arbol viejo).
Topicos MQTT = unica fuente de verdad en Python (contrato en capa2-red/MQTT_SPEC.md).
"""

import os
from pathlib import Path


def _load_env(p: Path) -> None:
    """Carga un .env a os.environ. Usa python-dotenv si está instalado; si no, un
    parser mínimo (KEY=VALUE). Así funciona sin instalar nada, también en la VM con
    PEP 668 (externally-managed) donde 'pip install' global está bloqueado."""
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


_load_env(Path(__file__).resolve().parents[1] / ".env")      # sistema_integrado/.env

# --- Broker MQTT ---
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")        # broker local anonimo => vacio
MQTT_PASS = os.getenv("MQTT_PASS", "")

# --- Modo DISTRIBUIDO (camara en una laptop, gateway/servidor en VPS u otra) ---
# Si SERVER_UPLOAD_URL esta vacio => modo LOCAL (un solo equipo: la camara publica
#   la RUTA del clip por MQTT y el gateway lo lee de su propio disco).
# Si tiene valor (ej. http://mi-vps:8090/upload) => la camara SUBE el clip por HTTP
#   a ese endpoint del gateway, que lo recibe, guarda y analiza. Asi el servidor
#   puede vivir en otra maquina y no necesita acceso al disco de la camara.
SERVER_UPLOAD_URL = os.getenv("SERVER_UPLOAD_URL", "")
# Receptor HTTP de clips que levanta el gateway (lado servidor).
GATEWAY_HTTP_HOST = os.getenv("GATEWAY_HTTP_HOST", "0.0.0.0")
GATEWAY_HTTP_PORT = int(os.getenv("GATEWAY_HTTP_PORT", "8090"))

# --- Rutas (todo vive dentro de sistema_integrado/) ---
HERE = Path(__file__).resolve().parent                    # capa3-procesamiento-servidor/
ROOT = HERE.parent                                        # sistema_integrado/
DATOS = ROOT / "datos"
CLIPS_DIR = Path(os.getenv("CLIPS_DIR", DATOS / "clips"))
DB_PATH = Path(os.getenv("DB_PATH", DATOS / "alerts.db"))
NODES_JSON = HERE / "nodes.json"

# --- Topicos MQTT (devices/<id>/...) ---
TOPIC_ALERT_WILDCARD   = "devices/+/alert"
TOPIC_SENSORS_WILDCARD = "devices/+/sensors"
TOPIC_GPS_WILDCARD     = "devices/+/gps"
TOPIC_STATUS_WILDCARD  = "devices/+/status"
TOPIC_CLIP_WILDCARD    = "devices/+/camera/clip"


def topic_clip(device_id: str) -> str:
    """camara -> gateway: clip listo para analizar."""
    return f"devices/{device_id}/camera/clip"


def topic_detection(device_id: str) -> str:
    """gateway -> dashboard: metadatos de la alerta CONFIRMADA por el detector."""
    return f"devices/{device_id}/camera/detection"


def device_from_topic(topic: str) -> str:
    """Extrae '<id>' de 'devices/<id>/...'."""
    parts = topic.split("/")
    return parts[1] if len(parts) >= 2 else "desconocido"

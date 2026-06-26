"""
run.py — Punto de entrada del servidor de monitoreo de nodos.

Levanta, en el mismo proceso:
  1. MqttIngest        -> suscribe los topics reales del ESP32 y llena la BD.
  2. HeartbeatMonitor  -> job de liveness cada 5 min (ONLINE/OFFLINE/COMPROMISED).
  3. VideoIndexer      -> indexa datos/clips/ en la tabla videos.
  4. web.serve()       -> dashboard HTTP (bloquea el hilo principal).

Uso:
    cd capa3-procesamiento-servidor/monitor
    python3 run.py
Variables de entorno utiles (ver config.py): MQTT_HOST, MONITOR_HTTP_PORT,
MONITOR_DB_PATH, OFFLINE_AFTER_S, COMPROMISED_AFTER_S, HB_CHECK_INTERVAL_S.
"""

from __future__ import annotations

import config as cfg
import web
from db import MonitorDB
from mqtt_ingest import MqttIngest
from heartbeat_monitor import HeartbeatMonitor
from video_indexer import VideoIndexer


def on_detection(node, payload):
    """Hook del 'alert pipeline' (spec). El procesamiento pesado (grabar/analizar
    el video) lo hace gateway.py; aqui solo dejamos constancia. Amplia esto si
    quieres notificaciones (email/push) ante cada deteccion."""
    print(f"[PIPE] alerta de {node}: {payload.get('confidence')} "
          f"(el gateway grabara/analizara el clip)")


def main():
    print("=" * 64)
    print(" SERVIDOR DE MONITOREO DE NODOS IoT")
    print(f"   broker  : {cfg.MQTT_HOST}:{cfg.MQTT_PORT}")
    print(f"   base    : {cfg.DB_PATH}")
    print(f"   clips   : {cfg.CLIPS_DIR}")
    print(f"   web     : http://{cfg.HTTP_HOST}:{cfg.HTTP_PORT}")
    print("=" * 64)

    db = MonitorDB(cfg.DB_PATH)

    ingest = MqttIngest(db, on_detection=on_detection)
    ingest.start()

    hb = HeartbeatMonitor(db)
    hb.start()

    vidx = VideoIndexer(db)
    vidx.start()

    try:
        web.serve(db)                  # bloquea aqui
    except KeyboardInterrupt:
        print("\n[RUN] apagando...")
    finally:
        ingest.stop()
        hb.stop()
        vidx.stop()
        db.close()


if __name__ == "__main__":
    main()

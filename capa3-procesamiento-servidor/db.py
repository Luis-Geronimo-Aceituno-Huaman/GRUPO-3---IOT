"""
db.py — Almacenamiento de alertas CONFIRMADAS por el detector de movimiento.

Solo llegan aquí las alertas que pasaron la compuerta de visión (detector.py:
MOG2 + flujo óptico). Una alerta guardada = un disparo del nodo que el detector
confirmó visualmente.

Por defecto usa SQLite (cero configuración, ideal para demo local). El esquema
para PostgreSQL de producción está en ../database/schema.sql.

El shape de cada alerta coincide EXACTAMENTE con el que espera el dashboard
(js/data.js), para que el front no necesite cambios:

    { id, nodeId, nodeName, district, lat, lon, ts, confidence, source,
      detClass, detCount, videoUrl, status,
      sensors: { temp_c, turb_v, audio_rms, audio_peak, sats } }
"""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# Unica fuente de verdad para la ruta de la BD: config.py (datos/alerts.db).
# Evita que se cree una segunda BD por accidente en database/.
try:
    from config import DB_PATH as DEFAULT_DB
except ImportError:
    DEFAULT_DB = BASE_DIR.parent / "datos" / "alerts.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT    NOT NULL,
    node_name       TEXT,
    district        TEXT,
    lat             REAL,
    lon             REAL,
    ts              INTEGER NOT NULL,     -- epoch ms
    confidence      REAL,                 -- confianza del detector (max sobre el clip)
    source          TEXT DEFAULT 'camera',-- siempre 'camera' (confirmado por vision)
    det_class       TEXT,                 -- Mosquito | Mosquito Swarm
    det_count       INTEGER,              -- n total de detecciones de movimiento en el clip
    video_url       TEXT,                 -- ruta/URL del clip analizado
    status          TEXT DEFAULT 'nueva', -- nueva | atendida | falso-positivo | fumigacion
    temp_c          REAL,
    turb_v          REAL,
    audio_rms       REAL,
    audio_peak      INTEGER,
    sats            INTEGER
);
CREATE INDEX IF NOT EXISTS idx_alerts_node_ts ON alerts(node_id, ts DESC);
"""


class AlertStore:
    def __init__(self, db_path=DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def insert_alert(self, alert: dict) -> int:
        """Inserta una alerta confirmada. `alert` usa el shape del dashboard."""
        s = alert.get("sensors", {}) or {}
        cur = self.conn.execute(
            """INSERT INTO alerts
               (node_id, node_name, district, lat, lon, ts, confidence, source,
                det_class, det_count, video_url, status,
                temp_c, turb_v, audio_rms, audio_peak, sats)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                alert["nodeId"], alert.get("nodeName"), alert.get("district"),
                alert.get("lat"), alert.get("lon"), alert["ts"],
                alert.get("confidence"), alert.get("source", "camera"),
                alert.get("detClass"), alert.get("detCount"),
                alert.get("videoUrl"), alert.get("status", "nueva"),
                s.get("temp_c"), s.get("turb_v"), s.get("audio_rms"),
                s.get("audio_peak"), s.get("sats"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def all_alerts(self) -> list:
        """Devuelve todas las alertas en el shape que consume el dashboard."""
        rows = self.conn.execute("SELECT * FROM alerts ORDER BY ts DESC").fetchall()
        return [self._row_to_alert(r) for r in rows]

    @staticmethod
    def _row_to_alert(r) -> dict:
        return {
            "id": r["id"],
            "nodeId": r["node_id"],
            "nodeName": r["node_name"],
            "district": r["district"],
            "lat": r["lat"],
            "lon": r["lon"],
            "ts": r["ts"],
            "confidence": r["confidence"],
            "source": r["source"],
            "detClass": r["det_class"],
            "detCount": r["det_count"],
            "videoUrl": r["video_url"],
            "status": r["status"],
            "sensors": {
                "temp_c": r["temp_c"],
                "turb_v": r["turb_v"],
                "audio_rms": r["audio_rms"],
                "audio_peak": r["audio_peak"],
                "sats": r["sats"],
            },
        }

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    store = AlertStore()
    new_id = store.insert_alert({
        "nodeId": "esp32-01", "nodeName": "Nodo SJL-01",
        "district": "San Juan de Lurigancho", "lat": -11.962, "lon": -77.0,
        "ts": 1718900060000, "confidence": 0.91, "source": "camera",
        "detClass": "Mosquito", "detCount": 12,
        "videoUrl": "clips/esp32-01/demo.mp4", "status": "nueva",
        "sensors": {"temp_c": 27.4, "turb_v": 1.2, "audio_rms": 1500, "audio_peak": 48000, "sats": 8},
    })
    print(f"Insertada alerta id={new_id}")
    print(json.dumps(store.all_alerts(), ensure_ascii=False, indent=2))

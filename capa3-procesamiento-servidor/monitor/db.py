"""
db.py — Capa de persistencia del monitoreo de nodos, ahora sobre PostgreSQL.

Conserva EXACTAMENTE la interfaz pública de la versión SQLite (MonitorDB con los
mismos métodos y los mismos nombres de clave en los dicts que devuelve), para que
mqtt_ingest.py, heartbeat_monitor.py, video_indexer.py y serve.py no cambien:

  - las filas siguen saliendo con 'node_name' / 'timestamp' / 'received_at'
    (en la BD las columnas son node_id / ts, se renombran con alias al leer);
  - los timestamps siguen siendo strings ISO 8601 con zona horaria (los
    TIMESTAMPTZ de PG se convierten con .isoformat() al leer, y al escribir
    PG castea el string ISO que le pasamos).

El esquema vive en ../database/schema.sql (tablas nodes, detections, heartbeats,
videos, anomalies, node_status_history — con FKs e índices de verdad).
El pool de conexiones es el global de ../database.py (thread-safe).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# database.py vive en capa3/ (el padre). El monitor se importa con capa3/monitor/
# en sys.path (así lo hace serve.py), de modo que 'import database' no resolvería.
_CAPA3 = str(Path(__file__).resolve().parents[1])
if _CAPA3 not in sys.path:
    sys.path.insert(0, _CAPA3)

from database import get_pool     # noqa: E402


def now_iso() -> str:
    """Instante actual en ISO 8601 con offset de zona local (segundos)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def unix_to_iso(unix_s) -> str | None:
    """Convierte un epoch en segundos (el del ESP32 via SNTP) a ISO 8601 local.
    Devuelve None si el valor no es un reloj valido (0 = SNTP aun sin sincronizar)."""
    try:
        u = int(unix_s)
    except (TypeError, ValueError):
        return None
    if u < 1_700_000_000:        # < 2023-11 => reloj no sincronizado
        return None
    return datetime.fromtimestamp(u, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _iso(v) -> str | None:
    """datetime de PG -> string ISO (contrato viejo de esta capa)."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.astimezone().isoformat(timespec="seconds")
    return str(v)


STATUS_ONLINE = "ONLINE"
STATUS_OFFLINE = "OFFLINE"
STATUS_COMPROMISED = "COMPROMISED"
STATUS_UNKNOWN = "UNKNOWN"

# Columnas de nodes que update_node_fields puede tocar (whitelist: los kwargs
# vienen del código propio, pero nunca interpolamos nombres sin validar).
_NODE_COLS = {
    "node_name", "district", "lat", "lon", "alt", "status", "battery_pct",
    "chip_temp_c", "threshold", "uptime_s", "last_heartbeat", "last_seen",
    "last_reading", "is_simulated", "risk_level", "risk_score",
}

# Alias de lectura: la BD dice node_id/ts, el resto del código espera
# node_name/timestamp (contrato de la versión SQLite).
_NODE_SELECT = """
    SELECT node_id AS node_name, node_name AS display_name, district, lat, lon, alt,
           status, battery_pct, chip_temp_c, threshold, uptime_s,
           first_seen, last_seen, last_heartbeat, last_reading,
           is_simulated, risk_level, risk_score
    FROM nodes
"""

_NODE_TS_KEYS = ("first_seen", "last_seen", "last_heartbeat", "last_reading")


class MonitorDB:
    """Misma interfaz que la versión SQLite. `db_path` se ignora (compat)."""

    def __init__(self, db_path=None):
        self.pool = get_pool()

    # ---------------------------------------------------------------- nodes
    def register_node(self, node_name: str) -> bool:
        """Auto-registro: crea el nodo la PRIMERA vez que se le ve y actualiza
        last_seen siempre. Devuelve True si era un nodo nuevo (recien registrado)."""
        with self.pool.connection() as conn:
            row = conn.execute(
                """INSERT INTO nodes (node_id, status) VALUES (%s, 'UNKNOWN')
                   ON CONFLICT (node_id) DO UPDATE SET last_seen = now()
                   RETURNING (xmax = 0) AS inserted""",
                (node_name,),
            ).fetchone()
        return bool(row["inserted"])

    def update_node_fields(self, node_name: str, **fields):
        """Actualiza columnas sueltas de un nodo (battery_pct, chip_temp_c, ...)."""
        fields = {k: v for k, v in fields.items() if k in _NODE_COLS}
        if not fields:
            return
        cols = ", ".join(f"{k}=%s" for k in fields)
        vals = list(fields.values()) + [node_name]
        with self.pool.connection() as conn:
            conn.execute(f"UPDATE nodes SET {cols} WHERE node_id=%s", vals)

    def set_status(self, node_name: str, new_status: str):
        """Cambia el status del nodo y registra la transicion en
        node_status_history si de verdad cambio (rastro de caidas/regresos)."""
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT status FROM nodes WHERE node_id=%s FOR UPDATE", (node_name,)
            ).fetchone()
            old = row["status"] if row else None
            if old == new_status:
                return
            conn.execute(
                "UPDATE nodes SET status=%s WHERE node_id=%s", (new_status, node_name)
            )
            conn.execute(
                """INSERT INTO node_status_history (node_id, ts, old_status, new_status)
                   VALUES (%s, now(), %s, %s)""",
                (node_name, old, new_status),
            )

    def _node_row(self, r: dict) -> dict:
        for k in _NODE_TS_KEYS:
            r[k] = _iso(r.get(k))
        return r

    def all_nodes(self) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute(_NODE_SELECT + " ORDER BY node_id").fetchall()
        return [self._node_row(r) for r in rows]

    def get_node(self, node_name: str) -> dict | None:
        with self.pool.connection() as conn:
            r = conn.execute(
                _NODE_SELECT + " WHERE node_id=%s", (node_name,)
            ).fetchone()
        return self._node_row(r) if r else None

    def node_threshold(self, node_name: str):
        with self.pool.connection() as conn:
            r = conn.execute(
                "SELECT threshold FROM nodes WHERE node_id=%s", (node_name,)
            ).fetchone()
        return r["threshold"] if r else None

    # ------------------------------------------------------------ detections
    def insert_detection(self, node_name, timestamp, score, threshold_used, seq) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                """INSERT INTO detections (node_id, ts, score, threshold_used, seq)
                   VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                (node_name, timestamp, score, threshold_used, seq),
            ).fetchone()
        return row["id"]

    def detections(self, node_name, page=1, size=50) -> tuple[list[dict], int]:
        """Historial paginado de detecciones de un nodo. Devuelve (filas, total)."""
        off = max(0, (page - 1) * size)
        with self.pool.connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) c FROM detections WHERE node_id=%s", (node_name,)
            ).fetchone()["c"]
            rows = conn.execute(
                """SELECT id, node_id AS node_name, ts AS timestamp,
                          score, threshold_used, seq
                   FROM detections WHERE node_id=%s
                   ORDER BY ts DESC, id DESC LIMIT %s OFFSET %s""",
                (node_name, size, off),
            ).fetchall()
        for r in rows:
            r["timestamp"] = _iso(r["timestamp"])
        return rows, total

    def last_detection(self, node_name) -> dict | None:
        with self.pool.connection() as conn:
            r = conn.execute(
                """SELECT id, node_id AS node_name, ts AS timestamp,
                          score, threshold_used, seq
                   FROM detections WHERE node_id=%s
                   ORDER BY ts DESC, id DESC LIMIT 1""",
                (node_name,),
            ).fetchone()
        if r:
            r["timestamp"] = _iso(r["timestamp"])
        return r

    # ------------------------------------------------------------ heartbeats
    def insert_heartbeat(self, node_name, timestamp, battery_pct, chip_temp_c,
                         uptime_s, threshold, status) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                """INSERT INTO heartbeats
                   (node_id, ts, battery_pct, chip_temp_c, uptime_s, threshold, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (node_name, timestamp, battery_pct, chip_temp_c,
                 uptime_s, threshold, status),
            ).fetchone()
        return row["id"]

    def heartbeats(self, node_name, limit=200) -> list[dict]:
        """Ultimos N heartbeats en orden CRONOLOGICO (para graficar tendencias)."""
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT id, node_id AS node_name, ts AS timestamp,
                          battery_pct, chip_temp_c, uptime_s, threshold, status
                   FROM heartbeats WHERE node_id=%s
                   ORDER BY ts DESC, id DESC LIMIT %s""",
                (node_name, limit),
            ).fetchall()
        for r in rows:
            r["timestamp"] = _iso(r["timestamp"])
        return list(reversed(rows))

    # ------------------------------------------------------------ videos
    def insert_video(self, node_name, received_at, file_path, file_size_kb) -> int | None:
        """Inserta un video; ignora si ya existe (file_path es UNIQUE)."""
        with self.pool.connection() as conn:
            row = conn.execute(
                """INSERT INTO videos (node_id, received_at, file_path, file_size_kb)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (file_path) DO NOTHING RETURNING id""",
                (node_name, received_at, file_path, file_size_kb),
            ).fetchone()
        return row["id"] if row else None

    def video_exists(self, file_path) -> bool:
        with self.pool.connection() as conn:
            r = conn.execute(
                "SELECT 1 FROM videos WHERE file_path=%s", (file_path,)
            ).fetchone()
        return r is not None

    def delete_video(self, video_id) -> str | None:
        """Borra un video por id. Devuelve su file_path (para borrar el archivo
        del disco) o None si no existia."""
        with self.pool.connection() as conn:
            r = conn.execute(
                "DELETE FROM videos WHERE id=%s RETURNING file_path", (video_id,)
            ).fetchone()
        return r["file_path"] if r else None

    def videos(self, node_name=None, order="received_at", desc=True) -> list[dict]:
        order = order if order in ("received_at", "node_name", "file_size_kb") else "received_at"
        col = {"received_at": "received_at", "node_name": "node_id",
               "file_size_kb": "file_size_kb"}[order]
        direction = "DESC" if desc else "ASC"
        q = """SELECT id, node_id AS node_name, received_at, file_path, file_size_kb
               FROM videos"""
        args = []
        if node_name:
            q += " WHERE node_id=%s"
            args.append(node_name)
        q += f" ORDER BY {col} {direction}"
        with self.pool.connection() as conn:
            rows = conn.execute(q, args).fetchall()
        for r in rows:
            r["received_at"] = _iso(r["received_at"])
        return rows

    # ------------------------------------------------------------ anomalies
    def insert_anomaly(self, node_name, timestamp, type_, detail) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                """INSERT INTO anomalies (node_id, ts, type, detail)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (node_name, timestamp, type_, detail),
            ).fetchone()
        return row["id"]

    def anomalies(self, node_name, limit=100) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT id, node_id AS node_name, ts AS timestamp, type, detail
                   FROM anomalies WHERE node_id=%s
                   ORDER BY ts DESC, id DESC LIMIT %s""",
                (node_name, limit),
            ).fetchall()
        for r in rows:
            r["timestamp"] = _iso(r["timestamp"])
        return rows

    # ------------------------------------------------------ status_history
    def status_history(self, node_name, limit=50) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT id, node_id AS node_name, ts AS timestamp,
                          old_status, new_status
                   FROM node_status_history WHERE node_id=%s
                   ORDER BY ts DESC, id DESC LIMIT %s""",
                (node_name, limit),
            ).fetchall()
        for r in rows:
            r["timestamp"] = _iso(r["timestamp"])
        return rows

    # ------------------------------------------------------ lecturas de sensores
    def insert_reading(self, node_name, reading: dict):
        """Guarda una lectura del topic devices/+/sensors (histórico para el motor
        de riesgo). Los campos conocidos van a columnas; el resto a extra JSONB.
        Aditivo: el ESP32 real solo manda turb_raw/turb_v/temp_c."""
        import json as _json
        known = {k: reading.get(k) for k in
                 ("temp_c", "turb_raw", "turb_v", "humedad", "ph",
                  "nivel_agua", "audio_conf")}
        extra = {k: v for k, v in reading.items()
                 if k not in known and not k.startswith("_")}
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO sensor_readings
                   (node_id, temp_c, turb_raw, turb_v, humedad, ph, nivel_agua,
                    audio_conf, extra)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (node_name, known["temp_c"], known["turb_raw"], known["turb_v"],
                 known["humedad"], known["ph"], known["nivel_agua"],
                 known["audio_conf"], _json.dumps(extra) if extra else None),
            )
            conn.execute(
                "UPDATE nodes SET last_reading = now() WHERE node_id=%s",
                (node_name,),
            )

    def last_reading(self, node_name) -> dict | None:
        """Última lectura de sensores del nodo (para el motor de riesgo)."""
        with self.pool.connection() as conn:
            r = conn.execute(
                """SELECT node_id AS node_name, ts, temp_c, turb_raw, turb_v,
                          humedad, ph, nivel_agua, audio_conf, extra
                   FROM sensor_readings WHERE node_id=%s
                   ORDER BY ts DESC, id DESC LIMIT 1""",
                (node_name,),
            ).fetchone()
        if r:
            r["ts"] = _iso(r["ts"])
        return r

    def close(self):
        pass    # el pool es global y compartido; lo cierra database.close_pool()


if __name__ == "__main__":
    # Smoke test minimo contra el PG real.
    import json
    db = MonitorDB()
    print("nuevo:", db.register_node("esp32-smoke"))
    print("repetido:", db.register_node("esp32-smoke"))
    db.insert_heartbeat("esp32-smoke", now_iso(), -1, 41.5, 123, 0.62, "alive")
    db.set_status("esp32-smoke", STATUS_ONLINE)
    db.insert_detection("esp32-smoke", now_iso(), 0.88, 0.62, 7)
    db.insert_reading("esp32-smoke", {"temp_c": 26.5, "turb_v": 1.1,
                                      "humedad": 70, "custom": 42})
    print(json.dumps(db.get_node("esp32-smoke"), indent=2, ensure_ascii=False))
    print(json.dumps(db.last_reading("esp32-smoke"), indent=2, ensure_ascii=False))

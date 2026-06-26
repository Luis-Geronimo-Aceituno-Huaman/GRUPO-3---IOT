"""
db.py — Capa de persistencia del servidor de monitoreo (SQLite).

Implementa el esquema del spec ("DATABASE SCHEMA") + una tabla extra
status_history para cumplir "Store status history so you can see when a node went
offline and came back".

Tablas:
  nodes        node_name PK, first_seen, last_seen, last_heartbeat, status,
               battery_pct, chip_temp_c, threshold, uptime_s
  detections   id, node_name, timestamp, score, threshold_used, seq
  heartbeats   id, node_name, timestamp, battery_pct, chip_temp_c, uptime_s,
               threshold, status
  videos       id, node_name, received_at, file_path, file_size_kb
  anomalies    id, node_name, timestamp, type, detail
  status_history id, node_name, timestamp, old_status, new_status

Todos los timestamps se guardan como TEXTO ISO 8601 CON zona horaria (spec:
"All timestamps stored and displayed in ISO 8601 format with timezone").
La BD es de uso concurrente (MQTT, job de heartbeat, HTTP), asi que toda
escritura/lectura pasa por un unico Lock y connect(check_same_thread=False).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


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


STATUS_ONLINE = "ONLINE"
STATUS_OFFLINE = "OFFLINE"
STATUS_COMPROMISED = "COMPROMISED"
STATUS_UNKNOWN = "UNKNOWN"

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_name      TEXT PRIMARY KEY,
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    last_heartbeat TEXT,
    status         TEXT NOT NULL DEFAULT 'UNKNOWN',
    battery_pct    INTEGER,
    chip_temp_c    REAL,
    threshold      REAL,
    uptime_s       INTEGER
);

CREATE TABLE IF NOT EXISTS detections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    node_name      TEXT NOT NULL REFERENCES nodes(node_name),
    timestamp      TEXT NOT NULL,
    score          REAL,
    threshold_used REAL,
    seq            INTEGER
);
CREATE INDEX IF NOT EXISTS idx_det_node_ts ON detections(node_name, timestamp DESC);

CREATE TABLE IF NOT EXISTS heartbeats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_name   TEXT NOT NULL REFERENCES nodes(node_name),
    timestamp   TEXT NOT NULL,
    battery_pct INTEGER,
    chip_temp_c REAL,
    uptime_s    INTEGER,
    threshold   REAL,
    status      TEXT
);
CREATE INDEX IF NOT EXISTS idx_hb_node_ts ON heartbeats(node_name, timestamp DESC);

CREATE TABLE IF NOT EXISTS videos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    node_name    TEXT NOT NULL REFERENCES nodes(node_name),
    received_at  TEXT NOT NULL,
    file_path    TEXT NOT NULL UNIQUE,
    file_size_kb INTEGER
);
CREATE INDEX IF NOT EXISTS idx_vid_node ON videos(node_name, received_at DESC);

CREATE TABLE IF NOT EXISTS anomalies (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    node_name TEXT NOT NULL REFERENCES nodes(node_name),
    timestamp TEXT NOT NULL,
    type      TEXT,
    detail    TEXT
);
CREATE INDEX IF NOT EXISTS idx_anom_node_ts ON anomalies(node_name, timestamp DESC);

CREATE TABLE IF NOT EXISTS status_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    node_name  TEXT NOT NULL REFERENCES nodes(node_name),
    timestamp  TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sh_node_ts ON status_history(node_name, timestamp DESC);
"""


class MonitorDB:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")   # mejor concurrencia lectura/escritura
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------------------------------------------------------------- nodes
    def register_node(self, node_name: str) -> bool:
        """Auto-registro: crea el nodo la PRIMERA vez que se le ve y actualiza
        last_seen siempre. Devuelve True si era un nodo nuevo (recien registrado)."""
        ts = now_iso()
        with self._lock:
            exists = self.conn.execute(
                "SELECT 1 FROM nodes WHERE node_name=?", (node_name,)
            ).fetchone() is not None
            if exists:
                self.conn.execute(
                    "UPDATE nodes SET last_seen=? WHERE node_name=?", (ts, node_name)
                )
            else:
                self.conn.execute(
                    """INSERT INTO nodes (node_name, first_seen, last_seen, status)
                       VALUES (?,?,?, 'UNKNOWN')""",
                    (node_name, ts, ts),
                )
            self.conn.commit()
        return not exists

    def update_node_fields(self, node_name: str, **fields):
        """Actualiza columnas sueltas de un nodo (battery_pct, chip_temp_c, ...)."""
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [node_name]
        with self._lock:
            self.conn.execute(f"UPDATE nodes SET {cols} WHERE node_name=?", vals)
            self.conn.commit()

    def set_status(self, node_name: str, new_status: str):
        """Cambia el status del nodo y registra la transicion en status_history si
        de verdad cambio. Asi queda el rastro de cuando cayo y cuando volvio."""
        with self._lock:
            row = self.conn.execute(
                "SELECT status FROM nodes WHERE node_name=?", (node_name,)
            ).fetchone()
            old = row["status"] if row else None
            if old == new_status:
                return
            self.conn.execute(
                "UPDATE nodes SET status=? WHERE node_name=?", (new_status, node_name)
            )
            self.conn.execute(
                """INSERT INTO status_history (node_name, timestamp, old_status, new_status)
                   VALUES (?,?,?,?)""",
                (node_name, now_iso(), old, new_status),
            )
            self.conn.commit()

    def all_nodes(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM nodes ORDER BY node_name"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_node(self, node_name: str) -> dict | None:
        with self._lock:
            r = self.conn.execute(
                "SELECT * FROM nodes WHERE node_name=?", (node_name,)
            ).fetchone()
        return dict(r) if r else None

    def node_threshold(self, node_name: str):
        n = self.get_node(node_name)
        return n["threshold"] if n else None

    # ------------------------------------------------------------ detections
    def insert_detection(self, node_name, timestamp, score, threshold_used, seq) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO detections (node_name, timestamp, score, threshold_used, seq)
                   VALUES (?,?,?,?,?)""",
                (node_name, timestamp, score, threshold_used, seq),
            )
            self.conn.commit()
            return cur.lastrowid

    def detections(self, node_name, page=1, size=50) -> tuple[list[dict], int]:
        """Historial paginado de detecciones de un nodo. Devuelve (filas, total)."""
        off = max(0, (page - 1) * size)
        with self._lock:
            total = self.conn.execute(
                "SELECT COUNT(*) c FROM detections WHERE node_name=?", (node_name,)
            ).fetchone()["c"]
            rows = self.conn.execute(
                """SELECT * FROM detections WHERE node_name=?
                   ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?""",
                (node_name, size, off),
            ).fetchall()
        return [dict(r) for r in rows], total

    def last_detection(self, node_name) -> dict | None:
        with self._lock:
            r = self.conn.execute(
                """SELECT * FROM detections WHERE node_name=?
                   ORDER BY timestamp DESC, id DESC LIMIT 1""",
                (node_name,),
            ).fetchone()
        return dict(r) if r else None

    # ------------------------------------------------------------ heartbeats
    def insert_heartbeat(self, node_name, timestamp, battery_pct, chip_temp_c,
                         uptime_s, threshold, status) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO heartbeats
                   (node_name, timestamp, battery_pct, chip_temp_c, uptime_s, threshold, status)
                   VALUES (?,?,?,?,?,?,?)""",
                (node_name, timestamp, battery_pct, chip_temp_c, uptime_s, threshold, status),
            )
            self.conn.commit()
            return cur.lastrowid

    def heartbeats(self, node_name, limit=200) -> list[dict]:
        """Ultimos N heartbeats en orden CRONOLOGICO (para graficar tendencias)."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT * FROM heartbeats WHERE node_name=?
                   ORDER BY timestamp DESC, id DESC LIMIT ?""",
                (node_name, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ------------------------------------------------------------ videos
    def insert_video(self, node_name, received_at, file_path, file_size_kb) -> int | None:
        """Inserta un video; ignora si ya existe (file_path es UNIQUE)."""
        with self._lock:
            cur = self.conn.execute(
                """INSERT OR IGNORE INTO videos (node_name, received_at, file_path, file_size_kb)
                   VALUES (?,?,?,?)""",
                (node_name, received_at, file_path, file_size_kb),
            )
            self.conn.commit()
            return cur.lastrowid if cur.rowcount else None

    def video_exists(self, file_path) -> bool:
        with self._lock:
            r = self.conn.execute(
                "SELECT 1 FROM videos WHERE file_path=?", (file_path,)
            ).fetchone()
        return r is not None

    def delete_video(self, video_id) -> str | None:
        """Borra un video por id. Devuelve su file_path (para borrar el archivo
        del disco) o None si no existia."""
        with self._lock:
            r = self.conn.execute(
                "SELECT file_path FROM videos WHERE id=?", (video_id,)
            ).fetchone()
            if r is None:
                return None
            self.conn.execute("DELETE FROM videos WHERE id=?", (video_id,))
            self.conn.commit()
            return r["file_path"]

    def videos(self, node_name=None, order="received_at", desc=True) -> list[dict]:
        order = order if order in ("received_at", "node_name", "file_size_kb") else "received_at"
        direction = "DESC" if desc else "ASC"
        q = f"SELECT * FROM videos"
        args = []
        if node_name:
            q += " WHERE node_name=?"
            args.append(node_name)
        q += f" ORDER BY {order} {direction}"
        with self._lock:
            rows = self.conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ anomalies
    def insert_anomaly(self, node_name, timestamp, type_, detail) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO anomalies (node_name, timestamp, type, detail)
                   VALUES (?,?,?,?)""",
                (node_name, timestamp, type_, detail),
            )
            self.conn.commit()
            return cur.lastrowid

    def anomalies(self, node_name, limit=100) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT * FROM anomalies WHERE node_name=?
                   ORDER BY timestamp DESC, id DESC LIMIT ?""",
                (node_name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ status_history
    def status_history(self, node_name, limit=50) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT * FROM status_history WHERE node_name=?
                   ORDER BY timestamp DESC, id DESC LIMIT ?""",
                (node_name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        with self._lock:
            self.conn.close()


if __name__ == "__main__":
    # Smoke test minimo del esquema.
    import json
    db = MonitorDB(":memory:")
    print("nuevo:", db.register_node("esp32-01"))
    print("repetido:", db.register_node("esp32-01"))
    db.insert_heartbeat("esp32-01", now_iso(), -1, 41.5, 123, 0.62, "alive")
    db.set_status("esp32-01", STATUS_ONLINE)
    db.insert_detection("esp32-01", now_iso(), 0.88, 0.62, 7)
    print(json.dumps(db.all_nodes(), indent=2, ensure_ascii=False))

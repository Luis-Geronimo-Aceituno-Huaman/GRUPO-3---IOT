"""
db.py — Almacenamiento de alertas CONFIRMADAS por el detector de movimiento.

Solo llegan aquí las alertas que pasaron la compuerta de visión (detector.py:
MOG2 + flujo óptico). Una alerta guardada = un disparo del nodo que el detector
confirmó visualmente.

Desde la ampliación, la persistencia vive en PostgreSQL (database/schema.sql,
pool compartido en database.py). Esta clase conserva EXACTAMENTE la interfaz que
usaban gateway.py y serve.py con SQLite (insert_alert / all_alerts) y añade el
workflow de estados con auditoría (update_status / history / alerts con filtros).

El shape de cada alerta coincide con el que espera el dashboard (js/data.js):

    { id, nodeId, nodeName, district, lat, lon, ts, confidence, source,
      detClass, detCount, videoUrl, status, riskLevel,
      sensors: { temp_c, turb_v, humedad, ph, nivel_agua,
                 audio_rms, audio_peak, sats } }

Estados del workflow (schema CHECK):
    pendiente | en-revision | respondida | resuelta | falsa-alarma | descartada
Los valores viejos de SQLite se mapean al insertar/migrar (nueva→pendiente, ...).
"""

from __future__ import annotations

import json

from database import get_pool

# Mapeo de estados del PoC viejo → workflow nuevo (retrocompat con callers viejos).
LEGACY_STATUS = {
    "nueva": "pendiente",
    "atendida": "respondida",
    "falso-positivo": "falsa-alarma",
    "fumigacion": "en-revision",
}

VALID_STATUSES = {"pendiente", "en-revision", "respondida",
                  "resuelta", "falsa-alarma", "descartada"}

# Estados que NO se muestran en el mapa (req.5) pero se conservan para auditoría.
HIDDEN_ON_MAP = ("falsa-alarma", "descartada")

# Estados terminales: no se permite salir de ellos.
TERMINAL_STATUSES = {"descartada"}


def _norm_status(status: str | None) -> str:
    s = (status or "pendiente").strip()
    s = LEGACY_STATUS.get(s, s)
    return s if s in VALID_STATUSES else "pendiente"


class AlertStore:
    """Misma interfaz pública que la versión SQLite; ahora sobre el pool de PG.
    `db_path` se ignora (queda por compatibilidad con callers viejos)."""

    def __init__(self, db_path=None):
        self.pool = get_pool()

    # ------------------------------------------------------------- escritura
    def insert_alert(self, alert: dict) -> int:
        """Inserta una alerta confirmada. `alert` usa el shape del dashboard.
        Crea el nodo si no existe (FK) y acepta sensores extra aditivos
        (humedad/ph/nivel_agua — el ESP32 real no los manda, el simulador sí)."""
        s = alert.get("sensors", {}) or {}
        status = _norm_status(alert.get("status"))
        node_id = alert["nodeId"]
        with self.pool.connection() as conn:
            # El nodo debe existir (integridad referencial). Si es la primera vez
            # que se le ve, se auto-registra con lo que traiga la alerta.
            conn.execute(
                """INSERT INTO nodes (node_id, node_name, district, lat, lon)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (node_id) DO UPDATE SET last_seen = now()""",
                (node_id, alert.get("nodeName"), alert.get("district"),
                 alert.get("lat"), alert.get("lon")),
            )
            row = conn.execute(
                """INSERT INTO alerts
                   (node_id, node_name, district, lat, lon, ts, confidence, source,
                    det_class, det_count, video_url, status, risk_level,
                    temp_c, turb_v, humedad, ph, nivel_agua,
                    audio_rms, audio_peak, sats, is_synthetic)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           %s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (
                    node_id, alert.get("nodeName"), alert.get("district"),
                    alert.get("lat"), alert.get("lon"), alert["ts"],
                    alert.get("confidence"), alert.get("source", "camera"),
                    alert.get("detClass"), alert.get("detCount"),
                    alert.get("videoUrl"), status, alert.get("riskLevel"),
                    s.get("temp_c"), s.get("turb_v"), s.get("humedad"),
                    s.get("ph"), s.get("nivel_agua"),
                    s.get("audio_rms"), s.get("audio_peak"), s.get("sats"),
                    bool(alert.get("isSynthetic", False)),
                ),
            ).fetchone()
            alert_id = row["id"]
            # Primera fila del historial: el nacimiento de la alerta.
            conn.execute(
                """INSERT INTO alert_history (alert_id, old_status, new_status, comment)
                   VALUES (%s, NULL, %s, %s)""",
                (alert_id, status,
                 "creada por el detector" if not alert.get("isSynthetic")
                 else "creada por el generador sintético"),
            )
        return alert_id

    def update_status(self, alert_id: int, new_status: str, *,
                      user_id: int | None = None, username: str | None = None,
                      comment: str | None = None) -> dict:
        """Transición de estado con auditoría, en UNA transacción.
        Devuelve {'ok': True, 'old': ..., 'new': ...} o {'ok': False, 'error': ...}."""
        new_status = _norm_status(new_status)
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT status FROM alerts WHERE id=%s FOR UPDATE", (alert_id,)
            ).fetchone()
            if row is None:
                return {"ok": False, "error": "la alerta no existe"}
            old = row["status"]
            if old in TERMINAL_STATUSES:
                return {"ok": False,
                        "error": f"la alerta está '{old}' (estado final, no se puede cambiar)"}
            if old == new_status:
                return {"ok": False, "error": f"la alerta ya está en '{new_status}'"}
            conn.execute(
                """UPDATE alerts
                   SET status=%s,
                       responded_at = COALESCE(responded_at, now()),
                       responded_by = COALESCE(responded_by, %s)
                   WHERE id=%s""",
                (new_status, user_id, alert_id),
            )
            conn.execute(
                """INSERT INTO alert_history
                   (alert_id, old_status, new_status, user_id, username, comment)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (alert_id, old, new_status, user_id, username, comment),
            )
            conn.execute(
                """INSERT INTO events (user_id, username, action, entity, entity_id, detail)
                   VALUES (%s,%s,'alert.status','alert',%s,%s)""",
                (user_id, username, str(alert_id),
                 json.dumps({"old": old, "new": new_status, "comment": comment})),
            )
        return {"ok": True, "old": old, "new": new_status}

    def delete_alert(self, alert_id: int, *, user_id: int | None = None,
                     username: str | None = None,
                     comment: str | None = None) -> dict:
        """Falsa alarma: ELIMINA la alerta de la BD de forma definitiva (su
        historial cae por FK ON DELETE CASCADE). Solo queda constancia del
        borrado en `events` (auditoría: quién, cuándo, qué alerta era)."""
        with self.pool.connection() as conn:
            row = conn.execute(
                "DELETE FROM alerts WHERE id=%s RETURNING status, node_id, ts",
                (alert_id,),
            ).fetchone()
            if row is None:
                return {"ok": False, "error": "la alerta no existe"}
            conn.execute(
                """INSERT INTO events (user_id, username, action, entity, entity_id, detail)
                   VALUES (%s,%s,'alert.delete','alert',%s,%s)""",
                (user_id, username, str(alert_id),
                 json.dumps({"motivo": "falsa alarma", "old_status": row["status"],
                             "node": row["node_id"], "ts": row["ts"],
                             "comment": comment})),
            )
        return {"ok": True, "old": row["status"]}

    # -------------------------------------------------------------- lectura
    def all_alerts(self) -> list:
        """Todas las alertas en el shape que consume el dashboard (compat)."""
        return self.alerts()

    def alerts(self, status: str | None = None, node: str | None = None,
               include_synthetic: bool = True, for_map: bool = False) -> list:
        """Alertas con filtros. `for_map=True` excluye falsas/descartadas (req.5)."""
        q = "SELECT * FROM alerts WHERE TRUE"
        args: list = []
        if status:
            q += " AND status=%s"
            args.append(_norm_status(status))
        if node:
            q += " AND node_id=%s"
            args.append(node)
        if not include_synthetic:
            q += " AND NOT is_synthetic"
        if for_map:
            q += " AND NOT (status = ANY(%s))"
            args.append(list(HIDDEN_ON_MAP))
        q += " ORDER BY ts DESC"
        with self.pool.connection() as conn:
            rows = conn.execute(q, args).fetchall()
        return [self._row_to_alert(r) for r in rows]

    def get_alert(self, alert_id: int) -> dict | None:
        with self.pool.connection() as conn:
            r = conn.execute("SELECT * FROM alerts WHERE id=%s", (alert_id,)).fetchone()
        return self._row_to_alert(r) if r else None

    def history(self, alert_id: int) -> list[dict]:
        """Historial de transiciones (auditoría), más reciente primero."""
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT id, ts, old_status, new_status, username, comment
                   FROM alert_history WHERE alert_id=%s ORDER BY ts DESC, id DESC""",
                (alert_id,),
            ).fetchall()
        for r in rows:
            r["ts"] = r["ts"].isoformat(timespec="seconds")
        return rows

    def counts_by_node(self) -> dict[str, dict]:
        """{node_id: {'total': n, 'visibles': n}} — para enriquecer /api/nodes."""
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT node_id,
                          COUNT(*) AS total,
                          COUNT(*) FILTER (WHERE NOT (status = ANY(%s))) AS visibles
                   FROM alerts GROUP BY node_id""",
                (list(HIDDEN_ON_MAP),),
            ).fetchall()
        return {r["node_id"]: {"total": r["total"], "visibles": r["visibles"]}
                for r in rows}

    @staticmethod
    def _row_to_alert(r: dict) -> dict:
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
            "riskLevel": r["risk_level"],
            "isSynthetic": r["is_synthetic"],
            "createdAt": r["created_at"].isoformat(timespec="seconds") if r["created_at"] else None,
            "respondedAt": r["responded_at"].isoformat(timespec="seconds") if r["responded_at"] else None,
            "sensors": {
                "temp_c": r["temp_c"],
                "turb_v": r["turb_v"],
                "humedad": r["humedad"],
                "ph": r["ph"],
                "nivel_agua": r["nivel_agua"],
                "audio_rms": r["audio_rms"],
                "audio_peak": r["audio_peak"],
                "sats": r["sats"],
            },
        }

    def close(self):
        pass    # el pool es global y compartido; lo cierra database.close_pool()


if __name__ == "__main__":
    store = AlertStore()
    new_id = store.insert_alert({
        "nodeId": "esp32-test", "nodeName": "Nodo de prueba",
        "district": "Prueba", "lat": -11.962, "lon": -77.0,
        "ts": 1718900060000, "confidence": 0.91, "source": "camera",
        "detClass": "Mosquito", "detCount": 12,
        "videoUrl": "clips/esp32-test/demo.webm", "status": "nueva",   # → pendiente
        "sensors": {"temp_c": 27.4, "turb_v": 1.2, "audio_rms": 1500,
                    "audio_peak": 48000, "sats": 8},
    })
    print(f"Insertada alerta id={new_id}")
    print(json.dumps(store.get_alert(new_id), ensure_ascii=False, indent=2, default=str))
    print(store.update_status(new_id, "en-revision", username="smoke-test",
                              comment="prueba de transición"))
    print(json.dumps(store.history(new_id), ensure_ascii=False, indent=2, default=str))

"""
migrate_sqlite_to_pg.py — Migración de las 2 SQLite del PoC a PostgreSQL.

Idempotente: se puede re-ejecutar sin duplicar nada (ON CONFLICT / dedupe por
claves naturales). Qué hace, en orden:

  1. Re-aplica database/schema.sql (CREATE IF NOT EXISTS).
  2. nodes        <- nodes.json (semilla: nombre/distrito/lat/lon)
                     + datos/monitor.db tabla nodes (estado vivo)
                     + node_sensors del hardware real del ESP32.
  3. alerts       <- datos/alerts.db (mapea estados viejos -> workflow nuevo,
                     conserva ids y ts epoch-ms, crea la fila inicial de
                     alert_history para cada alerta migrada).
  4. detections/heartbeats/videos/anomalies/status_history <- datos/monitor.db.
  5. Semillas: usuario admin (ADMIN_INIT_PASS), detector_params (los valores
     actuales de detector.py -> mismo comportamiento tras migrar), system_config
     (pesos/umbrales del motor de riesgo).

Uso:
    python migrate_sqlite_to_pg.py                       # rutas por defecto
    python migrate_sqlite_to_pg.py --alerts X --monitor Y
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent            # capa3/database/
CAPA3 = HERE.parent                               # capa3/
ROOT = CAPA3.parent                               # raíz del proyecto
sys.path.insert(0, str(CAPA3))

from database import get_pool, apply_schema       # noqa: E402

# Mapeo de estados del PoC -> workflow nuevo (igual que db.py LEGACY_STATUS).
LEGACY_STATUS = {
    "nueva": "pendiente",
    "atendida": "respondida",
    "falso-positivo": "falsa-alarma",
    "fumigacion": "en-revision",
}

# Sensores físicos del nodo ESP32 real (capa1: DS18B20 + turbidez ADC + GPS + mic).
REAL_NODE_SENSORS = ("temp_ds18b20", "turbidez", "gps", "audio")

# ─── Semilla detector_params: LOS VALORES ACTUALES de detector.py (líneas 34-62)
# más los parámetros nuevos de la Fase 4 con defaults neutros (features apagadas)
# para que migrar NO cambie el comportamiento del detector.
#      key                  valor    min    max    descripcion
DETECTOR_PARAMS = [
    ("umbral_mosquito",        1,     1,     50,   "mínimo de objetos para 'mosquito'"),
    ("umbral_enjambre",       10,     2,    100,   "mínimo de objetos para 'enjambre'"),
    ("area_min",              10,     1,    500,   "área mínima de blob (px²)"),
    ("area_max",             800,    50,  10000,   "área máxima de blob (px²)"),
    ("aspect_min",           0.2,  0.01,      1,   "ratio w/h mínimo"),
    ("aspect_max",           5.0,     1,     20,   "ratio w/h máximo"),
    ("max_frame_ratio",     0.02, 0.001,    0.5,   "blob no puede superar este % del frame"),
    ("circularidad_min",     0.1,     0,      1,   "circularidad mínima del contorno"),
    ("persistencia_min",       8,     1,     60,   "frames consecutivos para confirmar"),
    ("dist_max",              40,     5,    300,   "px máx de movimiento entre frames (matching)"),
    ("max_movimiento_total",0.05, 0.005,    0.9,   "si el movimiento supera este % del frame -> objeto grande"),
    ("mov_min",               12,     0,    200,   "desplazamiento mínimo total (px) para confirmar"),
    ("flow_min",             0.6,     0,     10,   "magnitud media mínima de flujo óptico (px/frame)"),
    ("ema_alpha",           0.08,  0.01,      1,   "suavizado EMA de la confianza"),
    ("conf_on",             0.70,     0,      1,   "umbral de encendido de alerta (histéresis)"),
    ("conf_off",            0.30,     0,      1,   "umbral de apagado de alerta (histéresis)"),
    ("conf_min_alerta",     0.70,     0,      1,   "confianza pico mínima para ACEPTAR la alerta"),
    ("mask_threshold",       200,     1,    255,   "umbral binario fijo de la máscara MOG2"),
    ("mog2_history",         500,    50,   2000,   "ventana temporal del sustractor de fondo"),
    ("mog2_var_threshold",    50,     4,    200,   "sensibilidad al cambio del MOG2"),
    ("proc_w",               640,   160,   1920,   "ancho de procesamiento"),
    ("proc_h",               480,   120,   1080,   "alto de procesamiento"),
    # ── Fase 4 (mejoras; apagadas/neutras por defecto) ──
    ("use_bilateral",          0,     0,      1,   "1 = denoise bilateral en vez de blur gaussiano"),
    ("clahe_enabled",          0,     0,      1,   "1 = ecualización CLAHE (costo CPU extra)"),
    ("noise_percentile",       0,     0,   99.9,   "umbral adaptativo por percentil de la máscara (0 = usar mask_threshold fijo)"),
    ("vel_min_px_s",           0,     0,   2000,   "velocidad mínima del track (px/s; 0 = sin filtro)"),
    ("vel_max_px_s",           0,     0,   5000,   "velocidad máxima del track (px/s; 0 = sin filtro)"),
    ("trayectoria_min_puntos", 0,     0,     60,   "puntos mínimos de trayectoria (0 = sin filtro)"),
    ("flow_downscale",         1,     1,      4,   "divisor de resolución para el flujo óptico (ARM)"),
]

# Config del motor de riesgo (system_config, JSONB).
RISK_CONFIG = {
    "pesos": {"temp": 0.30, "turbidez": 0.25, "humedad": 0.20,
              "ph": 0.05, "nivel_agua": 0.05, "actividad": 0.25},
    "umbrales_nivel": {"medio": 25, "alto": 50, "critico": 75},
    "temp_optima": [25, 30],       # °C ideales para Aedes aegypti
    "temp_rango": [15, 40],        # fuera de esto, factor 0
    "humedad_optima": [60, 80],    # % HR ideal
    "humedad_rango": [30, 100],
    "turb_v_baja": 0.5,            # voltios: por debajo, agua clara (riesgo bajo)
    "turb_v_alta": 2.0,            # por encima, agua muy turbia (riesgo alto)
    "turb_invertido": False,       # true si el sensor da MENOS voltaje = más turbio
    "ph_optimo": [6.5, 8.5],       # rango de cría viable
    "actividad_ventana_h": 72,     # ventana de alertas recientes
    "actividad_max": 10,           # nº de alertas que satura el factor a 1.0
}


def dict_rows(db_path: Path, query: str) -> list[dict]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(query).fetchall()]
    except sqlite3.OperationalError as e:
        print(f"  [WARN] {db_path.name}: {e}")
        return []
    finally:
        con.close()


def migrate_nodes(conn, monitor_db: Path, nodes_json: Path):
    """nodes.json (semilla estática) + monitor.db.nodes (estado vivo)."""
    seeds = {}
    if nodes_json.exists():
        seeds = json.loads(nodes_json.read_text(encoding="utf-8"))
    live = {r["node_name"]: r for r in
            (dict_rows(monitor_db, "SELECT * FROM nodes") if monitor_db.exists() else [])}

    # Solo migramos nodos REALES: los que el sistema ha visto (monitor.db) más
    # los del catálogo estático que coincidan. Los 7 nodos ficticios de nodes.json
    # que nunca reportaron nada NO se migran (req.7: nada inventado en el mapa).
    node_ids = set(live)
    count = 0
    for nid in sorted(node_ids):
        seed = seeds.get(nid, {})
        lv = live.get(nid, {})
        conn.execute(
            """INSERT INTO nodes (node_id, node_name, district, lat, lon, status,
                                  battery_pct, chip_temp_c, threshold, uptime_s,
                                  first_seen, last_seen, last_heartbeat)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       COALESCE(%s::timestamptz, now()),
                       COALESCE(%s::timestamptz, now()),
                       %s::timestamptz)
               ON CONFLICT (node_id) DO UPDATE SET
                   node_name = COALESCE(EXCLUDED.node_name, nodes.node_name),
                   district  = COALESCE(EXCLUDED.district, nodes.district),
                   lat       = COALESCE(EXCLUDED.lat, nodes.lat),
                   lon       = COALESCE(EXCLUDED.lon, nodes.lon)""",
            (nid, seed.get("name"), seed.get("district"),
             seed.get("lat"), seed.get("lon"),
             lv.get("status", "UNKNOWN"), lv.get("battery_pct"),
             lv.get("chip_temp_c"), lv.get("threshold"), lv.get("uptime_s"),
             lv.get("first_seen"), lv.get("last_seen"), lv.get("last_heartbeat")),
        )
        for sensor in REAL_NODE_SENSORS:
            conn.execute(
                """INSERT INTO node_sensors (node_id, sensor)
                   VALUES (%s,%s) ON CONFLICT (node_id, sensor) DO NOTHING""",
                (nid, sensor),
            )
        count += 1
    print(f"  nodes: {count} nodo(s) migrado(s): {sorted(node_ids)}")


def migrate_alerts(conn, alerts_db: Path):
    if not alerts_db.exists():
        print("  alerts: no hay alerts.db, nada que migrar")
        return
    rows = dict_rows(alerts_db, "SELECT * FROM alerts ORDER BY id")
    n = 0
    for r in rows:
        status = LEGACY_STATUS.get(r["status"], r["status"]) or "pendiente"
        # El nodo debe existir (FK) — por si la alerta es de un nodo sin monitor.
        conn.execute(
            """INSERT INTO nodes (node_id, node_name, district, lat, lon)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT (node_id) DO NOTHING""",
            (r["node_id"], r["node_name"], r["district"], r["lat"], r["lon"]),
        )
        inserted = conn.execute(
            """INSERT INTO alerts (id, node_id, node_name, district, lat, lon, ts,
                                   confidence, source, det_class, det_count,
                                   video_url, status, temp_c, turb_v,
                                   audio_rms, audio_peak, sats)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING RETURNING id""",
            (r["id"], r["node_id"], r["node_name"], r["district"], r["lat"],
             r["lon"], r["ts"], r["confidence"], r["source"], r["det_class"],
             r["det_count"], r["video_url"], status, r["temp_c"], r["turb_v"],
             r["audio_rms"], r["audio_peak"], r["sats"]),
        ).fetchone()
        if inserted:
            conn.execute(
                """INSERT INTO alert_history (alert_id, old_status, new_status, comment)
                   VALUES (%s, NULL, %s, 'migración desde SQLite')""",
                (r["id"], status),
            )
            n += 1
    conn.execute("SELECT setval('alerts_id_seq', (SELECT COALESCE(MAX(id),1) FROM alerts))")
    print(f"  alerts: {n} nueva(s) de {len(rows)} en SQLite")


def migrate_monitor_children(conn, monitor_db: Path):
    """detections / heartbeats / videos / anomalies / status_history."""
    if not monitor_db.exists():
        print("  monitor: no hay monitor.db, nada que migrar")
        return

    specs = [
        # (tabla_sqlite, tabla_pg, cols_sqlite->cols_pg, clave natural de dedupe)
        ("detections", "detections",
         "INSERT INTO detections (node_id, ts, score, threshold_used, seq) "
         "SELECT %s,%s::timestamptz,%s,%s,%s WHERE NOT EXISTS "
         "(SELECT 1 FROM detections WHERE node_id=%s AND ts=%s::timestamptz AND seq IS NOT DISTINCT FROM %s)",
         lambda r: (r["node_name"], r["timestamp"], r["score"], r["threshold_used"], r["seq"],
                    r["node_name"], r["timestamp"], r["seq"])),
        ("heartbeats", "heartbeats",
         "INSERT INTO heartbeats (node_id, ts, battery_pct, chip_temp_c, uptime_s, threshold, status) "
         "SELECT %s,%s::timestamptz,%s,%s,%s,%s,%s WHERE NOT EXISTS "
         "(SELECT 1 FROM heartbeats WHERE node_id=%s AND ts=%s::timestamptz)",
         lambda r: (r["node_name"], r["timestamp"], r["battery_pct"], r["chip_temp_c"],
                    r["uptime_s"], r["threshold"], r["status"],
                    r["node_name"], r["timestamp"])),
        ("videos", "videos",
         "INSERT INTO videos (node_id, received_at, file_path, file_size_kb) "
         "VALUES (%s,%s::timestamptz,%s,%s) ON CONFLICT (file_path) DO NOTHING",
         lambda r: (r["node_name"], r["received_at"], r["file_path"], r["file_size_kb"])),
        ("anomalies", "anomalies",
         "INSERT INTO anomalies (node_id, ts, type, detail) "
         "SELECT %s,%s::timestamptz,%s,%s WHERE NOT EXISTS "
         "(SELECT 1 FROM anomalies WHERE node_id=%s AND ts=%s::timestamptz AND type IS NOT DISTINCT FROM %s)",
         lambda r: (r["node_name"], r["timestamp"], r["type"], r["detail"],
                    r["node_name"], r["timestamp"], r["type"])),
        ("status_history", "node_status_history",
         "INSERT INTO node_status_history (node_id, ts, old_status, new_status) "
         "SELECT %s,%s::timestamptz,%s,%s WHERE NOT EXISTS "
         "(SELECT 1 FROM node_status_history WHERE node_id=%s AND ts=%s::timestamptz AND new_status=%s)",
         lambda r: (r["node_name"], r["timestamp"], r["old_status"], r["new_status"],
                    r["node_name"], r["timestamp"], r["new_status"])),
    ]
    for sqlite_table, pg_table, sql, binder in specs:
        rows = dict_rows(monitor_db, f"SELECT * FROM {sqlite_table}")
        for r in rows:
            conn.execute(sql, binder(r))
        print(f"  {pg_table}: {len(rows)} fila(s) procesada(s) de monitor.db")


def seed_admin(conn):
    import bcrypt
    username = os.getenv("ADMIN_INIT_USER", "admin")
    password = os.getenv("ADMIN_INIT_PASS", "admin2026")
    exists = conn.execute(
        "SELECT 1 FROM users WHERE username=%s", (username,)
    ).fetchone()
    if exists:
        print(f"  users: '{username}' ya existe (no se toca)")
        return
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn.execute(
        """INSERT INTO users (username, password_hash, role, full_name)
           VALUES (%s,%s,'admin','Administrador')""",
        (username, pw_hash),
    )
    print(f"  users: creado admin '{username}' (clave de ADMIN_INIT_PASS)")


def seed_detector_params(conn):
    n = 0
    for key, val, mn, mx, desc in DETECTOR_PARAMS:
        r = conn.execute(
            """INSERT INTO detector_params (key, value_num, value_type, min_num, max_num, description)
               VALUES (%s,%s,'num',%s,%s,%s)
               ON CONFLICT (key) DO NOTHING RETURNING key""",
            (key, val, mn, mx, desc),
        ).fetchone()
        n += 1 if r else 0
    print(f"  detector_params: {n} parámetro(s) sembrado(s) (existentes intactos)")


def seed_system_config(conn):
    r = conn.execute(
        """INSERT INTO system_config (key, value, description)
           VALUES ('risk', %s, 'pesos y umbrales del motor de riesgo')
           ON CONFLICT (key) DO NOTHING RETURNING key""",
        (json.dumps(RISK_CONFIG),),
    ).fetchone()
    print(f"  system_config: {'sembrado risk' if r else 'risk ya existía (intacto)'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alerts", default=str(ROOT / "datos" / "alerts.db"))
    ap.add_argument("--monitor", default=str(ROOT / "datos" / "monitor.db"))
    args = ap.parse_args()

    print("[MIGRA] aplicando schema.sql (idempotente)...")
    apply_schema()

    pool = get_pool()
    with pool.connection() as conn:      # una sola transacción: o migra todo o nada
        print("[MIGRA] nodos...")
        migrate_nodes(conn, Path(args.monitor), CAPA3 / "nodes.json")
        print("[MIGRA] alertas...")
        migrate_alerts(conn, Path(args.alerts))
        print("[MIGRA] monitoreo...")
        migrate_monitor_children(conn, Path(args.monitor))
        print("[MIGRA] semillas...")
        seed_admin(conn)
        seed_detector_params(conn)
        seed_system_config(conn)
    print("[MIGRA] LISTO ✔")


if __name__ == "__main__":
    main()

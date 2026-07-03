-- schema.sql — Esquema PostgreSQL del Sistema Integrado IoT (mosquitos/dengue).
--
-- Reemplaza a las dos SQLite del PoC (datos/alerts.db + datos/monitor.db) con un
-- solo esquema relacional: FKs, índices, CHECKs e integridad referencial.
-- Idempotente: todo es CREATE ... IF NOT EXISTS (se puede re-aplicar sin miedo).
--
-- Convenciones:
--  * Estados como TEXT + CHECK (no ENUM nativo): más fácil de evolucionar.
--  * alerts.ts sigue siendo epoch-ms (BIGINT) porque el dashboard hace new Date(ts);
--    el resto de tiempos son TIMESTAMPTZ (FastAPI los serializa a ISO 8601).
--  * node_id == device_id del ESP32 ("esp32-01"): la clave natural del sistema.
--
-- Se aplica: (a) al primer arranque del contenedor postgres (docker-entrypoint-initdb.d)
--            (b) por database/migrate_sqlite_to_pg.py (re-aplicación idempotente).

-- ============================================================ usuarios y sesiones
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,                  -- bcrypt
    role          TEXT NOT NULL DEFAULT 'operador'
                  CHECK (role IN ('admin', 'operador')),
    full_name     TEXT,
    active        BOOLEAN NOT NULL DEFAULT TRUE,  -- soft-delete: nunca se borran filas
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,                  -- secrets.token_urlsafe (opaco)
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    ip         TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_exp  ON sessions(expires_at);

-- ============================================================ nodos
-- Fusiona nodes.json (semilla estática) + monitor.db.nodes (estado vivo).
CREATE TABLE IF NOT EXISTS nodes (
    node_id        TEXT PRIMARY KEY,              -- "esp32-01" (== device_id/node_name MQTT)
    node_name      TEXT,                          -- "Nodo SJL-01" (nombre legible)
    district       TEXT,
    lat            DOUBLE PRECISION,
    lon            DOUBLE PRECISION,
    alt            DOUBLE PRECISION,
    status         TEXT NOT NULL DEFAULT 'UNKNOWN'
                   CHECK (status IN ('ONLINE', 'OFFLINE', 'COMPROMISED', 'UNKNOWN')),
    battery_pct    INTEGER,
    chip_temp_c    REAL,
    threshold      REAL,                          -- umbral adaptativo del detector TinyML
    uptime_s       BIGINT,
    first_seen     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat TIMESTAMPTZ,
    last_reading   TIMESTAMPTZ,                   -- última lectura de sensores
    is_simulated   BOOLEAN NOT NULL DEFAULT FALSE,-- true = creado por el simulador
    risk_level     TEXT NOT NULL DEFAULT 'bajo'
                   CHECK (risk_level IN ('bajo', 'medio', 'alto', 'critico')),
    risk_score     REAL NOT NULL DEFAULT 0        -- 0..100 (motor de riesgo)
);

-- Sensores INSTALADOS por nodo (req: "sensores instalados" visibles en el mapa).
CREATE TABLE IF NOT EXISTS node_sensors (
    id        BIGSERIAL PRIMARY KEY,
    node_id   TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    sensor    TEXT NOT NULL,   -- 'temp_ds18b20'|'turbidez'|'gps'|'audio'|'humedad'|'ph'|'nivel_agua'
    installed BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (node_id, sensor)
);

-- Histórico de lecturas de sensores. El ESP32 real solo manda temp/turb (+extras del
-- simulador o de nodos futuros: humedad/ph/nivel_agua). Lo desconocido cae en extra.
CREATE TABLE IF NOT EXISTS sensor_readings (
    id         BIGSERIAL PRIMARY KEY,
    node_id    TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    temp_c     REAL,
    turb_raw   INTEGER,
    turb_v     REAL,
    humedad    REAL,          -- % HR (no existe en el ESP32 actual; aditivo)
    ph         REAL,
    nivel_agua REAL,
    audio_conf REAL,          -- mosquito_conf del topic /audio
    extra      JSONB          -- claves futuras sin migración de esquema
);
CREATE INDEX IF NOT EXISTS idx_readings_node_ts ON sensor_readings(node_id, ts DESC);

-- ============================================================ alertas (workflow)
CREATE TABLE IF NOT EXISTS alerts (
    id           BIGSERIAL PRIMARY KEY,
    node_id      TEXT NOT NULL REFERENCES nodes(node_id),
    node_name    TEXT,
    district     TEXT,
    lat          DOUBLE PRECISION,
    lon          DOUBLE PRECISION,
    ts           BIGINT NOT NULL,                 -- epoch-ms (compat dashboard)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at TIMESTAMPTZ,                     -- primera respuesta de un usuario
    responded_by BIGINT REFERENCES users(id),
    confidence   REAL,
    source       TEXT DEFAULT 'camera',
    det_class    TEXT,                            -- Mosquito | Mosquito Swarm
    det_count    INTEGER,
    video_url    TEXT,
    status       TEXT NOT NULL DEFAULT 'pendiente'
                 CHECK (status IN ('pendiente', 'en-revision', 'respondida',
                                   'resuelta', 'falsa-alarma', 'descartada')),
    risk_level   TEXT CHECK (risk_level IN ('bajo', 'medio', 'alto', 'critico')),
    temp_c       REAL,
    turb_v       REAL,
    humedad      REAL,
    ph           REAL,
    nivel_agua   REAL,
    audio_rms    REAL,
    audio_peak   INTEGER,
    sats         INTEGER,
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE   -- true = generador de pruebas
);
CREATE INDEX IF NOT EXISTS idx_alerts_node_ts ON alerts(node_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_ts     ON alerts(ts DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);

-- Auditoría de transiciones de estado (req.1: historial completo, nunca se borra).
CREATE TABLE IF NOT EXISTS alert_history (
    id         BIGSERIAL PRIMARY KEY,
    alert_id   BIGINT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    old_status TEXT,
    new_status TEXT NOT NULL,
    user_id    BIGINT REFERENCES users(id),
    username   TEXT,                              -- desnormalizado (sobrevive al borrado del user)
    comment    TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerthist_alert ON alert_history(alert_id, ts DESC);

-- ============================================================ monitoreo de nodos
-- Equivalentes 1:1 a monitor.db, con FK a nodes y TIMESTAMPTZ.
CREATE TABLE IF NOT EXISTS detections (
    id             BIGSERIAL PRIMARY KEY,
    node_id        TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    ts             TIMESTAMPTZ NOT NULL,
    score          REAL,
    threshold_used REAL,
    seq            INTEGER
);
CREATE INDEX IF NOT EXISTS idx_det_node_ts ON detections(node_id, ts DESC);

CREATE TABLE IF NOT EXISTS heartbeats (
    id          BIGSERIAL PRIMARY KEY,
    node_id     TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    ts          TIMESTAMPTZ NOT NULL,
    battery_pct INTEGER,
    chip_temp_c REAL,
    uptime_s    BIGINT,
    threshold   REAL,
    status      TEXT
);
CREATE INDEX IF NOT EXISTS idx_hb_node_ts ON heartbeats(node_id, ts DESC);

CREATE TABLE IF NOT EXISTS videos (
    id           BIGSERIAL PRIMARY KEY,
    node_id      TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    received_at  TIMESTAMPTZ NOT NULL,
    file_path    TEXT NOT NULL UNIQUE,
    file_size_kb INTEGER
);
CREATE INDEX IF NOT EXISTS idx_vid_node ON videos(node_id, received_at DESC);

CREATE TABLE IF NOT EXISTS anomalies (
    id      BIGSERIAL PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    ts      TIMESTAMPTZ NOT NULL,
    type    TEXT,
    detail  TEXT
);
CREATE INDEX IF NOT EXISTS idx_anom_node_ts ON anomalies(node_id, ts DESC);

CREATE TABLE IF NOT EXISTS node_status_history (
    id         BIGSERIAL PRIMARY KEY,
    node_id    TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    ts         TIMESTAMPTZ NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nsh_node_ts ON node_status_history(node_id, ts DESC);

-- ============================================================ configuración
-- Parámetros del detector de visión (antes constantes en detector.py). Tipados y con
-- rango [min_num, max_num] para validar en el endpoint admin. La semilla la pone el
-- migrador con los valores actuales del código (mismo comportamiento tras migrar).
CREATE TABLE IF NOT EXISTS detector_params (
    key         TEXT PRIMARY KEY,
    value_num   DOUBLE PRECISION,
    value_txt   TEXT,
    value_type  TEXT NOT NULL DEFAULT 'num' CHECK (value_type IN ('num', 'txt', 'bool')),
    min_num     DOUBLE PRECISION,
    max_num     DOUBLE PRECISION,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  BIGINT REFERENCES users(id)
);

-- Config global (pesos/umbrales del motor de riesgo, retención, etc.) como JSONB.
CREATE TABLE IF NOT EXISTS system_config (
    key         TEXT PRIMARY KEY,
    value       JSONB,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================ auditoría global
CREATE TABLE IF NOT EXISTS events (
    id        BIGSERIAL PRIMARY KEY,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id   BIGINT REFERENCES users(id),
    username  TEXT,
    action    TEXT NOT NULL,   -- 'login'|'logout'|'alert.status'|'config.update'|'user.create'...
    entity    TEXT,            -- 'alert'|'node'|'user'|'detector_params'|...
    entity_id TEXT,
    detail    JSONB,
    ip        TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);

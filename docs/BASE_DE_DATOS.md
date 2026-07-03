# Base de datos (PostgreSQL 16)

Una sola BD `iot_mosquito` reemplaza a las dos SQLite del PoC (`alerts.db` +
`monitor.db`). Esquema en [`capa3-procesamiento-servidor/database/schema.sql`](../capa3-procesamiento-servidor/database/schema.sql)
(idempotente). Corre en Docker (`pg-iot`), **solo escucha en localhost**.

## Diagrama ER (relaciones principales)

```
 users ──1:N── sessions
   │
   ├──1:N── alerts.responded_by          ┌──────────── nodes (PK node_id) ────────────┐
   ├──1:N── alert_history.user_id        │ estado vivo + posición + riesgo + is_simulated │
   ├──1:N── events.user_id               └──────────────────────────────────────────────┘
   └──1:N── detector_params.updated_by        │ 1:N (todas con FK + ON DELETE CASCADE*)
                                               ├── node_sensors        (sensores instalados)
 alerts ──1:N── alert_history                  ├── sensor_readings     (histórico lecturas + extra JSONB)
   │  (auditoría del workflow)                 ├── alerts              (*sin cascade: histórico)
   └── FK node_id → nodes                      ├── detections          (disparos crudos del nodo)
                                               ├── heartbeats
 system_config (JSONB: config riesgo)          ├── videos              (UNIQUE file_path)
 detector_params (parámetros de visión)        ├── anomalies
 events (auditoría global)                     └── node_status_history (ONLINE/OFFLINE/...)
```

## Tablas

| Tabla | Contenido | Claves/Índices |
|---|---|---|
| `users` | usuarios del dashboard, hash bcrypt, rol `admin`/`operador`, soft-delete `active` | UNIQUE username |
| `sessions` | sesiones de login (revocables) | FK user_id, idx expires |
| `nodes` | UN registro por nodo (`node_id` = device_id MQTT). Fusiona el viejo `nodes.json` + `monitor.nodes`: nombre, distrito, lat/lon/alt, status, batería, umbral, uptime, `last_heartbeat`, `last_reading`, `is_simulated`, `risk_level`, `risk_score` | PK node_id, CHECKs |
| `node_sensors` | sensores INSTALADOS por nodo (`temp_ds18b20`, `turbidez`, `gps`, `audio`, `humedad`, `ph`, `nivel_agua`) | UNIQUE (node_id, sensor) |
| `sensor_readings` | histórico de `devices/+/sensors`; columnas conocidas + `extra JSONB` para claves futuras (retrocompatibilidad sin migración) | idx (node_id, ts DESC) |
| `alerts` | alertas CONFIRMADAS por el detector. **`ts` sigue siendo epoch-ms** (contrato del frontend) + `created_at`/`responded_at`/`responded_by`, `status` (workflow), `risk_level`, `is_synthetic` | idx (node_id, ts), idx status |
| `alert_history` | auditoría de CADA transición de estado: old/new, usuario, comentario, timestamp. Nunca se borra | idx (alert_id, ts) |
| `detections` | disparos crudos del nodo (topic alert), score vs umbral | idx (node_id, ts) |
| `heartbeats` | muestras de salud (batería, temp chip, uptime, umbral) | idx (node_id, ts) |
| `videos` | clips subidos (Video Log) | UNIQUE file_path |
| `anomalies` | eventos anómalos (offline, self-monitor) | idx (node_id, ts) |
| `node_status_history` | transiciones ONLINE/OFFLINE/COMPROMISED | idx (node_id, ts) |
| `detector_params` | parámetros del detector de visión, tipados con rango [min,max] y quién los cambió | PK key |
| `system_config` | config global JSONB (`risk`: pesos/umbrales del motor) | PK key |
| `events` | auditoría global (login, cambios de estado, config, usuarios) | idx ts |

## Estados de alerta (CHECK)

`pendiente · en-revision · respondida · resuelta · falsa-alarma · descartada`

Mapeo desde el PoC (lo aplica el migrador y `db.py` al insertar valores viejos):

| SQLite viejo | PostgreSQL nuevo |
|---|---|
| `nueva` | `pendiente` |
| `atendida` | `respondida` |
| `falso-positivo` | `falsa-alarma` |
| `fumigacion` | `en-revision` |

`descartada` es **terminal** (ninguna transición sale de ahí). `falsa-alarma` y
`descartada` se **filtran del mapa** (`GET /api/alerts?for_map=1`) pero permanecen
en BD y en la tabla de detecciones (auditoría).

## Decisiones de diseño

- **TEXT + CHECK, no ENUM**: añadir estados nuevos es un `ALTER ... DROP/ADD CHECK`
  transaccional; los ENUM de PG son rígidos.
- **`alerts.ts` epoch-ms**: el dashboard hace `new Date(a.ts)`; se conserva y se
  añade `created_at TIMESTAMPTZ` para SQL humano.
- **Resto de tiempos TIMESTAMPTZ**: la capa `MonitorDB` los convierte a strings
  ISO 8601 al leer (contrato de la versión SQLite → `nodes.js` no cambió).
- **Acceso**: pool único `psycopg_pool.ConnectionPool` (`database.py`), thread-safe
  para los hilos del gateway y del monitor. Cada operación usa
  `with pool.connection():` (transacción por bloque).

## Migración desde el PoC

```bash
python3 capa3-procesamiento-servidor/database/migrate_sqlite_to_pg.py
```
Idempotente (re-ejecutable). Copia nodos/alertas/monitoreo, mapea estados,
conserva los `id` de alerts (ajusta la secuencia), y siembra: usuario `admin`
(clave `ADMIN_INIT_PASS`), `detector_params` (valores del código original) y
`system_config['risk']`. Solo migra nodos **reales** (los 7 ficticios del
`nodes.json` demo no pasan).

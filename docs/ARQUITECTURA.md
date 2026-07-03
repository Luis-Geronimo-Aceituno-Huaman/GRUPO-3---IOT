# Arquitectura del sistema

Sistema IoT de vigilancia de mosquitos (dengue) en 4 capas. Desde la ampliación
2026-07, la persistencia es **PostgreSQL** y el dashboard tiene **login por roles**.

```
 CAPA 1 · PERCEPCIÓN            CAPA 2 · RED              CAPA 3 · PROCESAMIENTO           CAPA 4 · APLICACIÓN
 ────────────────────           ─────────────             ───────────────────────          ────────────────────
 ESP32-S3 (firmware)            mosquitto :1883           gateway.py :8090                 serve.py :8000
  mic I2S + TinyML     ──MQTT──▶ (Docker, auth) ──MQTT──▶  ├ recibe jpegseq                 ├ SPA dashboard (login)
  DS18B20 / turbidez                                       ├ detector.py (visión)           ├ API alertas + workflow
  GPS NEO-6M                    PostgreSQL 16              ├ risk.py (estampa riesgo)       ├ API nodos + riesgo
  cámara = cam_stream.py:8091    pg-iot :5433              └ AlertStore ─▶ PG               ├ auth.py (sesiones/roles)
  (laptop, LAN)                  (Docker, solo             monitor/ (librería)              └ monitor jobs (lifespan):
                                  localhost)                ├ mqtt_ingest ─▶ PG                MqttIngest·Heartbeat·
 tools/simulador_nodo :8200 ────(mismo protocolo)──▶       ├ heartbeat_monitor                VideoIndexer·RiskJob
  "ESP32 virtual" para pruebas                             └ video_indexer
```

## Flujo de una alerta (event-driven)

1. El ESP32 detecta zumbido (TinyML) → publica `devices/<id>/alert` (QoS1) y
   sensores/GPS/audio/status.
2. Jala una ráfaga JPEG de la cámara (`cam_stream.py :8091`, LAN) y la sube:
   `POST :8090/upload?device=<id>&fmt=jpegseq&seconds=6` (cuerpo `[4B len BE][JPEG]…`).
3. El gateway arma un `.webm`, lo analiza con `detector.py` (VisionGate: MOG2 +
   flujo óptico + tracker). **Negativo → se descarta** (no llega a la BD).
4. Positivo → `build_alert()` enriquece con el caché MQTT (sensores/GPS) + calcula
   el **nivel de riesgo** del momento (`risk.py`) → `AlertStore.insert_alert()`
   (estado inicial `pendiente` + primera fila de `alert_history`).
5. `serve.py` expone la alerta en `/api/alerts`; el dashboard la pinta en tabla,
   mapa (si no está descartada/falsa) y KPIs. Los operadores la atienden con
   `PATCH /api/alerts/<id>/status` — cada transición queda auditada.

En paralelo, `monitor/` registra nodos, heartbeats, detecciones crudas, videos y
anomalías; `HeartbeatMonitor` clasifica ONLINE/OFFLINE/COMPROMISED; `RiskJob`
recalcula el riesgo de todos los nodos cada 5 min.

## Procesos y puertos

| Proceso | Puerto | Dónde corre | Público |
|---|---|---|---|
| mosquitto (Docker `mosquitto-iot`) | 1883 | nube | sí (con clave) |
| PostgreSQL (Docker `pg-iot`) | 5433→5432 | nube | **NO** (solo localhost) |
| `gateway.py` | 8090 | nube | sí (`/upload` del ESP32) |
| `serve.py` | 8000 | nube | sí (dashboard, con login) |
| `cam_stream.py` | 8091 | laptop (LAN) | **NO** (solo LAN) |
| `tools/simulador_nodo/app.py` | 8200 | laptop dev | **NO** (solo localhost) |

## Módulos clave

| Archivo | Rol |
|---|---|
| `capa3-procesamiento-servidor/database.py` | Pool psycopg3 compartido (thread-safe) |
| `capa3-procesamiento-servidor/database/schema.sql` | Esquema completo (15 tablas) |
| `capa3-procesamiento-servidor/database/migrate_sqlite_to_pg.py` | Migración PoC→PG + semillas |
| `capa3-procesamiento-servidor/db.py` | `AlertStore`: alertas + workflow + auditoría |
| `capa3-procesamiento-servidor/monitor/db.py` | `MonitorDB`: nodos/heartbeats/videos/lecturas |
| `capa3-procesamiento-servidor/detector.py` | Visión (params desde BD, hot-reload por clip) |
| `capa3-procesamiento-servidor/risk.py` | Motor de nivel de riesgo |
| `capa4-aplicacion/serve.py` | API + SPA + jobs de fondo |
| `capa4-aplicacion/auth.py` | Sesiones con cookie firmada + roles |
| `capa4-aplicacion/dashboard/` | SPA vanilla JS (Leaflet + Chart.js) |
| `tools/simulador_nodo/` | ESP32 virtual + generador de alertas sintéticas |

Ver el resto de documentos de esta carpeta para el detalle de cada tema.

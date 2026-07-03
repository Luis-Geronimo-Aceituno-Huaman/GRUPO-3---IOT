# Changelog — Ampliación 2026-07 (PoC → sistema profesional)

Regla de oro respetada en todo: **el protocolo del ESP32 no cambió** (extensiones
solo aditivas; regresión verificada con payloads exactos de `MQTT_SPEC.md`).

## Base de datos
- **PostgreSQL 16** (Docker `pg-iot`, solo localhost) reemplaza a las 2 SQLite.
- Esquema relacional de 15 tablas con FKs, índices, CHECKs e integridad
  referencial (`database/schema.sql`).
- Migrador idempotente `database/migrate_sqlite_to_pg.py` (datos del PoC +
  semillas: admin, parámetros del detector, config de riesgo).
- Pool psycopg3 compartido (`database.py`); `AlertStore`/`MonitorDB` conservan
  sus firmas → `gateway.py`/`serve.py` casi no cambiaron.
- Nuevas tablas: `users`, `sessions`, `node_sensors`, `sensor_readings` (con
  `extra` JSONB), `alert_history`, `detector_params`, `system_config`, `events`.

## Workflow de alertas
- 6 estados: `pendiente / en-revision / respondida / resuelta / falsa-alarma /
  descartada` (mapeo automático de los 4 viejos).
- `PATCH /api/alerts/{id}/status` con acción + comentario; transacción única:
  UPDATE + `alert_history` (quién/cuándo/por qué) + `events`.
- `descartada` es terminal; `falsa-alarma`/`descartada` se limpian del mapa
  automáticamente pero se conservan para auditoría.
- El modal "Responder" del dashboard ahora **persiste de verdad** (antes solo
  mutaba memoria) y muestra el historial completo.

## Autenticación
- Login con bcrypt + sesiones en BD + cookie firmada (HttpOnly/SameSite).
- Roles admin/operador; CRUD de usuarios (soft-delete); auditoría en `events`.
- Todas las APIs y `/clips` protegidas; `/upload` y MQTT quedan libres para el
  ESP32 (que ya autentica contra el broker).

## Motor de riesgo (nuevo `risk.py`)
- Score 0-100 y nivel 🟢🟡🟠🔴 por nodo: temperatura óptima Aedes (25-30 °C),
  turbidez, humedad/pH/nivel si existen, actividad de alertas 72 h.
- Pesos redistribuidos ante sensores ausentes (compatible con el ESP32 real).
- Job cada 5 min + estampado en cada alerta + desglose on-demand.
- Config editable en vivo (`system_config['risk']`, pestaña Admin).

## Detector de visión
- TODOS los parámetros a la tabla `detector_params` con validación de rango y
  **hot-reload por clip** (fallback a defaults si la BD cae).
- Mejoras (opt-in, apagadas por defecto): denoising bilateral, CLAHE, umbral de
  flujo adaptativo por percentil de ruido, tracker de centroides con trayectoria
  y validación de velocidad (px/s), `flow_downscale` para la VM ARM.

## Dashboard (frontend)
- **Eliminados los 8 nodos demo hardcodeados**: nodos, posiciones, sensores,
  conteos y riesgo salen 100 % de la BD (`/api/nodes` enriquecido).
- Login (`login.html`) + chip de usuario + logout + pestaña **Admin** (usuarios,
  parámetros del detector, motor de riesgo).
- Mapa: pins coloreados por riesgo (tamaño = score), leyenda, popup con ficha
  completa del nodo, heatmap solo de alertas visibles.
- Nuevos badges de riesgo y estados, gráfico "alertas por estado", columna de
  riesgo en tablas, filas atenuadas para descartadas, toasts en vez de alert(),
  etiqueta «SIM» para nodos/alertas simuladas, auto-refresh 60 s.

## Simuladores (nuevo `tools/simulador_nodo/`, :8200)
- **ESP32 virtual** web: protocolo MQTT/upload idéntico al firmware (incl. LWT,
  heartbeat, respuesta a cmd) + ráfagas jpegseq sintéticas con "mosquitos"
  animados que ejercitan el detector real end-to-end. Sensores extra
  (humedad/pH/nivel) como claves aditivas.
- **Generador de alertas sintéticas** (`is_synthetic=TRUE`): pobla dashboard y
  mapa sin video ni detector; también `POST /api/alerts/synthetic` (admin).

## Infra
- `docker-compose.yml` en la raíz: mosquitto + postgres (healthcheck, volumen).
- `.env`/(`.env.example`): `PG_*`, `SESSION_SECRET`, `ADMIN_INIT_PASS`.
- `requirements-nube.txt`: + psycopg, bcrypt, itsdangerous.
- `run_nube.sh` avisa si falta la BD; systemd con `ExecStartPre=pg_isready`
  (DESPLIEGUE.md actualizado).
- Arranque degradado del dashboard si PG cae (503, sin crash); gateway con
  reintento/backoff.

## Sin cambios
- Firmware ESP32 (capa 1) y `MQTT_SPEC.md` (capa 2).
- `cam_stream.py`, formato jpegseq, `mosquito_veredicto_video.py` (herramienta
  de laboratorio), `run_laptop.sh`.

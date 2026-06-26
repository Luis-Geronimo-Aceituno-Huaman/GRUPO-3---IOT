# Servidor de monitoreo de nodos (capa 3)

Implementa el `server prmpt.txt`: registro automático de nodos, monitoreo de
heartbeat/liveness, esquema de BD, suscripciones MQTT y un dashboard web de 4
pestañas. **Subsistema independiente**: corre junto al `gateway.py` (:8090) y
`serve.py` (:8000) sin tocarlos. BD propia (`datos/monitor.db`), puerto propio
(:8100), cliente MQTT propio (`node-monitor`).

## Cómo ejecutar

```bash
docker start mosquitto-iot                 # el broker (si no está arriba)
cd "capa3-procesamiento-servidor/monitor"
python3 run.py
```

Dashboard: http://localhost:8100  · Estado: `/status` · Video Log: `/videos`

Sin dependencias nuevas: solo stdlib + `paho-mqtt` (ya instalado). OpenCV (`cv2`)
solo se usa si llega un video por el `POST /upload` propio.

Variables de entorno (opcionales, ver `config.py`): `MQTT_HOST`,
`MONITOR_HTTP_PORT`, `MONITOR_DB_PATH`, `OFFLINE_AFTER_S`, `COMPROMISED_AFTER_S`,
`HB_CHECK_INTERVAL_S`, `VIDEO_INDEX_INTERVAL_S`.

## Mapeo spec ↔ firmware real del ESP32

El `server prmpt.txt` asume `nodes/{name}/{detection,heartbeat,video,status}`. El
firmware real (`capa1-.../nodo_iot_autocalib/`) **no** usa todos esos topics. Este
servidor se implementa contra lo que el ESP32 **publica de verdad**:

| Spec | Real | Tabla |
|---|---|---|
| `nodes/+/detection` | `devices/+/alert` (QoS1) `{node_name,source,confidence,ts,timestamp,seq}` | `detections` |
| `nodes/+/heartbeat` | `nodes/+/heartbeat` `{node_name,status,uptime_s,battery_pct,chip_temp_c,threshold,timestamp,seq}` | `heartbeats` + `nodes` |
| `nodes/+/video` (MQTT) | **HTTP POST** al gateway `:8090/upload?fmt=jpegseq` → `.webm` en `datos/clips/` | `videos` (por indexado) |
| `nodes/+/status` | `devices/+/status` (online/LWT) + `nodes/+/status` (reservado) | `anomalies` |

Notas de diseño que hacen que **funcione con el ESP32 tal cual** (sin reflashear):

- **`threshold_used` de cada detección**: el payload de `alert` no trae el umbral;
  se usa el último `threshold` reportado por el heartbeat de ese nodo.
- **`timestamp`**: si el nodo ya sincronizó por SNTP, se usa su hora Unix; si no
  (`timestamp:0`), se usa la hora de recepción del servidor. Todo en ISO 8601 con
  zona.
- **`battery_pct`**: el hardware actual no mide batería → el firmware envía `-1` →
  el dashboard lo muestra como `N/A`.
- **Video Log**: el ESP32 solo sube vídeo al gateway (:8090). Para no chocar de
  puerto ni tocar el firmware, este servidor **indexa** los `.webm` que el gateway
  ya guarda en `datos/clips/`. Además expone su propio `POST /upload` (jpegseq)
  por si algún día se le apunta el nodo a este puerto.
- **node_name vs device_id**: en el firmware coinciden (`self_monitor.h` provisiona
  `node_name = DEVICE_ID = "esp32-01"`), así que `devices/<id>/...` y
  `nodes/<name>/...` son la misma clave de nodo.

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `config.py` | Broker, puertos, rutas, topics reales, umbrales de liveness |
| `db.py` | SQLite: `nodes, detections, heartbeats, videos, anomalies, status_history` |
| `mqtt_ingest.py` | Suscriptor MQTT + registro automático + handlers por topic |
| `heartbeat_monitor.py` | Job cada 5 min: ONLINE/OFFLINE(>30m)/COMPROMISED(>24h) |
| `video_indexer.py` | Indexa `datos/clips/` + arma jpegseq→webm para `/upload` |
| `views.py` | Render HTML del dashboard (4 pestañas, sin frameworks) |
| `web.py` | Servidor HTTP: páginas + API JSON + `/clips` (Range) + `POST /upload` |
| `run.py` | Punto de entrada: arranca los 4 servicios |

## Dashboard

- **Inicio** (`/`): una tarjeta aislada por nodo (status, batería, último
  heartbeat) + la última alerta de cada nodo, con enlace a su historial.
- **Detalle** (`/node/<name>`): historial de detecciones paginado + tendencias de
  temperatura/batería (SVG) + estado actual + anomalías + historial de estados.
- **Estado** (`/status`): tabla de todos los nodos con color por status
  (verde/amarillo/rojo), auto-refresh cada 60 s.
- **Video Log** (`/videos`): tabla ordenable por fecha y filtrable por nodo, con
  enlace de descarga/reproducción.

## API JSON

- `GET /api/nodes`
- `GET /api/node/<name>/detections?page=&size=`
- `GET /api/node/<name>/heartbeats`
- `GET /api/videos?node=`

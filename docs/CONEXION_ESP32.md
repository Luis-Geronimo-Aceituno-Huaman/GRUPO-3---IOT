# Conexión del ESP32 (protocolo intacto)

**La ampliación NO cambió el protocolo.** El firmware actual
(`capa1-percepcion-dispositivo/nodo_iot_autocalib/`) funciona sin reflashear:
solo asegurate de que `config.h` apunte al broker/gateway correctos (ver
`DESPLIEGUE.md`). El contrato completo está en `capa2-red/MQTT_SPEC.md`.

## Resumen del contrato (lo que el backend espera)

| Topic | Dir | Payload |
|---|---|---|
| `devices/<id>/alert` (QoS1) | ESP32→srv | `{node_name, source, confidence, ts, timestamp, seq}` |
| `devices/<id>/sensors` | ESP32→srv | `{turb_raw, turb_v, temp_c}` |
| `devices/<id>/gps` (retained) | ESP32→srv | `{lat, lon, alt, sats}` (solo con fix) |
| `devices/<id>/audio` | ESP32→srv | `{mosquito_conf}` |
| `devices/<id>/status` | ESP32→srv | `{uptime_ms, rssi, heap_free}` |
| `devices/<id>/availability` (LWT, retained) | ESP32→srv | `{online: bool}` |
| `nodes/<id>/heartbeat` (10 min) | ESP32→srv | `{node_name, status:"alive", uptime_s, battery_pct, chip_temp_c, threshold, timestamp, seq}` |
| `devices/<id>/cmd` | srv→ESP32 | texto: `recalib` \| `heartbeat` \| `restart` |

**Upload de video**: `POST http://<srv>:8090/upload?device=<id>&fmt=jpegseq&seconds=6`,
`Content-Type: application/octet-stream`, cuerpo `[4B len big-endian][JPEG]...`.
Este endpoint **no requiere login** (el ESP32 no maneja cookies); la seguridad del
nodo es la clave MQTT del broker.

## Qué pasa al conectar un ESP32 nuevo

1. Su primer mensaje MQTT lo **auto-registra** en la tabla `nodes` (`node_id` =
   `DEVICE_ID` del config.h) — no hay que darlo de alta a mano.
2. El heartbeat lo pone ONLINE; los sensores llenan `sensor_readings` y su GPS
   (con fix) fija su posición en el mapa.
3. Sus sensores instalados: si querés que la ficha muestre el detalle, insertá
   en `node_sensors` (el migrador ya lo hace para `esp32-01`):
   ```sql
   INSERT INTO node_sensors (node_id, sensor) VALUES
     ('esp32-02','temp_ds18b20'),('esp32-02','turbidez'),
     ('esp32-02','gps'),('esp32-02','audio') ON CONFLICT DO NOTHING;
   ```
4. Nombre/distrito legibles: `UPDATE nodes SET node_name='Nodo COM-01',
   district='Comas' WHERE node_id='esp32-02';` (o esperá — el mapa usa el GPS real).

## Extensiones retrocompatibles

- Campos **extra** en el JSON de `sensors` (`humedad`, `ph`, `nivel_agua` o
  cualquier otro) se aceptan sin tocar el backend: van a columnas propias o al
  JSONB `extra` de `sensor_readings`, y entran al cálculo de riesgo si el motor
  los conoce. Un firmware futuro puede añadirlos sin romper nada.
- Nunca renombres los campos existentes ni cambies el framing del jpegseq: eso sí
  rompería la ingesta.

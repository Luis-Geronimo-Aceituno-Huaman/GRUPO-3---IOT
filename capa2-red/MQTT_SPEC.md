# Especificación MQTT — Capa de Red (project_iot_2)

Contrato de mensajería entre las 3 capas. Define qué publica y a qué se suscribe
cada componente, con el QoS justificado por la criticidad del dato.

Convención de tópicos: `devices/<device_id>/...` (ej. `devices/esp32-01/...`).
El servidor escala a múltiples nodos suscribiéndose con un comodín: `devices/+/clip`,
`devices/+/status`, etc.

---

## Resumen de tópicos

| Tópico | Dirección | QoS | Retenido | Frecuencia | Propósito |
|--------|-----------|:---:|:--------:|------------|-----------|
| `devices/<id>/alert`            | nodo → cámara      | **1** | no | por evento | Disparo: el nodo sospecha mosquito |
| `devices/<id>/sensors`          | nodo → gateway     | 0 | no | cada 5 s   | Turbidez + temperatura (cache) |
| `devices/<id>/gps`              | nodo → gateway     | 0 | sí | cada 5 s   | Posición (cache + heatmap) |
| `devices/<id>/status`           | nodo → gateway     | 0 | sí | cada 5 min | Heartbeat: batería, WiFi, uptime |
| `devices/<id>/availability`     | nodo → servidor    | **1** | sí | conexión/LWT | Vivo/muerto (online/offline) |
| **`devices/<id>/camera/clip`**  | **cámara → gateway** | **1** | no | por evento | **Ruta del clip 5-10s listo para analizar** |
| `devices/<id>/camera/detection` | gateway → dashboard | **1** | no | por evento | Metadatos de la alerta CONFIRMADA por el detector |
| `devices/<id>/camera/record`    | gateway → cámara   | **1** | no | por evento | (opcional) Ordena grabar bajo demanda |

**Regla del QoS:** QoS **1** (entrega garantizada) cuando perder el mensaje tiene
consecuencias (un disparo, un clip, una alerta confirmada). QoS **0** cuando el dato
es redundante y el siguiente lo reemplaza (telemetría periódica).

---

## El flujo nuevo de project_iot_2 (resumen)

```
 [DEVICE]                 [NETWORK / MQTT]              [APPLICATION]
  ESP32 ── alert ───────────────────────────────► cámara graba clip 5-10s
                                                        │
            ◄──────── camera/clip {video_path} ─────────┘
  gateway ── analiza el movimiento del clip ──┐
                                              ▼
                        ¿detecta movimiento tipo Mosquito / Enjambre?
                         ┌──────────────┴──────────────┐
                        SÍ                              NO
                  guarda en BD                     descarta
                  + camera/detection               (falso positivo)
                         │
                  dashboard (/api/alerts)
```

> **Compuerta de visión:** el **gateway** analiza el clip con **visión por movimiento**
> (OpenCV: MOG2 + flujo óptico Farneback + filtrado de blobs por forma/tamaño) y **solo
> guarda en la base de datos si confirma** vuelo tipo mosquito. La compuerta está **antes**
> del INSERT, así que en la BD solo quedan alertas confirmadas (sin falsos positivos).

---

## 1. Disparo del nodo — `devices/<id>/alert`

**nodo → cámara · QoS 1 · por evento**

El nodo sospecha actividad (por **Edge ML / TinyML** del aleteo; GPIO como respaldo) y
dispara. No es una confirmación: solo pide a la cámara que grabe para que el detector decida.

```json
{ "source": "audio", "confidence": 0.86, "ts": 1718900000000 }
```
`source` es `"audio"` cuando lo confirma el modelo TinyML (incluye su `confidence`), o
`"gpio"` si vino del disparo manual de respaldo.

## 2. Clip listo — `devices/<id>/camera/clip`  *(NUEVO)*

**cámara → gateway · QoS 1 · por evento**

La cámara grabó el video de 5-10 s y publica la **referencia** (ruta/URL). El binario
**no** viaja por MQTT (no está diseñado para cargas grandes); solo va la ruta ligera.

```json
{ "video_path": "clips/esp32-01/20260621-153012.mp4",
  "ts": 1718900060000, "seconds": 8, "device_id": "esp32-01" }
```

## 3. Alerta confirmada — `devices/<id>/camera/detection`

**gateway → dashboard · QoS 1 · por evento**

Se publica **solo si el detector confirmó**. Metadatos ligeros del evento ya guardado en BD.

```json
{ "video_url": "clips/esp32-01/20260621-153012.mp4",
  "ts": 1718900061000, "confidence": 0.93,
  "det_class": "Mosquito", "detections": 9, "model": "motion-mog2+flow" }
```

## 4–5. Telemetría: `sensors`, `gps`, `status`

**nodo → gateway · QoS 0**

El gateway **cachea** la última lectura de cada nodo para **enriquecer** la alerta
confirmada (temp, turbidez, audio, sats, posición) antes de guardarla.

## 6. Disponibilidad — `devices/<id>/availability`

**nodo → servidor · QoS 1 · retenido · LWT.** `{"online":true}` al conectar; el broker
publica `{"online":false}` automáticamente si el nodo se cae (Last Will).

---

## Seguridad (pendiente para producción)

Hoy el broker es TCP plano (1883) con usuario/contraseña. El objetivo es **TLS 1.2**
(puerto 8883) con certificados X.509. Ver `mosquitto/mosquitto.conf`.

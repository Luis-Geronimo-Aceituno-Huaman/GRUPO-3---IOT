# sistema_integrado — Vigilancia de mosquitos (dengue) con TinyML + visión por movimiento, en 4 capas

Carpeta **limpia y autocontenida** que unifica todo el proyecto en un solo lugar:

1. **Detección acústica de mosquito** en el ESP32 con **TinyML** (Edge Impulse), ya calibrado.
2. **Alerta con todos los sensores** cuando el zumbido se detecta **3 ventanas seguidas**.
3. **Captura de imagen desde el ESP32**: jala una ráfaga JPEG de la **webcam expuesta como cámara IP** (`cam_stream.py`), ya no la Tapo.
4. **Compuerta de visión por movimiento** (MOG2 + flujo óptico) que confirma *mosquito / enjambre* antes de guardar.
5. **Dashboard** con las alertas confirmadas.

> Antes estaba repartido en `01-capa-device/`, `02-capa-network/`, `03-capa-application/`
> y varias carpetas de prueba. Aquí queda **todo junto y ordenado por capas**.

---

## Las 4 capas

| Capa | Carpeta | Qué hace | Dónde corre |
|---|---|---|---|
| **1 · Percepción / Dispositivo** | `capa1-percepcion-dispositivo/` | ESP32-S3: micrófono INMP441 + TinyML, turbidez, temperatura (DS18B20), GPS. Detecta el aleteo y, tras **3 ventanas seguidas**, publica la **alerta + telemetría**. | ESP32 |
| **2 · Red** | `capa2-red/` | Broker **Mosquitto**: transporta los mensajes `devices/<id>/...`. | Servidor/LAN |
| **3 · Procesamiento / Servidor** | `capa3-procesamiento-servidor/` | **Cámara IP** (`cam_stream.py`: la webcam de la laptop expuesta por HTTP, de donde el ESP32 jala la ráfaga) + **detector de movimiento** (compuerta) + **gateway** (orquesta) + **base de datos** (SQLite). | Laptop + Nube |
| **4 · Aplicación** | `capa4-aplicacion/` | **API + dashboard** web: mapa, tabla y gráficos de las alertas confirmadas. | Laptop / navegador |

---

## El flujo completo, de punta a punta

```
 CAPA 1 · ESP32-S3                       CAPA 2 · MQTT          CAPA 3 · SERVIDOR (laptop)            CAPA 4
 ─────────────────                       ─────────────          ──────────────────────────           ──────
 micrófono → TinyML (Edge Impulse)
   confianza ventana a ventana
   ¿≥ umbral en 3 ventanas seguidas?
     ESP32 jala ráfaga JPEG ──HTTP──► cam_stream.py :8091 (webcam = cámara IP, LAN)
     y sube la ráfaga ────────HTTP──────────────────────────────────► gateway.py /upload
   (+ turbidez, temp, GPS) ───────────► devices/<id>/sensors      │
                                         devices/<id>/gps         ▼
                                         devices/<id>/status                            gateway.py
                                                                                            │  analiza
                                                                                            ▼  movimiento
                                                              ¿Movimiento tipo Mosquito / Enjambre?
                                                               SÍ ─► guarda en BD (alerts) ──► dashboard
                                                                     + enriquece con sensores   /api/alerts
                                                               NO ─► descarta (falso positivo)
```

**Doble filtro:** audio barato en el borde (ESP32) + visión en el servidor (detector de
movimiento). El nodo solo dice "mira aquí"; **el detector decide** si la alerta se guarda.
La compuerta usa **MOG2 + flujo óptico** (OpenCV) para distinguir el vuelo errático del
mosquito y reporta `Mosquito` · `Mosquito Swarm` (enjambre).

---

## Estructura

```
sistema_integrado/
├── README.md                          ← este archivo
├── DESPLIEGUE.md                       ← cómo se parte en laptop + nube
├── run_laptop.sh                       ← laptop: expone la webcam como cámara IP (:8091)
├── run_nube.sh                         ← servidor: gateway + dashboard (broker, detector, BD)
│
├── capa1-percepcion-dispositivo/
│   └── nodo_iot/{nodo_iot.ino, config.h}   ← firmware ESP32 (TinyML calibrado + sensores + alerta)
│
├── capa2-red/
│   ├── mosquitto.conf · MQTT_SPEC.md · README.md
│
├── capa3-procesamiento-servidor/
│   ├── cam_stream.py        ← expone la WEBCAM como cámara IP (:8091); el ESP32 jala la ráfaga
│   ├── gateway.py           ← orquestador: recibe la ráfaga (/upload) → detector → BD condicional
│   ├── detector.py          ← compuerta de visión por movimiento (MOG2 + flujo óptico)
│   ├── db.py · config.py · nodes.json · requirements.txt
│
├── capa4-aplicacion/
│   ├── serve.py             ← API /api/alerts + sirve el dashboard
│   └── dashboard/           ← web (mapa, tabla, gráficos)
│
└── datos/                   ← (runtime) clips grabados y alerts.db
```

---

## Cómo correr (laptop + servidor)

El sistema se parte en dos lanzadores (el detalle del despliegue en la nube está en
[`DESPLIEGUE.md`](DESPLIEGUE.md)). Necesitas **Python 3** y un broker **Mosquitto** en
`localhost:1883` (`cd capa2-red && docker compose up -d`).

```bash
# LAPTOP — expone la webcam como cámara IP (:8091) por mDNS, para que el ESP32 jale la ráfaga
pip install -r requirements-laptop.txt    # solo OpenCV
bash run_laptop.sh

# SERVIDOR (laptop misma o nube) — gateway (:8090) + detector + BD + dashboard (:8000)
pip install -r requirements-nube.txt
bash run_nube.sh
```

Abre **http://localhost:8000** → las alertas confirmadas aparecen en el dashboard.
Para probar la cámara IP sin el ESP32: **http://localhost:8091/stream** (MJPEG en el navegador)
o `curl http://localhost:8091/snapshot.jpg -o snap.jpg`.

---

## El ESP32 de verdad

1. **Flashea el nodo:** abre `capa1-percepcion-dispositivo/nodo_iot_autocalib/` en Arduino IDE,
   instala el modelo `.zip` de Edge Impulse como librería, configura el WiFi (portal WiFiManager),
   y en `config.h` pon `CAM_MDNS` = hostname de la laptop con `cam_stream.py` y `MQTT_HOST` = IP del
   broker. Sube al ESP32-S3 + PSRAM. Valores ya **calibrados**
   (`MIC_GAIN_SHIFT=12`, `UMBRAL_MOSQUITO=0.50`, `VENTANAS_SEGUIDAS=3`).
2. El ESP32 detecta el zumbido (3 ventanas) → **jala una ráfaga JPEG** de `cam_stream.py` por la LAN
   → la **sube al gateway** (`/upload`) → el detector de movimiento confirma → la alerta se guarda
   con su snapshot de sensores y se ve en el dashboard.

---

## La calibración del TinyML (por qué estos números)

El modelo se entrenó con **clips de internet**, así que la confianza no separa tan fuerte
como con datos del propio micrófono. Medido en el nodo:

| `MIC_GAIN_SHIFT` | Zumbido | Silencio | Separación |
|---|---|---|---|
| 11 | 0.21 | 0.05 | baja |
| **12** | **0.56** | **0.21** | **mejor** ✓ |
| 13 | 0.63 | 0.50 | casi nula |

Por eso: `MIC_GAIN_SHIFT=12` y `UMBRAL_MOSQUITO=0.50`. La regla de **3 ventanas seguidas**
(`VENTANAS_SEGUIDAS=3`) mata los picos sueltos de ruido. Para máxima fiabilidad, el paso
pendiente es **reentrenar con audio del propio INMP441**.

---

## Qué cambió respecto al proyecto anterior

- **Cámara:** de Tapo/RTSP (H.264, que el ESP32 no puede decodificar) → **webcam de la
  laptop expuesta como cámara IP** (`cam_stream.py`); el ESP32 jala la ráfaga JPEG y la sube
  al gateway. El resto del pipeline (detector, BD, dashboard) no cambió.
- **TinyML calibrado** con valores reales del nodo.
- **Reorganizado en 4 capas** (se separó *Procesamiento* de *Aplicación*) y **todo
  autocontenido** dentro de `sistema_integrado/`.

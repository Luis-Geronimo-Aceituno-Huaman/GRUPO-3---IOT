# Dependencias

## Python — nube / desarrollo (`requirements-nube.txt`)

| Paquete | Para qué |
|---|---|
| `paho-mqtt >=2.0` | Cliente MQTT (gateway, monitor, simulador) |
| `opencv-python >=4.8` | Detector de visión + armado de .webm + jpegseq sintético |
| `numpy >=1.24` | Soporte de OpenCV (flujo óptico, máscaras) |
| `python-dotenv` | Lectura del `.env` (opcional: hay parser propio de fallback) |
| `fastapi >=0.110` | API + SPA del dashboard, simulador |
| `uvicorn >=0.27` | Servidor ASGI |
| `psycopg[binary,pool] >=3.1` | **PostgreSQL** (pool thread-safe en `database.py`) |
| `bcrypt >=4.0` | Hash de contraseñas (`auth.py`, migrador) |
| `itsdangerous >=2.1` | Firma de la cookie de sesión |

## Python — laptop cámara (`requirements-laptop.txt`)
Solo `opencv-python` (la laptop únicamente expone la webcam en :8091).

## Servicios (Docker, compose de la raíz)
- `eclipse-mosquitto:2` — broker MQTT con autenticación (capa 2).
- `postgres:16-alpine` — base de datos única del sistema (multi-arch, corre en la
  VM ARM de Oracle).

## Frontend (CDN, sin build step)
- Leaflet 1.9.4 + leaflet.heat 0.2.0 (mapa/heatmap).
- Chart.js 4.4.1 (gráficos).
- Vanilla JS/CSS — no hay node_modules ni compilación.

## Firmware (Arduino, sin cambios)
- PubSubClient (MQTT), OneWire/DallasTemperature (DS18B20), TinyGPSPlus,
  Edge Impulse SDK (TinyML), HTTPClient/mDNS del core ESP32.

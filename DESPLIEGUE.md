# DESPLIEGUE — el proyecto separado en 3 lugares de ejecución

Migración a la nube **gratis** (Oracle Cloud Always Free). El sistema se parte en
**3 lugares**, cada uno con su pedazo de las 4 capas:

```
  TU CASA (LAN)                                    ☁️ NUBE (VM Oracle, 24/7)
  ─────────────                                    ────────────────────────
  laptop: cam_stream.py :8091 ──┐
     (webcam como cámara IP)    │ (1) ESP32 pide ráfaga JPEG por LAN
                                │
  ESP32 ──jala fotos───────────┘
     │  detecta zumbido (mic+TinyML)
     ├─ alert/sensors ─MQTT────────────────────────► mosquitto :1883 (con clave)
     └─ sube ráfaga jpegseq ─HTTP───────────────────► gateway :8090 ─► detector ─► alerts.db
                                                          │
   abrís el dashboard desde el celu ◄─────────────── serve.py :8000
```

| Capa | 🟢 ESP32 | 🟡 LAPTOP | ☁️ NUBE |
|---|---|---|---|
| **1 · Percepción** | `nodo_iot_autocalib/` (firmware) | — | — |
| **2 · Red** | — | — | **mosquitto** (broker) |
| **3 · Procesamiento** | — | `cam_stream.py` | `gateway.py` · `detector.py` · `db.py` · `config.py` · `nodes.json` · `monitor/` |
| **4 · Aplicación** | — | — | `serve.py` · `dashboard/` |
| *(datos)* | — | — | `datos/` → `alerts.db`, `monitor.db`, `clips/` |

> La captura la hace el **ESP32**: jala una ráfaga JPEG de `cam_stream.py` (la laptop
> como cámara IP) y la sube al gateway. El servidor **no controla la webcam**.

**Puertos abiertos a internet (solo la nube):** `1883`, `8090`, `8000`.
**El `8091` NUNCA se abre a internet** — es solo LAN, entre el ESP32 y la laptop.

---

## 🟢 ESP32 — Capa 1 (no migra)

El firmware sigue igual salvo **un cambio**: hoy la cámara y el broker comparten el
mismo host (`g_brokerHost`). Al separarse (cámara=laptop, broker=nube) hay que:

- **Cámara** → encontrar la **laptop por mDNS** en la LAN (sin respaldo a IP pública).
- **Broker** → intentar mDNS y, al fallar (está en la nube), caer a la **IP pública**.

En [`config.h`](capa1-percepcion-dispositivo/nodo_iot_autocalib/config.h):

```c
// Broker + gateway: en la NUBE
#define MQTT_MDNS   ""               // vacío: el broker NO se busca por mDNS
#define MQTT_HOST   "140.x.x.x"      // IP pública de la VM Oracle
#define MQTT_PORT   1883
#define MQTT_USER   "esp32"          // debe coincidir con capa2-red/passwd y .env
#define MQTT_PASS   "iotmosquito2026"

// Cámara: en la LAPTOP (LAN), por mDNS
#define CAM_MDNS    "iot-server-2"   // hostname de tu laptop con cam_stream.py
#define CAM_PORT    8091
```

Y la cámara se resuelve por separado del broker (variable `g_camHost`, distinta de
`g_brokerHost`). ✅ **Ya aplicado** en el `.ino` y en `config.h` (usuario `esp32` +
clave ya configurados). **Solo falta** que reemplaces `MQTT_HOST` por la IP pública
real de tu VM antes de reflashear.

---

## 🟡 LAPTOP — un pedazo de la Capa 3 (no migra: tiene la webcam)

```bash
pip install -r requirements-laptop.txt   # solo OpenCV
./iniciar.sh laptop                       # expone la webcam en :8091
```

- Necesita **Avahi** para anunciarse por mDNS: `sudo apt install avahi-daemon`.
- El ESP32 y la laptop deben estar en la **misma WiFi**.

---

## ☁️ NUBE — Capas 2 + 3 + 4 (esto es lo que se sube)

### Parte A · Crear la VM gratis (una sola vez)
1. `cloud.oracle.com` → *Start for free* (pide tarjeta para verificar, **no cobra** en Always Free).
2. *Compute → Instances → Create*: imagen **Ubuntu 22.04**, shape **Ampere (ARM) `VM.Standard.A1.Flex`** con 2 OCPU / 12 GB.
3. *Generate a key pair* y **descargá la clave privada**. Anotá la **IP pública**.

```bash
chmod 400 ~/Descargas/tu-clave.key
ssh -i ~/Descargas/tu-clave.key ubuntu@140.x.x.x
```

### Parte B · Broker MQTT + PostgreSQL en Docker (Capa 2 + datos)
La infraestructura está dockerizada en el **compose de la raíz** (`docker-compose.yml`):
mosquitto con clave + **PostgreSQL 16** (única BD del sistema: alertas, nodos,
usuarios, auditoría). En la VM solo instalás Docker y lo levantás igual que en tu
laptop — **el mismo comando**:
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 python3-pip python3-opencv ffmpeg
sudo usermod -aG docker $USER && newgrp docker          # usar docker sin sudo
cd ~/iot && docker compose up -d                        # mosquitto-iot + pg-iot
docker compose ps                                       # esperar pg-iot "healthy"
```
> En una VM limpia podés usar `PG_PORT=5432` en el `.env` (en la laptop de
> desarrollo es 5433 porque el 5432 lo ocupa otro proyecto). El puerto de
> PostgreSQL **solo escucha en localhost**: nunca se abre a internet.
El `passwd` (usuario `esp32`) viaja con el `rsync` de la Parte C. Para cambiar la
clave: `docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/work eclipse-mosquitto:2 mosquitto_passwd -b /work/passwd esp32 <NUEVA_CLAVE>` y `docker compose restart`.

> Si una imagen futura de mosquitto se niega a cargar el `passwd` por el dueño,
> corré una vez: `sudo chown 1883:1883 capa2-red/passwd`.

### Parte C · Subir el código y las deps (Capas 3 + 4)
En tu laptop (sin la carpeta pesada `datos/`):
```bash
rsync -av -e "ssh -i ~/Descargas/tu-clave.key" --exclude datos --exclude '.git' \
  "/home/luis/Escritorio/SERVER IOT/Sistema-Integrado-IOT/" ubuntu@140.x.x.x:~/iot/
```
En la VM:
```bash
cd ~/iot
pip3 install -r requirements-nube.txt
# Si pip se queja de "externally-managed-environment" (Ubuntu 24.04+, PEP 668):
#   pip3 install --break-system-packages -r requirements-nube.txt
# En Ubuntu 22.04 (el shape recomendado arriba) pip3 funciona tal cual.
cat > .env <<'EOF'
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_USER=esp32
MQTT_PASS=iotmosquito2026
GATEWAY_HTTP_HOST=0.0.0.0
GATEWAY_HTTP_PORT=8090
PG_HOST=localhost
PG_PORT=5432
PG_USER=iot
PG_PASS=iotmosquito2026
PG_DB=iot_mosquito
SESSION_SECRET=cambia-por-un-secreto-largo-y-aleatorio
ADMIN_INIT_PASS=cambia-la-clave-del-admin
EOF

# Crear el esquema + usuario admin + parámetros del detector (idempotente).
# Si venís del PoC con SQLite, esto MIGRA datos/alerts.db y datos/monitor.db:
python3 capa3-procesamiento-servidor/database/migrate_sqlite_to_pg.py
```
> El `MQTT_USER`/`MQTT_PASS` debe coincidir con `capa2-red/passwd` (usuario `esp32`)
> y con el `config.h` del ESP32. `PG_PASS` debe coincidir con el compose (variable
> `PG_PASS` del mismo `.env` — el compose la lee). El dashboard exige login: entrá
> como `admin` con la clave de `ADMIN_INIT_PASS` y creá los operadores desde la
> pestaña Admin.

### Parte D · Dejarlo corriendo 24/7 (systemd)
```bash
# Gateway (capa 3) — espera a que PostgreSQL esté sano antes de arrancar
sudo tee /etc/systemd/system/iot-gateway.service >/dev/null <<EOF
[Unit]
After=docker.service
Requires=docker.service
[Service]
WorkingDirectory=/home/ubuntu/iot/capa3-procesamiento-servidor
ExecStartPre=/bin/sh -c 'until docker exec pg-iot pg_isready -q; do sleep 2; done'
ExecStart=/usr/bin/python3 gateway.py
Restart=always
User=ubuntu
[Install]
WantedBy=multi-user.target
EOF

# Dashboard (capa 4) — mismo pre-chequeo de la BD
sudo tee /etc/systemd/system/iot-dash.service >/dev/null <<EOF
[Unit]
After=docker.service
Requires=docker.service
[Service]
WorkingDirectory=/home/ubuntu/iot/capa4-aplicacion
ExecStartPre=/bin/sh -c 'until docker exec pg-iot pg_isready -q; do sleep 2; done'
ExecStart=/usr/bin/python3 serve.py 8000
Restart=always
User=ubuntu
[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now iot-gateway iot-dash
```
> Para probar a mano en una terminal (sin systemd): `./iniciar.sh nube`
> (levanta también la infra Docker y aplica las semillas si la BD está vacía).

### Parte E · Abrir los puertos (LOS DOS lados — footgun de Oracle)
1. **Security List** (web de Oracle): *Networking → VCN → Subnet → Security List → Add Ingress Rules*. Origen `0.0.0.0/0`, TCP, puertos **1883**, **8090**, **8000**.
2. **iptables en la VM:**
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 1883 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8090 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```
Probá: `http://140.x.x.x:8000` 🎉

---

## Limitaciones honestas
- **La laptop sigue siendo necesaria** mientras vigilás (es la cámara). Lo que ganás:
  broker, detector, BD y dashboard viven 24/7 en la nube, accesibles desde cualquier lado.
- **Disco:** los clips se acumulan. Con 200 GB de Oracle estás cómodo; conviene un cron
  que borre clips viejos (`find datos/clips -mtime +30 -delete`).
- **Seguridad:** con clave alcanza para un proyecto. Si lo dejás meses, pasá a TLS (8883)
  y autenticá también el `/upload`.

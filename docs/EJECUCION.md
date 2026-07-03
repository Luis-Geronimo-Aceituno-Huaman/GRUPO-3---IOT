# Cómo ejecutar el sistema

## Requisitos
- Docker + docker compose (broker + PostgreSQL).
- Python 3.11+ con `pip install -r requirements-nube.txt`
  (en Debian/Ubuntu con PEP 668: `pip3 install --break-system-packages -r requirements-nube.txt`).
- Un `.env` en la raíz (copiar de `.env.example` y completar).

## Arranque con un solo comando (recomendado)

`iniciar.sh` hace todo en orden: levanta Docker (broker + PostgreSQL), espera a
que la BD esté *healthy*, aplica esquema y semillas **solo la primera vez**
(usuario admin, parámetros del detector y del riesgo) y arranca los procesos.

```bash
./iniciar.sh                  # LOCAL: infra + gateway + dashboard + cámara (si hay webcam)
./iniciar.sh --simulador      # ídem + simulador de nodo ESP32 (:8200)
./iniciar.sh --sin-camara     # sin webcam (p. ej. probando solo con el simulador)
./iniciar.sh nube             # VM: infra + gateway + dashboard (sin cámara)
./iniciar.sh laptop           # laptop como cámara IP cuando el server vive en la nube
```

Ctrl+C detiene los procesos Python; los contenedores siguen (`docker compose down` para pararlos).

## Orden de arranque manual (si preferís paso a paso)

```bash
# 1. Infraestructura (broker con clave + PostgreSQL con esquema)
docker compose up -d                 # espera pg-iot "healthy" (docker compose ps)

# 2. Solo la primera vez: esquema/semillas
python3 capa3-procesamiento-servidor/database/migrate_sqlite_to_pg.py

# 3. Gateway (capa 3: receptor de ráfagas + detector + BD)
cd capa3-procesamiento-servidor && python3 gateway.py &

# 4. Dashboard (capa 4: API + SPA + jobs de monitoreo/riesgo)
cd ../capa4-aplicacion && python3 serve.py &     # http://localhost:8000

# 5. (opcional, pruebas) Simulador de nodo ESP32
cd ../tools/simulador_nodo && python3 app.py &   # http://localhost:8200

# 6. (opcional, con ESP32 real) La laptop como cámara IP para el nodo
cd ../../capa3-procesamiento-servidor && python3 cam_stream.py &  # webcam :8091 (solo LAN)
```

## Login

`http://localhost:8000` redirige a `login.html`. Usuario inicial: **admin** con
la clave de `ADMIN_INIT_PASS` del `.env` (el migrador lo crea). Desde la pestaña
**Admin**: crear operadores, ajustar parámetros del detector y del motor de riesgo.

## Comportamiento ante fallos

- **PostgreSQL caído**: `serve.py` arranca en modo degradado (APIs → 503 con
  mensaje claro); el gateway reintenta con backoff y avisa si pierde una alerta.
  Levantá la BD y reiniciá los procesos.
- **Broker caído**: paho reintenta solo; el dashboard sigue sirviendo lecturas.

## Producción (VM Oracle)

Ver `DESPLIEGUE.md`: rsync del código, compose en la VM, systemd con
`ExecStartPre=pg_isready` (orden: docker → gateway → dashboard), puertos
1883/8090/8000 abiertos (Security List + iptables). **Nunca abrir 5432/5433 ni
8091 a internet.**

## Verificación rápida (sin hardware)

1. `docker compose ps` → pg-iot healthy, mosquitto-iot up.
2. Abrir `:8200` → Iniciar nodo `esp32-99` → «Disparar alerta».
3. En `:8000` (login) → aparece la alerta `pendiente` con video y riesgo;
   el nodo sale en el mapa con su color.
4. Gestionarla con «Atender» → aparece en la pestaña **Atención** (con distrito,
   GPS y «Cómo llegar») para que el operador la cierre; marcarla «Falsa alarma»
   → se **elimina de la BD** y desaparece de tabla, mapa, KPIs y gráficos.

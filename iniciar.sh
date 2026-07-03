#!/usr/bin/env bash
# iniciar.sh — Lanzador ÚNICO del Sistema Integrado IoT.
#
# Levanta TODO en el orden correcto: infraestructura Docker (broker MQTT +
# PostgreSQL), semillas de la BD la primera vez, y luego los procesos Python
# (gateway con detector, dashboard, y opcionalmente cámara y simulador).
#
# Uso:
#   ./iniciar.sh                  # LOCAL (default): infra + gateway + dashboard + cámara
#   ./iniciar.sh nube             # NUBE/VM: infra + gateway + dashboard (sin cámara)
#   ./iniciar.sh laptop           # LAPTOP: solo la cámara (el server ya vive en la nube)
#
# Flags (combinables con el modo):
#   --sin-camara                  # local sin webcam (p. ej. probando con el simulador)
#   --simulador                   # además levanta el simulador de nodo ESP32 (:8200)
#
# Puertos: broker 1883 · dashboard 8000 · gateway 8090 · cámara 8091 · simulador 8200
# Para producción en la nube con systemd (sobrevive al cierre del SSH): ver DESPLIEGUE.md.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
C3="$DIR/capa3-procesamiento-servidor"
C4="$DIR/capa4-aplicacion"
cd "$DIR"

# ---------------- argumentos ----------------
MODE=local CAMARA=1 SIMULADOR=0
for arg in "$@"; do
  case "$arg" in
    local|nube|laptop) MODE="$arg" ;;
    --sin-camara)      CAMARA=0 ;;
    --simulador)       SIMULADOR=1 ;;
    -h|--help)         grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "argumento desconocido: $arg (usa --help)"; exit 1 ;;
  esac
done
[ "$MODE" = nube ] && CAMARA=0

# ---------------- .env (credenciales) ----------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[ENV] No había .env: lo creé desde .env.example."
  echo "[ENV] *** EDITA .env con tus claves reales (MQTT_PASS, PG_PASS, etc.) y volvé a correr. ***"
  exit 1
fi
set -a; . ./.env; set +a

# ---------------- dependencias Python ----------------
if [ "$MODE" = laptop ]; then
  python3 -c 'import cv2' 2>/dev/null || {
    echo "[DEPS] Falta OpenCV. Instala:  pip3 install -r requirements-laptop.txt"; exit 1; }
else
  python3 -c 'import fastapi, uvicorn, paho.mqtt.client, psycopg, cv2, bcrypt, itsdangerous, dotenv' 2>/dev/null || {
    echo "[DEPS] Faltan dependencias. Instala:  pip3 install -r requirements-nube.txt"
    echo "       (Debian/Ubuntu con PEP 668: agrega --break-system-packages)"; exit 1; }
fi

# ---------------- modo LAPTOP: solo cámara y listo ----------------
if [ "$MODE" = laptop ]; then
  echo ""
  echo "Laptop = cámara IP de la LAN (webcam para el ESP32)."
  echo "  webcam -> http://$(hostname).local:8091/snapshot.jpg"
  echo "  debug  -> http://localhost:8091/  (stream MJPEG)"
  echo "El gateway/dashboard corren en la nube (./iniciar.sh nube allá)."
  cd "$C3" && exec python3 cam_stream.py
fi

# ---------------- 1. Infraestructura Docker (broker + PostgreSQL) ----------------
echo "[1/4] Docker: broker MQTT + PostgreSQL..."
docker compose up -d

echo -n "[1/4] Esperando a que PostgreSQL esté healthy"
for i in $(seq 1 30); do
  st="$(docker inspect -f '{{.State.Health.Status}}' pg-iot 2>/dev/null || echo starting)"
  [ "$st" = healthy ] && break
  echo -n "."; sleep 2
done; echo ""
if [ "${st:-}" != healthy ]; then
  echo "[ERROR] PostgreSQL (pg-iot) no llegó a 'healthy'. Mirá: docker compose logs postgres"
  exit 1
fi
echo "[1/4] OK: broker :1883 · PostgreSQL :${PG_PORT:-5433} (solo localhost)"

# ---------------- 2. Primera vez: esquema + semillas (admin, parámetros) --------
echo "[2/4] Verificando la BD..."
if ! docker exec pg-iot psql -U "${PG_USER:-iot}" -d "${PG_DB:-iot_mosquito}" \
     -tAc "SELECT 1 FROM users LIMIT 1" 2>/dev/null | grep -q 1; then
  echo "[2/4] BD vacía: aplicando esquema + semillas (usuario admin, detector, riesgo)..."
  python3 "$C3/database/migrate_sqlite_to_pg.py"
else
  echo "[2/4] OK: la BD ya está inicializada."
fi

# ---------------- 3. Procesos Python ----------------
pids=() nombres=()
lanzar() {  # lanzar <nombre> <dir> <cmd...>
  local nombre="$1" dir="$2"; shift 2
  ( cd "$dir" && exec "$@" ) & pids+=($!); nombres+=("$nombre")
  echo "[3/4] $nombre en marcha (pid ${pids[-1]})"
}

lanzar "gateway (receptor + detector + BD)" "$C3" python3 gateway.py
lanzar "dashboard (API + web + monitoreo)"  "$C4" python3 serve.py

if [ "$CAMARA" = 1 ]; then
  if ls /dev/video* >/dev/null 2>&1; then
    lanzar "cámara IP (webcam :8091)" "$C3" python3 cam_stream.py
  else
    echo "[3/4] (sin webcam detectada: no levanto cam_stream; usa --simulador para probar)"
  fi
fi
[ "$SIMULADOR" = 1 ] && lanzar "simulador de nodo ESP32 (:8200)" "$DIR/tools/simulador_nodo" python3 app.py

trap 'echo; echo "Deteniendo procesos Python (la infra Docker sigue: docker compose down para pararla)..."; kill "${pids[@]}" 2>/dev/null || true' INT TERM

# ---------------- 4. Resumen ----------------
echo ""
echo "[4/4] Sistema en marcha (modo $MODE):"
echo "   dashboard : http://localhost:8000   (login admin / ADMIN_INIT_PASS del .env)"
echo "   gateway   : :8090/upload  (acá sube la ráfaga el ESP32)"
echo "   broker    : :1883 (con usuario/clave)"
[ "$CAMARA" = 1 ]    && echo "   cámara    : http://localhost:8091/ (si hay webcam)"
[ "$SIMULADOR" = 1 ] && echo "   simulador : http://localhost:8200"
if [ "$MODE" = nube ]; then
  echo "   ► Abrí en el firewall de la VM (Security List + iptables): 1883, 8090, 8000."
  echo "   ► Para que sobreviva al cierre del SSH usá systemd (DESPLIEGUE.md, Parte D)."
fi
echo "Ctrl+C detiene los procesos Python; los contenedores quedan corriendo."
wait

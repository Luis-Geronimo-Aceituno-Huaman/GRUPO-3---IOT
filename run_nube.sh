#!/usr/bin/env bash
# run_nube.sh — El "cerebro" que corre en la VM de la nube (Oracle/VPS).
#
# Levanta gateway + dashboard (capas 3 y 4). El broker mosquitto (capa 2) se instala
# y corre aparte como servicio del sistema (apt install mosquitto), NO desde aqui.
#
# Para PRODUCCION conviene systemd (sobrevive al cierre del SSH); ver DESPLIEGUE.md.
# Este script es para arrancar/probar todo a mano en una sola terminal.
#
# Requisitos:
#   1. Broker mosquitto corriendo y con clave (ver DESPLIEGUE.md, Parte B).
#   2. pip install -r requirements-nube.txt
#   3. Un .env en la raiz con MQTT_USER/MQTT_PASS (config.py lo lee solo).
#
# Flujo: ESP32 sube el jpegseq -> gateway :8090 -> detector -> alerts.db -> serve :8000.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
C3="$DIR/capa3-procesamiento-servidor"
C4="$DIR/capa4-aplicacion"

# Aviso si el broker no esta arriba (capa 2 = mosquitto en Docker).
if ! pgrep -x mosquitto >/dev/null 2>&1; then
  echo "[AVISO] No veo 'mosquitto' corriendo. Arrancalo con: (cd capa2-red && docker compose up -d)"
fi

pids=()
( cd "$C3" && python3 gateway.py ) &      # capa 3: recibe jpegseq + detector + BD
pids+=($!)
( cd "$C4" && python3 serve.py ) &        # capa 4: API + dashboard (:8000)
pids+=($!)

trap 'echo; echo "Deteniendo..."; kill "${pids[@]}" 2>/dev/null' INT TERM

echo ""
echo "Cerebro en marcha en la NUBE (gateway + dashboard)."
echo "  receptor de rafagas (ESP32 -> aqui): :8090/upload"
echo "  dashboard:                           http://<IP-PUBLICA>:8000"
echo "Recorda abrir en el firewall (Security List + iptables): 1883, 8090, 8000."
echo "NO abras el 8091 a internet: ese vive en la laptop (LAN)."
echo "Ctrl+C para detener gateway y dashboard (el broker sigue como servicio)."
wait

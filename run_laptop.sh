#!/usr/bin/env bash
# run_laptop.sh — Lo UNICO que corre en la laptop tras migrar el server a la nube.
#
# Expone la webcam de la laptop como "camara IP" en :8091. El ESP32, al detectar un
# mosquito, le pide aca una rafaga de fotos (por la LAN) y luego la sube al gateway
# que vive en la NUBE. La laptop ya NO graba clips, ni corre el detector, ni MQTT.
#
# Requisitos:
#   1. pip install -r requirements-laptop.txt   (solo OpenCV).
#   2. Una webcam disponible (CAM_INDEX=0 por defecto; export CAM_INDEX para cambiar).
#   3. mDNS/Avahi activo para que el ESP32 encuentre la laptop por nombre (.local).
#      En Debian/Ubuntu: sudo apt install avahi-daemon  (suele venir ya instalado).
#
# El gateway, el broker y el dashboard NO se levantan aca: ver run_nube.sh.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
C3="$DIR/capa3-procesamiento-servidor"

echo ""
echo "Laptop = camara IP de la LAN (webcam expuesta para el ESP32)."
echo "  webcam -> http://$(hostname).local:8091/snapshot.jpg"
echo "  debug  -> http://localhost:8091/  (stream MJPEG en el navegador)"
echo "El ESP32 jala la rafaga de aqui y la sube al gateway en la nube."
echo "Ctrl+C para detener."
echo ""

cd "$C3" && exec python3 cam_stream.py

# Capa 2 — Red (MQTT / Mosquitto)

El **broker Mosquitto** es la "central telefónica" que reparte los mensajes entre el
nodo (Capa 1), la cámara, el gateway (Capa 3) y el dashboard (Capa 4).

- Contrato de tópicos: **[MQTT_SPEC.md](MQTT_SPEC.md)**.
- Configuración del broker: **[mosquitto.conf](mosquitto.conf)** (`:1883`, con
  usuario/clave del archivo [passwd](passwd) — `allow_anonymous false`).

## Levantar el broker

El broker corre en **Docker** con el `docker-compose.yml` de la **raíz** del
proyecto (un solo compose orquesta broker + PostgreSQL); monta `mosquitto.conf`
y `passwd` de esta carpeta:

```bash
# desde la raíz del proyecto (o directamente ./iniciar.sh, que hace esto y más)
docker compose up -d mosquitto
```

Alternativa sin Docker (con Mosquitto instalado en el sistema):
```bash
mosquitto -c mosquitto.conf -v
```

Tópicos clave del flujo:
```
devices/<id>/alert            nodo  → cámara   (disparo: 3 ventanas TinyML seguidas)
devices/<id>/sensors|gps|status nodo → gateway (telemetría que enriquece la alerta)
devices/<id>/camera/clip      cámara → gateway (clip listo para analizar)
devices/<id>/camera/detection gateway → dashboard (alerta CONFIRMADA por el detector)
```

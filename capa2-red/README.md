# Capa 2 — Red (MQTT / Mosquitto)

El **broker Mosquitto** es la "central telefónica" que reparte los mensajes entre el
nodo (Capa 1), la cámara, el gateway (Capa 3) y el dashboard (Capa 4).

- Contrato de tópicos: **[MQTT_SPEC.md](MQTT_SPEC.md)**.
- Configuración del broker: **[mosquitto.conf](mosquitto.conf)** (demo local, `localhost:1883`, anónimo).

## Levantar el broker

**Windows** (con Mosquitto instalado):
```powershell
mosquitto -c mosquitto.conf -v
```

**Linux**:
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

"""
mqtt_ingest.py — Suscriptor MQTT del servidor de monitoreo.

Convierte lo que el ESP32 PUBLICA de verdad en filas de la BD (registro de nodos,
detecciones, heartbeats, anomalias). Ver el mapeo spec->real en config.py.

Handlers por topic:
  devices/+/alert      -> detections + (registro) + estado ONLINE   ["detection" del spec]
  nodes/+/heartbeat    -> heartbeats + actualiza nodes + ONLINE
  devices/+/status     -> telemetria/online; si online:false con razon -> anomalies
  nodes/+/status       -> eventos de self_monitor -> anomalies
  devices/+/sensors    -> cache (enriquecer, chip/turbidez no van al esquema del spec)
  devices/+/gps        -> cache
  devices/+/audio      -> cache (confianza de la ultima ventana)

Registro automatico (spec NODE REGISTRY): CUALQUIER mensaje de un node_name nuevo
lo da de alta en la tabla nodes con first_seen/last_seen.
"""

from __future__ import annotations

import json

import paho.mqtt.client as mqtt

import config as cfg
from db import unix_to_iso, now_iso, STATUS_ONLINE


class MqttIngest:
    def __init__(self, db, on_detection=None):
        """db: MonitorDB.  on_detection(node_name, payload): hook opcional para
        encadenar el 'alert pipeline' (lo pesado -grabar/analizar video- ya lo hace
        gateway.py; aqui solo se registra y se puede notificar)."""
        self.db = db
        self.on_detection = on_detection
        self.cache = {}   # node -> {"sensors":..,"gps":..,"audio":..} para enriquecer

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=cfg.MQTT_CLIENT_ID)
        if cfg.MQTT_USER:
            self.client.username_pw_set(cfg.MQTT_USER, cfg.MQTT_PASS)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    # ---------------------------------------------------------------- ciclo
    def start(self):
        # connect_async + loop_start: no lanza excepcion si el broker aun no esta;
        # paho reintenta solo en su hilo de red. Asi el servidor web sigue arriba
        # aunque el broker se levante despues.
        self.client.connect_async(cfg.MQTT_HOST, cfg.MQTT_PORT, keepalive=60)
        self.client.loop_start()    # hilo propio de red (no bloquea el proceso)
        print(f"[MQTT] conectando a {cfg.MQTT_HOST}:{cfg.MQTT_PORT} como '{cfg.MQTT_CLIENT_ID}'")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            print(f"[MQTT] fallo de conexion rc={rc}")
            return
        for t in cfg.SUBSCRIPTIONS:
            client.subscribe(t, qos=1)
            print(f"[MQTT]   suscrito -> {t}")

    # ---------------------------------------------------------------- mensajes
    def _on_message(self, client, userdata, msg):
        node = cfg.node_from_topic(msg.topic)
        try:
            payload = json.loads(msg.payload.decode())
            if not isinstance(payload, dict):
                payload = {"value": payload}
        except Exception:
            payload = {"raw": msg.payload.decode(errors="replace")}

        # node_name del payload manda sobre el del topic (en el firmware coinciden,
        # pero el alert trae node_name explicito y es la fuente mas fiable).
        node = payload.get("node_name") or node

        # Registro automatico + last_seen en CUALQUIER mensaje.
        if self.db.register_node(node):
            print(f"[REG] nodo nuevo registrado: {node}")

        topic = msg.topic
        try:
            if topic.endswith("/alert"):
                self._handle_alert(node, payload)
            elif topic.endswith("/heartbeat"):
                self._handle_heartbeat(node, payload)
            elif topic.startswith("devices/") and topic.endswith("/status"):
                self._handle_dev_status(node, payload)
            elif topic.startswith("nodes/") and topic.endswith("/status"):
                self._handle_node_status(node, payload)
            elif topic.endswith("/sensors"):
                self.cache.setdefault(node, {})["sensors"] = payload
                self._handle_sensors(node, payload)
            elif topic.endswith("/gps"):
                self.cache.setdefault(node, {})["gps"] = payload
                self._handle_gps(node, payload)
            elif topic.endswith("/audio"):
                self.cache.setdefault(node, {})["audio"] = payload
        except Exception as e:
            print(f"[MQTT] error procesando {topic}: {e}")

    # ---- handlers -----------------------------------------------------------
    def _handle_alert(self, node, p):
        """devices/<id>/alert = la DETECCION del spec. El payload no trae el umbral,
        asi que usamos el ultimo threshold conocido del nodo (lo reporta el heartbeat)."""
        ts = unix_to_iso(p.get("timestamp")) or now_iso()
        score = p.get("confidence")
        threshold_used = self.db.node_threshold(node)
        seq = p.get("seq")
        det_id = self.db.insert_detection(node, ts, score, threshold_used, seq)
        # El status del nodo lo decide el job de heartbeat (spec): una deteccion
        # actualiza last_seen (ya hecho en register_node) pero NO el last_heartbeat,
        # para no enmascarar un nodo que dejo de latir.
        print(f"[DET] {node}: score={score} thr={threshold_used} seq={seq} (id={det_id})")
        if self.on_detection:
            try:
                self.on_detection(node, p)
            except Exception as e:
                print(f"[DET] hook on_detection fallo: {e}")

    def _handle_heartbeat(self, node, p):
        """nodes/<name>/heartbeat -> tabla heartbeats + columnas vivas del nodo."""
        ts = unix_to_iso(p.get("timestamp")) or now_iso()
        battery = p.get("battery_pct")
        temp = p.get("chip_temp_c")
        uptime = p.get("uptime_s")
        threshold = p.get("threshold")
        status = p.get("status", "alive")
        self.db.insert_heartbeat(node, ts, battery, temp, uptime, threshold, status)
        self.db.update_node_fields(
            node, last_heartbeat=ts, battery_pct=battery, chip_temp_c=temp,
            threshold=threshold, uptime_s=uptime,
        )
        self.db.set_status(node, STATUS_ONLINE)
        print(f"[HB ] {node}: temp={temp}C uptime={uptime}s thr={threshold} bat={battery}")

    def _handle_dev_status(self, node, p):
        """devices/<id>/status: online/telemetria. Si llega online:false con razon
        (reinicio por comando, LWT, etc.) lo guardamos como anomalia/evento."""
        if p.get("online") is False:
            reason = p.get("reason", "offline")
            self.db.insert_anomaly(node, now_iso(), "offline", reason)
            print(f"[ANO] {node}: offline ({reason})")
        # telemetria util (rssi/heap/uptime) -> no esta en el esquema del spec; se
        # ignora salvo que quieras extender la tabla nodes. Se deja como cache.
        else:
            self.cache.setdefault(node, {})["status"] = p

    def _handle_sensors(self, node, p):
        """devices/<id>/sensors -> tabla sensor_readings (histórico para el motor
        de riesgo) + nodes.last_reading. Aditivo: el ESP32 real manda turb_raw/
        turb_v/temp_c; humedad/ph/nivel_agua vienen del simulador o nodos futuros
        (caen en columnas propias) y cualquier clave desconocida va a extra JSONB."""
        try:
            audio = self.cache.get(node, {}).get("audio", {})
            reading = dict(p)
            if audio.get("mosquito_conf") is not None:
                reading.setdefault("audio_conf", audio.get("mosquito_conf"))
            self.db.insert_reading(node, reading)
        except Exception as e:
            print(f"[SEN] {node}: no se pudo guardar la lectura: {e}")

    def _handle_gps(self, node, p):
        """devices/<id>/gps -> posición del nodo en la tabla nodes (solo con fix:
        el firmware solo publica si g_gpsFix, pero validamos igual)."""
        lat, lon = p.get("lat"), p.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            try:
                self.db.update_node_fields(node, lat=lat, lon=lon, alt=p.get("alt"))
            except Exception as e:
                print(f"[GPS] {node}: no se pudo actualizar posición: {e}")

    def _handle_node_status(self, node, p):
        """nodes/<name>/status: eventos de self_monitor (reservado en el firmware).
        Cuando el nodo empiece a publicar aqui, cada evento queda como anomalia."""
        type_ = p.get("type") or p.get("event") or "status"
        detail = p.get("detail") or json.dumps(p, ensure_ascii=False)
        self.db.insert_anomaly(node, now_iso(), type_, detail)
        print(f"[ANO] {node}: {type_} -> {detail}")

"""
heartbeat_monitor.py — Job de liveness en segundo plano (spec: HEARTBEAT MONITORING).

Cada HEARTBEAT_CHECK_INTERVAL_S (5 min por defecto) recorre TODOS los nodos y
recalcula su status segun cuanto hace que se recibio su ultimo heartbeat:

    < 30 min            -> ONLINE
    >= 30 min, < 24 h   -> OFFLINE
    >= 24 h             -> COMPROMISED
    sin heartbeat aun   -> UNKNOWN (recien registrado, aun no late)

Cada cambio de status lo escribe MonitorDB.set_status() en status_history, de modo
que queda el rastro de cuando un nodo cayo y cuando volvio.
"""

from __future__ import annotations

import threading
from datetime import datetime

import config as cfg
from db import (now_iso, STATUS_ONLINE, STATUS_OFFLINE, STATUS_COMPROMISED,
                STATUS_UNKNOWN)


def _age_seconds(iso_ts: str | None) -> float | None:
    """Segundos transcurridos desde un timestamp ISO 8601. None si no hay timestamp."""
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts)
    except ValueError:
        return None
    return (datetime.now(dt.tzinfo) - dt).total_seconds()


def classify(last_heartbeat: str | None) -> str:
    age = _age_seconds(last_heartbeat)
    if age is None:
        return STATUS_UNKNOWN
    if age >= cfg.COMPROMISED_AFTER_S:
        return STATUS_COMPROMISED
    if age >= cfg.OFFLINE_AFTER_S:
        return STATUS_OFFLINE
    return STATUS_ONLINE


class HeartbeatMonitor:
    def __init__(self, db, interval_s: int | None = None):
        self.db = db
        self.interval = interval_s or cfg.HEARTBEAT_CHECK_INTERVAL_S
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="hb-monitor")
        self._thread.start()
        print(f"[HBJOB] job de liveness cada {self.interval}s "
              f"(OFFLINE>{cfg.OFFLINE_AFTER_S}s, COMPROMISED>{cfg.COMPROMISED_AFTER_S}s)")

    def stop(self):
        self._stop.set()

    def _run(self):
        # Primera pasada inmediata, luego cada 'interval' (o hasta stop()).
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as e:
                print(f"[HBJOB] error en la pasada: {e}")
            self._stop.wait(self.interval)

    def check_once(self):
        """Recalcula y aplica el status de cada nodo. Devuelve la lista de cambios."""
        changes = []
        for node in self.db.all_nodes():
            new_status = classify(node["last_heartbeat"])
            if new_status != node["status"]:
                self.db.set_status(node["node_name"], new_status)
                changes.append((node["node_name"], node["status"], new_status))
                print(f"[HBJOB] {node['node_name']}: {node['status']} -> {new_status}")
        if changes:
            print(f"[HBJOB] {now_iso()}: {len(changes)} cambio(s) de status")
        return changes

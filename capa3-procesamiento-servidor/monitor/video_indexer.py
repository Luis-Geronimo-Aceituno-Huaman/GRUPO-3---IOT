"""
video_indexer.py — Llena la tabla 'videos' del Video Log (spec TAB 4).

El ESP32 sube su rafaga de fotos por HTTP SOLO al gateway (:8090), que la arma
como datos/clips/<node>/<stamp>.webm. Para no chocar con ese puerto ni tocar el
firmware, el monitor INDEXA esa carpeta: cada .webm nuevo se registra en 'videos'
con su nodo, fecha de recepcion (mtime del archivo) y tamano.

Ademas, jpegseq_to_webm() permite que el PROPIO /upload del monitor (web.py)
reciba la misma rafaga jpegseq del ESP32 si algun dia se le apunta a este puerto,
cumpliendo literalmente "video received via plain HTTP POST endpoint" del spec.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path

import config as cfg


def _iso_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def index_once(db) -> int:
    """Recorre CLIPS_DIR/<node>/*.webm e inserta los que falten. Devuelve cuantos
    nuevos registro."""
    base = Path(cfg.CLIPS_DIR)
    if not base.exists():
        return 0
    nuevos = 0
    for node_dir in base.iterdir():
        if not node_dir.is_dir():
            continue
        node = node_dir.name
        for clip in node_dir.glob("*.webm"):
            rel = str(clip.relative_to(cfg.DATOS))   # ruta estable para enlazar/descargar
            if db.video_exists(rel):
                continue
            # El nodo debe existir en la tabla nodes (FK). Si el video aparece antes
            # que cualquier mensaje MQTT, lo registramos igual.
            db.register_node(node)
            size_kb = max(1, clip.stat().st_size // 1024)
            if db.insert_video(node, _iso_from_mtime(clip), rel, size_kb):
                nuevos += 1
    if nuevos:
        print(f"[VIDX] {nuevos} video(s) nuevo(s) indexado(s)")
    return nuevos


class VideoIndexer:
    """Hilo que re-indexa la carpeta de clips cada VIDEO_INDEX_INTERVAL_S."""

    def __init__(self, db, interval_s: int | None = None):
        self.db = db
        self.interval = interval_s or cfg.VIDEO_INDEX_INTERVAL_S
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="video-indexer")
        self._thread.start()
        print(f"[VIDX] indexando {cfg.CLIPS_DIR} cada {self.interval}s")

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                index_once(self.db)
            except Exception as e:
                print(f"[VIDX] error indexando: {e}")
            self._stop.wait(self.interval)


def jpegseq_to_webm(device: str, data: bytes, seconds: float) -> Path | None:
    """Arma una rafaga jpegseq del ESP32 ([4B len][jpeg]...) como .webm en
    UPLOAD_DIR/<device>/. Mismo formato que gateway.handle_jpegseq. Devuelve la
    ruta del .webm o None si no habia frames validos."""
    import cv2
    import numpy as np

    frames = []
    i, n = 0, len(data)
    while i + 4 <= n:
        ln = int.from_bytes(data[i:i + 4], "big")
        i += 4
        if ln <= 0 or i + ln > n:
            break
        img = cv2.imdecode(np.frombuffer(data[i:i + ln], dtype=np.uint8), cv2.IMREAD_COLOR)
        i += ln
        if img is not None:
            frames.append(img)
    if not frames:
        return None

    out_dir = Path(cfg.UPLOAD_DIR) / device
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"{stamp}.webm"
    h, w = frames[0].shape[:2]
    fps = max(1.0, len(frames) / seconds) if seconds > 0 else 10.0
    wr = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"VP80"), fps, (w, h))
    for f in frames:
        if f.shape[1] != w or f.shape[0] != h:
            f = cv2.resize(f, (w, h))
        wr.write(f)
    wr.release()
    return out_path

"""
detector.py — Compuerta de vision por MOVIMIENTO (mejorada, params desde BD).

Deteccion clasica de mosquitos en movimiento: resta de fondo (MOG2) + flujo
optico (Farneback) + filtrado de blobs por forma/tamano + tracker de centroides
con validacion de trayectoria/velocidad + persistencia temporal + agregacion con
histeresis. No usa ningun modelo ni pesos: solo OpenCV + numpy.

Novedades de la ampliacion:
  * TODOS los parametros viven en la tabla detector_params (PostgreSQL) y se
    RECARGAN al inicio de cada analisis de clip (hot-reload sin reiniciar el
    gateway; 1 query por clip). Si la BD no responde, se usan los DEFAULTS de
    este modulo: el detector NUNCA deja de analizar.
  * Denoising bilateral opcional (use_bilateral): preserva los bordes de blobs
    pequenos mejor que el blur gaussiano. (fastNlMeans se descarto: demasiado
    caro para la VM ARM.)
  * CLAHE opcional (clahe_enabled): robustez ante cambios de iluminacion.
  * Umbral de flujo ADAPTATIVO (noise_percentile): el minimo de flujo optico se
    eleva al percentil-N del ruido de movimiento del frame, para que el viento/
    ruido global no produzca falsos positivos. 0 = apagado (flow_min fijo).
  * Tracker de centroides con ID persistente + trayectoria: valida VELOCIDAD
    (vel_min/max_px_s) y nº de puntos de trayectoria antes de confirmar.
  * flow_downscale: calcula el Farneback a resolucion reducida (ahorro ~n² de
    CPU en ARM) y reescala la magnitud a px reales.

Interfaz publica (INTACTA):
    from detector import VisionGate
    gate = VisionGate()
    verdict = gate.analyze_video("clip.webm")   # -> Verdict(detected, ...)

Uso por consola:
    python detector.py ruta/al/video.(webm|mp4)
"""

from __future__ import annotations

import sys
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent

# ─── DEFAULTS (fallback si PostgreSQL no responde; espejo de la semilla) ──────
DEFAULTS = {
    "umbral_mosquito": 1,        # minimo de objetos para "mosquito"
    "umbral_enjambre": 10,       # minimo para "enjambre"
    "area_min": 10,              # area minima de un blob (px^2)
    "area_max": 800,             # area maxima — descarta rostros/fondo grande
    "aspect_min": 0.2,           # ratio w/h minimo
    "aspect_max": 5.0,           # ratio w/h maximo
    "max_frame_ratio": 0.02,     # blob no puede ocupar mas del 2% del frame
    "circularidad_min": 0.1,     # circularidad minima del contorno
    "persistencia_min": 8,       # frames consecutivos para confirmar deteccion
    "dist_max": 40,              # px maximo entre frames (matching de blobs)
    "max_movimiento_total": 0.05,  # movimiento total >5% del frame -> objeto grande
    "mov_min": 12,               # px que un blob debe desplazarse en total
    "flow_min": 0.6,             # magnitud media de flujo optico minima (px/frame)
    "ema_alpha": 0.08,           # suavizado de la confianza
    "conf_on": 0.70,             # confianza para ENCENDER la alerta (histeresis)
    "conf_off": 0.30,            # confianza para APAGAR la alerta
    "conf_min_alerta": 0.70,     # confianza pico minima para ACEPTAR la alerta
    "mask_threshold": 200,       # umbral binario de la mascara MOG2
    "mog2_history": 500,
    "mog2_var_threshold": 50,
    "proc_w": 640,
    "proc_h": 480,
    # mejoras (apagadas/neutras por defecto)
    "use_bilateral": 0,
    "clahe_enabled": 0,
    "noise_percentile": 0,
    "vel_min_px_s": 0,
    "vel_max_px_s": 0,
    "trayectoria_min_puntos": 0,
    "flow_downscale": 1,
}

_INT_KEYS = {"umbral_mosquito", "umbral_enjambre", "persistencia_min",
             "mask_threshold", "mog2_history", "mog2_var_threshold",
             "proc_w", "proc_h", "trayectoria_min_puntos", "flow_downscale"}


class DetectorConfig:
    """Parametros del detector. `load()` los trae de detector_params (BD) con
    fallback a DEFAULTS — el gateway analiza clips aunque la BD este caida."""

    def __init__(self, params: dict | None = None):
        merged = {**DEFAULTS, **(params or {})}
        for k, v in merged.items():
            setattr(self, k, int(v) if k in _INT_KEYS else float(v)
                    if isinstance(v, (int, float)) else v)
        self.proc_size = (self.proc_w, self.proc_h)

    @classmethod
    def load(cls) -> "DetectorConfig":
        try:
            from database import get_pool
            with get_pool().connection() as conn:
                rows = conn.execute(
                    "SELECT key, value_num FROM detector_params"
                ).fetchall()
            params = {r["key"]: r["value_num"] for r in rows
                      if r["value_num"] is not None}
            if params:
                return cls(params)
        except Exception as e:
            print(f"[VISION] detector_params no disponible ({e}); usando defaults.")
        return cls()


@dataclass
class Verdict:
    """Resultado de analizar un video. Mismos campos que la compuerta anterior."""
    detected: bool
    top_class: object
    total_detections: int
    max_confidence: float
    per_class: dict = field(default_factory=dict)
    frames_processed: int = 0
    frames_with_detection: int = 0
    annotated_path: object = None
    summary: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class MosquitoDetector:
    """Detector por movimiento, frame a frame (headless, sin GUI)."""

    def __init__(self, cfg: DetectorConfig | None = None, fps: float = 10.0):
        self.cfg = cfg or DetectorConfig.load()
        self.fps = max(1.0, fps)
        c = self.cfg
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=c.mog2_history, varThreshold=c.mog2_var_threshold,
            detectShadows=False,
        )
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self.clahe = (cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                      if c.clahe_enabled else None)
        self.blob_historia = {}
        self.frame_count = 0
        self._next_blob_id = 0
        self.prev_gray = None
        # agregacion temporal
        self.confianza = 0.0
        self.conteo_ema = 0.0
        self.alerta = False

    # ------------------------------------------------------------- pipeline
    def _preprocesar(self, frame):
        """Gris (+CLAHE opcional) + denoising configurable."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.clahe is not None:
            gray = self.clahe.apply(gray)
        if self.cfg.use_bilateral:
            # bilateral: suaviza el ruido del sensor SIN borrar el borde de un
            # blob de 3-6 px (el gaussiano si lo difumina)
            blur = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=5)
        else:
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
        return gray, blur

    def _flujo(self, gray):
        """Flujo optico denso; opcionalmente a resolucion reducida (ARM)."""
        if self.prev_gray is None:
            self.prev_gray = gray
            return None
        ds = max(1, int(self.cfg.flow_downscale))
        if ds > 1:
            h, w = gray.shape
            small_prev = cv2.resize(self.prev_gray, (w // ds, h // ds))
            small_cur = cv2.resize(gray, (w // ds, h // ds))
            flow = cv2.calcOpticalFlowFarneback(
                small_prev, small_cur, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2) * ds  # px reales
            mag = cv2.resize(mag, (w, h))
        else:
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        self.prev_gray = gray
        return mag

    def procesar(self, frame):
        """Procesa un frame. Devuelve (n_confirmados, estado, confianza)."""
        c = self.cfg
        self.frame_count += 1
        h, w = frame.shape[:2]
        area_frame = h * w

        gray, blur = self._preprocesar(frame)
        flow_mag = self._flujo(gray)

        mask = self.bg_subtractor.apply(blur)
        mask = cv2.erode(mask, self.kernel, iterations=1)
        mask = cv2.dilate(mask, self.kernel, iterations=2)
        _, mask = cv2.threshold(mask, c.mask_threshold, 255, cv2.THRESH_BINARY)

        # Filtro anti-objeto-grande
        movimiento_total = cv2.countNonZero(mask) / area_frame
        if movimiento_total > c.max_movimiento_total:
            self.blob_historia = {}
            confianza, _ = self._agregar(0)
            return 0, "OBJETO GRANDE", confianza

        # Umbral de flujo ADAPTATIVO: si el frame entero "vibra" (viento, camara
        # inestable), el minimo exigido sube al percentil-N del ruido de fondo.
        flow_thr = c.flow_min
        if flow_mag is not None and c.noise_percentile > 0:
            flow_thr = max(c.flow_min,
                           float(np.percentile(flow_mag, c.noise_percentile)))

        contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detecciones = []
        for cnt in contornos:
            area = cv2.contourArea(cnt)
            if not (c.area_min < area < c.area_max):
                continue
            if area / area_frame > c.max_frame_ratio:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = bw / bh if bh > 0 else 0
            if not (c.aspect_min < aspect < c.aspect_max):
                continue
            perimetro = cv2.arcLength(cnt, True)
            circularidad = (4 * np.pi * area / (perimetro ** 2)) if perimetro > 0 else 0
            if circularidad < c.circularidad_min:
                continue
            if flow_mag is not None:
                region = flow_mag[y:y + bh, x:x + bw]
                flujo_medio = float(region.mean()) if region.size > 0 else 0.0
                if flujo_medio < flow_thr:
                    continue
            cx = x + bw // 2
            cy = y + bh // 2
            detecciones.append((x, y, bw, bh, area, circularidad, cx, cy))

        confirmadas, _candidatas = self._actualizar_persistencia(detecciones)
        n = len(confirmadas)

        if n >= c.umbral_enjambre:
            estado = "ENJAMBRE"
        elif n >= c.umbral_mosquito:
            estado = "MOSQUITO"
        else:
            estado = "LIMPIO"

        confianza, _sev = self._agregar(n)
        return n, estado, confianza

    def _agregar(self, n):
        c = self.cfg
        detectado = 1.0 if n >= c.umbral_mosquito else 0.0
        self.confianza = c.ema_alpha * detectado + (1 - c.ema_alpha) * self.confianza
        self.conteo_ema = c.ema_alpha * n + (1 - c.ema_alpha) * self.conteo_ema
        if not self.alerta and self.confianza >= c.conf_on:
            self.alerta = True
        elif self.alerta and self.confianza < c.conf_off:
            self.alerta = False
        severidad = ("ENJAMBRE" if self.conteo_ema >= c.umbral_enjambre else "MOSQUITO") \
            if self.alerta else "LIMPIO"
        return self.confianza, severidad

    # --------------------------------------------------- tracker de centroides
    def _valida_track(self, info) -> bool:
        """Validaciones NUEVAS sobre el track (ademas de frames+desplazamiento):
        velocidad media px/s dentro de rango y trayectoria con puntos minimos.
        Cada filtro esta apagado si su parametro es 0 (retrocompat)."""
        c = self.cfg
        tray = info["tray"]
        if c.trayectoria_min_puntos > 0 and len(tray) < c.trayectoria_min_puntos:
            return False
        if (c.vel_min_px_s > 0 or c.vel_max_px_s > 0) and len(tray) >= 2:
            # velocidad media = longitud del camino recorrido / tiempo del track
            path = sum(
                ((tray[i][0] - tray[i - 1][0]) ** 2 +
                 (tray[i][1] - tray[i - 1][1]) ** 2) ** 0.5
                for i in range(1, len(tray)))
            dur_s = (len(tray) - 1) / self.fps
            vel = path / dur_s if dur_s > 0 else 0.0
            if c.vel_min_px_s > 0 and vel < c.vel_min_px_s:
                return False        # demasiado lento: ruido casi estatico
            if c.vel_max_px_s > 0 and vel > c.vel_max_px_s:
                return False        # demasiado rapido: objeto cruzando/artefacto
        return True

    def _actualizar_persistencia(self, detecciones):
        c = self.cfg
        usados = set()
        nueva_historia = {}
        confirmadas = []
        candidatas = []
        for det in detecciones:
            cx, cy = det[6], det[7]
            mejor_id = None
            mejor_dist = c.dist_max
            for bid, info in self.blob_historia.items():
                if bid in usados:
                    continue
                dist = ((cx - info["cx"]) ** 2 + (cy - info["cy"]) ** 2) ** 0.5
                if dist < mejor_dist:
                    mejor_dist = dist
                    mejor_id = bid
            if mejor_id is not None:
                usados.add(mejor_id)
                prev = self.blob_historia[mejor_id]
                frames = prev["frames"] + 1
                cx0, cy0 = prev["cx0"], prev["cy0"]
                desp = ((cx - cx0) ** 2 + (cy - cy0) ** 2) ** 0.5
                desp_max = max(prev["desp_max"], desp)
                tray = prev["tray"][-59:] + [(cx, cy)]   # trayectoria acotada
            else:
                self._next_blob_id += 1
                mejor_id = self._next_blob_id
                frames = 1
                cx0, cy0 = cx, cy
                desp_max = 0.0
                tray = [(cx, cy)]
            info = {
                "cx": cx, "cy": cy, "cx0": cx0, "cy0": cy0,
                "frames": frames, "desp_max": desp_max, "tray": tray,
            }
            nueva_historia[mejor_id] = info
            if (frames >= c.persistencia_min and desp_max >= c.mov_min
                    and self._valida_track(info)):
                confirmadas.append(det)
            else:
                candidatas.append(det)
        self.blob_historia = nueva_historia
        return confirmadas, candidatas


class VisionGate:
    """Compuerta de vision por movimiento (MOG2 + flujo optico). No usa modelo."""

    def __init__(self):
        print("[VISION] Detector por MOVIMIENTO (MOG2 + flujo optico), sin modelo.")

    def analyze_video(self, video_path, write_annotated: bool = False) -> Verdict:
        """Analiza TODO el clip (archivo) y emite el veredicto. Recarga los
        parametros de la BD ANTES de cada analisis (hot-reload por clip)."""
        video_path = str(video_path)
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return Verdict(False, None, 0, 0.0,
                           summary=f"No se pudo abrir el video: {video_path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 10.0

        def _frames():
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    yield frame
            finally:
                cap.release()

        return self._run(_frames(), fps=fps)

    def analyze_frames(self, frames, fps: float = 10.0) -> Verdict:
        """Analiza una secuencia de fotogramas BGR ya decodificados (lista o
        generador). Lo usa el gateway cuando el ESP32 sube una rafaga de JPEGs."""
        return self._run(iter(frames), fps=fps)

    def _run(self, frame_iter, fps: float = 10.0) -> Verdict:
        """Pasa cada fotograma por el detector de movimiento y arma el veredicto."""
        cfg = DetectorConfig.load()            # hot-reload: 1 query por clip
        det = MosquitoDetector(cfg, fps=fps)
        frames = 0
        frames_con = 0          # frames con >=1 deteccion confirmada
        total_obj = 0           # suma de objetos confirmados por frame
        max_obj = 0             # pico de objetos en un frame
        alerta_disparada = False
        conf_max = 0.0

        for frame in frame_iter:
            if frame is None:
                continue
            if frame.shape[1] != cfg.proc_size[0] or frame.shape[0] != cfg.proc_size[1]:
                frame = cv2.resize(frame, cfg.proc_size)
            n, _estado, confianza = det.procesar(frame)
            frames += 1
            if n >= cfg.umbral_mosquito:
                frames_con += 1
                total_obj += n
            max_obj = max(max_obj, n)
            if det.alerta:
                alerta_disparada = True
            conf_max = max(conf_max, confianza)

        # POSITIVO solo si: (1) la confianza por histeresis (EMA) se encendio
        # -movimiento SOSTENIDO ~2s, no un estallido breve de blobs- Y (2) la
        # confianza pico SUPERA el minimo exigido.
        hay = alerta_disparada and conf_max >= cfg.conf_min_alerta
        enjambre = hay and max_obj >= cfg.umbral_enjambre
        top_class = ("Mosquito Swarm" if enjambre else "Mosquito") if hay else None

        per_class = {}
        if hay:
            per_class[top_class] = {"count": total_obj, "avg_conf": round(conf_max, 3)}

        return Verdict(
            detected=hay,
            top_class=top_class,
            total_detections=total_obj if hay else 0,
            max_confidence=round(conf_max, 3),
            per_class=per_class,
            frames_processed=frames,
            frames_with_detection=frames_con,
            annotated_path=None,
            summary=self._build_summary(hay, top_class, frames, frames_con,
                                        max_obj, conf_max),
        )

    @staticmethod
    def _build_summary(hay, top_class, frames, frames_con, max_obj, conf_max) -> str:
        if hay:
            head = f"POSITIVO - {top_class} (pico {max_obj} obj, {frames_con} frames con deteccion)"
        else:
            head = "NEGATIVO - sin movimiento tipo mosquito"
        return (f"{head}\nFrames: {frames} (con deteccion: {frames_con})  "
                f"confianza max: {conf_max:.0%}")


def main():
    if len(sys.argv) < 2:
        print("Uso: python detector.py <ruta_video.(webm|mp4)>")
        sys.exit(1)
    gate = VisionGate()
    verdict = gate.analyze_video(sys.argv[1])
    print(verdict.summary)
    print("\nJSON:")
    print(verdict.to_json())


if __name__ == "__main__":
    main()

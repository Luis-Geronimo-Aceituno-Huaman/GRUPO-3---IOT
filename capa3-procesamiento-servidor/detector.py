"""
detector.py — Compuerta de vision por MOVIMIENTO.

Deteccion clasica de mosquitos en movimiento (de `mosquito_veredicto_video.py`):
resta de fondo (MOG2) + flujo optico (Farneback) + filtrado de blobs por
forma/tamano + persistencia temporal + agregacion con histeresis. No usa ningun
modelo ni pesos: solo OpenCV + numpy.

Interfaz publica:
    from detector import VisionGate
    gate = VisionGate()                       # no carga ningun modelo
    verdict = gate.analyze_video("clip.webm") # -> Verdict(detected, top_class, ...)

Clases reportadas (las del proyecto):
  - "Mosquito"        (>=1 objeto en movimiento confirmado)
  - "Mosquito Swarm"  (>= UMBRAL_ENJAMBRE objetos: enjambre)

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

# ─── PARAMETROS DE DETECCION (de mosquito_veredicto_video.py) ─────────────────
UMBRAL_MOSQUITO = 1      # minimo de objetos para considerar "mosquito"
UMBRAL_ENJAMBRE = 10     # minimo para "enjambre"

AREA_MIN = 10            # area minima de un blob (px^2)
AREA_MAX = 800           # area maxima — descarta rostros/fondo grande
ASPECT_MIN = 0.2         # ratio w/h minimo
ASPECT_MAX = 5.0         # ratio w/h maximo
MAX_FRAME_RATIO = 0.02   # blob no puede ocupar mas del 2% del frame

PERSISTENCIA_MIN = 8     # frames consecutivos para confirmar deteccion
DIST_MAX = 40            # px maximo que un blob puede moverse entre frames (seguimiento)
MAX_MOVIMIENTO_TOTAL = 0.05  # si el movimiento total supera 5% del frame -> objeto grande
MOV_MIN = 12             # px que un blob debe desplazarse para ser mosquito
FLOW_MIN = 0.6           # magnitud media de flujo optico minima en el blob (px/frame)

EMA_ALPHA = 0.08         # suavizado de la confianza (menor = mas estable)
CONF_ON = 0.70           # confianza para ENCENDER la alerta (histeresis)
CONF_OFF = 0.30          # confianza para APAGAR la alerta (histeresis)

FRAMES_MIN_VEREDICTO = 5  # nº min. de frames con deteccion confirmada para "HAY MOSQUITOS"

# Confianza MINIMA (0.0-1.0) que debe superar la alerta para ACEPTARSE y guardarse.
# La confianza es el pico de la EMA (movimiento sostenido). Subela para ser mas
# estricto (menos falsos positivos); bajala si se escapan mosquitos reales.
CONF_MIN_ALERTA = 0.70

PROC_SIZE = (640, 480)    # los parametros estan calibrados a este tamano
# ─────────────────────────────────────────────────────────────────────────────


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

    def __init__(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=50, detectShadows=False
        )
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self.blob_historia = {}
        self.frame_count = 0
        self._next_blob_id = 0
        self.prev_gray = None
        # agregacion temporal
        self.confianza = 0.0
        self.conteo_ema = 0.0
        self.alerta = False

    def procesar(self, frame):
        """Procesa un frame. Devuelve (n_confirmados, estado, confianza)."""
        self.frame_count += 1
        h, w = frame.shape[:2]
        area_frame = h * w

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Flujo optico denso respecto al frame anterior
        if self.prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            flow_mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        else:
            flow_mag = None
        self.prev_gray = gray

        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        mask = self.bg_subtractor.apply(blur)
        mask = cv2.erode(mask, self.kernel, iterations=1)
        mask = cv2.dilate(mask, self.kernel, iterations=2)
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)

        # Filtro anti-objeto-grande
        movimiento_total = cv2.countNonZero(mask) / area_frame
        if movimiento_total > MAX_MOVIMIENTO_TOTAL:
            self.blob_historia = {}
            confianza, _ = self._agregar(0)
            return 0, "OBJETO GRANDE", confianza

        contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detecciones = []
        for cnt in contornos:
            area = cv2.contourArea(cnt)
            if not (AREA_MIN < area < AREA_MAX):
                continue
            if area / area_frame > MAX_FRAME_RATIO:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = bw / bh if bh > 0 else 0
            if not (ASPECT_MIN < aspect < ASPECT_MAX):
                continue
            perimetro = cv2.arcLength(cnt, True)
            circularidad = (4 * np.pi * area / (perimetro ** 2)) if perimetro > 0 else 0
            if circularidad < 0.1:
                continue
            if flow_mag is not None:
                region = flow_mag[y:y + bh, x:x + bw]
                flujo_medio = float(region.mean()) if region.size > 0 else 0.0
                if flujo_medio < FLOW_MIN:
                    continue
            cx = x + bw // 2
            cy = y + bh // 2
            detecciones.append((x, y, bw, bh, area, circularidad, cx, cy))

        confirmadas, _candidatas = self._actualizar_persistencia(detecciones)
        n = len(confirmadas)

        if n >= UMBRAL_ENJAMBRE:
            estado = "ENJAMBRE"
        elif n >= UMBRAL_MOSQUITO:
            estado = "MOSQUITO"
        else:
            estado = "LIMPIO"

        confianza, _sev = self._agregar(n)
        return n, estado, confianza

    def _agregar(self, n):
        detectado = 1.0 if n >= UMBRAL_MOSQUITO else 0.0
        self.confianza = EMA_ALPHA * detectado + (1 - EMA_ALPHA) * self.confianza
        self.conteo_ema = EMA_ALPHA * n + (1 - EMA_ALPHA) * self.conteo_ema
        if not self.alerta and self.confianza >= CONF_ON:
            self.alerta = True
        elif self.alerta and self.confianza < CONF_OFF:
            self.alerta = False
        severidad = ("ENJAMBRE" if self.conteo_ema >= UMBRAL_ENJAMBRE else "MOSQUITO") \
            if self.alerta else "LIMPIO"
        return self.confianza, severidad

    def _actualizar_persistencia(self, detecciones):
        usados = set()
        nueva_historia = {}
        confirmadas = []
        candidatas = []
        for det in detecciones:
            cx, cy = det[6], det[7]
            mejor_id = None
            mejor_dist = DIST_MAX
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
            else:
                self._next_blob_id += 1
                mejor_id = self._next_blob_id
                frames = 1
                cx0, cy0 = cx, cy
                desp_max = 0.0
            nueva_historia[mejor_id] = {
                "cx": cx, "cy": cy, "cx0": cx0, "cy0": cy0,
                "frames": frames, "desp_max": desp_max,
            }
            if frames >= PERSISTENCIA_MIN and desp_max >= MOV_MIN:
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
        """Analiza TODO el clip (archivo) y emite el veredicto."""
        video_path = str(video_path)
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return Verdict(False, None, 0, 0.0,
                           summary=f"No se pudo abrir el video: {video_path}")

        def _frames():
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    yield frame
            finally:
                cap.release()

        return self._run(_frames())

    def analyze_frames(self, frames) -> Verdict:
        """Analiza una secuencia de fotogramas BGR ya decodificados (lista o
        generador). Lo usa el gateway cuando el ESP32 sube una rafaga de JPEGs."""
        return self._run(iter(frames))

    def _run(self, frame_iter) -> Verdict:
        """Pasa cada fotograma por el detector de movimiento y arma el veredicto."""
        det = MosquitoDetector()
        frames = 0
        frames_con = 0          # frames con >=1 deteccion confirmada
        total_obj = 0           # suma de objetos confirmados por frame
        max_obj = 0             # pico de objetos en un frame
        alerta_disparada = False
        conf_max = 0.0

        for frame in frame_iter:
            if frame is None:
                continue
            if frame.shape[1] != PROC_SIZE[0] or frame.shape[0] != PROC_SIZE[1]:
                frame = cv2.resize(frame, PROC_SIZE)
            n, _estado, confianza = det.procesar(frame)
            frames += 1
            if n >= UMBRAL_MOSQUITO:
                frames_con += 1
                total_obj += n
            max_obj = max(max_obj, n)
            if det.alerta:
                alerta_disparada = True
            conf_max = max(conf_max, confianza)

        # POSITIVO solo si: (1) la confianza por histeresis (EMA) se encendio
        # -movimiento SOSTENIDO ~2s, no un estallido breve de blobs- Y (2) la
        # confianza pico SUPERA el minimo exigido. Asi una alerta solo se acepta
        # si pasa un umbral de confianza claro. La via laxa "frames_con>=N" se quito.
        hay = alerta_disparada and conf_max >= CONF_MIN_ALERTA
        enjambre = hay and max_obj >= UMBRAL_ENJAMBRE
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

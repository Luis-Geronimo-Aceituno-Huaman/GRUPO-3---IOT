import cv2
import tkinter as tk
from tkinter import ttk, filedialog
import threading
import numpy as np
from PIL import Image, ImageTk
import time

# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────
UMBRAL_MOSQUITO = 1    # mínimo de objetos para considerar "mosquito"
UMBRAL_ENJAMBRE = 10   # mínimo para "enjambre"

AREA_MIN = 10          # área mínima de un blob (px²)
AREA_MAX = 800         # área máxima — descarta rostros/fondo grande
ASPECT_MIN = 0.2       # ratio w/h mínimo
ASPECT_MAX = 5.0       # ratio w/h máximo
MAX_FRAME_RATIO = 0.02 # blob no puede ocupar más del 2% del frame

PERSISTENCIA_MIN = 8   # frames consecutivos para confirmar detección (más estricto)
DIST_MAX = 40          # px máximo que un blob puede moverse entre frames (seguimiento)
MAX_MOVIMIENTO_TOTAL = 0.05  # si el movimiento total supera 5% del frame → objeto grande
MOV_MIN = 12           # px que un blob debe desplazarse para ser mosquito (descarta luces/reflejos fijos)
FLOW_MIN = 0.6         # magnitud media de flujo óptico mínima en el blob (px/frame) = movimiento real

# Agregación temporal de la decisión (suaviza el parpadeo frame-a-frame)
EMA_ALPHA = 0.08       # suavizado de la confianza (menor = más estable y lento)
CONF_ON = 0.70         # confianza para ENCENDER la alerta (histéresis)
CONF_OFF = 0.30        # confianza para APAGAR la alerta (histéresis)

# Veredicto final sobre TODO el video
FRAMES_MIN_VEREDICTO = 5  # nº mínimo de frames con detección confirmada para decir "HAY MOSQUITOS"
# ─────────────────────────────────────────────────────────────────────────────


class MosquitoDetector:
    def __init__(self):
        # BackgroundSubtractor MOG2:
        # history=500  → cuántos frames usa para "aprender" el fondo
        # varThreshold → sensibilidad al cambio (mayor = menos sensible)
        # detectShadows → si True, marca sombras en gris (las ignoramos)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=50,
            detectShadows=False
        )

        # Kernel morfológico: elimina ruido de 1-2 píxeles
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        # Tracker de persistencia: {blob_id: {cx, cy, frames}}
        self.blob_historia = {}
        self.frame_count = 0
        self._next_blob_id = 0

        # Frame anterior en gris (para el flujo óptico)
        self.prev_gray = None

        # Agregación temporal (confianza suavizada + alerta con histéresis)
        self.confianza = 0.0   # 0.0–1.0, media móvil exponencial (EMA)
        self.conteo_ema = 0.0  # conteo suavizado, para la severidad estable
        self.alerta = False    # estado estable de la alerta (con histéresis)

    def procesar(self, frame):
        self.frame_count += 1
        h, w = frame.shape[:2]
        area_frame = h * w

        # PASO 1: Convertir a gris
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # PASO 1.5: Flujo óptico denso (Farnebäck) respecto al frame anterior.
        if self.prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray, gray, None,
                0.5, 3, 15, 3, 5, 1.2, 0
            )
            flow_mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        else:
            flow_mag = None  # primer frame: aún no hay con qué comparar
        self.prev_gray = gray

        # PASO 2: Suavizar para reducir ruido de cámara
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # PASO 3: Resta de fondo → máscara binaria
        mask = self.bg_subtractor.apply(blur)

        # PASO 4: Morfología — erosión quita ruido puntual, dilatación une fragmentos
        mask = cv2.erode(mask, self.kernel, iterations=1)
        mask = cv2.dilate(mask, self.kernel, iterations=2)

        # PASO 5: Umbral binario limpio
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)

        frame_out = frame.copy()

        # PASO 5.5: FILTRO ANTI-OBJETO-GRANDE
        movimiento_total = cv2.countNonZero(mask) / area_frame
        if movimiento_total > MAX_MOVIMIENTO_TOTAL:
            self.blob_historia = {}  # reiniciar seguimiento (no acumular fragmentos)
            cv2.putText(
                frame_out,
                f"OBJETO GRANDE ({movimiento_total*100:.0f}% mov) - ignorando",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2
            )
            confianza, severidad = self._agregar(0)  # cuenta como "sin detección"
            return frame_out, mask, 0, "OBJETO GRANDE", confianza, severidad

        # PASO 6: Encontrar contornos (blobs de movimiento)
        contornos, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        detecciones = []

        for cnt in contornos:
            area = cv2.contourArea(cnt)

            # Filtro 1: área mínima y máxima
            if not (AREA_MIN < area < AREA_MAX):
                continue

            # Filtro 2: que no ocupe demasiado del frame (descarta fondos grandes)
            if area / area_frame > MAX_FRAME_RATIO:
                continue

            x, y, bw, bh = cv2.boundingRect(cnt)

            # Filtro 3: aspect ratio (forma razonable, no líneas ni manchas raras)
            aspect = bw / bh if bh > 0 else 0
            if not (ASPECT_MIN < aspect < ASPECT_MAX):
                continue

            # Filtro 4: circularidad mínima
            perimetro = cv2.arcLength(cnt, True)
            circularidad = (4 * np.pi * area / (perimetro ** 2)) if perimetro > 0 else 0
            if circularidad < 0.1:
                continue

            # Filtro 5: flujo óptico — el blob debe tener movimiento REAL.
            if flow_mag is not None:
                region = flow_mag[y:y + bh, x:x + bw]
                flujo_medio = float(region.mean()) if region.size > 0 else 0.0
                if flujo_medio < FLOW_MIN:
                    continue

            # Centroide del blob (para seguir el mismo objeto entre frames)
            cx = x + bw // 2
            cy = y + bh // 2
            detecciones.append((x, y, bw, bh, area, circularidad, cx, cy))

        # PASO 6.5: SEGUNDO FILTRO — persistencia temporal.
        confirmadas, candidatas = self._actualizar_persistencia(detecciones)

        # PASO 7: Dibujar.
        n = len(confirmadas)
        for (x, y, bw, bh, area, circ, cx, cy) in candidatas:
            cv2.rectangle(frame_out, (x, y), (x + bw, y + bh), (120, 120, 120), 1)

        for (x, y, bw, bh, area, circ, cx, cy) in confirmadas:
            color = (0, 255, 0) if n < UMBRAL_ENJAMBRE else (0, 0, 255)
            cv2.rectangle(frame_out, (x, y), (x + bw, y + bh), color, 1)
            cv2.putText(
                frame_out,
                f"{area:.0f}px",
                (x, y - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1
            )

        # PASO 8: Determinar estado
        if n >= UMBRAL_ENJAMBRE:
            estado = "ENJAMBRE"
            color_estado = (0, 0, 255)
        elif n >= UMBRAL_MOSQUITO:
            estado = "MOSQUITO"
            color_estado = (0, 200, 100)
        else:
            estado = "LIMPIO"
            color_estado = (180, 180, 180)

        # Overlay de estado en el frame
        cv2.putText(
            frame_out,
            f"{estado}  ({n} obj)",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_estado, 2
        )

        confianza, severidad = self._agregar(n)
        return frame_out, mask, n, estado, confianza, severidad

    def _agregar(self, n):
        """Suaviza la decisión en el tiempo (EMA + histéresis)."""
        detectado = 1.0 if n >= UMBRAL_MOSQUITO else 0.0
        self.confianza = EMA_ALPHA * detectado + (1 - EMA_ALPHA) * self.confianza
        self.conteo_ema = EMA_ALPHA * n + (1 - EMA_ALPHA) * self.conteo_ema

        # Histéresis: dos umbrales para que la alerta sea estable
        if not self.alerta and self.confianza >= CONF_ON:
            self.alerta = True
        elif self.alerta and self.confianza < CONF_OFF:
            self.alerta = False

        if self.alerta:
            severidad = "ENJAMBRE" if self.conteo_ema >= UMBRAL_ENJAMBRE else "MOSQUITO"
        else:
            severidad = "LIMPIO"

        return self.confianza, severidad

    def _actualizar_persistencia(self, detecciones):
        """Empareja cada detección con el blob más cercano del frame anterior."""
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
                "frames": frames, "desp_max": desp_max
            }

            if frames >= PERSISTENCIA_MIN and desp_max >= MOV_MIN:
                confirmadas.append(det)
            else:
                candidatas.append(det)

        self.blob_historia = nueva_historia
        return confirmadas, candidatas


# ─── GUI ─────────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Mosquito Detector — Veredicto de Video")
        self.root.configure(bg="#1a1a2e")

        self.detector = MosquitoDetector()
        self.cap = None
        self.corriendo = False
        self.hilo = None
        self.video_path = None

        self._construir_ui()

    def _construir_ui(self):
        # ── Barra superior ──
        bar = tk.Frame(self.root, bg="#16213e", pady=8)
        bar.pack(fill="x")

        tk.Label(bar, text="🦟 Veredicto de Video", font=("Helvetica", 14, "bold"),
                 bg="#16213e", fg="#e0e0e0").pack(side="left", padx=14)

        self.btn_video = tk.Button(
            bar, text="📂  Abrir y analizar video", command=self.abrir_video,
            bg="#0f3460", fg="white", relief="flat", padx=10, pady=4,
            activebackground="#1a5276"
        )
        self.btn_video.pack(side="left", padx=6)

        self.btn_stop = tk.Button(
            bar, text="⏹  Cancelar", command=self.detener,
            bg="#5d0000", fg="white", relief="flat", padx=10, pady=4,
            state="disabled"
        )
        self.btn_stop.pack(side="left", padx=6)

        # ── Paneles de video ──
        videos = tk.Frame(self.root, bg="#1a1a2e")
        videos.pack(fill="both", expand=True, padx=10, pady=8)

        left = tk.Frame(videos, bg="#0d0d1a")
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        tk.Label(left, text="Procesando video", bg="#0d0d1a",
                 fg="#aaa", font=("Helvetica", 10)).pack(pady=4)
        self.lbl_frame = tk.Label(left, bg="#0d0d1a")
        self.lbl_frame.pack(fill="both", expand=True)

        right = tk.Frame(videos, bg="#0d0d1a")
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        tk.Label(right, text="Máscara (movimiento)", bg="#0d0d1a",
                 fg="#aaa", font=("Helvetica", 10)).pack(pady=4)
        self.lbl_mask = tk.Label(right, bg="#0d0d1a")
        self.lbl_mask.pack(fill="both", expand=True)

        # ── Progreso ──
        prog_frame = tk.Frame(self.root, bg="#16213e", pady=6)
        prog_frame.pack(fill="x", padx=10, pady=(0, 6))

        tk.Label(prog_frame, text="Progreso", bg="#16213e", fg="#aaa",
                 font=("Helvetica", 9)).pack(anchor="w", padx=20)
        self.barra_progreso = ttk.Progressbar(prog_frame, length=400, maximum=100)
        self.barra_progreso.pack(side="left", padx=20, pady=4)
        self.lbl_progreso = tk.Label(prog_frame, text="—",
                                     font=("Helvetica", 11), bg="#16213e", fg="#aaa")
        self.lbl_progreso.pack(side="left", padx=10)

        # ── Veredicto FINAL (grande, solo aparece al terminar) ──
        veredicto_frame = tk.Frame(self.root, bg="#16213e", pady=10)
        veredicto_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.lbl_veredicto = tk.Label(
            veredicto_frame, text="Abre un video para analizarlo…",
            font=("Helvetica", 22, "bold"),
            bg="#0d0d1a", fg="#888", padx=20, pady=18
        )
        self.lbl_veredicto.pack(fill="x", padx=20)

        self.lbl_detalle = tk.Label(
            veredicto_frame, text="",
            font=("Helvetica", 11),
            bg="#16213e", fg="#aaa"
        )
        self.lbl_detalle.pack(pady=(6, 0))

    # ── Control ─────────────────────────────────────────────────────

    def abrir_video(self):
        path = filedialog.askopenfilename(
            filetypes=[("Video", "*.mp4 *.avi *.mkv *.mov"), ("Todos", "*.*")]
        )
        if not path:
            return

        self.detener()
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            self.lbl_veredicto.config(text="ERROR: no se pudo abrir el video",
                                      bg="#5d0000", fg="#ffdddd")
            return

        self.video_path = path
        self.detector = MosquitoDetector()  # reiniciar modelo de fondo

        # Total de frames (puede ser 0 si el contenedor no lo reporta)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

        self.corriendo = True
        self.btn_stop.config(state="normal")
        self.btn_video.config(state="disabled")

        self.lbl_veredicto.config(text="⏳ PROCESANDO…",
                                  bg="#0d0d1a", fg="#cccccc")
        self.lbl_detalle.config(text="")
        self.barra_progreso['value'] = 0

        self.hilo = threading.Thread(target=self._procesar_video, daemon=True)
        self.hilo.start()

    def detener(self):
        self.corriendo = False
        if self.cap:
            self.cap.release()
            self.cap = None
        self.btn_stop.config(state="disabled")
        self.btn_video.config(state="normal")

    # ── Procesamiento completo del video ────────────────────────────

    def _procesar_video(self):
        # Acumuladores para el veredicto final
        frames_procesados = 0
        frames_con_mosquito = 0   # frames con al menos 1 detección confirmada
        max_objetos = 0           # pico de objetos confirmados en un frame
        alerta_disparada = False  # ¿la confianza estable cruzó el umbral en algún momento?
        confianza_max = 0.0

        t_prev = time.time()
        ultimo_render = 0.0

        while self.corriendo:
            ret, frame = self.cap.read()
            if not ret:
                break  # fin del video → emitir veredicto

            frame = cv2.resize(frame, (640, 480))
            frame_out, mask, n, estado, confianza, severidad = self.detector.procesar(frame)

            frames_procesados += 1
            if n >= UMBRAL_MOSQUITO:
                frames_con_mosquito += 1
            max_objetos = max(max_objetos, n)
            if self.detector.alerta:
                alerta_disparada = True
            confianza_max = max(confianza_max, confianza)

            # Refrescar la vista solo ~cada 40 ms (no en cada frame) para ir rápido
            t_now = time.time()
            if t_now - ultimo_render > 0.04:
                ultimo_render = t_now
                pct = (frames_procesados / self.total_frames * 100) if self.total_frames else 0
                self.root.after(0, self._actualizar_vista,
                                frame_out, mask, frames_procesados, pct)

        # ── Fin del video: calcular y mostrar el VEREDICTO ──
        if self.corriendo:  # terminó normalmente (no cancelado)
            veredicto = self._calcular_veredicto(
                frames_procesados, frames_con_mosquito,
                max_objetos, alerta_disparada, confianza_max
            )
            self.root.after(0, self._mostrar_veredicto, veredicto)

        self.root.after(0, self.detener)

    def _calcular_veredicto(self, frames_procesados, frames_con_mosquito,
                            max_objetos, alerta_disparada, confianza_max):
        """Decide el veredicto final sobre TODO el video.

        Hay mosquitos si:
          - la confianza estable cruzó el umbral en algún momento (alerta_disparada), O
          - hubo suficientes frames con detección confirmada (FRAMES_MIN_VEREDICTO).
        Se reporta ENJAMBRE si el pico de objetos confirmados llegó al umbral.
        """
        pct_frames = (frames_con_mosquito / frames_procesados * 100) if frames_procesados else 0
        hay = alerta_disparada or frames_con_mosquito >= FRAMES_MIN_VEREDICTO
        enjambre = max_objetos >= UMBRAL_ENJAMBRE

        if hay and enjambre:
            titulo = "🦟 SÍ HAY MOSQUITOS (ENJAMBRE)"
            color_bg, color_fg = "#5d0000", "#ffdddd"
        elif hay:
            titulo = "🦟 SÍ HAY MOSQUITOS"
            color_bg, color_fg = "#7a5200", "#fff3cc"
        else:
            titulo = "✓ NO HAY MOSQUITOS"
            color_bg, color_fg = "#0a3d0a", "#ccffcc"

        detalle = (
            f"Frames analizados: {frames_procesados}   |   "
            f"Con detección: {frames_con_mosquito} ({pct_frames:.1f}%)   |   "
            f"Pico de objetos: {max_objetos}   |   "
            f"Confianza máx: {confianza_max*100:.0f}%"
        )
        return titulo, color_bg, color_fg, detalle

    # ── Actualización de UI ─────────────────────────────────────────

    def _actualizar_vista(self, frame, mask, frames_procesados, pct):
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb).resize((400, 300))
        img_tk = ImageTk.PhotoImage(img_pil)
        self.lbl_frame.config(image=img_tk)
        self.lbl_frame.image = img_tk

        mask_rgb = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
        mask_pil = Image.fromarray(mask_rgb).resize((400, 300))
        mask_tk = ImageTk.PhotoImage(mask_pil)
        self.lbl_mask.config(image=mask_tk)
        self.lbl_mask.image = mask_tk

        self.barra_progreso['value'] = pct
        if self.total_frames:
            self.lbl_progreso.config(
                text=f"{frames_procesados}/{self.total_frames} frames  ({pct:.0f}%)")
        else:
            self.lbl_progreso.config(text=f"{frames_procesados} frames")

    def _mostrar_veredicto(self, veredicto):
        titulo, color_bg, color_fg, detalle = veredicto
        self.lbl_veredicto.config(text=titulo, bg=color_bg, fg=color_fg)
        self.lbl_detalle.config(text=detalle)
        self.barra_progreso['value'] = 100
        self.lbl_progreso.config(text="Completado ✓")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("900x720")
    app = App(root)
    root.mainloop()

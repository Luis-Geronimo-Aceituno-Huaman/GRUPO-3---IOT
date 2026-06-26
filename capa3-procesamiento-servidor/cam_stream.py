"""
cam_stream.py — Expone la WEBCAM de la laptop como una "camara IP" por HTTP.

Asi el ESP32 (u otro cliente) puede jalar imagenes de la camara por red usando
mDNS (http://iot-server.local:8091/...), en vez de que el servidor grabe local.

Endpoints:
  GET /snapshot.jpg   -> un fotograma JPEG (el mas reciente). Lo que usa el ESP32
                         en rafaga al detectar un mosquito.
  GET /stream         -> MJPEG multipart (para ver en el navegador, debug).
  GET /               -> pagina simple con el stream embebido.

Un hilo de fondo captura la webcam continuamente y guarda el ultimo frame; las
peticiones sirven ese frame (no abren la camara por request -> sin condiciones de
carrera y la webcam queda abierta una sola vez).

Uso:
  python3 cam_stream.py                 # CAM_INDEX=0, puerto 8091
  CAM_INDEX=2 CAM_PORT=8091 python3 cam_stream.py
"""
from __future__ import annotations

import os
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

CAM_INDEX = int(os.getenv("CAM_INDEX", "0"))
CAM_PORT = int(os.getenv("CAM_PORT", "8091"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "70"))
FRAME_W = int(os.getenv("FRAME_W", "640"))
FRAME_H = int(os.getenv("FRAME_H", "480"))

_latest = {"jpeg": None, "ts": 0.0}
_lock = threading.Lock()


def _capture_loop():
    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    if not cap.isOpened():
        print(f"[CAM] No se pudo abrir la webcam index={CAM_INDEX}")
        return
    print(f"[CAM] Webcam {CAM_INDEX} abierta ({FRAME_W}x{FRAME_H}), sirviendo en :{CAM_PORT}")
    enc = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue
        ok, buf = cv2.imencode(".jpg", frame, enc)
        if ok:
            with _lock:
                _latest["jpeg"] = buf.tobytes()
                _latest["ts"] = time.time()


def _get_jpeg():
    with _lock:
        return _latest["jpeg"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/snapshot.jpg", "/snapshot", "/jpg"):
            self._snapshot()
        elif path == "/stream":
            self._stream()
        elif path == "/":
            self._index()
        else:
            self.send_error(404, "no encontrado")

    def _snapshot(self):
        jpeg = _get_jpeg()
        if jpeg is None:
            self.send_error(503, "camara aun sin frame")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(jpeg)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(jpeg)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while True:
                jpeg = _get_jpeg()
                if jpeg is not None:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _index(self):
        html = (b"<html><body style='background:#111;margin:0'>"
                b"<img src='/stream' style='width:100%'></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


def main():
    threading.Thread(target=_capture_loop, daemon=True).start()
    # esperar al primer frame
    for _ in range(100):
        if _get_jpeg() is not None:
            break
        time.sleep(0.05)
    srv = ThreadingHTTPServer(("0.0.0.0", CAM_PORT), Handler)
    print(f"[CAM] Camara IP lista: http://0.0.0.0:{CAM_PORT}/snapshot.jpg  |  /stream")
    srv.serve_forever()


if __name__ == "__main__":
    main()

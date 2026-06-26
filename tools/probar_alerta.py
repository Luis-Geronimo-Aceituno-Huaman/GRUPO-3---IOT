"""
probar_alerta.py — Prueba el pipeline de vision SIN un mosquito real.
================================================================================
Para demostrar el sistema no necesitas cazar un mosquito: este script usa
imagenes REALES del dataset MosquitoFusion (incluidas en
capa3-procesamiento-servidor/muestras_prueba/) para fabricar un clip, lo pasa por
la MISMA compuerta de vision de produccion (detector por movimiento) y, si lo
confirma, inserta la alerta en la BD exactamente igual que lo haria el gateway.
Luego la veras en el dashboard, con su video, al abrir  python serve.py.

NO necesita broker MQTT ni la webcam: ataja el pipeline justo en la compuerta de vision.

Uso:
    python tools/probar_alerta.py                 # clip con las 3 muestras (mosquito,
                                                  # enjambre, yacimiento) -> 1 alerta
    python tools/probar_alerta.py --clip foto.jpg # usa TU imagen o video
    python tools/probar_alerta.py --device esp32-03

Despues:
    cd capa4-aplicacion && python serve.py        # abre http://localhost:8000
    -> la alerta aparece con boton "▶ Video".
================================================================================
"""

from __future__ import annotations

import sys
import time
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]                 # sistema_integrado/
CAPA3 = ROOT / "capa3-procesamiento-servidor"
sys.path.insert(0, str(CAPA3))

import config as cfg                                        # noqa: E402
from db import AlertStore                                   # noqa: E402

MUESTRAS = CAPA3 / "muestras_prueba"
SAMPLE_IMAGES = [MUESTRAS / "mosquito.jpg", MUESTRAS / "enjambre.jpg", MUESTRAS / "yacimiento.jpg"]


def build_clip_from_images(images, out_path, secs_per_image=2, fps=20):
    """Arma un mp4 mostrando cada imagen unos segundos (clip sintetico realista)."""
    import cv2
    imgs = [cv2.imread(str(p)) for p in images if Path(p).exists()]
    imgs = [im for im in imgs if im is not None]
    if not imgs:
        raise SystemExit(f"No encontre muestras en {MUESTRAS}. ¿Estan los .jpg ahi?")
    h, w = imgs[0].shape[:2]
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for im in imgs:
        if im.shape[:2] != (h, w):
            im = cv2.resize(im, (w, h))
        for _ in range(secs_per_image * fps):
            writer.write(im)
    writer.release()
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Inyecta una alerta de prueba confirmada por el detector.")
    ap.add_argument("--clip", help="Ruta a una imagen o video propio (en vez de las muestras).")
    ap.add_argument("--device", default="esp32-01", help="ID del nodo (por defecto esp32-01).")
    args = ap.parse_args()

    clips_dir = Path(cfg.CLIPS_DIR) / args.device
    clips_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    clip_path = clips_dir / f"prueba-{stamp}.mp4"

    # 1) Conseguir un clip: el del usuario, o uno fabricado con las 3 muestras.
    if args.clip:
        src = Path(args.clip)
        if not src.exists():
            raise SystemExit(f"No existe: {src}")
        if src.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv"}:
            import shutil
            shutil.copy(src, clip_path)
        else:                                               # es una imagen -> clip de 4 s
            build_clip_from_images([src], clip_path, secs_per_image=4)
    else:
        print(f"[PRUEBA] Fabricando clip con las 3 muestras del dataset -> {clip_path.name}")
        build_clip_from_images(SAMPLE_IMAGES, clip_path)

    # 2) Pasar el clip por la MISMA compuerta de vision de produccion (por movimiento).
    from detector import VisionGate
    gate = VisionGate()
    verdict = gate.analyze_video(str(clip_path))
    print("[PRUEBA] Veredicto del detector:")
    print("   " + verdict.summary.replace("\n", "\n   "))

    if not verdict.detected:
        print("[PRUEBA] El detector no encontro movimiento tipo mosquito; NO se inserta "
              "alerta (asi funciona la compuerta real: descarta falsos positivos).")
        return

    # 3) Insertar la alerta EXACTAMENTE como lo hace el gateway al confirmar.
    nodes = {}
    try:
        nodes = json.loads(cfg.NODES_JSON.read_text(encoding="utf-8"))
    except Exception:
        pass
    node = nodes.get(args.device, {})

    alert = {
        "nodeId": args.device,
        "nodeName": node.get("name", args.device),
        "district": node.get("district", "San Juan de Lurigancho"),
        "lat": node.get("lat", -11.962),
        "lon": node.get("lon", -77.0),
        "ts": int(time.time() * 1000),
        "confidence": verdict.max_confidence,
        "source": "camera",
        "detClass": verdict.top_class,
        "detCount": verdict.total_detections,
        "videoUrl": str(clip_path),                         # serve.py lo convierte a /clips/...
        "status": "nueva",
        "sensors": {"temp_c": 27.8, "turb_v": 1.4, "audio_rms": 2100, "audio_peak": 52000, "sats": 8},
    }
    store = AlertStore(cfg.DB_PATH)
    new_id = store.insert_alert(alert)
    store.close()

    print(f"\n[PRUEBA] ✅ Alerta insertada (id={new_id}): {verdict.top_class} "
          f"conf={verdict.max_confidence} - clip {clip_path.name}")
    print("[PRUEBA] Ahora levanta el dashboard y veras la alerta con su video:")
    print("         cd capa4-aplicacion && python serve.py   ->  http://localhost:8000")


if __name__ == "__main__":
    main()

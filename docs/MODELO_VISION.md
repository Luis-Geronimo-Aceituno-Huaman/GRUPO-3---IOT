# Modelo de visión (detector de movimiento)

`capa3-procesamiento-servidor/detector.py` — sin redes neuronales: OpenCV clásico
calibrado para blobs pequeños en movimiento errático. El gateway lo ejecuta sobre
cada clip que sube el ESP32; **solo los positivos llegan a la BD**.

## Pipeline por frame

1. **Preprocesado**: gris → CLAHE opcional (`clahe_enabled`) → denoising:
   `GaussianBlur 5×5` o **bilateral** (`use_bilateral=1`, preserva bordes de
   blobs de 3-6 px; `fastNlMeans` se descartó por coste en ARM).
2. **Flujo óptico denso (Farneback)** respecto al frame anterior. `flow_downscale`
   lo calcula a resolución reducida (~n² menos CPU) y reescala la magnitud a px reales.
3. **Resta de fondo MOG2** (`mog2_history`, `mog2_var_threshold`) + morfología
   (erosión 1, dilatación 2) + umbral binario (`mask_threshold`).
4. **Filtro anti-objeto-grande**: si el movimiento total supera
   `max_movimiento_total` (5 % del frame) → frame ignorado (persona/cortina).
5. **Filtrado de blobs**: área (`area_min`–`area_max` px²), aspect ratio,
   `% del frame`, circularidad mínima, y **flujo óptico medio del blob ≥ umbral**.
   - Umbral de flujo **adaptativo** (`noise_percentile>0`): sube al percentil-N
     del ruido de movimiento del frame → el viento/vibración global no genera
     falsos positivos.
6. **Tracker de centroides** con ID persistente y trayectoria acotada (60 puntos).
   Un track se **confirma** solo si:
   - `persistencia_min` frames consecutivos, y
   - desplazamiento total ≥ `mov_min` px, y
   - (nuevo) velocidad media en `[vel_min_px_s, vel_max_px_s]` px/s — descarta
     ruido casi estático y objetos que cruzan demasiado rápido, y
   - (nuevo) trayectoria con ≥ `trayectoria_min_puntos` puntos.
7. **Agregación temporal**: EMA de la confianza (`ema_alpha`) con **histéresis**
   (`conf_on`=0.70 enciende, `conf_off`=0.30 apaga) → exige movimiento SOSTENIDO
   (~2 s), no un estallido de blobs.

## Veredicto del clip

`POSITIVO` ⇔ la histéresis se encendió **y** la confianza pico ≥ `conf_min_alerta`.
`Mosquito Swarm` si el pico de objetos simultáneos ≥ `umbral_enjambre` (10).

## Parámetros configurables (tabla `detector_params`)

TODOS los umbrales de arriba viven en la BD, con rango de validación y auditoría
de quién los cambió. El detector los **recarga al inicio de cada análisis de
clip** (1 query — hot-reload sin reiniciar el gateway). Si PostgreSQL no responde,
usa los defaults del módulo: **nunca deja de analizar**.

- Ver/editar: pestaña **Admin** del dashboard, o `GET|PUT /api/config/detector` (admin).
- Las mejoras nuevas vienen **apagadas por defecto** (`use_bilateral=0`,
  `noise_percentile=0`, `vel_*=0`, `flow_downscale=1`): migrar no cambia el
  comportamiento; se activan desde Admin cuando quieras afinar.

## Ajuste recomendado

- Muchos falsos positivos por ruido/viento → subir `noise_percentile` (95-98),
  activar `use_bilateral`, subir `conf_min_alerta`.
- Se escapan mosquitos reales → bajar `conf_min_alerta`/`persistencia_min`.
- VM ARM lenta → `flow_downscale=2` y/o `proc_w/proc_h` a 480×360.
- Probar a mano: `python3 detector.py ruta/al/clip.webm` (usa los params de BD).
- La herramienta GUI de laboratorio (`mosquito_veredicto_video.py`, raíz) sigue
  disponible para depuración visual frame a frame.

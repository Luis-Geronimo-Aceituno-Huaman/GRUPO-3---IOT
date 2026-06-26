#pragma once
/*
 * detector_autocalib.h — Post-procesado adaptativo para el clasificador binario
 * de mosquito (Edge Impulse) en ESP32-S3.
 * ──────────────────────────────────────────────────────────────────────────
 * El modelo entrega un score 0.0–1.0 por ventana de inferencia (~500 ms en este
 * nodo: 4000 muestras / 8000 Hz). En vez de un umbral FIJO (que cambia con el
 * ruido eléctrico/ambiental de cada lugar), este módulo:
 *
 *   1) CALIBRACION (al arrancar, ~50 s SIN mosquito): junta scores, calcula el
 *      percentil 99 del ruido y fija  umbral = p99 + margen.
 *   2) DETECCION: media móvil de las últimas 5 ventanas; confirma si la media
 *      supera el umbral (filtra picos sueltos de ruido).
 *   3) RECALIBRACION: si pasan 60 min sin detección, recalibra 10 s y actualiza
 *      el umbral. Lo guarda en NVS para sobrevivir reinicios.
 *
 * Diseño embebido: TODO estático (sin malloc/new), buffers < 1 KB, solo float y
 * qsort de la libc. NVS vía Preferences (wrapper Arduino de nvs_flash).
 *
 * Uso:
 *   #include "detector_autocalib.h"
 *   setup(): detectorBegin();
 *   por cada inferencia: det_result_t r = detectorProcess(score);
 *                        if (r == DET_CONFIRMED) { ...disparar alerta... }
 * ────────────────────────────────────────────────────────────────────────── */

#include <Arduino.h>
#include <Preferences.h>
#include <stdlib.h>   // qsort

/* ===================== Parámetros (ajustables) ===========================
 * Se pueden sobreescribir definiéndolos ANTES de incluir este header (p.ej.
 * en config.h). Si no, se usan estos valores por defecto. */
#ifndef DET_CALIB_SAMPLES
#define DET_CALIB_SAMPLES        100      // ventanas de calibración (~50 s) → 400 B de buffer
#endif
#ifndef DET_RECAL_SAMPLES
#define DET_RECAL_SAMPLES        20       // ventanas de recalibración (~10 s)
#endif
#ifndef DET_SLIDING
#define DET_SLIDING              5        // tamaño de la media móvil (últimas N ventanas)
#endif
#ifndef DET_CONSEC_CONFIRM
#define DET_CONSEC_CONFIRM       3        // ventanas SEGUIDAS con media>umbral para confirmar
#endif
#ifndef DET_MARGIN
#define DET_MARGIN               0.08f    // margen de seguridad sobre el percentil
#endif
#ifndef DET_PERCENTILE
#define DET_PERCENTILE           0.99f    // percentil del ruido (99 %)
#endif
#ifndef DET_IDLE_RECAL_MS
#define DET_IDLE_RECAL_MS        (60UL * 60UL * 1000UL)   // 60 min sin detección → recalibra
#endif
#ifndef DET_THRESHOLD_CEIL
#define DET_THRESHOLD_CEIL       0.97f    // tope del umbral (nunca lo dejes imposible de cruzar)
#endif
#ifndef DET_LED_PIN
#define DET_LED_PIN              (-1)     // LED "calibración terminada" (-1 = desactivado)
#endif
#ifndef DET_OUT_PIN
#define DET_OUT_PIN              (-1)     // pulso GPIO al confirmar detección (-1 = desactivado)
#endif
#ifndef DET_FORCE_CALIB_ON_BOOT
#define DET_FORCE_CALIB_ON_BOOT  0        // 1 = calibra SIEMPRE al arrancar; 0 = reusa NVS tras reboot
#endif

/* Resultado de cada ventana procesada. */
typedef enum {
  DET_CALIBRATING,   // aún calibrando/recalibrando: no se evalúan detecciones
  DET_IDLE,          // detectando, sin evento
  DET_CONFIRMED      // ¡detección confirmada!
} det_result_t;

/* ===================== Estado interno (todo estático) ==================== */
typedef enum { DET_ST_CALIB = 0, DET_ST_DETECT = 1 } det_state_t;

static float       g_detCalBuf[DET_CALIB_SAMPLES];  // buffer de calibración (reusado en recal)
static int         g_detCalCount   = 0;
static int         g_detCalTarget  = DET_CALIB_SAMPLES;
static bool        g_detIsRecal    = false;

static float       g_detSlide[DET_SLIDING];         // ring buffer de la media móvil
static int         g_detSlideCount = 0;
static int         g_detSlideHead  = 0;
static int         g_detConfirmCount = 0;            // ventanas seguidas con media>umbral

static float       g_detThreshold  = 1.0f;          // arranca alto: no dispara hasta calibrar
static uint32_t    g_detLastDetMs  = 0;
static det_state_t g_detState      = DET_ST_CALIB;
static Preferences g_detPrefs;

/* ===================== Utilidades internas =============================== */

/* Comparador para qsort (orden ascendente de floats). */
static int det_cmpFloat(const void *a, const void *b) {
  float fa = *(const float *)a, fb = *(const float *)b;
  return (fa > fb) - (fa < fb);
}

/* Percentil p∈[0,1] de los primeros n valores de buf. Ordena buf in-place
 * (no pasa nada: tras calcularlo el buffer se vuelve a llenar desde cero). */
static float det_percentile(float *buf, int n, float p) {
  if (n <= 0) return 0.0f;
  qsort(buf, n, sizeof(float), det_cmpFloat);
  int idx = (int)(p * (n - 1) + 0.5f);      // índice redondeado
  if (idx < 0)      idx = 0;
  if (idx >= n)     idx = n - 1;
  return buf[idx];
}

/* Persistencia del umbral en NVS (sobrevive reinicios). */
static void det_saveNVS(float thr) {
  g_detPrefs.begin("mosqdet", false);       // namespace, RW
  g_detPrefs.putFloat("thr", thr);
  g_detPrefs.end();
}
static float det_loadNVS(float def) {
  g_detPrefs.begin("mosqdet", true);        // solo lectura
  float t = g_detPrefs.getFloat("thr", def);
  g_detPrefs.end();
  return t;
}

/* Arranca una fase de (re)calibración: limpia el contador y entra en estado CALIB. */
static void det_startCalibration(int nSamples, bool recal) {
  g_detCalCount  = 0;
  g_detCalTarget = (nSamples > DET_CALIB_SAMPLES) ? DET_CALIB_SAMPLES : nSamples;
  g_detIsRecal   = recal;
  g_detState     = DET_ST_CALIB;
  Serial.printf("[DET] %s: recolectando %d ventanas (~%.0f s). Manten el ambiente SIN mosquito.\n",
                recal ? "RECALIBRACION" : "CALIBRACION",
                g_detCalTarget, g_detCalTarget * 0.5f);
}

/* ===================== API pública ====================================== */

/* Llamar una vez en setup(). Carga el umbral de NVS; si existe y no se fuerza
 * recalibración, arranca detectando de inmediato (clave cuando el nodo se
 * reinicia tras cada alerta: no se queda 50 s "ciego"). Si no hay umbral
 * guardado (primer arranque), calibra. */
static void detectorBegin() {
  if (DET_LED_PIN >= 0) { pinMode(DET_LED_PIN, OUTPUT); digitalWrite(DET_LED_PIN, LOW); }
  if (DET_OUT_PIN >= 0) { pinMode(DET_OUT_PIN, OUTPUT); digitalWrite(DET_OUT_PIN, LOW); }

  g_detLastDetMs = millis();
  float stored = det_loadNVS(-1.0f);

  if (!DET_FORCE_CALIB_ON_BOOT && stored > 0.0f) {
    g_detThreshold  = stored;
    g_detState      = DET_ST_DETECT;
    g_detSlideCount = 0;
    g_detSlideHead  = 0;
    if (DET_LED_PIN >= 0) digitalWrite(DET_LED_PIN, HIGH);
    Serial.printf("[DET] umbral cargado de NVS = %.3f -> deteccion inmediata (sin recalibrar).\n",
                  g_detThreshold);
  } else {
    g_detThreshold = 1.0f;
    det_startCalibration(DET_CALIB_SAMPLES, false);
  }
}

/* Media móvil actual (para logging). */
static float detectorAvg() {
  if (g_detSlideCount == 0) return 0.0f;
  float a = 0.0f;
  for (int i = 0; i < g_detSlideCount; i++) a += g_detSlide[i];
  return a / g_detSlideCount;
}
static float       detectorThreshold() { return g_detThreshold; }
static const char *detectorStateStr() {
  if (g_detState == DET_ST_CALIB) return g_detIsRecal ? "RECAL" : "CALIB";
  return "DETECT";
}

/* Recalibracion a demanda (p.ej. comando MQTT "recalib" tras mover el nodo).
 * Lanza una calibracion limpia de 100 ventanas (~50 s) y reescribe el umbral en
 * NVS al terminar. Util cuando FORCE_CALIB_ON_BOOT=0 y cambia el ruido del sitio. */
static void detectorForceRecalibration() {
  Serial.println(F("[DET] recalibracion solicitada a demanda."));
  if (DET_LED_PIN >= 0) digitalWrite(DET_LED_PIN, LOW);   // LED apagado = recalibrando
  det_startCalibration(DET_CALIB_SAMPLES, true);
}

/* Procesa el score de UNA ventana de inferencia. Devuelve el resultado. */
static det_result_t detectorProcess(float score) {
  uint32_t now = millis();

  /* ---------- FASE 1/3: CALIBRACION (o RECALIBRACION) ---------- */
  if (g_detState == DET_ST_CALIB) {
    if (g_detCalCount < g_detCalTarget) g_detCalBuf[g_detCalCount++] = score;

    if (g_detCalCount >= g_detCalTarget) {           // buffer lleno → calcular umbral
      float p = det_percentile(g_detCalBuf, g_detCalCount, DET_PERCENTILE);
      g_detThreshold = p + DET_MARGIN;
      if (g_detThreshold > DET_THRESHOLD_CEIL) g_detThreshold = DET_THRESHOLD_CEIL;
      det_saveNVS(g_detThreshold);

      Serial.printf("[DET] %s lista: p%.0f=%.3f  ->  umbral=%.3f  (guardado en NVS)\n",
                    g_detIsRecal ? "Recalibracion" : "Calibracion",
                    DET_PERCENTILE * 100.0f, p, g_detThreshold);
      if (DET_LED_PIN >= 0) digitalWrite(DET_LED_PIN, HIGH);   // LED fijo = calibrado

      g_detState        = DET_ST_DETECT;
      g_detSlideCount   = 0;
      g_detSlideHead    = 0;
      g_detConfirmCount = 0;
      g_detLastDetMs    = now;
    }
    return DET_CALIBRATING;
  }

  /* ---------- FASE 2/3: DETECCION ---------- */
  // Empuja el score al ring buffer de la media móvil.
  g_detSlide[g_detSlideHead] = score;
  g_detSlideHead = (g_detSlideHead + 1) % DET_SLIDING;
  if (g_detSlideCount < DET_SLIDING) g_detSlideCount++;

  // FASE 3/3: ¿llevamos 60 min sin detección? → recalibración corta (10 s).
  if ((uint32_t)(now - g_detLastDetMs) > DET_IDLE_RECAL_MS) {
    det_startCalibration(DET_RECAL_SAMPLES, true);
    g_detLastDetMs = now;                 // evita re-disparar la recal de inmediato
    return DET_CALIBRATING;
  }

  // Detección confirmada: media móvil llena Y por encima del umbral durante
  // DET_CONSEC_CONFIRM ventanas SEGUIDAS (persistencia anti-falsos-positivos).
  float avg = detectorAvg();
  if (g_detSlideCount >= DET_SLIDING && avg > g_detThreshold) {
    g_detLastDetMs = now;                 // hay actividad: resetea el timer de recal
    if (++g_detConfirmCount >= DET_CONSEC_CONFIRM) {
      g_detConfirmCount = 0;
      if (DET_OUT_PIN >= 0) {             // pulso opcional en GPIO
        digitalWrite(DET_OUT_PIN, HIGH); delay(20); digitalWrite(DET_OUT_PIN, LOW);
      }
      return DET_CONFIRMED;
    }
    return DET_IDLE;                      // va acumulando la racha, aún no confirma
  }
  g_detConfirmCount = 0;                  // se rompió la racha: vuelve a empezar
  return DET_IDLE;
}

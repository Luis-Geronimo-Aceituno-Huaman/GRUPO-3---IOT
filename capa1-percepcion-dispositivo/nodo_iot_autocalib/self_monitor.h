#pragma once
/*
 * self_monitor.h — Auto-monitoreo y auto-recuperacion del nodo ESP32-S3.
 * ──────────────────────────────────────────────────────────────────────────
 * Modulo header-only y ESTATICO (sin malloc/new, buffers < 5 KB), al estilo de
 * detector_autocalib.h. Implementa el subconjunto del spec que se puede aplicar
 * SIN tocar infraestructura (no incluye mTLS ni Secure Boot, que son fase aparte):
 *
 *   1) IDENTIDAD     — node_name persistente en NVS (namespace "node_config").
 *                      Se lee al boot y se mete en cada payload.
 *   2) SNTP          — hora Unix sincronizada; prerrequisito de timestamps reales.
 *   3) HEARTBEAT     — cada SM_HEARTBEAT_MS publica nodes/<name>/heartbeat.
 *                      Si no hay WiFi/MQTT cuando vence, lo ENCOLA (1 ranura) y lo
 *                      envia al reconectar.
 *   4) SCORES ANOMALOS — cuenta inferencias seguidas en EXACTAMENTE 0.0 o 1.0;
 *                      si pasan de SM_ANOM_MAX (20), guarda la razon en NVS y
 *                      esp_restart() (pipeline corrupto / micro desconectado).
 *   5) TEMP + UPTIME — temperatura interna del chip y segundos desde el boot.
 *   6) SEQ           — contador incremental ("seq":N) para cada mensaje.
 *   7) WIFI BACKOFF  — reconexion con espera exponencial 1,2,4,...,300 s.
 *                      Tras 5 fallos lo registra en NVS y sigue reintentando.
 *
 * Uso (ver nodo_iot_autocalib.ino):
 *   setup(): smBegin(DEVICE_ID);            // fija/lee node_name
 *   loop():  smManageWifi();                // backoff de reconexion (sustituye WiFi.reconnect)
 *            smLoop(&g_mqtt, umbralActual); // SNTP + heartbeat + flush de la cola
 *   por inferencia: smOnScore(conf);        // vigilancia de scores anomalos
 *   en cada publish: usa smSeqNext() y smNodeName()
 * ────────────────────────────────────────────────────────────────────────── */

#include <Arduino.h>
#include <WiFi.h>
#include <MQTT.h>
#include <Preferences.h>
#include <time.h>
#include "esp_timer.h"
#include "esp_system.h"   // esp_restart

/* ===================== Parametros (sobreescribibles en config.h) ========== */
#ifndef SM_NVS_NS
#define SM_NVS_NS            "node_config"   // namespace NVS para valores persistentes
#endif
#ifndef SM_HEARTBEAT_MS
#define SM_HEARTBEAT_MS      (10UL * 60UL * 1000UL)   // cada 10 min
#endif
#ifndef SM_FIRST_HB_MS
#define SM_FIRST_HB_MS       15000UL         // primer heartbeat ~15 s tras boot (para verlo rapido)
#endif
#ifndef SM_ANOM_MAX
#define SM_ANOM_MAX          20              // scores 0.0/1.0 seguidos antes de reiniciar
#endif
#ifndef SM_WIFI_BACKOFF_MIN_MS
#define SM_WIFI_BACKOFF_MIN_MS  1000UL       // primer reintento WiFi: 1 s
#endif
#ifndef SM_WIFI_BACKOFF_MAX_MS
#define SM_WIFI_BACKOFF_MAX_MS  300000UL     // tope: 300 s
#endif
#ifndef SM_SNTP_SERVER1
#define SM_SNTP_SERVER1      "pool.ntp.org"
#endif
#ifndef SM_SNTP_SERVER2
#define SM_SNTP_SERVER2      "time.google.com"
#endif
/* battery_pct: no hay hardware de bateria por ahora; -1 = desconocido.
 * Si cableas un divisor a un ADC, define SM_BATTERY_PCT_EXPR para leerlo. */
#ifndef SM_BATTERY_PCT_EXPR
#define SM_BATTERY_PCT_EXPR  (-1)
#endif

/* ===================== Estado interno (todo estatico) ==================== */
static char       g_smName[24]      = {0};          // node_name (<24 chars)
static uint32_t   g_smSeq           = 0;            // contador secuencial
static char       g_smHbTopic[64]   = {0};          // nodes/<name>/heartbeat
static char       g_smStatusTopic[64] = {0};        // nodes/<name>/status

static uint32_t   g_smHbNext        = 0;            // millis del proximo heartbeat
static bool       g_smHbPending     = false;        // hay un heartbeat encolado?
static char       g_smHbQueue[256]  = {0};          // ranura unica de la cola (sin malloc)

static int        g_smAnomCount     = 0;            // scores 0.0/1.0 seguidos

static bool       g_smSntpStarted   = false;
static bool       g_smTimeOk        = false;

static uint32_t   g_smWifiNextTry   = 0;
static uint32_t   g_smWifiDelay     = SM_WIFI_BACKOFF_MIN_MS;
static int        g_smWifiFails     = 0;
static bool       g_smWifiLogged    = false;        // ya registramos los 5 fallos?

static Preferences g_smPrefs;

/* ===================== Utilidades internas =============================== */

/* Guarda un par clave/valor de texto en NVS (razon de reinicio, etc.). */
static void sm_nvsPutStr(const char *key, const char *val) {
  g_smPrefs.begin(SM_NVS_NS, false);
  g_smPrefs.putString(key, val);
  g_smPrefs.end();
}

/* Uptime en segundos usando el timer de 64 bits (no se desborda como millis). */
static uint32_t sm_uptimeS() {
  return (uint32_t)(esp_timer_get_time() / 1000000ULL);
}

/* Temperatura interna del SoC (ESP32-S3). temperatureRead() la da en °C.
 * En reposo suele leer ~30-50 °C; es relativa, sirve de tendencia, no de precision. */
static float sm_chipTempC() {
  return temperatureRead();
}

/* Unix time actual (0 si SNTP aun no sincronizo). */
static uint32_t sm_unix() {
  time_t now = time(nullptr);
  return (now > 1700000000) ? (uint32_t)now : 0;   // >2023-11 => reloj valido
}

/* Construye el JSON del heartbeat en 'out'. Devuelve longitud. */
static int sm_buildHeartbeat(char *out, size_t cap, float threshold) {
  return snprintf(out, cap,
    "{\"node_name\":\"%s\",\"status\":\"alive\",\"uptime_s\":%lu,"
    "\"battery_pct\":%d,\"chip_temp_c\":%.1f,\"threshold\":%.3f,"
    "\"timestamp\":%lu,\"seq\":%lu}",
    g_smName, (unsigned long)sm_uptimeS(),
    (int)(SM_BATTERY_PCT_EXPR), sm_chipTempC(), threshold,
    (unsigned long)sm_unix(), (unsigned long)(++g_smSeq));
}

/* ===================== API publica ====================================== */

/* node_name actual y siguiente numero de secuencia (para meterlos en payloads). */
static const char *smNodeName() { return g_smName; }
static uint32_t     smSeqNext() { return ++g_smSeq; }
static const char  *smStatusTopic() { return g_smStatusTopic; }
static bool         smTimeSynced() { return g_smTimeOk; }
static uint32_t     smUnix()    { return sm_unix(); }

/* Fuerza el envio del heartbeat en la PROXIMA llamada a smLoop() (en vez de
 * esperar el intervalo periodico). Lo usa el comando MQTT "heartbeat": un boton
 * en el servidor que pide el estado del nodo al instante. Vence el temporizador
 * del heartbeat; el envio real lo hace smLoop() reusando el mismo formato/seq. */
static void smRequestHeartbeat() {
  g_smHbNext = millis();   // temporizador vencido -> el proximo smLoop publica ya
  Serial.println(F("[SM] heartbeat a demanda solicitado (cmd del servidor)."));
}

/* Permite (re)provisionar el nombre del nodo: lo escribe en NVS y reconstruye
 * los topics. Llamalo una vez si quieres cambiar el nombre sin reflashear. */
static void smSetNodeName(const char *name) {
  strncpy(g_smName, name, sizeof(g_smName) - 1);
  g_smName[sizeof(g_smName) - 1] = '\0';
  sm_nvsPutStr("name", g_smName);
  snprintf(g_smHbTopic,     sizeof(g_smHbTopic),     "nodes/%s/heartbeat", g_smName);
  snprintf(g_smStatusTopic, sizeof(g_smStatusTopic), "nodes/%s/status",    g_smName);
}

/* Llamar UNA vez en setup(). Lee node_name de NVS; si no existe usa def y lo
 * guarda (provisioning). Programa el primer heartbeat. */
static void smBegin(const char *def) {
  g_smPrefs.begin(SM_NVS_NS, true);                 // solo lectura
  String stored = g_smPrefs.getString("name", "");
  g_smPrefs.end();

  if (stored.length() > 0) {
    strncpy(g_smName, stored.c_str(), sizeof(g_smName) - 1);
    g_smName[sizeof(g_smName) - 1] = '\0';
    snprintf(g_smHbTopic,     sizeof(g_smHbTopic),     "nodes/%s/heartbeat", g_smName);
    snprintf(g_smStatusTopic, sizeof(g_smStatusTopic), "nodes/%s/status",    g_smName);
    Serial.printf("[SM] node_name (NVS) = %s\n", g_smName);
  } else {
    smSetNodeName(def);                             // primer arranque: provisiona
    Serial.printf("[SM] node_name provisionado = %s\n", g_smName);
  }

  g_smHbNext = millis() + SM_FIRST_HB_MS;

  /* Si en el arranque anterior reiniciamos por una razon registrada, muestrala. */
  g_smPrefs.begin(SM_NVS_NS, true);
  String why = g_smPrefs.getString("last_reset", "");
  g_smPrefs.end();
  if (why.length()) Serial.printf("[SM] reinicio previo por: %s\n", why.c_str());
}

/* Vigilancia de scores anomalos: cuenta inferencias EXACTAMENTE 0.0 o 1.0
 * consecutivas. Mas de SM_ANOM_MAX => micro/pipeline roto: log a NVS + restart.
 * Cualquier score "normal" reinicia el contador. */
static void smOnScore(float score) {
  if (score == 0.0f || score == 1.0f) {
    if (++g_smAnomCount > SM_ANOM_MAX) {
      Serial.printf("[SM] %d scores anomalos seguidos (=%.1f): pipeline corrupto. Reiniciando.\n",
                    g_smAnomCount, score);
      sm_nvsPutStr("last_reset", "anomalous_scores");
      delay(100);
      esp_restart();
    }
  } else {
    g_smAnomCount = 0;
  }
}

/* Reconexion WiFi con backoff exponencial (sustituye al WiFi.reconnect() crudo).
 * Llamar en cada loop(). No bloquea: respeta el tiempo de espera entre intentos. */
static void smManageWifi() {
  if (WiFi.isConnected()) {                          // conectado: resetea el backoff
    g_smWifiDelay  = SM_WIFI_BACKOFF_MIN_MS;
    g_smWifiFails  = 0;
    g_smWifiLogged = false;
    return;
  }
  uint32_t now = millis();
  if ((int32_t)(now - g_smWifiNextTry) < 0) return;  // aun esperando

  Serial.printf("[SM] WiFi caido: reintento #%d (espera fue %lu ms)\n",
                g_smWifiFails + 1, (unsigned long)g_smWifiDelay);
  WiFi.reconnect();
  g_smWifiFails++;

  if (g_smWifiFails >= 5 && !g_smWifiLogged) {        // tras 5 fallos: registra y sigue
    sm_nvsPutStr("last_reset", "");                   // limpia (no reiniciamos por WiFi)
    sm_nvsPutStr("wifi_event", "5_fails_backoff");
    g_smWifiLogged = true;
    Serial.println(F("[SM] 5 fallos de WiFi: registrado en NVS, sigo reintentando en background."));
  }

  g_smWifiNextTry = now + g_smWifiDelay;
  g_smWifiDelay   = g_smWifiDelay * 2;
  if (g_smWifiDelay > SM_WIFI_BACKOFF_MAX_MS) g_smWifiDelay = SM_WIFI_BACKOFF_MAX_MS;
}

/* Llamar en cada loop(): arranca SNTP cuando hay WiFi, vence/encola el heartbeat
 * y vacia la cola al reconectar. 'threshold' = umbral actual del detector. */
static void smLoop(MQTTClient *mqtt, float threshold) {
  /* --- SNTP: arrancar una vez que haya WiFi --- */
  if (WiFi.isConnected() && !g_smSntpStarted) {
    configTime(0, 0, SM_SNTP_SERVER1, SM_SNTP_SERVER2);   // UTC (offset 0)
    g_smSntpStarted = true;
    Serial.println(F("[SM] SNTP solicitado (hora UTC)."));
  }
  if (g_smSntpStarted && !g_smTimeOk && sm_unix() > 0) {
    g_smTimeOk = true;
    Serial.printf("[SM] hora sincronizada: unix=%lu\n", (unsigned long)sm_unix());
  }

  /* --- Flush de la cola: si habia un heartbeat pendiente y ya hay MQTT --- */
  if (g_smHbPending && mqtt->connected()) {
    mqtt->publish(g_smHbTopic, g_smHbQueue, false, 0);
    g_smHbPending = false;
    Serial.println(F("[SM] heartbeat encolado enviado tras reconectar."));
  }

  /* --- Heartbeat periodico --- */
  uint32_t now = millis();
  if ((int32_t)(now - g_smHbNext) >= 0) {
    g_smHbNext = now + SM_HEARTBEAT_MS;

    char buf[256];
    sm_buildHeartbeat(buf, sizeof(buf), threshold);

    if (mqtt->connected()) {
      mqtt->publish(g_smHbTopic, buf, false, 0);
      Serial.printf("[SM] heartbeat -> %s\n", buf);
    } else {
      strncpy(g_smHbQueue, buf, sizeof(g_smHbQueue) - 1);   // encola (1 ranura)
      g_smHbQueue[sizeof(g_smHbQueue) - 1] = '\0';
      g_smHbPending = true;
      Serial.println(F("[SM] sin MQTT: heartbeat encolado."));
    }
  }
}

/* Guarda una razon de reinicio en NVS antes de un restart provocado por otro
 * modulo (p.ej. el reboot tras subir el video). */
static void smSaveResetReason(const char *reason) {
  sm_nvsPutStr("last_reset", reason);
}

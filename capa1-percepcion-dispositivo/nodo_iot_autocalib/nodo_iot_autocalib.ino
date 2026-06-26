/*
 * firmware_tinyml.ino — Nodo ESP32-S3 de PRODUCCION
 * ──────────────────────────────────────────────────────────────────────────
 * Detector de eventos acusticos con TinyML (Edge Impulse) desplegado como
 * inferencia EN EL DISPOSITIVO. El nodo:
 *
 *   1. Captura ventanas de 0.5 s del micro INMP441 (I2S).
 *   2. Corre el modelo Edge Impulse (EON / TFLite-Micro) sobre cada ventana
 *      → obtiene la confianza de la clase "mosquito" (0.0–1.0).
 *   3. Aplica la REGLA DE 3 VENTANAS CONSECUTIVAS (umbral + persistencia):
 *      solo cuando hay N ventanas seguidas por encima del umbral, dispara.
 *   4. Al disparar, publica  devices/<id>/alert  (QoS 1).  ← lo que la cámara
 *      de la Capa 3 esta esperando para grabar el clip que analizara el detector.
 *   5. En paralelo publica telemetria (sensors/gps/audio/status) para que el
 *      gateway enriquezca la alerta confirmada.
 *
 * Este sketch es el ESLABON que faltaba: convierte el disparo "por GPIO" del
 * probe en un disparo "por audio" hecho por el propio ESP32 (Edge AI / TinyML).
 *
 * Conexiones — idénticas al probe (firmware/code.ino):
 *   Turbidez (ADC) GPIO6 · DS18B20 GPIO7 · GPS UART1 TX17/RX18
 *   INMP441 I2S: BCLK=10  WS=11  DIN=9
 *   (opcional) disparo manual GPIO15/16
 *
 * Monitor serie @ 115200: imprime la confianza ventana por ventana (calibración).
 * ──────────────────────────────────────────────────────────────────────────
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>      // tzapu/WiFiManager — portal de configuracion WiFi
#include <ESPmDNS.h>          // descubrir el broker por nombre (.local), sin IP fija
#include <HTTPClient.h>       // jalar fotos de la camara IP y subir la rafaga al gateway
#include <MQTT.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <driver/i2s_std.h>
#include <math.h>

#include "config.h"

/* ──────────────────────────────────────────────────────────────────────────
 *  MODELO EDGE IMPULSE
 *  Ajusta este include al nombre EXACTO de tu libreria exportada.
 *  El .zip "ei-luis12345-project-1-..." normalmente instala el header:
 *      luis12345-project-1_inferencing.h
 *  Si Arduino se queja de "No such file", revisa Sketch → Include Library.
 * ────────────────────────────────────────────────────────────────────────── */
#include <Luis12345-project-1_inferencing.h>

/* Post-procesado adaptativo: calibracion automatica + media movil + recalibracion.
 * Reemplaza la regla fija "umbral + 3 ventanas consecutivas" por un umbral que se
 * mide solo segun el ruido real de cada lugar (ver detector_autocalib.h). */
#include "detector_autocalib.h"

/* Auto-monitoreo + auto-recuperacion: identidad NVS, SNTP, heartbeat con cola,
 * deteccion de scores anomalos, temp/uptime, numeracion seq y backoff de WiFi.
 * Va DESPUES del detector porque el heartbeat publica el umbral actual. */
#include "self_monitor.h"

/* -------- pines / parámetros -------- */
#define TURBIDITY_PIN     6
#define DS18B20_PIN       7

#define GPS_TX_PIN        17
#define GPS_RX_PIN        18
#define GPS_BAUD          9600

#define MIC_BCLK_PIN      10
#define MIC_WS_PIN        11
#define MIC_DATA_PIN      9

#define ALERT_PIN_A       15
#define ALERT_PIN_B       16

/* El modelo define a qué frecuencia y con cuántas muestras trabaja una ventana.
 * Edge Impulse expone estas macros desde el header del modelo: */
#define MIC_SAMPLE_RATE   ((uint32_t)EI_CLASSIFIER_FREQUENCY)        // p.ej. 8000 Hz
#define WINDOW_SAMPLES    (EI_CLASSIFIER_RAW_SAMPLE_COUNT)           // p.ej. 4000 (0.5 s)

/* -------- globals -------- */
OneWire           g_oneWire(DS18B20_PIN);
DallasTemperature g_ds18b20(&g_oneWire);
HardwareSerial&   GpsSerial = Serial1;
static String     g_nmeaBuf;

static i2s_chan_handle_t g_rx_chan = nullptr;

WiFiClient   g_wifiClient;
MQTTClient   g_mqtt(512);   // 512 (no 256): el heartbeat + topic + cabeceras no caben en 256
static String g_brokerHost;          // IP del broker + gateway (la NUBE): mDNS MQTT_MDNS o IP fija MQTT_HOST
static String g_camHost;             // IP de la camara (la LAPTOP): mDNS CAM_MDNS o IP fija CAM_HOST


/* Buffer de la ventana de audio que se le entrega al modelo (PCM int16). */
static int16_t  g_sampleBuffer[WINDOW_SAMPLES];

/* Estado de la regla de ventanas consecutivas. */
static int      g_contadorConsecutivas = 0;
static uint32_t g_lastAlert = 0;
static int      g_idxMosquito = -1;     // índice de la clase "mosquito" (se resuelve 1 vez)
static float    g_ultimaConfianza = 0;  // para telemetría

/* GPS parseado. */
static double g_lat = 0.0, g_lon = 0.0;
static float  g_alt = 0.0;
static int    g_sats = 0;
static bool   g_gpsFix = false;

#if ENABLE_GPIO_TRIGGER
static volatile bool g_gpioAlertFlag = false;
static void IRAM_ATTR onGpioAlertISR() { g_gpioAlertFlag = true; }
#endif

/* ──────────────────────────── WiFi (WiFiManager) ─────────────────────────────
 * Sin credenciales en el codigo: la 1a vez (o si no hay red guardada) el nodo
 * crea su propia red de configuracion (AP_SETUP_NAME). Te conectas con el
 * celular, eliges la red real + su clave, y queda guardada en flash.
 * Manten BOOT (FORCE_PORTAL_PIN) pulsado al encender para reabrir el portal.
 * Se llama UNA vez en setup(); en el loop solo se reconecta (no se reabre el
 * portal, eso bloquearia el detector TinyML). */
static void wifiSetup() {
  WiFiManager wm;
  wm.setConfigPortalTimeout(180);        // 3 min; si nadie configura, sigue e intenta luego

  pinMode(FORCE_PORTAL_PIN, INPUT_PULLUP);
  bool forzar = (digitalRead(FORCE_PORTAL_PIN) == LOW);

  const char *apPass = (strlen(AP_SETUP_PASS) >= 8) ? AP_SETUP_PASS : nullptr;
  bool ok;
  if (forzar) {
    Serial.println(F("[WIFI] BOOT pulsado: abriendo portal de configuracion..."));
    ok = wm.startConfigPortal(AP_SETUP_NAME, apPass);
  } else {
    Serial.println(F("[WIFI] Conectando (o abriendo portal si no hay red guardada)..."));
    ok = wm.autoConnect(AP_SETUP_NAME, apPass);   // usa creds guardadas; si no, crea el AP
  }

  if (ok) {
    Serial.print(F("[WIFI] OK  IP=")); Serial.println(WiFi.localIP());
    WiFi.setAutoReconnect(true);
  } else {
    Serial.println(F("[WIFI] No se configuro a tiempo; reintentara en el loop."));
  }
}

/* ──────────────────────────────── MQTT ──────────────────────────────────── */
/* Resuelve un host por mDNS (nombre + ".local") y, si no responde o el nombre está
 * vacío, cae a una IP fija de respaldo. Genérico: lo usan TANTO el broker (en la
 * nube: MQTT_MDNS / MQTT_HOST) COMO la cámara (en la laptop: CAM_MDNS / CAM_HOST).
 * Devuelve la IP como String (vacía si no resolvió ni hay respaldo). */
static String resolveHost(const char *mdnsName, const char *fallbackIp, const char *label) {
  if (mdnsName && strlen(mdnsName) > 0) {
    IPAddress ip = MDNS.queryHost(mdnsName, 1500);
    if (ip != IPAddress(0, 0, 0, 0)) {
      Serial.print(F("[mDNS] ")); Serial.print(label);
      Serial.print(F(" '")); Serial.print(mdnsName);
      Serial.print(F(".local' -> ")); Serial.println(ip);
      return ip.toString();
    }
  }
  if (fallbackIp && strlen(fallbackIp) > 0) {
    Serial.print(F("[mDNS] ")); Serial.print(label);
    Serial.print(F(": sin mDNS; uso IP fija ")); Serial.println(fallbackIp);
    return String(fallbackIp);
  }
  Serial.print(F("[mDNS] ")); Serial.print(label);
  Serial.println(F(": no encontrado y sin IP de respaldo."));
  return String();
}

/* Aplica un host al cliente MQTT (begin guarda el puntero, por eso g_brokerHost
 * es global y persiste). */
static void setBroker(const String &host) {
  g_brokerHost = host;
  g_mqtt.begin(g_brokerHost.c_str(), MQTT_PORT, g_wifiClient);
}

/* Se ejecuta cuando llega un mensaje a un tópico suscrito (TOPIC_CMD).
 * El servidor, tras recibir la alerta y guardar el video, publica aquí "restart"
 * para que el nodo se reinicie y deje el micrófono/I2S limpio para la próxima
 * detección (workaround al congelamiento tras la subida del video). */
static void onMqttMessage(String &topic, String &payload) {
  Serial.print(F("[MQTT] cmd ")); Serial.print(topic);
  Serial.print(F(" -> ")); Serial.println(payload);

  // Recalibracion a demanda: util tras mover el nodo a un sitio con otro ruido,
  // sin reflashear ni esperar los 60 min de recal por inactividad. Calibra ~50 s
  // (manten el ambiente SIN mosquito mientras dura) y guarda el umbral en NVS.
  if (payload.indexOf("recalib") >= 0) {
    detectorForceRecalibration();
    return;
  }

  // Heartbeat a demanda: el servidor (un boton) pide el estado del nodo al
  // instante en vez de esperar el intervalo periodico. Incluye el umbral actual.
  if (payload.indexOf("heartbeat") >= 0) {
    smRequestHeartbeat();
    return;
  }

  if (payload.indexOf("restart") >= 0 || payload.indexOf("reboot") >= 0 ||
      payload.indexOf("setvidfor") >= 0) {
    Serial.println(F("[CMD] reinicio solicitado por el servidor. Reiniciando..."));
    smSaveResetReason("video_sent_ok");   // flag en NVS: el video se subio bien antes del reboot
    g_mqtt.publish(TOPIC_STATUS, R"({"online":false,"reason":"cmd_restart"})", true, 1);
    delay(300);           // deja salir el último publish antes de cortar
    ESP.restart();
  }
}

static void mqttConnect() {
  if (g_mqtt.connected() || !WiFi.isConnected()) return;

  // Re-resolver el broker como mucho cada 15 s (por si cambió de IP o recién
  // arrancó). Entre tanto, se reintenta con el host ya cacheado.
  static uint32_t lastResolve = 0;
  uint32_t now = millis();
  if (g_brokerHost.isEmpty() || now - lastResolve > 15000) {
    lastResolve = now;
    String h = resolveHost(MQTT_MDNS, MQTT_HOST, "broker");
    if (h.length() && h != g_brokerHost) setBroker(h);
  }
  if (g_brokerHost.isEmpty()) return;

  Serial.print(F("[MQTT] Conectando a ")); Serial.print(g_brokerHost); Serial.print(':'); Serial.print(MQTT_PORT);
  if (g_mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS)) {
    Serial.println(F(" OK"));
    g_mqtt.publish(TOPIC_STATUS, R"({"online":true})", true, 1);
    g_mqtt.subscribe(TOPIC_CMD, 1);    // escucha ordenes del servidor (ej. "restart")
    Serial.print(F("[MQTT] suscrito a ")); Serial.println(TOPIC_CMD);
  } else {
    Serial.print(F(" FALLO err=")); Serial.println(g_mqtt.lastError());
  }
}

/* ─────────────────────────── INMP441 / I2S ──────────────────────────────── */
static bool micInit() {
  i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO, I2S_ROLE_MASTER);
  if (i2s_new_channel(&chan_cfg, nullptr, &g_rx_chan) != ESP_OK) return false;

  i2s_std_config_t rx_cfg = {
    .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(MIC_SAMPLE_RATE),
    .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO),
    .gpio_cfg = {
      .mclk = I2S_GPIO_UNUSED,
      .bclk = (gpio_num_t)MIC_BCLK_PIN,
      .ws   = (gpio_num_t)MIC_WS_PIN,
      .dout = I2S_GPIO_UNUSED,
      .din  = (gpio_num_t)MIC_DATA_PIN,
      .invert_flags = { false, false, false },
    },
  };
  if (i2s_channel_init_std_mode(g_rx_chan, &rx_cfg) != ESP_OK ||
      i2s_channel_enable(g_rx_chan) != ESP_OK) {
    i2s_del_channel(g_rx_chan); g_rx_chan = nullptr; return false;
  }
  return true;
}

/*
 * Recrea por completo el canal I2S (disable -> delete -> micInit) para limpiar los
 * descriptores DMA que quedan corruptos tras los bloqueos largos de la alerta:
 * reportarSensores() (DS18B20 ~750 ms) y sobre todo capturarYEnviarVideo() (subida
 * HTTP de 6+ s) dejan de leer el micro tanto tiempo que la captura queda devolviendo
 * silencio (mosquito=0.00) hasta el siguiente reinicio. Un simple disable/enable NO
 * basta (los descriptores siguen colgados); hay que borrar y reconstruir el canal.
 */
static void micRestart() {
  if (g_rx_chan) {
    i2s_channel_disable(g_rx_chan);
    i2s_del_channel(g_rx_chan);
    g_rx_chan = nullptr;
  }
  if (micInit()) Serial.println(F("[MIC] I2S resincronizado tras la alerta."));
  else           Serial.println(F("[MIC] re-init FALLO tras la alerta — revisa pines/heap."));
}

/*
 * Llena g_sampleBuffer con una ventana completa (WINDOW_SAMPLES muestras int16).
 * El INMP441 entrega 32 bits; tomamos los bits altos y aplicamos MIC_GAIN_SHIFT
 * como ganancia (menor shift = más amplificación). Bloquea ~0.5 s (1 ventana).
 */
static void captureAudioWindow() {
  static int32_t raw[256];
  size_t got = 0;
  while (got < WINDOW_SAMPLES) {
    size_t want = WINDOW_SAMPLES - got;
    if (want > 256) want = 256;
    size_t br = 0;
    if (i2s_channel_read(g_rx_chan, raw, want * sizeof(int32_t), &br, pdMS_TO_TICKS(200)) != ESP_OK) break;
    size_t n = br / sizeof(int32_t);
    for (size_t i = 0; i < n && got < WINDOW_SAMPLES; i++) {
      int32_t s = raw[i] >> MIC_GAIN_SHIFT;          // ganancia
      if (s >  32767) s =  32767;                    // clamp a int16
      if (s < -32768) s = -32768;
      g_sampleBuffer[got++] = (int16_t)s;
    }
    if (n == 0) break;
  }
  // Si quedó corto (timeout), rellena con silencio para no descuadrar la ventana.
  while (got < WINDOW_SAMPLES) g_sampleBuffer[got++] = 0;
}

/* Callback que Edge Impulse usa para leer la señal (convierte int16 → float). */
static int micGetData(size_t offset, size_t length, float *out_ptr) {
  numpy::int16_to_float(&g_sampleBuffer[offset], out_ptr, length);
  return 0;
}

/* Resuelve qué índice de clase es el "mosquito" (busca la etiqueta por nombre). */
static void resolveMosquitoIndex(const ei_impulse_result_t &result) {
  for (uint16_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
    String lbl = String(result.classification[i].label);
    lbl.toLowerCase();
    if (lbl.indexOf("mosquito") >= 0 || lbl.indexOf("aedes") >= 0) { g_idxMosquito = i; return; }
  }
  g_idxMosquito = 0;  // fallback: primera clase
  Serial.println(F("[EI] AVISO: no encontre etiqueta 'mosquito'; uso indice 0."));
}

/*
 * Una iteración del detector: captura → inferencia → regla de consecutivas.
 * Devuelve true cuando se confirma una detección (N ventanas seguidas).
 */
static bool runInferenceWindow() {
  captureAudioWindow();

  signal_t signal;
  signal.total_length = WINDOW_SAMPLES;
  signal.get_data     = &micGetData;

  ei_impulse_result_t result = { 0 };
  EI_IMPULSE_ERROR r = run_classifier(&signal, &result, false);
  if (r != EI_IMPULSE_OK) {
    Serial.print(F("[EI] run_classifier err=")); Serial.println(r);
    return false;
  }

  if (g_idxMosquito < 0) resolveMosquitoIndex(result);

  float conf = result.classification[g_idxMosquito].value;
  g_ultimaConfianza = conf;

  // Auto-recuperacion: si el micro/pipeline se corrompe, el score se queda clavado
  // en 0.0 o 1.0. Tras 20 ventanas asi seguidas, smOnScore registra la razon en NVS
  // y reinicia el nodo (no hace nada si el score es normal).
  smOnScore(conf);

  // Pipeline adaptativo: calibra el umbral solo, promedia 5 ventanas y recalibra
  // por inactividad (ver detector_autocalib.h). Sustituye a UMBRAL_MOSQUITO fijo
  // y a la regla de N ventanas consecutivas.
  det_result_t det = detectorProcess(conf);

  Serial.printf("[EI] mosquito=%.2f  media=%.2f  umbral=%.2f  [%s]  (DSP %dms + clf %dms)\n",
                conf, detectorAvg(), detectorThreshold(), detectorStateStr(),
                result.timing.dsp, result.timing.classification);

  return (det == DET_CONFIRMED);
}

/* Lee los sensores UNA sola vez, los publica por MQTT y los muestra en el monitor.
 * Se llama SOLO al confirmar una alerta: el nodo se concentra en escuchar audio y
 * lee sensores únicamente cuando hay algo que reportar. Así no hay telemetría
 * periódica y el DS18B20 (lectura bloqueante ~750 ms) deja de congelar la captura
 * de audio: cero puntos ciegos mientras escucha. */
static void reportarSensores() {
  if (!g_mqtt.connected()) return;
  char buf[200];

  int   turbRaw = analogRead(TURBIDITY_PIN);
  float turbV   = (float)turbRaw * 3.3f / 4095.0f;
  g_ds18b20.requestTemperatures();
  float tempC = g_ds18b20.getTempCByIndex(0);
  if (tempC == DEVICE_DISCONNECTED_C) tempC = -127.0f;

  // --- Publicar por MQTT (lo que el gateway pega a la alerta) ---
  snprintf(buf, sizeof(buf),
    "{\"turb_raw\":%d,\"turb_v\":%.3f,\"temp_c\":%.2f}", turbRaw, turbV, tempC);
  g_mqtt.publish(TOPIC_SENSORS, buf);
  if (g_gpsFix) {
    snprintf(buf, sizeof(buf),
      "{\"lat\":%.6f,\"lon\":%.6f,\"alt\":%.1f,\"sats\":%d}", g_lat, g_lon, g_alt, g_sats);
    g_mqtt.publish(TOPIC_GPS, buf, true, 0);
  }
  snprintf(buf, sizeof(buf), "{\"mosquito_conf\":%.2f}", g_ultimaConfianza);
  g_mqtt.publish(TOPIC_AUDIO, buf);
  snprintf(buf, sizeof(buf),
    "{\"uptime_ms\":%lu,\"rssi\":%d,\"heap_free\":%u}",
    millis(), WiFi.RSSI(), (unsigned)ESP.getFreeHeap());
  g_mqtt.publish(TOPIC_STATUS, buf, true, 0);

  // --- Mostrar en el monitor serie ---
  Serial.println(F("        --- Sensores que se envian con la alerta ---"));
  Serial.printf("        Temperatura : %.2f C%s\n", tempC, (tempC <= -127.0f) ? "  (DS18B20 sin conexion)" : "");
  Serial.printf("        Turbidez    : %.3f V  (raw %d)\n", turbV, turbRaw);
  Serial.printf("        Audio conf  : %.2f  (mosquito)\n", g_ultimaConfianza);
  if (g_gpsFix)
    Serial.printf("        GPS         : %.6f, %.6f  (%d sats, alt %.1f m)\n", g_lat, g_lon, g_sats, g_alt);
  else
    Serial.println(F("        GPS         : sin fix todavia"));
  Serial.printf("        WiFi RSSI   : %d dBm\n", WiFi.RSSI());
}

/* ─────────────── CÁMARA IP: jalar rafaga y subirla al gateway ───────────────
 * Al detectar un mosquito, el nodo pide varias fotos JPEG a la webcam expuesta por
 * el servidor (cam_stream.py en CAM_PORT) durante VIDEO_SECONDS, las empaqueta en
 * un buffer PSRAM como [4B longitud][jpeg]... y las SUBE de una sola vez al gateway
 * (UPLOAD_PORT, fmt=jpegseq). El gateway arma el video y corre el detector.
 * NOTA: requiere PSRAM habilitada (Tools -> PSRAM: "OPI PSRAM"). */
static uint8_t* g_videoBuf = nullptr;

static void capturarYEnviarVideo() {
  if (!WiFi.isConnected() || g_brokerHost.isEmpty()) {
    Serial.println(F("[VID] sin WiFi/host; no se captura video."));
    return;
  }
  if (g_videoBuf == nullptr) {
    g_videoBuf = (uint8_t*) ps_malloc(VIDEO_BUF_BYTES);
    if (g_videoBuf == nullptr) {
      Serial.println(F("[VID] ps_malloc fallo (¿PSRAM deshabilitada?); no se sube video."));
      return;
    }
  }

  // La cámara vive en la LAPTOP (LAN), en un host DISTINTO del broker/gateway (nube).
  // Se resuelve por su cuenta; si mDNS falla, reusa el último g_camHost cacheado.
  String ch = resolveHost(CAM_MDNS, CAM_HOST, "camara");
  if (ch.length()) g_camHost = ch;
  if (g_camHost.isEmpty()) {
    Serial.println(F("[VID] sin host de camara; no se captura video."));
    return;
  }
  String camUrl = "http://" + g_camHost + ":" + String(CAM_PORT) + CAM_PATH;
  size_t used = 0;
  int nframes = 0;
  uint32_t t0 = millis();
  WiFiClient client;

  while (millis() - t0 < (uint32_t)VIDEO_SECONDS * 1000 && nframes < VIDEO_MAX_FRAMES) {
    HTTPClient http;
    http.begin(client, camUrl);
    int code = http.GET();
    if (code == 200) {
      int len = http.getSize();
      if (len > 0 && used + 4 + (size_t)len <= VIDEO_BUF_BYTES) {
        // cabecera de 4 bytes con la longitud (big-endian)
        g_videoBuf[used + 0] = (len >> 24) & 0xFF;
        g_videoBuf[used + 1] = (len >> 16) & 0xFF;
        g_videoBuf[used + 2] = (len >> 8) & 0xFF;
        g_videoBuf[used + 3] = (len) & 0xFF;
        // leer el JPEG al buffer
        WiFiClient* st = http.getStreamPtr();
        int got = 0;
        uint8_t* dst = g_videoBuf + used + 4;
        uint32_t tr = millis();
        while (got < len && millis() - tr < 2000) {
          int avail = st->available();
          if (avail > 0) got += st->readBytes(dst + got, min(avail, len - got));
          else delay(1);
        }
        if (got == len) { used += 4 + len; nframes++; }
      }
    }
    http.end();
    delay(VIDEO_FRAME_GAP_MS);
  }

  Serial.printf("[VID] rafaga: %d fotos, %u bytes\n", nframes, (unsigned)used);
  if (nframes == 0) return;

  String upUrl = "http://" + g_brokerHost + ":" + String(UPLOAD_PORT) + UPLOAD_PATH +
                 "?device=" + DEVICE_ID + "&fmt=jpegseq&seconds=" + String(VIDEO_SECONDS);
  HTTPClient up;
  up.begin(client, upUrl);
  up.addHeader("Content-Type", "application/octet-stream");
  int code = up.POST(g_videoBuf, used);
  Serial.printf("[VID] subida al gateway -> HTTP %d\n", code);
  up.end();
}

/* Publica el disparo que la cámara (Capa 3) está esperando, y con él la telemetría. */
static void dispararAlerta(const char* source, float conf) {
  uint32_t now = millis();
  if (now - g_lastAlert < ALERT_COOLDOWN_MS) return;   // anti-rebote
  g_lastAlert = now;
  if (!g_mqtt.connected()) { Serial.println(F("[ALERT] sin MQTT; disparo perdido.")); return; }

  char buf[160];
  snprintf(buf, sizeof(buf),
           "{\"node_name\":\"%s\",\"source\":\"%s\",\"confidence\":%.2f,"
           "\"ts\":%lu,\"timestamp\":%lu,\"seq\":%lu}",
           smNodeName(), source, conf, now,
           (unsigned long)smUnix(), (unsigned long)smSeqNext());
  g_mqtt.publish(TOPIC_ALERT, buf, false, 1);          // QoS 1
  Serial.print(F("[ALERT] MOSQUITO -> ")); Serial.println(buf);

  reportarSensores();   // SOLO ahora (al detectar) se leen, envían y muestran los sensores
  capturarYEnviarVideo();  // NUEVO: jala la rafaga de la camara IP y la sube al gateway
  micRestart();   // resincroniza el I2S tras los bloqueos largos de arriba (si no, queda en 0.00)
}

/* ─────────────────────────── GPS NMEA ───────────────────────────────────── */
static double nmeaToDecimal(const char* rawv, char dir) {
  double val = atof(rawv);
  int deg = (int)(val / 100);
  double dec = deg + (val - deg * 100.0) / 60.0;
  if (dir == 'S' || dir == 'W') dec = -dec;
  return dec;
}

static void parseGGA(const String& line) {
  int idx[15]; int field = 0; idx[0] = 0;
  for (int i = 0; i < (int)line.length() && field < 14; i++)
    if (line[i] == ',') { field++; idx[field] = i + 1; }
  if (field < 9) return;
  String latRaw = line.substring(idx[2], idx[3] - 1); char latDir = line[idx[3]];
  String lonRaw = line.substring(idx[4], idx[5] - 1); char lonDir = line[idx[5]];
  String satsStr = line.substring(idx[7], idx[8] - 1);
  String altStr  = line.substring(idx[9], idx[10] - 1);
  if (latRaw.length() && lonRaw.length()) {
    g_lat = nmeaToDecimal(latRaw.c_str(), latDir);
    g_lon = nmeaToDecimal(lonRaw.c_str(), lonDir);
    g_alt = altStr.toFloat(); g_sats = satsStr.toInt(); g_gpsFix = true;
  }
}

static void gpsBackground() {
  while (GpsSerial.available()) {
    char c = (char)GpsSerial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (g_nmeaBuf.startsWith("$GPGGA") || g_nmeaBuf.startsWith("$GNGGA")) parseGGA(g_nmeaBuf);
      g_nmeaBuf = "";
    } else g_nmeaBuf += c;
  }
}

/* ─────────────────────────── setup / loop ───────────────────────────────── */
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println(F("\nESP32-S3 — Nodo TinyML (detector acustico de mosquito)"));
  Serial.printf("[EI] modelo: %d Hz, %d muestras/ventana, %d clases\n",
                (int)MIC_SAMPLE_RATE, (int)WINDOW_SAMPLES, (int)EI_CLASSIFIER_LABEL_COUNT);

  analogReadResolution(12);
  pinMode(TURBIDITY_PIN, INPUT);

  g_ds18b20.begin();
  GpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

  if (!micInit()) Serial.println(F("[MIC] INMP441 init FALLO — revisa I2S/pines."));
  else            Serial.println(F("[MIC] INMP441 listo."));

#if ENABLE_GPIO_TRIGGER
  pinMode(ALERT_PIN_A, INPUT_PULLDOWN);
  pinMode(ALERT_PIN_B, INPUT_PULLDOWN);
  attachInterrupt(digitalPinToInterrupt(ALERT_PIN_A), onGpioAlertISR, RISING);
  attachInterrupt(digitalPinToInterrupt(ALERT_PIN_B), onGpioAlertISR, RISING);
#endif

  wifiSetup();
  if (WiFi.isConnected() && !MDNS.begin(DEVICE_ID))
    Serial.println(F("[mDNS] no se pudo iniciar (se usara IP fija de respaldo)."));
  setBroker(resolveHost(MQTT_MDNS, MQTT_HOST, "broker"));   // broker en la nube (mDNS o IP fija)
  g_mqtt.onMessage(onMqttMessage);          // ordenes entrantes del servidor (TOPIC_CMD)
  g_mqtt.setWill(TOPIC_STATUS, R"({"online":false})", true, 1);
  mqttConnect();

  detectorBegin();   // calibracion automatica del umbral (o carga el guardado en NVS)
  smBegin(NODE_NAME);   // identidad NVS + programa heartbeat (SNTP arranca al haber WiFi)

  Serial.println(F("[RUN] Detector en marcha. Confianza ventana a ventana abajo:"));
}

void loop() {
  // Mantener conectividad viva (reconecta sin reabrir el portal: eso bloquearia
  // el detector). smManageWifi aplica backoff exponencial (1,2,4..300 s) en vez
  // del WiFi.reconnect() inmediato.
  smManageWifi();
  if (!g_mqtt.connected()) mqttConnect();
  g_mqtt.loop();
  gpsBackground();

  // Auto-monitoreo: SNTP, heartbeat periodico (nodes/<name>/heartbeat) y flush de
  // la cola al reconectar. Publica el umbral adaptativo actual del detector.
  smLoop(&g_mqtt, detectorThreshold());

#if ENABLE_GPIO_TRIGGER
  if (g_gpioAlertFlag) { g_gpioAlertFlag = false; dispararAlerta("gpio", g_ultimaConfianza); }
#endif

  // ── núcleo TinyML: el nodo se dedica a escuchar; una ventana de 0.5 s ──
  // (sin telemetría periódica: los sensores se leen solo al disparar la alerta)
  if (runInferenceWindow()) {
    dispararAlerta("audio", g_ultimaConfianza);
  }
}

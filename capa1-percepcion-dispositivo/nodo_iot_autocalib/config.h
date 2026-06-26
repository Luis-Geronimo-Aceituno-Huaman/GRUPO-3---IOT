#pragma once
/*
 * config.h — firmware de PRODUCCION con TinyML (Edge Impulse) para el nodo ESP32-S3.
 *
 * Diferencia con firmware/config.h (el probe): aqui se anaden las "3 perillas" del
 * detector acustico y el nombre de la libreria del modelo exportado.
 */

/* ───────── WiFi (gestionado por WiFiManager — NO se hardcodea aqui) ─────────
 * La 1a vez (o si no hay red guardada, o si no logra conectar) el nodo crea su
 * propia red de configuracion AP_SETUP_NAME. Te conectas con el celular, eliges
 * la red real + su clave, y queda guardada en flash (no hay que reflashear).
 * Manten BOOT (GPIO0) pulsado al ENCENDER para reabrir el portal a proposito,
 * util para cambiar de red. */
#define AP_SETUP_NAME    "Nodo-IoT-Setup"   // red de configuracion que crea el nodo
#define AP_SETUP_PASS    "12345678"         // clave del portal (>=8 chars) o "" para abierta
#define FORCE_PORTAL_PIN 0                   // BOOT=GPIO0: pulsado al encender abre el portal

/* ───────── MQTT (broker + gateway: en la NUBE) ─────────
 * Tras migrar el server, el broker y el gateway viven en la VM de la nube. El nodo
 * intenta mDNS primero (útil si en DESARROLLO corres el broker en la laptop) y, al
 * fallar, cae a la IP pública fija MQTT_HOST.
 *   - PRODUCCIÓN (nube): deja MQTT_MDNS vacío ("") y pon la IP pública en MQTT_HOST
 *     -> va directo, sin perder 1.5 s esperando un mDNS que no existe en la LAN.
 *   - DESARROLLO (broker local): pon en MQTT_MDNS el hostname de tu laptop. */
#define MQTT_MDNS     "iot-server-2"                 // "" = ir directo a MQTT_HOST. Hostname de la laptop solo en dev local.
#define MQTT_HOST     "161.153.193.114"  // IP PÚBLICA de la VM Oracle. "" para desactivar.
#define MQTT_PORT     1883
#define MQTT_USER     "esp32"            // usuario creado con mosquitto_passwd (capa2-red/passwd)
#define MQTT_PASS     "iotmosquito2026"  // clave del broker (cambiala junto con el passwd del broker)
#define DEVICE_ID     "esp32-01"

/* ───────── Tópicos (contrato MQTT_SPEC.md) ───────── */
#define TOPIC_SENSORS "devices/" DEVICE_ID "/sensors"
#define TOPIC_GPS     "devices/" DEVICE_ID "/gps"
#define TOPIC_AUDIO   "devices/" DEVICE_ID "/audio"
#define TOPIC_STATUS  "devices/" DEVICE_ID "/status"
#define TOPIC_ALERT   "devices/" DEVICE_ID "/alert"
#define TOPIC_CMD     "devices/" DEVICE_ID "/cmd"      // el servidor publica aqui ordenes (ej. "restart")

/* (Sin telemetría periódica: los sensores se leen y publican SOLO al disparar la
 *  alerta, para que el nodo se concentre en escuchar audio sin puntos ciegos.) */

/* ───────── CÁMARA IP (en la LAPTOP, por LAN) + SUBIDA DE VIDEO ─────────
 * Al confirmar una alerta, el nodo jala una RÁFAGA de fotos de la webcam expuesta
 * por la laptop (cam_stream.py) y la SUBE al gateway. Tras migrar el server, la
 * CÁMARA (laptop) y el GATEWAY (nube) viven en hosts DISTINTOS:
 *   - CÁMARA: se resuelve por su cuenta (CAM_MDNS / CAM_HOST) -> g_camHost (LAN).
 *     Sigue por mDNS porque la laptop SÍ está en tu red local.
 *   - SUBIDA: usa g_brokerHost (la nube), el mismo host del broker (UPLOAD_PORT).   */
#define CAM_MDNS          "iot-server-2"       // hostname real de la laptop con cam_stream.py (mDNS en la LAN)
#define CAM_HOST          "192.168.18.19"    // IP de respaldo de la laptop si falla mDNS
#define CAM_PORT          8091          // cam_stream.py (webcam como camara IP)
#define CAM_PATH          "/snapshot.jpg"
#define UPLOAD_PORT       8090          // receptor de clips del gateway (EN LA NUBE)
#define UPLOAD_PATH       "/upload"
#define VIDEO_SECONDS     6             // duracion de la rafaga al detectar
#define VIDEO_MAX_FRAMES  60            // tope de fotogramas (proteccion de RAM)
#define VIDEO_BUF_BYTES   (2u*1024u*1024u)  // 2 MB en PSRAM para la rafaga
#define VIDEO_FRAME_GAP_MS 80          // pausa entre fotos (regula los ~fps)

/* ─────────────────────────────────────────────────────────────────────────
 *  EDGE IMPULSE — el modelo TinyML
 *
 *  Importa el .zip exportado en Arduino IDE:
 *      Sketch → Include Library → Add .ZIP Library…  →  elige
 *      ei-luis12345-project-1-arduino-1.0.1-impulse-#1.zip
 *
 *  Luego mira en  Sketch → Include Library  el nombre real de la librería y,
 *  si difiere, ajústalo en EI_MODEL_HEADER (abajo, en el .ino).
 * ───────────────────────────────────────────────────────────────────────── */

/* ───────── Las 3 perillas del detector acústico ─────────
 *  (ver "TINY ML - EDGE AI - EDGE ML.md", sección "Código Explicación")        */

// (SUPERSEDIDO en esta version) Umbral fijo de confianza.
//   En nodo_iot_autocalib ya NO se usa: el umbral se calibra solo segun el ruido
//   real del lugar (ver detector_autocalib.h). Se deja por compatibilidad.
#define UMBRAL_MOSQUITO    0.50f

// (SUPERSEDIDO) Ventanas consecutivas. En esta version se reemplaza por la media
//   movil de DET_SLIDING ventanas del pipeline adaptativo.
#define VENTANAS_SEGUIDAS  2

/* ───────── Pipeline adaptativo (detector_autocalib.h) ─────────
 * Estos #define SOBREESCRIBEN los valores por defecto del modulo. Descomenta y
 * ajusta solo si lo necesitas; si los dejas comentados, usa los del header.
 *
 *   DET_CALIB_SAMPLES   100   // ventanas de calibracion al arrancar (~50 s)
 *   DET_RECAL_SAMPLES   20    // ventanas de recalibracion (~10 s)
 *   DET_SLIDING         5     // tamano de la media movil
 *   DET_MARGIN          0.08f // margen de seguridad sobre el percentil 99
 *   DET_IDLE_RECAL_MS   3600000UL  // 60 min sin deteccion -> recalibra
 *   DET_FORCE_CALIB_ON_BOOT 0 // 0 = reusa umbral de NVS tras reboot (recomendado
 *                             //     con el reinicio-tras-alerta); 1 = calibra siempre
 *   DET_LED_PIN         -1    // LED que se enciende al terminar la calibracion
 *   DET_OUT_PIN         -1    // pulso GPIO al confirmar una deteccion
 */
#define DET_FORCE_CALIB_ON_BOOT 0   // 0 = reusa el umbral de NVS tras cada reboot (alerta/watchdog) -> sin 50 s ciego.
                                    //     Recalibra solo: por inactividad (60 min) o a demanda con el comando MQTT "recalib".
#define DET_SLIDING             2   // tu mosquito dura ~2 ventanas: media corta para no diluirlo
#define DET_CONSEC_CONFIRM      2   // exige 2 ventanas seguidas con media>umbral para disparar
#define DET_MARGIN              0.05f // margen mas ajustado sobre el ruido (antes 0.08)
// #define DET_LED_PIN 2

// Ganancia del micrófono INMP441 (desplazamiento de bits).
//   CALIBRADO = 12 (mejor separacion zumbido/silencio). Si la confianza queda
//   plana cerca de 0, BAJA este numero (11, 10, 9…); si satura, SUBELO (13).
#define MIC_GAIN_SHIFT     12

// Anti-rebote del disparo: tras una alerta, ignora nuevas durante este tiempo.
#define ALERT_COOLDOWN_MS  10000

/* Disparo manual por GPIO (se conserva del probe como respaldo; 0 = desactivado).
 * Desactivado: el nodo SOLO dispara por audio (TinyML, 3 ventanas seguidas).
 * Evita falsos positivos de los pines 15/16 flotando. Pon 1 si cableas un boton. */
#define ENABLE_GPIO_TRIGGER  0

/* ─────────────────────────────────────────────────────────────────────────
 *  AUTO-MONITOREO / AUTO-RECUPERACION (self_monitor.h)
 *  Subconjunto del spec que NO toca infraestructura (sin mTLS / Secure Boot).
 * ───────────────────────────────────────────────────────────────────────── */

// Nombre del nodo. Solo es el VALOR POR DEFECTO del primer arranque: tras eso se
// lee de NVS (namespace "node_config"). Para cambiarlo sin reflashear, usa
// smSetNodeName("nodo_02") una vez, o borra la NVS.
#define NODE_NAME            DEVICE_ID        // p.ej. "esp32-01"

// Estos #define SOBREESCRIBEN los valores por defecto de self_monitor.h.
// Descomenta solo lo que quieras ajustar.
// #define SM_HEARTBEAT_MS  (10UL*60UL*1000UL)  // intervalo del heartbeat (10 min)
// #define SM_FIRST_HB_MS   15000UL             // primer heartbeat tras boot (~15 s)
// #define SM_ANOM_MAX      20                  // scores 0.0/1.0 seguidos -> restart
// #define SM_BATTERY_PCT_EXPR  (-1)            // -1 = sin hardware de bateria

// Topics nuevos del auto-monitoreo (estructura del spec: nodes/<name>/...).
// Los construye self_monitor.h a partir del node_name; aqui solo se documentan:
//   nodes/<name>/heartbeat   -> keep-alive cada 10 min
//   nodes/<name>/status      -> eventos de auto-monitoreo

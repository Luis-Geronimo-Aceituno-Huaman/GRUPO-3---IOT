# Simuladores (pruebas sin hardware)

`tools/simulador_nodo/` — servidor web local de pruebas (**no** se despliega a
producción). Un solo proceso con dos pestañas:

```bash
cd tools/simulador_nodo && python3 app.py     # http://localhost:8200
```

Requiere el broker y PostgreSQL arriba (`docker compose up -d` en la raíz) y,
para el pipeline completo, el gateway (`:8090`).

## Pestaña 1 · Simulador de nodo (MQTT)

Un **ESP32 virtual indistinguible del real** para el backend: publica exactamente
los topics/payloads del firmware (ver `capa2-red/MQTT_SPEC.md`):

- `devices/<id>/alert` (QoS1) → `devices/<id>/sensors` → `gps` (retained) →
  `audio` → `status`, en el mismo orden que `dispararAlerta()` del .ino.
- `nodes/<id>/heartbeat` periódico (configurable; el real usa 10 min).
- `devices/<id>/availability` con LWT retained (online true/false).
- **Escucha `devices/<id>/cmd`** y responde a `heartbeat` (inmediato), `recalib`
  (simulado) y `restart` (resetea uptime/seq) — probalo desde la pestaña Estado
  del dashboard.
- Al disparar, sube una **ráfaga jpegseq sintética** al gateway
  (`[4B len big-endian][JPEG]…`, formato binario exacto del firmware): frames
  640×480 con N "mosquitos" (puntos oscuros de 3 px, trayectoria errática) que
  **ejercitan el detector real**. Con "movimiento" apagado el clip va vacío y el
  detector debe DESCARTARLO (prueba de falsos positivos).

Controles: temperatura, turbidez, humedad/pH/nivel de agua (en 0 = el nodo "no
tiene" ese sensor, como el ESP32 real), confianza TinyML, nº de mosquitos del
video, intervalo del modo AUTO, posición GPS. Los sliders se aplican en vivo.

Los sensores extra viajan como **claves aditivas** en el JSON de `sensors` — el
protocolo no cambia y el ESP32 real sigue siendo 100 % compatible. Los nodos
creados quedan marcados `is_simulated=TRUE` (etiqueta «SIM» en dashboard/mapa).

## Pestaña 2 · Alertas sintéticas (BD directa)

Para poblar dashboard/mapa **sin video y sin detector**: inserta alertas con
`is_synthetic=TRUE` directamente en la BD (nodo, cantidad, reparto en días hacia
atrás, estado inicial, sensores → el nivel de riesgo se calcula con esos datos).

Equivalente autenticado para usar desde fuera: `POST /api/alerts/synthetic`
(admin) en el dashboard.

Filtrarlas: `GET /api/alerts?include_synthetic=0`. Borrarlas:
```sql
DELETE FROM alerts WHERE is_synthetic;
```

## Escenarios de prueba típicos

1. **Pipeline completo**: iniciar nodo → «Disparar alerta» → ver en el gateway
   `POSITIVO` → alerta `pendiente` en el dashboard con video y riesgo.
2. **Falso positivo**: apagar «movimiento» → disparar → el gateway descarta.
3. **Riesgo**: subir temp a 28 °C + turbidez 2.5 V + humedad 75 % → en ≤5 min el
   nodo pasa a 🔴 crítico en el mapa.
4. **Liveness**: detener el nodo → a los 30 min pasa a OFFLINE (job de heartbeat).
5. **Workflow**: generar 20 sintéticas → atender/resolver/marcar falsas → ver
   historial, mapa limpio y auditoría.

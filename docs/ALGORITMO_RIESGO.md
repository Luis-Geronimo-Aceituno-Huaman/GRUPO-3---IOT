# Algoritmo de nivel de riesgo

`capa3-procesamiento-servidor/risk.py` — score 0–100 por nodo según condiciones
de cría de *Aedes aegypti* + actividad reciente de alertas.

## Factores (pesos por defecto)

| Factor | Peso | Cálculo |
|---|---|---|
| `temp` | 0.30 | Trapezoidal: factor 1.0 en 25–30 °C (óptimo de reproducción), decae lineal a 0 hacia 15/40 °C. `temp_c ≤ -100` (sonda desconectada) = **ausente**, no penaliza |
| `turbidez` | 0.25 | Lineal entre `turb_v_baja` (0.5 V → 0) y `turb_v_alta` (2.0 V → 1). `turb_invertido` para sensores que dan menos voltaje al agua turbia |
| `humedad` | 0.20 | Trapezoidal, óptimo 60–80 % HR (el ESP32 real no la tiene) |
| `ph` | 0.05 | 1.0 dentro de 6.5–8.5 (agua viable para larvas), decae ±2 |
| `nivel_agua` | 0.05 | Lineal, satura en `nivel_agua_max` (10 cm) |
| `actividad` | 0.25 | Nº de alertas del nodo en las últimas `actividad_ventana_h` (72 h), **excluyendo falsas/descartadas**, satura en `actividad_max` (10) |

**Redistribución de pesos** (clave para la retrocompatibilidad): los factores
cuyo sensor no existe o no reportó (`None`) se excluyen y su peso se reparte
entre los presentes. Así el ESP32 real (solo temp+turbidez+actividad) produce
scores comparables a un nodo con sensores completos.

```
score = 100 · Σ(peso_i · factor_i) / Σ(peso_i presentes)
```

## Niveles (umbrales configurables)

| Score | Nivel | Color |
|---|---|---|
| < 25 | `bajo` | 🟢 |
| 25–49 | `medio` | 🟡 |
| 50–74 | `alto` | 🟠 |
| ≥ 75 | `critico` | 🔴 |

## Dónde y cuándo se calcula (híbrido)

- **Job periódico** (`RiskJob` en `serve.py`, cada 5 min): recalcula todos los
  nodos con su última lectura (`sensor_readings`) + actividad, y persiste
  `nodes.risk_score/risk_level` → el mapa/KPIs leen valores ya calculados.
- **Al insertar una alerta**: el gateway evalúa el riesgo del nodo con los
  sensores del momento y lo estampa en `alerts.risk_level` (foto histórica).
- **On-demand**: `GET /api/node/{id}/risk` devuelve el desglose por factor
  (`factores`, `pesos_efectivos`, `ausentes`) para tooltip/depuración.

## Configuración

Todo vive en `system_config['risk']` (JSONB): pesos, umbrales de nivel, rangos
óptimos, ventana de actividad. Editable en la pestaña **Admin** del dashboard o
`GET|PUT /api/config/risk` (admin). Cambios efectivos en ≤5 min (siguiente ciclo
del job) o al instante en el endpoint on-demand.

## Visualización

- Mapa: color y tamaño del pin del nodo = nivel/score; leyenda fija.
- Dashboard: badges 🟢🟡🟠🔴 en tablas de detecciones/nodos/estado; KPI "nodo más
  crítico"; gráfico "alertas por nodo" coloreado por riesgo.
- Se actualiza solo (auto-refresh de 60 s del dashboard + job de 5 min).

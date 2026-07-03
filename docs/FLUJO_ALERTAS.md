# Flujo de alertas (workflow + auditoría)

## Máquina de estados

```
                       ┌────────────┐
        detector ────▶ │ pendiente  │ ◀── reabrir ──┐
                       └─────┬──────┘               │
              atender/revisar│resolver...           │
        ┌──────────┬─────────┼──────────┬───────────┤
        ▼          ▼         ▼          ▼           │
  en-revision  respondida resuelta  falsa-alarma ───┘   (todas pueden moverse
        └──────────┴─────────┴──────────┴───── descartar ──▶ descartada 🔒 FINAL
```

- Cualquier estado (salvo `descartada`) puede transicionar a cualquier otro
  mediante una **acción**; `descartada` es terminal (el backend rechaza con 409).
- `falsa-alarma` y `descartada` **desaparecen del mapa y del heatmap
  automáticamente** (req. de limpieza) pero siguen en la tabla de detecciones
  (atenuadas) y en la BD — la auditoría nunca se pierde.

## Acciones (API)

`PATCH /api/alerts/{id}/status` con body `{"action": "...", "comment": "..."}`
(requiere sesión; operador o admin):

| Acción | Estado destino |
|---|---|
| `atender` / `responder` | `respondida` |
| `revisar` / `en-revision` | `en-revision` |
| `resolver` | `resuelta` |
| `falsa-alarma` (alias `falso-positivo`) | `falsa-alarma` |
| `descartar` | `descartada` (final) |
| `reabrir` | `pendiente` |

Cada transición ejecuta **en una sola transacción** (`AlertStore.update_status`):
1. `UPDATE alerts SET status, responded_at (primera vez), responded_by`.
2. `INSERT alert_history (old_status, new_status, user_id, username, comment)`.
3. `INSERT events (action='alert.status', ...)` — auditoría global.

## Qué guarda cada alerta

- **Creación**: `ts` (epoch-ms) + `created_at`; el detector crea la primera fila
  del historial (`NULL → pendiente, 'creada por el detector'`).
- **Respuesta**: `responded_at`/`responded_by` (primer usuario que la toca).
- **Comentarios**: en cada fila de `alert_history` (visible en el modal de atención).
- **Riesgo**: `risk_level` estampado por el gateway al momento de la detección.

## Dónde se refleja un cambio

`submitResponse()` (dashboard) → PATCH → al confirmar, el frontend recarga
`/api/alerts` + `/api/nodes` y re-renderiza **tabla, KPIs, mapa, heatmap y
gráficos** — todo queda consistente con la BD. El historial se consulta con
`GET /api/alerts/{id}/history`.

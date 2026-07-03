# Documentación del Sistema Integrado IoT

| Documento | Contenido |
|---|---|
| [ARQUITECTURA.md](ARQUITECTURA.md) | Capas, componentes, flujo event-driven, puertos, módulos |
| [BASE_DE_DATOS.md](BASE_DE_DATOS.md) | Diagrama ER, las 15 tablas, mapeo de estados, migración |
| [FLUJO_ALERTAS.md](FLUJO_ALERTAS.md) | Máquina de estados, acciones, auditoría |
| [MODELO_VISION.md](MODELO_VISION.md) | Pipeline OpenCV, parámetros configurables, ajuste |
| [ALGORITMO_RIESGO.md](ALGORITMO_RIESGO.md) | Factores, pesos, niveles 🟢🟡🟠🔴, dónde se calcula |
| [AUTENTICACION.md](AUTENTICACION.md) | Login, sesiones, roles, qué está protegido |
| [SIMULADORES.md](SIMULADORES.md) | ESP32 virtual + generador sintético (:8200) |
| [CONEXION_ESP32.md](CONEXION_ESP32.md) | Protocolo (intacto), alta de nodos nuevos |
| [EJECUCION.md](EJECUCION.md) | Cómo levantar todo, orden, fallos, verificación |
| [DEPENDENCIAS.md](DEPENDENCIAS.md) | Paquetes Python, servicios Docker, CDN |
| [CHANGELOG.md](CHANGELOG.md) | Todos los cambios de la ampliación vs el PoC |

Referencias previas que siguen vigentes: [`../DESPLIEGUE.md`](../DESPLIEGUE.md)
(nube Oracle) y [`../capa2-red/MQTT_SPEC.md`](../capa2-red/MQTT_SPEC.md)
(contrato MQTT del ESP32).

"""
risk.py — Motor de NIVEL DE RIESGO por nodo (condiciones de cría de Aedes aegypti).

Combina los datos de sensores con la actividad reciente de alertas en un score
0–100 y un nivel: bajo 🟢 | medio 🟡 | alto 🟠 | critico 🔴.

Factores ponderados (pesos y umbrales configurables en system_config key 'risk'):

  temp       Temperatura del agua/aire. Óptimo de reproducción 25–30 °C
             (función trapezoidal: 1.0 dentro del óptimo, decae lineal a 0
             hacia los extremos del rango [15,40]).
  turbidez   Agua estancada turbia = criadero. turb_v se mapea lineal entre
             turb_v_baja (factor 0) y turb_v_alta (factor 1).
  humedad    % HR óptimo 60–80 (mismo esquema trapezoidal). El ESP32 real NO
             tiene este sensor: si falta, su peso se REDISTRIBUYE entre los
             factores presentes (no penaliza tener menos sensores).
  ph         Riesgo alto cuando el agua es viable para larvas (6.5–8.5).
  nivel_agua Más agua acumulada = más criadero (satura en nivel_agua_max cm).
  actividad  Nº de alertas confirmadas del nodo en la ventana reciente
             (excluye falsa-alarma/descartada), satura en actividad_max.

Uso puro (testeable sin BD):
    score, level, detalle = compute(sensores, actividad_n, cfg)

Uso integrado:
    evaluate_node(node_id, sensores=None)  -> evalúa un nodo contra la BD
    refresh_all()                          -> recalcula y persiste todos los nodos
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

# Defaults idénticos a la semilla del migrador (por si system_config no responde).
DEFAULT_CONFIG = {
    "pesos": {"temp": 0.30, "turbidez": 0.25, "humedad": 0.20,
              "ph": 0.05, "nivel_agua": 0.05, "actividad": 0.25},
    "umbrales_nivel": {"medio": 25, "alto": 50, "critico": 75},
    "temp_optima": [25, 30],
    "temp_rango": [15, 40],
    "humedad_optima": [60, 80],
    "humedad_rango": [30, 100],
    "turb_v_baja": 0.5,
    "turb_v_alta": 2.0,
    "turb_invertido": False,
    "ph_optimo": [6.5, 8.5],
    "ph_margen": 2.0,
    "nivel_agua_max": 10.0,
    "actividad_ventana_h": 72,
    "actividad_max": 10,
}

LEVELS = ("bajo", "medio", "alto", "critico")


# ───────────────────────────── factores puros ────────────────────────────────
def _trapezoide(v: float, optimo: list, rango: list) -> float:
    """1.0 dentro de [optimo], decae lineal a 0 hacia los bordes de [rango]."""
    lo, hi = float(rango[0]), float(rango[1])
    olo, ohi = float(optimo[0]), float(optimo[1])
    if v <= lo or v >= hi:
        return 0.0
    if olo <= v <= ohi:
        return 1.0
    if v < olo:
        return (v - lo) / (olo - lo) if olo > lo else 1.0
    return (hi - v) / (hi - ohi) if hi > ohi else 1.0


def factor_temp(temp_c, cfg) -> float | None:
    if temp_c is None or temp_c <= -100:      # DS18B20 sin sonda reporta -127
        return None
    return _trapezoide(float(temp_c), cfg["temp_optima"], cfg["temp_rango"])


def factor_turbidez(turb_v, cfg) -> float | None:
    if turb_v is None:
        return None
    v = float(turb_v)
    lo, hi = float(cfg["turb_v_baja"]), float(cfg["turb_v_alta"])
    if cfg.get("turb_invertido"):
        v = lo + hi - v                       # sensores que dan MENOS V = más turbio
    if v <= lo:
        return 0.0
    if v >= hi:
        return 1.0
    return (v - lo) / (hi - lo)


def factor_humedad(humedad, cfg) -> float | None:
    if humedad is None:
        return None
    return _trapezoide(float(humedad), cfg["humedad_optima"], cfg["humedad_rango"])


def factor_ph(ph, cfg) -> float | None:
    if ph is None:
        return None
    v = float(ph)
    olo, ohi = cfg["ph_optimo"]
    margen = float(cfg.get("ph_margen", 2.0))
    if olo <= v <= ohi:
        return 1.0
    dist = (olo - v) if v < olo else (v - ohi)
    return max(0.0, 1.0 - dist / margen)


def factor_nivel_agua(nivel, cfg) -> float | None:
    if nivel is None:
        return None
    mx = float(cfg.get("nivel_agua_max", 10.0)) or 10.0
    return max(0.0, min(1.0, float(nivel) / mx))


def factor_actividad(n_alertas, cfg) -> float | None:
    if n_alertas is None:
        return None
    mx = float(cfg.get("actividad_max", 10)) or 10.0
    return max(0.0, min(1.0, float(n_alertas) / mx))


def nivel_de(score: float, cfg: dict) -> str:
    u = cfg.get("umbrales_nivel", DEFAULT_CONFIG["umbrales_nivel"])
    if score >= float(u.get("critico", 75)):
        return "critico"
    if score >= float(u.get("alto", 50)):
        return "alto"
    if score >= float(u.get("medio", 25)):
        return "medio"
    return "bajo"


def compute(sensores: dict, actividad_n: int | None,
            cfg: dict | None = None) -> tuple[float, str, dict]:
    """Núcleo puro del motor. `sensores` = última lectura ({temp_c, turb_v,
    humedad, ph, nivel_agua}); `actividad_n` = nº de alertas recientes visibles.
    Devuelve (score 0-100, nivel, detalle por factor para depurar/tooltip).

    Los pesos de factores AUSENTES (sensor no instalado / sin datos) se
    redistribuyen entre los presentes — clave para que el ESP32 real (solo
    temp+turbidez) compita en igualdad con nodos más equipados."""
    cfg = {**DEFAULT_CONFIG, **(cfg or {})}
    pesos = {**DEFAULT_CONFIG["pesos"], **cfg.get("pesos", {})}
    s = sensores or {}

    factores = {
        "temp": factor_temp(s.get("temp_c"), cfg),
        "turbidez": factor_turbidez(s.get("turb_v"), cfg),
        "humedad": factor_humedad(s.get("humedad"), cfg),
        "ph": factor_ph(s.get("ph"), cfg),
        "nivel_agua": factor_nivel_agua(s.get("nivel_agua"), cfg),
        "actividad": factor_actividad(actividad_n, cfg),
    }

    presentes = {k: f for k, f in factores.items() if f is not None}
    peso_total = sum(pesos.get(k, 0) for k in presentes)
    if not presentes or peso_total <= 0:
        return 0.0, "bajo", {"factores": factores, "score": 0.0, "nota": "sin datos"}

    score = 100.0 * sum(pesos.get(k, 0) * f for k, f in presentes.items()) / peso_total
    score = round(min(100.0, max(0.0, score)), 1)
    level = nivel_de(score, cfg)

    detalle = {
        "score": score,
        "nivel": level,
        "factores": {k: (round(f, 3) if f is not None else None)
                     for k, f in factores.items()},
        "pesos_efectivos": {k: round(pesos.get(k, 0) / peso_total, 3)
                            for k in presentes},
        "ausentes": [k for k, f in factores.items() if f is None],
    }
    return score, level, detalle


# ───────────────────────── integración con la BD ─────────────────────────────
def load_config() -> dict:
    """Config de system_config key 'risk'; DEFAULT_CONFIG si no hay BD."""
    try:
        from database import get_pool
        with get_pool().connection() as conn:
            r = conn.execute(
                "SELECT value FROM system_config WHERE key='risk'").fetchone()
        if r and r["value"]:
            v = r["value"]
            return {**DEFAULT_CONFIG, **(v if isinstance(v, dict) else json.loads(v))}
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)


def _actividad(conn, node_id: str, ventana_h: float) -> int:
    """Alertas del nodo en la ventana, excluyendo falsas/descartadas."""
    ms = int(ventana_h * 3600 * 1000)
    ahora_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    r = conn.execute(
        """SELECT COUNT(*) c FROM alerts
           WHERE node_id=%s AND ts >= %s
             AND status NOT IN ('falsa-alarma', 'descartada')""",
        (node_id, ahora_ms - ms),
    ).fetchone()
    return r["c"]


def _ultima_lectura(conn, node_id: str) -> dict:
    r = conn.execute(
        """SELECT temp_c, turb_v, humedad, ph, nivel_agua
           FROM sensor_readings WHERE node_id=%s
           ORDER BY ts DESC, id DESC LIMIT 1""",
        (node_id,),
    ).fetchone()
    return dict(r) if r else {}


def evaluate_node(node_id: str, sensores: dict | None = None,
                  cfg: dict | None = None) -> tuple[float, str, dict]:
    """Evalúa un nodo contra la BD: última lectura (o la que le pases) +
    actividad reciente. Devuelve (score, nivel, detalle)."""
    from database import get_pool
    cfg = cfg or load_config()
    with get_pool().connection() as conn:
        lectura = {k: v for k, v in (sensores or {}).items() if v is not None}
        if not lectura:
            lectura = _ultima_lectura(conn, node_id)
        n = _actividad(conn, node_id, float(cfg["actividad_ventana_h"]))
    return compute(lectura, n, cfg)


def refresh_all() -> int:
    """Recalcula y PERSISTE nodes.risk_level/risk_score de todos los nodos.
    Lo llama el job periódico de serve.py. Devuelve nº de nodos actualizados."""
    from database import get_pool
    cfg = load_config()
    with get_pool().connection() as conn:
        nodes = conn.execute("SELECT node_id FROM nodes").fetchall()
        n = 0
        for row in nodes:
            nid = row["node_id"]
            lectura = _ultima_lectura(conn, nid)
            act = _actividad(conn, nid, float(cfg["actividad_ventana_h"]))
            score, level, _ = compute(lectura, act, cfg)
            conn.execute(
                "UPDATE nodes SET risk_score=%s, risk_level=%s WHERE node_id=%s",
                (score, level, nid),
            )
            n += 1
    return n


# ─────────────────────────────── smoke test ──────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("ESP32 real, condiciones ideales",
         {"temp_c": 27.5, "turb_v": 2.2}, 5),
        ("ESP32 real, agua clara y frío",
         {"temp_c": 16.0, "turb_v": 0.3}, 0),
        ("Nodo completo, todo crítico",
         {"temp_c": 28, "turb_v": 2.5, "humedad": 70, "ph": 7.2, "nivel_agua": 9}, 10),
        ("Sonda de temperatura desconectada (-127)",
         {"temp_c": -127.0, "turb_v": 1.2}, 2),
        ("Sin sensores, sin actividad", {}, 0),
    ]
    for nombre, sensores, act in tests:
        score, level, det = compute(sensores, act, None)
        print(f"{nombre}:\n  score={score} nivel={level} "
              f"ausentes={det.get('ausentes')}\n  factores={det.get('factores')}")

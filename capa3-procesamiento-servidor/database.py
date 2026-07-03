"""
database.py — Conexión única a PostgreSQL para todo el sistema (capas 3 y 4).

Un solo ConnectionPool (psycopg 3) compartido por el gateway, el dashboard y el
monitor. psycopg_pool es thread-safe: los hilos del gateway (jpegseq, MQTT) y los
del monitor (ingest, heartbeat, indexer) toman y devuelven conexiones con
`with pool.connection():` sin pisarse.

Config por .env de la raíz (PG_HOST/PG_PORT/PG_USER/PG_PASS/PG_DB). Este módulo
carga el .env por sí mismo (parser mínimo, igual que config.py) para no depender
de qué `config` esté en sys.path — el monitor tiene su propio config.py y ambos
importan este módulo.

Uso:
    from database import get_pool, healthy
    with get_pool().connection() as conn:
        rows = conn.execute("SELECT ...", (args,)).fetchall()

Las filas salen como dict (row_factory=dict_row).
"""

from __future__ import annotations

import atexit
import os
import threading
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_HERE = Path(__file__).resolve().parent          # capa3-procesamiento-servidor/
_ROOT = _HERE.parent                             # raíz del proyecto


def _load_env(p: Path) -> None:
    """Parser mínimo KEY=VALUE (mismo criterio que config.py: setdefault)."""
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env(_ROOT / ".env")

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5433"))
PG_USER = os.getenv("PG_USER", "iot")
PG_PASS = os.getenv("PG_PASS", "iotmosquito2026")
PG_DB   = os.getenv("PG_DB", "iot_mosquito")

CONNINFO = f"host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASS} dbname={PG_DB}"

SCHEMA_SQL = _HERE / "database" / "schema.sql"

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def get_pool(timeout: float = 10.0) -> ConnectionPool:
    """Pool global, creado perezosamente. Lanza si Postgres no responde en
    `timeout` s — el caller decide si degradarse (serve) o reintentar (gateway)."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            pool = ConnectionPool(
                conninfo=CONNINFO,
                min_size=1,
                max_size=8,
                open=False,
                kwargs={"row_factory": dict_row},
                name="iot-pg",
            )
            pool.open(wait=True, timeout=timeout)   # falla rápido si PG está caído
            _pool = pool
    return _pool


def healthy() -> bool:
    """True si Postgres responde (SELECT 1). Nunca lanza."""
    try:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def apply_schema() -> None:
    """Re-aplica schema.sql (idempotente: CREATE IF NOT EXISTS)."""
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    with get_pool().connection() as conn:
        conn.execute(sql)


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


atexit.register(close_pool)   # cierre limpio del pool al terminar el proceso


if __name__ == "__main__":
    print(f"PostgreSQL {PG_HOST}:{PG_PORT}/{PG_DB} ->", "OK" if healthy() else "SIN CONEXION")

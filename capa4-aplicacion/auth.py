"""
auth.py — Autenticación del dashboard (Capa 4): sesiones con cookie firmada.

Diseño (decisiones acordadas):
  * Login clásico usuario/contraseña; hash bcrypt en la tabla users.
  * Sesión persistida en la tabla sessions (revocable con logout real);
    en la cookie viaja SOLO el id de sesión FIRMADO (itsdangerous + SESSION_SECRET
    del .env) — HttpOnly y SameSite=Lax.
  * Roles: 'admin' (todo) y 'operador' (responder alertas, comandos a nodos).
  * El ESP32 NO se autentica aquí: /upload y MQTT quedan fuera del login
    (el broker ya exige su propia clave). Retrocompatibilidad total.

Dependencias FastAPI:
    user = Depends(current_user)     -> 401 si no hay sesión válida
    user = Depends(require_admin)    -> 403 si el rol no es admin
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, TimestampSigner

# database.py vive en capa3/ — mismo truco de path que monitor/db.py.
_CAPA3 = str(Path(__file__).resolve().parents[1] / "capa3-procesamiento-servidor")
if _CAPA3 not in sys.path:
    sys.path.insert(0, _CAPA3)
from database import get_pool                                   # noqa: E402

COOKIE_NAME = "iot_session"
SESSION_DAYS = 7
_SECRET = os.getenv("SESSION_SECRET", "dev-secret-cambiar-en-produccion")
_signer = TimestampSigner(_SECRET)

ROLES = ("admin", "operador")


# ─────────────────────────────── contraseñas ─────────────────────────────────
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def check_password(plain: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), pw_hash.encode())
    except ValueError:
        return False


# ─────────────────────────────── sesiones ────────────────────────────────────
def verify_login(username: str, password: str) -> dict | None:
    """Valida credenciales. Devuelve el user (dict) o None."""
    with get_pool().connection() as conn:
        u = conn.execute(
            """SELECT id, username, password_hash, role, full_name, active
               FROM users WHERE username=%s""",
            (username,),
        ).fetchone()
    if not u or not u["active"] or not check_password(password, u["password_hash"]):
        return None
    u.pop("password_hash")
    return u


def create_session(user_id: int, ip: str | None, user_agent: str | None) -> str:
    """Crea la sesión en BD y devuelve el valor FIRMADO para la cookie."""
    sid = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with get_pool().connection() as conn:
        conn.execute(
            """INSERT INTO sessions (id, user_id, expires_at, ip, user_agent)
               VALUES (%s,%s,%s,%s,%s)""",
            (sid, user_id, expires, ip, (user_agent or "")[:300]),
        )
        conn.execute("UPDATE users SET last_login=now() WHERE id=%s", (user_id,))
        # higiene: limpiar sesiones vencidas de vez en cuando (barato aquí)
        conn.execute("DELETE FROM sessions WHERE expires_at < now()")
    return _signer.sign(sid.encode()).decode()


def destroy_session(cookie_value: str | None) -> None:
    sid = _unsign(cookie_value)
    if sid:
        with get_pool().connection() as conn:
            conn.execute("DELETE FROM sessions WHERE id=%s", (sid,))


def _unsign(cookie_value: str | None) -> str | None:
    if not cookie_value:
        return None
    try:
        return _signer.unsign(cookie_value, max_age=SESSION_DAYS * 86400).decode()
    except BadSignature:
        return None


def user_from_cookie(cookie_value: str | None) -> dict | None:
    sid = _unsign(cookie_value)
    if not sid:
        return None
    try:
        with get_pool().connection() as conn:
            row = conn.execute(
                """SELECT u.id, u.username, u.role, u.full_name
                   FROM sessions s JOIN users u ON u.id = s.user_id
                   WHERE s.id=%s AND s.expires_at > now() AND u.active""",
                (sid,),
            ).fetchone()
        return row
    except Exception:
        return None          # BD caída => tratar como no autenticado (503 lo dan las APIs)


def set_session_cookie(response: Response, cookie_value: str) -> None:
    response.set_cookie(
        COOKIE_NAME, cookie_value,
        max_age=SESSION_DAYS * 86400,
        httponly=True, samesite="lax",
        # secure=True cuando el dashboard esté detrás de TLS (producción)
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


# ─────────────────────── dependencias para FastAPI ───────────────────────────
def current_user(request: Request) -> dict:
    user = user_from_cookie(request.cookies.get(COOKIE_NAME))
    if not user:
        raise HTTPException(401, "no autenticado")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "requiere rol admin")
    return user


# ─────────────────────────── auditoría (events) ──────────────────────────────
def log_event(action: str, user: dict | None = None, entity: str | None = None,
              entity_id=None, detail: dict | None = None, ip: str | None = None):
    """Registra un evento en la tabla events. Nunca lanza (best-effort)."""
    try:
        with get_pool().connection() as conn:
            conn.execute(
                """INSERT INTO events (user_id, username, action, entity, entity_id, detail, ip)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                ((user or {}).get("id"), (user or {}).get("username"), action,
                 entity, str(entity_id) if entity_id is not None else None,
                 json.dumps(detail) if detail else None, ip),
            )
    except Exception as e:
        print(f"[AUTH] no se pudo registrar evento '{action}': {e}")

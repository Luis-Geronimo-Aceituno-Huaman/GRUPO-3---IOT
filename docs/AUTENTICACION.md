# Autenticación y roles

`capa4-aplicacion/auth.py` + tablas `users`/`sessions`/`events`.

## Diseño

- **Login clásico** usuario/contraseña. Hash **bcrypt** (nunca se guarda la clave).
- **Sesión en BD** (tabla `sessions`, 7 días): revocable con logout real.
  En la cookie viaja solo el id de sesión **firmado** (itsdangerous +
  `SESSION_SECRET` del `.env`), `HttpOnly` + `SameSite=Lax`.
- **Roles**: `admin` (todo) y `operador` (ver + responder alertas + comandos a
  nodos). Los controles de admin se ocultan en la UI y se validan en el backend
  (`Depends(require_admin)` → 403).
- **Usuarios**: soft-delete (`active=false`) para no romper la auditoría; alta,
  cambio de rol y reseteo de clave desde la pestaña Admin.
- **Auditoría**: login/logout/fallos, cambios de estado de alertas, cambios de
  config y de usuarios quedan en la tabla `events`.

## Qué está protegido y qué no

| Recurso | Acceso |
|---|---|
| `POST /api/auth/login` | público |
| SPA estática (`/`, `login.html`, js/css) | pública (la SPA redirige a login sin sesión) |
| **`POST /upload`** (ráfagas del ESP32) | **público a propósito** — el nodo no maneja cookies; el broker MQTT ya exige su propia clave |
| Todas las demás `/api/*` y `/clips/*` | sesión requerida (401 sin cookie) |
| `/api/users`, `/api/config/*`, `/api/alerts/synthetic` | solo `admin` (403 para operador) |
| `/api/node/{id}/cmd`, `PATCH /api/alerts/{id}/status`, `DELETE /api/video/{id}` | operador o admin |

## Usuario inicial

Lo crea el migrador: `admin` con la clave de `ADMIN_INIT_PASS` (`.env`).
**Cambiala en producción** y creá operadores individuales desde la pestaña Admin.

## Endpoints

```
POST   /api/auth/login     {username, password}  → set-cookie
POST   /api/auth/logout                          → borra sesión + cookie
GET    /api/auth/me                              → {id, username, role, full_name}
GET    /api/users                       (admin)
POST   /api/users          {username, password, role, full_name?}   (admin)
PATCH  /api/users/{id}     {role?|active?|password?|full_name?}      (admin)
DELETE /api/users/{id}     — desactiva (soft-delete)                 (admin)
```

## Producción (recomendaciones)

- `SESSION_SECRET` largo y aleatorio, distinto del de desarrollo.
- Al poner TLS delante (nginx/caddy), activar `secure=True` en la cookie
  (`auth.set_session_cookie`).
- El puerto de PostgreSQL nunca se abre a internet (ya viene así en el compose).

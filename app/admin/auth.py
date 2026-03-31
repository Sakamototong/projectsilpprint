"""Admin authentication helpers for /admin/* routes."""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

SECRET_KEY = os.getenv("SECRET_KEY", "silpprint-dev-secret-do-not-use-in-prod")
ALGORITHM = "HS256"
ADMIN_TOKEN_EXPIRE_HOURS = 8
ADMIN_COOKIE = "admin_token"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_admin_token(admin_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ADMIN_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": "admin", "admin_id": admin_id, "username": username, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_admin_token(token: str) -> dict:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("sub") != "admin":
        raise JWTError("not an admin token")
    return payload


def get_admin_ctx(request: Request) -> dict | None:
    """Return admin context dict or None if not authenticated."""
    token = request.cookies.get(ADMIN_COOKIE)
    if not token:
        return None
    try:
        payload = decode_admin_token(token)
        return {"admin_id": payload["admin_id"], "username": payload["username"]}
    except JWTError:
        return None


def require_admin(request: Request):
    """Return admin ctx dict, or return RedirectResponse to /admin/login."""
    ctx = get_admin_ctx(request)
    if ctx is None:
        return RedirectResponse("/admin/login", status_code=302)
    return ctx

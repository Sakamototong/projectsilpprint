import os
import logging
import secrets
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "silpprint-dev-secret-do-not-use-in-prod"
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = _DEFAULT_SECRET
    logger.warning(
        "SECRET_KEY is not set! Using insecure default. "
        "Set SECRET_KEY environment variable for production."
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Raise JWTError if invalid or expired."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def validate_password(password: str) -> str | None:
    """Return error message if password is weak, None if OK."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"รหัสผ่านต้องมีอย่างน้อย {MIN_PASSWORD_LENGTH} ตัวอักษร"
    if password.isdigit():
        return "รหัสผ่านต้องไม่เป็นตัวเลขล้วน"
    if password.isalpha():
        return "รหัสผ่านต้องมีตัวเลขอย่างน้อย 1 ตัว"
    return None

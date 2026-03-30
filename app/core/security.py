import os
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import JWTError, jwt

SECRET_KEY = os.getenv("SECRET_KEY", "silpprint-dev-secret-do-not-use-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8


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

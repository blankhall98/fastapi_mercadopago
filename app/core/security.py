from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.core.config import settings
import hashlib

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _bcrypt_input(password: str) -> str:
    """
    Bcrypt has a 72-byte input limit.
    We pre-hash with SHA-256 to make the input fixed-length and safe,
    then bcrypt the hex digest (64 chars ASCII).
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def hash_password(password: str) -> str:
    pre = _bcrypt_input(password)
    print("DEBUG security.py prehash length:", len(pre), "value starts:", pre[:8])
    return pwd_context.hash(pre)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(_bcrypt_input(password), password_hash)

def create_access_token(subject: str) -> str:
    # subject = a string that identifies the user (e.g., user ID or email)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_access_ttl_min)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()), # issued at
        "exp": int(exp.timestamp()), # expiration time
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)

def decode_token(token: str) -> dict:
    # Returns the token payload if valid, raises JWTError if invalid
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request

from .config import settings

# ---------- passwords (stdlib scrypt, no extra dependency) ----------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


DUMMY_HASH = hash_password("dummy-password-for-timing")

# ---------- tokens ----------

def create_token(user_id: int, kind: str, version: int) -> str:
    minutes = settings.access_minutes if kind == "access" else settings.refresh_days * 24 * 60
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": kind, "ver": version,
               "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str, kind: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise ValueError(str(e))
    if payload.get("type") != kind:
        raise ValueError("wrong token type")
    return payload


def hash_otp(target: str, code: str) -> str:
    return hmac.new(settings.secret_key.encode(), f"{target}:{code}".encode(), hashlib.sha256).hexdigest()

# ---------- tiny in-memory rate limiter (per process) ----------

class RateLimiter:
    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int):
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")
        q.append(now)


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    if settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

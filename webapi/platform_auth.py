"""JWT 签发与校验。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from utils.config import auth_config
from webapi.platform_roles import ROLE_WATCHER

_DURATION_RE = re.compile(r"^(\d+)([smhd])$", re.I)


def _parse_expiry(raw: str) -> timedelta:
    text = str(raw or "24h").strip().lower()
    match = _DURATION_RE.match(text)
    if not match:
        return timedelta(hours=24)
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "d":
        return timedelta(days=amount)
    return timedelta(hours=amount)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def issue_token(user: dict[str, Any]) -> str:
    cfg = auth_config()
    expiry = _parse_expiry(cfg["token_expiry"])
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": int(user["id"]),
        "username": str(user["name"]),
        "role": str(user["role"]),
        "iat": now,
        "exp": now + expiry,
    }
    return jwt.encode(payload, cfg["jwt_secret"], algorithm="HS256")


def parse_token(token: str) -> dict[str, Any]:
    cfg = auth_config()
    try:
        payload = jwt.decode(token, cfg["jwt_secret"], algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ValueError("登录已失效，请重新登录") from exc
    return {
        "user_id": int(payload["user_id"]),
        "username": str(payload.get("username") or ""),
        "role": str(payload.get("role") or ROLE_WATCHER),
    }


def token_max_age_seconds() -> int:
    return int(_parse_expiry(auth_config()["token_expiry"]).total_seconds()) or 86400

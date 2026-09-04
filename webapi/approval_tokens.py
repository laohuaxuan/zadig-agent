"""审批动作 JWT（飞书卡片按钮 / URL 链接）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from utils.config import auth_config

_APPROVAL_TOKEN_TTL = timedelta(days=7)


def generate_approval_token(instance_id: int, task_id: int, user_id: int, action: str) -> str:
    action = str(action or "").strip()
    if instance_id <= 0 or task_id <= 0 or user_id <= 0:
        raise ValueError("invalid approval action token payload")
    if action not in {"approve", "reject"}:
        raise ValueError(f"invalid approval action: {action}")
    now = datetime.now(timezone.utc)
    payload = {
        "instance_id": int(instance_id),
        "task_id": int(task_id),
        "user_id": int(user_id),
        "action": action,
        "iat": now,
        "exp": now + _APPROVAL_TOKEN_TTL,
    }
    return jwt.encode(payload, auth_config()["jwt_secret"], algorithm="HS256")


def parse_approval_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, auth_config()["jwt_secret"], algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ValueError("链接已失效，请登录平台处理") from exc
    action = str(payload.get("action") or "").strip()
    if action not in {"approve", "reject"}:
        raise ValueError("无效审批操作")
    return {
        "instance_id": int(payload["instance_id"]),
        "task_id": int(payload["task_id"]),
        "user_id": int(payload["user_id"]),
        "action": action,
    }

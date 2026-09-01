"""Zadig OpenAPI 请求与结果序列化。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from utils.config import zadig_config


def dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def error(message: str) -> str:
    return dump({"ok": False, "error": message})


def zadig_request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_data: Any = None,
    timeout: float = 60.0,
) -> Any:
    cfg = zadig_config()
    url = f"{cfg['base_url']}{path}"
    headers = {
        "Authorization": f"Bearer {cfg['api_token']}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_data,
        )
    if resp.status_code >= 400:
        detail = resp.text[:800]
        try:
            body = resp.json()
            if isinstance(body, dict):
                detail = str(body.get("description") or body.get("message") or detail)
        except Exception:
            pass
        raise RuntimeError(f"Zadig API 错误 {resp.status_code}: {detail}")
    if resp.status_code == 204 or not resp.text:
        return {}
    try:
        return resp.json()
    except Exception:
        return resp.text

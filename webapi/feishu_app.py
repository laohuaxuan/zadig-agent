"""飞书多产品共用 App 时的应用标识与回调路由。"""

from __future__ import annotations

from typing import Any

DEFAULT_APP_NAMESPACE = "zadig-agent"


def feishu_app_namespace(cfg: dict[str, Any]) -> str:
    ns = str(cfg.get("app_namespace") or "").strip()
    return ns or DEFAULT_APP_NAMESPACE


def feishu_peer_base_url(cfg: dict[str, Any], app: str) -> str:
    peers = cfg.get("peer_app_base_urls")
    if not isinstance(peers, dict):
        return ""
    return str(peers.get(app) or "").strip().rstrip("/")

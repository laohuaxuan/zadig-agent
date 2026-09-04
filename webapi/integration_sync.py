"""系统集成资源：从 Zadig 定期拉取并缓存。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from utils.db import execute, query_one
from utils.zadig import zadig_request
from webapi.zadig_meta import list_all_users, list_chart_templates, list_codehosts

logger = logging.getLogger(__name__)

_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "application_id",
    "client_secret",
    "password",
    "secret_key",
    "access_key",
}

INTEGRATION_RESOURCE_TYPES = (
    "code_sources",
    "clusters",
    "registries",
    "service_templates",
    "users",
)

_sync_lock = asyncio.Lock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {
            key: "********" if key in _SECRET_KEYS and item else _sanitize(item)
            for key, item in value.items()
        }
    return value


def _as_list(data: Any) -> list[Any]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "clusters", "registries", "users", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("Zadig 返回格式无法解析为列表")


def _fetch_code_sources() -> list[dict[str, Any]]:
    return _sanitize(_as_list(list_codehosts()))


def _fetch_clusters() -> list[dict[str, Any]]:
    return _sanitize(_as_list(zadig_request("GET", "/openapi/system/cluster")))


def _fetch_registries() -> list[dict[str, Any]]:
    return _sanitize(_as_list(zadig_request("GET", "/openapi/system/registry")))


def _fetch_service_templates() -> list[dict[str, Any]]:
    return _sanitize(list_chart_templates())


def _fetch_users() -> list[dict[str, Any]]:
    return _sanitize(list_all_users())


_FETCHERS = {
    "code_sources": _fetch_code_sources,
    "clusters": _fetch_clusters,
    "registries": _fetch_registries,
    "service_templates": _fetch_service_templates,
    "users": _fetch_users,
}


def normalize_integration_resource_type(resource_type: str) -> str:
    text = str(resource_type or "").strip()
    aliases = {
        "code-sources": "code_sources",
        "code_source": "code_sources",
        "service-templates": "service_templates",
        "service_template": "service_templates",
    }
    return aliases.get(text, text)


def _load_cache_row(resource_type: str) -> dict[str, Any] | None:
    return query_one(
        "SELECT resource_type, items_json, synced_at, sync_error FROM integration_sync_cache WHERE resource_type = %s",
        (resource_type,),
    )


def _decode_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []
    return []


def get_integration_items(resource_type: str) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """返回 (items, synced_at, sync_error)。"""
    key = normalize_integration_resource_type(resource_type)
    row = _load_cache_row(key)
    if not row:
        return [], None, None
    items = _decode_items(row.get("items_json"))
    synced_at = str(row.get("synced_at") or "").strip() or None
    sync_error = str(row.get("sync_error") or "").strip() or None
    return items, synced_at, sync_error


def sync_integration_resource(resource_type: str) -> dict[str, Any]:
    key = normalize_integration_resource_type(resource_type)
    if key not in _FETCHERS:
        raise ValueError(f"不支持的资源类型：{resource_type}")
    now = _now()
    try:
        items = _FETCHERS[key]()
        execute(
            """
            INSERT INTO integration_sync_cache (resource_type, items_json, synced_at, sync_error)
            VALUES (%s, %s, %s, NULL)
            ON DUPLICATE KEY UPDATE
                items_json = VALUES(items_json),
                synced_at = VALUES(synced_at),
                sync_error = NULL
            """,
            (key, json.dumps(items, ensure_ascii=False), now),
        )
        return {"resource_type": key, "count": len(items), "synced_at": now, "ok": True}
    except Exception as exc:
        message = str(exc)
        logger.warning("同步系统集成资源失败 %s: %s", key, message)
        existing = _load_cache_row(key)
        if existing:
            execute(
                """
                UPDATE integration_sync_cache
                SET synced_at = %s, sync_error = %s
                WHERE resource_type = %s
                """,
                (now, message, key),
            )
        else:
            execute(
                """
                INSERT INTO integration_sync_cache (resource_type, items_json, synced_at, sync_error)
                VALUES (%s, %s, %s, %s)
                """,
                (key, "[]", now, message),
            )
        return {"resource_type": key, "count": 0, "synced_at": now, "ok": False, "error": message}


def sync_integration_resources(resource_type: str | None = None) -> dict[str, Any]:
    targets = [normalize_integration_resource_type(resource_type)] if resource_type else list(INTEGRATION_RESOURCE_TYPES)
    results: list[dict[str, Any]] = []
    for key in targets:
        if key not in _FETCHERS:
            raise ValueError(f"不支持的资源类型：{resource_type}")
        results.append(sync_integration_resource(key))
    synced_at = max((item.get("synced_at") or "") for item in results) or _now()
    errors = [str(item.get("error") or "") for item in results if not item.get("ok")]
    return {
        "synced_at": synced_at,
        "results": results,
        "ok": not errors,
        "error": "; ".join(error for error in errors if error),
    }


async def integration_sync_loop() -> None:
    from utils.config import integration_config

    while True:
        interval = integration_config()["sync_interval_seconds"]
        try:
            async with _sync_lock:
                result = await asyncio.to_thread(sync_integration_resources)
            if result.get("ok"):
                logger.info("系统集成资源同步完成")
            else:
                logger.warning("系统集成资源同步部分失败：%s", result.get("error"))
        except Exception:
            logger.exception("系统集成资源同步异常")
        await asyncio.sleep(interval)


async def run_integration_sync_once() -> None:
    async with _sync_lock:
        await asyncio.to_thread(sync_integration_resources)

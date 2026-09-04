"""Agent 模板：MySQL 存储；启动时将仓库 JSON 一次性同步入库。"""

from __future__ import annotations

import json
from typing import Any

from utils.db import execute, query, query_one
from utils.template_store import list_file_templates
from webapi.catalog import validate_name

_TEMPLATE_CATEGORIES = {"workflow", "general"}


def _parse_body(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("模板内容必须是 JSON 对象")


def _template_from_row(row: dict[str, Any]) -> dict[str, Any]:
    updated = row.get("updated_at")
    if hasattr(updated, "isoformat"):
        updated = updated.isoformat(timespec="seconds")
    body_raw = row.get("body_json")
    if isinstance(body_raw, str):
        body_raw = json.loads(body_raw)
    body = body_raw if isinstance(body_raw, dict) else {}
    return {
        "name": row["name"],
        "display_name": row["display_name"],
        "description": row.get("description") or "",
        "category": row.get("category") or "workflow",
        "source": "mysql",
        "updated_at": str(updated or ""),
        "maintainer_id": int(row["maintainer_id"]) if row.get("maintainer_id") is not None else None,
        "body": body,
    }


def _db_templates() -> list[dict[str, Any]]:
    return [_template_from_row(row) for row in query("SELECT * FROM agent_templates ORDER BY name")]


def sync_file_templates_to_db() -> None:
    """将 templates/ 目录下尚未入库的模板导入 MySQL。"""
    for item in list_file_templates():
        name = item["name"]
        if query_one("SELECT name FROM agent_templates WHERE name = %s", (name,)):
            continue
        body = item.get("body") or {}
        if not isinstance(body, dict):
            continue
        execute(
            """
            INSERT INTO agent_templates
            (name, display_name, description, category, body_json, maintainer_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, NULL, NOW(), NOW())
            """,
            (
                name,
                item["display_name"],
                item.get("description") or "",
                item.get("category") or "workflow",
                json.dumps(body, ensure_ascii=False),
            ),
        )


def _name_taken(name: str) -> bool:
    return bool(query_one("SELECT name FROM agent_templates WHERE name = %s", (name,)))


def list_templates() -> list[dict[str, Any]]:
    sync_file_templates_to_db()
    return _db_templates()


def get_template(name: str) -> dict[str, Any]:
    text = str(name or "").strip()
    if not text:
        raise ValueError("模板标识不能为空")
    row = query_one("SELECT * FROM agent_templates WHERE name = %s", (text,))
    if not row:
        sync_file_templates_to_db()
        row = query_one("SELECT * FROM agent_templates WHERE name = %s", (text,))
    if not row:
        raise LookupError(f"未找到模板 {text}")
    return _template_from_row(row)


def get_template_body(name: str) -> dict[str, Any]:
    return dict(get_template(name)["body"])


def create_template(payload: dict[str, Any], *, maintainer_id: int | None = None) -> dict[str, Any]:
    name = validate_name(payload.get("name"))
    if _name_taken(name):
        raise FileExistsError(f"模板 {name} 已存在")
    display_name = str(payload.get("display_name") or name).strip() or name
    description = str(payload.get("description") or "").strip()
    category = str(payload.get("category") or "workflow").strip().lower() or "workflow"
    if category not in _TEMPLATE_CATEGORIES:
        raise ValueError("category 必须是 workflow 或 general")
    body = _parse_body(payload.get("body"))
    execute(
        """
        INSERT INTO agent_templates
        (name, display_name, description, category, body_json, maintainer_id, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
        """,
        (name, display_name, description, category, json.dumps(body, ensure_ascii=False), maintainer_id),
    )
    return get_template(name)


def import_template(payload: dict[str, Any]) -> dict[str, Any]:
    """从 JSON 导入模板；若未指定 name 则尝试从 body 推断。"""
    body = _parse_body(payload.get("body") if payload.get("body") is not None else payload)
    name = str(payload.get("name") or body.get("name") or "").strip()
    if name.startswith("{") and name.endswith("}"):
        name = ""
    if not name:
        raise ValueError("导入模板需指定标识 name")
    name = validate_name(name)
    if _name_taken(name):
        raise FileExistsError(f"模板 {name} 已存在")
    display_name = str(payload.get("display_name") or body.get("display_name") or name).strip() or name
    if display_name.startswith("{") and display_name.endswith("}"):
        display_name = name
    description = str(payload.get("description") or "").strip()
    category = str(payload.get("category") or "workflow").strip().lower() or "workflow"
    if category not in _TEMPLATE_CATEGORIES:
        raise ValueError("category 必须是 workflow 或 general")
    clean_body = dict(body)
    for key in ("name", "display_name", "description", "category"):
        clean_body.pop(key, None)
    return create_template(
        {
            "name": name,
            "display_name": display_name,
            "description": description,
            "category": category,
            "body": clean_body,
        },
        maintainer_id=payload.get("maintainer_id"),
    )


def update_template(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    text = str(name or "").strip()
    row = query_one("SELECT name FROM agent_templates WHERE name = %s", (text,))
    if not row:
        raise LookupError(f"模板 {text} 不存在或不可编辑")
    display_name = str(payload.get("display_name") or text).strip() or text
    description = str(payload.get("description") or "").strip()
    category = str(payload.get("category") or "workflow").strip().lower() or "workflow"
    if category not in _TEMPLATE_CATEGORIES:
        raise ValueError("category 必须是 workflow 或 general")
    body = _parse_body(payload.get("body"))
    execute(
        """
        UPDATE agent_templates
        SET display_name = %s, description = %s, category = %s, body_json = %s, updated_at = NOW()
        WHERE name = %s
        """,
        (display_name, description, category, json.dumps(body, ensure_ascii=False), text),
    )
    return get_template(text)


def delete_template(name: str) -> None:
    text = str(name or "").strip()
    row = query_one("SELECT name FROM agent_templates WHERE name = %s", (text,))
    if not row:
        raise LookupError(f"模板 {text} 不存在或不可删除")
    execute("DELETE FROM agent_templates WHERE name = %s", (text,))

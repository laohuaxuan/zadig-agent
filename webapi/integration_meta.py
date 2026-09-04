"""系统集成资源备注：代码源、镜像仓库、服务模板。"""

from __future__ import annotations

from typing import Any

from utils.db import execute, query

_RESOURCE_TYPES = {"code_source", "registry", "service_template"}


def _resource_key(resource_type: str, row: dict[str, Any]) -> str:
    if resource_type == "code_source":
        return str(row.get("alias") or row.get("name") or row.get("id") or "").strip()
    if resource_type == "registry":
        return str(row.get("registry_id") or row.get("id") or "").strip()
    if resource_type == "service_template":
        return str(row.get("name") or "").strip()
    return ""


def load_remarks_map(resource_type: str) -> dict[str, str]:
    text = str(resource_type or "").strip()
    if text not in _RESOURCE_TYPES:
        return {}
    rows = query(
        "SELECT resource_key, remark FROM integration_resource_remarks WHERE resource_type = %s",
        (text,),
    )
    return {str(row["resource_key"]): str(row.get("remark") or "") for row in rows}


def attach_integration_remarks(items: list[dict[str, Any]], resource_type: str) -> list[dict[str, Any]]:
    remarks = load_remarks_map(resource_type)
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        key = _resource_key(resource_type, row)
        row["resource_key"] = key
        row["remark"] = remarks.get(key, "")
        out.append(row)
    return out


def update_integration_remark(resource_type: str, resource_key: str, remark: str) -> dict[str, Any]:
    rtype = str(resource_type or "").strip()
    key = str(resource_key or "").strip()
    if rtype not in _RESOURCE_TYPES:
        raise ValueError("不支持的资源类型")
    if not key:
        raise ValueError("资源标识不能为空")
    text = str(remark or "").strip()
    if text:
        execute(
            """
            INSERT INTO integration_resource_remarks (resource_type, resource_key, remark, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE remark = VALUES(remark), updated_at = NOW()
            """,
            (rtype, key, text),
        )
    else:
        execute(
            "DELETE FROM integration_resource_remarks WHERE resource_type = %s AND resource_key = %s",
            (rtype, key),
        )
    return {"resource_type": rtype, "resource_key": key, "remark": text}

"""审批流模板配置。"""

from __future__ import annotations

import json
from typing import Any

from utils.db import _now, connection, execute, query, query_one
from webapi.platform_roles import WORKFLOW_TYPE_HELM_PROJECT
from webapi.platform_users import get_user_by_id


def _normalize_mode(mode: str) -> str:
    return "all" if str(mode or "").strip().lower() == "all" else "any"


def _load_level_users(level_id: int, table: str) -> list[dict[str, Any]]:
    rows = query(f"SELECT user_id FROM {table} WHERE level_id = %s ORDER BY id ASC", (level_id,))
    out: list[dict[str, Any]] = []
    for row in rows:
        user = get_user_by_id(int(row["user_id"]))
        if user:
            out.append(
                {
                    "user_id": user["id"],
                    "user_name": user["display_name"] or user["name"],
                    "display_name": user["display_name"],
                    "email": user.get("email") or "",
                    "auth_source": user.get("auth_source") or "local",
                }
            )
    return out


def _load_template_levels(template_id: int) -> list[dict[str, Any]]:
    levels = query(
        "SELECT * FROM approval_flow_levels WHERE template_id = %s ORDER BY level ASC",
        (template_id,),
    )
    out: list[dict[str, Any]] = []
    for lv in levels:
        out.append(
            {
                "id": int(lv["id"]),
                "level": int(lv["level"]),
                "name": lv["name"],
                "approval_mode": _normalize_mode(lv.get("approval_mode") or "any"),
                "assignees": _load_level_users(int(lv["id"]), "approval_flow_level_assignees"),
                "cc_users": _load_level_users(int(lv["id"]), "approval_flow_level_ccs"),
            }
        )
    return out


def _public_template(row: dict[str, Any], *, with_levels: bool = False) -> dict[str, Any]:
    item = {
        "id": int(row["id"]),
        "name": row["name"],
        "workflow_type": row["workflow_type"],
        "enabled": bool(row.get("enabled")),
        "is_default": bool(row.get("is_default")),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }
    if with_levels:
        item["levels"] = _load_template_levels(int(row["id"]))
    return item


def list_templates(workflow_type: str = "") -> list[dict[str, Any]]:
    if workflow_type.strip():
        rows = query(
            "SELECT * FROM approval_flow_templates WHERE workflow_type = %s ORDER BY id ASC",
            (workflow_type.strip(),),
        )
    else:
        rows = query("SELECT * FROM approval_flow_templates ORDER BY id ASC")
    return [_public_template(row) for row in rows]


def get_template(template_id: int) -> dict[str, Any]:
    row = query_one("SELECT * FROM approval_flow_templates WHERE id = %s", (template_id,))
    if not row:
        raise LookupError("审批模板不存在")
    return _public_template(row, with_levels=True)


def get_default_template(workflow_type: str = WORKFLOW_TYPE_HELM_PROJECT) -> dict[str, Any] | None:
    row = query_one(
        """
        SELECT * FROM approval_flow_templates
        WHERE workflow_type = %s AND enabled = 1 AND is_default = 1
        ORDER BY id ASC LIMIT 1
        """,
        (workflow_type,),
    )
    if not row:
        return None
    return _public_template(row, with_levels=True)


def _replace_levels(template_id: int, levels: list[dict[str, Any]]) -> None:
    old_levels = query("SELECT id FROM approval_flow_levels WHERE template_id = %s", (template_id,))
    for lv in old_levels:
        lid = int(lv["id"])
        execute("DELETE FROM approval_flow_level_assignees WHERE level_id = %s", (lid,))
        execute("DELETE FROM approval_flow_level_ccs WHERE level_id = %s", (lid,))
    execute("DELETE FROM approval_flow_levels WHERE template_id = %s", (template_id,))
    for index, lv in enumerate(levels, start=1):
        execute(
            """
            INSERT INTO approval_flow_levels (template_id, level, name, approval_mode)
            VALUES (%s, %s, %s, %s)
            """,
            (template_id, index, str(lv.get("name") or f"{index}级审批"), _normalize_mode(lv.get("approval_mode") or "any")),
        )
        level_row = query_one(
            "SELECT id FROM approval_flow_levels WHERE template_id = %s AND level = %s",
            (template_id, index),
        )
        if not level_row:
            continue
        level_id = int(level_row["id"])
        for uid in lv.get("assignee_ids") or []:
            execute(
                "INSERT INTO approval_flow_level_assignees (level_id, user_id) VALUES (%s, %s)",
                (level_id, int(uid)),
            )
        for uid in lv.get("cc_user_ids") or []:
            execute(
                "INSERT INTO approval_flow_level_ccs (level_id, user_id) VALUES (%s, %s)",
                (level_id, int(uid)),
            )


def create_template(payload: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    workflow_type = str(payload.get("workflow_type") or WORKFLOW_TYPE_HELM_PROJECT).strip()
    with connection() as conn:
        with conn.cursor() as cur:
            if payload.get("is_default"):
                cur.execute(
                    "UPDATE approval_flow_templates SET is_default = 0 WHERE workflow_type = %s",
                    (workflow_type,),
                )
            cur.execute(
                """
                INSERT INTO approval_flow_templates
                (name, workflow_type, enabled, is_default, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    str(payload.get("name") or "默认审批").strip(),
                    workflow_type,
                    1 if payload.get("enabled", True) else 0,
                    1 if payload.get("is_default") else 0,
                    now,
                    now,
                ),
            )
            template_id = int(cur.lastrowid)
        conn.commit()
    _replace_levels(template_id, payload.get("levels") or [])
    return get_template(template_id)


def update_template(template_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = query_one("SELECT * FROM approval_flow_templates WHERE id = %s", (template_id,))
    if not row:
        raise LookupError("审批模板不存在")
    now = _now()
    workflow_type = str(payload.get("workflow_type") or row["workflow_type"]).strip()
    with connection() as conn:
        with conn.cursor() as cur:
            if payload.get("is_default"):
                cur.execute(
                    "UPDATE approval_flow_templates SET is_default = 0 WHERE workflow_type = %s AND id <> %s",
                    (workflow_type, template_id),
                )
            cur.execute(
                """
                UPDATE approval_flow_templates
                SET name = %s, workflow_type = %s, enabled = %s, is_default = %s, updated_at = %s
                WHERE id = %s
                """,
                (
                    str(payload.get("name") or row["name"]).strip(),
                    workflow_type,
                    1 if payload.get("enabled", True) else 0,
                    1 if payload.get("is_default") else 0,
                    now,
                    template_id,
                ),
            )
        conn.commit()
    _replace_levels(template_id, payload.get("levels") or [])
    return get_template(template_id)


def delete_template(template_id: int) -> None:
    levels = query("SELECT id FROM approval_flow_levels WHERE template_id = %s", (template_id,))
    for lv in levels:
        lid = int(lv["id"])
        execute("DELETE FROM approval_flow_level_assignees WHERE level_id = %s", (lid,))
        execute("DELETE FROM approval_flow_level_ccs WHERE level_id = %s", (lid,))
    execute("DELETE FROM approval_flow_levels WHERE template_id = %s", (template_id,))
    execute("DELETE FROM approval_flow_templates WHERE id = %s", (template_id,))


def levels_snapshot(levels: list[dict[str, Any]]) -> str:
    return json.dumps(levels, ensure_ascii=False)

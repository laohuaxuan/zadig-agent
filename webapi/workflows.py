"""审批流引擎。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from utils.db import _now, connection, execute, query, query_one
from webapi.approval_templates import get_default_template, levels_snapshot
from webapi.platform_roles import WORKFLOW_TYPE_ADD_SERVICE, WORKFLOW_TYPE_HELM_PROJECT
from webapi.platform_users import get_user_by_id, list_approver_users

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_REVOKED = "revoked"
STATUS_COMPLETED = "completed"

TASK_PENDING = "pending"
TASK_APPROVED = "approved"
TASK_REJECTED = "rejected"
TASK_CANCELLED = "cancelled"

_EXECUTABLE_APP_STATUSES = ("待执行", "已通过", "执行中")
_LIST_SELECT = """
    t.id AS task_id, i.id AS instance_id, i.serial_no, i.title, i.workflow_type,
    i.status, i.summary, i.initiator_name, t.assignee_name, t.processed_at,
    i.created_at, i.updated_at
"""
_INITIATOR_SELECT = """
    0 AS task_id, i.id AS instance_id, i.serial_no, i.title, i.workflow_type,
    i.status, i.summary, i.initiator_name, '' AS assignee_name, NULL AS processed_at,
    i.created_at, i.updated_at
"""


def _initiator_execution_clause(instance_alias: str = "i") -> str:
    return f"""
    {instance_alias}.initiator_id = %s
    AND {instance_alias}.status = %s
    AND {instance_alias}.ref_record_id <> ''
    AND EXISTS (
        SELECT 1 FROM project_applications pa
        WHERE pa.record_id = {instance_alias}.ref_record_id
          AND pa.approval_status IN (%s, %s, %s)
    )
    """


def _exclude_initiator_execution_clause(instance_alias: str = "i") -> str:
    return f"NOT ({_initiator_execution_clause(instance_alias)})"


def _parse_execution_context(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    return None


def _status_label(status: str) -> str:
    return {
        STATUS_PENDING: "待审批",
        STATUS_APPROVED: "已通过",
        STATUS_REJECTED: "已驳回",
        STATUS_REVOKED: "已撤销",
        STATUS_COMPLETED: "已完成",
    }.get(status, status)


def _display_status_key(instance_status: str, application_status: str = "", *, has_application: bool = False) -> str:
    app_status = str(application_status or "").strip()
    if instance_status == STATUS_COMPLETED and has_application:
        if app_status in {"待执行", "已通过", ""}:
            return "awaiting_execution"
        if app_status == "执行中":
            return "executing"
        if app_status == "失败":
            return "execution_failed"
    return instance_status


def _display_status_label(instance_status: str, application_status: str = "", *, has_application: bool = False) -> str:
    key = _display_status_key(instance_status, application_status, has_application=has_application)
    if key == "awaiting_execution":
        return "待执行"
    if key == "executing":
        return "执行中"
    if key == "execution_failed":
        return "失败"
    return _status_label(instance_status)


def _application_status_by_instances(instance_ids: list[int]) -> dict[int, str]:
    if not instance_ids:
        return {}
    placeholders = ",".join(["%s"] * len(instance_ids))
    rows = query(
        f"""
        SELECT workflow_instance_id, approval_status
        FROM project_applications
        WHERE workflow_instance_id IN ({placeholders})
        """,
        tuple(instance_ids),
    )
    return {int(row["workflow_instance_id"]): str(row.get("approval_status") or "") for row in rows}


def generate_serial_no() -> str:
    prefix = datetime.now().strftime("%Y%m%d")
    row = query_one("SELECT COUNT(*) AS n FROM workflow_instances WHERE serial_no LIKE %s", (f"{prefix}%",))
    count = int(row["n"]) if row else 0
    return f"{prefix}{count + 1:04d}"


def _parse_levels(instance: dict[str, Any]) -> list[dict[str, Any]]:
    snap = instance.get("template_snapshot")
    if isinstance(snap, str):
        snap = json.loads(snap or "[]")
    if isinstance(snap, list):
        return snap
    return []


def _offset_levels(pre_levels: list[dict[str, Any]], tpl_levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    offset = len(pre_levels)
    merged = [dict(item) for item in pre_levels]
    for lv in tpl_levels:
        merged.append(
            {
                **lv,
                "level": offset + int(lv.get("level") or len(merged) + 1),
            }
        )
    for index, lv in enumerate(merged, start=1):
        lv["level"] = index
    return merged


def create_helm_project_workflow(
    *,
    record_id: str,
    title: str,
    summary: str,
    form_data: list[dict[str, Any]],
    initiator_id: int,
    initiator_name: str,
    pre_levels: list[dict[str, Any]] | None = None,
    workflow_type: str = WORKFLOW_TYPE_HELM_PROJECT,
) -> tuple[int, str]:
    pre_levels = pre_levels or []
    tpl = get_default_template(workflow_type) or get_default_template(WORKFLOW_TYPE_HELM_PROJECT)
    tpl_levels = (tpl or {}).get("levels") or []
    merged = _offset_levels(pre_levels, tpl_levels)
    if not merged:
        approvers = list_approver_users()
        if not approvers:
            raise ValueError("未配置审批模板或管理员账号，无法创建审批任务")
        merged = [
            {
                "level": 1,
                "name": "管理员审批",
                "approval_mode": "any",
                "assignees": [
                    {"user_id": user["id"], "user_name": user["display_name"] or user["name"]}
                    for user in approvers
                ],
                "cc_users": [],
            }
        ]
    first = merged[0]
    serial_no = generate_serial_no()
    now = _now()
    template_id = int(tpl["id"]) if tpl else None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflow_instances
                (serial_no, title, workflow_type, status, initiator_id, initiator_name, summary,
                 form_data, current_node, ref_record_id, template_id, template_snapshot, current_level, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
                """,
                (
                    serial_no,
                    title,
                    workflow_type,
                    STATUS_PENDING,
                    initiator_id,
                    initiator_name,
                    summary,
                    json.dumps(form_data, ensure_ascii=False),
                    first.get("name") or "一级审批",
                    record_id,
                    template_id,
                    levels_snapshot(merged),
                    now,
                    now,
                ),
            )
            instance_id = int(cur.lastrowid)
            for assignee in first.get("assignees") or []:
                cur.execute(
                    """
                    INSERT INTO workflow_tasks
                    (instance_id, assignee_id, assignee_name, status, node_name, level, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
                    """,
                    (
                        instance_id,
                        int(assignee["user_id"]),
                        str(assignee.get("user_name") or ""),
                        TASK_PENDING,
                        first.get("name") or "一级审批",
                        now,
                        now,
                    ),
                )
            for cc in first.get("cc_users") or []:
                cur.execute(
                    "INSERT INTO workflow_ccs (instance_id, user_id, created_at) VALUES (%s, %s, %s)",
                    (instance_id, int(cc["user_id"]), now),
                )
            cur.execute(
                """
                INSERT INTO workflow_records
                (instance_id, node_name, user_id, user_name, action, action_label, comment, created_at)
                VALUES (%s, %s, %s, %s, 'submit', '已提交', '', %s)
                """,
                (instance_id, "提交", initiator_id, initiator_name, now),
            )
        conn.commit()
    return instance_id, serial_no


def _get_instance(instance_id: int) -> dict[str, Any]:
    row = query_one("SELECT * FROM workflow_instances WHERE id = %s", (instance_id,))
    if not row:
        raise LookupError("审批实例不存在")
    return row


def _advance_or_complete(instance_id: int, current_level: int) -> bool:
    instance = _get_instance(instance_id)
    levels = _parse_levels(instance)
    next_level = current_level + 1
    next_lv = next((lv for lv in levels if int(lv.get("level") or 0) == next_level), None)
    now = _now()
    if not next_lv:
        execute(
            "UPDATE workflow_instances SET status = %s, current_node = %s, updated_at = %s WHERE id = %s",
            (STATUS_COMPLETED, "已完成", now, instance_id),
        )
        return True
    execute(
        """
        UPDATE workflow_instances
        SET current_level = %s, current_node = %s, updated_at = %s
        WHERE id = %s
        """,
        (next_level, next_lv.get("name") or f"{next_level}级审批", now, instance_id),
    )
    for assignee in next_lv.get("assignees") or []:
        execute(
            """
            INSERT INTO workflow_tasks
            (instance_id, assignee_id, assignee_name, status, node_name, level, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                instance_id,
                int(assignee["user_id"]),
                str(assignee.get("user_name") or ""),
                TASK_PENDING,
                next_lv.get("name") or f"{next_level}级审批",
                next_level,
                now,
                now,
            ),
        )
    for cc in next_lv.get("cc_users") or []:
        execute(
            "INSERT INTO workflow_ccs (instance_id, user_id, created_at) VALUES (%s, %s, %s)",
            (instance_id, int(cc["user_id"]), now),
        )
    return False


def approve_task(instance_id: int, task_id: int, user_id: int, user_name: str, comment: str = "") -> bool:
    instance = _get_instance(instance_id)
    if instance["status"] != STATUS_PENDING:
        raise ValueError("当前审批已结束")
    task = query_one(
        "SELECT * FROM workflow_tasks WHERE id = %s AND instance_id = %s AND status = %s",
        (task_id, instance_id, TASK_PENDING),
    )
    if not task:
        raise LookupError("待办任务不存在")
    if int(task["assignee_id"]) != user_id:
        raise PermissionError("无权审批该任务")
    now = _now()
    levels = _parse_levels(instance)
    level_no = int(task["level"])
    level = next((lv for lv in levels if int(lv.get("level") or 0) == level_no), None)
    mode = str((level or {}).get("approval_mode") or "any")
    execute(
        "UPDATE workflow_tasks SET status = %s, comment = %s, processed_at = %s, updated_at = %s WHERE id = %s",
        (TASK_APPROVED, comment, now, now, task_id),
    )
    execute(
        """
        INSERT INTO workflow_records
        (instance_id, node_name, user_id, user_name, action, action_label, comment, created_at)
        VALUES (%s, %s, %s, %s, 'approve', '已通过', %s, %s)
        """,
        (instance_id, task["node_name"], user_id, user_name, comment, now),
    )
    if mode == "any":
        execute(
            """
            UPDATE workflow_tasks
            SET status = %s, processed_at = %s, updated_at = %s
            WHERE instance_id = %s AND level = %s AND status = %s AND id <> %s
            """,
            (TASK_CANCELLED, now, now, instance_id, level_no, TASK_PENDING, task_id),
        )
        return _advance_or_complete(instance_id, level_no)
    pending = query_one(
        """
        SELECT COUNT(*) AS n FROM workflow_tasks
        WHERE instance_id = %s AND level = %s AND status = %s
        """,
        (instance_id, level_no, TASK_PENDING),
    )
    if pending and int(pending["n"]) > 0:
        return False
    return _advance_or_complete(instance_id, level_no)


def reject_task(instance_id: int, task_id: int, user_id: int, user_name: str, comment: str = "") -> None:
    instance = _get_instance(instance_id)
    if instance["status"] != STATUS_PENDING:
        raise ValueError("当前审批已结束")
    task = query_one(
        "SELECT * FROM workflow_tasks WHERE id = %s AND instance_id = %s AND status = %s",
        (task_id, instance_id, TASK_PENDING),
    )
    if not task:
        raise LookupError("待办任务不存在")
    if int(task["assignee_id"]) != user_id:
        raise PermissionError("无权审批该任务")
    now = _now()
    execute(
        "UPDATE workflow_tasks SET status = %s, comment = %s, processed_at = %s, updated_at = %s WHERE id = %s",
        (TASK_REJECTED, comment, now, now, task_id),
    )
    execute(
        """
        INSERT INTO workflow_records
        (instance_id, node_name, user_id, user_name, action, action_label, comment, created_at)
        VALUES (%s, %s, %s, %s, 'reject', '已驳回', %s, %s)
        """,
        (instance_id, task["node_name"], user_id, user_name, comment, now),
    )
    execute(
        "UPDATE workflow_instances SET status = %s, updated_at = %s WHERE id = %s",
        (STATUS_REJECTED, now, instance_id),
    )


def revoke_instance(instance_id: int, user_id: int) -> None:
    instance = _get_instance(instance_id)
    if int(instance["initiator_id"]) != user_id:
        raise PermissionError("仅发起人可撤销")
    if instance["status"] not in {STATUS_PENDING}:
        raise ValueError("当前状态不可撤销")
    now = _now()
    execute("UPDATE workflow_instances SET status = %s, updated_at = %s WHERE id = %s", (STATUS_REVOKED, now, instance_id))
    execute(
        """
        UPDATE workflow_tasks SET status = %s, updated_at = %s
        WHERE instance_id = %s AND status = %s
        """,
        (TASK_CANCELLED, now, instance_id, TASK_PENDING),
    )


def get_counts(user_id: int) -> dict[str, int]:
    todo = query_one(
        f"""
        SELECT COUNT(*) AS n FROM (
            SELECT i.id FROM workflow_tasks t
            JOIN workflow_instances i ON i.id = t.instance_id
            WHERE t.assignee_id = %s AND t.status = %s AND i.status = %s
            UNION
            SELECT i.id FROM workflow_instances i
            WHERE {_initiator_execution_clause("i")}
        ) todo_items
        """,
        (
            user_id,
            TASK_PENDING,
            STATUS_PENDING,
            user_id,
            STATUS_COMPLETED,
            *_EXECUTABLE_APP_STATUSES,
        ),
    )
    done = query_one(
        f"""
        SELECT COUNT(*) AS n FROM workflow_tasks t
        JOIN workflow_instances i ON i.id = t.instance_id
        WHERE t.assignee_id = %s AND t.status IN (%s, %s, %s)
          AND {_exclude_initiator_execution_clause("i")}
        """,
        (
            user_id,
            TASK_APPROVED,
            TASK_REJECTED,
            TASK_CANCELLED,
            user_id,
            STATUS_COMPLETED,
            *_EXECUTABLE_APP_STATUSES,
        ),
    )
    cc = query_one(
        f"""
        SELECT COUNT(*) AS n FROM workflow_ccs c
        JOIN workflow_instances i ON i.id = c.instance_id
        WHERE c.user_id = %s AND c.read_at IS NULL
        """,
        (user_id,),
    )
    initiated = query_one(
        "SELECT COUNT(*) AS n FROM workflow_instances WHERE initiator_id = %s",
        (user_id,),
    )
    return {
        "todo": int(todo["n"]) if todo else 0,
        "done": int(done["n"]) if done else 0,
        "cc": int(cc["n"]) if cc else 0,
        "initiated": int(initiated["n"]) if initiated else 0,
    }


def list_tasks(user_id: int, box: str, page: int, page_size: int, keyword: str = "") -> tuple[list[dict[str, Any]], int]:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size
    kw = keyword.strip()
    kw_clause = ""
    kw_args: list[Any] = []
    if kw:
        like = f"%{kw}%"
        kw_clause = " AND (i.title LIKE %s OR i.serial_no LIKE %s OR i.summary LIKE %s OR i.initiator_name LIKE %s)"
        kw_args = [like, like, like, like]
    if box == "todo":
        total_row = query_one(
            f"""
            SELECT COUNT(*) AS n FROM (
                SELECT i.id FROM workflow_tasks t
                JOIN workflow_instances i ON i.id = t.instance_id
                WHERE t.assignee_id = %s AND t.status = %s AND i.status = %s{kw_clause}
                UNION
                SELECT i.id FROM workflow_instances i
                WHERE {_initiator_execution_clause("i")}{kw_clause}
            ) todo_items
            """,
            (
                user_id,
                TASK_PENDING,
                STATUS_PENDING,
                *kw_args,
                user_id,
                STATUS_COMPLETED,
                *_EXECUTABLE_APP_STATUSES,
                *kw_args,
            ),
        )
        rows = query(
            f"""
            SELECT * FROM (
                SELECT {_LIST_SELECT}
                FROM workflow_tasks t
                JOIN workflow_instances i ON i.id = t.instance_id
                WHERE t.assignee_id = %s AND t.status = %s AND i.status = %s{kw_clause}
                UNION ALL
                SELECT {_INITIATOR_SELECT}
                FROM workflow_instances i
                WHERE {_initiator_execution_clause("i")}{kw_clause}
            ) todo_items
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
            """,
            (
                user_id,
                TASK_PENDING,
                STATUS_PENDING,
                *kw_args,
                user_id,
                STATUS_COMPLETED,
                *_EXECUTABLE_APP_STATUSES,
                *kw_args,
                page_size,
                offset,
            ),
        )
    elif box == "done":
        total_row = query_one(
            f"""
            SELECT COUNT(*) AS n FROM workflow_tasks t
            JOIN workflow_instances i ON i.id = t.instance_id
            WHERE t.assignee_id = %s AND t.status IN (%s, %s, %s)
              AND {_exclude_initiator_execution_clause("i")}{kw_clause}
            """,
            (
                user_id,
                TASK_APPROVED,
                TASK_REJECTED,
                TASK_CANCELLED,
                user_id,
                STATUS_COMPLETED,
                *_EXECUTABLE_APP_STATUSES,
                *kw_args,
            ),
        )
        rows = query(
            f"""
            SELECT t.id AS task_id, i.id AS instance_id, i.serial_no, i.title, i.workflow_type,
                   i.status, i.summary, i.initiator_name, t.assignee_name, t.processed_at,
                   i.created_at, i.updated_at
            FROM workflow_tasks t
            JOIN workflow_instances i ON i.id = t.instance_id
            WHERE t.assignee_id = %s AND t.status IN (%s, %s, %s)
              AND {_exclude_initiator_execution_clause("i")}{kw_clause}
            ORDER BY t.processed_at DESC
            LIMIT %s OFFSET %s
            """,
            (
                user_id,
                TASK_APPROVED,
                TASK_REJECTED,
                TASK_CANCELLED,
                user_id,
                STATUS_COMPLETED,
                *_EXECUTABLE_APP_STATUSES,
                *kw_args,
                page_size,
                offset,
            ),
        )
    elif box == "cc":
        total_row = query_one(
            f"""
            SELECT COUNT(*) AS n FROM workflow_ccs c
            JOIN workflow_instances i ON i.id = c.instance_id
            WHERE c.user_id = %s{kw_clause}
            """,
            (user_id, *kw_args),
        )
        rows = query(
            f"""
            SELECT 0 AS task_id, i.id AS instance_id, i.serial_no, i.title, i.workflow_type,
                   i.status, i.summary, i.initiator_name, '' AS assignee_name, NULL AS processed_at,
                   i.created_at, i.updated_at, c.read_at AS cc_read_at
            FROM workflow_ccs c
            JOIN workflow_instances i ON i.id = c.instance_id
            WHERE c.user_id = %s{kw_clause}
            ORDER BY i.updated_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, *kw_args, page_size, offset),
        )
    else:
        total_row = query_one(
            f"SELECT COUNT(*) AS n FROM workflow_instances WHERE initiator_id = %s{kw_clause.replace('i.', '')}",
            (user_id, *kw_args),
        )
        rows = query(
            f"""
            SELECT 0 AS task_id, id AS instance_id, serial_no, title, workflow_type,
                   status, summary, initiator_name, '' AS assignee_name, NULL AS processed_at,
                   created_at, updated_at
            FROM workflow_instances
            WHERE initiator_id = %s{kw_clause.replace('i.', '')}
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, *kw_args, page_size, offset),
        )
    total = int(total_row["n"]) if total_row else 0
    app_status_map = _application_status_by_instances([int(row["instance_id"]) for row in rows])
    items = []
    for row in rows:
        status = str(row["status"])
        instance_id = int(row["instance_id"])
        application_status = app_status_map.get(instance_id, "")
        has_application = instance_id in app_status_map
        items.append(
            {
                "task_id": int(row.get("task_id") or 0),
                "instance_id": instance_id,
                "serial_no": row["serial_no"],
                "title": row["title"],
                "workflow_type": row["workflow_type"],
                "status": status,
                "status_key": _display_status_key(status, application_status, has_application=has_application),
                "status_label": _display_status_label(status, application_status, has_application=has_application),
                "summary": row.get("summary") or "",
                "initiator_name": row.get("initiator_name") or "",
                "assignee_name": row.get("assignee_name") or "",
                "processed_at": str(row.get("processed_at") or "") or None,
                "created_at": str(row.get("created_at") or ""),
                "updated_at": str(row.get("updated_at") or ""),
                "cc_read": bool(row.get("cc_read_at")),
            }
        )
    return items, total


def _level_assignee_names(level: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in level.get("assignees") or []:
        if isinstance(item, dict):
            name = str(item.get("user_name") or item.get("display_name") or "").strip()
            if name:
                names.append(name)
    return names


def build_flow_steps(
    instance: dict[str, Any],
    records: list[dict[str, Any]],
    application_status: str = "",
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    submit_step: dict[str, Any] = {"level": 0, "name": "提交", "status": "done", "assignees": []}
    for row in records:
        if row.get("action") == "submit":
            submit_step["actor_name"] = row.get("user_name") or ""
            submit_step["action_label"] = row.get("action_label") or "已提交"
            submit_step["processed_at"] = str(row.get("created_at") or "") or None
            break
    if not submit_step.get("actor_name"):
        submit_step["actor_name"] = instance.get("initiator_name") or ""
        submit_step["action_label"] = "已提交"
        submit_step["processed_at"] = str(instance.get("created_at") or "") or None
    steps.append(submit_step)

    levels = _parse_levels(instance)
    record_by_node = {str(r.get("node_name") or ""): r for r in records if r.get("action") != "submit"}
    status = str(instance.get("status") or "")
    current_level = int(instance.get("current_level") or 1)

    pending_by_level: dict[int, list[str]] = {}
    if status == STATUS_PENDING:
        pending_rows = query(
            """
            SELECT level, assignee_name FROM workflow_tasks
            WHERE instance_id = %s AND status = %s
            ORDER BY id ASC
            """,
            (int(instance["id"]), TASK_PENDING),
        )
        for row in pending_rows:
            level_no = int(row.get("level") or 1)
            name = str(row.get("assignee_name") or "").strip() or "审批人"
            pending_by_level.setdefault(level_no, []).append(name)

    for lv in levels:
        level_no = int(lv.get("level") or 0)
        name = str(lv.get("name") or f"{level_no}级审批")
        step: dict[str, Any] = {"level": level_no, "name": name, "assignees": _level_assignee_names(lv)}
        record = record_by_node.get(name)
        if record and record.get("action") == "reject":
            step.update(
                {
                    "status": "rejected",
                    "actor_name": record.get("user_name") or "",
                    "action_label": record.get("action_label") or "",
                    "processed_at": str(record.get("created_at") or "") or None,
                }
            )
        elif status in {STATUS_REJECTED, STATUS_REVOKED}:
            if record and record.get("action") == "approve":
                step.update(
                    {
                        "status": "done",
                        "actor_name": record.get("user_name") or "",
                        "action_label": record.get("action_label") or "",
                        "processed_at": str(record.get("created_at") or "") or None,
                    }
                )
            elif level_no < current_level:
                step["status"] = "done"
            else:
                step["status"] = "cancelled"
        elif status in {STATUS_COMPLETED, STATUS_APPROVED}:
            if record:
                step.update(
                    {
                        "status": "done",
                        "actor_name": record.get("user_name") or "",
                        "action_label": record.get("action_label") or "",
                        "processed_at": str(record.get("created_at") or "") or None,
                    }
                )
            else:
                step["status"] = "done"
        elif level_no < current_level:
            if record:
                step.update(
                    {
                        "status": "done",
                        "actor_name": record.get("user_name") or "",
                        "action_label": record.get("action_label") or "",
                        "processed_at": str(record.get("created_at") or "") or None,
                    }
                )
            else:
                step["status"] = "done"
        elif status == STATUS_PENDING and level_no == current_level:
            step["status"] = "pending"
            if pending_by_level.get(level_no):
                step["assignees"] = pending_by_level[level_no]
        elif record:
            step.update(
                {
                    "status": "done",
                    "actor_name": record.get("user_name") or "",
                    "action_label": record.get("action_label") or "",
                    "processed_at": str(record.get("created_at") or "") or None,
                }
            )
        else:
            step["status"] = "upcoming"
        steps.append(step)

    agent_step: dict[str, Any] = {
        "level": 10000,
        "name": "Agent 执行",
        "status": "upcoming",
        "assignees": [str(instance.get("initiator_name") or "申请人")],
    }
    app_status = str(application_status or "").strip()
    if app_status == "已完成":
        agent_step["status"] = "done"
        agent_step["actor_name"] = str(instance.get("initiator_name") or "申请人")
        agent_step["action_label"] = "已执行"
    elif app_status == "执行中":
        agent_step["status"] = "pending"
        agent_step["action_label"] = "执行中"
    elif app_status == "失败":
        agent_step["status"] = "failed"
        agent_step["actor_name"] = str(instance.get("initiator_name") or "申请人")
        agent_step["action_label"] = "执行失败"
    elif status == STATUS_COMPLETED and app_status in {"待执行", "已通过", ""}:
        agent_step["status"] = "pending"
        agent_step["action_label"] = "待执行"
    elif status == STATUS_COMPLETED:
        agent_step["status"] = "pending"
    steps.append(agent_step)
    return steps


def get_instance_detail(instance_id: int, user_id: int) -> dict[str, Any]:
    from webapi.applications import reconcile_stale_execution

    reconcile_stale_execution(instance_id)
    instance = _get_instance(instance_id)
    records = query(
        "SELECT * FROM workflow_records WHERE instance_id = %s ORDER BY id ASC",
        (instance_id,),
    )
    tasks = query("SELECT * FROM workflow_tasks WHERE instance_id = %s ORDER BY id ASC", (instance_id,))
    pending_task = query_one(
        """
        SELECT * FROM workflow_tasks
        WHERE instance_id = %s AND assignee_id = %s AND status = %s
        ORDER BY id ASC LIMIT 1
        """,
        (instance_id, user_id, TASK_PENDING),
    )
    form_data = instance.get("form_data")
    if isinstance(form_data, str):
        form_data = json.loads(form_data or "[]")
    status = str(instance.get("status") or "")
    can_approve = pending_task is not None
    application = None
    application_status = ""
    if instance.get("ref_record_id"):
        app_row = query_one(
            "SELECT * FROM project_applications WHERE record_id = %s",
            (instance.get("ref_record_id"),),
        )
        if app_row:
            application_status = str(app_row.get("approval_status") or "")
            project_key = str(app_row.get("project_key") or "")
            from webapi.agent_runner import build_project_url

            execution_context = _parse_execution_context(app_row.get("execution_context_json"))
            agent_meta = execution_context.get("agent") if isinstance(execution_context, dict) else None
            application = {
                "record_id": app_row.get("record_id") or "",
                "flow_status": application_status,
                "process_message": app_row.get("process_message") or "",
                "execution_log": app_row.get("execution_log") or "",
                "project_key": project_key,
                "project_url": str(app_row.get("project_url") or "").strip() or build_project_url(project_key),
                "execution_context": execution_context,
                "agent_meta": agent_meta if isinstance(agent_meta, dict) else None,
            }
    from webapi.applications import can_execute_application, is_execution_awaiting_input

    awaiting_input = is_execution_awaiting_input(instance_id)
    is_readonly = status in {STATUS_REJECTED, STATUS_REVOKED} or (
        status == STATUS_COMPLETED and (not application or application_status == "已完成")
    )
    flow_steps = build_flow_steps(instance, records, application_status)
    record_items = [
        {
            "id": int(row["id"]),
            "node_name": row.get("node_name") or "",
            "user_name": row.get("user_name") or "",
            "action": row.get("action") or "",
            "action_label": row.get("action_label") or "",
            "comment": row.get("comment") or "",
            "created_at": str(row.get("created_at") or ""),
        }
        for row in records
    ]
    return {
        "instance": {
            "id": int(instance["id"]),
            "serial_no": instance["serial_no"],
            "title": instance["title"],
            "workflow_type": instance["workflow_type"],
            "status": status,
            "status_key": _display_status_key(status, application_status, has_application=application is not None),
            "status_label": _display_status_label(status, application_status, has_application=application is not None),
            "summary": instance.get("summary") or "",
            "initiator_id": int(instance["initiator_id"]),
            "initiator_name": instance.get("initiator_name") or "",
            "initiator_dept": "Zadig",
            "current_node": instance.get("current_node") or "",
            "current_level": int(instance.get("current_level") or 1),
            "ref_record_id": instance.get("ref_record_id") or "",
            "created_at": str(instance.get("created_at") or ""),
            "updated_at": str(instance.get("updated_at") or ""),
        },
        "form_data": form_data if isinstance(form_data, list) else [],
        "flow_steps": flow_steps,
        "records": record_items,
        "application": application,
        "can_approve": can_approve,
        "can_reject": can_approve,
        "can_revoke": int(instance["initiator_id"]) == user_id and status == STATUS_PENDING,
        "can_execute": bool(
            application
            and can_execute_application(
                {"initiator_id": int(instance["initiator_id"]), "approval_status": application_status},
                initiator_id=user_id,
                workflow_status=status,
                instance_id=instance_id,
            )
        ),
        "is_readonly": is_readonly,
        "execution_session": {
            "awaiting_input": awaiting_input,
        },
        "permissions": {
            "can_approve": can_approve,
            "can_reject": can_approve,
            "can_revoke": int(instance["initiator_id"]) == user_id and status == STATUS_PENDING,
            "can_execute": bool(
                application
                and can_execute_application(
                    {"initiator_id": int(instance["initiator_id"]), "approval_status": application_status},
                    initiator_id=user_id,
                    workflow_status=status,
                    instance_id=instance_id,
                )
            ),
            "pending_task_id": int(pending_task["id"]) if pending_task else 0,
        },
        "tasks": [
            {
                "id": int(row["id"]),
                "assignee_id": int(row["assignee_id"]),
                "assignee_name": row.get("assignee_name") or "",
                "status": row.get("status") or "",
                "node_name": row.get("node_name") or "",
                "level": int(row.get("level") or 1),
            }
            for row in tasks
        ],
    }

"""审批动作执行（Web / 飞书卡片 / URL）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.db import execute, query_one
from webapi.applications import sync_application_status
from webapi.approval_tokens import parse_approval_token
from webapi.feishu_cards import build_approval_card
from webapi.platform_users import get_user_by_id, get_user_row_by_id
from webapi.workflow_notify import get_level_targets, schedule_approval_notifications
from webapi.workflows import (
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_REVOKED,
    TASK_PENDING,
    _get_instance,
    _parse_levels,
    approve_task,
    reject_task,
)


@dataclass
class ApprovalActionOutcome:
    toast_type: str = "info"
    toast_message: str = ""
    card_status: str = ""
    card_message: str = ""
    http_status: int = 200
    page_title: str = ""
    page_message: str = ""
    final_approved: bool = False
    instance_id: int = 0
    title: str = ""
    initiator_name: str = ""
    serial_no: str = ""
    from_node: str = ""
    next_level_name: str = ""
    next_assignees: list[dict[str, Any]] = field(default_factory=list)
    next_cc_users: list[dict[str, Any]] = field(default_factory=list)
    reject_comment: str = ""
    notify_now: bool = True
    clicked_action: str = ""


def _parse_form_fields(instance: dict[str, Any]) -> list[dict[str, str]]:
    import json

    raw = instance.get("form_data")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if label and value:
            out.append({"label": label, "value": value})
    return out


def build_outcome_card(instance_id: int, outcome: ApprovalActionOutcome) -> dict[str, Any] | None:
    if instance_id <= 0:
        return None
    try:
        instance = _get_instance(instance_id)
    except LookupError:
        return None
    status = outcome.card_status.strip()
    message = outcome.card_message.strip()
    clicked = outcome.clicked_action.strip()
    if not status and not message and not clicked:
        return None
    return build_approval_card(
        header_title=str(instance.get("current_node") or "审批待办"),
        title=str(instance.get("title") or ""),
        initiator=str(instance.get("initiator_name") or ""),
        serial_no=str(instance.get("serial_no") or ""),
        level_name=str(instance.get("current_node") or ""),
        summary=str(instance.get("summary") or ""),
        form_fields=_parse_form_fields(instance),
        clicked_action=clicked,
        result_status=status,
        result_message=message,
    )


def _resolve_pending_task_id(instance_id: int, user_id: int, token_task_id: int) -> int:
    row = query_one(
        """
        SELECT id FROM workflow_tasks
        WHERE instance_id = %s AND assignee_id = %s AND status = %s
        ORDER BY id ASC
        LIMIT 1
        """,
        (instance_id, user_id, TASK_PENDING),
    )
    if row:
        return int(row["id"])
    if token_task_id > 0:
        exists = query_one(
            "SELECT id FROM workflow_tasks WHERE id = %s AND instance_id = %s",
            (token_task_id, instance_id),
        )
        if exists:
            return token_task_id
    raise LookupError("审批任务已变更，请处理最新收到的待办卡片")


def _cancel_other_pending_tasks(instance_id: int, keep_task_id: int) -> None:
    from utils.db import _now

    execute(
        """
        UPDATE workflow_tasks
        SET status = 'cancelled', updated_at = %s
        WHERE instance_id = %s AND status = %s AND id <> %s
        """,
        (_now(), instance_id, TASK_PENDING, keep_task_id),
    )


def verify_feishu_card_actor(user_id: int, open_id: str) -> None:
    open_id = open_id.strip()
    if not open_id:
        return
    row = get_user_row_by_id(user_id)
    if not row:
        raise PermissionError("审批用户不存在")
    existing = str(row.get("feishu_open_id") or "").strip()
    if existing and existing != open_id:
        raise PermissionError("飞书账号与审批人不匹配")
    if not existing:
        from utils.db import _now

        execute(
            "UPDATE platform_users SET feishu_open_id = %s, auth_source = 'feishu', updated_at = %s WHERE id = %s",
            (open_id, _now(), user_id),
        )


def run_approval_action(
    instance_id: int,
    task_id: int,
    user_id: int,
    action: str,
    *,
    comment: str = "",
    notify_now: bool = True,
) -> ApprovalActionOutcome:
    action = str(action or "").strip()
    if action not in {"approve", "reject"}:
        return ApprovalActionOutcome(
            toast_type="error",
            toast_message="无效操作",
            http_status=400,
            page_title="无效链接",
            page_message="无效审批操作",
        )
    user = get_user_by_id(user_id)
    if not user:
        return ApprovalActionOutcome(
            toast_type="error",
            toast_message="用户无效",
            http_status=400,
            page_title="用户无效",
            page_message="审批用户不存在或已删除",
        )
    user_name = str(user.get("display_name") or user.get("name") or "")
    try:
        instance = _get_instance(instance_id)
    except LookupError:
        return ApprovalActionOutcome(
            toast_type="error",
            toast_message="流程不存在",
            http_status=400,
            page_title="流程不存在",
            page_message="审批流程不存在或已删除",
        )
    if str(instance.get("status") or "") == STATUS_REVOKED:
        return ApprovalActionOutcome(
            toast_type="info",
            toast_message="申请人已撤销",
            card_status="revoked",
            card_message="**审批结果：**申请人已撤销",
            http_status=400,
            instance_id=instance_id,
            notify_now=notify_now,
        )
    before_level = int(instance.get("current_level") or 1)
    from_node = str(instance.get("current_node") or "")

    if action == "reject":
        try:
            reject_task(instance_id, task_id, user_id, user_name, comment)
            _cancel_other_pending_tasks(instance_id, task_id)
        except (PermissionError, LookupError, ValueError) as exc:
            return _already_handled_outcome(exc, "reject", notify_now=notify_now)
        sync_application_status(instance_id, "rejected")
        outcome = ApprovalActionOutcome(
            toast_type="success",
            toast_message="已驳回",
            card_status="rejected",
            card_message="**审批结果：**已驳回",
            http_status=200,
            page_title="已驳回",
            page_message="您已完成驳回，流程已更新。",
            instance_id=instance_id,
            reject_comment=comment,
            notify_now=notify_now,
            clicked_action="reject",
        )
        if notify_now:
            schedule_approval_notifications(outcome.__dict__)
        return outcome

    try:
        completed = approve_task(instance_id, task_id, user_id, user_name, comment)
    except (PermissionError, LookupError, ValueError) as exc:
        return _already_handled_outcome(exc, "approve", notify_now=notify_now)
    if completed:
        sync_application_status(instance_id, "completed")
        outcome = ApprovalActionOutcome(
            toast_type="success",
            toast_message="已通过",
            card_status="approved",
            card_message="**审批结果：**已通过，请发起人进入平台执行。",
            http_status=200,
            page_title="已通过",
            page_message="您已完成审批，流程已进入待执行状态。",
            final_approved=True,
            instance_id=instance_id,
            notify_now=notify_now,
            clicked_action="approve",
        )
        if notify_now:
            schedule_approval_notifications(outcome.__dict__)
        return outcome

    after = _get_instance(instance_id)
    after_level = int(after.get("current_level") or before_level)
    next_level_name = ""
    next_assignees: list[dict[str, Any]] = []
    next_cc_users: list[dict[str, Any]] = []
    if after_level > before_level:
        next_level_name, next_assignees, next_cc_users = get_level_targets(instance_id, after_level)
    outcome = ApprovalActionOutcome(
        toast_type="success",
        toast_message="已通过",
        card_status="approved",
        card_message="**审批结果：**已通过，流程已流转至下一节点。",
        http_status=200,
        page_title="已通过",
        page_message="您已完成本级审批，流程已流转至下一节点。",
        instance_id=instance_id,
        title=str(after.get("title") or ""),
        initiator_name=str(after.get("initiator_name") or ""),
        serial_no=str(after.get("serial_no") or ""),
        from_node=from_node,
        next_level_name=next_level_name,
        next_assignees=next_assignees,
        next_cc_users=next_cc_users,
        notify_now=notify_now,
        clicked_action="approve",
    )
    if notify_now:
        schedule_approval_notifications(outcome.__dict__)
    return outcome


def run_approval_action_from_token(
    token: str,
    *,
    action: str = "",
    open_id: str = "",
    notify_now: bool = True,
) -> ApprovalActionOutcome:
    try:
        claims = parse_approval_token(token)
    except ValueError as exc:
        return ApprovalActionOutcome(
            toast_type="error",
            toast_message=str(exc),
            card_status="rejected",
            card_message=f"**审批结果：**{exc}",
            http_status=400,
            page_title="链接已失效",
            page_message=str(exc),
        )
    expected_action = str(action or claims["action"]).strip()
    if expected_action != claims["action"]:
        return ApprovalActionOutcome(
            toast_type="error",
            toast_message="操作不匹配",
            card_status="rejected",
            card_message="**审批结果：**操作不匹配",
            http_status=400,
            instance_id=int(claims["instance_id"]),
        )
    try:
        if open_id.strip():
            verify_feishu_card_actor(int(claims["user_id"]), open_id)
        task_id = _resolve_pending_task_id(int(claims["instance_id"]), int(claims["user_id"]), int(claims["task_id"]))
    except PermissionError as exc:
        return ApprovalActionOutcome(
            toast_type="error",
            toast_message=str(exc),
            http_status=403,
            page_title="无权操作",
            page_message=str(exc),
            instance_id=int(claims["instance_id"]),
        )
    except LookupError as exc:
        return ApprovalActionOutcome(
            toast_type="error",
            toast_message=str(exc),
            card_status="rejected",
            card_message=f"**审批结果：**{exc}",
            http_status=400,
            instance_id=int(claims["instance_id"]),
        )
    return run_approval_action(
        int(claims["instance_id"]),
        task_id,
        int(claims["user_id"]),
        expected_action,
        notify_now=notify_now,
    )


def _already_handled_outcome(exc: Exception, action: str, *, notify_now: bool) -> ApprovalActionOutcome:
    msg = str(exc)
    if "不存在" in msg or "已结束" in msg or "无权" in msg:
        status = "approved" if action == "approve" else "rejected"
        text = "该审批已处理，无需重复操作。"
        if action == "reject":
            text = "该审批已驳回或已处理，无需重复操作。"
        return ApprovalActionOutcome(
            toast_type="info",
            toast_message=text,
            card_status=status,
            card_message=f"**审批结果：**{text}",
            http_status=400,
            page_title="已处理",
            page_message=text,
            notify_now=notify_now,
        )
    return ApprovalActionOutcome(
        toast_type="error",
        toast_message=msg,
        http_status=400,
        page_title="审批失败",
        page_message=msg,
        notify_now=notify_now,
    )

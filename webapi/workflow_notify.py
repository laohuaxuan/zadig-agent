"""审批流飞书通知。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from utils.db import query, query_one
from webapi.approval_tokens import generate_approval_token
from webapi.feishu_cards import build_approval_card, build_cc_card, build_status_card
from webapi.feishu_client import FeishuClient
from webapi.platform_users import get_user_by_id
from webapi.workflow_feishu_cards import create_workflow_feishu_card, list_workflow_feishu_cards_by_instance
from webapi.workflows import TASK_PENDING, _get_instance, _parse_levels

logger = logging.getLogger(__name__)
_feishu = FeishuClient()


def _workflow_instance_link(instance_id: int) -> str:
    base = str(_feishu.cfg.get("app_base_url") or "").strip().rstrip("/")
    if not base or instance_id <= 0:
        return ""
    return f"{base}/workflows?instance={instance_id}"


def _parse_form_data(instance: dict[str, Any]) -> list[dict[str, str]]:
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


def _resolve_feishu_open_id(user: dict[str, Any]) -> str:
    open_id = str(user.get("feishu_open_id") or "").strip()
    if open_id:
        return open_id
    display = str(user.get("display_name") or user.get("name") or "").strip()
    if not display or not _feishu.enabled():
        return ""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return ""
    except RuntimeError:
        pass
    return ""


async def _resolve_feishu_open_id_async(user: dict[str, Any]) -> str:
    open_id = str(user.get("feishu_open_id") or "").strip()
    if open_id:
        return open_id
    if not _feishu.enabled():
        return ""
    display = str(user.get("display_name") or user.get("name") or "").strip()
    if not display:
        return ""
    try:
        result = await _feishu.list_contact_users(display, 5)
    except Exception:
        return ""
    for item in result.get("items") or []:
        name = str(item.get("name") or "").strip()
        candidate = str(item.get("open_id") or "").strip()
        if candidate and name == display:
            return candidate
    items = result.get("items") or []
    if len(items) == 1:
        return str(items[0].get("open_id") or "").strip()
    return ""


def _pending_task_for_user(instance_id: int, user_id: int) -> dict[str, Any] | None:
    return query_one(
        """
        SELECT * FROM workflow_tasks
        WHERE instance_id = %s AND assignee_id = %s AND status = %s
        ORDER BY id ASC
        LIMIT 1
        """,
        (instance_id, user_id, TASK_PENDING),
    )


async def _notify_feishu_approver(
    instance_id: int,
    user: dict[str, Any],
    *,
    title: str,
    initiator: str,
    serial_no: str,
    level_name: str,
    summary: str,
    form_fields: list[dict[str, str]],
) -> bool:
    if not _feishu.enabled():
        return False
    open_id = await _resolve_feishu_open_id_async(user)
    if not open_id:
        return False
    task = _pending_task_for_user(instance_id, int(user["id"]))
    if not task:
        return False
    try:
        approve_token = generate_approval_token(instance_id, int(task["id"]), int(user["id"]), "approve")
        reject_token = generate_approval_token(instance_id, int(task["id"]), int(user["id"]), "reject")
    except ValueError:
        return False
    api_base = _feishu.public_api_base()
    card = build_approval_card(
        header_title=level_name,
        title=title,
        initiator=initiator,
        serial_no=serial_no,
        level_name=level_name,
        summary=summary,
        form_fields=form_fields,
        approve_token=approve_token,
        reject_token=reject_token,
        approve_url=_feishu.approval_action_url(api_base, approve_token) if api_base else "",
        reject_url=_feishu.approval_action_url(api_base, reject_token) if api_base else "",
    )
    try:
        message_id = await _feishu.send_interactive_card(open_id, card)
    except Exception as exc:
        logger.warning("feishu approval card user_id=%s: %s", user.get("id"), exc)
        return False
    if message_id:
        create_workflow_feishu_card(
            instance_id=instance_id,
            task_id=int(task["id"]),
            user_id=int(user["id"]),
            open_message_id=message_id,
            open_id=open_id,
        )
    return True


async def _notify_initiator(instance: dict[str, Any], header: str, body: str, *, template: str = "blue") -> None:
    if not _feishu.enabled():
        return
    user = get_user_by_id(int(instance.get("initiator_id") or 0))
    if not user:
        return
    open_id = await _resolve_feishu_open_id_async(user)
    if not open_id:
        return
    card = build_status_card(
        header_title=header,
        body=body,
        view_url=_workflow_instance_link(int(instance["id"])),
        template=template,
    )
    try:
        await _feishu.send_interactive_card(open_id, card)
    except Exception as exc:
        logger.warning("feishu applicant card user_id=%s: %s", user.get("id"), exc)


async def notify_workflow_level(
    instance_id: int,
    *,
    title: str,
    initiator: str,
    serial_no: str,
    level_name: str,
    assignees: list[dict[str, Any]],
    cc_users: list[dict[str, Any]] | None = None,
) -> None:
    if not _feishu.enabled() or instance_id <= 0:
        return
    instance = _get_instance(instance_id)
    form_fields = _parse_form_data(instance)
    summary = str(instance.get("summary") or "")
    link = _workflow_instance_link(instance_id)
    seen: set[int] = set()
    for raw in assignees or []:
        user_id = int(raw.get("user_id") or 0)
        if user_id <= 0 or user_id in seen:
            continue
        seen.add(user_id)
        user = get_user_by_id(user_id)
        if not user:
            continue
        await _notify_feishu_approver(
            instance_id,
            user,
            title=title,
            initiator=initiator,
            serial_no=serial_no,
            level_name=level_name,
            summary=summary,
            form_fields=form_fields,
        )
    for raw in cc_users or []:
        user_id = int(raw.get("user_id") or 0)
        if user_id <= 0 or user_id in seen:
            continue
        user = get_user_by_id(user_id)
        if not user:
            continue
        open_id = await _resolve_feishu_open_id_async(user)
        if not open_id:
            continue
        card = build_cc_card(
            header_title=level_name,
            title=title,
            initiator=initiator,
            serial_no=serial_no,
            level_name=level_name,
            summary=summary,
            view_url=link,
        )
        try:
            await _feishu.send_interactive_card(open_id, card)
        except Exception as exc:
            logger.warning("feishu cc card user_id=%s: %s", user_id, exc)


async def notify_workflow_submitted(instance_id: int, level_name: str) -> None:
    instance = _get_instance(instance_id)
    body = (
        f"您的申请已提交，流程编号 **{instance.get('serial_no') or ''}**。\n"
        f"当前等待审批节点：**{level_name}**"
    )
    await _notify_initiator(instance, "申请已提交", body, template="blue")


async def notify_workflow_level_progress(instance_id: int, approved_level_name: str, next_level_name: str) -> None:
    instance = _get_instance(instance_id)
    body = f"审批节点 **{approved_level_name}** 已通过。"
    if next_level_name.strip():
        body += f"\n当前等待：**{next_level_name}**"
    await _notify_initiator(instance, "审批进度更新", body, template="blue")


async def notify_workflow_all_approved(instance_id: int) -> None:
    instance = _get_instance(instance_id)
    body = "全部审批已通过，请进入平台 **执行** 对应申请。"
    await _notify_initiator(instance, "审批已全部通过", body, template="green")


async def notify_workflow_rejected(instance_id: int, comment: str = "") -> None:
    instance = _get_instance(instance_id)
    body = "您的申请已被驳回，流程已终止。"
    if comment.strip():
        body += f"\n审批意见：{comment.strip()}"
    await _notify_initiator(instance, "审批已驳回", body, template="red")


async def notify_workflow_revoked(instance_id: int) -> None:
    instance = _get_instance(instance_id)
    await _notify_initiator(instance, "申请已撤销", "您已撤销该申请，流程已终止。", template="grey")
    await update_feishu_approval_cards_for_instance(instance_id, "revoked", "**审批结果：**申请人已撤销")


async def update_feishu_approval_cards_for_instance(instance_id: int, status: str, message: str = "") -> None:
    if not _feishu.enabled():
        return
    instance = _get_instance(instance_id)
    form_fields = _parse_form_data(instance)
    card = build_approval_card(
        header_title=str(instance.get("current_node") or "审批待办"),
        title=str(instance.get("title") or ""),
        initiator=str(instance.get("initiator_name") or ""),
        serial_no=str(instance.get("serial_no") or ""),
        level_name=str(instance.get("current_node") or ""),
        summary=str(instance.get("summary") or ""),
        form_fields=form_fields,
        result_status=status,
        result_message=message,
    )
    for rec in list_workflow_feishu_cards_by_instance(instance_id):
        message_id = str(rec.get("open_message_id") or "").strip()
        if not message_id:
            continue
        try:
            await _feishu.update_interactive_message(message_id, card)
        except Exception as exc:
            logger.warning("feishu update card message_id=%s: %s", message_id, exc)


def get_level_targets(instance_id: int, level_no: int | None = None) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    instance = _get_instance(instance_id)
    levels = _parse_levels(instance)
    current_level = int(level_no or instance.get("current_level") or 1)
    level = next((item for item in levels if int(item.get("level") or 0) == current_level), None)
    if not level:
        rows = query(
            """
            SELECT assignee_id, assignee_name, node_name FROM workflow_tasks
            WHERE instance_id = %s AND level = %s AND status = %s
            ORDER BY id ASC
            """,
            (instance_id, current_level, TASK_PENDING),
        )
        if not rows:
            return f"{current_level}级审批", [], []
        name = str(rows[0].get("node_name") or f"{current_level}级审批")
        assignees = [
            {"user_id": int(row["assignee_id"]), "user_name": str(row.get("assignee_name") or "")}
            for row in rows
            if int(row.get("assignee_id") or 0) > 0
        ]
        return name, assignees, []
    assignees = [
        {"user_id": int(item.get("user_id") or 0), "user_name": str(item.get("user_name") or "")}
        for item in (level.get("assignees") or [])
        if int(item.get("user_id") or 0) > 0
    ]
    cc_users = [
        {"user_id": int(item.get("user_id") or 0), "user_name": str(item.get("user_name") or "")}
        for item in (level.get("cc_users") or [])
        if int(item.get("user_id") or 0) > 0
    ]
    return str(level.get("name") or f"{current_level}级审批"), assignees, cc_users


def schedule_revoke_notifications(instance_id: int) -> None:
    async def _run() -> None:
        try:
            await notify_workflow_revoked(instance_id)
        except Exception as exc:
            logger.warning("feishu revoke notify instance=%s: %s", instance_id, exc)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())


def schedule_submit_notifications(instance_id: int) -> None:
    async def _run() -> None:
        try:
            instance = _get_instance(instance_id)
            level_name, assignees, cc_users = get_level_targets(instance_id, int(instance.get("current_level") or 1))
            await notify_workflow_level(
                instance_id,
                title=str(instance.get("title") or ""),
                initiator=str(instance.get("initiator_name") or ""),
                serial_no=str(instance.get("serial_no") or ""),
                level_name=level_name,
                assignees=assignees,
                cc_users=cc_users,
            )
            await notify_workflow_submitted(instance_id, level_name)
        except Exception as exc:
            logger.warning("feishu submit notify instance=%s: %s", instance_id, exc)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())


def schedule_approval_notifications(outcome: dict[str, Any]) -> None:
    async def _run() -> None:
        try:
            instance_id = int(outcome.get("instance_id") or 0)
            if instance_id <= 0:
                return
            if outcome.get("toast_type") != "success":
                return
            status = str(outcome.get("card_status") or "")
            if status == "rejected":
                await notify_workflow_rejected(instance_id, str(outcome.get("reject_comment") or ""))
                return
            if status == "revoked":
                await notify_workflow_revoked(instance_id)
                return
            if outcome.get("final_approved"):
                await notify_workflow_all_approved(instance_id)
                return
            next_assignees = outcome.get("next_assignees") or []
            if next_assignees:
                await notify_workflow_level(
                    instance_id,
                    title=str(outcome.get("title") or ""),
                    initiator=str(outcome.get("initiator_name") or ""),
                    serial_no=str(outcome.get("serial_no") or ""),
                    level_name=str(outcome.get("next_level_name") or ""),
                    assignees=next_assignees,
                    cc_users=outcome.get("next_cc_users") or [],
                )
                await notify_workflow_level_progress(
                    instance_id,
                    str(outcome.get("from_node") or ""),
                    str(outcome.get("next_level_name") or ""),
                )
        except Exception as exc:
            logger.warning("feishu approval notify: %s", exc)

    notify_now = bool(outcome.get("notify_now", True))
    if not notify_now:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run())
        except RuntimeError:
            asyncio.run(_run())
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())

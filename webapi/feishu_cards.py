"""飞书审批卡片 JSON 2.0 构建。"""

from __future__ import annotations

import json
from typing import Any


def _plain_text(content: str) -> dict[str, Any]:
    return {"tag": "plain_text", "content": content}


def _disabled_button(label: str) -> dict[str, Any]:
    return {"tag": "button", "type": "default", "text": _plain_text(label), "disabled": True}


def _callback_button(label: str, btn_type: str, value: dict[str, Any], *, app: str = "") -> dict[str, Any]:
    payload = dict(value)
    if app.strip():
        payload["app"] = app.strip()
    action = str(payload.get("action") or "").strip()
    element_id = f"btn_{action}" if action else "btn_callback"
    type_map = {"primary": "primary_filled", "danger": "danger_filled"}
    return {
        "tag": "button",
        "type": type_map.get(btn_type, btn_type or "default"),
        "element_id": element_id,
        "width": "fill",
        "text": _plain_text(label),
        "behaviors": [{"type": "callback", "value": _callback_value_object(payload)}],
    }


def _url_button(label: str, btn_type: str, url: str) -> dict[str, Any]:
    type_map = {"primary": "primary_filled", "danger": "danger_filled"}
    return {
        "tag": "button",
        "type": type_map.get(btn_type, btn_type or "default"),
        "width": "fill",
        "text": _plain_text(label),
        "behaviors": [{"type": "open_url", "default_url": url}],
    }


def _callback_value_object(value: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, raw in value.items():
        key = str(key or "").strip()
        if not key or raw is None:
            continue
        if isinstance(raw, (str, bool, int, float)):
            out[key] = raw
        else:
            out[key] = str(raw)
    return out


def _format_form_fields(fields: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for item in fields:
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label or not value:
            continue
        if len(value) > 500:
            value = value[:500] + "..."
        lines.append(f"- **{label}：**{value}")
    return "\n".join(lines)


def _approval_result_markdown(status: str) -> str:
    mapping = {
        "approved": "**审批结果：**已通过",
        "rejected": "**审批结果：**已驳回",
        "revoked": "**审批结果：**申请人已撤销",
    }
    return mapping.get(status, "")


def _build_body(
    *,
    initiator: str,
    summary: str,
    serial_no: str,
    title: str,
    level_name: str,
    form_fields: list[dict[str, str]],
    result_message: str = "",
    result_status: str = "",
) -> str:
    parts = [
        f"**申请人：**{initiator or '-'}",
        f"**摘要：**{summary or title or '-'}",
        f"**流程编号：**{serial_no or '-'}",
        f"**当前节点：**{level_name or '-'}",
    ]
    body = "\n".join(parts)
    section = _format_form_fields(form_fields)
    if section:
        body += "\n\n**申请内容**\n" + section
    if result_message.strip():
        body += "\n\n" + result_message.strip()
    elif result_status.strip():
        body += "\n\n" + _approval_result_markdown(result_status)
    return body


def _button_row(buttons: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tag": "column_set",
        "flex_mode": "flow",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "center",
                "elements": [btn],
            }
            for btn in buttons
        ],
    }


def build_approval_card(
    *,
    header_title: str = "",
    title: str = "",
    initiator: str = "",
    serial_no: str = "",
    level_name: str = "",
    summary: str = "",
    form_fields: list[dict[str, str]] | None = None,
    approve_token: str = "",
    reject_token: str = "",
    approve_url: str = "",
    reject_url: str = "",
    app_namespace: str = "",
    clicked_action: str = "",
    result_status: str = "",
    result_message: str = "",
) -> dict[str, Any]:
    header = header_title.strip() or level_name.strip() or "Zadig Agent 审批待办"
    body_text = _build_body(
        initiator=initiator,
        summary=summary,
        serial_no=serial_no,
        title=title,
        level_name=level_name,
        form_fields=form_fields or [],
        result_message=result_message,
        result_status=result_status,
    )
    elements: list[dict[str, Any]] = [{"tag": "markdown", "content": body_text}]
    actions: list[dict[str, Any]] = []
    if clicked_action.strip():
        approve_label = "已点击" if clicked_action == "approve" else "审批通过"
        reject_label = "已点击" if clicked_action == "reject" else "拒绝"
        actions = [_disabled_button(approve_label), _disabled_button(reject_label)]
    elif result_status.strip() == "revoked":
        actions = [_disabled_button("审批通过"), _disabled_button("拒绝")]
    elif not result_status.strip():
        if approve_token:
            actions.append(
                _callback_button(
                    "审批通过",
                    "primary",
                    {"action": "approve", "token": approve_token},
                    app=app_namespace,
                )
            )
        elif approve_url:
            actions.append(_url_button("审批通过", "primary", approve_url))
        if reject_token:
            actions.append(
                _callback_button(
                    "拒绝",
                    "danger",
                    {"action": "reject", "token": reject_token},
                    app=app_namespace,
                )
            )
        elif reject_url:
            actions.append(_url_button("拒绝", "danger", reject_url))
    if actions:
        elements.append(_button_row(actions))
    elements.extend([{"tag": "hr"}, {"tag": "markdown", "content": "来自 Zadig Agent"}])
    template = "purple"
    if result_status == "approved":
        template = "green"
    elif result_status == "rejected":
        template = "red"
    elif result_status == "revoked":
        template = "grey"
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {"title": _plain_text(header), "template": template},
        "body": {"elements": elements},
    }


def build_status_card(
    *,
    header_title: str,
    body: str,
    view_url: str = "",
    primary_label: str = "查看详情",
    template: str = "blue",
) -> dict[str, Any]:
    elements: list[dict[str, Any]] = [{"tag": "markdown", "content": body.strip()}]
    if view_url.strip():
        elements.append(_button_row([_url_button(primary_label, "primary", view_url.strip())]))
    elements.extend([{"tag": "hr"}, {"tag": "markdown", "content": "来自 Zadig Agent"}])
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {"title": _plain_text(header_title), "template": template},
        "body": {"elements": elements},
    }


def build_cc_card(
    *,
    header_title: str,
    title: str,
    initiator: str,
    serial_no: str,
    level_name: str,
    summary: str,
    view_url: str,
) -> dict[str, Any]:
    body = _build_body(
        initiator=initiator,
        summary=summary,
        serial_no=serial_no,
        title=title,
        level_name=level_name,
        form_fields=[],
    )
    body += "\n\n您已被抄送，请知悉。"
    return build_status_card(
        header_title=header_title or "审批抄送",
        body=body,
        view_url=view_url,
        primary_label="查看",
        template="purple",
    )


def format_card_callback_response(
    toast_type: str,
    toast_content: str,
    card: dict[str, Any] | None,
    *,
    v1: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if toast_content.strip():
        out["toast"] = {"type": toast_type.strip() or "info", "content": toast_content.strip()}
    if card is not None:
        out["card"] = card if v1 else {"type": "raw", "data": card}
    return out


def marshal_interactive_card(card: dict[str, Any]) -> str:
    raw = json.dumps(card, ensure_ascii=False)
    return raw

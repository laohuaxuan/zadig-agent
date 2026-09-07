"""飞书卡片回调与 URL 审批路由。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from utils.config import feishu_config
from webapi.approval_action import ApprovalActionOutcome, build_outcome_card, run_approval_action_from_token
from webapi.approval_tokens import infer_approval_token_app
from webapi.feishu_app import feishu_app_namespace, feishu_peer_base_url
from webapi.feishu_callback import callback_verification_token, parse_callback_body, parse_card_action_event
from webapi.feishu_cards import format_card_callback_response
from webapi.workflow_notify import schedule_approval_notifications

logger = logging.getLogger(__name__)
router = APIRouter()

_inflight: dict[str, float] = {}
_INFLIGHT_TTL = 120.0
_PROCESS_HEADER = "x-feishu-callback-process"


def _resolve_callback_target_app(event_app: str, token: str, cfg: dict[str, Any]) -> str:
    app = str(event_app or "").strip()
    if app:
        return app
    inferred = infer_approval_token_app(token)
    if inferred:
        return inferred
    return feishu_app_namespace(cfg)


def _peer_approval_action_url(cfg: dict[str, Any], target_app: str, token: str) -> str:
    peer = feishu_peer_base_url(cfg, target_app)
    text = str(token or "").strip()
    if not peer or not text:
        return ""
    from urllib.parse import quote

    return f"{peer.rstrip('/')}/api/feishu/approval/action?token={quote(text)}"


def _ack_json(payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=payload, status_code=200)


def _begin_job(key: str) -> bool:
    now = time.time()
    expired = [item for item, ts in _inflight.items() if now - ts > _INFLIGHT_TTL]
    for item in expired:
        _inflight.pop(item, None)
    if not key:
        return True
    if key in _inflight:
        return False
    _inflight[key] = now
    return True


async def _forward_feishu_callback(peer_base: str, raw: bytes, headers: Any) -> JSONResponse:
    url = f"{peer_base.rstrip('/')}/api/feishu/card/callback/process"
    forward_headers = {
        "Content-Type": str(headers.get("content-type") or "application/json"),
        _PROCESS_HEADER: "1",
    }
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, content=raw, headers=forward_headers)
        data = resp.json()
        if isinstance(data, dict):
            return _ack_json(data)
    except Exception as exc:
        logger.warning("feishu card callback forward to %s failed: %s", url, exc)
    return _ack_json(format_card_callback_response("error", "审批服务暂时不可用，请登录平台处理", None))


async def _handle_feishu_card_callback(request: Request, *, skip_route: bool) -> JSONResponse:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return _ack_json({})

    raw = await request.body()
    if not raw:
        return _ack_json(format_card_callback_response("info", "正在处理", None))

    try:
        plain = raw.decode("utf-8").strip()
        if plain.startswith("{") and '"challenge"' in plain:
            data = json.loads(plain)
            challenge = str(data.get("challenge") or "").strip()
            if challenge:
                return _ack_json({"challenge": challenge})
    except json.JSONDecodeError:
        pass

    cfg = feishu_config()
    try:
        payload, _encrypted = parse_callback_body(str(cfg.get("encrypt_key") or ""), raw)
    except Exception as exc:
        logger.warning("feishu card callback parse: %s", exc)
        return _ack_json(format_card_callback_response("info", "正在处理", None))

    challenge = str(payload.get("challenge") or "").strip()
    if challenge:
        return _ack_json({"challenge": challenge})

    verify = str(cfg.get("verification_token") or "").strip()
    if verify:
        got = callback_verification_token(payload)
        if got and got != verify:
            logger.warning("feishu card callback invalid verification token")
            return _ack_json(format_card_callback_response("info", "正在处理", None))

    try:
        event = parse_card_action_event(payload)
    except ValueError as exc:
        if str(exc) == "challenge":
            return _ack_json(format_card_callback_response("info", "正在处理", None))
        logger.warning("feishu card callback event: %s", exc)
        return _ack_json(format_card_callback_response("info", "正在处理", None))

    if event.action not in {"approve", "reject"}:
        return _ack_json({})

    local_app = feishu_app_namespace(cfg)
    target_app = _resolve_callback_target_app(event.app, event.token, cfg)
    if not skip_route and target_app and target_app != local_app:
        peer = feishu_peer_base_url(cfg, target_app)
        if peer:
            logger.info(
                "feishu card callback route %s -> %s action=%s message_id=%s",
                local_app,
                target_app,
                event.action,
                event.open_message_id,
            )
            return await _forward_feishu_callback(peer, raw, request.headers)
        return _ack_json(
            format_card_callback_response(
                "error",
                f"该审批属于 {target_app}，请前往对应平台处理",
                None,
                v1=event.v1,
            )
        )

    job_key = f"{event.action}:{event.token or event.open_message_id}"
    if not _begin_job(job_key):
        return _ack_json(format_card_callback_response("info", "正在处理", None, v1=event.v1))

    outcome = run_approval_action_from_token(
        event.token,
        action=event.action,
        open_id=event.open_id,
        notify_now=False,
    )
    card = build_outcome_card(outcome.instance_id, outcome)
    response = format_card_callback_response(
        outcome.toast_type or "info",
        outcome.toast_message or "正在处理",
        card,
        v1=event.v1,
    )

    async def _deferred_notify() -> None:
        schedule_approval_notifications({**outcome.__dict__, "notify_now": False})

    asyncio.create_task(_deferred_notify())
    return _ack_json(response)


@router.api_route("/api/feishu/card/callback", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def feishu_card_callback(request: Request) -> JSONResponse:
    return await _handle_feishu_card_callback(request, skip_route=False)


@router.api_route("/api/feishu/card/callback/process", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def feishu_card_callback_process(request: Request) -> JSONResponse:
    if request.headers.get(_PROCESS_HEADER) != "1":
        return _ack_json(format_card_callback_response("error", "无效回调", None))
    return await _handle_feishu_card_callback(request, skip_route=True)


@router.get("/api/feishu/approval/action", response_class=HTMLResponse)
def feishu_approval_action(token: str = "") -> HTMLResponse | RedirectResponse:
    cfg = feishu_config()
    local_app = feishu_app_namespace(cfg)
    target_app = _resolve_callback_target_app("", token, cfg)
    if target_app and target_app != local_app:
        redirect_url = _peer_approval_action_url(cfg, target_app, token)
        if redirect_url:
            logger.info("feishu approval action redirect %s -> %s", local_app, target_app)
            return RedirectResponse(url=redirect_url, status_code=307)
    outcome = run_approval_action_from_token(token, notify_now=True)
    title = outcome.page_title or "审批结果"
    message = outcome.page_message or outcome.toast_message or "处理完成"
    status_code = 200 if outcome.http_status == 200 else 400
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;display:grid;place-items:center;min-height:100vh;background:#f5f6f8;margin:0}}
.card{{background:#fff;border-radius:12px;padding:32px 40px;box-shadow:0 8px 24px rgba(0,0,0,.08);max-width:420px;text-align:center}}
h1{{margin:0 0 12px;font-size:22px}}p{{margin:0;color:#555;line-height:1.6}}</style></head>
<body><div class="card"><h1>{title}</h1><p>{message}</p></div></body></html>"""
    return HTMLResponse(content=html, status_code=status_code)

"""平台认证、用户、审批流等 API。"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from webapi.applications import stream_application_execution, submit_application, submit_execution_reply, sync_application_status
from webapi.approval_action import run_approval_action
from webapi.approval_templates import create_template, delete_template, get_template, list_templates, update_template
from webapi.feishu_client import FeishuClient
from webapi.platform_auth import issue_token, parse_token, token_max_age_seconds, verify_password
from webapi.platform_permissions import (
    build_permissions,
    can_modify_approval_config,
    can_view_approval_config,
)
from webapi.platform_roles import (
    WORKFLOW_TYPE_HELM_PROJECT,
    can_manage_users,
    can_modify_users,
)
from webapi.platform_users import (
    authenticate_local,
    create_local_user,
    delete_user,
    ensure_feishu_user,
    get_user_by_id,
    map_users_by_feishu_open_ids,
    list_approver_candidates,
    list_users,
    reset_user_password,
    update_own_profile,
    update_user,
    update_user_status,
    write_audit,
)
from webapi.workflows import get_counts, get_instance_detail, list_tasks, revoke_instance

router = APIRouter()
_feishu = FeishuClient()
AUTH_COOKIE = "zadig_auth_token"
OAUTH_STATE_COOKIE = "feishu_oauth_state"


class CurrentUser(BaseModel):
    user_id: int
    username: str
    role: str


class LocalLoginBody(BaseModel):
    name: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RootLoginBody(LocalLoginBody):
    """兼容旧客户端。"""


class PlatformUserBody(BaseModel):
    name: str = ""
    display_name: str = ""
    phone: str = ""
    email: str = ""
    password: str = ""
    role: str = "watcher"
    status: str = "active"


class UpdateProfileBody(BaseModel):
    phone: str | None = None
    email: str | None = None
    new_password: str = ""
    confirm_password: str = ""


class UserStatusBody(BaseModel):
    status: str = Field(min_length=1)


class ApprovalTemplateBody(BaseModel):
    name: str = Field(min_length=1)
    workflow_type: str = WORKFLOW_TYPE_HELM_PROJECT
    enabled: bool = True
    is_default: bool = False
    levels: list[dict[str, Any]] = Field(default_factory=list)


class FeishuEnsureBody(BaseModel):
    open_id: str = Field(min_length=1)
    name: str = ""
    display_name: str = ""
    email: str = ""
    phone: str = ""


class ApplicationSubmitBody(BaseModel):
    payload: dict[str, Any]


class WorkflowActionBody(BaseModel):
    task_id: int = 0
    comment: str = ""


class ExecuteReplyBody(BaseModel):
    message: str = Field(min_length=1)


def _extract_token(request: Request) -> str:
    auth = str(request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = str(request.headers.get("X-Access-Token") or "").strip()
    if header:
        return header
    return str(request.cookies.get(AUTH_COOKIE) or request.query_params.get("feishu_token") or "").strip()


def get_current_user(request: Request) -> CurrentUser:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        claims = parse_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = get_user_by_id(int(claims["user_id"]))
    if not user or str(user.get("status") or "") == "disabled":
        raise HTTPException(status_code=401, detail="账号不可用")
    return CurrentUser(user_id=int(user["id"]), username=str(user["name"]), role=str(user["role"]))


def require_roles(*roles: str):
    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="无权访问")
        return user

    return _dep


def _set_auth_cookie(response: Response, token: str, request: Request | None = None) -> None:
    secure = False
    if request is not None:
        scheme = str(request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
        secure = scheme == "https"
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=token_max_age_seconds(),
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )


def _public_base_url(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


@router.get("/api/auth/providers")
def auth_providers() -> dict[str, Any]:
    return {
        "ok": True,
        "feishu_enabled": _feishu.enabled(),
        "local_login_enabled": True,
        "root_login_enabled": True,
    }


@router.get("/api/login/feishu")
async def login_feishu(request: Request) -> RedirectResponse:
    if not _feishu.enabled():
        raise HTTPException(status_code=404, detail="飞书登录未启用")
    state = secrets.token_hex(16)
    redirect_uri = _feishu.oauth_redirect_uri(_public_base_url(request))
    url = _feishu.authorize_url(state, redirect_uri)
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax", path="/")
    return response


@router.get("/api/login/feishu/callback")
async def login_feishu_callback(request: Request, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    front = _feishu.cfg.get("app_base_url") or _public_base_url(request)
    if error:
        return RedirectResponse(f"{front}/login?feishu_error={error}")
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE) or ""
    if not cookie_state or cookie_state != state:
        return RedirectResponse(f"{front}/login?feishu_error=飞书登录状态无效")
    try:
        info = await _feishu.exchange_oauth_code(code)
        user, created = ensure_feishu_user(info)
        if str(user.get("status") or "") == "disabled":
            return RedirectResponse(f"{front}/login?feishu_error=账号已禁用")
        token = issue_token(user)
    except Exception as exc:
        return RedirectResponse(f"{front}/login?feishu_error={exc}")
    write_audit(
        user_id=user["id"],
        username=user["name"],
        display_name=user.get("display_name") or user["name"],
        action="login_feishu",
        result="success",
        ip=request.client.host if request.client else "",
        detail="created watcher" if created else "feishu login",
    )
    response = RedirectResponse(f"{front}/?feishu_token={token}", status_code=302)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    _set_auth_cookie(response, token, request)
    return response


def _user_item_with_permissions(user: dict[str, Any]) -> dict[str, Any]:
    return {**user, "permissions": build_permissions(str(user.get("role") or ""))}


def _login_local(body: LocalLoginBody, request: Request, response: Response, *, action: str) -> dict[str, Any]:
    user = authenticate_local(body.name, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = issue_token(user)
    _set_auth_cookie(response, token, request)
    write_audit(
        user_id=user["id"],
        username=user["name"],
        display_name=user.get("display_name") or user["name"],
        action=action,
        result="success",
        ip=request.client.host if request.client else "",
        detail=f"role={user.get('role') or ''}",
    )
    return {"ok": True, "token": token, "item": _user_item_with_permissions(user)}


@router.post("/api/login/local")
def login_local(body: LocalLoginBody, request: Request, response: Response) -> dict[str, Any]:
    return _login_local(body, request, response, action="login_local")


@router.post("/api/login/root")
def login_root(body: RootLoginBody, request: Request, response: Response) -> dict[str, Any]:
    return _login_local(body, request, response, action="login_root")


@router.get("/api/user-info")
def user_info(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    item = get_user_by_id(user.user_id)
    if not item:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "ok": True,
        "item": _user_item_with_permissions(item),
    }


@router.put("/api/user-profile")
def update_user_profile(
    body: UpdateProfileBody,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        item = update_own_profile(user.user_id, body.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_audit(
        user_id=user.user_id,
        username=user.username,
        display_name=item.get("display_name") or user.username,
        action="update_profile",
        result="success",
        ip=request.client.host if request.client else "",
        detail="",
    )
    return {
        "ok": True,
        "display_name": item.get("display_name") or "",
        "phone": item.get("phone") or "",
        "email": item.get("email") or "",
        "item": item,
    }


@router.post("/api/logout")
def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(AUTH_COOKIE, path="/")
    return {"ok": True}


@router.get("/api/platform/users")
def api_list_platform_users(
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not can_manage_users(user.role):
        raise HTTPException(status_code=403, detail="无权查看用户")
    items, total = list_users(page, page_size, keyword)
    return {"ok": True, "items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/api/platform/users/approver-candidates")
def api_approver_candidates(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    if not can_view_approval_config(user.role):
        raise HTTPException(status_code=403, detail="无权访问")
    return {"ok": True, "items": list_approver_candidates()}


@router.post("/api/platform/users")
def api_create_platform_user(body: PlatformUserBody, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    try:
        item = create_local_user(body.model_dump(), user.role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": item}


@router.put("/api/platform/users/{user_id}")
def api_update_platform_user(user_id: int, body: PlatformUserBody, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    try:
        item = update_user(user_id, body.model_dump(), user.role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "item": item}


@router.put("/api/platform/users/{user_id}/status")
def api_update_platform_user_status(
    user_id: int,
    body: UserStatusBody,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        item = update_user_status(user_id, body.status, user.role, user.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": item}


@router.delete("/api/platform/users/{user_id}")
def api_delete_platform_user(user_id: int, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    try:
        delete_user(user_id, user.role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/api/platform/users/{user_id}/reset-password")
def api_reset_password(user_id: int, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    try:
        password = reset_user_password(user_id, user.role)
    except (PermissionError, ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "password": password}


def _can_use_feishu_directory(role: str) -> bool:
    return can_manage_users(role) or can_view_approval_config(role)


@router.get("/api/feishu/users")
async def api_feishu_users(q: str = "", page_size: int = 20, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    if not _can_use_feishu_directory(user.role):
        raise HTTPException(status_code=403, detail="无权访问")
    try:
        result = await _feishu.list_contact_users(q, page_size)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    items = []
    open_ids: list[str] = []
    for raw in result.get("items") or []:
        if not isinstance(raw, dict):
            continue
        open_id = str(raw.get("open_id") or "").strip()
        item = {
            "open_id": open_id,
            "name": raw.get("name") or "",
            "display_name": raw.get("name") or "",
            "email": raw.get("email") or "",
            "mobile": raw.get("mobile") or "",
            "phone": raw.get("mobile") or "",
            "source": "feishu",
            "auth_source": "feishu",
        }
        if open_id:
            open_ids.append(open_id)
        items.append(item)
    linked = map_users_by_feishu_open_ids(open_ids)
    for item in items:
        open_id = str(item.get("open_id") or "")
        if open_id and open_id in linked:
            item["user_id"] = linked[open_id]
    return {
        "ok": True,
        "items": items,
        "warning": str(result.get("warning") or ""),
        "cached": bool(result.get("cached")),
    }


@router.post("/api/feishu/warmup")
async def api_feishu_warmup(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    if not _can_use_feishu_directory(user.role):
        raise HTTPException(status_code=403, detail="无权访问")
    if not _feishu.enabled():
        raise HTTPException(status_code=400, detail="飞书 Open API 未配置")
    _feishu.warmup_contact_users_async()
    return {"ok": True, "message": "warmup started"}


@router.post("/api/feishu/users/ensure")
def api_feishu_users_ensure(body: FeishuEnsureBody, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    if not _can_use_feishu_directory(user.role):
        raise HTTPException(status_code=403, detail="无权访问")
    platform_user, _ = ensure_feishu_user(
        {
            "open_id": body.open_id.strip(),
            "name": body.name.strip(),
            "display_name": (body.display_name or body.name).strip(),
            "email": body.email.strip(),
            "mobile": body.phone.strip(),
        }
    )
    return {"ok": True, "user_id": int(platform_user["id"])}


@router.get("/api/approval-templates")
def api_list_approval_templates(workflow_type: str = WORKFLOW_TYPE_HELM_PROJECT, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    if not can_view_approval_config(user.role):
        raise HTTPException(status_code=403, detail="无权查看审批配置")
    return {"ok": True, "items": list_templates(workflow_type)}


@router.get("/api/approval-templates/{template_id}")
def api_get_approval_template(template_id: int, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    if not can_view_approval_config(user.role):
        raise HTTPException(status_code=403, detail="无权查看审批配置")
    try:
        item = get_template(template_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "item": item}


@router.post("/api/approval-templates")
def api_create_approval_template(body: ApprovalTemplateBody, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    if not can_modify_approval_config(user.role):
        raise HTTPException(status_code=403, detail="无权配置审批流")
    return {"ok": True, "item": create_template(body.model_dump())}


@router.put("/api/approval-templates/{template_id}")
def api_update_approval_template(template_id: int, body: ApprovalTemplateBody, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    if not can_modify_approval_config(user.role):
        raise HTTPException(status_code=403, detail="无权配置审批流")
    try:
        item = update_template(template_id, body.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "item": item}


@router.delete("/api/approval-templates/{template_id}")
def api_delete_approval_template(template_id: int, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    if not can_modify_approval_config(user.role):
        raise HTTPException(status_code=403, detail="无权配置审批流")
    delete_template(template_id)
    return {"ok": True}


@router.post("/api/applications")
async def api_submit_application(body: ApplicationSubmitBody, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    try:
        item = await submit_application(body.payload, user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "item": item}


@router.get("/api/workflows/counts")
def api_workflow_counts(user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return {"ok": True, **get_counts(user.user_id)}


@router.get("/api/workflows/tasks")
def api_workflow_tasks(
    box: str = "todo",
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    items, total = list_tasks(user.user_id, box, page, page_size, keyword)
    return {"ok": True, "items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/api/workflows/instances/{instance_id}")
def api_workflow_instance(instance_id: int, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return {"ok": True, **get_instance_detail(instance_id, user.user_id)}


@router.post("/api/workflows/instances/{instance_id}/approve")
async def api_workflow_approve(instance_id: int, body: WorkflowActionBody, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    task_id = body.task_id
    if not task_id:
        from utils.db import query_one
        from webapi.workflows import TASK_PENDING

        pending = query_one(
            """
            SELECT id FROM workflow_tasks
            WHERE instance_id = %s AND assignee_id = %s AND status = %s
            ORDER BY id ASC LIMIT 1
            """,
            (instance_id, user.user_id, TASK_PENDING),
        )
        task_id = int(pending["id"]) if pending else 0
    if not task_id:
        raise HTTPException(status_code=400, detail="无待办任务")
    outcome = run_approval_action(instance_id, task_id, user.user_id, "approve", comment=body.comment, notify_now=True)
    if outcome.http_status != 200:
        raise HTTPException(status_code=outcome.http_status, detail=outcome.toast_message or outcome.page_message)
    return {"ok": True, "completed": outcome.final_approved}


@router.get("/api/workflows/instances/{instance_id}/execute/stream")
async def api_workflow_execute_stream(instance_id: int, user: CurrentUser = Depends(get_current_user)) -> StreamingResponse:
    import json

    async def event_stream():
        try:
            async for event in stream_application_execution(instance_id, user.user_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except (LookupError, PermissionError, ValueError) as exc:
            payload = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/api/workflows/instances/{instance_id}/execute/reply")
async def api_workflow_execute_reply(
    instance_id: int,
    body: ExecuteReplyBody,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        await submit_execution_reply(instance_id, user.user_id, body.message)
    except (LookupError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/api/workflows/instances/{instance_id}/reject")
def api_workflow_reject(instance_id: int, body: WorkflowActionBody, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    task_id = body.task_id
    if not task_id:
        from utils.db import query_one
        from webapi.workflows import TASK_PENDING

        pending = query_one(
            """
            SELECT id FROM workflow_tasks
            WHERE instance_id = %s AND assignee_id = %s AND status = %s
            ORDER BY id ASC LIMIT 1
            """,
            (instance_id, user.user_id, TASK_PENDING),
        )
        task_id = int(pending["id"]) if pending else 0
    if not task_id:
        raise HTTPException(status_code=400, detail="无待办任务")
    outcome = run_approval_action(instance_id, task_id, user.user_id, "reject", comment=body.comment, notify_now=True)
    if outcome.http_status != 200:
        raise HTTPException(status_code=outcome.http_status, detail=outcome.toast_message or outcome.page_message)
    return {"ok": True}


@router.post("/api/workflows/instances/{instance_id}/revoke")
def api_workflow_revoke(instance_id: int, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    try:
        revoke_instance(instance_id, user.user_id)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sync_application_status(instance_id, "revoked")
    schedule_revoke_notifications(instance_id)
    return {"ok": True}

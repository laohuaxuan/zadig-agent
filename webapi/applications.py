"""Helm 项目申请与审批后执行。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from tools.file_saver import clear_thread_checkpoints, has_checkpoint, resolve_checkpoints_path
from utils.db import _now, execute, query, query_one
from utils.llm_errors import format_llm_error
from webapi.agent_runner import (
    build_project_url,
    format_agent_meta_line,
    format_execution_footer,
    get_agent_meta,
    run_project_create_agent,
)
from webapi.agent_resources import public_execution_context, resolve_execution_resources
from webapi.platform_users import get_user_by_id, new_record_id
from webapi.platform_roles import (
    WORKFLOW_TYPE_ADD_ENVIRONMENT,
    WORKFLOW_TYPE_ADD_SERVICE,
    WORKFLOW_TYPE_ADD_WORKFLOW,
    WORKFLOW_TYPE_HELM_PROJECT,
)
from webapi.workflows import STATUS_COMPLETED, STATUS_REJECTED, STATUS_REVOKED, bump_initiator_notify, create_helm_project_workflow
from webapi.workflow_notify import schedule_submit_notifications
from webapi.zadig_meta import build_application_plan

_EXECUTABLE_STATUSES = {"待执行", "已通过", "失败"}
_ACTIVE_DUPLICATE_STATUSES = ("待审批", "待执行", "执行中")
_execution_input_queues: dict[int, asyncio.Queue[str]] = {}


@dataclass
class _ExecutionSession:
    task: asyncio.Task[Any]
    event_queues: list[asyncio.Queue[tuple[str, Any]]] = field(default_factory=list)
    input_queue: asyncio.Queue[str] | None = None


_execution_sessions: dict[int, _ExecutionSession] = {}


def execution_thread_id(instance_id: int, execution_context: dict[str, Any] | None = None) -> str:
    if execution_context:
        thread_id = str(execution_context.get("checkpoint_thread_id") or "").strip()
        if thread_id:
            return thread_id
    return str(instance_id)


def has_resumable_checkpoint(instance_id: int, execution_context: dict[str, Any] | None = None) -> bool:
    return has_checkpoint(execution_thread_id(instance_id, execution_context))


def is_execution_awaiting_input(instance_id: int) -> bool:
    return int(instance_id) in _execution_input_queues


def is_execution_running(instance_id: int) -> bool:
    session = _execution_sessions.get(instance_id)
    return session is not None and not session.task.done()


def _payload_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _assert_no_duplicate_application(payload: dict[str, Any]) -> None:
    app_type = str(payload.get("application_type") or "create_project").strip()
    project_key = str(payload.get("project_key") or "").strip()
    service_name = str(payload.get("service_name") or "").strip()
    environment = str(payload.get("environment") or "").strip()
    workflow_name = str(payload.get("workflow_name") or "").strip()
    if not project_key:
        return

    rows = query(
        """
        SELECT approval_status, payload_json
        FROM project_applications
        WHERE project_key = %s AND approval_status IN (%s, %s, %s)
        ORDER BY id DESC
        """,
        (project_key, *_ACTIVE_DUPLICATE_STATUSES),
    )
    for row in rows:
        item = _payload_dict(row.get("payload_json"))
        item_type = str(item.get("application_type") or "create_project").strip()
        if item_type != app_type:
            continue
        if app_type == "add_service":
            if str(item.get("service_name") or "").strip() != service_name:
                continue
            if str(item.get("environment") or "").strip() != environment:
                continue
            status = str(row.get("approval_status") or "")
            raise ValueError(
                f"已存在相同添加服务申请（{project_key} / {service_name} / {environment}），"
                f"当前状态：{status}，请勿重复提交"
            )
        if app_type == "add_workflow":
            if str(item.get("workflow_name") or "").strip() != workflow_name:
                continue
            status = str(row.get("approval_status") or "")
            raise ValueError(
                f"已存在相同添加工作流申请（{project_key} / {workflow_name}），"
                f"当前状态：{status}，请勿重复提交"
            )
        if app_type == "add_environment":
            if str(item.get("environment") or "").strip() != environment:
                continue
            if bool(item.get("environment_production")) != bool(payload.get("environment_production")):
                continue
            status = str(row.get("approval_status") or "")
            env_type = "生产环境" if payload.get("environment_production") else "测试环境"
            raise ValueError(
                f"已存在相同添加环境申请（{project_key} / {environment} / {env_type}），"
                f"当前状态：{status}，请勿重复提交"
            )
        if app_type == "create_project":
            status = str(row.get("approval_status") or "")
            raise ValueError(f"项目 {project_key} 已有进行中的创建申请（{status}），请勿重复提交")


def _public_application(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json")
    if isinstance(payload, str):
        payload = json.loads(payload)
    project_key = str(row.get("project_key") or "")
    project_url = str(row.get("project_url") or "").strip() or build_project_url(project_key)
    execution_context = row.get("execution_context_json")
    if isinstance(execution_context, str):
        execution_context = json.loads(execution_context or "null")
    if not isinstance(execution_context, dict):
        execution_context = None
    agent_meta = execution_context.get("agent") if execution_context else None
    return {
        "id": int(row["id"]),
        "record_id": row["record_id"],
        "initiator_id": int(row["initiator_id"]),
        "project_key": project_key,
        "project_name": row["project_name"],
        "payload": payload if isinstance(payload, dict) else {},
        "approval_status": row.get("approval_status") or "待审批",
        "process_message": row.get("process_message") or "",
        "execution_log": row.get("execution_log") or "",
        "project_url": project_url,
        "execution_context": execution_context,
        "agent_meta": agent_meta if isinstance(agent_meta, dict) else None,
        "workflow_instance_id": int(row["workflow_instance_id"]) if row.get("workflow_instance_id") else None,
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def get_application_by_record(record_id: str) -> dict[str, Any] | None:
    row = query_one("SELECT * FROM project_applications WHERE record_id = %s", (record_id,))
    return _public_application(row) if row else None


def get_application_by_instance(instance_id: int) -> dict[str, Any] | None:
    row = query_one("SELECT * FROM project_applications WHERE workflow_instance_id = %s", (instance_id,))
    return _public_application(row) if row else None


def can_execute_application(
    app: dict[str, Any] | None,
    *,
    initiator_id: int,
    workflow_status: str,
    instance_id: int = 0,
) -> bool:
    if not app or workflow_status != STATUS_COMPLETED:
        return False
    if int(app.get("initiator_id") or 0) != initiator_id:
        return False
    status = str(app.get("approval_status") or "")
    if status == "执行中":
        return False
    return status in _EXECUTABLE_STATUSES


def can_resume_application(
    app: dict[str, Any] | None,
    *,
    initiator_id: int,
    workflow_status: str,
    instance_id: int = 0,
) -> bool:
    if not app or workflow_status != STATUS_COMPLETED:
        return False
    if int(app.get("initiator_id") or 0) != initiator_id:
        return False
    if str(app.get("approval_status") or "") != "执行中":
        return False
    if is_execution_running(instance_id):
        return True
    execution_context = app.get("execution_context")
    if not isinstance(execution_context, dict):
        execution_context = None
    return has_resumable_checkpoint(instance_id, execution_context)


def _build_form_data(payload: dict[str, Any]) -> list[dict[str, str]]:
    app_type = str(payload.get("application_type") or "create_project").strip()
    if app_type == "add_service":
        return [
            {"label": "项目名称", "value": str(payload.get("project_name") or payload.get("project_key") or "")},
            {"label": "项目标识", "value": str(payload.get("project_key") or "")},
            {"label": "服务名称", "value": str(payload.get("service_name") or "")},
            {"label": "环境", "value": str(payload.get("environment") or "")},
            {
                "label": "环境类型",
                "value": "生产环境" if payload.get("environment_production") else "测试环境",
            },
            {"label": "工作流名称", "value": str(payload.get("workflow_name") or "")},
            {"label": "集群", "value": str(payload.get("cluster_name") or "")},
            {"label": "命名空间", "value": str(payload.get("namespace") or "")},
            {"label": "代码库", "value": str(payload.get("repo_name") or "")},
            {"label": "分支", "value": str(payload.get("branch") or "")},
        ]
    if app_type == "add_workflow":
        deploy_type = "生产环境" if payload.get("deploy_production") else "测试环境"
        return [
            {"label": "项目名称", "value": str(payload.get("project_name") or payload.get("project_key") or "")},
            {"label": "项目标识", "value": str(payload.get("project_key") or "")},
            {"label": "环境", "value": str(payload.get("environment") or "")},
            {"label": "工作流名称", "value": str(payload.get("workflow_name") or "")},
            {"label": "镜像仓库", "value": str(payload.get("registry_label") or payload.get("registry_id") or "")},
            {"label": "服务组件", "value": str(payload.get("service_name") or "")},
            {"label": "部署环境类型", "value": deploy_type},
            {"label": "部署环境", "value": str(payload.get("deploy_env_name") or "")},
        ]
    if app_type == "add_environment":
        return [
            {"label": "项目名称", "value": str(payload.get("project_name") or payload.get("project_key") or "")},
            {"label": "项目标识", "value": str(payload.get("project_key") or "")},
            {
                "label": "环境类型",
                "value": "生产环境" if payload.get("environment_production") else "测试环境",
            },
            {"label": "环境名称", "value": str(payload.get("environment") or "")},
            {"label": "集群", "value": str(payload.get("cluster_name") or "")},
            {"label": "命名空间", "value": str(payload.get("namespace") or "")},
            {"label": "镜像仓库", "value": str(payload.get("registry_label") or payload.get("registry_id") or "")},
        ]
    return [
        {"label": "项目名称", "value": str(payload.get("project_name") or "")},
        {"label": "项目标识", "value": str(payload.get("project_key") or "")},
        {"label": "服务名称", "value": str(payload.get("service_name") or "")},
        {
            "label": "环境类型",
            "value": "生产环境" if payload.get("environment_production") else "测试环境",
        },
        {"label": "环境名称", "value": str(payload.get("environment") or "")},
        {"label": "工作流名称", "value": str(payload.get("workflow_name") or "")},
        {"label": "集群", "value": str(payload.get("cluster_name") or "")},
        {"label": "命名空间", "value": str(payload.get("namespace") or "")},
        {"label": "代码库", "value": str(payload.get("repo_name") or "")},
        {"label": "分支", "value": str(payload.get("branch") or "")},
    ]


async def submit_application(payload: dict[str, Any], initiator_id: int) -> dict[str, Any]:
    app_type = str(payload.get("application_type") or "create_project").strip()
    _assert_no_duplicate_application({**payload, "application_type": app_type})
    plan = build_application_plan(payload)
    initiator = get_user_by_id(initiator_id)
    if not initiator:
        raise ValueError("发起人不存在")
    record_id = new_record_id()
    now = _now()
    project_key = str(plan.get("project_key") or payload.get("project_key") or "")
    project_name = str(payload.get("project_name") or project_key)
    summary = (
        f"{project_name} / {payload.get('workflow_name') or ''}"
        if app_type == "add_workflow"
        else f"{project_name} / {payload.get('environment') or ''}"
        if app_type == "add_environment"
        else f"{project_name} / {payload.get('service_name') or ''} / {payload.get('environment') or ''}"
    )
    form_data = _build_form_data({**payload, "application_type": app_type})
    if app_type == "add_workflow":
        workflow_type = WORKFLOW_TYPE_ADD_WORKFLOW
        title = f"Helm 添加工作流：{project_name} / {payload.get('workflow_name') or ''}"
    elif app_type == "add_service":
        workflow_type = WORKFLOW_TYPE_ADD_SERVICE
        title = f"Helm 添加服务：{project_name} / {payload.get('service_name') or ''}"
    elif app_type == "add_environment":
        workflow_type = WORKFLOW_TYPE_ADD_ENVIRONMENT
        title = f"Helm 添加环境：{project_name} / {payload.get('environment') or ''}"
    else:
        workflow_type = WORKFLOW_TYPE_HELM_PROJECT
        title = f"Helm 项目申请：{project_name}"
    instance_id, serial_no = create_helm_project_workflow(
        record_id=record_id,
        title=title,
        summary=summary,
        form_data=form_data,
        initiator_id=initiator_id,
        initiator_name=initiator.get("display_name") or initiator.get("name") or "",
        workflow_type=workflow_type,
    )
    execute(
        """
        INSERT INTO project_applications
        (record_id, initiator_id, project_key, project_name, payload_json, custom_fields_json,
         approval_status, workflow_instance_id, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record_id,
            initiator_id,
            project_key,
            project_name,
            json.dumps(payload, ensure_ascii=False),
            "{}",
            "待审批",
            instance_id,
            now,
            now,
        ),
    )
    row = query_one("SELECT * FROM project_applications WHERE record_id = %s", (record_id,))
    item = _public_application(row) if row else {}
    item["serial_no"] = serial_no
    item["workflow_instance_id"] = instance_id
    schedule_submit_notifications(instance_id)
    return item


def _load_payload(app: dict[str, Any]) -> dict[str, Any]:
    payload = app.get("payload_json") or app.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload if isinstance(payload, dict) else {}


def _append_execution_log(app_id: int, chunk: str) -> None:
    if not chunk:
        return
    execute(
        """
        UPDATE project_applications
        SET execution_log = CONCAT(COALESCE(execution_log, ''), %s), updated_at = %s
        WHERE id = %s
        """,
        (chunk, _now(), app_id),
    )


def _mark_execution_started(app_id: int, *, thread_id: str) -> None:
    now = _now()
    row = query_one("SELECT workflow_instance_id FROM project_applications WHERE id = %s", (app_id,))
    clear_thread_checkpoints(thread_id)
    execute(
        """
        UPDATE project_applications
        SET approval_status = %s, execution_log = '', process_message = '', project_url = '',
            execution_context_json = NULL, updated_at = %s
        WHERE id = %s
        """,
        ("执行中", now, app_id),
    )
    if row and row.get("workflow_instance_id"):
        bump_initiator_notify(int(row["workflow_instance_id"]))


def reconcile_stale_execution(instance_id: int) -> None:
    """无活跃执行会话且无可恢复 checkpoint 时，将僵死的「执行中」标记为失败。"""
    if instance_id in _execution_input_queues:
        return
    if is_execution_running(instance_id):
        return
    row = query_one(
        "SELECT id, approval_status, execution_context_json FROM project_applications WHERE workflow_instance_id = %s",
        (instance_id,),
    )
    if not row or str(row.get("approval_status") or "") != "执行中":
        return
    execution_context = row.get("execution_context_json")
    if isinstance(execution_context, str):
        try:
            execution_context = json.loads(execution_context or "null")
        except json.JSONDecodeError:
            execution_context = None
    if not isinstance(execution_context, dict):
        execution_context = None
    if has_resumable_checkpoint(instance_id, execution_context):
        return
    app_id = int(row["id"])
    _append_execution_log(app_id, "\n❌ 执行已中断，请重新执行\n")
    execute(
        """
        UPDATE project_applications
        SET approval_status = %s, process_message = %s, updated_at = %s
        WHERE id = %s
        """,
        ("失败", "执行已中断，请重新执行", _now(), app_id),
    )


def _validate_execute_request(instance_id: int, user_id: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    instance = query_one("SELECT * FROM workflow_instances WHERE id = %s", (instance_id,))
    if not instance:
        raise LookupError("流程不存在")
    if str(instance.get("status") or "") != STATUS_COMPLETED:
        raise ValueError("审批尚未完成，暂不能执行 Agent")
    app_row = query_one("SELECT * FROM project_applications WHERE workflow_instance_id = %s", (instance_id,))
    if not app_row:
        raise LookupError("未找到关联的项目申请")
    app = _public_application(app_row)
    if int(app["initiator_id"]) != user_id:
        raise PermissionError("仅申请人可执行 Agent")
    status = str(app.get("approval_status") or "")
    if status == "执行中":
        raise ValueError("Agent 正在执行中，请稍候")
    if status not in _EXECUTABLE_STATUSES:
        raise ValueError(f"当前状态「{status}」不可执行")
    return instance, app_row, app


def _validate_resume_request(instance_id: int, user_id: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    instance = query_one("SELECT * FROM workflow_instances WHERE id = %s", (instance_id,))
    if not instance:
        raise LookupError("流程不存在")
    if str(instance.get("status") or "") != STATUS_COMPLETED:
        raise ValueError("审批尚未完成，暂不能恢复 Agent")
    app_row = query_one("SELECT * FROM project_applications WHERE workflow_instance_id = %s", (instance_id,))
    if not app_row:
        raise LookupError("未找到关联的项目申请")
    app = _public_application(app_row)
    if int(app["initiator_id"]) != user_id:
        raise PermissionError("仅申请人可恢复 Agent")
    status = str(app.get("approval_status") or "")
    if status != "执行中":
        raise ValueError(f"当前状态「{status}」不可恢复")
    execution_context = app.get("execution_context")
    if not isinstance(execution_context, dict):
        execution_context = None
    if not is_execution_running(instance_id) and not has_resumable_checkpoint(instance_id, execution_context):
        raise ValueError("未找到可恢复的 Agent 会话")
    return instance, app_row, app


async def submit_execution_reply(instance_id: int, user_id: int, message: str) -> None:
    app = get_application_by_instance(instance_id)
    if not app:
        raise LookupError("未找到关联的项目申请")
    if int(app["initiator_id"]) != user_id:
        raise PermissionError("仅申请人可回复")
    queue = _execution_input_queues.get(instance_id)
    if not queue:
        session = _execution_sessions.get(instance_id)
        if session and session.input_queue is not None:
            queue = session.input_queue
    if not queue:
        raise ValueError("当前没有等待回复的执行会话，请先连接执行流")
    text = str(message or "").strip()
    if not text:
        raise ValueError("回复内容不能为空")
    await queue.put(text)


def _finalize_execution_success(
    app_id: int,
    *,
    summary: str,
    project_url: str,
    execution_context: dict[str, Any],
) -> None:
    row = query_one("SELECT workflow_instance_id FROM project_applications WHERE id = %s", (app_id,))
    execute(
        """
        UPDATE project_applications
        SET approval_status = %s, process_message = %s, project_url = %s,
            execution_context_json = %s, updated_at = %s
        WHERE id = %s
        """,
        (
            "已完成",
            summary,
            project_url,
            json.dumps(execution_context, ensure_ascii=False),
            _now(),
            app_id,
        ),
    )
    if row and row.get("workflow_instance_id"):
        bump_initiator_notify(int(row["workflow_instance_id"]))


def _finalize_execution_error(app_id: int, err: str) -> None:
    message = format_llm_error(str(err or "").strip() or "Agent 执行失败")
    row = query_one("SELECT workflow_instance_id FROM project_applications WHERE id = %s", (app_id,))
    _append_execution_log(app_id, f"\n❌ 执行失败：{message}\n")
    execute(
        """
        UPDATE project_applications
        SET approval_status = %s, process_message = %s, updated_at = %s
        WHERE id = %s
        """,
        ("失败", message, _now(), app_id),
    )
    if row and row.get("workflow_instance_id"):
        bump_initiator_notify(int(row["workflow_instance_id"]))


async def _broadcast_event(instance_id: int, kind: str, payload_item: Any) -> None:
    session = _execution_sessions.get(instance_id)
    if not session:
        return
    for queue in list(session.event_queues):
        await queue.put((kind, payload_item))


async def _attach_execution_stream(
    instance_id: int,
    *,
    app_id: int,
    app: dict[str, Any],
    payload: dict[str, Any],
    resume: bool,
) -> AsyncIterator[dict[str, Any]]:
    existing = _execution_sessions.get(instance_id)
    if existing and not existing.task.done():
        subscriber: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        existing.event_queues.append(subscriber)
        input_queue = existing.input_queue or asyncio.Queue()
        existing.input_queue = input_queue
        _execution_input_queues[instance_id] = input_queue
        agent_meta = get_agent_meta()
        execution_context = app.get("execution_context") if isinstance(app.get("execution_context"), dict) else None
        yield {
            "type": "meta",
            "resumed": True,
            "agent_meta": agent_meta,
            "execution_context": execution_context,
            "text": "已重新连接到进行中的 Agent 执行...\n",
        }
        try:
            while True:
                try:
                    kind, payload_item = await asyncio.wait_for(subscriber.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    if existing.task.done():
                        break
                    yield {"type": "ping"}
                    continue
                if kind == "log":
                    yield {"type": "log", "text": payload_item}
                elif kind == "input_required":
                    yield {"type": "input_required", "prompt": str(payload_item or "")}
                elif kind == "done":
                    result = payload_item
                    yield {
                        "type": "done",
                        "summary": str(result.get("summary") or "Agent 执行完成"),
                        "project_key": result.get("project_key") or app["project_key"],
                        "project_url": str(result.get("project_url") or ""),
                        "flow_status": "已完成",
                        "agent_meta": agent_meta,
                        "execution_context": result.get("execution_context") or execution_context,
                    }
                    break
                elif kind == "error":
                    err = str(payload_item)
                    yield {"type": "log", "text": f"\n❌ 执行失败：{err}\n"}
                    yield {"type": "error", "message": err, "flow_status": "失败"}
                    break
        finally:
            if subscriber in existing.event_queues:
                existing.event_queues.remove(subscriber)
            if not existing.event_queues:
                _execution_input_queues.pop(instance_id, None)
        return

    plan = build_application_plan(payload)
    execution_context = public_execution_context(resolve_execution_resources(payload, plan))
    agent_meta = get_agent_meta()
    execution_context["agent"] = agent_meta
    thread_id = execution_thread_id(instance_id, execution_context)
    execution_context["checkpoint_thread_id"] = thread_id

    if resume:
        saved_context = app.get("execution_context")
        if isinstance(saved_context, dict):
            execution_context = {**saved_context, **execution_context}
            execution_context["agent"] = agent_meta
            execution_context["checkpoint_thread_id"] = execution_thread_id(instance_id, saved_context)
            thread_id = execution_context["checkpoint_thread_id"]
        footer = format_execution_footer(agent_meta, execution_context)
        _append_execution_log(app_id, f"\n{footer}\n♻️ 恢复 Agent 执行（checkpoint: {resolve_checkpoints_path()}/{thread_id}）\n")
    else:
        _mark_execution_started(app_id, thread_id=thread_id)
        footer = format_execution_footer(agent_meta, execution_context)
        _append_execution_log(app_id, f"{footer}\n")

    execute(
        """
        UPDATE project_applications SET execution_context_json = %s, updated_at = %s WHERE id = %s
        """,
        (json.dumps(execution_context, ensure_ascii=False), _now(), app_id),
    )

    event_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    input_queue: asyncio.Queue[str] = asyncio.Queue()
    _execution_input_queues[instance_id] = input_queue

    async def log_fn(line: str) -> None:
        text = line if line.endswith("\n") else f"{line}\n"
        _append_execution_log(app_id, text)
        await event_queue.put(("log", text))
        await _broadcast_event(instance_id, "log", text)

    async def input_fn(prompt: str) -> str:
        await event_queue.put(("input_required", prompt))
        await _broadcast_event(instance_id, "input_required", prompt)
        return await input_queue.get()

    async def runner() -> None:
        try:
            result = await run_project_create_agent(
                payload,
                log_fn=log_fn,
                input_fn=input_fn,
                thread_id=thread_id,
                resume=resume,
            )
            project_url = str(
                result.get("project_url") or build_project_url(result.get("project_key") or app["project_key"])
            )
            summary = str(result.get("summary") or "Agent 执行完成")
            result_context = dict(result.get("execution_context") or execution_context)
            if execution_context.get("agent") and not result_context.get("agent"):
                result_context["agent"] = execution_context["agent"]
            _finalize_execution_success(
                app_id,
                summary=summary,
                project_url=project_url,
                execution_context=result_context,
            )
            payload_done = {
                **result,
                "project_url": project_url,
                "summary": summary,
                "execution_context": result_context,
            }
            await event_queue.put(("done", payload_done))
            await _broadcast_event(instance_id, "done", payload_done)
        except Exception as exc:
            err = str(exc).strip() or repr(exc)
            _finalize_execution_error(app_id, err)
            await event_queue.put(("error", err))
            await _broadcast_event(instance_id, "error", err)
        finally:
            _execution_input_queues.pop(instance_id, None)
            _execution_sessions.pop(instance_id, None)

    task = asyncio.create_task(runner())
    _execution_sessions[instance_id] = _ExecutionSession(task=task, event_queues=[event_queue], input_queue=input_queue)

    yield {
        "type": "meta",
        "resumed": resume,
        "agent_meta": agent_meta,
        "execution_context": execution_context,
        "text": footer if not resume else f"{footer}\n♻️ 恢复 Agent 执行...\n",
    }
    if not resume:
        yield {"type": "log", "text": "正在启动 Agent 执行...\n"}

    try:
        while True:
            try:
                kind, payload_item = await asyncio.wait_for(event_queue.get(), timeout=20.0)
            except asyncio.TimeoutError:
                if task.done():
                    break
                yield {"type": "ping"}
                continue
            if kind == "log":
                yield {"type": "log", "text": payload_item}
                continue
            if kind == "input_required":
                yield {"type": "input_required", "prompt": str(payload_item or "")}
                continue
            if kind == "done":
                result = payload_item
                project_url = str(result.get("project_url") or "")
                summary = str(result.get("summary") or "Agent 执行完成")
                result_context = result.get("execution_context") or execution_context
                yield {
                    "type": "done",
                    "summary": summary,
                    "project_key": result.get("project_key") or app["project_key"],
                    "project_url": project_url,
                    "flow_status": "已完成",
                    "agent_meta": agent_meta,
                    "execution_context": result_context,
                }
                break
            if kind == "error":
                err = str(payload_item)
                yield {"type": "log", "text": f"\n❌ 执行失败：{err}\n"}
                yield {"type": "error", "message": err, "flow_status": "失败"}
                break
    finally:
        session = _execution_sessions.get(instance_id)
        if session and event_queue in session.event_queues:
            session.event_queues.remove(event_queue)
        if session and not session.event_queues:
            _execution_input_queues.pop(instance_id, None)
        if not task.done():
            return
        await task


async def stream_application_execution(instance_id: int, user_id: int, *, resume: bool = False) -> AsyncIterator[dict[str, Any]]:
    if resume:
        _, app_row, app = _validate_resume_request(instance_id, user_id)
    else:
        _, app_row, app = _validate_execute_request(instance_id, user_id)

    app_id = int(app_row["id"])
    payload = _load_payload(app_row)
    async for event in _attach_execution_stream(
        instance_id,
        app_id=app_id,
        app=app,
        payload=payload,
        resume=resume,
    ):
        yield event


def sync_application_status(instance_id: int, workflow_status: str) -> None:
    mapping = {
        STATUS_REJECTED: "已驳回",
        STATUS_REVOKED: "已撤销",
        STATUS_COMPLETED: "待执行",
    }
    label = mapping.get(workflow_status)
    if not label:
        return
    execute(
        """
        UPDATE project_applications
        SET approval_status = %s, updated_at = %s
        WHERE workflow_instance_id = %s
        """,
        (label, _now(), instance_id),
    )
    if workflow_status in {STATUS_REJECTED, STATUS_COMPLETED}:
        bump_initiator_notify(instance_id)

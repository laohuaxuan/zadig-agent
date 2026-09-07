"""通过 Agent + Skill 执行项目创建等编排任务。"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from urllib.parse import urlparse

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from model.openrouter import get_openrouter_llm, new_llm_session_id
from tools.file_saver import FileSaver, has_checkpoint
from utils.llm_errors import format_llm_error
from utils.mcp import get_zadig_mcp_tools
from webapi.agent_resources import (
    format_execution_resources_log,
    format_execution_resources_meta_line,
    public_execution_context,
    resolve_execution_resources,
)
from webapi.settings import load_zadig
from webapi.zadig_meta import build_application_plan

_CONFIRM_MARKER = "[需要用户确认]"

LogCallback = Callable[[str], Awaitable[None] | None]
InputCallback = Callable[[str], Awaitable[str]]


def build_project_url(project_key: str) -> str:
    key = str(project_key or "").strip()
    if not key:
        return ""
    base = str(load_zadig().get("base_url") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/v1/projects/detail/{key}/detail"


def _infer_provider(base_url: str) -> str:
    host = (urlparse(str(base_url or "").strip()).hostname or "").lower()
    if not host:
        return "unknown"
    if "openrouter" in host:
        return "openrouter"
    if "anthropic" in host:
        return "anthropic"
    if "openai" in host:
        return "openai"
    if "deepseek" in host:
        return "deepseek"
    return host.split(".")[0] if "." in host else host


def get_agent_meta() -> dict[str, Any]:
    from utils.config import openrouter_config

    cfg = openrouter_config()
    name = str(cfg.get("name") or "zadig_bot").strip() or "zadig_bot"
    model = str(cfg.get("model") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    primary_model = str(cfg.get("primary_model") or model).strip()
    return {
        "id": str(cfg.get("id") or "").strip(),
        "name": name,
        "agent": name,
        "model": model,
        "primary_model": primary_model,
        "provider": _infer_provider(base_url),
        "base_url": base_url,
        "is_primary_model": bool(cfg.get("is_primary_model", True)),
        "is_default": bool(cfg.get("is_default")),
    }


def format_agent_meta_log(meta: dict[str, str] | None = None) -> str:
    item = meta or get_agent_meta()
    name = str(item.get("name") or item.get("agent") or "-").strip()
    lines = [
        "🤖 Agent 配置",
        "=" * 60,
        f"名称：{name}",
    ]
    agent_id = str(item.get("id") or "").strip()
    if agent_id:
        lines.append(f"标识：{agent_id}")
    lines.append(f"模型：{item.get('model') or '-'}")
    primary = str(item.get("primary_model") or "").strip()
    active = str(item.get("model") or "").strip()
    if primary and primary != active:
        lines.append(f"主模型：{primary}（当前已切换备用模型）")
    lines.extend(
        [
            f"提供商：{item.get('provider') or '-'}",
            f"API：{item.get('base_url') or '-'}",
        ]
    )
    if item.get("is_default"):
        lines.append("默认 Agent：是")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_agent_meta_line(meta: dict[str, str] | None = None) -> str:
    item = meta or get_agent_meta()
    name = str(item.get("name") or item.get("agent") or "zadig_bot").strip()
    parts = [f"Agent: {name}"]
    if item.get("id"):
        parts.append(f"ID: {item['id']}")
    parts.append(f"Model: {item.get('model') or '-'}")
    parts.append(f"Provider: {item.get('provider') or '-'}")
    return " | ".join(parts)


def format_execution_footer(agent_meta: dict[str, str], execution_context: dict[str, Any] | None) -> str:
    lines = [format_agent_meta_log(agent_meta), ""]
    if execution_context:
        lines.append(format_execution_resources_meta_line(execution_context))
    return "\n".join(line for line in lines if line is not None)


def _collect_tool_calls(messages: list[Any]) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tool in msg.tool_calls or []:
                calls.append({"name": str(tool.get("name") or ""), "status": "called"})
        elif isinstance(msg, ToolMessage):
            name = str(getattr(msg, "name", "") or "")
            if calls and calls[-1]["name"] == name and calls[-1]["status"] == "called":
                calls[-1]["status"] = "ok" if "error" not in str(msg.content).lower()[:80] else "error"
    return [item for item in calls if item["name"]]


_MAX_PLAN_CONTINUE_ROUNDS = 6

_PLAN_TOOL_AGENT_KEYS: dict[str, str] = {
    "create_helm_project": "helm_project",
    "create_build": "build",
    "create_workflow": "workflow",
    "create_helm_service_from_template": "helm_service",
    "add_helm_services": "helm_env_service",
    "create_helm_environment": "helm_environment",
}


def _required_tools_for_plan(payload: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    app_type = str(payload.get("application_type") or "create_project").strip()
    if app_type == "add_workflow":
        return ["create_workflow"]
    if app_type == "add_environment":
        return ["create_helm_environment"]
    if app_type == "add_service":
        return [
            "create_helm_service_from_template",
            "add_helm_services",
            "create_build",
            "create_workflow",
        ]
    agent = plan.get("agent") or {}
    tools = ["create_helm_project", "create_build", "create_workflow"]
    if agent.get("helm_env_service"):
        tools = ["create_helm_project", "add_helm_services", "create_build", "create_workflow"]
    return tools


def _successful_tool_names(messages: list[Any]) -> set[str]:
    return {item["name"] for item in _collect_tool_calls(messages) if item.get("status") == "ok" and item.get("name")}


def _missing_plan_tools(payload: dict[str, Any], plan: dict[str, Any], messages: list[Any]) -> list[str]:
    required = _required_tools_for_plan(payload, plan)
    done = _successful_tool_names(messages)
    return [name for name in required if name not in done]


def _continue_plan_prompt(missing: list[str], plan: dict[str, Any]) -> str:
    next_tool = missing[0]
    agent = plan.get("agent") or {}
    key = _PLAN_TOOL_AGENT_KEYS.get(next_tool, "")
    payload_hint = ""
    if key and agent.get(key) is not None:
        payload_hint = f"\n\n请使用执行计划中 agent.{key} 的 JSON 参数调用 `{next_tool}`：\n{json.dumps(agent[key], ensure_ascii=False, indent=2)}"
    return (
        f"计划尚未完成。请立即调用 MCP 工具 `{next_tool}`，不要输出最终总结或结束语。"
        f"\n剩余必做步骤：{', '.join(missing)}。"
        f"{payload_hint}"
    )


async def _emit_log(log_fn: LogCallback | None, text: str) -> None:
    if not log_fn or not text:
        return
    maybe = log_fn(text)
    if maybe is not None and hasattr(maybe, "__await__"):
        await maybe


def _format_step_header(step: int) -> str:
    return f"\n第 {step} 步执行：\n{'-' * 30}\n"


def _format_ai_think(content: str) -> str:
    body = content.strip()
    return f"💡【AI思考】\n{'-' * 40}\n{body}\n{'-' * 40}\n"


def _format_tool_call(name: str, args: Any) -> str:
    payload = json.dumps(args or {}, ensure_ascii=False)
    return f"🛠️【工具调用】\n{'-' * 40}\n{name}: {payload}\n{'-' * 40}\n"


def _format_tool_result(name: str, content: str, duration: float) -> str:
    body = str(content or "").strip()
    if len(body) > 2000:
        body = body[:2000] + "\n...(结果已截断)"
    return (
        f"🛠️【工具执行结果】\n{'-' * 40}\n"
        f"🔧工具：{name}\n"
        f"📮结果：\n{body}\n"
        f"✅状态：执行完成，可以开始下一个任务\n"
        f"⏱ 执行时间：{duration:.2f}秒\n"
        f"{'-' * 40}\n"
    )


_CONFIRM_MARKER = "[需要用户确认]"
_CONFIRM_HINTS = (
    "请您确认",
    "请确认",
    "请选择",
    "请您选择",
    "请告诉我",
    "等待您的确认",
    "等待用户确认",
    "请您确认采用",
    "请确认是否",
    "请确认采用",
)


def _needs_user_confirmation(msg: AIMessage) -> bool:
    if msg.tool_calls:
        return False
    content = str(msg.content or "").strip()
    if not content:
        return False
    if _CONFIRM_MARKER in content:
        return True
    if any(hint in content for hint in _CONFIRM_HINTS):
        return True
    tail = content.rstrip()
    if tail.endswith("？") or tail.endswith("?"):
        if any(word in content for word in ("确认", "选择", "方案", "是否", "哪种", "哪一个")):
            return True
    return False


def _confirmation_prompt(msg: AIMessage) -> str:
    content = str(msg.content or "").replace(_CONFIRM_MARKER, "").strip()
    return content or "请确认是否继续执行。"


def _last_ai_message(messages: list[Any]) -> AIMessage | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg
    return None


def _load_checkpoint_messages(checkpointer: FileSaver, thread_id: str) -> list[Any]:
    tup = checkpointer.get_tuple(RunnableConfig(configurable={"thread_id": thread_id}))
    if not tup:
        return []
    values = tup.checkpoint.get("channel_values") or {}
    messages = values.get("messages") or []
    return list(messages) if isinstance(messages, list) else []


async def _stream_agent_round(
    agent: Any,
    new_messages: list[Any],
    config: RunnableConfig,
    *,
    log_fn: LogCallback | None,
    step_offset: int,
    resume_from_checkpoint: bool = False,
) -> tuple[list[Any], int, float]:
    new_messages_out: list[Any] = []
    step_no = step_offset
    last_tool_time = time.time()

    if resume_from_checkpoint:
        stream_input = None
    elif new_messages:
        stream_input = {"messages": new_messages}
    else:
        stream_input = {"messages": []}

    async for chunk in agent.astream(stream_input, config=config):
        step_no += 1
        await _emit_log(log_fn, _format_step_header(step_no))
        for _node_name, node_output in chunk.items():
            batch = node_output.get("messages") if isinstance(node_output, dict) else None
            if not batch:
                continue
            for msg in batch:
                new_messages_out.append(msg)
                if isinstance(msg, AIMessage):
                    if msg.content:
                        await _emit_log(log_fn, _format_ai_think(str(msg.content)))
                    for tool in msg.tool_calls or []:
                        await _emit_log(
                            log_fn,
                            _format_tool_call(str(tool.get("name") or ""), tool.get("args") or {}),
                        )
                elif isinstance(msg, ToolMessage):
                    now = time.time()
                    duration = now - last_tool_time
                    last_tool_time = now
                    await _emit_log(
                        log_fn,
                        _format_tool_result(str(getattr(msg, "name", "") or "unknown"), str(msg.content or ""), duration),
                    )

    total_duration = time.time() - last_tool_time
    return new_messages_out, step_no, total_duration


async def run_project_create_agent(
    payload: dict[str, Any],
    *,
    log_fn: LogCallback | None = None,
    input_fn: InputCallback | None = None,
    thread_id: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    plan = build_application_plan(payload)
    resources = resolve_execution_resources(payload, plan)
    execution_context = public_execution_context(resources)
    skill_content = resources["skill_content"]
    project_key = plan["project_key"]
    skill_name = execution_context["skill"]["name"]
    is_add_service = str(payload.get("application_type") or "").strip() == "add_service"
    is_add_workflow = str(payload.get("application_type") or "").strip() == "add_workflow"
    is_add_environment = str(payload.get("application_type") or "").strip() == "add_environment"

    await _emit_log(log_fn, f"🤖 助手正在思考和处理...\n{'=' * 60}\n")
    if is_add_workflow:
        await _emit_log(
            log_fn,
            f"开始执行 Helm 添加工作流计划，项目：{project_key}，工作流：{payload.get('workflow_name') or ''}\n",
        )
    elif is_add_environment:
        await _emit_log(
            log_fn,
            f"开始执行 Helm 添加环境计划，项目：{project_key}，环境：{payload.get('environment') or ''}\n",
        )
    elif is_add_service:
        await _emit_log(log_fn, f"开始执行 Helm 添加服务计划，项目：{project_key}，服务：{payload.get('service_name') or ''}\n")
    else:
        await _emit_log(log_fn, f"开始执行 Helm 项目创建计划，项目标识：{project_key}\n")

    tools, client = await get_zadig_mcp_tools()
    await _emit_log(log_fn, format_execution_resources_log(execution_context, runtime_tool_count=len(tools)))

    all_messages: list[Any] = []
    try:
        mcp_summary = json.dumps(execution_context.get("mcp") or {}, ensure_ascii=False, indent=2)
        catalog_summary = json.dumps(
            {
                "selected_skill": execution_context["skill"],
                "selected_template": execution_context["workflow_template"],
                "available_skills": execution_context["catalog"]["skills"],
                "available_templates": execution_context["catalog"]["templates"],
            },
            ensure_ascii=False,
            indent=2,
        )
        system_prompt = (
            "你是 Zadig 运维工程师 zadig_bot，熟悉 Zadig CICD，按 Skill 指引调用 MCP 工具完成任务。\n\n"
            f"# Skill（{skill_name}）\n{skill_content}\n\n"
            f"# 已选工作流模板\n{json.dumps(execution_context['workflow_template'], ensure_ascii=False, indent=2)}\n\n"
            f"# MCP 配置\n{mcp_summary}\n\n"
            f"# 资源目录\n{catalog_summary}\n\n"
            "# 执行计划\n"
            f"{json.dumps(plan['agent'], ensure_ascii=False, indent=2)}\n\n"
            "请严格按 Skill 步骤顺序依次调用 MCP 工具，每步成功后必须立即执行下一步，"
            "在完成 Skill 规定的全部必做步骤之前不要输出最终总结。\n"
            "create_workflow 必须使用执行计划中 workflow.template_name 指定的模板。"
            "全部必做步骤成功后再用中文简要总结结果。\n"
            f"仅在需要用户确认参数、选择或关键操作前，在回复末尾单独一行输出 `{_CONFIRM_MARKER}`。"
            "任务全部完成后的最终总结不要加此标记。"
        )
        checkpoint_thread_id = str(thread_id or new_llm_session_id("zadig-agent"))
        checkpointer = FileSaver()
        execution_context["checkpoint_thread_id"] = checkpoint_thread_id
        agent = create_react_agent(
            model=get_openrouter_llm(session_id=checkpoint_thread_id).bind_tools(tools),
            tools=tools,
            prompt=system_prompt,
            checkpointer=checkpointer,
        )
        config = RunnableConfig(
            configurable={"thread_id": checkpoint_thread_id},
            recursion_limit=40,
        )
        start_message = (
            "请开始执行添加 Helm 工作流计划。"
            if is_add_workflow
            else "请开始执行添加 Helm 环境计划。"
            if is_add_environment
            else "请开始执行添加 Helm 服务计划。"
            if is_add_service
            else "请开始执行创建 Helm Chart 项目计划。"
        )
        all_messages = _load_checkpoint_messages(checkpointer, checkpoint_thread_id) if resume else []
        step_offset = 0
        pending_user_reply: HumanMessage | None = None
        resume_from_checkpoint = False

        if resume and has_checkpoint(checkpoint_thread_id):
            await _emit_log(log_fn, "♻️ 从 checkpoint 恢复 Agent 会话...\n")
            last_ai = _last_ai_message(all_messages)
            if last_ai and _needs_user_confirmation(last_ai):
                prompt = _confirmation_prompt(last_ai)
                await _emit_log(log_fn, f"\n⏸ 恢复会话，等待用户确认：\n{prompt}\n")
                if not input_fn:
                    raise ValueError("Agent 需要用户确认，但未提供交互通道")
                reply = str(await input_fn(prompt)).strip()
                if not reply:
                    raise ValueError("用户确认内容不能为空")
                await _emit_log(log_fn, f"👤 用户：{reply}\n")
                pending_user_reply = HumanMessage(content=reply)
            else:
                resume_from_checkpoint = True
        else:
            pending_user_reply = HumanMessage(content=start_message)

        await _emit_log(log_fn, "正在调用模型推理...\n")

        plan_continue_rounds = 0
        while True:
            try:
                round_messages, step_offset, _duration = await _stream_agent_round(
                    agent,
                    [pending_user_reply] if pending_user_reply else [],
                    config,
                    log_fn=log_fn,
                    step_offset=step_offset,
                    resume_from_checkpoint=resume_from_checkpoint,
                )
            except Exception as exc:
                await _emit_log(log_fn, f"\n❌ 模型调用失败：{format_llm_error(exc)}\n")
                raise
            pending_user_reply = None
            resume_from_checkpoint = False
            all_messages.extend(round_messages)
            last_ai = _last_ai_message(round_messages) or _last_ai_message(all_messages)
            if last_ai and _needs_user_confirmation(last_ai):
                prompt = _confirmation_prompt(last_ai)
                await _emit_log(log_fn, f"\n⏸ 等待用户确认：\n{prompt}\n")
                if not input_fn:
                    raise ValueError("Agent 需要用户确认，但未提供交互通道")
                reply = str(await input_fn(prompt)).strip()
                if not reply:
                    raise ValueError("用户确认内容不能为空")
                await _emit_log(log_fn, f"👤 用户：{reply}\n")
                pending_user_reply = HumanMessage(content=reply)
                continue

            missing_tools = _missing_plan_tools(payload, plan, all_messages)
            if missing_tools:
                if plan_continue_rounds >= _MAX_PLAN_CONTINUE_ROUNDS:
                    raise ValueError(f"Agent 未完成全部步骤，缺少：{', '.join(missing_tools)}")
                plan_continue_rounds += 1
                continue_text = _continue_plan_prompt(missing_tools, plan)
                await _emit_log(
                    log_fn,
                    f"\n⚠️ 计划未完整执行，自动继续第 {plan_continue_rounds} 轮，待完成：{', '.join(missing_tools)}\n",
                )
                pending_user_reply = HumanMessage(content=continue_text)
                continue
            break

        missing_tools = _missing_plan_tools(payload, plan, all_messages)
        if missing_tools:
            raise ValueError(f"Agent 未完成全部步骤，缺少：{', '.join(missing_tools)}")

        summary = ""
        for msg in reversed(all_messages):
            if isinstance(msg, AIMessage) and msg.content:
                summary = str(msg.content).replace(_CONFIRM_MARKER, "").strip()
                break
        project_url = build_project_url(project_key)
        await _emit_log(log_fn, f"\n{'=' * 60}\n✅ 流程结束\n项目链接：{project_url or project_key}\n")
        return {
            "project_key": project_key,
            "project_url": project_url,
            "skill_name": skill_name,
            "execution_context": execution_context,
            "summary": summary,
            "tool_calls": _collect_tool_calls(all_messages),
        }
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            maybe = close()
            if hasattr(maybe, "__await__"):
                await maybe

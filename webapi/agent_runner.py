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


async def _stream_agent_round(
    agent: Any,
    conversation: list[Any],
    config: RunnableConfig,
    *,
    log_fn: LogCallback | None,
    step_offset: int,
) -> tuple[list[Any], int, float]:
    new_messages: list[Any] = []
    step_no = step_offset
    last_tool_time = time.time()

    async for chunk in agent.astream({"messages": conversation}, config=config):
        step_no += 1
        await _emit_log(log_fn, _format_step_header(step_no))
        for _node_name, node_output in chunk.items():
            batch = node_output.get("messages") if isinstance(node_output, dict) else None
            if not batch:
                continue
            for msg in batch:
                new_messages.append(msg)
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
    return new_messages, step_no, total_duration


async def run_project_create_agent(
    payload: dict[str, Any],
    *,
    log_fn: LogCallback | None = None,
    input_fn: InputCallback | None = None,
) -> dict[str, Any]:
    plan = build_application_plan(payload)
    resources = resolve_execution_resources(payload, plan)
    execution_context = public_execution_context(resources)
    skill_content = resources["skill_content"]
    project_key = plan["project_key"]
    skill_name = execution_context["skill"]["name"]
    is_add_service = str(payload.get("application_type") or "").strip() == "add_service"
    is_add_workflow = str(payload.get("application_type") or "").strip() == "add_workflow"

    await _emit_log(log_fn, f"🤖 助手正在思考和处理...\n{'=' * 60}\n")
    if is_add_workflow:
        await _emit_log(
            log_fn,
            f"开始执行 Helm 添加工作流计划，项目：{project_key}，工作流：{payload.get('workflow_name') or ''}\n",
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
            "请严格按 Skill 步骤顺序执行，create_workflow 必须使用执行计划中 workflow.template_name 指定的模板。"
            "完成后用中文简要总结结果。\n"
            f"仅在需要用户确认参数、选择或关键操作前，在回复末尾单独一行输出 `{_CONFIRM_MARKER}`。"
            "任务全部完成后的最终总结不要加此标记。"
        )
        session_id = new_llm_session_id("zadig-agent")
        agent = create_react_agent(
            model=get_openrouter_llm(session_id=session_id).bind_tools(tools),
            tools=tools,
            prompt=system_prompt,
        )
        config = RunnableConfig(
            configurable={"thread_id": session_id},
            recursion_limit=40,
        )
        conversation: list[Any] = [
            HumanMessage(
                content=(
                    "请开始执行添加 Helm 工作流计划。"
                    if is_add_workflow
                    else "请开始执行添加 Helm 服务计划。"
                    if is_add_service
                    else "请开始执行创建 Helm Chart 项目计划。"
                )
            )
        ]
        await _emit_log(log_fn, "正在调用模型推理...\n")
        step_offset = 0

        while True:
            try:
                round_messages, step_offset, _duration = await _stream_agent_round(
                    agent,
                    conversation,
                    config,
                    log_fn=log_fn,
                    step_offset=step_offset,
                )
            except Exception as exc:
                await _emit_log(log_fn, f"\n❌ 模型调用失败：{format_llm_error(exc)}\n")
                raise
            conversation.extend(round_messages)
            all_messages.extend(round_messages)
            last_ai = _last_ai_message(round_messages)
            if last_ai and _needs_user_confirmation(last_ai):
                prompt = _confirmation_prompt(last_ai)
                await _emit_log(log_fn, f"\n⏸ 等待用户确认：\n{prompt}\n")
                if not input_fn:
                    raise ValueError("Agent 需要用户确认，但未提供交互通道")
                reply = str(await input_fn(prompt)).strip()
                if not reply:
                    raise ValueError("用户确认内容不能为空")
                await _emit_log(log_fn, f"👤 用户：{reply}\n")
                conversation.append(HumanMessage(content=reply))
                continue
            break

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

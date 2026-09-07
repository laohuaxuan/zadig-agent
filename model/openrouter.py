from __future__ import annotations

import uuid
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from utils.config import openrouter_config

_llm: ChatOpenAI | None = None
_llm_fingerprint: tuple[str, str, str, str] | None = None


def new_llm_session_id(prefix: str = "zadig-agent") -> str:
    """生成 free-router / OpenRouter 兼容的 session_id（≤256 字符）。"""
    text = str(prefix or "zadig-agent").strip() or "zadig-agent"
    return f"{text}-{uuid.uuid4().hex[:16]}"[:256]


def llm_session_headers(session_id: str) -> dict[str, str]:
    sid = str(session_id or "").strip()[:256]
    if not sid:
        return {}
    return {"x-session-id": sid}


def llm_session_extra_body(session_id: str) -> dict[str, Any]:
    sid = str(session_id or "").strip()[:256]
    if not sid:
        return {}
    return {"session_id": sid}


def create_chat_llm(*, session_id: str) -> ChatOpenAI:
    """按 session 创建 LLM 客户端（free-router 等网关要求 agent 请求带 session_id）。"""
    cfg = openrouter_config()
    sid = str(session_id or "").strip()[:256] or new_llm_session_id()
    headers = {"Accept-Encoding": "identity", **llm_session_headers(sid)}
    return ChatOpenAI(
        model=cfg["model"],
        base_url=cfg["base_url"],
        api_key=SecretStr(cfg["api_key"]),
        streaming=True,
        default_headers=headers,
        extra_body=llm_session_extra_body(sid),
    )


def get_openrouter_llm(*, session_id: str | None = None) -> ChatOpenAI:
    """按当前可用 Agent 返回 ChatOpenAI；传入 session_id 时按执行会话创建客户端。"""
    if session_id:
        return create_chat_llm(session_id=session_id)

    global _llm, _llm_fingerprint
    cfg = openrouter_config()
    fingerprint = (cfg.get("id") or "", cfg["model"], cfg["base_url"], cfg["api_key"])
    if _llm is None or fingerprint != _llm_fingerprint:
        sid = new_llm_session_id("zadig-agent-default")
        _llm = create_chat_llm(session_id=sid)
        if _llm_fingerprint is not None:
            print(
                f"已切换 Agent：{cfg.get('name') or cfg.get('id')} "
                f"model={cfg['model']} base_url={cfg['base_url']}"
            )
        _llm_fingerprint = fingerprint
    return _llm


def chat_completion_probe_body(model: str, *, session_id: str | None = None) -> tuple[str, dict[str, Any]]:
    """构造带 session_id 的最小 chat/completions 探测请求体。"""
    sid = session_id or new_llm_session_id("zadig-agent-probe")
    body = {
        "model": str(model or "").strip(),
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        **llm_session_extra_body(sid),
    }
    return sid, body


def chat_completion_probe_headers(api_key: str, *, session_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **llm_session_headers(session_id),
    }

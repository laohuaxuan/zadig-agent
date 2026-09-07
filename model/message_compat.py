"""Normalize LangChain/OpenAI chat payloads for strict gateways (e.g. free-router)."""

from __future__ import annotations

import json
from typing import Any


def flatten_message_content(content: Any) -> str:
    """Convert tool/assistant content blocks to a plain string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                block_type = str(block.get("type") or "").strip()
                if block_type == "text":
                    text = str(block.get("text") or "").strip()
                    if text:
                        parts.append(text)
                elif block_type in {"image", "file", "audio"}:
                    parts.append(f"[{block_type} content omitted]")
                else:
                    parts.append(json.dumps(block, ensure_ascii=False))
            elif block is not None:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def sanitize_openai_gateway_message(message: dict[str, Any]) -> dict[str, Any]:
    """Fix message shapes rejected by some OpenAI-compatible agent gateways."""
    msg = dict(message)
    role = str(msg.get("role") or "").strip()

    if role == "tool":
        msg["content"] = flatten_message_content(msg.get("content"))
        return msg

    if role == "assistant" and msg.get("tool_calls"):
        # free-router 等网关不接受 assistant 同时带正文与 tool_calls
        msg["content"] = None

    return msg


def sanitize_openai_gateway_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize chat/completions payload before sending to the gateway."""
    data = dict(payload)
    messages = data.get("messages")
    if isinstance(messages, list):
        data["messages"] = [
            sanitize_openai_gateway_message(item) if isinstance(item, dict) else item
            for item in messages
        ]
    return data

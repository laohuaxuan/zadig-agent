"""将 LLM / OpenAI 兼容 API 的错误转为可读说明。"""

from __future__ import annotations

import json
import re


def format_llm_error(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return "模型调用失败"

    lowered = text.lower()
    if "ip_not_allowed" in lowered or "proxy_forbidden" in lowered or "allowed network segments" in lowered:
        return (
            "模型 API 网关拒绝了当前服务器的 IP（ip_not_allowed）。"
            "请在 Agent 的 base_url 服务商处将 Kubernetes 集群出口 IP 加入白名单，"
            "或改用无 IP 限制的 Agent（如 OpenRouter），"
            "或在 Deployment 中为 Pod 配置 HTTP_PROXY / HTTPS_PROXY 走允许网段的代理。"
        )

    code_match = re.search(r"Error code:\s*(\d+)", text)
    if code_match and code_match.group(1) == "457":
        return format_llm_error("ip_not_allowed")

    json_start = text.find("{")
    if json_start >= 0:
        try:
            payload = json.loads(text[json_start:])
            err = payload.get("error")
            if isinstance(err, dict):
                nested = format_llm_error(json.dumps(err, ensure_ascii=False))
                if nested != json.dumps(err, ensure_ascii=False):
                    return nested
                message = str(err.get("message") or "").strip()
                if message:
                    return message
        except json.JSONDecodeError:
            pass

    return text


def format_http_llm_error(status_code: int, body: str) -> str:
    detail = format_llm_error(body)
    if detail != body.strip():
        return detail
    if status_code >= 400:
        return f"HTTP {status_code}: {body[:240] or '模型 API 请求失败'}"
    return detail

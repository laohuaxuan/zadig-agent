from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from utils.config import openrouter_config

_llm: ChatOpenAI | None = None
_llm_fingerprint: tuple[str, str, str, str] | None = None


def get_openrouter_llm() -> ChatOpenAI:
    """按当前可用 Agent 返回 ChatOpenAI；配置变更后重建客户端。"""
    global _llm, _llm_fingerprint
    cfg = openrouter_config()
    fingerprint = (cfg.get("id") or "", cfg["model"], cfg["base_url"], cfg["api_key"])
    if _llm is None or fingerprint != _llm_fingerprint:
        _llm = ChatOpenAI(
            model=cfg["model"],
            base_url=cfg["base_url"],
            api_key=SecretStr(cfg["api_key"]),
            streaming=True,
            default_headers={"Accept-Encoding": "identity"},
        )
        if _llm_fingerprint is not None:
            print(
                f"已切换 Agent：{cfg.get('name') or cfg.get('id')} "
                f"model={cfg['model']} base_url={cfg['base_url']}"
            )
        _llm_fingerprint = fingerprint
    return _llm

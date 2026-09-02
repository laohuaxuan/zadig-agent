from __future__ import annotations

import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

_ROOT = Path(__file__).resolve().parents[1]
_SERVER = _ROOT / "zadig_mcp" / "server.py"


async def create_mcp_stdio_client(name, params):
    config = {
        name: {
            "transport": "stdio",
            **params,
        }
    }
    client = MultiServerMCPClient(config)
    tools = await client.get_tools()
    return tools, client


async def get_zadig_mcp_tools():
    """启动统一 Zadig MCP 服务器，返回 LangChain 工具列表。"""
    params = {
        "command": sys.executable,
        "args": [str(_SERVER)],
        "cwd": str(_ROOT),
    }
    return await create_mcp_stdio_client("zadig", params)

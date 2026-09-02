"""Zadig MCP 服务器：本地 stdio，或可选 SSE 供外部 agent 接入。"""

from __future__ import annotations

import argparse
import hmac
import importlib.util
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools.base import Tool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

from utils.config import mcp_server_config

_DOMAIN_MODULES = (
    "project_tools",
    "environment_tools",
    "services_tools",
    "build_tools",
    "workflows_tools",
    "cluster_tools",
    "registry_tools",
    "templates_tools",
    "policy_tools",
    "users_tools",
    "system_tools",
    "collaboration_tools",
)
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _load_domain_tools(module_name: str) -> list[Tool]:
    path = _DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"zadig_mcp_{module_name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 MCP 模块 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    domain = getattr(module, "mcp", None)
    if domain is None:
        raise ImportError(f"{path} 未导出 FastMCP 实例 mcp")
    return domain._tool_manager.list_tools()


def create_server(host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    tools: list[Tool] = []
    for name in _DOMAIN_MODULES:
        tools.extend(_load_domain_tools(name))
    return FastMCP(
        name="zadig",
        instructions=(
            "Zadig 发布系统 OpenAPI 工具。"
            "覆盖项目、环境、服务、构建、工作流、集群、镜像仓库、模板、权限、用户、系统日志和协作模式。"
        ),
        host=host,
        port=port,
        tools=tools,
    )


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/health":
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        scheme, _, provided = auth.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(provided, self.token):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return await call_next(request)


def _file_defaults() -> dict[str, object]:
    try:
        return mcp_server_config()
    except FileNotFoundError:
        return {"transport": "stdio", "host": "127.0.0.1", "port": 8000, "token": ""}


def _pick(cli: object, env_name: str, fallback: object) -> object:
    if cli is not None and cli != "":
        return cli
    env = os.environ.get(env_name, "").strip()
    if env:
        return env
    return fallback


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    defaults = _file_defaults()
    parser = argparse.ArgumentParser(description="Zadig MCP 服务器（stdio 或 SSE）")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse"),
        default=None,
        help="stdio 供 Cursor/本地 agent；sse 供 HTTP 或公网接入。默认 stdio",
    )
    parser.add_argument("--host", default=None, help="SSE 监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help="SSE 端口，默认 8000")
    parser.add_argument("--token", default=None, help="SSE Bearer Token；绑定非本机地址时必填")
    args = parser.parse_args(argv)
    transport = str(_pick(args.transport, "ZADIG_MCP_TRANSPORT", defaults["transport"])).lower()
    if transport not in {"stdio", "sse"}:
        parser.error("transport 必须是 stdio 或 sse")
    host = str(_pick(args.host, "ZADIG_MCP_HOST", defaults["host"]))
    port_raw = _pick(args.port, "ZADIG_MCP_PORT", defaults["port"])
    token = str(_pick(args.token, "ZADIG_MCP_TOKEN", defaults["token"]))
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        parser.error("port 必须是整数")
    args.transport = transport
    args.host = host
    args.port = port
    args.token = token
    return args


def _run_sse(server: FastMCP, token: str) -> None:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Mount, Route

    host = server.settings.host
    if host in _LOOPBACK and not token:
        print("警告：SSE 未启用 Bearer 鉴权，仅建议本机调试使用。", file=sys.stderr)

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "name": "zadig"})

    middleware = [Middleware(BearerAuthMiddleware, token=token)] if token else []
    app = Starlette(
        routes=[
            Route("/health", health),
            Mount("/", app=server.sse_app()),
        ],
        middleware=middleware,
    )
    print(f"Zadig MCP SSE: http://{host}:{server.settings.port}/sse", file=sys.stderr)
    print(f"健康检查: http://{host}:{server.settings.port}/health", file=sys.stderr)
    uvicorn.run(app, host=host, port=server.settings.port, log_level="info")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.transport == "sse" and args.host not in _LOOPBACK and not args.token:
        raise SystemExit("绑定非本机地址时必须提供 --token / ZADIG_MCP_TOKEN / mcp.token")
    server = create_server(host=args.host, port=args.port)
    if args.transport == "sse":
        _run_sse(server, args.token)
        return
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

"""Zadig 系统 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/system/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/
"""

from __future__ import annotations

from typing import Any, Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_SYSTEM_SEARCH_TYPES = {"all", "project", "user", "function", "status"}
_ENV_SEARCH_TYPES = {"all", "user", "function", "status", "detail"}


def _require(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


@mcp.tool(name="list_system_operation_logs", description="分页列出系统操作日志，可按项目、用户、功能或状态码搜索。")
def list_system_operation_logs(
    search_type: Annotated[
        str,
        Field(description="搜索类型：all（全部）、project（项目）、user（用户）、function（功能）、status（状态码）", example="all"),
    ],
    page: Annotated[int, Field(description="页码", example=1)],
    per_page: Annotated[int, Field(description="每页数量", example=20)],
    project_key: Annotated[str, Field(description="项目标识，search_type 为 project 时使用", example="")] = "",
    username: Annotated[str, Field(description="用户名，search_type 为 user 时使用", example="")] = "",
    function: Annotated[str, Field(description="功能名称，search_type 为 function 时使用", example="")] = "",
    status: Annotated[int, Field(description="状态码，search_type 为 status 时使用；0 表示不按状态过滤", example=0)] = 0,
) -> Annotated[str, Field(description="系统操作日志")]:
    """对应 GET /openapi/system/operation。"""
    try:
        stype = _require("search_type", search_type).lower()
        if stype not in _SYSTEM_SEARCH_TYPES:
            raise ValueError("search_type 必须是 all、project、user、function 或 status")
        params: dict[str, Any] = {
            "searchType": stype,
            "page": page if page > 0 else 1,
            "perPage": per_page if per_page > 0 else 20,
        }
        if project_key.strip():
            params["projectKey"] = project_key.strip()
        elif stype == "project":
            raise ValueError("search_type 为 project 时必须提供 project_key")
        if username.strip():
            params["username"] = username.strip()
        elif stype == "user":
            raise ValueError("search_type 为 user 时必须提供 username")
        if function.strip():
            params["function"] = function.strip()
        elif stype == "function":
            raise ValueError("search_type 为 function 时必须提供 function")
        if status:
            params["status"] = int(status)
        elif stype == "status":
            raise ValueError("search_type 为 status 时必须提供 status")
        return _dump(zadig_request("GET", "/openapi/system/operation", params=params))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_env_operation_logs", description="分页列出指定环境的操作日志，可按用户、功能、状态码或详情搜索。")
def list_env_operation_logs(
    project_key: Annotated[str, Field(description="项目标识", example="yaml")],
    env_name: Annotated[str, Field(description="环境名称", example="dev")],
    search_type: Annotated[
        str,
        Field(description="搜索类型：all（全部）、user（用户）、function（功能）、status（状态码）、detail（详情）", example="all"),
    ],
    page: Annotated[int, Field(description="页码", example=1)],
    per_page: Annotated[int, Field(description="每页数量", example=20)],
    username: Annotated[str, Field(description="用户名，search_type 为 user 时使用", example="")] = "",
    function: Annotated[str, Field(description="功能名称，search_type 为 function 时使用", example="")] = "",
    status: Annotated[int, Field(description="状态码，search_type 为 status 时使用；0 表示不按状态过滤", example=0)] = 0,
    detail: Annotated[str, Field(description="详情关键字，search_type 为 detail 时使用", example="")] = "",
) -> Annotated[str, Field(description="环境操作日志")]:
    """对应 GET /openapi/system/operation/env。"""
    try:
        stype = _require("search_type", search_type).lower()
        if stype not in _ENV_SEARCH_TYPES:
            raise ValueError("search_type 必须是 all、user、function、status 或 detail")
        params: dict[str, Any] = {
            "projectKey": _require("project_key", project_key),
            "envName": _require("env_name", env_name),
            "searchType": stype,
            "page": page if page > 0 else 1,
            "perPage": per_page if per_page > 0 else 20,
        }
        if username.strip():
            params["username"] = username.strip()
        elif stype == "user":
            raise ValueError("search_type 为 user 时必须提供 username")
        if function.strip():
            params["function"] = function.strip()
        elif stype == "function":
            raise ValueError("search_type 为 function 时必须提供 function")
        if status:
            params["status"] = int(status)
        elif stype == "status":
            raise ValueError("search_type 为 status 时必须提供 status")
        if detail.strip():
            params["detail"] = detail.strip()
        elif stype == "detail":
            raise ValueError("search_type 为 detail 时必须提供 detail")
        return _dump(zadig_request("GET", "/openapi/system/operation/env", params=params))
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

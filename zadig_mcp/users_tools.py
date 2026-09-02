"""Zadig 用户 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/user/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/
"""

from __future__ import annotations

from typing import Any, Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_IDENTITY_TYPES = {"ldap", "lark", "oauth", "dingtalk", "workwx", "system"}


def _require(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


def _enc(value: str) -> str:
    return quote(value, safe="")


@mcp.tool(name="list_users", description="分页列出用户信息，可按账户名关键字和身份类型过滤。")
def list_users(
    page_num: Annotated[int, Field(description="页码", example=1)],
    page_size: Annotated[int, Field(description="每页数量", example=20)],
    account: Annotated[str, Field(description="账户名关键字，可选", example="")] = "",
    identity_type: Annotated[
        str,
        Field(description="身份类型，集成外部账号时指定：ldap、lark、oauth、dingtalk、workwx；系统用户可用 system", example=""),
    ] = "",
) -> Annotated[str, Field(description="用户列表")]:
    """对应 GET /openapi/users。"""
    try:
        params: dict[str, Any] = {
            "pageNum": page_num if page_num > 0 else 1,
            "pageSize": page_size if page_size > 0 else 20,
        }
        if account.strip():
            params["account"] = account.strip()
        if identity_type.strip():
            itype = identity_type.strip().lower()
            if itype not in _IDENTITY_TYPES:
                raise ValueError("identity_type 必须是 ldap、lark、oauth、dingtalk、workwx 或 system")
            params["identity_type"] = itype
        return _dump(zadig_request("GET", "/openapi/users", params=params))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_user_groups", description="分页列出用户组信息。")
def list_user_groups(
    page_num: Annotated[int, Field(description="页码", example=1)],
    page_size: Annotated[int, Field(description="每页数量", example=20)],
) -> Annotated[str, Field(description="用户组列表")]:
    """对应 GET /openapi/user-groups。"""
    try:
        return _dump(
            zadig_request(
                "GET",
                "/openapi/user-groups",
                params={
                    "pageNum": page_num if page_num > 0 else 1,
                    "pageSize": page_size if page_size > 0 else 20,
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_user", description="删除指定用户。")
def delete_user(
    uid: Annotated[str, Field(description="用户 uid", example="ddd405d5-5131-11ee-b458-4a4088364d94")],
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/users/:uid。"""
    try:
        user_id = _require("uid", uid)
        return _dump(zadig_request("DELETE", f"/openapi/users/{_enc(user_id)}"))
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

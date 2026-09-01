"""Zadig 权限 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/policy/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/
"""

from __future__ import annotations

from typing import Any, Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_ENV_TYPES = {"k8s", "pm"}
_IDENTITY_TYPES = {"user", "group"}


def _require(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


def _enc(value: str) -> str:
    return quote(value, safe="")


def _normalize_actions(items: list[str], name: str = "actions") -> list[str]:
    if not items:
        raise ValueError(f"{name} 不能为空")
    if not isinstance(items, list):
        raise ValueError(f"{name} 必须是字符串数组")
    out: list[str] = []
    for item in items:
        action = str(item or "").strip()
        if not action:
            raise ValueError(f"{name} 中不能包含空字符串")
        out.append(action)
    return out


def _normalize_identities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise ValueError("identities 不能为空")
    if not isinstance(items, list):
        raise ValueError("identities 必须是对象数组")
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("identities 中的每一项必须是对象")
        itype = _require("identities.identity_type", item.get("identity_type")).lower()
        if itype not in _IDENTITY_TYPES:
            raise ValueError("identity_type 必须是 user 或 group")
        row: dict[str, Any] = {"identity_type": itype}
        if itype == "user":
            row["uid"] = _require("identities.uid", item.get("uid"))
        else:
            row["gid"] = _require("identities.gid", item.get("gid"))
        out.append(row)
    return out


@mcp.tool(name="list_policy_actions", description="列出项目可用的权限项定义（操作对象与操作项）。")
def list_policy_actions(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    env_type: Annotated[str, Field(description="项目类型：k8s 或其他类型用 k8s，自由项目用 pm", example="k8s")],
) -> Annotated[str, Field(description="权限项定义列表")]:
    """对应 GET /openapi/policy/resource-actions。"""
    try:
        etype = _require("env_type", env_type).lower()
        if etype not in _ENV_TYPES:
            raise ValueError("env_type 必须是 k8s 或 pm")
        return _dump(
            zadig_request(
                "GET",
                "/openapi/policy/resource-actions",
                params={
                    "projectName": _require("project_key", project_key),
                    "envType": etype,
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_roles", description="列出项目角色信息。")
def list_roles(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
) -> Annotated[str, Field(description="角色列表")]:
    """对应 GET /openapi/policy/roles。"""
    try:
        return _dump(
            zadig_request(
                "GET",
                "/openapi/policy/roles",
                params={"namespace": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_role", description="获取项目角色详情，含权限规则。")
def get_role(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    name: Annotated[str, Field(description="角色名称", example="dev")],
) -> Annotated[str, Field(description="角色详情")]:
    """对应 GET /openapi/policy/roles/:name。"""
    try:
        role = _require("name", name)
        return _dump(
            zadig_request(
                "GET",
                f"/openapi/policy/roles/{_enc(role)}",
                params={"namespace": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_role", description="创建项目自定义角色，并绑定权限项。")
def create_role(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    name: Annotated[str, Field(description="角色名称", example="test")],
    actions: Annotated[
        list[str],
        Field(description="权限项列表，取值见 list_policy_actions 返回的 action", example=["get_test", "create_test"]),
    ],
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/policy/roles。"""
    try:
        key = _require("project_key", project_key)
        payload = {
            "name": _require("name", name),
            "namespace": key,
            "actions": _normalize_actions(actions),
        }
        return _dump(
            zadig_request("POST", "/openapi/policy/roles", params={"namespace": key}, json_data=payload)
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_role", description="编辑项目角色的权限项。")
def update_role(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    name: Annotated[str, Field(description="角色名称", example="test")],
    actions: Annotated[
        list[str],
        Field(description="权限项列表，取值见 list_policy_actions 返回的 action", example=["get_test", "get_build"]),
    ],
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/policy/roles/:name。"""
    try:
        role = _require("name", name)
        return _dump(
            zadig_request(
                "PUT",
                f"/openapi/policy/roles/{_enc(role)}",
                params={"namespace": _require("project_key", project_key)},
                json_data={"actions": _normalize_actions(actions)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_role", description="删除项目自定义角色。")
def delete_role(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    name: Annotated[str, Field(description="角色名称", example="test")],
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/policy/roles/:name。"""
    try:
        role = _require("name", name)
        return _dump(
            zadig_request(
                "DELETE",
                f"/openapi/policy/roles/{_enc(role)}",
                params={"namespace": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_role_bindings", description="列出项目成员（用户和用户组）及其角色。")
def list_role_bindings(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
) -> Annotated[str, Field(description="成员列表")]:
    """对应 GET /openapi/policy/role-bindings。"""
    try:
        return _dump(
            zadig_request(
                "GET",
                "/openapi/policy/role-bindings",
                params={"namespace": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="add_role_bindings", description="为用户或用户组增加项目角色。")
def add_role_bindings(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    role: Annotated[str, Field(description="要绑定的角色名称", example="read-project-only")],
    identities: Annotated[
        list[dict[str, Any]],
        Field(
            description="成员列表。用户：{identity_type: user, uid}；用户组：{identity_type: group, gid}",
            example=[{"identity_type": "user", "uid": "ddd405d5-5131-11ee-b458-4a4088364d94"}],
        ),
    ],
) -> Annotated[str, Field(description="添加结果")]:
    """对应 POST /openapi/policy/role-bindings。"""
    try:
        key = _require("project_key", project_key)
        payload = {
            "role": _require("role", role),
            "identities": _normalize_identities(identities),
        }
        return _dump(
            zadig_request(
                "POST",
                "/openapi/policy/role-bindings",
                params={"namespace": key},
                json_data=payload,
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_user_roles", description="更新项目中指定用户的角色列表（覆盖写入）。")
def update_user_roles(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    uid: Annotated[str, Field(description="用户 ID", example="ddd405d5-5131-11ee-b458-4a4088364d94")],
    roles: Annotated[
        list[str],
        Field(description="角色名称列表", example=["prod-test", "read-project-only"]),
    ],
) -> Annotated[str, Field(description="更新结果")]:
    """对应 POST /openapi/policy/role-bindings/user/:uid。"""
    try:
        user_id = _require("uid", uid)
        return _dump(
            zadig_request(
                "POST",
                f"/openapi/policy/role-bindings/user/{_enc(user_id)}",
                params={"namespace": _require("project_key", project_key)},
                json_data={"roles": _normalize_actions(roles, "roles")},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_user_binding", description="删除项目中的指定用户成员。")
def delete_user_binding(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    uid: Annotated[str, Field(description="用户 ID", example="ddd405d5-5131-11ee-b458-4a4088364d94")],
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/policy/role-bindings/user/:uid。"""
    try:
        user_id = _require("uid", uid)
        return _dump(
            zadig_request(
                "DELETE",
                f"/openapi/policy/role-bindings/user/{_enc(user_id)}",
                params={"namespace": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_group_roles", description="更新项目中指定用户组的角色列表（覆盖写入）。")
def update_group_roles(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    gid: Annotated[str, Field(description="用户组 ID", example="98256be6-6e53-11ee-a205-9653dd3e9c32")],
    roles: Annotated[
        list[str],
        Field(description="角色名称列表", example=["prod-test", "read-project-only"]),
    ],
) -> Annotated[str, Field(description="更新结果")]:
    """对应 POST /openapi/policy/role-bindings/group/:gid。"""
    try:
        group_id = _require("gid", gid)
        return _dump(
            zadig_request(
                "POST",
                f"/openapi/policy/role-bindings/group/{_enc(group_id)}",
                params={"namespace": _require("project_key", project_key)},
                json_data={"roles": _normalize_actions(roles, "roles")},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_group_binding", description="删除项目中的指定用户组成员。")
def delete_group_binding(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    gid: Annotated[str, Field(description="用户组 ID", example="98256be6-6e53-11ee-a205-9653dd3e9c32")],
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/policy/role-bindings/group/:gid。"""
    try:
        group_id = _require("gid", gid)
        return _dump(
            zadig_request(
                "DELETE",
                f"/openapi/policy/role-bindings/group/{_enc(group_id)}",
                params={"namespace": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

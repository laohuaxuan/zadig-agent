"""Zadig 协作模式 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/collaboration/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/
"""

from __future__ import annotations

from typing import Any, Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_COLLAB_TYPES = {"share", "new"}
_WORKFLOW_VERBS = {"get_workflow", "edit_workflow", "run_workflow", "debug_workflow"}
_ENV_VERBS = {"get_environment", "config_environment", "manage_environment", "debug_pod"}


def _require(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


def _enc(value: str) -> str:
    return quote(value, safe="")


def _normalize_ids(items: list[str] | None, name: str) -> list[str]:
    if not items:
        return []
    if not isinstance(items, list):
        raise ValueError(f"{name} 必须是字符串数组")
    out: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value:
            raise ValueError(f"{name} 中不能包含空字符串")
        out.append(value)
    return out


def _normalize_verbs(items: list[str], allowed: set[str], name: str) -> list[str]:
    if not items:
        raise ValueError(f"{name} 不能为空")
    if not isinstance(items, list):
        raise ValueError(f"{name} 必须是字符串数组")
    out: list[str] = []
    for item in items:
        verb = str(item or "").strip()
        if verb not in allowed:
            raise ValueError(f"{name} 非法：{verb}，允许值为 {', '.join(sorted(allowed))}")
        out.append(verb)
    return out


def _normalize_resources(
    items: list[dict[str, Any]] | None,
    *,
    name: str,
    allowed_verbs: set[str],
) -> list[dict[str, Any]]:
    if not items:
        return []
    if not isinstance(items, list):
        raise ValueError(f"{name} 必须是对象数组")
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{name} 中的每一项必须是对象")
        ctype = _require(f"{name}.collaboration_type", item.get("collaboration_type")).lower()
        if ctype not in _COLLAB_TYPES:
            raise ValueError(f"{name}.collaboration_type 必须是 share 或 new")
        out.append(
            {
                "name": _require(f"{name}.name", item.get("name")),
                "collaboration_type": ctype,
                "verbs": _normalize_verbs(item.get("verbs") or [], allowed_verbs, f"{name}.verbs"),
            }
        )
    return out


@mcp.tool(name="create_collaboration", description="新建协作模式，为用户或用户组分配工作流和环境权限。")
def create_collaboration(
    project_key: Annotated[str, Field(description="项目标识", example="multi-chart")],
    name: Annotated[str, Field(description="协作模式名称", example="api-test")],
    recycle_day: Annotated[int, Field(description="资源回收天数，0 表示不回收", example=0)] = 0,
    user_ids: Annotated[
        list[str],
        Field(description="用户 ID 列表", example=["00abf4dc-5c6d-11f0-8608-3abfaba6efff"]),
    ] = [],
    group_ids: Annotated[
        list[str],
        Field(description="用户组 ID 列表", example=["f0035a8b-66a7-11f0-89e1-1631ef6b4739"]),
    ] = [],
    workflows: Annotated[
        list[dict[str, Any]],
        Field(
            description="工作流列表，每项含 name、collaboration_type（share/new）、verbs（get_workflow/edit_workflow/run_workflow/debug_workflow）",
            example=[{"name": "test-ops", "collaboration_type": "share", "verbs": ["get_workflow", "run_workflow"]}],
        ),
    ] = [],
    envs: Annotated[
        list[dict[str, Any]],
        Field(
            description="环境列表，每项含 name、collaboration_type（share/new）、verbs（get_environment/config_environment/manage_environment/debug_pod）",
            example=[{"name": "dev", "collaboration_type": "share", "verbs": ["get_environment"]}],
        ),
    ] = [],
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/collaborations。"""
    try:
        payload: dict[str, Any] = {
            "project_key": _require("project_key", project_key),
            "name": _require("name", name),
            "recycle_day": int(recycle_day) if recycle_day >= 0 else 0,
        }
        users = _normalize_ids(user_ids, "user_ids")
        if users:
            payload["user_ids"] = users
        groups = _normalize_ids(group_ids, "group_ids")
        if groups:
            payload["group_ids"] = groups
        wf_list = _normalize_resources(workflows, name="workflows", allowed_verbs=_WORKFLOW_VERBS)
        if wf_list:
            payload["workflows"] = wf_list
        env_list = _normalize_resources(envs, name="envs", allowed_verbs=_ENV_VERBS)
        if env_list:
            payload["envs"] = env_list
        return _dump(zadig_request("POST", "/openapi/collaborations", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_collaboration", description="删除指定协作模式。")
def delete_collaboration(
    project_key: Annotated[str, Field(description="项目标识", example="multi-chart")],
    name: Annotated[str, Field(description="协作模式名称", example="api-test")],
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/collaborations/<协作模式名称>。"""
    try:
        collab = _require("name", name)
        return _dump(
            zadig_request(
                "DELETE",
                f"/openapi/collaborations/{_enc(collab)}",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

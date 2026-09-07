"""Zadig 项目 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/project/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/
"""

from __future__ import annotations

from typing import Any, Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_EMPTY_PROJECT_TYPES = {"helm", "yaml", "loaded"}


def _normalize_helm_services(service_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not service_list:
        raise ValueError("创建 Helm 项目时 service_list 不能为空")
    out: list[dict[str, Any]] = []
    for item in service_list:
        if not isinstance(item, dict):
            raise ValueError("service_list 中的每一项必须是对象")
        service_name = str(item.get("service_name") or "").strip()
        template_name = str(item.get("template_name") or "").strip()
        if not service_name:
            raise ValueError("Helm 服务缺少 service_name")
        if not template_name:
            raise ValueError(f"服务 {service_name} 缺少 template_name")
        row: dict[str, Any] = {
            "source": "template",
            "service_name": service_name,
            "template_name": template_name,
            "auto_sync": bool(item.get("auto_sync", False)),
            "values_yaml": str(item.get("values_yaml") or ""),
        }
        variables = item.get("variable_yaml") or []
        if variables:
            if not isinstance(variables, list):
                raise ValueError("variable_yaml 必须是 [{key, value}, ...] 数组")
            row["variable_yaml"] = [
                {"key": str(v.get("key")), "value": v.get("value")}
                for v in variables
                if isinstance(v, dict) and v.get("key")
            ]
        out.append(row)
    return out


def _normalize_helm_envs(env_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not env_list:
        raise ValueError("创建 Helm 项目时 env_list 不能为空")
    out: list[dict[str, Any]] = []
    for item in env_list:
        if not isinstance(item, dict):
            raise ValueError("env_list 中的每一项必须是对象")
        env_key = str(item.get("env_key") or "").strip()
        cluster_name = str(item.get("cluster_name") or item.get("cluster") or "").strip()
        namespace = str(item.get("namespace") or "").strip()
        if not env_key or not cluster_name or not namespace:
            raise ValueError("Helm 环境需要 env_key、cluster_name、namespace")
        out.append(
            {
                "env_key": env_key,
                "cluster_name": cluster_name,
                "namespace": namespace,
                **({"production": bool(item["production"])} if "production" in item else {}),
            }
        )
    return out


@mcp.tool(name="create_empty_project", description="创建空的 Zadig 项目，不包含任何服务或环境资源。")
def create_empty_project(
    project_name: Annotated[str, Field(description="项目名称", example="我的项目")],
    project_key: Annotated[str, Field(description="项目key，只能包含小写字母、数字和中划线", example="my-project")],
    project_type: Annotated[str, Field(description="项目类型", example="helm")],
    is_public: Annotated[bool, Field(description="是否公开", example=False)],
    description: Annotated[str, Field(description="项目描述", example="我的项目描述")],
) -> Annotated[str, Field(description="创建结果")]:
    """创建空的 Zadig 项目，不包含任何服务或环境资源。

    对应 POST /openapi/projects/project。
    project_type 可选：helm（Helm Chart 项目）、yaml（YAML 项目）、loaded（托管项目）。
    project_key 只能包含小写字母、数字和中划线。
    """
    try:
        ptype = project_type.strip().lower()
        if ptype not in _EMPTY_PROJECT_TYPES:
            raise ValueError("project_type 必须是 helm、yaml 或 loaded")
        payload: dict[str, Any] = {
            "project_name": project_name.strip(),
            "project_key": project_key.strip(),
            "is_public": is_public,
            "project_type": ptype,
        }
        if description.strip():
            payload["description"] = description.strip()
        return _dump(zadig_request("POST", "/openapi/projects/project", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_helm_project", description="创建 helm 项目并初始化服务与环境。")
def create_helm_project(
    project_name: Annotated[str, Field(description="项目名称", example="我的项目")],
    project_key: Annotated[str, Field(description="项目key，只能包含小写字母、数字和中划线", example="my-project")],
    service_list: Annotated[list[dict[str, Any]], Field(description="服务列表", example=[{"service_name": "my-service", "template_name": "my-template"}])],
    env_list: Annotated[list[dict[str, Any]], Field(description="环境列表", example=[{"env_key": "my-env", "cluster_name": "my-cluster", "namespace": "my-namespace"}])],
    is_public: Annotated[bool, Field(description="是否公开", example=False)],
    description: Annotated[str, Field(description="项目描述", example="我的项目描述")],
) -> Annotated[str, Field(description="创建结果")]:
    """创建 Helm 项目并初始化服务与环境。

    对应 POST /openapi/projects/project/init/helm。
    service_list 每项需含 service_name、template_name，可选 variable_yaml、values_yaml、auto_sync。
    env_list 每项需含 env_key、cluster_name、namespace。
    从代码仓导入 values 请使用 add_helm_services，init 接口不支持 import_values_from_git。
    project_key 只能包含小写字母、数字和中划线。
    """
    try:
        payload: dict[str, Any] = {
            "project_name": project_name.strip(),
            "project_key": project_key.strip(),
            "is_public": is_public,
            "service_list": _normalize_helm_services(service_list),
            "env_list": _normalize_helm_envs(env_list),
        }
        if description.strip():
            payload["description"] = description.strip()
        return _dump(
            zadig_request("POST", "/openapi/projects/project/init/helm", json_data=payload)
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_projects", description="获取 Zadig 项目列表（分页）。")
def list_projects(
    page_size: Annotated[int, Field(description="每页项目数量", example=20)], 
    page_num: Annotated[int, Field(description="页码", example=1)]
    ) -> Annotated[str, Field(description="项目列表")]:
    """获取 Zadig 项目列表（分页）。
    对应 GET /openapi/projects/project。
    返回 projects 列表和 total。
    """
    try:
        size = page_size if page_size > 0 else 20
        num = page_num if page_num > 0 else 1
        return _dump(
            zadig_request(
                "GET",
                "/openapi/projects/project",
                params={"pageSize": size, "pageNum": num},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_project", description="获取指定 Zadig 项目详情。")
def get_project(
    project_key: Annotated[str, Field(description="项目key", example="my-project")]
    ) -> Annotated[str, Field(description="项目详情")]:
    """获取指定 Zadig 项目详情。
    对应 GET /openapi/projects/project/detail?projectKey=<项目标识>。
    """
    try:
        key = project_key.strip()
        if not key:
            raise ValueError("project_key 不能为空")
        return _dump(
            zadig_request(
                "GET",
                "/openapi/projects/project/detail",
                params={"projectKey": key},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_project", description="删除 Zadig 项目。")
def delete_project(
    project_key: Annotated[str, Field(description="项目key", example="my-project")],
    is_delete: Annotated[bool, Field(description="是否删除环境对应的 Kubernetes 命名空间和服务", example=False)]
    ) -> Annotated[str, Field(description="删除结果")]:
    """删除 Zadig 项目。
    对应 DELETE /openapi/projects/project。
    is_delete 为 True 时同时删除环境对应的 Kubernetes 命名空间和服务，请谨慎使用。
    """
    try:
        key = project_key.strip()
        if not key:
            raise ValueError("project_key 不能为空")
        return _dump(
            zadig_request(
                "DELETE",
                "/openapi/projects/project",
                params={"projectKey": key, "isDelete": str(is_delete).lower()},
            )
        )
    except Exception as exc:
        return _error(str(exc))

if __name__ == "__main__":
    mcp.run(transport="stdio")
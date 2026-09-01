"""Zadig 服务 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/service/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/

本文档 OpenAPI 主要覆盖 K8s YAML 服务；Helm 服务包含从代码仓加载、使用模板新建。
"""

from __future__ import annotations

from typing import Any, Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_VAR_TYPES = {"bool", "string", "enum", "yaml"}
_HELM_SOURCES = {"repo", "gerrit", "gitee", "gitee-enterprise", "publicRepo", "chartRepo"}
_GIT_SOURCES = {"repo", "gerrit", "gitee", "gitee-enterprise"}


def _require(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


def _enc(value: str) -> str:
    return quote(value, safe="")


def _yaml_root(production: bool) -> str:
    return "/openapi/service/yaml/production" if production else "/openapi/service/yaml"


def _template_yaml_path(production: bool) -> str:
    if production:
        return "/openapi/service/template/production/load/yaml"
    return "/openapi/service/template/load/yaml"


def _normalize_keyvals(
    items: list[dict[str, Any]] | None,
    *,
    require_type: bool = False,
    name: str = "variable_yaml",
) -> list[dict[str, Any]]:
    if not items:
        return []
    if not isinstance(items, list):
        raise ValueError(f"{name} 必须是对象数组")
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{name} 中的每一项必须是对象")
        key = str(item.get("key") or "").strip()
        if not key:
            raise ValueError(f"{name} 缺少 key")
        if "value" not in item:
            raise ValueError(f"{name} 中 {key} 缺少 value")
        row: dict[str, Any] = {"key": key, "value": item.get("value")}
        vtype = str(item.get("type") or "").strip()
        if require_type:
            if vtype not in _VAR_TYPES:
                raise ValueError(f"{name} 中 {key} 的 type 必须是 bool、string、enum 或 yaml")
            row["type"] = vtype
        elif vtype:
            if vtype not in _VAR_TYPES:
                raise ValueError(f"{name} 中 {key} 的 type 必须是 bool、string、enum 或 yaml")
            row["type"] = vtype
        if item.get("options") is not None:
            options = item.get("options")
            if not isinstance(options, list):
                raise ValueError(f"{name} 中 {key} 的 options 必须是字符串数组")
            row["options"] = options
        if item.get("desc") is not None:
            row["desc"] = str(item.get("desc") or "")
        out.append(row)
    return out


def _normalize_service_paths(service_paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not service_paths:
        raise ValueError("service_paths 不能为空")
    if not isinstance(service_paths, list):
        raise ValueError("service_paths 必须是对象数组")
    out: list[dict[str, Any]] = []
    for item in service_paths:
        if not isinstance(item, dict):
            raise ValueError("service_paths 中的每一项必须是对象")
        service_name = str(item.get("service_name") or "").strip()
        if not service_name:
            raise ValueError("service_paths 缺少 service_name")
        is_dir = bool(item.get("is_dir", False))
        path = str(item.get("path") or "")
        if not is_dir and not path.strip():
            raise ValueError(f"服务 {service_name} 从文件加载时 path 不能为空")
        out.append(
            {
                "service_name": service_name,
                "path": path,
                "is_dir": is_dir,
            }
        )
    return out


def _normalize_helm_create_from(source: str, create_from: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(create_from, dict):
        raise ValueError("create_from 必须是对象")
    if source in _GIT_SOURCES:
        codehost = str(
            create_from.get("codehostName") or create_from.get("codehost_name") or ""
        ).strip()
        owner = str(create_from.get("owner") or "").strip()
        repo = str(create_from.get("repo") or "").strip()
        branch = str(create_from.get("branch") or "").strip()
        paths = create_from.get("paths")
        if not codehost or not owner or not repo or not branch:
            raise ValueError("create_from 需要 codehostName、owner、repo、branch")
        if not paths or not isinstance(paths, list):
            raise ValueError("create_from.paths 必须是非空字符串数组")
        row: dict[str, Any] = {
            "codehostName": codehost,
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "paths": [str(p) for p in paths],
        }
        namespace = str(create_from.get("namespace") or "").strip()
        if namespace:
            row["namespace"] = namespace
        return row
    if source == "publicRepo":
        repo_link = str(
            create_from.get("repoLink") or create_from.get("repo_link") or ""
        ).strip()
        paths = create_from.get("paths")
        if not repo_link:
            raise ValueError("publicRepo 需要 create_from.repoLink")
        if not paths or not isinstance(paths, list):
            raise ValueError("create_from.paths 必须是非空字符串数组")
        return {"repoLink": repo_link, "paths": [str(p) for p in paths]}
    if source == "chartRepo":
        chart_repo = str(
            create_from.get("chartRepoName") or create_from.get("chart_repo_name") or ""
        ).strip()
        chart_name = str(
            create_from.get("chartName") or create_from.get("chart_name") or ""
        ).strip()
        if not chart_repo or not chart_name:
            raise ValueError("chartRepo 需要 create_from.chartRepoName、chartName")
        row = {"chartRepoName": chart_repo, "chartName": chart_name}
        version = str(
            create_from.get("chartVersion") or create_from.get("chart_version") or ""
        ).strip()
        if version:
            row["chartVersion"] = version
        return row
    raise ValueError("source 必须是 repo、gerrit、gitee、gitee-enterprise、publicRepo 或 chartRepo")


@mcp.tool(name="list_yaml_services", description="获取项目下的 K8s YAML 服务列表（测试或生产）。")
def list_yaml_services(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    production: Annotated[bool, Field(description="是否查询生产服务", example=False)] = False,
) -> Annotated[str, Field(description="服务列表")]:
    """对应 GET /openapi/service/yaml/services 或其 production 路径。"""
    try:
        key = _require("project_key", project_key)
        return _dump(
            zadig_request("GET", f"{_yaml_root(production)}/services", params={"projectKey": key})
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_yaml_service", description="获取指定 K8s YAML 服务详情，含 YAML 内容、组件和变量。")
def get_yaml_service(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
    production: Annotated[bool, Field(description="是否为生产服务", example=False)] = False,
) -> Annotated[str, Field(description="服务详情")]:
    """对应 GET /openapi/service/yaml/:serviceName 或其 production 路径。"""
    try:
        key = _require("project_key", project_key)
        svc = _require("service_name", service_name)
        return _dump(
            zadig_request("GET", f"{_yaml_root(production)}/{_enc(svc)}", params={"projectKey": key})
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_yaml_service_labels", description="获取指定 K8s YAML 服务的标签列表。")
def get_yaml_service_labels(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
) -> Annotated[str, Field(description="服务标签")]:
    """对应 GET /openapi/service/yaml/:serviceName/labels。"""
    try:
        key = _require("project_key", project_key)
        svc = _require("service_name", service_name)
        return _dump(
            zadig_request(
                "GET",
                f"/openapi/service/yaml/{_enc(svc)}/labels",
                params={"projectKey": key},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_yaml_service_from_template", description="使用 K8s YAML 模板新建服务（测试或生产）。")
def create_yaml_service_from_template(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    service_name: Annotated[str, Field(description="服务名称", example="service1")],
    template_name: Annotated[str, Field(description="K8s YAML 模板名称", example="microservice-template")],
    production: Annotated[bool, Field(description="是否创建生产服务", example=False)] = False,
    auto_sync: Annotated[bool, Field(description="是否自动同步模板", example=True)] = False,
    variable_yaml: Annotated[
        list[dict[str, Any]],
        Field(description="模板变量列表，每项含 key、value", example=[{"key": "cpuLimit", "value": "100m"}]),
    ] = [],
    yaml: Annotated[str, Field(description="生产服务可选 YAML 内容；测试服务一般不传", example="")] = "",
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/service/template/load/yaml 或其 production 路径。"""
    try:
        payload: dict[str, Any] = {
            "service_name": _require("service_name", service_name),
            "project_key": _require("project_key", project_key),
            "template_name": _require("template_name", template_name),
            "auto_sync": auto_sync,
        }
        variables = _normalize_keyvals(variable_yaml, name="variable_yaml")
        if variables:
            payload["variable_yaml"] = variables
        if production:
            payload["production"] = True
            if yaml.strip():
                payload["yaml"] = yaml
        return _dump(zadig_request("POST", _template_yaml_path(production), json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_yaml_service", description="手动输入 YAML 新建 K8s 服务（测试或生产）。")
def create_yaml_service(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    service_name: Annotated[str, Field(description="服务名称", example="service-3")],
    yaml: Annotated[str, Field(description="服务的 YAML 内容", example="apiVersion: apps/v1\nkind: Deployment\n")],
    production: Annotated[bool, Field(description="是否创建生产服务", example=False)] = False,
    variable_yaml: Annotated[
        list[dict[str, Any]],
        Field(
            description="YAML 变量列表，每项需含 key、value、type（bool/string/enum/yaml），可选 options、desc",
            example=[{"key": "cpu", "value": "12m", "type": "string", "desc": "cpu值"}],
        ),
    ] = [],
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/service/yaml/raw 或其 production 路径。"""
    try:
        key = _require("project_key", project_key)
        payload: dict[str, Any] = {
            "service_name": _require("service_name", service_name),
            "yaml": _require("yaml", yaml),
        }
        variables = _normalize_keyvals(variable_yaml, require_type=True, name="variable_yaml")
        if variables:
            payload["variable_yaml"] = variables
        return _dump(
            zadig_request(
                "POST",
                f"{_yaml_root(production)}/raw",
                params={"projectKey": key},
                json_data=payload,
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="load_yaml_services_from_repo", description="从代码库新建 K8s YAML 服务（测试或生产）。")
def load_yaml_services_from_repo(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    codehost_name: Annotated[str, Field(description="代码源名称", example="github-demo")],
    repo_name: Annotated[str, Field(description="代码库名称", example="demo")],
    branch_name: Annotated[str, Field(description="服务配置所在分支", example="main")],
    repo_owner: Annotated[str, Field(description="仓库拥有者/组织名", example="koderover")],
    service_paths: Annotated[
        list[dict[str, Any]],
        Field(
            description="服务路径列表，每项需含 service_name；path 为仓库相对路径，is_dir 表示是否从目录加载",
            example=[{"service_name": "backend", "path": "services/backend/deployment.yaml", "is_dir": False}],
        ),
    ],
    remote_name: Annotated[str, Field(description="Git 远端名称，Gerrit/Gitee 场景使用，默认 origin", example="")] = "",
    namespace: Annotated[str, Field(description="GitHub/GitLab 仓库命名空间，为空默认使用 repo_owner", example="")] = "",
    production: Annotated[bool, Field(description="是否创建生产服务", example=False)] = False,
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/service/loader/load。"""
    try:
        params: dict[str, Any] = {
            "codehostName": _require("codehost_name", codehost_name),
            "repoName": _require("repo_name", repo_name),
            "branchName": _require("branch_name", branch_name),
            "repoOwner": _require("repo_owner", repo_owner),
            "production": str(production).lower(),
        }
        if remote_name.strip():
            params["remoteName"] = remote_name.strip()
        if namespace.strip():
            params["namespace"] = namespace.strip()
        payload = {
            "product_name": _require("project_key", project_key),
            "service_paths": _normalize_service_paths(service_paths),
        }
        return _dump(
            zadig_request(
                "POST",
                "/openapi/service/loader/load",
                params=params,
                json_data=payload,
                timeout=90.0,
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(
    name="load_helm_services",
    description="从已接入代码源、公开仓库或 Chart 仓库新建 Helm 服务。",
)
def load_helm_services(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    source: Annotated[
        str,
        Field(
            description="服务来源：repo、gerrit、gitee、gitee-enterprise、publicRepo、chartRepo",
            example="repo",
        ),
    ],
    create_from: Annotated[
        dict[str, Any],
        Field(
            description="来源配置。代码源需 codehostName/owner/repo/branch/paths；公开仓库需 repoLink/paths；Chart 仓库需 chartRepoName/chartName，可选 chartVersion",
            example={
                "codehostName": "github-demo",
                "owner": "koderover",
                "repo": "helm-charts",
                "branch": "main",
                "paths": ["charts/backend"],
            },
        ),
    ],
    production: Annotated[bool, Field(description="是否创建生产服务", example=False)] = False,
) -> Annotated[str, Field(description="创建结果，含 successServices 与 failedServices")]:
    """对应 POST /openapi/service/helm/load。"""
    try:
        src = _require("source", source)
        if src not in _HELM_SOURCES:
            raise ValueError("source 必须是 repo、gerrit、gitee、gitee-enterprise、publicRepo 或 chartRepo")
        payload = {
            "source": src,
            "production": production,
            "createFrom": _normalize_helm_create_from(src, create_from),
        }
        return _dump(
            zadig_request(
                "POST",
                "/openapi/service/helm/load",
                params={"projectKey": _require("project_key", project_key)},
                json_data=payload,
                timeout=90.0,
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_yaml_service", description="更新 K8s YAML 服务配置（测试或生产）。")
def update_yaml_service(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    service_name: Annotated[str, Field(description="服务名称", example="service1")],
    yaml: Annotated[str, Field(description="服务配置的 YAML 内容", example="apiVersion: apps/v1\nkind: Deployment\n")],
    production: Annotated[bool, Field(description="是否为生产服务", example=False)] = False,
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/service/yaml/:serviceName 或其 production 路径。"""
    try:
        key = _require("project_key", project_key)
        svc = _require("service_name", service_name)
        return _dump(
            zadig_request(
                "PUT",
                f"{_yaml_root(production)}/{_enc(svc)}",
                params={"projectKey": key},
                json_data={"type": "k8s", "yaml": _require("yaml", yaml)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_yaml_service_variables", description="更新 K8s YAML 服务变量（测试或生产）。")
def update_yaml_service_variables(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    service_name: Annotated[str, Field(description="服务名称", example="service1")],
    service_variable_kvs: Annotated[
        list[dict[str, Any]],
        Field(
            description="服务变量列表，每项需含 key、value、type（bool/string/enum/yaml），可选 options、desc",
            example=[{"key": "cpu", "value": "12m", "type": "string", "options": [], "desc": ""}],
        ),
    ],
    production: Annotated[bool, Field(description="是否为生产服务", example=False)] = False,
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/service/yaml/:serviceName/variable 或其 production 路径。"""
    try:
        key = _require("project_key", project_key)
        svc = _require("service_name", service_name)
        variables = _normalize_keyvals(
            service_variable_kvs, require_type=True, name="service_variable_kvs"
        )
        if not variables:
            raise ValueError("service_variable_kvs 不能为空")
        return _dump(
            zadig_request(
                "PUT",
                f"{_yaml_root(production)}/{_enc(svc)}/variable",
                params={"projectKey": key},
                json_data={"service_variable_kvs": variables},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_yaml_service", description="删除 K8s YAML 服务（测试或生产）。")
def delete_yaml_service(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    service_name: Annotated[str, Field(description="服务名称", example="service1")],
    production: Annotated[bool, Field(description="是否为生产服务", example=False)] = False,
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/service/yaml/:serviceName 或其 production 路径。"""
    try:
        key = _require("project_key", project_key)
        svc = _require("service_name", service_name)
        return _dump(
            zadig_request(
                "DELETE",
                f"{_yaml_root(production)}/{_enc(svc)}",
                params={"projectKey": key},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_helm_service_from_template", description="使用 Helm 模板新建服务（测试或生产）。")
def create_helm_service_from_template(
    project_key: Annotated[str, Field(description="项目标识", example="multi-chart")],
    service_name: Annotated[str, Field(description="服务名称", example="api-test")],
    template_name: Annotated[str, Field(description="Helm 模板名称", example="general-chart")],
    production: Annotated[bool, Field(description="是否创建生产服务", example=False)] = False,
    values_yaml: Annotated[str, Field(description="values.yaml 内容", example="aa: bb\ncc: dd")] = "",
    variables: Annotated[
        list[dict[str, Any]],
        Field(description="模板变量列表，每项含 key、value", example=[{"key": "port", "value": 20012}]),
    ] = [],
    auto_sync: Annotated[bool, Field(description="是否自动同步模板", example=True)] = False,
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/service/template/load/helm。"""
    try:
        key = _require("project_key", project_key)
        payload: dict[str, Any] = {
            "project_key": key,
            "service_name": _require("service_name", service_name),
            "template_name": _require("template_name", template_name),
            "production": production,
            "auto_sync": auto_sync,
        }
        if values_yaml.strip():
            payload["values_yaml"] = values_yaml
        vars_list = _normalize_keyvals(variables, name="variables")
        if vars_list:
            payload["variables"] = vars_list
        return _dump(
            zadig_request(
                "POST",
                "/openapi/service/template/load/helm",
                params={"projectKey": key},
                json_data=payload,
            )
        )
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

"""Zadig 环境 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/env/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/
"""

from __future__ import annotations

from typing import Any, Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_WORKLOAD_TYPES = {"Deployment", "StatefulSet", "CronJob"}
_SCALE_TYPES = {"Deployment", "StatefulSet"}
_ENVCFG_TYPES = {"ConfigMap", "Ingress", "Secret", "PVC"}
_SHARE_OPS = {"enable", "disable"}
_IMAGE_KINDS = {"deployment", "statefulset", "cronjob"}


def _require(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


def _env_root(production: bool) -> str:
    return "/openapi/environments/production" if production else "/openapi/environments"


def _enc(value: str) -> str:
    return quote(value, safe="")


def _envcfg_type(value: str) -> str:
    cfg_type = value.strip()
    if cfg_type not in _ENVCFG_TYPES:
        raise ValueError("type 必须是 ConfigMap、Ingress、Secret 或 PVC")
    return cfg_type


@mcp.tool(name="list_environments", description="查看项目下的环境列表（测试或生产）。")
def list_environments(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    production: Annotated[bool, Field(description="是否查询生产环境", example=False)] = False,
) -> Annotated[str, Field(description="环境列表")]:
    """对应 GET /openapi/environments 或 /openapi/environments/production。"""
    try:
        key = _require("project_key", project_key)
        return _dump(zadig_request("GET", _env_root(production), params={"projectKey": key}))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_environment", description="查看指定环境详情。")
def get_environment(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="环境详情")]:
    """对应 GET /openapi/environments/<环境标识> 或其 production 路径。"""
    try:
        key = _require("project_key", project_key)
        env = _require("env_key", env_key)
        return _dump(
            zadig_request("GET", f"{_env_root(production)}/{_enc(env)}", params={"projectKey": key})
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_environment_service", description="查看环境中某个 K8s YAML 服务的详情。")
def get_environment_service(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
    workload_type: Annotated[str, Field(description="工作负载类型：Deployment、StatefulSet、CronJob", example="Deployment")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="服务详情")]:
    """对应 GET /openapi/environments/<环境>/services/<服务>。"""
    try:
        key = _require("project_key", project_key)
        env = _require("env_key", env_key)
        svc = _require("service_name", service_name)
        wtype = _require("workload_type", workload_type)
        if wtype not in _WORKLOAD_TYPES:
            raise ValueError("workload_type 必须是 Deployment、StatefulSet 或 CronJob")
        return _dump(
            zadig_request(
                "GET",
                f"{_env_root(production)}/{_enc(env)}/services/{_enc(svc)}",
                params={"projectKey": key, "workLoadtype": wtype},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_environment_service_yaml", description="查看环境中 K8s YAML 服务的渲染后 YAML。")
def get_environment_service_yaml(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_name: Annotated[str, Field(description="环境名称", example="dev")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="服务 YAML")]:
    """对应 GET /openapi/environments/services/yaml。"""
    try:
        path = (
            "/openapi/environments/production/services/yaml"
            if production
            else "/openapi/environments/services/yaml"
        )
        return _dump(
            zadig_request(
                "GET",
                path,
                params={
                    "projectKey": _require("project_key", project_key),
                    "envName": _require("env_name", env_name),
                    "serviceName": _require("service_name", service_name),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_environment_helm_values", description="查看环境中 Helm 服务的 Values。")
def get_environment_helm_values(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_name: Annotated[str, Field(description="环境名称", example="dev")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="Helm Values")]:
    """对应 GET /openapi/environments/service/values。"""
    try:
        path = (
            "/openapi/environments/production/service/values"
            if production
            else "/openapi/environments/service/values"
        )
        return _dump(
            zadig_request(
                "GET",
                path,
                params={
                    "projectKey": _require("project_key", project_key),
                    "envName": _require("env_name", env_name),
                    "serviceName": _require("service_name", service_name),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_yaml_environment", description="新建 K8s YAML 项目环境（测试或生产）。")
def create_yaml_environment(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    cluster_id: Annotated[str, Field(description="K8s 集群 ID", example="0123456789abcdef12345678")],
    namespace: Annotated[str, Field(description="K8s 命名空间", example="my-project-env-dev")],
    registry_id: Annotated[str, Field(description="镜像仓库 ID", example="630c7ad700430c131062e245")],
    production: Annotated[bool, Field(description="是否创建生产环境", example=False)] = False,
    env_name: Annotated[str, Field(description="生产环境名称，仅生产环境可选", example="")] = "",
    global_variables: Annotated[list[dict[str, Any]], Field(description="全局变量列表", example=[])] = [],
    services: Annotated[list[dict[str, Any]], Field(description="服务列表", example=[])] = [],
    env_configs: Annotated[list[dict[str, Any]], Field(description="环境配置列表", example=[])] = [],
    sub_env: Annotated[dict[str, Any] | None, Field(description="子环境配置 {base_env, enable}", example=None)] = None,
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/environments 或 /openapi/environments/production。"""
    try:
        key = _require("project_key", project_key)
        payload: dict[str, Any] = {
            "env_key": _require("env_key", env_key),
            "cluster_id": _require("cluster_id", cluster_id),
            "namespace": _require("namespace", namespace),
            "registry_id": _require("registry_id", registry_id),
        }
        if production:
            if env_name.strip():
                payload["env_name"] = env_name.strip()
            if sub_env:
                payload["sub_env"] = sub_env
        else:
            if global_variables:
                payload["global_variables"] = global_variables
            if services:
                payload["services"] = services
            if env_configs:
                payload["env_configs"] = env_configs
            if sub_env:
                payload["sub_env"] = sub_env
        return _dump(zadig_request("POST", _env_root(production), params={"projectKey": key}, json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_helm_environment", description="新建 Helm Chart 项目环境。")
def create_helm_environment(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_name: Annotated[str, Field(description="环境标识", example="dev")],
    cluster_id: Annotated[str, Field(description="K8s 集群 ID", example="0123456789abcdef12345678")],
    namespace: Annotated[str, Field(description="K8s 命名空间", example="my-project-env-dev")],
    registry_id: Annotated[str, Field(description="镜像仓库 ID", example="630c7ad700430c131062e245")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
    alias: Annotated[str, Field(description="环境名称/别名", example="")] = "",
    sub_env: Annotated[dict[str, Any] | None, Field(description="子环境配置 {base_env, enable}", example=None)] = None,
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/environments/helm。"""
    try:
        key = _require("project_key", project_key)
        payload: dict[str, Any] = {
            "env_name": _require("env_name", env_name),
            "cluster_id": _require("cluster_id", cluster_id),
            "namespace": _require("namespace", namespace),
            "registry_id": _require("registry_id", registry_id),
            "project_key": key,
            "production": production,
        }
        if alias.strip():
            payload["alias"] = alias.strip()
        if sub_env:
            payload["sub_env"] = sub_env
        return _dump(
            zadig_request("POST", "/openapi/environments/helm", params={"projectKey": key}, json_data=payload)
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_environment", description="编辑环境（K8s YAML 项目），可更新镜像仓库或生产环境名称。")
def update_environment(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    registry_id: Annotated[str, Field(description="镜像仓库 ID", example="630c7ad700430c131062e245")] = "",
    env_name: Annotated[str, Field(description="生产环境名称，仅生产环境可选", example="")] = "",
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/environments/<环境标识>。"""
    try:
        key = _require("project_key", project_key)
        env = _require("env_key", env_key)
        payload: dict[str, Any] = {}
        if registry_id.strip():
            payload["registry_id"] = registry_id.strip()
        elif not production:
            raise ValueError("测试环境更新必须提供 registry_id")
        if production and env_name.strip():
            payload["env_name"] = env_name.strip()
        if not payload:
            raise ValueError("至少提供 registry_id 或 env_name")
        return _dump(
            zadig_request(
                "PUT",
                f"{_env_root(production)}/{_enc(env)}",
                params={"projectKey": key},
                json_data=payload,
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_environment", description="删除环境。测试环境可选择是否同时删除 K8s 命名空间。")
def delete_environment(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    is_delete: Annotated[bool, Field(description="测试环境是否同时删除 K8s 命名空间和服务", example=False)] = False,
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/environments/<环境标识>。"""
    try:
        key = _require("project_key", project_key)
        env = _require("env_key", env_key)
        params: dict[str, Any] = {"projectKey": key}
        if not production:
            params["isDelete"] = str(is_delete).lower()
        return _dump(zadig_request("DELETE", f"{_env_root(production)}/{_enc(env)}", params=params))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="add_yaml_services", description="向 K8s YAML 环境添加服务。")
def add_yaml_services(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    service_list: Annotated[list[dict[str, Any]], Field(description="服务列表，每项含 service_name，可选 variable_kvs")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="添加结果")]:
    """对应 POST /openapi/environments/service/yaml。"""
    try:
        if not service_list:
            raise ValueError("service_list 不能为空")
        path = (
            "/openapi/environments/production/service/yaml"
            if production
            else "/openapi/environments/service/yaml"
        )
        return _dump(
            zadig_request(
                "POST",
                path,
                params={"projectKey": _require("project_key", project_key)},
                json_data={"env_key": _require("env_key", env_key), "service_list": service_list},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="add_helm_services", description="向 Helm 环境添加服务。")
def add_helm_services(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_name: Annotated[str, Field(description="环境标识", example="dev")],
    services: Annotated[list[dict[str, Any]], Field(description="Helm 服务列表，每项需含 service_name、deploy_strategy")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="添加结果")]:
    """对应 POST /openapi/environments/helm/<环境>/services。"""
    try:
        env = _require("env_name", env_name)
        if not services:
            raise ValueError("services 不能为空")
        return _dump(
            zadig_request(
                "POST",
                f"/openapi/environments/helm/{_enc(env)}/services",
                params={"projectKey": _require("project_key", project_key)},
                json_data={"env_name": env, "production": production, "services": services},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_yaml_services", description="更新 K8s YAML 环境中的服务变量。")
def update_yaml_services(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    service_list: Annotated[list[dict[str, Any]], Field(description="服务变量列表，每项含 service_name，可选 variable_kvs")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/environments/<环境>/services。"""
    try:
        if not service_list:
            raise ValueError("service_list 不能为空")
        env = _require("env_key", env_key)
        return _dump(
            zadig_request(
                "PUT",
                f"{_env_root(production)}/{_enc(env)}/services",
                params={"projectKey": _require("project_key", project_key)},
                json_data={"service_list": service_list},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_yaml_services", description="从 K8s YAML 环境删除服务。")
def delete_yaml_services(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    service_names: Annotated[list[str], Field(description="要删除的服务名称列表")],
    not_delete_resource: Annotated[bool, Field(description="是否保留 K8s 资源", example=False)] = False,
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/environments/service/yaml。"""
    try:
        if not service_names:
            raise ValueError("service_names 不能为空")
        path = (
            "/openapi/environments/production/service/yaml"
            if production
            else "/openapi/environments/service/yaml"
        )
        return _dump(
            zadig_request(
                "DELETE",
                path,
                params={"projectKey": _require("project_key", project_key)},
                json_data={
                    "env_key": _require("env_key", env_key),
                    "service_names": service_names,
                    "not_delete_resource": not_delete_resource,
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_environment_variables", description="查看 K8s YAML 环境的全局变量。")
def get_environment_variables(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="全局变量列表")]:
    """对应 GET /openapi/environments/<环境>/variable。"""
    try:
        env = _require("env_key", env_key)
        return _dump(
            zadig_request(
                "GET",
                f"{_env_root(production)}/{_enc(env)}/variable",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_environment_variables", description="更新 K8s YAML 环境的全局变量，关联服务会同步更新。")
def update_environment_variables(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    global_variables: Annotated[list[dict[str, Any]], Field(description="全局变量列表，每项含 key、value")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/environments/<环境>/variable。"""
    try:
        if not global_variables:
            raise ValueError("global_variables 不能为空")
        env = _require("env_key", env_key)
        return _dump(
            zadig_request(
                "PUT",
                f"{_env_root(production)}/{_enc(env)}/variable",
                params={"projectKey": _require("project_key", project_key)},
                json_data={"global_variables": global_variables},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="add_environment_envcfg", description="添加环境配置（ConfigMap/Ingress/Secret/PVC）。")
def add_environment_envcfg(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    name: Annotated[str, Field(description="环境配置名称", example="game-demo")],
    common_env_cfg_type: Annotated[str, Field(description="配置类型：ConfigMap、Ingress、Secret、PVC", example="ConfigMap")],
    yaml_data: Annotated[str, Field(description="环境配置 YAML 内容")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="添加结果")]:
    """对应 POST /openapi/environments/<环境>/envcfgs。"""
    try:
        env = _require("env_key", env_key)
        return _dump(
            zadig_request(
                "POST",
                f"{_env_root(production)}/{_enc(env)}/envcfgs",
                params={"projectKey": _require("project_key", project_key)},
                json_data={
                    "name": _require("name", name),
                    "common_env_cfg_type": _envcfg_type(common_env_cfg_type),
                    "yaml_data": _require("yaml_data", yaml_data),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_environment_envcfgs", description="查看环境配置列表。")
def list_environment_envcfgs(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    cfg_type: Annotated[str, Field(description="配置类型：ConfigMap、Ingress、Secret、PVC", example="ConfigMap")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="环境配置列表")]:
    """对应 GET /openapi/environments/<环境>/envcfgs。"""
    try:
        env = _require("env_key", env_key)
        return _dump(
            zadig_request(
                "GET",
                f"{_env_root(production)}/{_enc(env)}/envcfgs",
                params={
                    "projectKey": _require("project_key", project_key),
                    "type": _envcfg_type(cfg_type),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_environment_envcfg", description="查看环境配置详情。")
def get_environment_envcfg(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    cfg_name: Annotated[str, Field(description="环境配置名称", example="game-demo")],
    cfg_type: Annotated[str, Field(description="配置类型：ConfigMap、Ingress、Secret、PVC", example="ConfigMap")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="环境配置详情")]:
    """对应 GET /openapi/environments/<环境>/envcfg/<名称>。"""
    try:
        env = _require("env_key", env_key)
        name = _require("cfg_name", cfg_name)
        return _dump(
            zadig_request(
                "GET",
                f"{_env_root(production)}/{_enc(env)}/envcfg/{_enc(name)}",
                params={
                    "projectKey": _require("project_key", project_key),
                    "type": _envcfg_type(cfg_type),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_environment_envcfg", description="更新环境配置 YAML。")
def update_environment_envcfg(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    name: Annotated[str, Field(description="环境配置名称", example="game-demo")],
    common_env_cfg_type: Annotated[str, Field(description="配置类型：ConfigMap、Ingress、Secret、PVC", example="ConfigMap")],
    yaml_data: Annotated[str, Field(description="环境配置 YAML 内容")],
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/environments/envcfgs。"""
    try:
        return _dump(
            zadig_request(
                "PUT",
                "/openapi/environments/envcfgs",
                params={"projectKey": _require("project_key", project_key)},
                json_data={
                    "name": _require("name", name),
                    "env_key": _require("env_key", env_key),
                    "common_env_cfg_type": _envcfg_type(common_env_cfg_type),
                    "yaml_data": _require("yaml_data", yaml_data),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_environment_envcfg", description="删除环境配置。")
def delete_environment_envcfg(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    cfg_name: Annotated[str, Field(description="环境配置名称", example="game-demo")],
    cfg_type: Annotated[str, Field(description="配置类型：ConfigMap、Ingress、Secret、PVC", example="ConfigMap")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/environments/<环境>/envcfg/<名称>。"""
    try:
        env = _require("env_key", env_key)
        name = _require("cfg_name", cfg_name)
        return _dump(
            zadig_request(
                "DELETE",
                f"{_env_root(production)}/{_enc(env)}/envcfg/{_enc(name)}",
                params={
                    "projectKey": _require("project_key", project_key),
                    "type": _envcfg_type(cfg_type),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="scale_workload", description="调整服务实例副本数。")
def scale_workload(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境名称", example="dev")],
    workload_name: Annotated[str, Field(description="服务实例名称", example="backend")],
    workload_type: Annotated[str, Field(description="实例类型：Deployment 或 StatefulSet", example="Deployment")],
    target_replicas: Annotated[int, Field(description="目标副本数", example=3)],
) -> Annotated[str, Field(description="调整结果")]:
    """对应 POST /openapi/environments/scale。"""
    try:
        wtype = _require("workload_type", workload_type)
        if wtype not in _SCALE_TYPES:
            raise ValueError("workload_type 必须是 Deployment 或 StatefulSet")
        if target_replicas < 0:
            raise ValueError("target_replicas 不能为负数")
        return _dump(
            zadig_request(
                "POST",
                "/openapi/environments/scale",
                json_data={
                    "project_key": _require("project_key", project_key),
                    "env_key": _require("env_key", env_key),
                    "workload_name": _require("workload_name", workload_name),
                    "workload_type": wtype,
                    "target_replicas": target_replicas,
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_service_pods", description="查看服务当前关联的 Pod 列表。")
def list_service_pods(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="Pod 列表")]:
    """对应 GET /openapi/environments/<环境>/service/<服务>/pods。"""
    try:
        env = _require("env_key", env_key)
        svc = _require("service_name", service_name)
        return _dump(
            zadig_request(
                "GET",
                f"{_env_root(production)}/{_enc(env)}/service/{_enc(svc)}/pods",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="restart_pod", description="重启单个 Pod（删除后由工作负载拉起新 Pod）。")
def restart_pod(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    pod_name: Annotated[str, Field(description="Pod 名称", example="svc-xxx")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="重启结果")]:
    """对应 POST /openapi/environments/<环境>/pod/<Pod>/restart。"""
    try:
        env = _require("env_key", env_key)
        pod = _require("pod_name", pod_name)
        return _dump(
            zadig_request(
                "POST",
                f"{_env_root(production)}/{_enc(env)}/pod/{_enc(pod)}/restart",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="restart_service", description="重启环境中的整个服务实例。")
def restart_service(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
    production: Annotated[bool, Field(description="是否为生产环境", example=False)] = False,
) -> Annotated[str, Field(description="重启结果")]:
    """对应 POST /openapi/environments/<环境>/service/<服务>/restart。"""
    try:
        env = _require("env_key", env_key)
        svc = _require("service_name", service_name)
        return _dump(
            zadig_request(
                "POST",
                f"{_env_root(production)}/{_enc(env)}/service/{_enc(svc)}/restart",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_workload_image", description="更新 Deployment/StatefulSet/CronJob 镜像。")
def update_workload_image(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_name: Annotated[str, Field(description="环境名称", example="dev")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
    name: Annotated[str, Field(description="工作负载名称", example="my-service")],
    container_name: Annotated[str, Field(description="容器名称", example="my-service")],
    image: Annotated[str, Field(description="完整镜像地址", example="repo/app:tag")],
    workload_kind: Annotated[str, Field(description="工作负载种类：deployment、statefulset、cronjob", example="deployment")],
) -> Annotated[str, Field(description="更新结果")]:
    """对应 POST /openapi/environments/image/<kind>/<环境>。"""
    try:
        kind = _require("workload_kind", workload_kind).lower()
        if kind not in _IMAGE_KINDS:
            raise ValueError("workload_kind 必须是 deployment、statefulset 或 cronjob")
        env = _require("env_name", env_name)
        return _dump(
            zadig_request(
                "POST",
                f"/openapi/environments/image/{kind}/{_enc(env)}",
                json_data={
                    "product_name": _require("project_key", project_key),
                    "env_name": env,
                    "service_name": _require("service_name", service_name),
                    "name": _require("name", name),
                    "container_name": _require("container_name", container_name),
                    "image": _require("image", image),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_environment_events", description="列出环境中指定 K8s 对象的事件。")
def list_environment_events(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_name: Annotated[str, Field(description="环境名称", example="dev")],
    name: Annotated[str, Field(description="involvedObject 名称", example="my-service")],
    object_type: Annotated[str, Field(description="involvedObject 类型，如 Deployment", example="Deployment")],
) -> Annotated[str, Field(description="事件列表")]:
    """对应 GET /openapi/environments/kube/events。"""
    try:
        return _dump(
            zadig_request(
                "GET",
                "/openapi/environments/kube/events",
                params={
                    "projectKey": _require("project_key", project_key),
                    "envName": _require("env_name", env_name),
                    "name": _require("name", name),
                    "type": _require("object_type", object_type),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="check_workload_k8s_services", description="检查环境 Workload 是否关联了 K8s Service。")
def check_workload_k8s_services(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
) -> Annotated[str, Field(description="检查结果")]:
    """对应 GET /openapi/environments/<环境>/check/workloads/k8sservices。"""
    try:
        env = _require("env_key", env_key)
        return _dump(
            zadig_request(
                "GET",
                f"/openapi/environments/{_enc(env)}/check/workloads/k8sservices",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="enable_share_env", description="开启子环境。")
def enable_share_env(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
) -> Annotated[str, Field(description="开启结果")]:
    """对应 POST /openapi/environments/<环境>/share/enable。"""
    try:
        env = _require("env_key", env_key)
        return _dump(
            zadig_request(
                "POST",
                f"/openapi/environments/{_enc(env)}/share/enable",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="disable_share_env", description="关闭子环境。")
def disable_share_env(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_key: Annotated[str, Field(description="环境标识", example="dev")],
) -> Annotated[str, Field(description="关闭结果")]:
    """对应 DELETE /openapi/environments/<环境>/share/enable。"""
    try:
        env = _require("env_key", env_key)
        return _dump(
            zadig_request(
                "DELETE",
                f"/openapi/environments/{_enc(env)}/share/enable",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="check_share_env_ready", description="检查子环境 enable/disable 操作是否 Ready。")
def check_share_env_ready(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_name: Annotated[str, Field(description="环境名称", example="dev")],
    op: Annotated[str, Field(description="操作类型：enable 或 disable", example="enable")],
) -> Annotated[str, Field(description="Ready 检查结果")]:
    """对应 GET /openapi/environments/:name/check/sharenv/:op/ready。"""
    try:
        name = _require("env_name", env_name)
        action = _require("op", op).lower()
        if action not in _SHARE_OPS:
            raise ValueError("op 必须是 enable 或 disable")
        return _dump(
            zadig_request(
                "GET",
                f"/openapi/environments/{_enc(name)}/check/sharenv/{action}/ready",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_share_portal_service", description="获取子环境入口服务。")
def get_share_portal_service(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_name: Annotated[str, Field(description="环境名称", example="dev")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
) -> Annotated[str, Field(description="入口服务信息")]:
    """对应 GET /openapi/environments/:name/share/portal/:serviceName。"""
    try:
        name = _require("env_name", env_name)
        svc = _require("service_name", service_name)
        return _dump(
            zadig_request(
                "GET",
                f"/openapi/environments/{_enc(name)}/share/portal/{_enc(svc)}",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="set_share_portal_service", description="设置子环境入口服务。")
def set_share_portal_service(
    project_key: Annotated[str, Field(description="项目标识", example="my-project")],
    env_name: Annotated[str, Field(description="环境名称", example="dev")],
    service_name: Annotated[str, Field(description="服务名称", example="my-service")],
    servers: Annotated[list[dict[str, Any]], Field(description="入口列表，每项含 host、port_number、port_protocol")],
) -> Annotated[str, Field(description="设置结果")]:
    """对应 POST /openapi/environments/:name/share/portal/:serviceName。"""
    try:
        if not servers:
            raise ValueError("servers 不能为空")
        name = _require("env_name", env_name)
        svc = _require("service_name", service_name)
        return _dump(
            zadig_request(
                "POST",
                f"/openapi/environments/{_enc(name)}/share/portal/{_enc(svc)}",
                params={"projectKey": _require("project_key", project_key)},
                json_data=servers,
            )
        )
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

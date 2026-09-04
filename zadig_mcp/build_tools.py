"""Zadig 构建 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/build/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/
"""

from __future__ import annotations

from typing import Any, Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_INFRA = {"kubernetes", "vm"}
_SCRIPT_TYPES = {"shell", "batch_file", "powershell"}
_PARAM_TYPES = {"string", "choice", "multi-select"}
_DOCKERFILE_SOURCES = {"local", "template"}
_ACCESS_MODES = {"ReadWriteOnce", "ReadOnlyMany", "ReadWriteMany", "ReadWriteOncePod"}
_PROVISION_TYPES = {"dynamic", "static", "dynmaic"}


def _require(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


def _enc(value: str) -> str:
    return quote(value, safe="")


def _as_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} 必须是对象")
    return value


def _as_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} 必须是数组")
    return value


def _normalize_inputs(items: list[dict[str, Any]] | None, name: str) -> list[dict[str, Any]]:
    if not items:
        return []
    out: list[dict[str, Any]] = []
    for item in _as_list(items, name):
        if not isinstance(item, dict):
            raise ValueError(f"{name} 中的每一项必须是对象")
        out.append(
            {
                "key": _require(f"{name}.key", item.get("key")),
                "value": str(item.get("value") if item.get("value") is not None else ""),
            }
        )
    return out


def _normalize_repo_info(items: list[dict[str, Any]] | None, name: str = "repo_info") -> list[dict[str, Any]]:
    if not items:
        return []
    out: list[dict[str, Any]] = []
    for item in _as_list(items, name):
        if not isinstance(item, dict):
            raise ValueError(f"{name} 中的每一项必须是对象")
        row: dict[str, Any] = {
            "codehost_name": _require(f"{name}.codehost_name", item.get("codehost_name")),
            "repo_namespace": _require(f"{name}.repo_namespace", item.get("repo_namespace")),
            "repo_name": _require(f"{name}.repo_name", item.get("repo_name")),
            "branch": _require(f"{name}.branch", item.get("branch")),
        }
        checkout_path = str(item.get("checkout_path") or "")
        if checkout_path:
            row["checkout_path"] = checkout_path
        out.append(row)
    return out


def _normalize_services(items: list[dict[str, Any]], name: str = "services") -> list[dict[str, Any]]:
    if not items:
        raise ValueError(f"{name} 不能为空")
    out: list[dict[str, Any]] = []
    for item in _as_list(items, name):
        if not isinstance(item, dict):
            raise ValueError(f"{name} 中的每一项必须是对象")
        out.append(
            {
                "service_name": _require(f"{name}.service_name", item.get("service_name")),
                "service_module": _require(f"{name}.service_module", item.get("service_module")),
            }
        )
    return out


def _normalize_installs(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    out: list[dict[str, Any]] = []
    for item in _as_list(items, "installs"):
        if not isinstance(item, dict):
            raise ValueError("installs 中的每一项必须是对象")
        out.append(
            {
                "name": _require("installs.name", item.get("name")),
                "version": _require("installs.version", item.get("version")),
            }
        )
    return out


def _normalize_parameters(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    out: list[dict[str, Any]] = []
    for item in _as_list(items, "parameters"):
        if not isinstance(item, dict):
            raise ValueError("parameters 中的每一项必须是对象")
        ptype = _require("parameters.type", item.get("type"))
        if ptype not in _PARAM_TYPES:
            raise ValueError("parameters.type 必须是 string、choice 或 multi-select")
        if "default_value" not in item or item.get("default_value") is None:
            raise ValueError("parameters 缺少 default_value")
        row: dict[str, Any] = {
            "key": _require("parameters.key", item.get("key")),
            "type": ptype,
            "default_value": str(item.get("default_value")),
        }
        if item.get("is_credential") is not None:
            row["is_credential"] = bool(item.get("is_credential"))
        if item.get("description") is not None:
            row["description"] = str(item.get("description") or "")
        if item.get("choice_option") is not None:
            row["choice_option"] = [str(v) for v in _as_list(item.get("choice_option"), "parameters.choice_option")]
        if item.get("choice_value") is not None:
            row["choice_value"] = [str(v) for v in _as_list(item.get("choice_value"), "parameters.choice_value")]
        out.append(row)
    return out


def _normalize_docker_build_step(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    item = _as_dict(value, "docker_build_step")
    source = _require("docker_build_step.dockerfile_source", item.get("dockerfile_source"))
    if source not in _DOCKERFILE_SOURCES:
        raise ValueError("dockerfile_source 必须是 local 或 template")
    row: dict[str, Any] = {
        "dockerfile_source": source,
        "build_context_dir": _require("docker_build_step.build_context_dir", item.get("build_context_dir")),
        "dockerfile_directory": _require(
            "docker_build_step.dockerfile_directory", item.get("dockerfile_directory")
        ),
    }
    if item.get("build_args") is not None:
        row["build_args"] = str(item.get("build_args") or "")
    template_name = str(item.get("template_name") or "")
    if source == "template":
        row["template_name"] = _require("docker_build_step.template_name", template_name)
    elif template_name:
        row["template_name"] = template_name
    if "enable_buildkit" in item:
        row["enable_buildkit"] = bool(item.get("enable_buildkit"))
    if item.get("platforms") is not None:
        row["platforms"] = str(item.get("platforms") or "")
    return row


def _normalize_resource_spec(value: dict[str, Any]) -> dict[str, Any]:
    item = _as_dict(value, "resource_spec")
    row: dict[str, Any] = {
        "cpu_req": int(item.get("cpu_req")),
        "cpu_limit": int(item.get("cpu_limit")),
        "memory_req": int(item.get("memory_req")),
        "memory_limit": int(item.get("memory_limit")),
    }
    if item.get("gpu_limit") is not None:
        row["gpu_limit"] = str(item.get("gpu_limit") or "")
    return row


def _normalize_cache_setting(value: dict[str, Any]) -> dict[str, Any]:
    item = _as_dict(value, "cache_setting")
    if "enabled" not in item:
        raise ValueError("cache_setting.enabled 不能为空")
    return {
        "enabled": bool(item.get("enabled")),
        "cache_dir": _require("cache_setting.cache_dir", item.get("cache_dir")),
    }


def _normalize_storages(value: dict[str, Any]) -> dict[str, Any]:
    item = _as_dict(value, "storages")
    if "enabled" not in item:
        raise ValueError("storages.enabled 不能为空")
    props = _as_list(item.get("storages_properties") or [], "storages.storages_properties")
    if bool(item.get("enabled")) and not props:
        raise ValueError("启用存储时 storages_properties 不能为空")
    out_props: list[dict[str, Any]] = []
    for prop in props:
        if not isinstance(prop, dict):
            raise ValueError("storages_properties 中的每一项必须是对象")
        provision = _require("storages_properties.provision_type", prop.get("provision_type"))
        if provision not in _PROVISION_TYPES:
            raise ValueError("provision_type 必须是 dynamic 或 static")
        if provision == "dynmaic":
            provision = "dynamic"
        row: dict[str, Any] = {
            "mount_path": _require("storages_properties.mount_path", prop.get("mount_path")),
            "provision_type": provision,
            "subpath": _require("storages_properties.subpath", prop.get("subpath")),
        }
        if "storage_size_in_gib" in prop and prop.get("storage_size_in_gib") is not None:
            row["storage_size_in_gib"] = int(prop.get("storage_size_in_gib"))
        elif provision == "dynamic":
            raise ValueError("dynamic 存储需要 storage_size_in_gib")
        if prop.get("access_mode"):
            mode = str(prop.get("access_mode"))
            if mode not in _ACCESS_MODES:
                raise ValueError(
                    "access_mode 必须是 ReadWriteOnce、ReadOnlyMany、ReadWriteMany 或 ReadWriteOncePod"
                )
            row["access_mode"] = mode
        if prop.get("is_temporary") is not None:
            row["is_temporary"] = bool(prop.get("is_temporary"))
        if prop.get("pvc"):
            row["pvc"] = str(prop.get("pvc"))
        if prop.get("storage_class"):
            row["storage_class"] = str(prop.get("storage_class"))
        out_props.append(row)
    return {"enabled": bool(item.get("enabled")), "storages_properties": out_props}


def _normalize_advanced_settings(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    item = _as_dict(value, "advanced_settings")
    row: dict[str, Any] = {}
    if item.get("cluster_name"):
        row["cluster_name"] = str(item.get("cluster_name")).strip()
    if item.get("strategy_name"):
        row["strategy_name"] = str(item.get("strategy_name")).strip()
    if item.get("timeout") is not None:
        row["timeout"] = int(item.get("timeout"))
    if item.get("resource_spec"):
        row["resource_spec"] = _normalize_resource_spec(item.get("resource_spec"))
    if item.get("use_host_docker_daemon") is not None:
        row["use_host_docker_daemon"] = bool(item.get("use_host_docker_daemon"))
    if item.get("privileged_mode") is not None:
        row["privileged_mode"] = bool(item.get("privileged_mode"))
    if item.get("cache_setting"):
        row["cache_setting"] = _normalize_cache_setting(item.get("cache_setting"))
    if item.get("storages"):
        row["storages"] = _normalize_storages(item.get("storages"))
    annotations = _normalize_inputs(item.get("custom_annotations"), "custom_annotations")
    if annotations:
        row["custom_annotations"] = annotations
    labels = _normalize_inputs(item.get("custom_labels"), "custom_labels")
    if labels:
        row["custom_labels"] = labels
    if item.get("outputs") is not None:
        row["outputs"] = [str(v) for v in _as_list(item.get("outputs"), "outputs")]
    return row


def _build_definition_payload(
    *,
    name: str,
    project_key: str,
    infrastructure: str,
    build_os: str,
    installs: list[dict[str, Any]] | None,
    script_type: str,
    build_script: str,
    services: list[dict[str, Any]],
    repo_info: list[dict[str, Any]] | None,
    parameters: list[dict[str, Any]] | None,
    docker_build_step: dict[str, Any] | None,
    advanced_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    infra = _require("infrastructure", infrastructure)
    if infra not in _INFRA:
        raise ValueError("infrastructure 必须是 kubernetes 或 vm")
    stype = _require("script_type", script_type)
    if stype not in _SCRIPT_TYPES:
        raise ValueError("script_type 必须是 shell、batch_file 或 powershell")
    payload: dict[str, Any] = {
        "name": _require("name", name),
        "project_key": _require("project_key", project_key),
        "infrastructure": infra,
        "build_os": _require("build_os", build_os),
        "installs": _normalize_installs(installs),
        "script_type": stype,
        "build_script": _require("build_script", build_script),
        "services": _normalize_services(services),
    }
    repos = _normalize_repo_info(repo_info)
    if repos:
        payload["repo_info"] = repos
    params = _normalize_parameters(parameters)
    if params:
        payload["parameters"] = params
    docker_step = _normalize_docker_build_step(docker_build_step)
    if docker_step:
        payload["docker_build_step"] = docker_step
    settings = _normalize_advanced_settings(advanced_settings)
    if settings:
        payload["advanced_settings"] = settings
    return payload


def _normalize_target_services(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise ValueError("target_services 不能为空")
    out: list[dict[str, Any]] = []
    for item in _as_list(items, "target_services"):
        if not isinstance(item, dict):
            raise ValueError("target_services 中的每一项必须是对象")
        repos = _normalize_repo_info(item.get("repo_info"), "target_services.repo_info")
        if not repos:
            raise ValueError("target_services.repo_info 不能为空")
        inputs = _normalize_inputs(item.get("inputs"), "target_services.inputs")
        if not inputs:
            raise ValueError("target_services.inputs 不能为空")
        out.append(
            {
                "service_name": _require("target_services.service_name", item.get("service_name")),
                "service_module": _require("target_services.service_module", item.get("service_module")),
                "repo_info": repos,
                "inputs": inputs,
            }
        )
    return out


@mcp.tool(name="create_build", description="新建构建配置，绑定服务组件、代码库和构建脚本。")
def create_build(
    project_key: Annotated[str, Field(description="项目标识", example="yaml")],
    name: Annotated[str, Field(description="构建名称", example="api-test")],
    infrastructure: Annotated[str, Field(description="基础设施：kubernetes 或 vm", example="kubernetes")],
    build_os: Annotated[str, Field(description="构建操作系统", example="ubuntu 20.04")],
    script_type: Annotated[str, Field(description="脚本类型：shell、batch_file、powershell", example="shell")],
    build_script: Annotated[str, Field(description="构建脚本内容", example="#!/bin/bash\nset -e\n")],
    services: Annotated[
        list[dict[str, Any]],
        Field(
            description="绑定的服务列表，每项含 service_name、service_module",
            example=[{"service_name": "service1", "service_module": "service1"}],
        ),
    ],
    installs: Annotated[
        list[dict[str, Any]],
        Field(description="依赖软件包列表，每项含 name、version；可选，可传空列表", example=[{"name": "go", "version": "1.20.7"}]),
    ] = [],
    repo_info: Annotated[
        list[dict[str, Any]],
        Field(
            description="代码信息，每项含 codehost_name、repo_namespace、repo_name、branch，可选 checkout_path",
            example=[{"codehost_name": "gitlab", "repo_namespace": "kr-test-org1", "repo_name": "multi-service-demo", "branch": "main"}],
        ),
    ] = [],
    parameters: Annotated[
        list[dict[str, Any]],
        Field(
            description="自定义变量，每项含 key、type（string/choice/multi-select）、default_value，可选 is_credential、description、choice_option、choice_value",
            example=[{"key": "bb", "type": "string", "default_value": "abc123", "is_credential": False}],
        ),
    ] = [],
    docker_build_step: Annotated[
        dict[str, Any] | None,
        Field(
            description="镜像构建步骤，需 dockerfile_source（local/template）、build_context_dir、dockerfile_directory；可选 build_args、template_name、enable_buildkit、platforms",
            example={"dockerfile_source": "local", "build_context_dir": "$REPONAME_0", "dockerfile_directory": "$REPONAME_0/Dockerfile"},
        ),
    ] = None,
    advanced_settings: Annotated[
        dict[str, Any] | None,
        Field(description="高级设置，可含 cluster_name、strategy_name、timeout、resource_spec、cache_setting、storages、custom_annotations、custom_labels、outputs 等", example=None),
    ] = None,
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/build。"""
    try:
        key = _require("project_key", project_key)
        payload = _build_definition_payload(
            name=name,
            project_key=key,
            infrastructure=infrastructure,
            build_os=build_os,
            installs=installs,
            script_type=script_type,
            build_script=build_script,
            services=services,
            repo_info=repo_info,
            parameters=parameters,
            docker_build_step=docker_build_step,
            advanced_settings=advanced_settings,
        )
        return _dump(zadig_request("POST", "/openapi/build", params={"projectKey": key}, json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_build", description="更新已有构建配置（完整覆盖，字段与新建构建相同）。")
def update_build(
    project_key: Annotated[str, Field(description="项目标识", example="yaml")],
    name: Annotated[str, Field(description="构建名称", example="api-test")],
    infrastructure: Annotated[str, Field(description="基础设施：kubernetes 或 vm", example="kubernetes")],
    build_os: Annotated[str, Field(description="构建操作系统", example="ubuntu 20.04")],
    script_type: Annotated[str, Field(description="脚本类型：shell、batch_file、powershell", example="shell")],
    build_script: Annotated[str, Field(description="构建脚本内容", example="#!/bin/bash\nset -e\n")],
    services: Annotated[
        list[dict[str, Any]],
        Field(
            description="绑定的服务列表，每项含 service_name、service_module",
            example=[{"service_name": "service1", "service_module": "service1"}],
        ),
    ],
    installs: Annotated[
        list[dict[str, Any]],
        Field(description="依赖软件包列表，每项含 name、version；可选，可传空列表", example=[{"name": "go", "version": "1.20.7"}]),
    ] = [],
    repo_info: Annotated[
        list[dict[str, Any]],
        Field(
            description="代码信息，每项含 codehost_name、repo_namespace、repo_name、branch，可选 checkout_path",
            example=[{"codehost_name": "gitlab", "repo_namespace": "kr-test-org1", "repo_name": "multi-service-demo", "branch": "main"}],
        ),
    ] = [],
    parameters: Annotated[
        list[dict[str, Any]],
        Field(
            description="自定义变量，每项含 key、type（string/choice/multi-select）、default_value，可选 is_credential、description、choice_option、choice_value",
            example=[{"key": "bb", "type": "string", "default_value": "abc123", "is_credential": False}],
        ),
    ] = [],
    docker_build_step: Annotated[
        dict[str, Any] | None,
        Field(
            description="镜像构建步骤，需 dockerfile_source（local/template）、build_context_dir、dockerfile_directory",
            example={"dockerfile_source": "local", "build_context_dir": "$REPONAME_0", "dockerfile_directory": "$REPONAME_0/Dockerfile"},
        ),
    ] = None,
    advanced_settings: Annotated[
        dict[str, Any] | None,
        Field(description="高级设置，可含 cluster_name、timeout、resource_spec、cache_setting、storages 等", example=None),
    ] = None,
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/build。"""
    try:
        key = _require("project_key", project_key)
        payload = _build_definition_payload(
            name=name,
            project_key=key,
            infrastructure=infrastructure,
            build_os=build_os,
            installs=installs,
            script_type=script_type,
            build_script=build_script,
            services=services,
            repo_info=repo_info,
            parameters=parameters,
            docker_build_step=docker_build_step,
            advanced_settings=advanced_settings,
        )
        return _dump(zadig_request("PUT", "/openapi/build", params={"projectKey": key}, json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_build_from_template", description="使用构建模板新建构建，并为服务绑定代码库和变量。")
def create_build_from_template(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    name: Annotated[str, Field(description="构建名称", example="demo-build")],
    template_name: Annotated[str, Field(description="构建模板名称", example="demo-template")],
    target_services: Annotated[
        list[dict[str, Any]],
        Field(
            description="服务配置，每项含 service_name、service_module、repo_info、inputs",
            example=[
                {
                    "service_name": "zadigx",
                    "service_module": "aslan",
                    "repo_info": [
                        {
                            "codehost_name": "github-demo",
                            "repo_namespace": "kr-test-org",
                            "repo_name": "zadig",
                            "branch": "main",
                        }
                    ],
                    "inputs": [{"key": "name", "value": "admin"}],
                }
            ],
        ),
    ],
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/build?source=template。"""
    try:
        key = _require("project_key", project_key)
        payload = {
            "name": _require("name", name),
            "project_key": key,
            "template_name": _require("template_name", template_name),
            "target_services": _normalize_target_services(target_services),
        }
        return _dump(
            zadig_request("POST", "/openapi/build", params={"source": "template"}, json_data=payload)
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_template_build", description="更新从模板创建的构建（服务绑定、代码库和变量）。")
def update_template_build(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    name: Annotated[str, Field(description="构建名称", example="demo-build")],
    template_name: Annotated[str, Field(description="构建模板名称", example="demo-template")],
    target_services: Annotated[
        list[dict[str, Any]],
        Field(
            description="服务配置，每项含 service_name、service_module、repo_info、inputs",
            example=[
                {
                    "service_name": "zadigx",
                    "service_module": "aslan",
                    "repo_info": [
                        {
                            "codehost_name": "github-demo",
                            "repo_namespace": "kr-test-org",
                            "repo_name": "zadig",
                            "branch": "main",
                        }
                    ],
                    "inputs": [{"key": "name", "value": "admin"}],
                }
            ],
        ),
    ],
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/build/<构建名称>/template。"""
    try:
        key = _require("project_key", project_key)
        build_name = _require("name", name)
        payload = {
            "name": build_name,
            "project_key": key,
            "template_name": _require("template_name", template_name),
            "target_services": _normalize_target_services(target_services),
        }
        return _dump(
            zadig_request(
                "PUT",
                f"/openapi/build/{_enc(build_name)}/template",
                params={"projectKey": key},
                json_data=payload,
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_builds", description="分页查询项目下的构建列表。")
def list_builds(
    project_key: Annotated[str, Field(description="项目标识", example="lilian-test")],
    page_num: Annotated[int, Field(description="当前页数", example=1)] = 1,
    page_size: Annotated[int, Field(description="每页条数", example=20)] = 20,
) -> Annotated[str, Field(description="构建列表")]:
    """对应 GET /openapi/build。"""
    try:
        return _dump(
            zadig_request(
                "GET",
                "/openapi/build",
                params={
                    "projectKey": _require("project_key", project_key),
                    "pageNum": page_num if page_num > 0 else 1,
                    "pageSize": page_size if page_size > 0 else 20,
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_build", description="获取指定构建详情，需同时指定服务名称和组件名称。")
def get_build(
    project_key: Annotated[str, Field(description="项目标识", example="lilian-test")],
    build_name: Annotated[str, Field(description="构建名称", example="openapi-build")],
    service_name: Annotated[str, Field(description="服务名称", example="service1")],
    service_module: Annotated[str, Field(description="服务组件名称", example="service1")],
) -> Annotated[str, Field(description="构建详情")]:
    """对应 GET /openapi/build/:buildName/detail。"""
    try:
        name = _require("build_name", build_name)
        return _dump(
            zadig_request(
                "GET",
                f"/openapi/build/{_enc(name)}/detail",
                params={
                    "projectKey": _require("project_key", project_key),
                    "serviceName": _require("service_name", service_name),
                    "serviceModule": _require("service_module", service_module),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_build", description="删除指定构建。")
def delete_build(
    project_key: Annotated[str, Field(description="项目标识", example="lilian-test")],
    name: Annotated[str, Field(description="构建名称", example="openapi-build")],
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/build。"""
    try:
        return _dump(
            zadig_request(
                "DELETE",
                "/openapi/build",
                params={
                    "name": _require("name", name),
                    "projectKey": _require("project_key", project_key),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

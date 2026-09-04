"""Zadig 工作流 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/workflow/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/

未实现 SSE 实时日志（GET /openapi/logs/sse/v4/workflow/...），请用完整日志接口。
"""

from __future__ import annotations

import copy
import json
from typing import Any, Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_PARAM_TYPES = {"string", "text", "choice", "repo"}
_JOB_TYPES = {
    "zadig-build",
    "zadig-deploy",
    "custom-deploy",
    "freestyle",
    "zadig-test",
    "zadig-scanning",
    "sql",
    "tapd",
    "approval",
    "plugin",
}
_NOTIFY_TYPES = {
    "feishu",
    "feishu_app",
    "feishu_person",
    "wechat",
    "dingding",
    "msteams",
    "mail",
}
_VIEW_TYPES = {"custom"}
_TICKET_STATUS = {0, 1}
_DEFAULT_WORKFLOW_TEMPLATE = "workflow_build_deploy"


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


def _normalize_repo(item: dict[str, Any], name: str) -> dict[str, Any]:
    repo = _as_dict(item, name)
    row: dict[str, Any] = {
        "codehost_name": _require(f"{name}.codehost_name", repo.get("codehost_name")),
        "repo_namespace": _require(f"{name}.repo_namespace", repo.get("repo_namespace")),
        "repo_name": _require(f"{name}.repo_name", repo.get("repo_name")),
    }
    branch = str(repo.get("branch") or "").strip()
    if branch:
        row["branch"] = branch
    if repo.get("pr") is not None:
        row["pr"] = int(repo.get("pr"))
    if repo.get("prs") is not None:
        row["prs"] = [int(v) for v in _as_list(repo.get("prs"), f"{name}.prs")]
    if repo.get("enable_commit") is not None:
        row["enable_commit"] = bool(repo.get("enable_commit"))
    if repo.get("commit_id"):
        row["commit_id"] = str(repo.get("commit_id")).strip()
        if row.get("enable_commit") and not row["commit_id"]:
            raise ValueError(f"{name}.commit_id 在 enable_commit 为 true 时不能为空")
    if repo.get("remote_name"):
        row["remote_name"] = str(repo.get("remote_name")).strip()
    if repo.get("checkout_path"):
        row["checkout_path"] = str(repo.get("checkout_path"))
    if repo.get("submodules") is not None:
        row["submodules"] = bool(repo.get("submodules"))
    if not row.get("branch") and repo.get("pr") is None and not row.get("enable_commit"):
        raise ValueError(f"{name} 需要 branch、pr 或 enable_commit+commit_id 之一")
    return row


def _normalize_parameters(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    out: list[dict[str, Any]] = []
    for item in _as_list(items, "parameters"):
        if not isinstance(item, dict):
            raise ValueError("parameters 中的每一项必须是对象")
        ptype = _require("parameters.type", item.get("type"))
        if ptype not in _PARAM_TYPES:
            raise ValueError("parameters.type 必须是 string、text、choice 或 repo")
        row: dict[str, Any] = {
            "name": _require("parameters.name", item.get("name")),
            "type": ptype,
        }
        if ptype == "repo":
            if not item.get("repo"):
                raise ValueError("type 为 repo 时必须提供 repo")
            row["repo"] = _normalize_repo(item.get("repo"), "parameters.repo")
        else:
            if item.get("value") is None:
                raise ValueError(f"参数 {row['name']} 缺少 value")
            row["value"] = str(item.get("value"))
        out.append(row)
    return out


def _normalize_run_inputs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise ValueError("inputs 不能为空")
    out: list[dict[str, Any]] = []
    for item in _as_list(items, "inputs"):
        if not isinstance(item, dict):
            raise ValueError("inputs 中的每一项必须是对象")
        job_type = _require("inputs.job_type", item.get("job_type"))
        if job_type not in _JOB_TYPES:
            raise ValueError(
                "job_type 必须是 zadig-build、zadig-deploy、custom-deploy、freestyle、"
                "zadig-test、zadig-scanning、sql、tapd、approval 或 plugin"
            )
        params = item.get("parameters")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError("inputs.parameters 必须是对象")
        out.append(
            {
                "job_name": _require("inputs.job_name", item.get("job_name")),
                "job_type": job_type,
                "parameters": params,
            }
        )
    return out


def _normalize_notify_inputs(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    out: list[dict[str, Any]] = []
    for item in _as_list(items, "notify_inputs"):
        if not isinstance(item, dict):
            raise ValueError("notify_inputs 中的每一项必须是对象")
        if item.get("id") is None:
            raise ValueError("notify_inputs.id 不能为空，从 0 开始表示工作流中第几个通知")
        ntype = _require("notify_inputs.type", item.get("type"))
        if ntype not in _NOTIFY_TYPES:
            raise ValueError(
                "notify_inputs.type 必须是 feishu、feishu_app、feishu_person、wechat、dingding、msteams 或 mail"
            )
        row = dict(item)
        row["id"] = int(item.get("id"))
        row["type"] = ntype
        out.append(row)
    return out


def _normalize_stages(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    out: list[dict[str, Any]] = []
    for item in _as_list(items, "stages"):
        if not isinstance(item, dict):
            raise ValueError("stages 中的每一项必须是对象")
        jobs = item.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise ValueError("stages.jobs 不能为空")
        row: dict[str, Any] = {
            "name": _require("stages.name", item.get("name")),
            "parallel": bool(item.get("parallel", False)),
            "jobs": jobs,
        }
        if item.get("approval"):
            row["approval"] = _as_dict(item.get("approval"), "stages.approval")
        out.append(row)
    return out


def _fill_placeholders(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        for key, replacement in mapping.items():
            value = value.replace("{" + key + "}", replacement)
        return value
    if isinstance(value, list):
        return [_fill_placeholders(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: _fill_placeholders(item, mapping) for key, item in value.items()}
    return value


def _load_workflow_template(template_name: str = _DEFAULT_WORKFLOW_TEMPLATE) -> dict[str, Any]:
    from utils.template_store import load_template_body

    try:
        from webapi.templates_catalog import get_template_body

        return get_template_body(template_name)
    except Exception:
        return load_template_body(template_name)


def _set_deploy_production(payload: dict[str, Any], production: bool) -> None:
    for stage in payload.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        for job in stage.get("jobs") or []:
            if not isinstance(job, dict):
                continue
            if job.get("type") != "zadig-deploy":
                continue
            spec = job.get("spec")
            if isinstance(spec, dict):
                spec["production"] = bool(production)


def _workflow_from_template(
    *,
    project: str,
    workflow_name: str,
    display_name: str,
    registry_id: str,
    service_name: str,
    build_name: str,
    image_name: str,
    env_name: str,
    concurrency_limit: int,
    description: str = "",
    template_name: str = _DEFAULT_WORKFLOW_TEMPLATE,
    production: bool = False,
) -> dict[str, Any]:
    payload = _fill_placeholders(
        copy.deepcopy(_load_workflow_template(template_name)),
        {
            "workflow_name": workflow_name,
            "registry_id": registry_id,
            "service_name": service_name,
            "build_name": build_name,
            "image_name": image_name,
            "env_name": env_name,
        },
    )
    payload["name"] = workflow_name
    payload["display_name"] = display_name
    payload["project"] = project
    payload["concurrency_limit"] = int(concurrency_limit)
    _set_deploy_production(payload, production)
    if description.strip():
        payload["description"] = description.strip()
    return payload


def _workflow_definition(
    *,
    name: str,
    display_name: str,
    project: str,
    concurrency_limit: int,
    description: str = "",
    stages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": _require("name", name),
        "display_name": _require("display_name", display_name),
        "project": _require("project", project),
        "concurrency_limit": int(concurrency_limit),
    }
    if description.strip():
        payload["description"] = description.strip()
    stage_list = _normalize_stages(stages)
    if stage_list:
        payload["stages"] = stage_list
    return payload


def _normalize_view_workflows(items: list[dict[str, Any]], *, require_enabled: bool) -> list[dict[str, Any]]:
    if not items:
        raise ValueError("workflow_list 不能为空")
    out: list[dict[str, Any]] = []
    for item in _as_list(items, "workflow_list"):
        if not isinstance(item, dict):
            raise ValueError("workflow_list 中的每一项必须是对象")
        wtype = _require("workflow_list.workflow_type", item.get("workflow_type"))
        if wtype not in _VIEW_TYPES:
            raise ValueError("workflow_type 必须是 custom")
        row: dict[str, Any] = {
            "workflow_key": _require("workflow_list.workflow_key", item.get("workflow_key")),
            "workflow_type": wtype,
        }
        if require_enabled:
            if "enabled" not in item:
                raise ValueError("编辑视图时 workflow_list.enabled 不能为空")
            row["enabled"] = bool(item.get("enabled"))
        out.append(row)
    return out


@mcp.tool(name="list_workflows", description="获取项目下的工作流列表，可按视图过滤。")
def list_workflows(
    project_key: Annotated[str, Field(description="项目标识", example="lilian-test")],
    view_name: Annotated[str, Field(description="工作流视图名称，可选", example="")] = "",
) -> Annotated[str, Field(description="工作流列表")]:
    """对应 GET /openapi/workflows。"""
    try:
        params: dict[str, Any] = {"projectKey": _require("project_key", project_key)}
        if view_name.strip():
            params["viewName"] = view_name.strip()
        return _dump(zadig_request("GET", "/openapi/workflows", params=params))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_workflow", description="获取指定自定义工作流详情，含参数、阶段和任务配置。")
def get_workflow(
    project_key: Annotated[str, Field(description="项目标识", example="lilian-test")],
    workflow_key: Annotated[str, Field(description="工作流标识", example="build-deploy")],
) -> Annotated[str, Field(description="工作流详情")]:
    """对应 GET /openapi/workflows/custom/:workflowKey/detail。"""
    try:
        key = _require("workflow_key", workflow_key)
        return _dump(
            zadig_request(
                "GET",
                f"/openapi/workflows/custom/{_enc(key)}/detail",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_workflow_tasks", description="分页查询指定工作流的任务列表。")
def list_workflow_tasks(
    project_key: Annotated[str, Field(description="项目标识", example="lilian-test")],
    workflow_key: Annotated[str, Field(description="工作流标识", example="build-deploy")],
    page_num: Annotated[int, Field(description="当前页数", example=1)] = 1,
    page_size: Annotated[int, Field(description="每页条数", example=50)] = 50,
) -> Annotated[str, Field(description="工作流任务列表")]:
    """对应 GET /openapi/workflows/custom/:workflowKey/tasks。"""
    try:
        key = _require("workflow_key", workflow_key)
        return _dump(
            zadig_request(
                "GET",
                f"/openapi/workflows/custom/{_enc(key)}/tasks",
                params={
                    "projectKey": _require("project_key", project_key),
                    "pageNum": page_num if page_num > 0 else 1,
                    "pageSize": page_size if page_size > 0 else 50,
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_workflow_task", description="获取指定工作流任务详情，含各阶段和 Job 执行信息。")
def get_workflow_task(
    workflow_key: Annotated[str, Field(description="工作流标识", example="build-images")],
    task_id: Annotated[int, Field(description="工作流任务 ID", example=24)],
) -> Annotated[str, Field(description="工作流任务详情")]:
    """对应 GET /openapi/workflows/custom/task。"""
    try:
        return _dump(
            zadig_request(
                "GET",
                "/openapi/workflows/custom/task",
                params={
                    "workflowKey": _require("workflow_key", workflow_key),
                    "taskId": int(task_id),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(
    name="run_workflow",
    description="执行自定义工作流。inputs 按 Job 类型传入构建、部署、测试、扫描、脚本、SQL 等参数。",
)
def run_workflow(
    project_key: Annotated[str, Field(description="项目标识", example="helm")],
    workflow_key: Annotated[str, Field(description="工作流标识", example="test-openapi")],
    inputs: Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "执行参数，每项含 job_name、job_type、parameters。"
                "job_type 支持 zadig-build、zadig-deploy、custom-deploy、freestyle、"
                "zadig-test、zadig-scanning、sql、tapd、approval、plugin"
            ),
            example=[{"job_name": "build-myapps", "job_type": "zadig-build", "parameters": {"service_list": []}}],
        ),
    ],
    parameters: Annotated[
        list[dict[str, Any]],
        Field(
            description="全局变量，每项含 name、type（string/text/choice/repo）；string/text/choice 用 value，repo 用 repo 对象",
            example=[{"name": "test", "type": "string", "value": "zadig"}],
        ),
    ] = [],
    notify_inputs: Annotated[
        list[dict[str, Any]],
        Field(
            description="通知覆盖参数，每项含 id（从 0 开始）、type（feishu/feishu_app/feishu_person/wechat/dingding/msteams/mail）及对应配置",
            example=[],
        ),
    ] = [],
) -> Annotated[str, Field(description="执行结果，含 task_id")]:
    """对应 POST /openapi/workflows/custom/task。"""
    try:
        payload: dict[str, Any] = {
            "project_key": _require("project_key", project_key),
            "workflow_key": _require("workflow_key", workflow_key),
            "inputs": _normalize_run_inputs(inputs),
        }
        params = _normalize_parameters(parameters)
        if params:
            payload["parameters"] = params
        notifies = _normalize_notify_inputs(notify_inputs)
        if notifies:
            payload["notify_inputs"] = notifies
        return _dump(zadig_request("POST", "/openapi/workflows/custom/task", json_data=payload, timeout=90.0))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="cancel_workflow_task", description="取消尚未结束的工作流任务。")
def cancel_workflow_task(
    workflow_key: Annotated[str, Field(description="工作流标识", example="build-images")],
    task_id: Annotated[int, Field(description="工作流任务 ID", example=20)],
) -> Annotated[str, Field(description="取消结果")]:
    """对应 DELETE /openapi/workflows/custom/task。"""
    try:
        return _dump(
            zadig_request(
                "DELETE",
                "/openapi/workflows/custom/task",
                params={
                    "workflowKey": _require("workflow_key", workflow_key),
                    "taskId": int(task_id),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="retry_workflow_task", description="重试指定工作流任务。")
def retry_workflow_task(
    project_key: Annotated[str, Field(description="项目标识", example="lilian-test")],
    workflow_key: Annotated[str, Field(description="工作流标识", example="build-deploy")],
    task_id: Annotated[int, Field(description="工作流任务 ID", example=15)],
) -> Annotated[str, Field(description="重试结果")]:
    """对应 POST /openapi/workflows/custom/:workflowKey/task/:taskID。"""
    try:
        key = _require("workflow_key", workflow_key)
        return _dump(
            zadig_request(
                "POST",
                f"/openapi/workflows/custom/{_enc(key)}/task/{int(task_id)}",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="approve_workflow_task", description="审批工作流任务的指定阶段（Zadig 原生审批）。")
def approve_workflow_task(
    workflow_key: Annotated[str, Field(description="工作流标识", example="infra-dev-workflow")],
    task_id: Annotated[int, Field(description="工作流任务 ID", example=2)],
    stage_name: Annotated[str, Field(description="待审批的阶段名称", example="deploy")],
    approve: Annotated[bool, Field(description="是否审批通过", example=True)] = False,
    comment: Annotated[str, Field(description="审批意见", example="LGTM")] = "",
) -> Annotated[str, Field(description="审批结果")]:
    """对应 POST /openapi/workflows/custom/task/approve。"""
    try:
        payload: dict[str, Any] = {
            "workflow_key": _require("workflow_key", workflow_key),
            "task_id": int(task_id),
            "stage_name": _require("stage_name", stage_name),
            "approve": approve,
        }
        if comment.strip():
            payload["comment"] = comment.strip()
        return _dump(zadig_request("POST", "/openapi/workflows/custom/task/approve", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(
    name="create_workflow",
    description="按内置构建+部署模板创建工作流，绑定镜像仓库、服务、构建配置和部署环境。",
)
def create_workflow(
    project: Annotated[str, Field(description="项目标识", example="demo")],
    name: Annotated[str, Field(description="工作流标识", example="demo-build-deploy")],
    registry_id: Annotated[str, Field(description="镜像仓库 ID", example="630c7ad700430c131062e245")],
    service_name: Annotated[str, Field(description="服务名称，同时作为服务组件名", example="myservice")],
    build_name: Annotated[str, Field(description="构建名称", example="myservice-build")],
    image_name: Annotated[str, Field(description="镜像名称", example="myservice")],
    display_name: Annotated[str, Field(description="工作流显示名称，默认与标识相同", example="")] = "",
    env_name: Annotated[str, Field(description="部署环境标识", example="dev")] = "dev",
    concurrency_limit: Annotated[int, Field(description="任务并发数，-1 无限制，0 不可执行", example=1)] = 1,
    description: Annotated[str, Field(description="工作流描述", example="")] = "",
    template_name: Annotated[
        str,
        Field(description="Agent 模板标识，默认 workflow_build_deploy", example="workflow_build_deploy"),
    ] = _DEFAULT_WORKFLOW_TEMPLATE,
    production: Annotated[
        bool,
        Field(description="是否部署到生产环境，false 为测试环境", example=False),
    ] = False,
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /api/aslan/workflow/v4。

    使用 templates/workflow_build_deploy.json：构建阶段 zadig-build，部署阶段 zadig-deploy（镜像来自构建任务）。
    """
    try:
        workflow_name = _require("name", name)
        payload = _workflow_from_template(
            project=_require("project", project),
            workflow_name=workflow_name,
            display_name=display_name.strip() or workflow_name,
            registry_id=_require("registry_id", registry_id),
            service_name=_require("service_name", service_name),
            build_name=_require("build_name", build_name),
            image_name=_require("image_name", image_name),
            env_name=_require("env_name", env_name),
            concurrency_limit=concurrency_limit,
            description=description,
            template_name=template_name.strip() or _DEFAULT_WORKFLOW_TEMPLATE,
            production=production,
        )
        return _dump(zadig_request("POST", "/api/aslan/workflow/v4", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(
    name="update_workflow",
    description="更新自定义工作流，body 与创建工作流相同，需传入完整定义。",
)
def update_workflow(
    project: Annotated[str, Field(description="项目标识", example="demo")],
    name: Annotated[str, Field(description="工作流标识（路径参数）", example="workflow-demo")],
    display_name: Annotated[str, Field(description="工作流名称", example="workflow-demo")],
    concurrency_limit: Annotated[int, Field(description="任务并发数，-1 无限制，0 不可执行", example=5)],
    description: Annotated[str, Field(description="工作流描述", example="")] = "",
    stages: Annotated[
        list[dict[str, Any]],
        Field(description="阶段配置，每项含 name、parallel、jobs，可选 approval", example=[]),
    ] = [],
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /api/aslan/workflow/v4/:name。"""
    try:
        workflow_name = _require("name", name)
        payload = _workflow_definition(
            name=workflow_name,
            display_name=display_name,
            project=project,
            concurrency_limit=concurrency_limit,
            description=description,
            stages=stages,
        )
        return _dump(
            zadig_request(
                "PUT",
                f"/api/aslan/workflow/v4/{_enc(workflow_name)}",
                params={"projectName": _require("project", project)},
                json_data=payload,
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_workflow", description="删除自定义工作流。")
def delete_workflow(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    workflow_key: Annotated[str, Field(description="工作流标识", example="workflow-demo")],
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/workflows/custom。"""
    try:
        return _dump(
            zadig_request(
                "DELETE",
                "/openapi/workflows/custom",
                params={
                    "projectKey": _require("project_key", project_key),
                    "workflowKey": _require("workflow_key", workflow_key),
                },
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="list_workflow_views", description="获取项目下的工作流视图列表。")
def list_workflow_views(
    project_key: Annotated[str, Field(description="项目标识", example="lilian-test")],
) -> Annotated[str, Field(description="视图列表")]:
    """对应 GET /openapi/workflows/view。"""
    try:
        return _dump(
            zadig_request(
                "GET",
                "/openapi/workflows/view",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_workflow_view", description="创建工作流视图并绑定工作流。")
def create_workflow_view(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    name: Annotated[str, Field(description="工作流视图名称", example="view-demo")],
    workflow_list: Annotated[
        list[dict[str, Any]],
        Field(
            description="工作流列表，每项含 workflow_key、workflow_type（custom）",
            example=[{"workflow_key": "dev", "workflow_type": "custom"}],
        ),
    ],
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/workflows/view。"""
    try:
        payload = {
            "project_key": _require("project_key", project_key),
            "name": _require("name", name),
            "workflow_list": _normalize_view_workflows(workflow_list, require_enabled=False),
        }
        return _dump(zadig_request("POST", "/openapi/workflows/view", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_workflow_view", description="编辑工作流视图：enabled 为 true 加入视图，false 从视图移除。")
def update_workflow_view(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    view_name: Annotated[str, Field(description="视图名称", example="view-demo")],
    workflow_list: Annotated[
        list[dict[str, Any]],
        Field(
            description="工作流列表，每项含 workflow_key、workflow_type（custom）、enabled",
            example=[{"workflow_key": "build-deploy", "workflow_type": "custom", "enabled": True}],
        ),
    ],
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/workflows/view/:viewName。"""
    try:
        name = _require("view_name", view_name)
        return _dump(
            zadig_request(
                "PUT",
                f"/openapi/workflows/view/{_enc(name)}",
                params={"projectKey": _require("project_key", project_key)},
                json_data={"workflow_list": _normalize_view_workflows(workflow_list, require_enabled=True)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_workflow_view", description="删除工作流视图。")
def delete_workflow_view(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    view_name: Annotated[str, Field(description="视图名称", example="view-demo")],
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/workflows/view/:viewName。"""
    try:
        name = _require("view_name", view_name)
        return _dump(
            zadig_request(
                "DELETE",
                f"/openapi/workflows/view/{_enc(name)}",
                params={"projectKey": _require("project_key", project_key)},
            )
        )
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_workflow_approval_ticket", description="创建工作流预审批单，限制可执行环境、服务、用户或时间窗口。")
def create_workflow_approval_ticket(
    project_key: Annotated[str, Field(description="项目标识", example="demo")],
    approval_id: Annotated[str, Field(description="第三方系统审批单号", example="TICKET-1001")],
    status: Annotated[int, Field(description="审批单状态：0 无效，1 生效", example=1)],
    envs: Annotated[str, Field(description="可选环境限制，空为无限制", example="")] = "",
    services: Annotated[
        list[dict[str, Any]],
        Field(description="可选服务限制，每项含 service_name、service_module；空为无限制", example=[]),
    ] = [],
    users: Annotated[
        list[dict[str, Any]],
        Field(description="可执行用户限制，每项含 name、email；空为无限制", example=[]),
    ] = [],
    execution_window_start: Annotated[int, Field(description="可执行时间窗口开始（Unix 秒），0 表示不限制", example=0)] = 0,
    execution_window_end: Annotated[int, Field(description="可执行时间窗口结束（Unix 秒），0 表示不限制", example=0)] = 0,
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/ticket/approval。"""
    try:
        if int(status) not in _TICKET_STATUS:
            raise ValueError("status 必须是 0（无效）或 1（生效）")
        payload: dict[str, Any] = {
            "project_key": _require("project_key", project_key),
            "approval_id": _require("approval_id", approval_id),
            "status": int(status),
        }
        if envs.strip():
            payload["envs"] = envs.strip()
        if services:
            svc_list: list[dict[str, Any]] = []
            for item in _as_list(services, "services"):
                if not isinstance(item, dict):
                    raise ValueError("services 中的每一项必须是对象")
                svc_list.append(
                    {
                        "service_name": _require("services.service_name", item.get("service_name")),
                        "service_module": _require("services.service_module", item.get("service_module")),
                    }
                )
            payload["services"] = svc_list
        if users:
            user_list: list[dict[str, Any]] = []
            for item in _as_list(users, "users"):
                if not isinstance(item, dict):
                    raise ValueError("users 中的每一项必须是对象")
                user_list.append(
                    {
                        "name": _require("users.name", item.get("name")),
                        "email": _require("users.email", item.get("email")),
                    }
                )
            payload["users"] = user_list
        if execution_window_start:
            payload["execution_window_start"] = int(execution_window_start)
        if execution_window_end:
            payload["execution_window_end"] = int(execution_window_end)
        return _dump(zadig_request("POST", "/openapi/ticket/approval", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_workflow_task_log", description="查看已结束工作流任务中某个 Job 的完整日志。")
def get_workflow_task_log(
    workflow_name: Annotated[str, Field(description="工作流标识", example="build-deploy")],
    task_id: Annotated[int, Field(description="工作流任务 ID", example=20)],
    job_name: Annotated[str, Field(description="JobTask 标识，可从任务详情获取", example="build")],
) -> Annotated[str, Field(description="完整日志")]:
    """对应 GET /openapi/logs/log/v4/workflow/<workflowName>/<taskID>/<jobName>。"""
    try:
        name = _require("workflow_name", workflow_name)
        job = _require("job_name", job_name)
        data = zadig_request(
            "GET",
            f"/openapi/logs/log/v4/workflow/{_enc(name)}/{int(task_id)}/{_enc(job)}",
        )
        if isinstance(data, str):
            return _dump({"log": data})
        return _dump(data)
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

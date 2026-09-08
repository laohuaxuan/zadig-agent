"""系统设置页 API：从 Zadig 同步代码源、集群、镜像仓库和用户。"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from webapi.platform_permissions import (
    apply_skill_acl,
    apply_template_acl,
    can_manage_agents,
    can_manage_skills,
    can_manage_templates,
    can_manage_zadig,
    can_view_integration,
    require_skill_manage,
    require_template_manage,
)
from webapi.integration_meta import attach_integration_remarks, update_integration_remark
from webapi.integration_sync import (
    get_integration_items,
    sync_integration_resources,
    integration_sync_loop,
)
from webapi.catalog import (
    create_mcp_skill,
    create_skill,
    delete_mcp_skill,
    delete_skill,
    get_mcp_skill,
    get_skill,
    list_mcp_skills,
    list_skills,
    update_mcp_skill,
    update_skill,
)
from webapi.templates_catalog import (
    create_template,
    delete_template,
    get_template,
    import_template,
    list_templates,
    update_template,
)
from webapi.settings import (
    create_agent,
    create_zadig_instance,
    delete_agent,
    delete_zadig_instance,
    get_zadig_instance,
    load_agents,
    load_zadig,
    load_zadig_instances,
    probe_agent,
    probe_zadig,
    public_agent,
    public_zadig,
    save_zadig,
    set_active_zadig,
    set_default_agent,
    test_agent_config,
    update_agent,
    update_zadig_instance,
)
from webapi.platform_routes import AUTH_COOKIE, _extract_token, router as platform_router
from webapi.feishu_routes import router as feishu_router
from webapi.platform_auth import parse_token
from webapi.platform_users import get_user_by_id
from webapi.zadig_meta import (
    build_add_environment_plan,
    build_add_service_plan,
    build_add_workflow_plan,
    build_application_plan,
    build_project_plan,
    environment_exists_in_project,
    get_project_environment,
    list_branches,
    list_cluster_namespaces,
    list_helm_projects,
    list_project_build_services,
    list_project_environments,
    list_project_roles,
    list_project_service_names,
    list_project_workflow_names,
    list_repo_namespaces,
    list_repo_tree,
    list_repos,
    check_add_service_constraints,
    resolve_applicant,
    resolve_platform_applicant,
    workflow_exists_in_project,
)

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

from utils.db import _ensure_db_core
from utils.zadig import zadig_request

_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "application_id",
    "client_secret",
    "password",
    "secret_key",
    "access_key",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger.info("应用启动：初始化数据库 schema…")
    try:
        await asyncio.to_thread(_ensure_db_core)
    except Exception:
        logger.exception("数据库初始化失败，进程退出")
        raise
    logger.info("应用启动：开始监听 HTTP 请求")
    sync_task = asyncio.create_task(integration_sync_loop())
    catalog_task = asyncio.create_task(_startup_catalog_sync())
    feishu_task = asyncio.create_task(_startup_feishu_warmup())
    try:
        yield
    finally:
        feishu_task.cancel()
        catalog_task.cancel()
        sync_task.cancel()
        for task in (feishu_task, catalog_task, sync_task):
            try:
                await task
            except asyncio.CancelledError:
                pass


async def _startup_catalog_sync() -> None:
    try:
        from utils.db import sync_catalog_to_db

        await asyncio.to_thread(sync_catalog_to_db)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("后台 catalog 同步失败")


async def _startup_feishu_warmup() -> None:
    try:
        from webapi.feishu_client import FeishuClient

        client = FeishuClient()
        if not client.enabled():
            logger.info("飞书未配置 app_id/app_secret，跳过通讯录预热")
            return
        await client.list_contact_users("", 1)
        logger.info("飞书通讯录预热完成")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("飞书通讯录预热失败")


app = FastAPI(title="Zadig Agent Settings", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

_PUBLIC_API_PREFIXES = (
    "/api/health",
    "/api/auth/providers",
    "/api/login/feishu",
    "/api/login/local",
    "/api/login/root",
    "/api/feishu/card/callback",
    "/api/feishu/card/callback/process",
    "/api/feishu/approval/action",
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not any(path == item or path.startswith(item + "/") for item in _PUBLIC_API_PREFIXES):
        if path.startswith("/api/login/feishu/callback"):
            return await call_next(request)
        token = _extract_token(request)
        if not token:
            return JSONResponse(status_code=401, content={"ok": False, "detail": "未登录"})
        try:
            claims = parse_token(token)
            user = get_user_by_id(int(claims["user_id"]))
        except Exception:
            return JSONResponse(status_code=401, content={"ok": False, "detail": "登录已失效"})
        if not user or str(user.get("status") or "") == "disabled":
            return JSONResponse(status_code=401, content={"ok": False, "detail": "账号不可用"})
        request.state.platform_user = user
    return await call_next(request)


app.include_router(feishu_router)
app.include_router(platform_router)


class SkillCreateBody(BaseModel):
    name: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    content: str = ""


class SkillUpdateBody(BaseModel):
    display_name: str = ""
    description: str = ""
    content: str = ""


class McpSkillCreateBody(BaseModel):
    name: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    transport: str = "stdio"
    command: str = ""
    args: list[str] = []
    url: str = ""


class McpSkillUpdateBody(BaseModel):
    display_name: str = ""
    description: str = ""
    transport: str = "stdio"
    command: str = ""
    args: list[str] = []
    url: str = ""


class TemplateCreateBody(BaseModel):
    name: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    category: str = "workflow"
    body: dict[str, Any] = Field(default_factory=dict)


class TemplateUpdateBody(BaseModel):
    display_name: str = ""
    description: str = ""
    category: str = "workflow"
    body: dict[str, Any] = Field(default_factory=dict)


class TemplateImportBody(BaseModel):
    name: str = ""
    display_name: str = ""
    description: str = ""
    category: str = "workflow"
    body: dict[str, Any] | None = None


class AgentBody(BaseModel):
    name: str = ""
    api_key: str = ""
    model: str = ""
    primary_model: str = ""
    backup_models: list[str] = []
    base_url: str = ""
    is_default: bool = False


class AgentTestBody(AgentBody):
    agent_id: str = ""


def _agent_payload(body: AgentBody) -> dict[str, Any]:
    payload = body.model_dump(exclude_unset=True)
    primary = str(payload.get("primary_model") or payload.get("model") or "").strip()
    if primary and not str(payload.get("model") or "").strip():
        payload["model"] = primary
    return payload


class ZadigBody(BaseModel):
    name: str = ""
    remark: str = ""
    base_url: str = ""
    api_token: str = ""
    is_active: bool = False


class ZadigUpdateBody(BaseModel):
    name: str = ""
    remark: str = ""
    base_url: str = ""
    api_token: str = ""
    is_active: bool = False


class BuildVariable(BaseModel):
    key: str = ""
    type: str = "string"
    value: str = ""
    options: str = ""
    multi_value: list[str] = []
    scope: str = "env"
    description: str = ""


class AuthorizedUser(BaseModel):
    uid: str = ""
    role: str = ""


class ProjectCreateBody(BaseModel):
    project_name: str = Field(min_length=1)
    project_key: str = ""
    service_name: str = Field(min_length=1)
    template_name: str = Field(min_length=1)
    environment: str = "dev"
    environment_production: bool = False
    workflow_name: str = ""
    cluster_name: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    codehost_name: str = Field(min_length=1)
    repo_namespace: str = Field(min_length=1)
    repo_name: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    values_file: str = ""
    values_auto_sync: bool = True
    build_context_dir: str = "."
    dockerfile_path: str = Field(min_length=1)
    build_template_name: str = ""
    build_name: str = ""
    build_variables: list[BuildVariable] = []
    authorized_users: list[AuthorizedUser] = []


class ServiceAddBody(BaseModel):
    application_type: str = "add_service"
    project_key: str = Field(min_length=1)
    project_name: str = ""
    service_name: str = Field(min_length=1)
    template_name: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    workflow_name: str = ""
    cluster_name: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    codehost_name: str = Field(min_length=1)
    repo_namespace: str = Field(min_length=1)
    repo_name: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    values_file: str = ""
    values_auto_sync: bool = True
    build_context_dir: str = Field(min_length=1)
    dockerfile_path: str = Field(min_length=1)
    build_template_name: str = ""
    build_name: str = ""
    build_variables: list[BuildVariable] = []


class WorkflowAddBody(BaseModel):
    application_type: str = "add_workflow"
    project_key: str = Field(min_length=1)
    project_name: str = ""
    environment: str = Field(min_length=1)
    workflow_name: str = Field(min_length=1)
    registry_id: str = Field(min_length=1)
    registry_label: str = ""
    service_name: str = Field(min_length=1)
    service_module: str = ""
    build_name: str = ""
    image_name: str = ""
    deploy_production: bool = False
    deploy_env_name: str = Field(min_length=1)


class EnvironmentAddBody(BaseModel):
    application_type: str = "add_environment"
    project_key: str = Field(min_length=1)
    project_name: str = ""
    environment: str = Field(min_length=1)
    environment_production: bool = False
    cluster_name: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    registry_id: str = Field(min_length=1)
    registry_label: str = ""


class IntegrationRemarkBody(BaseModel):
    remark: str = ""


def _sanitize(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, dict):
        return {
            key: "********" if key in _SECRET_KEYS and item else _sanitize(item)
            for key, item in value.items()
        }
    return value


def _as_list(data: Any) -> list[Any]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "clusters", "registries", "users", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("Zadig 返回格式无法解析为列表")


def _page_args(page_num: int, page_size: int) -> tuple[int, int]:
    return max(1, page_num), min(100, max(1, page_size))


def _slice(items: list[Any], page_num: int, page_size: int) -> tuple[list[Any], int, int, int]:
    page_num, page_size = _page_args(page_num, page_size)
    total = len(items)
    start = (page_num - 1) * page_size
    return items[start : start + page_size], total, page_num, page_size


def _page_payload(items: list[Any], total: int, page_num: int, page_size: int, **extra: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "total": total,
        "page_num": page_num,
        "page_size": page_size,
        "items": items,
        **extra,
    }


def _platform_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "platform_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def _maintainer_id_for_create(user: dict[str, Any]) -> int | None:
    if str(user.get("role") or "") == "admin":
        return int(user["id"])
    return None


def _fetch(path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return zadig_request("GET", path, params=params)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        from utils.db import query_one

        query_one("SELECT 1 AS ok")
        return {"ok": True, "name": "zadig-agent-settings", "db": "up"}
    except Exception as exc:
        logger.warning("health check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"ok": False, "name": "zadig-agent-settings", "db": "down", "detail": str(exc)},
        )


@app.get("/api/code-sources")
def list_code_sources(page_num: int = 1, page_size: int = 10) -> dict[str, Any]:
    items, synced_at, sync_error = get_integration_items("code_sources")
    items = attach_integration_remarks(items, "code_source")
    page_items, total, page_num, page_size = _slice(items, page_num, page_size)
    return _page_payload(page_items, total, page_num, page_size, synced_at=synced_at, sync_error=sync_error)


@app.get("/api/clusters")
def list_clusters(page_num: int = 1, page_size: int = 10) -> dict[str, Any]:
    items, synced_at, sync_error = get_integration_items("clusters")
    page_items, total, page_num, page_size = _slice(items, page_num, page_size)
    return _page_payload(page_items, total, page_num, page_size, synced_at=synced_at, sync_error=sync_error)


@app.get("/api/clusters/{cluster}/namespaces")
def api_cluster_namespaces(cluster: str) -> dict[str, Any]:
    try:
        items = list_cluster_namespaces(cluster)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": items}


@app.get("/api/registries")
def list_registries(page_num: int = 1, page_size: int = 10) -> dict[str, Any]:
    items, synced_at, sync_error = get_integration_items("registries")
    items = attach_integration_remarks(items, "registry")
    page_items, total, page_num, page_size = _slice(items, page_num, page_size)
    return _page_payload(page_items, total, page_num, page_size, synced_at=synced_at, sync_error=sync_error)


@app.get("/api/users")
def list_users(page_num: int = 1, page_size: int = 10, all_users: bool = False) -> dict[str, Any]:
    items, synced_at, sync_error = get_integration_items("users")
    if all_users:
        return _page_payload(items, len(items), 1, max(len(items), 1), synced_at=synced_at, sync_error=sync_error)
    page_items, total, page_num, page_size = _slice(items, page_num, page_size)
    return _page_payload(page_items, total, page_num, page_size, synced_at=synced_at, sync_error=sync_error)


@app.get("/api/service-templates")
def list_service_templates(page_num: int = 1, page_size: int = 10) -> dict[str, Any]:
    items, synced_at, sync_error = get_integration_items("service_templates")
    items = attach_integration_remarks(items, "service_template")
    page_items, total, page_num, page_size = _slice(items, page_num, page_size)
    return _page_payload(page_items, total, page_num, page_size, synced_at=synced_at, sync_error=sync_error)


@app.post("/api/integration/sync")
def api_sync_integration(request: Request, resource_type: str = "") -> dict[str, Any]:
    user = _platform_user(request)
    if not can_view_integration(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权同步系统集成资源")
    try:
        result = sync_integration_resources(resource_type or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error") or "同步失败")
    return {"ok": True, **result}


@app.put("/api/integration-resources/{resource_type}/{resource_key}/remark")
def api_update_integration_remark(
    request: Request,
    resource_type: str,
    resource_key: str,
    body: IntegrationRemarkBody,
) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_view_integration(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权修改集成资源备注")
    try:
        item = update_integration_remark(resource_type, resource_key, body.remark)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": item}


@app.get("/api/projects")
def api_list_projects(page_num: int = 1, page_size: int = 200) -> dict[str, Any]:
    try:
        items, total = list_helm_projects(page_num, page_size)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _page_payload(items, total, page_num, page_size, synced_at=_now())


@app.get("/api/projects/{project_key}/services")
def api_list_project_services(project_key: str) -> dict[str, Any]:
    try:
        names = list_project_service_names(project_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": [{"name": name} for name in names]}


@app.get("/api/projects/{project_key}/services/check")
def api_check_project_service(
    project_key: str,
    name: str = "",
    environment: str = "",
    production: bool = False,
    environment_mode: str = "existing",
) -> dict[str, Any]:
    try:
        result = check_add_service_constraints(
            project_key,
            name,
            environment,
            environment_production=production,
            environment_mode=environment_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.get("/api/projects/{project_key}/workflows")
def api_list_project_workflows(project_key: str) -> dict[str, Any]:
    try:
        names = list_project_workflow_names(project_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": [{"name": name} for name in names]}


@app.get("/api/projects/{project_key}/workflows/check")
def api_check_project_workflow(project_key: str, name: str = "") -> dict[str, Any]:
    try:
        exists = workflow_exists_in_project(project_key, name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "exists": exists, "name": name}


@app.get("/api/projects/{project_key}/build-services")
def api_list_project_build_services(project_key: str) -> dict[str, Any]:
    try:
        items = list_project_build_services(project_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": items}


@app.get("/api/projects/{project_key}/environments")
def api_list_project_environments(project_key: str, production: bool = False) -> dict[str, Any]:
    try:
        items = list_project_environments(project_key, production=production)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": items, "production": production}


@app.get("/api/projects/{project_key}/environments/check")
def api_check_project_environment(
    project_key: str,
    name: str = "",
    production: bool = False,
) -> dict[str, Any]:
    try:
        exists = environment_exists_in_project(project_key, name, production=production)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "exists": exists, "name": name, "production": production}


@app.get("/api/projects/{project_key}/environments/{env_name}")
def api_get_project_environment(project_key: str, env_name: str, production: bool = False) -> dict[str, Any]:
    try:
        item = get_project_environment(project_key, env_name, production=production)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="未找到环境")
    return {"ok": True, "item": item}


@app.get("/api/code-sources/{codehost}/namespaces")
def api_code_namespaces(codehost: str) -> dict[str, Any]:
    try:
        items = list_repo_namespaces(codehost)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": items}


@app.get("/api/code-sources/{codehost}/repos")
def api_code_repos(codehost: str, namespace: str) -> dict[str, Any]:
    try:
        items = list_repos(codehost, namespace)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": items}


@app.get("/api/code-sources/{codehost}/branches")
def api_code_branches(codehost: str, namespace: str, repo: str) -> dict[str, Any]:
    try:
        items = list_branches(codehost, namespace, repo)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": items}


@app.get("/api/code-sources/{codehost}/tree")
def api_code_tree(codehost: str, namespace: str, repo: str, branch: str, path: str = "") -> dict[str, Any]:
    try:
        items = list_repo_tree(codehost, namespace, repo, branch, path)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": items}


@app.get("/api/project-roles")
def api_project_roles() -> dict[str, Any]:
    try:
        items = list_project_roles()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "items": items}


@app.get("/api/applicant")
def api_applicant(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "platform_user", None)
    if user:
        return {"ok": True, "item": resolve_platform_applicant(user)}
    try:
        item = resolve_applicant()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": item}


@app.post("/api/projects/preview")
def api_preview_project(body: ProjectCreateBody) -> dict[str, Any]:
    try:
        plan = build_project_plan(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "item": plan["preview"]}


@app.post("/api/services/preview")
def api_preview_service(body: ServiceAddBody) -> dict[str, Any]:
    try:
        plan = build_add_service_plan(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "item": plan["preview"]}


@app.post("/api/workflows/preview")
def api_preview_workflow(body: WorkflowAddBody) -> dict[str, Any]:
    try:
        plan = build_add_workflow_plan(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "item": plan["preview"]}


@app.post("/api/environments/preview")
def api_preview_environment(body: EnvironmentAddBody) -> dict[str, Any]:
    try:
        plan = build_add_environment_plan(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "item": plan["preview"]}


@app.post("/api/projects")
async def api_create_project(body: ProjectCreateBody) -> dict[str, Any]:
    try:
        result = await run_project_create_agent(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "item": result}


@app.get("/api/skills")
def api_list_skills(request: Request, page_num: int = 1, page_size: int = 10) -> dict[str, Any]:
    user = _platform_user(request)
    items, total, page_num, page_size = _slice(list_skills(), page_num, page_size)
    items = [apply_skill_acl(user, item) for item in items]
    return _page_payload(items, total, page_num, page_size)


@app.post("/api/skills")
def api_create_skill(request: Request, body: SkillCreateBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_skills(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权创建技能")
    try:
        item = create_skill(body.model_dump(), maintainer_id=_maintainer_id_for_create(user))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_skill_acl(user, item)}


@app.get("/api/skills/{name}")
def api_get_skill(request: Request, name: str) -> dict[str, Any]:
    user = _platform_user(request)
    try:
        item = get_skill(name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_skill_acl(user, item)}


@app.put("/api/skills/{name}")
def api_update_skill(request: Request, name: str, body: SkillUpdateBody) -> dict[str, Any]:
    user = _platform_user(request)
    try:
        existing = get_skill(name)
        require_skill_manage(user, existing)
        item = update_skill(name, body.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_skill_acl(user, item)}


@app.delete("/api/skills/{name}")
def api_delete_skill(request: Request, name: str) -> dict[str, Any]:
    user = _platform_user(request)
    try:
        existing = get_skill(name)
        require_skill_manage(user, existing)
        delete_skill(name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/mcp-skills")
def api_list_mcp_skills(request: Request, page_num: int = 1, page_size: int = 10) -> dict[str, Any]:
    user = _platform_user(request)
    items, total, page_num, page_size = _slice(list_mcp_skills(), page_num, page_size)
    items = [apply_skill_acl(user, item) for item in items]
    return _page_payload(items, total, page_num, page_size)


@app.post("/api/mcp-skills")
def api_create_mcp_skill(request: Request, body: McpSkillCreateBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_skills(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权创建技能")
    try:
        item = create_mcp_skill(body.model_dump(), maintainer_id=_maintainer_id_for_create(user))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_skill_acl(user, item)}


@app.get("/api/mcp-skills/{name}")
def api_get_mcp_skill(request: Request, name: str) -> dict[str, Any]:
    user = _platform_user(request)
    try:
        item = get_mcp_skill(name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_skill_acl(user, item)}


@app.put("/api/mcp-skills/{name}")
def api_update_mcp_skill(request: Request, name: str, body: McpSkillUpdateBody) -> dict[str, Any]:
    user = _platform_user(request)
    try:
        existing = get_mcp_skill(name)
        require_skill_manage(user, existing)
        item = update_mcp_skill(name, body.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_skill_acl(user, item)}


@app.delete("/api/mcp-skills/{name}")
def api_delete_mcp_skill(request: Request, name: str) -> dict[str, Any]:
    user = _platform_user(request)
    try:
        existing = get_mcp_skill(name)
        require_skill_manage(user, existing)
        delete_mcp_skill(name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/templates")
def api_list_templates(request: Request, page_num: int = 1, page_size: int = 10) -> dict[str, Any]:
    user = _platform_user(request)
    items, total, page_num, page_size = _slice(list_templates(), page_num, page_size)
    public_items = []
    for item in items:
        row = apply_template_acl(user, {**item, "body": None})
        public_items.append(row)
    return _page_payload(public_items, total, page_num, page_size)


@app.post("/api/templates")
def api_create_template(request: Request, body: TemplateCreateBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_templates(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权创建模板")
    try:
        item = create_template(body.model_dump(), maintainer_id=_maintainer_id_for_create(user))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_template_acl(user, item)}


@app.post("/api/templates/import")
def api_import_template(request: Request, body: TemplateImportBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_templates(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权创建模板")
    payload = body.model_dump()
    payload["maintainer_id"] = _maintainer_id_for_create(user)
    try:
        item = import_template(payload)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_template_acl(user, item)}


@app.get("/api/templates/{name}")
def api_get_template(request: Request, name: str) -> dict[str, Any]:
    user = _platform_user(request)
    try:
        item = get_template(name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_template_acl(user, item)}


@app.put("/api/templates/{name}")
def api_update_template(request: Request, name: str, body: TemplateUpdateBody) -> dict[str, Any]:
    user = _platform_user(request)
    try:
        existing = get_template(name)
        require_template_manage(user, existing)
        item = update_template(name, body.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "item": apply_template_acl(user, item)}


@app.delete("/api/templates/{name}")
def api_delete_template(request: Request, name: str) -> dict[str, Any]:
    user = _platform_user(request)
    try:
        existing = get_template(name)
        require_template_manage(user, existing)
        delete_template(name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/agents")
def api_list_agents(page_num: int = 1, page_size: int = 10) -> dict[str, Any]:
    default_id, items = load_agents()
    page_items, total, page_num, page_size = _slice(items, page_num, page_size)
    public = []
    for item in page_items:
        ok, error = probe_agent(item)
        public.append(public_agent(item, default_id, ok, error))
    return _page_payload(public, total, page_num, page_size, default=default_id)


@app.get("/api/agents/{agent_id}")
def api_get_agent(agent_id: str) -> dict[str, Any]:
    default_id, items = load_agents()
    item = next((row for row in items if row["id"] == agent_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} 不存在")
    ok, error = probe_agent(item)
    return {"ok": True, "item": public_agent(item, default_id, ok, error)}


@app.post("/api/agents/test")
def api_test_agent(request: Request, body: AgentTestBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_agents(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Agent")
    try:
        result = test_agent_config(_agent_payload(body), agent_id=str(body.agent_id or "").strip())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.post("/api/agents")
def api_create_agent(request: Request, body: AgentBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_agents(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Agent")
    try:
        item = create_agent(_agent_payload(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    default_id, _items = load_agents()
    ok, error = probe_agent(item)
    return {"ok": True, "item": public_agent(item, default_id, ok, error)}


@app.put("/api/agents/{agent_id}")
def api_update_agent(request: Request, agent_id: str, body: AgentBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_agents(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Agent")
    try:
        item = update_agent(agent_id, _agent_payload(body))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    default_id, _items = load_agents()
    ok, error = probe_agent(item)
    return {"ok": True, "item": public_agent(item, default_id, ok, error)}


@app.delete("/api/agents/{agent_id}")
def api_delete_agent(request: Request, agent_id: str) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_agents(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Agent")
    try:
        delete_agent(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/agents/{agent_id}/default")
def api_set_default_agent(request: Request, agent_id: str) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_agents(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Agent")
    try:
        set_default_agent(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "default": agent_id}


@app.get("/api/zadig")
def api_get_zadig() -> dict[str, Any]:
    active_id, items = load_zadig_instances()
    if not items:
        cfg = load_zadig()
        ok, error, body = probe_zadig(cfg)
        return {
            "ok": True,
            "item": public_zadig(
                {
                    "id": "",
                    "name": "未配置",
                    "remark": "",
                    "base_url": cfg.get("base_url") or "",
                    "api_token": cfg.get("api_token") or "",
                    "is_active": True,
                },
                "",
                ok,
                error,
                body,
            ),
        }
    current = next((item for item in items if item["id"] == active_id), items[0])
    ok, error, body = probe_zadig(current)
    return {"ok": True, "item": public_zadig({**current, "is_active": True}, active_id, ok, error, body)}


@app.get("/api/zadig/instances")
def api_list_zadig_instances(page_num: int = 1, page_size: int = 10) -> dict[str, Any]:
    active_id, items = load_zadig_instances()
    public_items = []
    for item in items:
        ok, error, body = probe_zadig(item)
        public_items.append(public_zadig(item, active_id, ok, error, body if item["id"] == active_id else None))
    page_items, total, page_num, page_size = _slice(public_items, page_num, page_size)
    return _page_payload(page_items, total, page_num, page_size, active=active_id)


@app.post("/api/zadig/instances")
def api_create_zadig_instance(request: Request, body: ZadigBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_zadig(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Zadig")
    try:
        item = create_zadig_instance(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    active_id, _ = load_zadig_instances()
    ok, error, probe_body = probe_zadig(item)
    return {"ok": True, "item": public_zadig(item, active_id, ok, error, probe_body)}


@app.get("/api/zadig/instances/{instance_id}")
def api_get_zadig_instance(instance_id: str) -> dict[str, Any]:
    try:
        item = get_zadig_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    active_id, _ = load_zadig_instances()
    ok, error, body = probe_zadig(item)
    return {"ok": True, "item": public_zadig(item, active_id, ok, error, body)}


@app.put("/api/zadig/instances/{instance_id}")
def api_update_zadig_instance(request: Request, instance_id: str, body: ZadigUpdateBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_zadig(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Zadig")
    try:
        item = update_zadig_instance(instance_id, body.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    active_id, _ = load_zadig_instances()
    ok, error, probe_body = probe_zadig(item)
    return {"ok": True, "item": public_zadig(item, active_id, ok, error, probe_body)}


@app.delete("/api/zadig/instances/{instance_id}")
def api_delete_zadig_instance(request: Request, instance_id: str) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_zadig(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Zadig")
    try:
        delete_zadig_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/zadig/instances/{instance_id}/activate")
def api_activate_zadig_instance(request: Request, instance_id: str) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_zadig(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Zadig")
    try:
        set_active_zadig(instance_id)
        item = get_zadig_instance(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ok, error, body = probe_zadig(item)
    return {"ok": True, "item": public_zadig({**item, "is_active": True}, instance_id, ok, error, body)}


@app.put("/api/zadig")
def api_update_zadig(request: Request, body: ZadigBody) -> dict[str, Any]:
    user = _platform_user(request)
    if not can_manage_zadig(str(user.get("role") or "")):
        raise HTTPException(status_code=403, detail="无权管理 Zadig")
    try:
        save_zadig(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return api_get_zadig()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


_DIST = _ROOT / "web" / "dist"
if _DIST.is_dir():

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = "") -> FileResponse:
        """Serve built frontend; never intercept /api/* (StaticFiles would return 404/405)."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path:
            asset = _DIST / full_path
            if asset.is_file():
                return FileResponse(asset)
        index = _DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Not Found")

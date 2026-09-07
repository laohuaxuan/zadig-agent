"""Zadig 元数据查询与项目创建编排。"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from utils.zadig import zadig_request

_PROJECT_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_ENV_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
_APPLICANT_ROLE = "project-admin"


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = str(token or "").strip().split(".")
    if len(parts) < 2:
        return {}
    padding = "=" * (-len(parts[1]) % 4)
    try:
        raw = base64.urlsafe_b64decode(parts[1] + padding)
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_applicant() -> dict[str, str]:
    from webapi.settings import load_zadig

    token = str(load_zadig().get("api_token") or "").strip()
    if not token:
        raise ValueError("未配置 Zadig API Token，无法识别当前申请用户")
    payload = _decode_jwt_payload(token)
    uid = str(payload.get("uid") or "").strip()
    if not uid:
        raise ValueError("无法从 Zadig Token 解析当前用户")
    account = str(payload.get("preferred_username") or payload.get("account") or "").strip()
    name = str(payload.get("name") or account or uid).strip()
    return {
        "uid": uid,
        "account": account,
        "name": name,
        "role": _APPLICANT_ROLE,
        "in_zadig_users": True,
        "source": "zadig_token",
    }


def match_zadig_user(platform_user: dict[str, Any], zadig_users: list[dict[str, Any]] | None = None) -> dict[str, str] | None:
    users = zadig_users if zadig_users is not None else list_all_users()
    aliases = {
        str(platform_user.get("name") or "").strip().lower(),
        str(platform_user.get("display_name") or "").strip().lower(),
    }
    aliases.discard("")
    for item in users:
        uid = str(item.get("uid") or "").strip()
        if not uid:
            continue
        account = str(item.get("account") or "").strip().lower()
        name = str(item.get("name") or "").strip().lower()
        if account in aliases or name in aliases:
            return {
                "uid": uid,
                "account": str(item.get("account") or "").strip(),
                "name": str(item.get("name") or item.get("account") or uid).strip(),
                "role": _APPLICANT_ROLE,
            }
    return None


def resolve_platform_applicant(platform_user: dict[str, Any]) -> dict[str, Any]:
    matched = match_zadig_user(platform_user)
    display = str(platform_user.get("display_name") or platform_user.get("name") or "").strip()
    if matched:
        return {**matched, "source": "platform", "in_zadig_users": True}
    return {
        "uid": "",
        "account": str(platform_user.get("name") or "").strip(),
        "name": display,
        "role": _APPLICANT_ROLE,
        "source": "platform",
        "in_zadig_users": False,
    }


def _merge_applicant_users(users: list[dict[str, str]]) -> list[dict[str, str]]:
    try:
        applicant = resolve_applicant()
    except ValueError:
        return users
    merged = [{"uid": applicant["uid"], "role": applicant["role"]}]
    seen = {applicant["uid"]}
    for item in users:
        uid = str(item.get("uid") or "").strip()
        role = str(item.get("role") or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        merged.append({"uid": uid, "role": role})
    return merged


def _resolve_default_registry_id() -> str:
    data = zadig_request("GET", "/openapi/system/registry")
    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("registries") or data.get("items") or []
    else:
        items = []
    default_id = ""
    fallback_id = ""
    for item in items:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or item.get("registry_id") or "").strip()
        if not rid:
            continue
        if not fallback_id:
            fallback_id = rid
        if item.get("is_default"):
            default_id = rid
            break
    registry_id = default_id or fallback_id
    if not registry_id:
        raise ValueError("未找到可用的镜像仓库，请先在 Zadig 中配置默认镜像仓库")
    return registry_id


def slug_project_key(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    if not text:
        text = "project"
    if not text[0].isalpha():
        text = f"p-{text}"
    return text[:63]


def _cluster_id(cluster: str) -> str:
    text = str(cluster or "").strip()
    if not text:
        raise ValueError("cluster 不能为空")
    if len(text) == 24 and all(ch in "0123456789abcdef" for ch in text.lower()):
        return text
    data = zadig_request("GET", "/openapi/system/cluster")
    clusters = data if isinstance(data, list) else []
    for item in clusters:
        if str(item.get("name") or "") == text:
            cid = str(item.get("cluster_id") or item.get("id") or "").strip()
            if cid:
                return cid
    raise ValueError(f"未找到集群 {cluster}")


def list_cluster_namespaces(cluster: str) -> list[dict[str, Any]]:
    cid = _cluster_id(cluster)
    data = zadig_request("GET", f"/api/aslan/environment/kube/namespace/cluster/{cid}")
    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], str):
            return [{"name": name} for name in data if str(name).strip()]
        if isinstance(data[0], dict):
            out: list[dict[str, Any]] = []
            for item in data:
                name = str(item.get("name") or "").strip()
                if name:
                    out.append({**item, "name": name})
            return out
    return []


def list_chart_templates() -> list[dict[str, Any]]:
    data = zadig_request("GET", "/openapi/templates/charts")
    if not isinstance(data, dict):
        return []
    items = data.get("chart_templates") or []
    return items if isinstance(items, list) else []


def list_codehosts() -> list[dict[str, Any]]:
    data = zadig_request("GET", "/api/aslan/code/codehost")
    return data if isinstance(data, list) else []


def _codehost_id(codehost: str) -> str:
    text = str(codehost or "").strip()
    if not text:
        raise ValueError("codehost 不能为空")
    if text.isdigit():
        return text
    for item in list_codehosts():
        if str(item.get("alias") or "") == text or str(item.get("name") or "") == text:
            return str(item.get("id"))
    raise ValueError(f"未找到代码源 {codehost}")


def list_repo_namespaces(codehost: str) -> list[dict[str, Any]]:
    cid = _codehost_id(codehost)
    data = zadig_request("GET", f"/api/aslan/code/codehost/{cid}/namespaces")
    return data if isinstance(data, list) else []


def _repo_owner(codehost: str, namespace: str) -> tuple[str, str]:
    text = str(namespace or "").strip()
    if not text:
        raise ValueError("组织/用户不能为空")
    if "/" in text:
        return text, "group"
    for item in list_repo_namespaces(codehost):
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or name).strip()
        if text in {name, path}:
            kind = str(item.get("kind") or "group").strip().lower()
            return path, ("user" if kind == "user" else "group")
    return text, "group"


def list_repos(codehost: str, namespace: str) -> list[dict[str, Any]]:
    cid = _codehost_id(codehost)
    repo_owner, ns_type = _repo_owner(codehost, namespace)
    data = zadig_request(
        "GET",
        f"/api/aslan/code/codehost/{cid}/projects",
        params={"repoOwner": repo_owner, "type": ns_type},
    )
    items: list[Any] = data if isinstance(data, list) else []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            out.append({"name": item})
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("repo") or item.get("path") or "").strip()
            if name:
                out.append({**item, "name": name})
    return out


def _as_name_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        out: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, str):
                out.append({"name": item})
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("branch") or item.get("path") or "").strip()
                if name:
                    out.append({**item, "name": name})
        return out
    return []


def list_branches(codehost: str, namespace: str, repo: str) -> list[dict[str, Any]]:
    cid = _codehost_id(codehost)
    repo_owner, _ = _repo_owner(codehost, namespace)
    repo_name = str(repo or "").strip()
    data = zadig_request(
        "GET",
        f"/api/aslan/code/codehost/{cid}/branches",
        params={"repoOwner": repo_owner, "repoName": repo_name},
    )
    return _as_name_items(data if isinstance(data, list) else (data or {}).get("branches") if isinstance(data, dict) else [])


def fetch_repo_file_content(codehost: str, namespace: str, repo: str, branch: str, path: str) -> str:
    cid = _codehost_id(codehost)
    repo_owner, _ = _repo_owner(codehost, namespace)
    repo_name = str(repo or "").strip()
    branch_name = str(branch or "").strip()
    file_path = str(path or "").strip().strip("/")
    if not file_path:
        raise ValueError("values 文件路径不能为空")
    data = zadig_request(
        "GET",
        f"/api/aslan/code/workspace/getcontents/{cid}",
        params={
            "repoOwner": repo_owner,
            "repoName": repo_name,
            "branchName": branch_name,
            "path": file_path,
            "isDir": "false",
        },
    )
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        content = data.get("content") or data.get("data") or data.get("text")
        if content is not None:
            return str(content)
    raise ValueError(f"无法读取 values 文件 {file_path}")


def list_repo_tree(codehost: str, namespace: str, repo: str, branch: str, path: str = "") -> list[dict[str, Any]]:
    cid = _codehost_id(codehost)
    repo_owner, _ = _repo_owner(codehost, namespace)
    repo_name = str(repo or "").strip()
    branch_name = str(branch or "").strip()
    sub_path = str(path or "").strip().strip("/")
    data = zadig_request(
        "GET",
        "/api/aslan/code/workspace/tree",
        params={
            "codehost_id": int(cid),
            "namespace": repo_owner,
            "repo": repo_name,
            "branch": branch_name,
            "path": sub_path,
        },
    )
    items = data if isinstance(data, list) else []
    if isinstance(data, dict):
        for key in ("tree", "data", "items", "nodes"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("path") or item.get("full_path") or "").strip()
            full_path = str(item.get("full_path") or item.get("path") or name).strip()
            if name:
                out.append({**item, "name": name, "path": full_path})
        elif isinstance(item, str):
            out.append({"name": item, "path": item})
    return out


def list_project_roles() -> list[dict[str, Any]]:
    data = zadig_request("GET", "/openapi/policy/roles", params={"namespace": "default"})
    return data if isinstance(data, list) else []


def list_all_users(page_size: int = 200) -> list[dict[str, Any]]:
    page_num = 1
    items: list[dict[str, Any]] = []
    while True:
        data = zadig_request(
            "GET",
            "/openapi/users",
            params={"pageNum": page_num, "pageSize": page_size},
        )
        if not isinstance(data, dict):
            break
        batch = data.get("users") or []
        if not isinstance(batch, list) or not batch:
            break
        items.extend(batch)
        total = int(data.get("total_count") or len(items))
        if len(items) >= total:
            break
        page_num += 1
        if page_num > 50:
            break
    return items


def _normalize_build_parameters(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        ptype = str(item.get("type") or "string").strip()
        if ptype not in {"string", "choice", "multi-select"}:
            raise ValueError(f"构建变量 {key} 的类型无效")
        if ptype == "string":
            out.append({"key": key, "type": "string", "default_value": str(item.get("value") or "")})
            continue
        raw_options = item.get("options")
        if isinstance(raw_options, list):
            choice_option = [str(v).strip() for v in raw_options if str(v).strip()]
        else:
            choice_option = [part.strip() for part in str(raw_options or "").split(",") if part.strip()]
        if not choice_option:
            raise ValueError(f"构建变量 {key} 需要配置选项")
        if ptype == "choice":
            default_value = str(item.get("value") or choice_option[0]).strip()
            if default_value not in choice_option:
                default_value = choice_option[0]
            out.append(
                {
                    "key": key,
                    "type": "choice",
                    "default_value": default_value,
                    "choice_option": choice_option,
                }
            )
            continue
        raw_multi = item.get("multi_value")
        if isinstance(raw_multi, list):
            choice_value = [str(v).strip() for v in raw_multi if str(v).strip()]
        else:
            choice_value = [part.strip() for part in str(item.get("value") or "").split(",") if part.strip()]
        choice_value = [value for value in choice_value if value in choice_option]
        out.append(
            {
                "key": key,
                "type": "multi-select",
                "default_value": ",".join(choice_value),
                "choice_option": choice_option,
                "choice_value": choice_value,
            }
        )
    return out


def _normalize_build_args(items: list[dict[str, Any]] | None) -> str:
    lines: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        value = str(item.get("value") or "")
        lines.append(f"{key}={value}")
    return "\n".join(lines)


def list_helm_projects(page_num: int = 1, page_size: int = 200) -> tuple[list[dict[str, str]], int]:
    size = min(200, max(1, page_size))
    num = max(1, page_num)
    data = zadig_request("GET", "/openapi/projects/project", params={"pageSize": size, "pageNum": num})
    items: list[dict[str, str]] = []
    for row in data.get("projects") or data.get("project_list") or []:
        if not isinstance(row, dict):
            continue
        ptype = str(row.get("project_type") or row.get("type") or "").lower()
        if ptype and "helm" not in ptype:
            continue
        key = str(row.get("project_key") or row.get("projectKey") or "").strip()
        name = str(row.get("project_name") or row.get("projectName") or key).strip()
        if key:
            items.append({"project_key": key, "project_name": name})
    total = int(data.get("total") or data.get("total_count") or len(items))
    return items, total


def get_project_detail(project_key: str) -> dict[str, Any]:
    key = str(project_key or "").strip()
    if not key:
        raise ValueError("项目标识不能为空")
    data = zadig_request("GET", "/openapi/projects/project/detail", params={"projectKey": key})
    return data if isinstance(data, dict) else {}


def list_project_service_names(project_key: str) -> list[str]:
    detail = get_project_detail(project_key)
    names: list[str] = []
    for bucket in (detail.get("services"), detail.get("service_list")):
        if not isinstance(bucket, list):
            continue
        for item in bucket:
            if not isinstance(item, dict):
                continue
            name = str(item.get("service_name") or item.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def service_exists_in_project(project_key: str, service_name: str) -> bool:
    target = str(service_name or "").strip().lower()
    if not target:
        return False
    return any(name.lower() == target for name in list_project_service_names(project_key))


def _extract_service_names_from_env_payload(data: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(data, dict):
        return names
    buckets: list[Any] = []
    for key in ("services", "service_list", "workloads", "helm_services"):
        bucket = data.get(key)
        if isinstance(bucket, list):
            buckets.append(bucket)
    env_info = data.get("env_info")
    if isinstance(env_info, dict):
        for key in ("services", "service_list", "workloads"):
            bucket = env_info.get(key)
            if isinstance(bucket, list):
                buckets.append(bucket)
    for bucket in buckets:
        for item in bucket:
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(item.get("service_name") or item.get("name") or "").strip()
            else:
                continue
            if name and name.lower() not in {existing.lower() for existing in names}:
                names.append(name)
    return names


def service_exists_in_environment(
    project_key: str,
    env_name: str,
    service_name: str,
    *,
    production: bool = False,
) -> bool:
    key = str(project_key or "").strip()
    env = str(env_name or "").strip()
    target = str(service_name or "").strip().lower()
    if not key or not env or not target:
        return False
    root = "/openapi/environments/production" if production else "/openapi/environments"
    try:
        data = zadig_request("GET", f"{root}/{env}", params={"projectKey": key})
    except Exception:
        return False
    names = _extract_service_names_from_env_payload(data)
    return any(name.lower() == target for name in names)


def build_exists_for_service(project_key: str, service_name: str) -> bool:
    return _resolve_build_for_service(project_key, service_name) is not None


def check_add_service_constraints(
    project_key: str,
    service_name: str,
    environment: str = "",
    *,
    environment_production: bool = False,
    environment_mode: str = "existing",
) -> dict[str, Any]:
    key = str(project_key or "").strip()
    name = str(service_name or "").strip()
    env = str(environment or "").strip()
    mode = str(environment_mode or "existing").strip() or "existing"
    result: dict[str, Any] = {
        "ok": True,
        "blocked": False,
        "exists": False,
        "reason": "",
        "message": "",
        "name": name,
    }
    if not key or not name:
        return result

    if environment_production and not build_exists_for_service(key, name):
        return {
            **result,
            "blocked": True,
            "exists": True,
            "reason": "prod_without_test_build",
            "message": f"请先在测试环境创建服务「{name}」（含构建），再添加生产环境服务",
        }

    if env and mode != "new":
        if environment_exists_in_project(key, env, production=environment_production):
            if service_exists_in_environment(key, env, name, production=environment_production):
                return {
                    **result,
                    "blocked": True,
                    "exists": True,
                    "reason": "same_env",
                    "message": f"当前已选环境「{env}」中存在相同名称的服务「{name}」",
                }

    return result


def list_project_environments(project_key: str, *, production: bool = False) -> list[dict[str, str]]:
    key = str(project_key or "").strip()
    if not key:
        return []
    root = "/openapi/environments/production" if production else "/openapi/environments"
    data = zadig_request("GET", root, params={"projectKey": key})
    rows = data if isinstance(data, list) else (data.get("envs") or data.get("environments") or [])
    items: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        env_name = str(row.get("env_name") or row.get("env_key") or row.get("name") or "").strip()
        if not env_name:
            continue
        items.append(
            {
                "env_name": env_name,
                "cluster_name": str(row.get("cluster_name") or row.get("clusterName") or "").strip(),
                "namespace": str(row.get("namespace") or row.get("ns") or "").strip(),
                "production": str(production).lower(),
            }
        )
    return items


def environment_exists_in_project(project_key: str, env_name: str, *, production: bool = False) -> bool:
    key = str(project_key or "").strip()
    env = str(env_name or "").strip()
    if not key or not env:
        return False
    return any(item["env_name"] == env for item in list_project_environments(key, production=production))


def get_project_environment(project_key: str, env_name: str, *, production: bool = False) -> dict[str, str]:
    key = str(project_key or "").strip()
    env = str(env_name or "").strip()
    if not key or not env:
        return {}
    for item in list_project_environments(key, production=production):
        if item["env_name"] == env:
            return item
    root = "/openapi/environments/production" if production else "/openapi/environments"
    try:
        data = zadig_request("GET", f"{root}/{env}", params={"projectKey": key})
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "env_name": env,
        "cluster_name": str(data.get("cluster_name") or data.get("clusterName") or "").strip(),
        "namespace": str(data.get("namespace") or data.get("ns") or "").strip(),
        "production": str(production).lower(),
    }


def _validate_project_input(payload: dict[str, Any]) -> dict[str, Any]:
    project_name = str(payload.get("project_name") or "").strip()
    project_key = str(payload.get("project_key") or slug_project_key(project_name)).strip()
    service_name = str(payload.get("service_name") or "").strip()
    template_name = str(payload.get("template_name") or "").strip()
    environment = str(payload.get("environment") or "dev").strip()
    environment_production = False
    workflow_name = str(payload.get("workflow_name") or "").strip()
    cluster_name = str(payload.get("cluster_name") or "").strip()
    namespace = str(payload.get("namespace") or "").strip()
    codehost_name = str(payload.get("codehost_name") or "").strip()
    repo_namespace = str(payload.get("repo_namespace") or "").strip()
    repo_name = str(payload.get("repo_name") or "").strip()
    branch = str(payload.get("branch") or "").strip()
    values_file = str(payload.get("values_file") or "").strip()
    values_auto_sync = bool(payload.get("values_auto_sync", True))
    build_context_dir = str(payload.get("build_context_dir") or ".").strip() or "."
    dockerfile_path = str(payload.get("dockerfile_path") or "").strip()
    build_template_name = str(payload.get("build_template_name") or "").strip()
    build_name = str(payload.get("build_name") or f"{service_name}-build").strip()
    authorized_users = payload.get("authorized_users") or []

    if not project_name:
        raise ValueError("项目名称不能为空")
    if not _PROJECT_KEY_RE.match(project_key):
        raise ValueError("项目标识只能包含小写字母、数字和中划线，且以字母开头")
    if not service_name:
        raise ValueError("服务名称不能为空")
    if not template_name:
        raise ValueError("请选择服务模板")
    if not environment:
        raise ValueError("请填写环境名称")
    if not _ENV_KEY_RE.match(environment):
        raise ValueError("环境名称需以字母开头，只能包含字母、数字、下划线和中划线")
    if not workflow_name:
        workflow_name = f"{project_key}-{environment}"
    if not cluster_name:
        raise ValueError("请选择 K8s 集群")
    if not namespace:
        raise ValueError("请填写或选择 K8s 命名空间")
    if not codehost_name or not repo_namespace or not repo_name or not branch:
        raise ValueError("请完整填写代码源信息")
    if not build_context_dir:
        raise ValueError("请填写构建上下文")
    if not dockerfile_path:
        raise ValueError("请填写 Dockerfile 绝对路径")

    bindings: list[dict[str, str]] = []
    for item in authorized_users:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid") or item.get("user_id") or "").strip()
        role = str(item.get("role") or "").strip()
        if uid and not role:
            raise ValueError("授权用户已选择用户时，角色不能为空")
        if uid and role:
            bindings.append({"uid": uid, "role": role})

    bindings = _merge_applicant_users(bindings)

    return {
        "project_name": project_name,
        "project_key": project_key,
        "service_name": service_name,
        "template_name": template_name,
        "environment": environment,
        "environment_production": environment_production,
        "workflow_name": workflow_name,
        "cluster_name": cluster_name,
        "namespace": namespace,
        "codehost_name": codehost_name,
        "repo_namespace": repo_namespace,
        "repo_name": repo_name,
        "branch": branch,
        "values_file": values_file,
        "values_auto_sync": values_auto_sync,
        "build_context_dir": build_context_dir,
        "dockerfile_path": dockerfile_path,
        "build_template_name": build_template_name,
        "build_name": build_name,
        "build_variables": payload.get("build_variables") or [],
        "authorized_users": bindings,
    }


def _build_service_row(data: dict[str, Any]) -> dict[str, Any]:
    service_row: dict[str, Any] = {
        "source": "template",
        "service_name": data["service_name"],
        "template_name": data["template_name"],
        "auto_sync": False,
        "values_yaml": "",
    }
    if data["values_file"]:
        service_row["values_yaml"] = fetch_repo_file_content(
            data["codehost_name"],
            data["repo_namespace"],
            data["repo_name"],
            data["branch"],
            data["values_file"],
        )
        service_row["import_values_from_git"] = {
            "codehost_name": data["codehost_name"],
            "namespace": data["repo_namespace"],
            "repo": data["repo_name"],
            "branch": data["branch"],
            "value_path": data["values_file"],
            "auto_sync": data["values_auto_sync"],
        }
    return service_row


def _init_helm_service_row(service_row: dict[str, Any]) -> dict[str, Any]:
    """Project init API only accepts values_yaml; Git import is env-level."""
    return {key: value for key, value in service_row.items() if key != "import_values_from_git"}


def _build_helm_env_service(data: dict[str, Any], service_row: dict[str, Any]) -> dict[str, Any] | None:
    imported = service_row.get("import_values_from_git")
    if not imported:
        return None
    return {
        "project_key": data["project_key"],
        "env_name": data["environment"],
        "services": [
            {
                "service_name": data["service_name"],
                "deploy_strategy": "deploy",
                "import_values_from_git": imported,
            }
        ],
    }


def build_project_plan(payload: dict[str, Any]) -> dict[str, Any]:
    data = _validate_project_input(payload)
    service_row = _build_service_row(data)
    helm_env_service = _build_helm_env_service(data, service_row)
    build_parameters = _normalize_build_parameters(data["build_variables"])
    helm_project = {
        "project_name": data["project_name"],
        "project_key": data["project_key"],
        "is_public": False,
        "description": "",
        "service_list": [_init_helm_service_row(service_row)],
        "env_list": [
            {
                "env_key": data["environment"],
                "cluster_name": data["cluster_name"],
                "namespace": data["namespace"],
                "production": data["environment_production"],
            }
        ],
    }
    build = {
        "project_key": data["project_key"],
        "name": data["build_name"],
        "infrastructure": "kubernetes",
        "build_os": "ubuntu 20.04",
        "script_type": "shell",
        "build_script": "#!/bin/bash\nset -e",
        "installs": [],
        "services": [{"service_name": data["service_name"], "service_module": data["service_name"]}],
        "repo_info": [
            {
                "codehost_name": data["codehost_name"],
                "repo_namespace": data["repo_namespace"],
                "repo_name": data["repo_name"],
                "branch": data["branch"],
            }
        ],
        "docker_build_step": {
            "dockerfile_source": "local",
            "dockerfile_directory": data["dockerfile_path"],
            "build_context_dir": data["build_context_dir"],
            "build_args": "",
            "enable_buildkit": True,
            "platforms": "linux/amd64",
            "template_name": data["build_template_name"],
        },
        "parameters": build_parameters,
    }
    role_bindings = [
        {
            "project_key": data["project_key"],
            "role": item["role"],
            "identities": [{"identity_type": "user", "uid": item["uid"]}],
        }
        for item in data["authorized_users"]
    ]
    registry_id = _resolve_default_registry_id()
    workflow = {
        "project": data["project_key"],
        "name": data["workflow_name"],
        "display_name": data["workflow_name"],
        "registry_id": registry_id,
        "service_name": data["service_name"],
        "build_name": data["build_name"],
        "image_name": data["service_name"],
        "env_name": data["environment"],
        "production": data["environment_production"],
        "template_name": "workflow_build_deploy",
    }
    env_type_label = "生产环境" if data["environment_production"] else "测试环境"
    preview = {
        "project_key": data["project_key"],
        "sections": [
            {
                "title": "基本信息",
                "items": [
                    {"label": "项目名称", "value": data["project_name"]},
                    {"label": "项目标识", "value": data["project_key"]},
                    {"label": "服务名称", "value": data["service_name"]},
                    {"label": "服务模板", "value": data["template_name"]},
                    {"label": "环境类型", "value": env_type_label},
                    {"label": "环境名称", "value": data["environment"]},
                    {"label": "工作流名称", "value": data["workflow_name"]},
                ],
            },
            {
                "title": "K8s 集群",
                "items": [
                    {"label": "集群", "value": data["cluster_name"]},
                    {"label": "命名空间", "value": data["namespace"]},
                ],
            },
            {
                "title": "代码源",
                "items": [
                    {"label": "代码源", "value": data["codehost_name"]},
                    {"label": "组织/用户", "value": data["repo_namespace"]},
                    {"label": "代码库", "value": data["repo_name"]},
                    {"label": "分支", "value": data["branch"]},
                    {"label": "Values 文件", "value": data["values_file"] or "使用 Chart 默认值"},
                    {"label": "自动同步 Values", "value": "是" if data["values_auto_sync"] else "否" if data["values_file"] else "—"},
                    {"label": "构建上下文", "value": data["build_context_dir"]},
                    {"label": "Dockerfile", "value": data["dockerfile_path"]},
                ],
            },
            {
                "title": "构建变量",
                "items": [
                    {"label": item["key"], "value": _format_build_variable(item)}
                    for item in data["build_variables"]
                    if isinstance(item, dict) and str(item.get("key") or "").strip()
                ]
                or [{"label": "—", "value": "未配置"}],
            },
            {
                "title": "授权用户",
                "items": [
                    {"label": item["uid"], "value": item["role"]}
                    for item in data["authorized_users"]
                ]
                or [{"label": "—", "value": "未配置"}],
            },
        ],
        "skill_name": "create_helm_project",
    }
    agent: dict[str, Any] = {
        "helm_project": helm_project,
        "build": build,
        "role_bindings": role_bindings,
        "workflow": workflow,
    }
    if helm_env_service:
        agent["helm_env_service"] = helm_env_service
    result: dict[str, Any] = {
        "project_key": data["project_key"],
        "preview": preview,
        "agent": agent,
    }
    try:
        from webapi.agent_resources import public_execution_context, resolve_execution_resources

        ctx = public_execution_context(resolve_execution_resources(payload, result))
        preview["skill_name"] = ctx["skill"]["name"]
        result["agent"]["workflow"]["template_name"] = ctx["workflow_template"]["name"]
        preview["sections"].append(
            {
                "title": "Agent 资源",
                "items": [
                    {
                        "label": "Skill",
                        "value": f"{ctx['skill']['name']}（{ctx['skill']['display_name']}）",
                    },
                    {
                        "label": "工作流模板",
                        "value": f"{ctx['workflow_template']['name']}（{ctx['workflow_template']['display_name']}）",
                    },
                    {
                        "label": "MCP",
                        "value": f"{ctx['mcp']['server']} · {ctx['catalog']['mcp_tools_count']} 工具",
                    },
                ],
            }
        )
        result["execution_resources"] = ctx
    except Exception:
        pass
    return result


def _validate_add_service_input(payload: dict[str, Any]) -> dict[str, Any]:
    project_key = str(payload.get("project_key") or "").strip()
    project_name = str(payload.get("project_name") or project_key).strip()
    service_name = str(payload.get("service_name") or "").strip()
    template_name = str(payload.get("template_name") or "").strip()
    environment = str(payload.get("environment") or "dev").strip().lower()
    environment_mode = str(payload.get("environment_mode") or "existing").strip()
    environment_production = bool(payload.get("environment_production", False))
    workflow_name = str(payload.get("workflow_name") or "").strip()
    cluster_name = str(payload.get("cluster_name") or "").strip()
    namespace = str(payload.get("namespace") or "").strip()
    codehost_name = str(payload.get("codehost_name") or "").strip()
    repo_namespace = str(payload.get("repo_namespace") or "").strip()
    repo_name = str(payload.get("repo_name") or "").strip()
    branch = str(payload.get("branch") or "").strip()
    values_file = str(payload.get("values_file") or "").strip()
    values_auto_sync = bool(payload.get("values_auto_sync", True))
    build_context_dir = str(payload.get("build_context_dir") or ".").strip() or "."
    dockerfile_path = str(payload.get("dockerfile_path") or "").strip()
    build_template_name = str(payload.get("build_template_name") or "").strip()
    build_name = str(payload.get("build_name") or f"{service_name}-build").strip()

    if not project_key:
        raise ValueError("请选择项目")
    if not service_name:
        raise ValueError("服务名称不能为空")
    constraint = check_add_service_constraints(
        project_key,
        service_name,
        environment,
        environment_production=environment_production,
        environment_mode=environment_mode,
    )
    if constraint.get("blocked"):
        raise ValueError(str(constraint.get("message") or "当前无法添加该服务"))
    if not template_name:
        raise ValueError("请选择服务模板")
    if not environment:
        raise ValueError("请选择或填写环境")
    if not workflow_name:
        workflow_name = f"{service_name}-{environment}"
    if not cluster_name:
        raise ValueError("请选择 K8s 集群")
    if not namespace:
        raise ValueError("请填写或选择 K8s 命名空间")
    if not codehost_name or not repo_namespace or not repo_name or not branch:
        raise ValueError("请完整填写代码源信息")
    if not build_context_dir:
        raise ValueError("请填写构建上下文")
    if not dockerfile_path:
        raise ValueError("请填写 Dockerfile 绝对路径")

    return {
        "application_type": "add_service",
        "project_name": project_name,
        "project_key": project_key,
        "service_name": service_name,
        "template_name": template_name,
        "environment": environment,
        "environment_mode": environment_mode,
        "environment_production": environment_production,
        "workflow_name": workflow_name,
        "cluster_name": cluster_name,
        "namespace": namespace,
        "codehost_name": codehost_name,
        "repo_namespace": repo_namespace,
        "repo_name": repo_name,
        "branch": branch,
        "values_file": values_file,
        "values_auto_sync": values_auto_sync,
        "build_context_dir": build_context_dir,
        "dockerfile_path": dockerfile_path,
        "build_template_name": build_template_name,
        "build_name": build_name,
        "build_variables": payload.get("build_variables") or [],
        "authorized_users": [],
    }


def build_add_service_plan(payload: dict[str, Any]) -> dict[str, Any]:
    data = _validate_add_service_input(payload)
    service_row = _build_service_row(data)
    build_parameters = _normalize_build_parameters(data["build_variables"])
    helm_service: dict[str, Any] = {
        "project_key": data["project_key"],
        "service_name": data["service_name"],
        "template_name": data["template_name"],
        "production": False,
        "auto_sync": False,
    }
    if service_row.get("values_yaml"):
        helm_service["values_yaml"] = service_row["values_yaml"]

    env_name = data["environment"]
    helm_env_service = _build_helm_env_service(data, service_row)
    if not helm_env_service:
        helm_env_service = {
            "project_key": data["project_key"],
            "env_name": env_name,
            "services": [{"service_name": data["service_name"], "deploy_strategy": "deploy"}],
        }

    build = {
        "project_key": data["project_key"],
        "name": data["build_name"],
        "infrastructure": "kubernetes",
        "build_os": "ubuntu 20.04",
        "script_type": "shell",
        "build_script": "#!/bin/bash\nset -e",
        "installs": [],
        "services": [{"service_name": data["service_name"], "service_module": data["service_name"]}],
        "repo_info": [
            {
                "codehost_name": data["codehost_name"],
                "repo_namespace": data["repo_namespace"],
                "repo_name": data["repo_name"],
                "branch": data["branch"],
            }
        ],
        "docker_build_step": {
            "dockerfile_source": "local",
            "dockerfile_directory": data["dockerfile_path"],
            "build_context_dir": data["build_context_dir"],
            "build_args": "",
            "enable_buildkit": True,
            "platforms": "linux/amd64",
            "template_name": data["build_template_name"],
        },
        "parameters": build_parameters,
    }
    registry_id = _resolve_default_registry_id()
    production = bool(data.get("environment_production", False))
    existing_envs = list_project_environments(data["project_key"], production=production)
    env_exists = any(item["env_name"] == env_name for item in existing_envs)
    workflow = {
        "project": data["project_key"],
        "name": data["workflow_name"],
        "display_name": data["workflow_name"],
        "registry_id": registry_id,
        "service_name": data["service_name"],
        "build_name": data["build_name"],
        "image_name": data["service_name"],
        "env_name": env_name,
        "template_name": "workflow_build_deploy",
    }
    agent: dict[str, Any] = {
        "env_exists": env_exists,
        "helm_service": helm_service,
        "helm_env_service": helm_env_service,
        "build": build,
        "workflow": workflow,
    }
    if not env_exists:
        agent["helm_environment"] = {
            "project_key": data["project_key"],
            "env_name": env_name,
            "cluster_id": _cluster_id(data["cluster_name"]),
            "namespace": data["namespace"],
            "registry_id": registry_id,
            "production": production,
        }
    preview = {
        "project_key": data["project_key"],
        "application_type": "add_service",
        "sections": [
            {
                "title": "基本信息",
                "items": [
                    {"label": "项目名称", "value": data["project_name"]},
                    {"label": "项目标识", "value": data["project_key"]},
                    {"label": "服务名称", "value": data["service_name"]},
                    {"label": "服务模板", "value": data["template_name"]},
                    {"label": "环境", "value": data["environment"]},
                    {"label": "环境状态", "value": "已存在，无需新建" if env_exists else "不存在，Agent 将新建"},
                    {"label": "工作流名称", "value": data["workflow_name"]},
                ],
            },
            {
                "title": "K8s 集群",
                "items": [
                    {"label": "集群", "value": data["cluster_name"]},
                    {"label": "命名空间", "value": data["namespace"]},
                ],
            },
            {
                "title": "代码源",
                "items": [
                    {"label": "代码源", "value": data["codehost_name"]},
                    {"label": "组织/用户", "value": data["repo_namespace"]},
                    {"label": "代码库", "value": data["repo_name"]},
                    {"label": "分支", "value": data["branch"]},
                    {"label": "Values 文件", "value": data["values_file"] or "使用 Chart 默认值"},
                    {"label": "自动同步 Values", "value": "是" if data["values_auto_sync"] else "否" if data["values_file"] else "—"},
                    {"label": "构建上下文", "value": data["build_context_dir"]},
                    {"label": "Dockerfile", "value": data["dockerfile_path"]},
                ],
            },
            {
                "title": "构建变量",
                "items": [
                    {"label": item["key"], "value": _format_build_variable(item)}
                    for item in data["build_variables"]
                    if isinstance(item, dict) and str(item.get("key") or "").strip()
                ]
                or [{"label": "—", "value": "未配置"}],
            },
        ],
        "skill_name": "add_helm_service",
    }
    result: dict[str, Any] = {
        "project_key": data["project_key"],
        "preview": preview,
        "agent": agent,
    }
    try:
        from webapi.agent_resources import public_execution_context, resolve_execution_resources

        ctx = public_execution_context(resolve_execution_resources(payload, result))
        preview["skill_name"] = ctx["skill"]["name"]
        result["agent"]["workflow"]["template_name"] = ctx["workflow_template"]["name"]
        preview["sections"].append(
            {
                "title": "Agent 资源",
                "items": [
                    {"label": "Skill", "value": f"{ctx['skill']['name']}（{ctx['skill']['display_name']}）"},
                    {"label": "工作流模板", "value": f"{ctx['workflow_template']['name']}（{ctx['workflow_template']['display_name']}）"},
                    {"label": "MCP", "value": f"{ctx['mcp']['server']} · {ctx['catalog']['mcp_tools_count']} 工具"},
                ],
            }
        )
        result["execution_resources"] = ctx
    except Exception:
        pass
    return result


def list_registries() -> list[dict[str, str]]:
    data = zadig_request("GET", "/openapi/system/registry")
    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("registries") or data.get("items") or []
    else:
        items = []
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        registry_id = str(item.get("id") or item.get("registry_id") or "").strip()
        if not registry_id:
            continue
        address = str(item.get("address") or item.get("url") or "").strip().rstrip("/")
        namespace = str(item.get("namespace") or "").strip()
        label = f"{address}/{namespace}" if address and namespace else address or registry_id
        out.append(
            {
                "registry_id": registry_id,
                "address": address,
                "namespace": namespace,
                "label": label,
                "is_default": bool(item.get("is_default")),
            }
        )
    return out


def list_project_workflow_names(project_key: str) -> list[str]:
    key = str(project_key or "").strip()
    if not key:
        return []
    data = zadig_request("GET", "/openapi/workflows", params={"projectKey": key})
    rows = data.get("workflows") if isinstance(data, dict) else []
    names: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for field in ("workflow_key", "workflow_name", "name"):
            name = str(row.get(field) or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def workflow_exists_in_project(project_key: str, workflow_name: str) -> bool:
    target = str(workflow_name or "").strip().lower()
    if not target:
        return False
    return any(name.lower() == target for name in list_project_workflow_names(project_key))


def list_project_build_services(project_key: str, page_size: int = 200) -> list[dict[str, str]]:
    key = str(project_key or "").strip()
    if not key:
        return []
    data = zadig_request(
        "GET",
        "/openapi/build",
        params={"projectKey": key, "pageNum": 1, "pageSize": page_size},
    )
    builds = data.get("builds") if isinstance(data, dict) else []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for build in builds or []:
        if not isinstance(build, dict):
            continue
        build_name = str(build.get("name") or "").strip()
        for target in build.get("target_services") or []:
            if not isinstance(target, dict):
                continue
            service_name = str(target.get("service_name") or "").strip()
            service_module = str(target.get("service_module") or service_name).strip()
            if not service_name or not build_name:
                continue
            dedupe = f"{service_name}:{service_module}:{build_name}"
            if dedupe in seen:
                continue
            seen.add(dedupe)
            out.append(
                {
                    "service_name": service_name,
                    "service_module": service_module,
                    "build_name": build_name,
                    "image_name": service_module,
                    "label": f"{service_name} / {build_name}",
                }
            )
    out.sort(key=lambda item: item["label"])
    return out


def _resolve_build_for_service(project_key: str, service_name: str) -> dict[str, str] | None:
    target = str(service_name or "").strip().lower()
    if not target:
        return None
    for item in list_project_build_services(project_key):
        if item["service_name"].lower() == target:
            return item
    return None


def _validate_add_workflow_input(payload: dict[str, Any]) -> dict[str, Any]:
    project_key = str(payload.get("project_key") or "").strip()
    project_name = str(payload.get("project_name") or project_key).strip()
    environment = str(payload.get("environment") or "").strip()
    workflow_name = str(payload.get("workflow_name") or "").strip()
    registry_id = str(payload.get("registry_id") or "").strip()
    registry_label = str(payload.get("registry_label") or registry_id).strip()
    service_name = str(payload.get("service_name") or "").strip()
    service_module = str(payload.get("service_module") or service_name).strip()
    build_name = str(payload.get("build_name") or "").strip()
    image_name = str(payload.get("image_name") or service_module or service_name).strip()
    deploy_production = bool(payload.get("deploy_production", False))
    deploy_env_name = str(payload.get("deploy_env_name") or environment).strip()

    if not project_key:
        raise ValueError("请选择项目")
    if not environment:
        raise ValueError("请选择或填写环境")
    if not workflow_name:
        raise ValueError("工作流名称不能为空")
    if workflow_exists_in_project(project_key, workflow_name):
        raise ValueError(f"项目 {project_key} 中已存在工作流 {workflow_name}")
    if not registry_id:
        raise ValueError("请选择镜像仓库")
    if not service_name:
        raise ValueError("请选择服务组件")
    if not build_name:
        matched = _resolve_build_for_service(project_key, service_name)
        if not matched:
            raise ValueError(f"项目 {project_key} 中未找到服务 {service_name} 对应的构建")
        build_name = matched["build_name"]
        service_module = matched["service_module"]
        image_name = matched["image_name"]
    if not deploy_env_name:
        raise ValueError("请选择部署环境")
    deploy_envs = list_project_environments(project_key, production=deploy_production)
    if deploy_envs and not any(item["env_name"] == deploy_env_name for item in deploy_envs):
        env_type = "生产环境" if deploy_production else "测试环境"
        raise ValueError(f"部署环境 {deploy_env_name} 不在项目 {project_key} 的{env_type}列表中")

    return {
        "application_type": "add_workflow",
        "project_name": project_name,
        "project_key": project_key,
        "environment": environment,
        "workflow_name": workflow_name,
        "registry_id": registry_id,
        "registry_label": registry_label,
        "service_name": service_name,
        "service_module": service_module,
        "build_name": build_name,
        "image_name": image_name,
        "deploy_production": deploy_production,
        "deploy_env_name": deploy_env_name,
    }


def build_add_workflow_plan(payload: dict[str, Any]) -> dict[str, Any]:
    data = _validate_add_workflow_input(payload)
    workflow = {
        "project": data["project_key"],
        "name": data["workflow_name"],
        "display_name": data["workflow_name"],
        "registry_id": data["registry_id"],
        "service_name": data["service_name"],
        "build_name": data["build_name"],
        "image_name": data["image_name"],
        "env_name": data["deploy_env_name"],
        "production": data["deploy_production"],
        "template_name": "workflow_build_deploy",
    }
    deploy_type_label = "生产环境" if data["deploy_production"] else "测试环境"
    preview = {
        "project_key": data["project_key"],
        "application_type": "add_workflow",
        "sections": [
            {
                "title": "基本信息",
                "items": [
                    {"label": "项目名称", "value": data["project_name"]},
                    {"label": "项目标识", "value": data["project_key"]},
                    {"label": "环境", "value": data["environment"]},
                    {"label": "工作流名称", "value": data["workflow_name"]},
                ],
            },
            {
                "title": "构建",
                "items": [
                    {"label": "镜像仓库", "value": data["registry_label"]},
                    {"label": "服务组件", "value": data["service_name"]},
                    {"label": "构建名称", "value": data["build_name"]},
                ],
            },
            {
                "title": "部署",
                "items": [
                    {"label": "环境类型", "value": deploy_type_label},
                    {"label": "部署环境", "value": data["deploy_env_name"]},
                    {"label": "环境要求", "value": "必须为项目中已存在的环境"},
                ],
            },
        ],
        "skill_name": "add_helm_workflow",
    }
    result: dict[str, Any] = {
        "project_key": data["project_key"],
        "preview": preview,
        "agent": {
            "env_must_exist": True,
            "workflow": workflow,
        },
    }
    try:
        from webapi.agent_resources import public_execution_context, resolve_execution_resources

        ctx = public_execution_context(resolve_execution_resources(payload, result))
        preview["skill_name"] = ctx["skill"]["name"]
        result["agent"]["workflow"]["template_name"] = ctx["workflow_template"]["name"]
        preview["sections"].append(
            {
                "title": "Agent 资源",
                "items": [
                    {"label": "Skill", "value": f"{ctx['skill']['name']}（{ctx['skill']['display_name']}）"},
                    {"label": "工作流模板", "value": f"{ctx['workflow_template']['name']}（{ctx['workflow_template']['display_name']}）"},
                    {"label": "MCP", "value": f"{ctx['mcp']['server']} · {ctx['catalog']['mcp_tools_count']} 工具"},
                ],
            }
        )
        result["execution_resources"] = ctx
    except Exception:
        pass
    return result


def _validate_add_environment_input(payload: dict[str, Any]) -> dict[str, Any]:
    project_key = str(payload.get("project_key") or "").strip()
    project_name = str(payload.get("project_name") or project_key).strip()
    environment = str(payload.get("environment") or "").strip()
    environment_production = bool(payload.get("environment_production", False))
    cluster_name = str(payload.get("cluster_name") or "").strip()
    namespace = str(payload.get("namespace") or "").strip()
    registry_id = str(payload.get("registry_id") or "").strip()
    registry_label = str(payload.get("registry_label") or registry_id).strip()

    if not project_key:
        raise ValueError("请选择项目")
    if not environment:
        raise ValueError("请填写环境名称")
    if not _ENV_KEY_RE.match(environment):
        raise ValueError("环境名称需以字母开头，只能包含字母、数字、下划线和中划线")
    if environment_exists_in_project(project_key, environment, production=environment_production):
        env_type = "生产环境" if environment_production else "测试环境"
        raise ValueError(f"项目 {project_key} 的{env_type}中已存在环境 {environment}")
    if not cluster_name:
        raise ValueError("请选择 K8s 集群")
    if not namespace:
        raise ValueError("请填写或选择 K8s 命名空间")
    if not registry_id:
        raise ValueError("请选择镜像仓库")

    return {
        "application_type": "add_environment",
        "project_name": project_name,
        "project_key": project_key,
        "environment": environment,
        "environment_production": environment_production,
        "cluster_name": cluster_name,
        "namespace": namespace,
        "registry_id": registry_id,
        "registry_label": registry_label,
    }


def build_add_environment_plan(payload: dict[str, Any]) -> dict[str, Any]:
    data = _validate_add_environment_input(payload)
    production = bool(data.get("environment_production", False))
    env_name = data["environment"]
    existing_envs = list_project_environments(data["project_key"], production=production)
    env_exists = any(item["env_name"] == env_name for item in existing_envs)
    helm_environment: dict[str, Any] = {
        "project_key": data["project_key"],
        "env_name": env_name,
        "cluster_id": _cluster_id(data["cluster_name"]),
        "namespace": data["namespace"],
        "registry_id": data["registry_id"],
        "production": production,
    }
    env_type_label = "生产环境" if production else "测试环境"
    preview = {
        "project_key": data["project_key"],
        "application_type": "add_environment",
        "sections": [
            {
                "title": "基本信息",
                "items": [
                    {"label": "项目名称", "value": data["project_name"]},
                    {"label": "项目标识", "value": data["project_key"]},
                    {"label": "环境类型", "value": env_type_label},
                    {"label": "环境名称", "value": env_name},
                    {"label": "环境状态", "value": "已存在，无需新建" if env_exists else "不存在，Agent 将新建"},
                ],
            },
            {
                "title": "K8s 集群",
                "items": [
                    {"label": "集群", "value": data["cluster_name"]},
                    {"label": "命名空间", "value": data["namespace"]},
                    {"label": "镜像仓库", "value": data["registry_label"]},
                ],
            },
        ],
        "skill_name": "add_helm_environment",
    }
    agent: dict[str, Any] = {
        "env_exists": env_exists,
        "helm_environment": helm_environment,
    }
    result: dict[str, Any] = {
        "project_key": data["project_key"],
        "preview": preview,
        "agent": agent,
    }
    try:
        from webapi.agent_resources import public_execution_context, resolve_execution_resources

        ctx = public_execution_context(resolve_execution_resources(payload, result))
        preview["skill_name"] = ctx["skill"]["name"]
        preview["sections"].append(
            {
                "title": "执行资源",
                "items": [
                    {"label": "Skill", "value": ctx["skill"]["display_name"] or ctx["skill"]["name"]},
                    {"label": "MCP", "value": ctx["mcp"]["server"]},
                ],
            }
        )
        result["execution_resources"] = ctx
    except Exception:
        pass
    return result


def build_application_plan(payload: dict[str, Any]) -> dict[str, Any]:
    app_type = str(payload.get("application_type") or "create_project").strip()
    if app_type == "add_service":
        return build_add_service_plan(payload)
    if app_type == "add_workflow":
        return build_add_workflow_plan(payload)
    if app_type == "add_environment":
        return build_add_environment_plan(payload)
    return build_project_plan(payload)


def _format_build_variable(item: dict[str, Any]) -> str:
    key = str(item.get("key") or "").strip()
    ptype = str(item.get("type") or "string")
    if ptype == "string":
        return str(item.get("value") or "")
    if ptype == "choice":
        options = str(item.get("options") or "")
        value = str(item.get("value") or "")
        return f"{value}（选项：{options}）"
    multi = item.get("multi_value") or []
    if isinstance(multi, list):
        selected = ", ".join(str(v) for v in multi if str(v).strip())
    else:
        selected = str(item.get("value") or "")
    options = str(item.get("options") or "")
    return f"{selected}（选项：{options}）"


def create_project(payload: dict[str, Any]) -> dict[str, Any]:
    plan = build_project_plan(payload)
    agent = plan["agent"]
    project_result = zadig_request(
        "POST",
        "/openapi/projects/project/init/helm",
        json_data=agent["helm_project"],
    )
    build_result = zadig_request(
        "POST",
        "/openapi/build",
        params={"projectKey": plan["project_key"]},
        json_data=agent["build"],
    )
    binding_results: list[dict[str, Any]] = []
    for item in agent["role_bindings"]:
        result = zadig_request(
            "POST",
            "/openapi/policy/role-bindings",
            params={"namespace": plan["project_key"]},
            json_data={"role": item["role"], "uid": item["identities"][0]["uid"]},
        )
        binding_results.append({"uid": item["identities"][0]["uid"], "role": item["role"], "result": result})
    return {
        "project_key": plan["project_key"],
        "project": project_result,
        "build": build_result,
        "bindings": binding_results,
    }

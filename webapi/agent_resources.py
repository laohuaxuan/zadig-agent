"""Agent 执行时自动加载并选择 Skill、Template、MCP 资源。"""

from __future__ import annotations

from typing import Any

from webapi.catalog import get_skill, list_mcp_skills, list_skills
from webapi.templates_catalog import get_template, list_templates

_DEFAULT_HELM_SKILL = "create_helm_project"
_DEFAULT_ADD_SERVICE_SKILL = "add_helm_service"
_DEFAULT_ADD_WORKFLOW_SKILL = "add_helm_workflow"
_DEFAULT_ADD_ENVIRONMENT_SKILL = "add_helm_environment"
_DEFAULT_WORKFLOW_TEMPLATE = "workflow_build_deploy"


def _skill_names(skills: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("name") or "") for item in skills}


def _template_names(templates: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("name") or "") for item in templates}


def load_skill_content(name: str) -> tuple[dict[str, Any], str]:
    text = str(name or "").strip()
    if not text:
        raise ValueError("Skill 标识不能为空")
    item = get_skill(text)
    content = str(item.get("content") or "").strip()
    if not content:
        raise ValueError(f"Skill {text} 缺少 content")
    return item, content


def _resolve_skill(payload: dict[str, Any], plan: dict[str, Any], skills: list[dict[str, Any]]) -> dict[str, Any]:
    names = _skill_names(skills)
    explicit = str(
        payload.get("skill_name") or (plan.get("preview") or {}).get("skill_name") or ""
    ).strip()
    if explicit:
        if explicit in names:
            return next(item for item in skills if item["name"] == explicit)
        return {"name": explicit, "display_name": explicit, "source": "unknown", "description": ""}

    if str(payload.get("application_type") or "").strip() == "add_service":
        if _DEFAULT_ADD_SERVICE_SKILL in names:
            return next(item for item in skills if item["name"] == _DEFAULT_ADD_SERVICE_SKILL)

    if str(payload.get("application_type") or "").strip() == "add_workflow":
        if _DEFAULT_ADD_WORKFLOW_SKILL in names:
            return next(item for item in skills if item["name"] == _DEFAULT_ADD_WORKFLOW_SKILL)

    if str(payload.get("application_type") or "").strip() == "add_environment":
        if _DEFAULT_ADD_ENVIRONMENT_SKILL in names:
            return next(item for item in skills if item["name"] == _DEFAULT_ADD_ENVIRONMENT_SKILL)

    if payload.get("project_name") and payload.get("template_name") and not payload.get("application_type"):
        if _DEFAULT_HELM_SKILL in names:
            return next(item for item in skills if item["name"] == _DEFAULT_HELM_SKILL)

    if payload.get("project_key") and payload.get("service_name") and str(payload.get("application_type") or "") == "add_service":
        if _DEFAULT_ADD_SERVICE_SKILL in names:
            return next(item for item in skills if item["name"] == _DEFAULT_ADD_SERVICE_SKILL)

    if payload.get("project_key") and payload.get("workflow_name") and str(payload.get("application_type") or "") == "add_workflow":
        if _DEFAULT_ADD_WORKFLOW_SKILL in names:
            return next(item for item in skills if item["name"] == _DEFAULT_ADD_WORKFLOW_SKILL)

    if payload.get("project_key") and payload.get("environment") and str(payload.get("application_type") or "") == "add_environment":
        if _DEFAULT_ADD_ENVIRONMENT_SKILL in names:
            return next(item for item in skills if item["name"] == _DEFAULT_ADD_ENVIRONMENT_SKILL)

    keywords = " ".join(
        [
            str(payload.get("project_name") or ""),
            str(payload.get("service_name") or ""),
            str(payload.get("template_name") or ""),
            "helm",
            "chart",
        ]
    ).lower()
    best: dict[str, Any] | None = None
    best_score = -1
    for item in skills:
        text = f"{item.get('name') or ''} {item.get('description') or ''} {item.get('display_name') or ''}".lower()
        score = 0
        if item["name"] == _DEFAULT_HELM_SKILL:
            score += 10
        if item["name"] == _DEFAULT_ADD_SERVICE_SKILL and str(payload.get("application_type") or "") == "add_service":
            score += 12
        if item["name"] == _DEFAULT_ADD_WORKFLOW_SKILL and str(payload.get("application_type") or "") == "add_workflow":
            score += 12
        if item["name"] == _DEFAULT_ADD_ENVIRONMENT_SKILL and str(payload.get("application_type") or "") == "add_environment":
            score += 12
        if "helm" in keywords and "helm" in text:
            score += 4
        if "chart" in keywords and "chart" in text:
            score += 2
        if "create" in text and ("项目" in text or "project" in text):
            score += 2
        if score > best_score:
            best_score = score
            best = item
    if best:
        return best
    if _DEFAULT_HELM_SKILL in names:
        return next(item for item in skills if item["name"] == _DEFAULT_HELM_SKILL)
    if skills:
        return skills[0]
    return {"name": _DEFAULT_HELM_SKILL, "display_name": _DEFAULT_HELM_SKILL, "source": "unknown", "description": ""}


def _resolve_workflow_template(
    payload: dict[str, Any],
    plan: dict[str, Any],
    templates: list[dict[str, Any]],
) -> dict[str, Any]:
    names = _template_names(templates)
    workflow = (plan.get("agent") or {}).get("workflow") or {}
    explicit = str(
        workflow.get("template_name")
        or payload.get("workflow_template_name")
        or payload.get("agent_template_name")
        or ""
    ).strip()
    if explicit and explicit in names:
        return next(item for item in templates if item["name"] == explicit)
    if explicit:
        try:
            return get_template(explicit)
        except LookupError:
            pass

    if payload.get("workflow_name") or payload.get("environment"):
        if _DEFAULT_WORKFLOW_TEMPLATE in names:
            return next(item for item in templates if item["name"] == _DEFAULT_WORKFLOW_TEMPLATE)

    workflow_templates = [item for item in templates if str(item.get("category") or "") == "workflow"]
    if workflow_templates:
        return workflow_templates[0]
    if templates:
        return templates[0]
    return get_template(_DEFAULT_WORKFLOW_TEMPLATE)


def _mcp_modules(mcp_items: list[dict[str, Any]]) -> list[str]:
    modules = sorted({str(item.get("module") or "").strip() for item in mcp_items if item.get("module")})
    return modules


def resolve_execution_resources(payload: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    skills = list_skills()
    templates = list_templates()
    mcp_items = list_mcp_skills()

    skill_pick = _resolve_skill(payload, plan, skills)
    skill_item, skill_content = load_skill_content(skill_pick["name"])

    template_pick = _resolve_workflow_template(payload, plan, templates)

    workflow = dict((plan.get("agent") or {}).get("workflow") or {})
    workflow["template_name"] = template_pick["name"]
    if plan.get("agent") is not None:
        plan["agent"]["workflow"] = workflow

    chart_template = str(payload.get("template_name") or "").strip()
    modules = _mcp_modules(mcp_items)

    return {
        "skill": {
            "name": skill_item["name"],
            "display_name": skill_item.get("display_name") or skill_item["name"],
            "source": skill_item.get("source") or "",
            "description": skill_item.get("description") or "",
        },
        "workflow_template": {
            "name": template_pick["name"],
            "display_name": template_pick.get("display_name") or template_pick["name"],
            "source": template_pick.get("source") or "",
            "category": template_pick.get("category") or "workflow",
            "description": template_pick.get("description") or "",
        },
        "service_template": {
            "name": chart_template,
            "label": "Chart 服务模板",
        },
        "mcp": {
            "server": "zadig",
            "transport": "stdio",
            "source": "builtin",
            "registered_tools": len(mcp_items),
            "modules": modules,
        },
        "catalog": {
            "skills": [{"name": i["name"], "display_name": i.get("display_name") or i["name"]} for i in skills],
            "templates": [{"name": i["name"], "display_name": i.get("display_name") or i["name"]} for i in templates],
            "skills_count": len(skills),
            "templates_count": len(templates),
            "mcp_tools_count": len(mcp_items),
        },
        "skill_content": skill_content,
    }


def public_execution_context(ctx: dict[str, Any]) -> dict[str, Any]:
    data = dict(ctx)
    data.pop("skill_content", None)
    return data


def format_execution_resources_log(ctx: dict[str, Any], *, runtime_tool_count: int | None = None) -> str:
    skill = ctx["skill"]
    tpl = ctx["workflow_template"]
    chart = ctx.get("service_template") or {}
    mcp = ctx["mcp"]
    cat = ctx["catalog"]
    tool_line = f"{runtime_tool_count}（运行时）" if runtime_tool_count is not None else str(mcp["registered_tools"])
    lines = [
        "📦 执行资源（自动选择）",
        "=" * 60,
        f"Skill: {skill['name']} ({skill['display_name']}) [{skill['source']}]",
        f"工作流模板: {tpl['name']} ({tpl['display_name']}) [{tpl['source']}]",
    ]
    if chart.get("name"):
        lines.append(f"Chart 服务模板: {chart['name']}")
    lines.append(f"MCP: {mcp['server']} ({mcp['transport']}, {mcp['source']}) · 工具 {tool_line}")
    if mcp.get("modules"):
        preview = ", ".join(mcp["modules"][:6])
        if len(mcp["modules"]) > 6:
            preview += f" 等 {len(mcp['modules'])} 个模块"
        lines.append(f"  MCP 模块: {preview}")
    lines.append(
        f"目录已加载: Skills {cat['skills_count']} · Templates {cat['templates_count']} · MCP {cat['mcp_tools_count']}"
    )
    lines.append("=" * 60 + "\n")
    return "\n".join(lines) + "\n"


def format_execution_resources_meta_line(ctx: dict[str, Any]) -> str:
    skill = ctx["skill"]["name"]
    tpl = ctx["workflow_template"]["name"]
    mcp = ctx["mcp"]["server"]
    return f"Skill: {skill} | Template: {tpl} | MCP: {mcp}"

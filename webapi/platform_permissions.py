"""平台角色权限矩阵。"""

from __future__ import annotations

from typing import Any

from webapi.platform_roles import ROLE_ADMIN, ROLE_ROOT, ROLE_WATCHER


def can_view_integration(role: str) -> bool:
    return role in {ROLE_ADMIN, ROLE_ROOT}


def can_view_approval_config(role: str) -> bool:
    return role in {ROLE_ADMIN, ROLE_ROOT}


def can_modify_approval_config(role: str) -> bool:
    return role in {ROLE_ADMIN, ROLE_ROOT}


def can_manage_users(role: str) -> bool:
    return role in {ROLE_ADMIN, ROLE_ROOT}


def can_modify_users(role: str) -> bool:
    return role == ROLE_ROOT


def can_manage_skills(role: str) -> bool:
    return role in {ROLE_ADMIN, ROLE_ROOT}


def can_manage_any_skill(role: str) -> bool:
    return role == ROLE_ROOT


def can_manage_templates(role: str) -> bool:
    return role in {ROLE_ADMIN, ROLE_ROOT}


def can_manage_any_template(role: str) -> bool:
    return role == ROLE_ROOT


def can_manage_agents(role: str) -> bool:
    return role == ROLE_ROOT


def can_manage_zadig(role: str) -> bool:
    return role == ROLE_ROOT


def build_permissions(role: str) -> dict[str, bool]:
    return {
        "can_view_integration": can_view_integration(role),
        "can_view_approval_config": can_view_approval_config(role),
        "can_modify_approval_config": can_modify_approval_config(role),
        "can_manage_users": can_manage_users(role),
        "can_modify_users": can_modify_users(role),
        "can_manage_skills": can_manage_skills(role),
        "can_manage_any_skill": can_manage_any_skill(role),
        "can_manage_templates": can_manage_templates(role),
        "can_manage_any_template": can_manage_any_template(role),
        "can_manage_agents": can_manage_agents(role),
        "can_manage_zadig": can_manage_zadig(role),
        # 兼容旧字段：审批配置页导航
        "can_manage_approval_config": can_view_approval_config(role),
    }


def _user_id(user: dict[str, Any]) -> int:
    return int(user.get("id") or 0)


def _maintainer_id(item: dict[str, Any]) -> int | None:
    raw = item.get("maintainer_id")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def can_manage_skill_item(user: dict[str, Any], item: dict[str, Any]) -> bool:
    role = str(user.get("role") or ROLE_WATCHER)
    source = str(item.get("source") or "mysql")
    if source == "builtin":
        return False
    if role == ROLE_ROOT:
        return True
    if role == ROLE_ADMIN:
        if source != "mysql":
            return False
        maintainer = _maintainer_id(item)
        return maintainer is not None and maintainer == _user_id(user)
    return False


def can_manage_template_item(user: dict[str, Any], item: dict[str, Any]) -> bool:
    role = str(user.get("role") or ROLE_WATCHER)
    source = str(item.get("source") or "mysql")
    if source != "mysql":
        return False
    if role == ROLE_ROOT:
        return True
    if role == ROLE_ADMIN:
        maintainer = _maintainer_id(item)
        return maintainer is not None and maintainer == _user_id(user)
    return False


def apply_skill_acl(user: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item)
    allowed = can_manage_skill_item(user, item)
    enriched["editable"] = allowed
    enriched["deletable"] = allowed
    return enriched


def apply_template_acl(user: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item)
    allowed = can_manage_template_item(user, item)
    enriched["editable"] = allowed
    enriched["deletable"] = allowed
    return enriched


def require_skill_manage(user: dict[str, Any], item: dict[str, Any]) -> None:
    if not can_manage_skill_item(user, item):
        raise PermissionError("无权修改该技能")


def require_template_manage(user: dict[str, Any], item: dict[str, Any]) -> None:
    if not can_manage_template_item(user, item):
        raise PermissionError("无权修改该模板")

"""平台角色与权限（对齐 mse-domain-binding）。"""

from __future__ import annotations

ROLE_ROOT = "root"
ROLE_ADMIN = "admin"
ROLE_WATCHER = "watcher"

ROLE_LABELS = {
    ROLE_ROOT: "超级管理员",
    ROLE_ADMIN: "管理员",
    ROLE_WATCHER: "普通成员",
}

WORKFLOW_TYPE_HELM_PROJECT = "Helm项目申请"
WORKFLOW_TYPE_ADD_SERVICE = "Helm添加服务申请"
WORKFLOW_TYPE_ADD_WORKFLOW = "Helm添加工作流申请"


def role_label(role: str) -> str:
    return ROLE_LABELS.get(str(role or "").strip(), role or "")


def can_manage_users(role: str) -> bool:
    return role in {ROLE_ROOT, ROLE_ADMIN}


def can_modify_users(role: str) -> bool:
    return role == ROLE_ROOT


def can_manage_approval_config(role: str) -> bool:
    return role in {ROLE_ROOT, ROLE_ADMIN}


def is_approver_role(role: str) -> bool:
    return role in {ROLE_ROOT, ROLE_ADMIN}


def can_operate_user(actor_role: str, target_role: str) -> bool:
    if actor_role == ROLE_ROOT:
        return True
    if actor_role == ROLE_ADMIN:
        return target_role == ROLE_WATCHER
    return False

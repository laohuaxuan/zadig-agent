"""平台用户存储与 CRUD。"""

from __future__ import annotations

import json
import re
import secrets
import string
import uuid
from typing import Any

PHONE_REGEX = re.compile(r"^1[3-9]\d{9}$")
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PASSWORD_RULE_ERROR = "密码不符合规范（需包含大小写字母、数字、特殊字符，不少于6位且不超过24位）"
FEISHU_PASSWORD_HINT = "飞书用户请在飞书客户端修改账号密码"

from utils.db import _now, execute, query, query_one
from webapi.platform_auth import hash_password, verify_password
from webapi.platform_roles import ROLE_ROOT, ROLE_WATCHER, can_operate_user, role_label


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    display = str(row.get("display_name") or row.get("name") or "").strip()
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "display_name": display or row["name"],
        "phone": row.get("phone") or "",
        "email": row.get("email") or "",
        "auth_source": row.get("auth_source") or "local",
        "feishu_open_id": row.get("feishu_open_id") or "",
        "role": row.get("role") or ROLE_WATCHER,
        "role_label": role_label(str(row.get("role") or ROLE_WATCHER)),
        "status": row.get("status") or "active",
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def persist_feishu_open_id_if_empty(user_id: int, open_id: str) -> None:
    text = str(open_id or "").strip()
    if user_id <= 0 or not text:
        return
    execute(
        """
        UPDATE platform_users
        SET feishu_open_id = %s, updated_at = %s
        WHERE id = %s AND deleted_at IS NULL
          AND (feishu_open_id IS NULL OR feishu_open_id = '')
        """,
        (text, _now(), user_id),
    )


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    row = query_one(
        "SELECT * FROM platform_users WHERE id = %s AND deleted_at IS NULL",
        (user_id,),
    )
    return _public_user(row) if row else None


def get_user_row_by_id(user_id: int) -> dict[str, Any] | None:
    return query_one("SELECT * FROM platform_users WHERE id = %s AND deleted_at IS NULL", (user_id,))


def get_user_by_name(name: str) -> dict[str, Any] | None:
    row = query_one(
        "SELECT * FROM platform_users WHERE name = %s AND deleted_at IS NULL",
        (name.strip(),),
    )
    return row


def get_user_by_feishu_open_id(open_id: str) -> dict[str, Any] | None:
    row = query_one(
        "SELECT * FROM platform_users WHERE feishu_open_id = %s AND deleted_at IS NULL",
        (open_id.strip(),),
    )
    return row


def map_users_by_feishu_open_ids(open_ids: list[str]) -> dict[str, int]:
    ids = [str(item).strip() for item in open_ids if str(item).strip()]
    if not ids:
        return {}
    placeholders = ", ".join(["%s"] * len(ids))
    rows = query(
        f"""
        SELECT id, feishu_open_id
        FROM platform_users
        WHERE deleted_at IS NULL AND feishu_open_id IN ({placeholders})
        """,
        tuple(ids),
    )
    out: dict[str, int] = {}
    for row in rows:
        open_id = str(row.get("feishu_open_id") or "").strip()
        if open_id:
            out[open_id] = int(row["id"])
    return out


def authenticate_local(name: str, password: str) -> dict[str, Any] | None:
    row = get_user_by_name(name)
    if not row:
        return None
    if str(row.get("auth_source") or "") != "local":
        return None
    if str(row.get("status") or "").lower() == "disabled":
        return None
    if not verify_password(password, str(row.get("password_hash") or "")):
        return None
    return _public_user(row)


def ensure_feishu_user(info: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    open_id = str(info.get("open_id") or "").strip()
    if not open_id:
        raise ValueError("飞书 open_id 不能为空")
    existing = get_user_by_feishu_open_id(open_id)
    now = _now()
    name = str(info.get("name") or open_id[:12]).strip() or open_id[:12]
    display = name
    email = str(info.get("email") or "").strip() or f"{open_id}@feishu.local"
    phone = str(info.get("mobile") or "").strip() or None
    if existing:
        execute(
            """
            UPDATE platform_users
            SET display_name = %s, email = %s, phone = %s, updated_at = %s
            WHERE id = %s
            """,
            (display, email, phone, now, existing["id"]),
        )
        return _public_user(get_user_row_by_id(int(existing["id"])) or existing), False
    base_name = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in name.lower())[:40] or f"fs-{open_id[:8]}"
    candidate = base_name
    suffix = 1
    while get_user_by_name(candidate):
        candidate = f"{base_name}-{suffix}"
        suffix += 1
    execute(
        """
        INSERT INTO platform_users
        (name, display_name, phone, email, password_hash, auth_source, feishu_open_id, role, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, '', 'feishu', %s, %s, 'active', %s, %s)
        """,
        (candidate, display, phone, email, open_id, ROLE_WATCHER, now, now),
    )
    row = get_user_by_feishu_open_id(open_id)
    if not row:
        raise ValueError("创建飞书用户失败")
    return _public_user(row), True


def list_users(page: int, page_size: int, keyword: str = "") -> tuple[list[dict[str, Any]], int]:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    where = "deleted_at IS NULL"
    args: list[Any] = []
    if keyword.strip():
        where += " AND (name LIKE %s OR display_name LIKE %s OR email LIKE %s OR phone LIKE %s)"
        like = f"%{keyword.strip()}%"
        args.extend([like, like, like, like])
    total_row = query_one(f"SELECT COUNT(*) AS n FROM platform_users WHERE {where}", tuple(args))
    total = int(total_row["n"]) if total_row else 0
    offset = (page - 1) * page_size
    rows = query(
        f"""
        SELECT * FROM platform_users
        WHERE {where}
        ORDER BY id ASC
        LIMIT %s OFFSET %s
        """,
        (*args, page_size, offset),
    )
    return [_public_user(row) for row in rows], total


def list_approver_candidates() -> list[dict[str, Any]]:
    rows = query(
        """
        SELECT * FROM platform_users
        WHERE deleted_at IS NULL AND status = 'active'
        ORDER BY id ASC
        """
    )
    return [_public_user(row) for row in rows]


def list_approver_users() -> list[dict[str, Any]]:
    rows = query(
        """
        SELECT * FROM platform_users
        WHERE deleted_at IS NULL AND status = 'active' AND role IN ('root', 'admin')
        ORDER BY id ASC
        """
    )
    return [_public_user(row) for row in rows]


def create_local_user(payload: dict[str, Any], actor_role: str) -> dict[str, Any]:
    from webapi.platform_roles import can_modify_users

    if not can_modify_users(actor_role):
        raise PermissionError("仅超级管理员可创建用户")
    name = str(payload.get("name") or "").strip()
    password = str(payload.get("password") or "").strip()
    role = str(payload.get("role") or ROLE_WATCHER).strip()
    if not name:
        raise ValueError("用户名不能为空")
    if not password:
        raise ValueError("密码不能为空")
    if get_user_by_name(name):
        raise ValueError("用户名已存在")
    now = _now()
    execute(
        """
        INSERT INTO platform_users
        (name, display_name, phone, email, password_hash, auth_source, role, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'local', %s, 'active', %s, %s)
        """,
        (
            name,
            str(payload.get("display_name") or name).strip() or name,
            str(payload.get("phone") or "").strip() or None,
            str(payload.get("email") or f"{name}@local").strip(),
            hash_password(password),
            role,
            now,
            now,
        ),
    )
    row = get_user_by_name(name)
    return _public_user(row) if row else {}


def update_user(user_id: int, payload: dict[str, Any], actor_role: str) -> dict[str, Any]:
    from webapi.platform_roles import ROLE_ADMIN, can_modify_users

    if not can_modify_users(actor_role):
        raise PermissionError("仅超级管理员可修改用户")
    target_role = str(payload.get("role") or ROLE_WATCHER).strip()
    row = get_user_row_by_id(user_id)
    if not row:
        raise LookupError("用户不存在")
    if not can_operate_user(actor_role, str(row.get("role") or ROLE_WATCHER)):
        raise PermissionError("无权修改该用户")
    if str(row.get("role") or "") == ROLE_ROOT and actor_role != ROLE_ROOT:
        raise PermissionError("不能修改超级管理员")
    if actor_role == ROLE_ADMIN and target_role != ROLE_WATCHER:
        raise PermissionError("管理员仅可将用户角色设置为普通成员")
    if str(row.get("role") or "") == ROLE_ROOT and target_role != ROLE_ROOT:
        roots = query_one("SELECT COUNT(*) AS n FROM platform_users WHERE role = 'root' AND deleted_at IS NULL")
        if roots and int(roots["n"]) <= 1:
            raise ValueError("不能降级最后一个超级管理员")
    display_name = str(payload.get("display_name") or row.get("display_name") or row["name"]).strip()
    if not display_name:
        raise ValueError("请填写显示名")
    if len(display_name) > 120:
        raise ValueError("显示名最长不超过 120 个字符")
    is_feishu = str(row.get("auth_source") or "") == "feishu"
    if is_feishu:
        phone = str(row.get("phone") or "").strip()
        email = str(row.get("email") or "").strip()
    else:
        phone = str(payload.get("phone") or "").strip()
        email = str(payload.get("email") or "").strip()
        if not phone or not PHONE_REGEX.match(phone):
            raise ValueError("请输入有效的手机号码")
        if not email or not EMAIL_REGEX.match(email):
            raise ValueError("请输入有效的邮箱地址")
    now = _now()
    execute(
        """
        UPDATE platform_users
        SET display_name = %s, phone = %s, email = %s, role = %s, updated_at = %s
        WHERE id = %s AND deleted_at IS NULL
        """,
        (
            display_name,
            phone or None,
            email,
            target_role,
            now,
            user_id,
        ),
    )
    updated = get_user_row_by_id(user_id)
    return _public_user(updated) if updated else {}


def update_user_status(user_id: int, status: str, actor_role: str, actor_user_id: int) -> dict[str, Any]:
    from webapi.platform_roles import can_modify_users

    if not can_modify_users(actor_role):
        raise PermissionError("仅超级管理员可修改用户状态")
    if user_id == actor_user_id:
        raise ValueError("不能修改自己的账号状态")
    normalized = str(status or "").strip().lower()
    if normalized not in {"active", "disabled"}:
        raise ValueError("状态无效")
    row = get_user_row_by_id(user_id)
    if not row:
        raise LookupError("用户不存在")
    if not can_operate_user(actor_role, str(row.get("role") or ROLE_WATCHER)):
        raise PermissionError("无权修改该用户")
    if str(row.get("role") or "") == ROLE_ROOT and normalized == "disabled":
        roots = query_one(
            "SELECT COUNT(*) AS n FROM platform_users WHERE role = 'root' AND deleted_at IS NULL AND status = 'active'"
        )
        if roots and int(roots["n"]) <= 1:
            raise ValueError("不能下线最后一个超级管理员")
    execute(
        "UPDATE platform_users SET status = %s, updated_at = %s WHERE id = %s AND deleted_at IS NULL",
        (normalized, _now(), user_id),
    )
    updated = get_user_row_by_id(user_id)
    return _public_user(updated) if updated else {}


def delete_user(user_id: int, actor_role: str) -> None:
    from webapi.platform_roles import can_modify_users

    if not can_modify_users(actor_role):
        raise PermissionError("仅超级管理员可删除用户")
    row = get_user_row_by_id(user_id)
    if not row:
        raise LookupError("用户不存在")
    if str(row.get("role") or "") == ROLE_ROOT:
        roots = query_one("SELECT COUNT(*) AS n FROM platform_users WHERE role = 'root' AND deleted_at IS NULL")
        if roots and int(roots["n"]) <= 1:
            raise ValueError("不能删除最后一个超级管理员")
    execute("UPDATE platform_users SET deleted_at = %s WHERE id = %s", (_now(), user_id))


def _is_password_valid(password: str) -> bool:
    return (
        6 <= len(password) <= 24
        and any(ch.isupper() for ch in password)
        and any(ch.islower() for ch in password)
        and any(ch.isdigit() for ch in password)
        and any(not ch.isalnum() for ch in password)
    )


def update_own_profile(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_user_row_by_id(user_id)
    if not row:
        raise LookupError("用户不存在")
    is_feishu = str(row.get("auth_source") or "") == "feishu"
    phone = str(row.get("phone") or "").strip()
    email = str(row.get("email") or "").strip()
    new_password = str(payload.get("new_password") or "").strip()
    confirm_password = str(payload.get("confirm_password") or "").strip()
    if not is_feishu:
        phone = str(payload.get("phone") or "").strip()
        email = str(payload.get("email") or "").strip()
        if not email:
            raise ValueError("邮箱不能为空")
        if not phone or not PHONE_REGEX.match(phone):
            raise ValueError("请输入有效的手机号码")
        if not EMAIL_REGEX.match(email):
            raise ValueError("请输入有效的邮箱地址")
    if new_password or confirm_password:
        if is_feishu:
            raise ValueError(FEISHU_PASSWORD_HINT)
        if not _is_password_valid(new_password) or new_password != confirm_password:
            raise ValueError(PASSWORD_RULE_ERROR)
    now = _now()
    execute(
        """
        UPDATE platform_users
        SET phone = %s, email = %s, updated_at = %s
        WHERE id = %s AND deleted_at IS NULL
        """,
        (phone or None, email, now, user_id),
    )
    if new_password:
        execute(
            "UPDATE platform_users SET password_hash = %s, updated_at = %s WHERE id = %s",
            (hash_password(new_password), _now(), user_id),
        )
    updated = get_user_row_by_id(user_id)
    return _public_user(updated) if updated else {}


def reset_user_password(user_id: int, actor_role: str) -> str:
    from webapi.platform_roles import can_modify_users

    if not can_modify_users(actor_role):
        raise PermissionError("仅超级管理员可重置密码")
    row = get_user_row_by_id(user_id)
    if not row:
        raise LookupError("用户不存在")
    if str(row.get("auth_source") or "") == "feishu":
        raise ValueError("飞书用户不支持重置密码")
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    password = "".join(secrets.choice(alphabet) for _ in range(12))
    execute(
        "UPDATE platform_users SET password_hash = %s, updated_at = %s WHERE id = %s",
        (hash_password(password), _now(), user_id),
    )
    return password


def write_audit(
    *,
    user_id: int | None,
    username: str,
    display_name: str,
    action: str,
    result: str,
    ip: str,
    detail: str,
) -> None:
    execute(
        """
        INSERT INTO audit_logs
        (user_id, username, display_name, action, result, ip, detail, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, username, display_name, action, result, ip, detail[:1000], _now()),
    )


def new_record_id() -> str:
    return uuid.uuid4().hex

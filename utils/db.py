"""MySQL 连接、建表，以及把旧版 yaml 页面配置迁入数据库。"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor
from yaml import safe_dump

from utils.config import config_path, invalidate_config_cache, load_config, mysql_config

_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
_initialized = False
_KEEP_KEYS = ("server", "mysql", "mcp", "integration")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect(*, database: str | None) -> pymysql.connections.Connection:
    cfg = mysql_config()
    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=database,
        charset=cfg["charset"],
        cursorclass=DictCursor,
        autocommit=False,
    )


@contextmanager
def connection() -> Iterator[pymysql.connections.Connection]:
    ensure_db()
    conn = _connect(database=mysql_config()["database"])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql: str, args: tuple[Any, ...] | list[Any] = ()) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())


def query_one(sql: str, args: tuple[Any, ...] | list[Any] = ()) -> dict[str, Any] | None:
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args: tuple[Any, ...] | list[Any] = ()) -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return int(cur.rowcount)


def executemany(sql: str, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)


def ensure_db() -> None:
    global _initialized
    if _initialized:
        return
    _create_database()
    _create_tables()
    _migrate_yaml_if_needed()
    _migrate_zadig_settings_if_needed()
    _migrate_agent_models_if_needed()
    _migrate_platform_if_needed()
    _migrate_resource_maintainers()
    _migrate_skills_composite_pk()
    _migrate_integration_remarks()
    _migrate_integration_sync_cache()
    _initialized = True
    from webapi.catalog import sync_file_skills_to_db, sync_mcp_to_db
    from webapi.templates_catalog import sync_file_templates_to_db

    sync_file_skills_to_db()
    sync_file_templates_to_db()
    sync_mcp_to_db()


def _create_database() -> None:
    cfg = mysql_config()
    name = cfg["database"]
    if not _DB_NAME_RE.match(name):
        raise ValueError("mysql.database 只能包含字母、数字和下划线")
    conn = _connect(database=None)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def _create_tables() -> None:
    conn = _connect(database=mysql_config()["database"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id VARCHAR(64) NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    api_key TEXT NOT NULL,
                    model VARCHAR(256) NOT NULL,
                    base_url VARCHAR(512) NOT NULL,
                    is_default TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    name VARCHAR(64) NOT NULL,
                    value_json JSON NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (name)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    name VARCHAR(64) NOT NULL,
                    kind VARCHAR(16) NOT NULL,
                    display_name VARCHAR(128) NOT NULL,
                    description TEXT,
                    content TEXT,
                    transport VARCHAR(16) DEFAULT '',
                    command VARCHAR(512) DEFAULT '',
                    args_json JSON,
                    url VARCHAR(512) DEFAULT '',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (name, kind)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_templates (
                    name VARCHAR(64) NOT NULL,
                    display_name VARCHAR(128) NOT NULL,
                    description TEXT,
                    category VARCHAR(32) NOT NULL DEFAULT 'workflow',
                    body_json JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (name)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS zadig_instances (
                    id VARCHAR(64) NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    remark TEXT,
                    base_url VARCHAR(512) NOT NULL,
                    api_token TEXT NOT NULL,
                    is_active TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_resource_remarks (
                    resource_type VARCHAR(32) NOT NULL,
                    resource_key VARCHAR(128) NOT NULL,
                    remark TEXT,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (resource_type, resource_key)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
        conn.commit()
    finally:
        conn.close()


def _migrate_agent_models_if_needed() -> None:
    conn = _connect(database=mysql_config()["database"])
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM agents LIKE 'models_json'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE agents ADD COLUMN models_json JSON NULL AFTER model")
            cur.execute("SELECT id, model, models_json FROM agents")
            rows = cur.fetchall() or []
            for row in rows:
                raw = row.get("models_json")
                if isinstance(raw, str):
                    raw = json.loads(raw)
                if isinstance(raw, dict) and raw.get("primary"):
                    continue
                primary = str(row.get("model") or "").strip()
                if not primary:
                    continue
                cur.execute(
                    "UPDATE agents SET models_json = %s WHERE id = %s",
                    (json.dumps({"primary": primary, "backups": []}, ensure_ascii=False), row["id"]),
                )
        conn.commit()
    finally:
        conn.close()


def _yaml_agents(data: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    block = data.get("agents")
    if isinstance(block, dict) and isinstance(block.get("items"), list):
        for item in block["items"]:
            if not isinstance(item, dict):
                continue
            aid = str(item.get("id") or "").strip()
            if not aid:
                continue
            items.append(
                {
                    "id": aid,
                    "name": str(item.get("name") or aid).strip() or aid,
                    "api_key": str(item.get("api_key") or "").strip(),
                    "model": str(item.get("model") or "").strip(),
                    "base_url": str(item.get("base_url") or "").strip(),
                }
            )
        default_id = str(block.get("default") or (items[0]["id"] if items else "")).strip()
        if items and default_id not in {item["id"] for item in items}:
            default_id = items[0]["id"]
        return default_id, items
    raw = data.get("openrouter") or {}
    if isinstance(raw, dict) and (raw.get("api_key") or raw.get("model") or raw.get("base_url")):
        item = {
            "id": "default",
            "name": "default",
            "api_key": str(raw.get("api_key") or "").strip(),
            "model": str(raw.get("model") or "").strip(),
            "base_url": str(raw.get("base_url") or "").strip(),
        }
        return item["id"], [item]
    return "", []


def _has_legacy_yaml(data: dict[str, Any]) -> bool:
    return any(key in data for key in ("agents", "openrouter", "zadig"))


def _strip_yaml_secrets(data: dict[str, Any]) -> None:
    cleaned = {key: data[key] for key in _KEEP_KEYS if key in data and isinstance(data.get(key), dict)}
    path = config_path()
    path.write_text(
        safe_dump(cleaned, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    invalidate_config_cache()


def _migrate_yaml_if_needed() -> None:
    if not config_path().exists():
        return
    data = dict(load_config())
    if not _has_legacy_yaml(data):
        return
    conn = _connect(database=mysql_config()["database"])
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM agents")
            agent_count = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM settings WHERE name = %s", ("zadig",))
            zadig_count = int(cur.fetchone()["n"])
            now = _now()
            default_id, items = _yaml_agents(data)
            if agent_count == 0 and items:
                cur.executemany(
                    """
                    INSERT INTO agents
                    (id, name, api_key, model, base_url, is_default, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            item["id"],
                            item["name"],
                            item["api_key"],
                            item["model"],
                            item["base_url"],
                            1 if item["id"] == default_id else 0,
                            now,
                            now,
                        )
                        for item in items
                    ],
                )
            raw_zadig = data.get("zadig") if isinstance(data.get("zadig"), dict) else {}
            if zadig_count == 0 and (raw_zadig.get("base_url") or raw_zadig.get("api_token")):
                cur.execute(
                    """
                    INSERT INTO settings (name, value_json, updated_at)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        "zadig",
                        json.dumps(
                            {
                                "base_url": str(raw_zadig.get("base_url") or "").strip().rstrip("/"),
                                "api_token": str(raw_zadig.get("api_token") or "").strip(),
                            },
                            ensure_ascii=False,
                        ),
                        now,
                    ),
                )
        conn.commit()
    finally:
        conn.close()
    _strip_yaml_secrets(data)


def _migrate_zadig_settings_if_needed() -> None:
    conn = _connect(database=mysql_config()["database"])
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM zadig_instances")
            if int(cur.fetchone()["n"]) > 0:
                return
            cur.execute("SELECT value_json FROM settings WHERE name = %s", ("zadig",))
            row = cur.fetchone()
            if not row:
                return
            raw = row["value_json"]
            if isinstance(raw, str):
                raw = json.loads(raw)
            if not isinstance(raw, dict):
                return
            base_url = str(raw.get("base_url") or "").strip().rstrip("/")
            api_token = str(raw.get("api_token") or "").strip()
            if not base_url and not api_token:
                return
            now = _now()
            cur.execute(
                """
                INSERT INTO zadig_instances
                (id, name, remark, base_url, api_token, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
                """,
                ("default", "默认 Zadig", "", base_url, api_token, now, now),
            )
        conn.commit()
    finally:
        conn.close()


def _migrate_resource_maintainers() -> None:
    conn = _connect(database=mysql_config()["database"])
    try:
        with conn.cursor() as cur:
            for table in ("skills", "agent_templates"):
                cur.execute(f"SHOW COLUMNS FROM `{table}` LIKE 'maintainer_id'")
                if not cur.fetchone():
                    cur.execute(f"ALTER TABLE `{table}` ADD COLUMN maintainer_id BIGINT NULL")
        conn.commit()
    finally:
        conn.close()


def _migrate_skills_composite_pk() -> None:
    conn = _connect(database=mysql_config()["database"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = 'skills'
                  AND index_name = 'PRIMARY'
                  AND column_name = 'kind'
                """
            )
            if int((cur.fetchone() or {}).get("cnt") or 0) > 0:
                return
            cur.execute("SHOW KEYS FROM skills WHERE Key_name = 'PRIMARY'")
            pk_cols = [row["Column_name"] for row in cur.fetchall()]
            if pk_cols == ["name", "kind"]:
                return
            if pk_cols != ["name"]:
                return
            cur.execute("ALTER TABLE skills DROP PRIMARY KEY, ADD PRIMARY KEY (name, kind)")
        conn.commit()
    finally:
        conn.close()


def _migrate_integration_sync_cache() -> None:
    conn = _connect(database=mysql_config()["database"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_sync_cache (
                    resource_type VARCHAR(32) NOT NULL,
                    items_json LONGTEXT NOT NULL,
                    synced_at DATETIME NULL,
                    sync_error TEXT NULL,
                    PRIMARY KEY (resource_type)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
        conn.commit()
    finally:
        conn.close()


def _migrate_integration_remarks() -> None:
    conn = _connect(database=mysql_config()["database"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_resource_remarks (
                    resource_type VARCHAR(32) NOT NULL,
                    resource_key VARCHAR(128) NOT NULL,
                    remark TEXT,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (resource_type, resource_key)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
        conn.commit()
    finally:
        conn.close()


def _migrate_platform_if_needed() -> None:
    conn = _connect(database=mysql_config()["database"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_users (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    name VARCHAR(100) NOT NULL,
                    display_name VARCHAR(120) NOT NULL DEFAULT '',
                    phone VARCHAR(30) NULL,
                    email VARCHAR(120) NOT NULL DEFAULT '',
                    password_hash VARCHAR(255) NOT NULL DEFAULT '',
                    auth_source VARCHAR(20) NOT NULL DEFAULT 'local',
                    feishu_open_id VARCHAR(64) NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'watcher',
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    deleted_at DATETIME NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY uk_platform_users_name (name),
                    UNIQUE KEY uk_platform_users_email (email),
                    UNIQUE KEY uk_platform_users_feishu (feishu_open_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    user_id BIGINT NULL,
                    username VARCHAR(100) NOT NULL DEFAULT '',
                    display_name VARCHAR(120) NOT NULL DEFAULT '',
                    action VARCHAR(60) NOT NULL,
                    result VARCHAR(20) NOT NULL DEFAULT '',
                    ip VARCHAR(64) NOT NULL DEFAULT '',
                    detail VARCHAR(1000) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_audit_action (action),
                    KEY idx_audit_user (user_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_application_field_defs (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    name VARCHAR(128) NOT NULL,
                    required TINYINT(1) NOT NULL DEFAULT 0,
                    field_type VARCHAR(16) NOT NULL,
                    options_json JSON NULL,
                    description VARCHAR(512) NOT NULL DEFAULT '',
                    sort_order INT NOT NULL DEFAULT 0,
                    enabled TINYINT(1) NOT NULL DEFAULT 1,
                    options_feishu_source TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_field_sort (sort_order),
                    KEY idx_field_enabled (enabled)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS project_applications (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    record_id VARCHAR(64) NOT NULL,
                    initiator_id BIGINT NOT NULL,
                    project_key VARCHAR(128) NOT NULL,
                    project_name VARCHAR(256) NOT NULL,
                    payload_json JSON NOT NULL,
                    custom_fields_json JSON NULL,
                    approval_status VARCHAR(32) NOT NULL DEFAULT '待审批',
                    process_message TEXT,
                    workflow_instance_id BIGINT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY uk_project_app_record (record_id),
                    KEY idx_project_app_initiator (initiator_id),
                    KEY idx_project_app_status (approval_status)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_flow_templates (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    name VARCHAR(128) NOT NULL,
                    workflow_type VARCHAR(128) NOT NULL,
                    enabled TINYINT(1) NOT NULL DEFAULT 1,
                    is_default TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_tpl_workflow_type (workflow_type)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_flow_levels (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    template_id BIGINT NOT NULL,
                    level INT NOT NULL,
                    name VARCHAR(64) NOT NULL,
                    approval_mode VARCHAR(16) NOT NULL DEFAULT 'any',
                    PRIMARY KEY (id),
                    KEY idx_level_template (template_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_flow_level_assignees (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    level_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_assignee_level (level_id),
                    KEY idx_assignee_user (user_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_flow_level_ccs (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    level_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_cc_level (level_id),
                    KEY idx_cc_user (user_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_instances (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    serial_no VARCHAR(32) NOT NULL,
                    title VARCHAR(256) NOT NULL,
                    workflow_type VARCHAR(128) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    initiator_id BIGINT NOT NULL,
                    initiator_name VARCHAR(120) NOT NULL DEFAULT '',
                    summary VARCHAR(512) NOT NULL DEFAULT '',
                    form_data JSON NULL,
                    current_node VARCHAR(64) NOT NULL DEFAULT '',
                    ref_record_id VARCHAR(64) NOT NULL DEFAULT '',
                    template_id BIGINT NULL,
                    template_snapshot JSON NULL,
                    current_level INT NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE KEY uk_workflow_serial (serial_no),
                    KEY idx_workflow_ref (ref_record_id),
                    KEY idx_workflow_status (status)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_tasks (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    instance_id BIGINT NOT NULL,
                    assignee_id BIGINT NOT NULL,
                    assignee_name VARCHAR(120) NOT NULL DEFAULT '',
                    status VARCHAR(20) NOT NULL,
                    node_name VARCHAR(64) NOT NULL DEFAULT '',
                    level INT NOT NULL DEFAULT 1,
                    comment TEXT,
                    processed_at DATETIME NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_task_instance (instance_id),
                    KEY idx_task_assignee (assignee_id),
                    KEY idx_task_status (status)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_records (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    instance_id BIGINT NOT NULL,
                    node_name VARCHAR(64) NOT NULL DEFAULT '',
                    user_id BIGINT NULL,
                    user_name VARCHAR(120) NOT NULL DEFAULT '',
                    action VARCHAR(32) NOT NULL,
                    action_label VARCHAR(64) NOT NULL DEFAULT '',
                    comment TEXT,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_record_instance (instance_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_ccs (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    instance_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    read_at DATETIME NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_cc_instance (instance_id),
                    KEY idx_cc_user (user_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_feishu_cards (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    instance_id BIGINT NOT NULL,
                    task_id BIGINT NOT NULL DEFAULT 0,
                    user_id BIGINT NOT NULL,
                    open_message_id VARCHAR(128) NOT NULL,
                    open_id VARCHAR(128) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_wfc_instance (instance_id),
                    KEY idx_wfc_user (user_id),
                    KEY idx_wfc_message (open_message_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            for column_sql in (
                "ALTER TABLE project_applications ADD COLUMN execution_log MEDIUMTEXT NULL AFTER process_message",
                "ALTER TABLE project_applications ADD COLUMN project_url VARCHAR(512) NOT NULL DEFAULT '' AFTER execution_log",
                "ALTER TABLE project_applications ADD COLUMN execution_context_json JSON NULL AFTER project_url",
            ):
                try:
                    cur.execute(column_sql)
                except pymysql.err.OperationalError as exc:
                    if exc.args[0] != 1060:
                        raise
        conn.commit()
    finally:
        conn.close()
    _bootstrap_root_user()


_LEGACY_ROOT_PASSWORD = "Root@123456"


def _password_matches(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    import bcrypt

    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _bootstrap_root_user() -> None:
    from utils.config import auth_config

    cfg = auth_config()
    cfg_name = cfg["root_initial_name"]
    cfg_password = cfg["root_initial_password"]
    conn = _connect(database=mysql_config()["database"])
    try:
        import bcrypt

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, password_hash
                FROM platform_users
                WHERE role = %s AND auth_source = 'local' AND deleted_at IS NULL
                ORDER BY id ASC
                LIMIT 1
                """,
                ("root",),
            )
            row = cur.fetchone()
            if row:
                password_hash = str(row.get("password_hash") or "")
                legacy_password = _password_matches(_LEGACY_ROOT_PASSWORD, password_hash)
                cfg_password_ok = _password_matches(cfg_password, password_hash)
                should_sync = (
                    row["name"] == "root"
                    or row["name"] != cfg_name
                    or (not cfg_password_ok and legacy_password)
                )
                if should_sync:
                    now = _now()
                    password_hash = bcrypt.hashpw(cfg_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                    cur.execute(
                        """
                        UPDATE platform_users
                        SET name = %s, display_name = %s, phone = %s, email = %s,
                            password_hash = %s, updated_at = %s
                        WHERE id = %s
                        """,
                        (
                            cfg_name,
                            cfg_name,
                            cfg["root_initial_phone"] or None,
                            cfg["root_initial_email"],
                            password_hash,
                            now,
                            row["id"],
                        ),
                    )
                conn.commit()
                return

            now = _now()
            password_hash = bcrypt.hashpw(cfg_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cur.execute(
                """
                INSERT INTO platform_users
                (name, display_name, phone, email, password_hash, auth_source, role, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 'local', 'root', 'active', %s, %s)
                """,
                (
                    cfg_name,
                    cfg_name,
                    cfg["root_initial_phone"] or None,
                    cfg["root_initial_email"],
                    password_hash,
                    now,
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()

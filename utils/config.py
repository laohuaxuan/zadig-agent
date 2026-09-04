from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"

_cache: dict | None = None
_mtime: float | None = None


def load_config() -> dict:
    """读取 config.yaml；文件 mtime 变化时自动重新加载。"""
    global _cache, _mtime
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"缺少配置文件 {CONFIG_PATH}，请复制 config.example.yaml 为 config.yaml 后填写 MySQL 和服务地址"
        )
    mtime = CONFIG_PATH.stat().st_mtime
    if _cache is not None and _mtime == mtime:
        return _cache
    with CONFIG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml 格式无效，根节点必须是映射")
    reloaded = _cache is not None
    _cache = data
    _mtime = mtime
    if reloaded:
        print(f"已热加载配置：{CONFIG_PATH}")
    return _cache


def invalidate_config_cache() -> None:
    global _cache, _mtime
    _cache = None
    _mtime = None


def _int(value: object, default: int, field: str) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是整数") from exc


def server_config() -> dict:
    raw = (load_config().get("server") or {}) if CONFIG_PATH.exists() else {}
    if not isinstance(raw, dict):
        raise ValueError("config.yaml 中 server 必须是映射")
    host = str(raw.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    return {"host": host, "port": _int(raw.get("port"), 8088, "server.port")}


def mysql_config() -> dict:
    raw = load_config().get("mysql") or {}
    if not isinstance(raw, dict):
        raise ValueError("config.yaml 中 mysql 必须是映射")
    host = str(raw.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    user = str(raw.get("user") or "root").strip() or "root"
    database = str(raw.get("database") or raw.get("name") or "zadig_agent").strip()
    if not database:
        raise ValueError("请在 config.yaml 的 mysql.database 中填写数据库名")
    charset = str(raw.get("charset") or "utf8mb4").strip() or "utf8mb4"
    return {
        "host": host,
        "port": _int(raw.get("port"), 3306, "mysql.port"),
        "user": user,
        "password": str(raw.get("password") or ""),
        "database": database,
        "charset": charset,
    }


def mcp_server_config() -> dict:
    """读取可选的 MCP 服务配置；缺省为本地 stdio。"""
    raw = load_config().get("mcp") or {}
    if not isinstance(raw, dict):
        raise ValueError("config.yaml 中 mcp 必须是映射")
    transport = str(raw.get("transport") or "stdio").strip().lower()
    if transport not in {"stdio", "sse"}:
        raise ValueError("mcp.transport 必须是 stdio 或 sse")
    host = str(raw.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    token = str(raw.get("token") or "").strip()
    return {
        "transport": transport,
        "host": host,
        "port": _int(raw.get("port"), 8000, "mcp.port"),
        "token": token,
    }


def openrouter_config() -> dict:
    """返回当前可用的 Agent。默认不可用时随机切换到其他已探测可用的 Agent。"""
    from webapi.settings import resolve_agent

    item = resolve_agent()
    api_key = str(item.get("api_key") or "").strip()
    model = str(item.get("model") or "").strip()
    base_url = str(item.get("base_url") or "").strip()
    if not api_key or api_key == "YOUR_OPENROUTER_API_KEY":
        raise ValueError("请在页面「Agent 管理」中填写 API Key")
    if not model:
        raise ValueError("请在页面「Agent 管理」中填写模型名称")
    if not base_url:
        raise ValueError("请在页面「Agent 管理」中填写 base_url")
    return {
        "id": item.get("id") or "",
        "name": item.get("name") or "",
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
    }


def zadig_config() -> dict:
    from webapi.settings import load_zadig

    cfg = load_zadig()
    base_url = str(cfg.get("base_url") or "").strip().rstrip("/")
    api_token = str(cfg.get("api_token") or "").strip()
    if not base_url or base_url in {"https://your.zadig.com", "http://your.zadig.com"}:
        raise ValueError("请在页面「Zadig 管理」中填写 Zadig 访问地址")
    if not api_token or api_token == "YOUR_ZADIG_API_TOKEN":
        raise ValueError("请在页面「Zadig 管理」中填写 Zadig API Token")
    return {"base_url": base_url, "api_token": api_token}


def _section(name: str) -> dict:
    raw = load_config().get(name) or {}
    return raw if isinstance(raw, dict) else {}


def auth_config() -> dict:
    raw = _section("auth")
    secret = str(raw.get("jwt_secret") or "change-me-in-production").strip()
    expiry = str(raw.get("token_expiry") or "24h").strip() or "24h"
    return {
        "jwt_secret": secret,
        "token_expiry": expiry,
        "root_initial_name": str(raw.get("root_initial_name") or "admin").strip() or "admin",
        "root_initial_phone": str(raw.get("root_initial_phone") or "").strip(),
        "root_initial_email": str(raw.get("root_initial_email") or "admin@example.com").strip(),
        "root_initial_password": str(raw.get("root_initial_password") or "Admin@123456"),
    }


def feishu_config() -> dict:
    raw = _section("feishu")
    dept_ids = raw.get("department_ids") or raw.get("department_id")
    if isinstance(dept_ids, str):
        dept_ids = [dept_ids]
    if not isinstance(dept_ids, list):
        dept_ids = ["0"]
    return {
        "app_base_url": str(raw.get("app_base_url") or "http://127.0.0.1:5173").strip().rstrip("/"),
        "app_id": str(raw.get("app_id") or "").strip(),
        "app_secret": str(raw.get("app_secret") or "").strip(),
        "oauth_redirect_uri": str(raw.get("oauth_redirect_uri") or "").strip(),
        "department_ids": [str(item).strip() for item in dept_ids if str(item).strip()],
    }


def integration_config() -> dict:
    raw = _section("integration")
    seconds = _int(raw.get("sync_interval_seconds"), 300, "integration.sync_interval_seconds")
    if seconds < 30:
        raise ValueError("integration.sync_interval_seconds 不能小于 30")
    return {"sync_interval_seconds": seconds}

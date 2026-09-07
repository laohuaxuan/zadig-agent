"""读写 MySQL 中的 Agent / Zadig 配置。"""

from __future__ import annotations

import json
import random
import re
import time
import uuid
from typing import Any

import httpx

from utils.db import execute, query, query_one
from utils.llm_errors import format_http_llm_error, format_llm_error
from model.openrouter import chat_completion_probe_body, chat_completion_probe_headers

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
_PLACEHOLDER_KEYS = {"YOUR_OPENROUTER_API_KEY", ""}
_PLACEHOLDER_TOKENS = {"YOUR_ZADIG_API_TOKEN", ""}
_PLACEHOLDER_ZADIG = {"https://your.zadig.com", "http://your.zadig.com", ""}
_probe_cache: dict[str, tuple[float, bool, str]] = {}
_PROBE_TTL = 20.0


def _mask(secret: str) -> str:
    text = str(secret or "")
    if len(text) <= 8:
        return "********" if text else ""
    return f"{text[:4]}****{text[-4:]}"


def _agent_id(name: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()) or "agent"
    base = base.strip("-").lower() or "agent"
    if not base[0].isalpha():
        base = f"a-{base}"
    candidate = base[:48]
    if candidate not in existing:
        return candidate
    return f"{candidate}-{uuid.uuid4().hex[:6]}"


def _parse_models_json(raw: Any, fallback_model: str = "") -> dict[str, Any]:
    data: dict[str, Any] = {}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = {}
    elif isinstance(raw, dict):
        data = raw
    primary = str(data.get("primary") or fallback_model or "").strip()
    backups_raw = data.get("backups") if isinstance(data.get("backups"), list) else []
    backups: list[str] = []
    seen = {primary} if primary else set()
    for item in backups_raw:
        model = str(item or "").strip()
        if not model or model in seen:
            continue
        seen.add(model)
        backups.append(model)
    return {"primary": primary, "backups": backups}


def _row_agent(row: dict[str, Any]) -> dict[str, Any]:
    models = _parse_models_json(row.get("models_json"), str(row.get("model") or ""))
    primary = models["primary"]
    return {
        "id": row["id"],
        "name": row["name"],
        "api_key": row["api_key"],
        "model": primary,
        "models": models,
        "base_url": row["base_url"],
        "is_default": bool(row.get("is_default")),
    }


def _model_probe_key(base_url: str, api_key: str, model: str) -> str:
    return f"{base_url}|{model}|{api_key}"


def _extract_model_ids(data: Any) -> set[str]:
    ids: set[str] = set()
    if not isinstance(data, dict):
        return ids
    items = data.get("data")
    if not isinstance(items, list):
        items = data.get("models") if isinstance(data.get("models"), list) else []
    for item in items:
        if isinstance(item, dict):
            mid = str(item.get("id") or item.get("name") or "").strip()
            if mid:
                ids.add(mid)
        elif isinstance(item, str) and item.strip():
            ids.add(item.strip())
    return ids


def _model_matches(model: str, known_ids: set[str]) -> bool:
    if not known_ids:
        return True
    if model in known_ids:
        return True
    return any(model == mid or mid.endswith(f"/{model}") or mid.endswith(model) for mid in known_ids)


def probe_model(base_url: str, api_key: str, model: str, *, fresh: bool = False) -> tuple[bool, str]:
    text = str(model or "").strip()
    url = str(base_url or "").strip().rstrip("/")
    key = str(api_key or "").strip()
    if not text:
        return False, "未配置 model"
    if not key or key in _PLACEHOLDER_KEYS:
        return False, "未配置 API Key"
    if not url:
        return False, "未配置 base_url"
    cache_key = _model_probe_key(url, key, text)
    now = time.monotonic()
    if not fresh:
        cached = _probe_cache.get(cache_key)
        if cached and now - cached[0] < _PROBE_TTL:
            return cached[1], cached[2]
    try:
        session_id, payload = chat_completion_probe_body(text)
        resp = httpx.post(
            f"{url}/chat/completions",
            headers=chat_completion_probe_headers(key, session_id=session_id),
            json=payload,
            timeout=15.0,
        )
        if resp.status_code >= 400:
            result = (False, format_http_llm_error(resp.status_code, resp.text))
        else:
            result = (True, "")
    except Exception as exc:
        result = (False, format_llm_error(str(exc)))
    _probe_cache[cache_key] = (now, *result)
    return result


def probe_agent(item: dict[str, Any]) -> tuple[bool, str]:
    models = item.get("models") or _parse_models_json(None, item.get("model") or "")
    primary = str(models.get("primary") or item.get("model") or "").strip()
    backups = models.get("backups") or []
    base_url = str(item.get("base_url") or "").strip().rstrip("/")
    api_key = str(item.get("api_key") or "").strip()
    if primary:
        ok, error = probe_model(base_url, api_key, primary)
        if ok:
            return True, ""
    for backup in backups:
        ok, error = probe_model(base_url, api_key, str(backup))
        if ok:
            return True, f"主模型 {primary or '—'} 不可用，备用 {backup} 可用"
    return False, error if primary else "未配置 model"


def build_probe_item(payload: dict[str, Any], *, agent_id: str = "") -> dict[str, Any]:
    api_key = str(payload.get("api_key") or "").strip()
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    current: dict[str, Any] | None = None
    if agent_id:
        row = query_one("SELECT * FROM agents WHERE id = %s", (agent_id,))
        if row is None:
            raise KeyError(f"Agent {agent_id} 不存在")
        current = _row_agent(row)
    if not api_key and current:
        api_key = str(current.get("api_key") or "").strip()
    if not base_url and current:
        base_url = str(current.get("base_url") or "").strip().rstrip("/")
    if _should_update_models(payload) or not current:
        models = _normalize_agent_models(payload, current)
    elif current:
        models = current.get("models") or _parse_models_json(None, str(current.get("model") or ""))
    else:
        models = _normalize_agent_models(payload)
    if not api_key:
        raise ValueError("请填写 API Key")
    if not base_url:
        raise ValueError("请填写 base_url")
    primary = str(models.get("primary") or "").strip()
    if not primary:
        raise ValueError("请填写主模型")
    return {
        "id": agent_id or "probe",
        "name": str(payload.get("name") or (current or {}).get("name") or "probe"),
        "api_key": api_key,
        "base_url": base_url,
        "model": primary,
        "models": models,
    }


def test_agent_config(payload: dict[str, Any], *, agent_id: str = "") -> dict[str, Any]:
    item = build_probe_item(payload, agent_id=agent_id)
    models = item.get("models") or {}
    primary = str(models.get("primary") or item.get("model") or "").strip()
    backups = [str(model).strip() for model in models.get("backups") or [] if str(model).strip()]
    base_url = str(item.get("base_url") or "").strip().rstrip("/")
    api_key = str(item.get("api_key") or "").strip()
    last_error = "不可用"
    if primary:
        ok, error = probe_model(base_url, api_key, primary, fresh=True)
        if ok:
            return {"available": True, "message": f"主模型 {primary} 可用", "active_model": primary}
        last_error = error
    for backup in backups:
        ok, error = probe_model(base_url, api_key, backup, fresh=True)
        if ok:
            return {
                "available": True,
                "message": f"主模型 {primary or '—'} 不可用，备用 {backup} 可用",
                "active_model": backup,
            }
        last_error = error
    return {"available": False, "message": last_error, "active_model": ""}


def resolve_agent_models(item: dict[str, Any]) -> dict[str, Any]:
    models = item.get("models") or _parse_models_json(None, item.get("model") or "")
    primary = str(models.get("primary") or item.get("model") or "").strip()
    backups = [str(model).strip() for model in models.get("backups") or [] if str(model).strip()]
    ordered: list[str] = []
    seen: set[str] = set()
    for model in [primary, *backups]:
        if not model or model in seen:
            continue
        seen.add(model)
        ordered.append(model)
    if not ordered:
        raise ValueError(f"Agent {item.get('name') or item.get('id')} 未配置模型")
    base_url = str(item.get("base_url") or "").strip().rstrip("/")
    api_key = str(item.get("api_key") or "").strip()
    last_error = "不可用"
    for model in ordered:
        ok, error = probe_model(base_url, api_key, model)
        if ok:
            resolved = dict(item)
            resolved["model"] = model
            resolved["active_model"] = model
            resolved["is_primary_model"] = model == primary
            if model != primary:
                print(
                    f"Agent {item.get('name') or item.get('id')} 主模型 {primary} 不可用，"
                    f"已切换到备用模型 {model}"
                )
            return resolved
        last_error = error
    raise ValueError(f"Agent {item.get('name') or item.get('id')} 所有模型不可用：{last_error}")


def resolve_agent() -> dict[str, Any]:
    default_id, items = load_agents()
    if not items:
        raise ValueError("尚未配置 Agent，请在页面「Agent 管理」中添加")
    default = next((item for item in items if item["id"] == default_id), items[0])
    backups = [item for item in items if item["id"] != default["id"]]
    random.shuffle(backups)
    last_error = "不可用"
    for item in [default, *backups]:
        try:
            resolved = resolve_agent_models(item)
            if item["id"] != default["id"]:
                print(f"默认 Agent 不可用，已切换到 {item['name']} ({item['id']})")
            return resolved
        except ValueError as exc:
            last_error = str(exc)
    raise ValueError(f"没有可用的 Agent：{last_error}")


def public_agent(item: dict[str, Any], default_id: str, available: bool, error: str = "") -> dict[str, Any]:
    models = item.get("models") or _parse_models_json(None, item.get("model") or "")
    return {
        "id": item["id"],
        "name": item["name"],
        "model": models.get("primary") or item.get("model") or "",
        "primary_model": models.get("primary") or item.get("model") or "",
        "backup_models": list(models.get("backups") or []),
        "models": models,
        "base_url": item["base_url"],
        "api_key_masked": _mask(item["api_key"]),
        "is_default": item["id"] == default_id,
        "available": available,
        "error": error,
    }


def _normalize_agent_models(payload: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, Any]:
    current_models = (current or {}).get("models") or {"primary": "", "backups": []}
    legacy_model = str(payload.get("model") or "").strip()
    primary = str(
        payload.get("primary_model")
        or legacy_model
        or current_models.get("primary")
        or (current or {}).get("model")
        or ""
    ).strip()
    if not primary:
        raise ValueError("主模型不能为空")
    backups_raw = payload.get("backup_models")
    if backups_raw is None:
        backups = list(current_models.get("backups") or [])
    elif isinstance(backups_raw, list):
        backups = [str(item or "").strip() for item in backups_raw if str(item or "").strip()]
    else:
        backups = [part.strip() for part in str(backups_raw or "").split(",") if part.strip()]
    seen = {primary}
    normalized_backups: list[str] = []
    for model in backups:
        if model in seen:
            continue
        seen.add(model)
        normalized_backups.append(model)
    return {"primary": primary, "backups": normalized_backups}


def _should_update_models(payload: dict[str, Any]) -> bool:
    if "primary_model" in payload:
        return True
    if "backup_models" in payload:
        return True
    return bool(str(payload.get("model") or "").strip())


def load_agents() -> tuple[str, list[dict[str, Any]]]:
    items = [_row_agent(row) for row in query("SELECT * FROM agents ORDER BY name")]
    default = next((item for item in items if item["is_default"]), items[0] if items else None)
    return (default["id"] if default else ""), items


def _set_default(agent_id: str) -> None:
    execute("UPDATE agents SET is_default = 0 WHERE is_default = 1")
    execute("UPDATE agents SET is_default = 1 WHERE id = %s", (agent_id,))


def create_agent(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or payload.get("id") or "agent").strip() or "agent"
    api_key = str(payload.get("api_key") or "").strip()
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    models = _normalize_agent_models(payload)
    if not api_key:
        raise ValueError("api_key 不能为空")
    if not base_url:
        raise ValueError("base_url 不能为空")
    default_id, items = load_agents()
    aid = _agent_id(str(payload.get("id") or name), {item["id"] for item in items})
    if not _NAME_RE.match(aid):
        raise ValueError("id 需以字母开头，只能包含字母、数字、下划线和中划线")
    make_default = bool(payload.get("is_default")) or not default_id
    models_json = json.dumps(models, ensure_ascii=False)
    execute(
        """
        INSERT INTO agents (id, name, api_key, model, models_json, base_url, is_default, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        """,
        (aid, name, api_key, models["primary"], models_json, base_url, 1 if make_default else 0),
    )
    if make_default:
        _set_default(aid)
    row = query_one("SELECT * FROM agents WHERE id = %s", (aid,))
    return _row_agent(row or {"id": aid, "name": name, "api_key": api_key, "model": models["primary"], "models_json": models, "base_url": base_url, "is_default": make_default})


def update_agent(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current_row = query_one("SELECT * FROM agents WHERE id = %s", (agent_id,))
    if current_row is None:
        raise KeyError(f"Agent {agent_id} 不存在")
    current = _row_agent(current_row)
    api_key = str(payload.get("api_key") or "").strip()
    if api_key:
        current["api_key"] = api_key
    if payload.get("name") is not None:
        name = str(payload.get("name") or "").strip()
        if name:
            current["name"] = name
    if payload.get("base_url") is not None:
        base_url = str(payload.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url 不能为空")
        current["base_url"] = base_url
    if _should_update_models(payload):
        current["models"] = _normalize_agent_models(payload, current)
        current["model"] = current["models"]["primary"]
    execute(
        """
        UPDATE agents
        SET name = %s, api_key = %s, model = %s, models_json = %s, base_url = %s, updated_at = NOW()
        WHERE id = %s
        """,
        (
            current["name"],
            current["api_key"],
            current["model"],
            json.dumps(current["models"], ensure_ascii=False),
            current["base_url"],
            agent_id,
        ),
    )
    if payload.get("is_default"):
        _set_default(agent_id)
        current["is_default"] = True
    _probe_cache.clear()
    return current


def delete_agent(agent_id: str) -> None:
    current = query_one("SELECT id, is_default FROM agents WHERE id = %s", (agent_id,))
    if current is None:
        raise KeyError(f"Agent {agent_id} 不存在")
    execute("DELETE FROM agents WHERE id = %s", (agent_id,))
    if current.get("is_default"):
        nxt = query_one("SELECT id FROM agents ORDER BY name LIMIT 1")
        if nxt:
            _set_default(nxt["id"])
    _probe_cache.clear()


def set_default_agent(agent_id: str) -> None:
    if query_one("SELECT id FROM agents WHERE id = %s", (agent_id,)) is None:
        raise KeyError(f"Agent {agent_id} 不存在")
    _set_default(agent_id)


def _zadig_id(name: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()) or "zadig"
    base = base.strip("-").lower() or "zadig"
    if not base[0].isalpha():
        base = f"z-{base}"
    candidate = base[:48]
    if candidate not in existing:
        return candidate
    return f"{candidate}-{uuid.uuid4().hex[:6]}"


def _row_zadig(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "remark": str(row.get("remark") or ""),
        "base_url": str(row.get("base_url") or "").strip().rstrip("/"),
        "api_token": str(row.get("api_token") or "").strip(),
        "is_active": bool(row.get("is_active")),
    }


def load_zadig_instances() -> tuple[str, list[dict[str, Any]]]:
    items = [_row_zadig(row) for row in query("SELECT * FROM zadig_instances ORDER BY name")]
    active = next((item for item in items if item["is_active"]), items[0] if items else None)
    if not items:
        legacy = _load_zadig_legacy_settings()
        if legacy.get("base_url") or legacy.get("api_token"):
            return "", [legacy]
    return (active["id"] if active else ""), items


def _load_zadig_legacy_settings() -> dict[str, Any]:
    row = query_one("SELECT value_json FROM settings WHERE name = %s", ("zadig",))
    raw: Any = {}
    if row:
        raw = row["value_json"]
        if isinstance(raw, str):
            raw = json.loads(raw)
    if not isinstance(raw, dict):
        raw = {}
    return {
        "id": "",
        "name": "默认 Zadig",
        "remark": "",
        "base_url": str(raw.get("base_url") or "").strip().rstrip("/"),
        "api_token": str(raw.get("api_token") or "").strip(),
        "is_active": True,
    }


def load_zadig() -> dict[str, str]:
    active_id, items = load_zadig_instances()
    if not items:
        legacy = _load_zadig_legacy_settings()
        return {"base_url": legacy["base_url"], "api_token": legacy["api_token"]}
    current = next((item for item in items if item["id"] == active_id), items[0])
    return {"base_url": current["base_url"], "api_token": current["api_token"]}


def get_zadig_instance(instance_id: str) -> dict[str, Any]:
    row = query_one("SELECT * FROM zadig_instances WHERE id = %s", (instance_id,))
    if row is None:
        raise KeyError(f"Zadig {instance_id} 不存在")
    return _row_zadig(row)


def public_zadig(item: dict[str, Any], active_id: str, available: bool, error: str = "", body: Any = None) -> dict[str, Any]:
    token = item.get("api_token") or ""
    info: dict[str, Any] = {
        "id": item.get("id") or "",
        "name": item.get("name") or "",
        "remark": item.get("remark") or "",
        "base_url": item.get("base_url") or "",
        "api_token_masked": _mask(token),
        "is_active": bool(item.get("is_active")) or item.get("id") == active_id,
        "available": available,
        "error": error,
    }
    if isinstance(body, dict):
        info["project_total"] = body.get("total")
    return info


def create_zadig_instance(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "Zadig").strip() or "Zadig"
    remark = str(payload.get("remark") or "").strip()
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    api_token = str(payload.get("api_token") or "").strip()
    if not base_url:
        raise ValueError("base_url 不能为空")
    if not api_token:
        raise ValueError("api_token 不能为空")
    active_id, items = load_zadig_instances()
    zid = _zadig_id(str(payload.get("id") or name), {item["id"] for item in items if item.get("id")})
    if not _NAME_RE.match(zid):
        raise ValueError("id 需以字母开头，只能包含字母、数字、下划线和中划线")
    make_active = bool(payload.get("is_active")) or not active_id
    execute(
        """
        INSERT INTO zadig_instances
        (id, name, remark, base_url, api_token, is_active, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
        """,
        (zid, name, remark, base_url, api_token, 1 if make_active else 0),
    )
    if make_active:
        set_active_zadig(zid)
    return get_zadig_instance(zid)


def update_zadig_instance(instance_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_zadig_instance(instance_id)
    if payload.get("name") is not None:
        name = str(payload.get("name") or "").strip()
        if name:
            current["name"] = name
    if payload.get("remark") is not None:
        current["remark"] = str(payload.get("remark") or "").strip()
    if payload.get("base_url") is not None:
        base_url = str(payload.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url 不能为空")
        current["base_url"] = base_url
    api_token = str(payload.get("api_token") or "").strip()
    if api_token:
        current["api_token"] = api_token
    execute(
        """
        UPDATE zadig_instances
        SET name = %s, remark = %s, base_url = %s, api_token = %s, updated_at = NOW()
        WHERE id = %s
        """,
        (current["name"], current["remark"], current["base_url"], current["api_token"], instance_id),
    )
    if payload.get("is_active"):
        set_active_zadig(instance_id)
    return get_zadig_instance(instance_id)


def delete_zadig_instance(instance_id: str) -> None:
    current = query_one("SELECT id, is_active FROM zadig_instances WHERE id = %s", (instance_id,))
    if current is None:
        raise KeyError(f"Zadig {instance_id} 不存在")
    execute("DELETE FROM zadig_instances WHERE id = %s", (instance_id,))
    if current.get("is_active"):
        nxt = query_one("SELECT id FROM zadig_instances ORDER BY name LIMIT 1")
        if nxt:
            set_active_zadig(nxt["id"])


def set_active_zadig(instance_id: str) -> None:
    if query_one("SELECT id FROM zadig_instances WHERE id = %s", (instance_id,)) is None:
        raise KeyError(f"Zadig {instance_id} 不存在")
    execute("UPDATE zadig_instances SET is_active = 0 WHERE is_active = 1")
    execute("UPDATE zadig_instances SET is_active = 1 WHERE id = %s", (instance_id,))


def save_zadig(payload: dict[str, Any]) -> dict[str, str]:
    active_id, items = load_zadig_instances()
    if active_id:
        updated = update_zadig_instance(
            active_id,
            {
                "name": payload.get("name"),
                "remark": payload.get("remark"),
                "base_url": payload.get("base_url"),
                "api_token": payload.get("api_token"),
            },
        )
        return {"base_url": updated["base_url"], "api_token": updated["api_token"]}
    created = create_zadig_instance(payload)
    return {"base_url": created["base_url"], "api_token": created["api_token"]}


def probe_zadig(cfg: dict[str, str] | None = None) -> tuple[bool, str, Any]:
    info = cfg or load_zadig()
    base_url = info.get("base_url") or ""
    token = info.get("api_token") or ""
    if not base_url or base_url in _PLACEHOLDER_ZADIG:
        return False, "未配置 Zadig 地址", None
    if not token or token in _PLACEHOLDER_TOKENS:
        return False, "未配置 API Token", None
    try:
        resp = httpx.get(
            f"{base_url}/openapi/projects/project",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            params={"pageSize": 1, "pageNum": 1},
            timeout=10.0,
        )
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}", None
        body = resp.json()
        return True, "", body
    except Exception as exc:
        return False, str(exc)[:160], None

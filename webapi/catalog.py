"""Skills / MCP 技能：MySQL 存储；启动时将仓库文件与内置工具一次性同步入库。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.db import execute, query, query_one

_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_DIR = _ROOT / "skills"
_MCP_DIR = _ROOT / "mcp_skills"
_MCP_SRC = _ROOT / "zadig_mcp"
_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
_TOOL_RE = re.compile(
    r'@mcp\.tool\(\s*name="([^"]+)"\s*,\s*description="([^"]*)"',
    re.MULTILINE,
)


def validate_name(name: str) -> str:
    text = str(name or "").strip()
    if not _NAME_RE.match(text):
        raise ValueError("名称需以字母开头，只能包含字母、数字、下划线和中划线")
    return text


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 必须是 JSON 对象")
    return data


def _skill_from_file(path: Path, kind: str) -> dict[str, Any]:
    data = _read_json(path)
    name = str(data.get("name") or path.stem).strip() or path.stem
    if name.startswith("{") and name.endswith("}"):
        name = path.stem
    display_name = str(data.get("display_name") or name).strip() or name
    if display_name.startswith("{") and display_name.endswith("}"):
        display_name = name
    return {
        "name": name,
        "display_name": display_name,
        "description": str(data.get("description") or data.get("hint") or "").strip(),
        "kind": kind,
        "source": "file",
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "file": path.name,
        "transport": data.get("transport") or "",
        "command": data.get("command") or "",
        "args": data.get("args") or [],
        "url": data.get("url") or "",
        "content": data.get("content") or "",
    }


def _parse_args(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _skill_from_row(row: dict[str, Any]) -> dict[str, Any]:
    updated = row.get("updated_at")
    if hasattr(updated, "isoformat"):
        updated = updated.isoformat(timespec="seconds")
    transport = row.get("transport") or ""
    command = row.get("command") or ""
    source = "builtin" if transport == "builtin" else "mysql"
    item: dict[str, Any] = {
        "name": row["name"],
        "display_name": row["display_name"],
        "description": row.get("description") or "",
        "kind": row["kind"],
        "source": source,
        "updated_at": str(updated or ""),
        "maintainer_id": int(row["maintainer_id"]) if row.get("maintainer_id") is not None else None,
        "transport": transport,
        "command": command,
        "args": _parse_args(row.get("args_json")),
        "url": row.get("url") or "",
        "content": row.get("content") or "",
    }
    if transport == "builtin":
        item["module"] = command
    return item


def _db_skills(kind: str) -> list[dict[str, Any]]:
    return [_skill_from_row(row) for row in query("SELECT * FROM skills WHERE kind = %s ORDER BY name", (kind,))]


def list_file_skills() -> list[dict[str, Any]]:
    if not _SKILLS_DIR.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(_SKILLS_DIR.glob("*.json")):
        item = _skill_from_file(path, "skill")
        if not str(item.get("content") or "").strip():
            continue
        items.append(item)
    items.sort(key=lambda item: item["name"])
    return items


def list_skills() -> list[dict[str, Any]]:
    sync_file_skills_to_db()
    return _db_skills("skill")


def sync_file_skills_to_db() -> None:
    """将 skills/ 目录下尚未入库的 Skill 导入 MySQL。"""
    for item in list_file_skills():
        name = item["name"]
        if query_one("SELECT name FROM skills WHERE name = %s AND kind = 'skill'", (name,)):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        execute(
            """
            INSERT INTO skills
            (name, kind, display_name, description, content, transport, command, args_json, url, created_at, updated_at)
            VALUES (%s, 'skill', %s, %s, %s, '', '', JSON_ARRAY(), '', NOW(), NOW())
            """,
            (name, item["display_name"], item.get("description") or "", content),
        )


def list_file_mcp_skills() -> list[dict[str, Any]]:
    if not _MCP_DIR.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(_MCP_DIR.glob("*.json")):
        items.append(_skill_from_file(path, "mcp"))
    items.sort(key=lambda item: item["name"])
    return items


def sync_file_mcp_to_db() -> None:
    """将 mcp_skills/ 目录下尚未入库的 MCP 配置导入 MySQL。"""
    for item in list_file_mcp_skills():
        name = item["name"]
        if query_one("SELECT name FROM skills WHERE name = %s AND kind = 'mcp'", (name,)):
            continue
        transport = str(item.get("transport") or "stdio").strip().lower()
        if transport not in {"stdio", "sse"}:
            transport = "stdio"
        execute(
            """
            INSERT INTO skills
            (name, kind, display_name, description, content, transport, command, args_json, url, created_at, updated_at)
            VALUES (%s, 'mcp', %s, %s, '', %s, %s, %s, %s, NOW(), NOW())
            """,
            (
                name,
                item["display_name"],
                item.get("description") or "",
                transport,
                item.get("command") or "",
                json.dumps(item.get("args") or [], ensure_ascii=False),
                item.get("url") or "",
            ),
        )


def sync_builtin_mcp_tools_to_db() -> None:
    """将 zadig_mcp 内置工具注册信息同步到 MySQL。"""
    for item in list_builtin_mcp_tools():
        name = item["name"]
        if query_one("SELECT name FROM skills WHERE name = %s AND kind = 'mcp'", (name,)):
            continue
        execute(
            """
            INSERT INTO skills
            (name, kind, display_name, description, content, transport, command, args_json, url, created_at, updated_at)
            VALUES (%s, 'mcp', %s, %s, '', 'builtin', %s, JSON_ARRAY(), '', NOW(), NOW())
            """,
            (name, item["display_name"], item.get("description") or "", item.get("module") or ""),
        )


def sync_mcp_to_db() -> None:
    sync_builtin_mcp_tools_to_db()
    sync_file_mcp_to_db()


def list_builtin_mcp_tools() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(_MCP_SRC.glob("*_tools.py")):
        text = path.read_text(encoding="utf-8")
        for name, description in _TOOL_RE.findall(text):
            items.append(
                {
                    "name": name,
                    "display_name": name,
                    "description": description,
                    "kind": "mcp",
                    "source": "builtin",
                    "module": path.name,
                    "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                }
            )
    items.sort(key=lambda item: item["name"])
    return items


def list_mcp_skills() -> list[dict[str, Any]]:
    sync_mcp_to_db()
    return _db_skills("mcp")


def _name_taken(name: str, kind: str) -> bool:
    return bool(query_one("SELECT name FROM skills WHERE name = %s AND kind = %s", (name, kind)))


def create_skill(payload: dict[str, Any], *, maintainer_id: int | None = None) -> dict[str, Any]:
    name = validate_name(payload.get("name"))
    if _name_taken(name, "skill"):
        raise FileExistsError(f"技能 {name} 已存在")
    display_name = str(payload.get("display_name") or name).strip() or name
    description = str(payload.get("description") or "").strip()
    content = str(payload.get("content") or "").strip()
    execute(
        """
        INSERT INTO skills
        (name, kind, display_name, description, content, transport, command, args_json, url, maintainer_id, created_at, updated_at)
        VALUES (%s, 'skill', %s, %s, %s, '', '', JSON_ARRAY(), '', %s, NOW(), NOW())
        """,
        (name, display_name, description, content, maintainer_id),
    )
    row = query_one("SELECT * FROM skills WHERE name = %s AND kind = 'skill'", (name,))
    return _skill_from_row(row or {"name": name, "kind": "skill", "display_name": display_name, "description": description, "content": content})


def create_mcp_skill(payload: dict[str, Any], *, maintainer_id: int | None = None) -> dict[str, Any]:
    name = validate_name(payload.get("name"))
    if _name_taken(name, "mcp"):
        raise FileExistsError(f"MCP 技能 {name} 已存在")
    transport = str(payload.get("transport") or "stdio").strip().lower()
    if transport not in {"stdio", "sse"}:
        raise ValueError("transport 必须是 stdio 或 sse")
    command = str(payload.get("command") or "").strip()
    url = str(payload.get("url") or "").strip()
    args = payload.get("args") if isinstance(payload.get("args"), list) else []
    if transport == "stdio" and not command:
        raise ValueError("stdio 模式必须填写 command")
    if transport == "sse" and not url:
        raise ValueError("sse 模式必须填写 url")
    display_name = str(payload.get("display_name") or name).strip() or name
    description = str(payload.get("description") or "").strip()
    execute(
        """
        INSERT INTO skills
        (name, kind, display_name, description, content, transport, command, args_json, url, maintainer_id, created_at, updated_at)
        VALUES (%s, 'mcp', %s, %s, '', %s, %s, %s, %s, %s, NOW(), NOW())
        """,
        (name, display_name, description, transport, command, json.dumps(args, ensure_ascii=False), url, maintainer_id),
    )
    row = query_one("SELECT * FROM skills WHERE name = %s AND kind = 'mcp'", (name,))
    return _skill_from_row(
        row
        or {
            "name": name,
            "kind": "mcp",
            "display_name": display_name,
            "description": description,
            "transport": transport,
            "command": command,
            "args_json": args,
            "url": url,
        }
    )


def get_skill(name: str) -> dict[str, Any]:
    text = str(name or "").strip()
    if not text:
        raise ValueError("技能标识不能为空")
    row = query_one("SELECT * FROM skills WHERE name = %s AND kind = 'skill'", (text,))
    if not row:
        sync_file_skills_to_db()
        row = query_one("SELECT * FROM skills WHERE name = %s AND kind = 'skill'", (text,))
    if not row:
        raise LookupError(f"未找到 Skill {text}")
    return _skill_from_row(row)


def get_mcp_skill(name: str) -> dict[str, Any]:
    text = str(name or "").strip()
    if not text:
        raise ValueError("技能标识不能为空")
    row = query_one("SELECT * FROM skills WHERE name = %s AND kind = 'mcp'", (text,))
    if not row:
        sync_mcp_to_db()
        row = query_one("SELECT * FROM skills WHERE name = %s AND kind = 'mcp'", (text,))
    if not row:
        raise LookupError(f"未找到 MCP 技能 {text}")
    return _skill_from_row(row)


def update_skill(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    text = str(name or "").strip()
    display_name = str(payload.get("display_name") or text).strip() or text
    description = str(payload.get("description") or "").strip()
    content = str(payload.get("content") or "").strip()
    row = query_one("SELECT * FROM skills WHERE name = %s AND kind = 'skill'", (text,))
    if row:
        execute(
            """
            UPDATE skills
            SET display_name = %s, description = %s, content = %s, updated_at = NOW()
            WHERE name = %s AND kind = 'skill'
            """,
            (display_name, description, content, text),
        )
    else:
        sync_file_skills_to_db()
        row = query_one("SELECT * FROM skills WHERE name = %s AND kind = 'skill'", (text,))
        if row:
            execute(
                """
                UPDATE skills
                SET display_name = %s, description = %s, content = %s, updated_at = NOW()
                WHERE name = %s AND kind = 'skill'
                """,
                (display_name, description, content, text),
            )
        else:
            execute(
                """
                INSERT INTO skills
                (name, kind, display_name, description, content, transport, command, args_json, url, created_at, updated_at)
                VALUES (%s, 'skill', %s, %s, %s, '', '', JSON_ARRAY(), '', NOW(), NOW())
                """,
                (text, display_name, description, content),
            )
    return get_skill(text)


def update_mcp_skill(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    text = str(name or "").strip()
    row = query_one("SELECT * FROM skills WHERE name = %s AND kind = 'mcp'", (text,))
    if not row:
        raise LookupError(f"MCP 技能 {text} 不存在或不可编辑")
    if str(row.get("transport") or "") == "builtin":
        raise LookupError(f"MCP 技能 {text} 为内置工具，不可编辑")
    transport = str(payload.get("transport") or "stdio").strip().lower()
    if transport not in {"stdio", "sse"}:
        raise ValueError("transport 必须是 stdio 或 sse")
    command = str(payload.get("command") or "").strip()
    url = str(payload.get("url") or "").strip()
    args = payload.get("args") if isinstance(payload.get("args"), list) else []
    if transport == "stdio" and not command:
        raise ValueError("stdio 模式必须填写 command")
    if transport == "sse" and not url:
        raise ValueError("sse 模式必须填写 url")
    display_name = str(payload.get("display_name") or text).strip() or text
    description = str(payload.get("description") or "").strip()
    execute(
        """
        UPDATE skills
        SET display_name = %s, description = %s, transport = %s, command = %s,
            args_json = %s, url = %s, updated_at = NOW()
        WHERE name = %s AND kind = 'mcp'
        """,
        (display_name, description, transport, command, json.dumps(args, ensure_ascii=False), url, text),
    )
    return get_mcp_skill(text)


def delete_skill(name: str) -> None:
    text = str(name or "").strip()
    row = query_one("SELECT name FROM skills WHERE name = %s AND kind = 'skill'", (text,))
    if not row:
        raise LookupError(f"Skill {text} 不存在")
    execute("DELETE FROM skills WHERE name = %s AND kind = 'skill'", (text,))


def delete_mcp_skill(name: str) -> None:
    text = str(name or "").strip()
    row = query_one("SELECT name, transport FROM skills WHERE name = %s AND kind = 'mcp'", (text,))
    if not row:
        raise LookupError(f"MCP 技能 {text} 不存在或不可删除")
    if str(row.get("transport") or "") == "builtin":
        raise LookupError(f"MCP 技能 {text} 为内置工具，不可删除")
    execute("DELETE FROM skills WHERE name = %s AND kind = 'mcp'", (text,))

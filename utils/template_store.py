"""Agent 模板：仓库 JSON 文件读写（webapi 与 MCP 共用）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = _ROOT / "templates"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 必须是 JSON 对象")
    return data


def _normalize_file_template(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or path.stem).strip() or path.stem
    if name.startswith("{") and name.endswith("}"):
        name = path.stem
    body = data.get("body")
    if body is None:
        if "stages" in data or "params" in data:
            body = {key: value for key, value in data.items() if key not in {"name", "display_name", "description", "category"}}
        else:
            body = data
    if not isinstance(body, dict):
        raise ValueError(f"{path.name} 的 body 必须是 JSON 对象")
    display_name = str(data.get("display_name") or name).strip() or name
    if display_name.startswith("{") and display_name.endswith("}"):
        display_name = name
    return {
        "name": name,
        "display_name": display_name,
        "description": str(data.get("description") or "").strip(),
        "category": str(data.get("category") or "workflow").strip() or "workflow",
        "source": "file",
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "file": path.name,
        "body": body,
    }


def list_file_templates() -> list[dict[str, Any]]:
    if not TEMPLATES_DIR.exists():
        return []
    items = [_normalize_file_template(path, _read_json(path)) for path in sorted(TEMPLATES_DIR.glob("*.json"))]
    items.sort(key=lambda item: item["name"])
    return items

def load_file_template(name: str) -> dict[str, Any]:
    text = str(name or "").strip()
    if not text:
        raise ValueError("模板标识不能为空")
    path = TEMPLATES_DIR / f"{text}.json"
    if not path.is_file():
        raise LookupError(f"未找到模板 {text}")
    return _normalize_file_template(path, _read_json(path))


def load_template_body(name: str) -> dict[str, Any]:
    from webapi.templates_catalog import get_template_body

    return get_template_body(name)

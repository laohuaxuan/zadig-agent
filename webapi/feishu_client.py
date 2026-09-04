"""飞书 Open API 客户端（OAuth + 通讯录）。"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from utils.config import feishu_config

_OPENAPI = "https://open.feishu.cn/open-apis"
_TOKEN_CACHE: dict[str, Any] = {"token": "", "expires_at": 0.0}
_CONTACT_CACHE_TTL = 1800
_CONTACT_CACHE: dict[str, Any] = {
    "users": [],
    "expires_at": 0.0,
    "loading": False,
    "error": "",
}


def _normalize_contact_user(item: dict[str, Any]) -> dict[str, Any]:
    open_id = str(item.get("open_id") or "").strip()
    name = str(item.get("name") or item.get("en_name") or open_id).strip()
    return {
        "open_id": open_id,
        "name": name,
        "email": str(item.get("email") or "").strip(),
        "mobile": str(item.get("mobile") or "").strip(),
    }


def _filter_contact_users(users: list[dict[str, Any]], keyword: str) -> list[dict[str, Any]]:
    query = keyword.strip().lower()
    if not query:
        return users
    out: list[dict[str, Any]] = []
    for user in users:
        haystack = " ".join(
            [
                str(user.get("name") or ""),
                str(user.get("email") or ""),
                str(user.get("mobile") or ""),
            ]
        ).lower()
        if query in haystack:
            out.append(user)
    return out


class FeishuClient:
    def __init__(self) -> None:
        self.cfg = feishu_config()

    def enabled(self) -> bool:
        return bool(self.cfg.get("app_id") and self.cfg.get("app_secret"))

    def oauth_redirect_uri(self, fallback: str) -> str:
        uri = str(self.cfg.get("oauth_redirect_uri") or "").strip()
        if uri:
            return uri
        base = str(self.cfg.get("app_base_url") or fallback or "").strip().rstrip("/")
        return f"{base}/api/login/feishu/callback" if base else ""

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        if not self.enabled():
            raise ValueError("飞书 OAuth 未配置")
        params = {
            "app_id": self.cfg["app_id"],
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{_OPENAPI}/authen/v1/authorize?{urlencode(params)}"

    async def tenant_access_token(self) -> str:
        now = time.time()
        if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > now + 30:
            return str(_TOKEN_CACHE["token"])
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_OPENAPI}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.cfg["app_id"], "app_secret": self.cfg["app_secret"]},
            )
            data = resp.json()
        if int(data.get("code", -1)) != 0:
            raise ValueError(data.get("msg") or "获取飞书 tenant token 失败")
        token = str(data.get("tenant_access_token") or "")
        expire = int(data.get("expire") or 7200)
        _TOKEN_CACHE["token"] = token
        _TOKEN_CACHE["expires_at"] = now + expire
        return token

    async def exchange_oauth_code(self, code: str) -> dict[str, Any]:
        app_token = await self.tenant_access_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_OPENAPI}/authen/v1/access_token",
                headers={"Authorization": f"Bearer {app_token}"},
                json={"grant_type": "authorization_code", "code": code},
            )
            data = resp.json()
        if int(data.get("code", -1)) != 0:
            raise ValueError(data.get("msg") or "飞书 OAuth 换票失败")
        user_token = str((data.get("data") or {}).get("access_token") or "")
        if not user_token:
            raise ValueError("飞书 OAuth 换票失败")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_OPENAPI}/authen/v1/user_info",
                headers={"Authorization": f"Bearer {user_token}"},
            )
            info = resp.json()
        if int(info.get("code", -1)) != 0:
            raise ValueError(info.get("msg") or "获取飞书用户信息失败")
        raw = info.get("data") or {}
        name = str(raw.get("name") or raw.get("en_name") or "").strip()
        return {
            "open_id": str(raw.get("open_id") or ""),
            "name": name,
            "email": str(raw.get("email") or "").strip(),
            "mobile": str(raw.get("mobile") or "").strip(),
            "avatar": str(raw.get("avatar_url") or "").strip(),
        }

    def _configured_department_roots(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in self.cfg.get("department_ids") or ["0"]:
            dept_id = str(raw).strip()
            if not dept_id or dept_id in seen:
                continue
            seen.add(dept_id)
            out.append(dept_id)
        return out or ["0"]

    async def _list_department_children(
        self,
        client: httpx.AsyncClient,
        token: str,
        department_id: str,
        page_token: str = "",
    ) -> tuple[list[str], str, bool]:
        params: dict[str, Any] = {
            "department_id_type": "department_id",
            "fetch_child": "false",
            "page_size": 50,
        }
        if page_token:
            params["page_token"] = page_token
        resp = await client.get(
            f"{_OPENAPI}/contact/v3/departments/{quote(department_id, safe='')}/children",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        data = resp.json()
        if int(data.get("code", -1)) != 0:
            raise ValueError(data.get("msg") or "获取飞书子部门失败")
        payload = data.get("data") or {}
        ids: list[str] = []
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            dept_id = str(item.get("department_id") or item.get("open_department_id") or "").strip()
            if dept_id:
                ids.append(dept_id)
        return ids, str(payload.get("page_token") or ""), bool(payload.get("has_more"))

    async def _list_all_department_ids(self, client: httpx.AsyncClient, token: str, max_departments: int = 500) -> list[str]:
        roots = self._configured_department_roots()
        seen = set(roots)
        queue = list(roots)
        out = list(roots)
        while queue:
            if len(out) >= max_departments:
                break
            department_id = queue.pop(0)
            page_token = ""
            while True:
                child_ids, page_token, has_more = await self._list_department_children(
                    client, token, department_id, page_token
                )
                for child_id in child_ids:
                    if child_id in seen:
                        continue
                    seen.add(child_id)
                    out.append(child_id)
                    queue.append(child_id)
                    if len(out) >= max_departments:
                        break
                if len(out) >= max_departments or not has_more or not page_token:
                    break
        return out

    async def _list_users_by_department(
        self,
        client: httpx.AsyncClient,
        token: str,
        department_id: str,
        page_token: str = "",
    ) -> tuple[list[dict[str, Any]], str, bool]:
        params: dict[str, Any] = {
            "department_id": department_id,
            "department_id_type": "department_id",
            "user_id_type": "open_id",
            "page_size": 50,
        }
        if page_token:
            params["page_token"] = page_token
        resp = await client.get(
            f"{_OPENAPI}/contact/v3/users/find_by_department",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        data = resp.json()
        if int(data.get("code", -1)) != 0:
            raise ValueError(data.get("msg") or "获取飞书部门成员失败")
        payload = data.get("data") or {}
        items = [_normalize_contact_user(item) for item in (payload.get("items") or []) if isinstance(item, dict)]
        return items, str(payload.get("page_token") or ""), bool(payload.get("has_more"))

    async def _collect_all_contact_users(self, max_users: int = 2000) -> tuple[list[dict[str, Any]], str]:
        token = await self.tenant_access_token()
        warnings: list[str] = []
        users_by_open_id: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            department_ids = await self._list_all_department_ids(client, token)
            for department_id in department_ids:
                page_token = ""
                while True:
                    try:
                        batch, page_token, has_more = await self._list_users_by_department(
                            client, token, department_id, page_token
                        )
                    except ValueError as exc:
                        warnings.append(str(exc))
                        break
                    for user in batch:
                        open_id = user.get("open_id")
                        if open_id:
                            users_by_open_id[str(open_id)] = user
                        if len(users_by_open_id) >= max_users:
                            warnings.append(f"通讯录已加载前 {max_users} 名成员")
                            break
                    if len(users_by_open_id) >= max_users or not has_more or not page_token:
                        break
                if len(users_by_open_id) >= max_users:
                    break
        users = sorted(users_by_open_id.values(), key=lambda item: str(item.get("name") or ""))
        warning = "；".join(dict.fromkeys(w for w in warnings if w))
        return users, warning

    def _cached_users_snapshot(self) -> list[dict[str, Any]] | None:
        if _CONTACT_CACHE["loading"]:
            return None
        if time.time() >= float(_CONTACT_CACHE["expires_at"] or 0):
            return None
        users = _CONTACT_CACHE.get("users") or []
        if not users:
            return None
        return list(users)

    async def _refresh_contact_cache(self) -> tuple[list[dict[str, Any]], str]:
        if _CONTACT_CACHE["loading"]:
            while _CONTACT_CACHE["loading"]:
                await asyncio.sleep(0.2)
            cached = self._cached_users_snapshot()
            if cached is not None:
                return cached, str(_CONTACT_CACHE.get("error") or "")
        _CONTACT_CACHE["loading"] = True
        try:
            users, warning = await self._collect_all_contact_users()
            _CONTACT_CACHE["users"] = users
            _CONTACT_CACHE["expires_at"] = time.time() + _CONTACT_CACHE_TTL
            _CONTACT_CACHE["error"] = warning
            return users, warning
        finally:
            _CONTACT_CACHE["loading"] = False

    def warmup_contact_users_async(self) -> None:
        if not self.enabled() or _CONTACT_CACHE["loading"] or self._cached_users_snapshot() is not None:
            return

        async def _run() -> None:
            try:
                await self._refresh_contact_cache()
            except Exception as exc:
                _CONTACT_CACHE["error"] = str(exc) or "通讯录加载失败"

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(_run())

    async def list_contact_users(self, keyword: str = "", page_size: int = 30) -> dict[str, Any]:
        if not self.enabled():
            return {"items": [], "warning": "", "cached": False}
        page_size = min(max(int(page_size or 30), 1), 50)
        keyword = keyword.strip()

        cached = self._cached_users_snapshot()
        if cached is None:
            if _CONTACT_CACHE["loading"]:
                return {"items": [], "warning": "通讯录加载中，请稍候再试", "cached": False}
            users, warning = await self._refresh_contact_cache()
        else:
            users, warning = cached, str(_CONTACT_CACHE.get("error") or "")

        filtered = _filter_contact_users(users, keyword)
        return {
            "items": filtered[:page_size],
            "warning": warning,
            "cached": cached is not None,
        }

    async def search_users(self, keyword: str, page_size: int = 20) -> list[dict[str, Any]]:
        result = await self.list_contact_users(keyword, page_size)
        warning = str(result.get("warning") or "").strip()
        items = result.get("items") or []
        if warning and not items and "加载中" not in warning:
            raise ValueError(warning)
        return items

    async def send_interactive_card(self, open_id: str, card: dict[str, Any]) -> str:
        from webapi.feishu_cards import marshal_interactive_card

        if not self.enabled():
            raise ValueError("飞书 Open API 未配置")
        open_id = open_id.strip()
        if not open_id:
            raise ValueError("feishu open_id empty")
        content = marshal_interactive_card(card)
        token = await self.tenant_access_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_OPENAPI}/im/v1/messages",
                headers={"Authorization": f"Bearer {token}"},
                params={"receive_id_type": "open_id"},
                json={"receive_id": open_id, "msg_type": "interactive", "content": content},
            )
            data = resp.json()
        if int(data.get("code", -1)) != 0:
            raise ValueError(data.get("msg") or "发送飞书卡片失败")
        return str(((data.get("data") or {}).get("message_id")) or "").strip()

    async def update_interactive_message(self, message_id: str, card: dict[str, Any]) -> None:
        from webapi.feishu_cards import marshal_interactive_card

        message_id = message_id.strip()
        if not message_id:
            raise ValueError("feishu message_id empty")
        content = marshal_interactive_card(card)
        token = await self.tenant_access_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(
                f"{_OPENAPI}/im/v1/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": content},
            )
            data = resp.json()
        if int(data.get("code", -1)) != 0:
            raise ValueError(data.get("msg") or "更新飞书卡片失败")

    def approval_action_url(self, base_url: str, token: str) -> str:
        from urllib.parse import quote

        base = str(base_url or "").strip().rstrip("/")
        token = str(token or "").strip()
        if not base or not token:
            return ""
        return f"{base}/api/feishu/approval/action?token={quote(token)}"

    def public_api_base(self) -> str:
        from urllib.parse import urlparse

        base = str(self.cfg.get("app_base_url") or "").strip().rstrip("/")
        if not base:
            return ""
        parsed = urlparse(base)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return base

"""飞书 Open API 客户端（OAuth + 通讯录搜索）。"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import httpx

from utils.config import feishu_config

_OPENAPI = "https://open.feishu.cn/open-apis"
_token_cache: dict[str, Any] = {"token": "", "expires_at": 0.0}


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
        if _token_cache["token"] and _token_cache["expires_at"] > now + 30:
            return str(_token_cache["token"])
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
        _token_cache["token"] = token
        _token_cache["expires_at"] = now + expire
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

    async def search_users(self, keyword: str, page_size: int = 20) -> list[dict[str, Any]]:
        if not self.enabled():
            return []
        token = await self.tenant_access_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_OPENAPI}/contact/v3/users/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"page_size": min(page_size, 50)},
                json={"query": keyword.strip()},
            )
            data = resp.json()
        if int(data.get("code", -1)) != 0:
            raise ValueError(data.get("msg") or "搜索飞书用户失败")
        items = ((data.get("data") or {}).get("users")) or []
        out: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            open_id = str(item.get("open_id") or "").strip()
            name = str(item.get("name") or item.get("en_name") or open_id).strip()
            out.append(
                {
                    "open_id": open_id,
                    "name": name,
                    "email": str(item.get("email") or "").strip(),
                    "mobile": str(item.get("mobile") or "").strip(),
                }
            )
        return out

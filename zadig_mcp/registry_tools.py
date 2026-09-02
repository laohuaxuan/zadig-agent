"""Zadig 镜像仓库 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/registry/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/
"""

from __future__ import annotations

from typing import Any, Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_PROVIDERS = {"acr", "tcr", "swr", "ecr", "dockerhub", "harbor", "nexus", "native"}


def _require(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


def _enc(value: str) -> str:
    return quote(value, safe="")


def _normalize_address(address: str) -> str:
    addr = _require("address", address)
    if not addr.startswith(("http://", "https://")):
        raise ValueError("address 需包含协议，例如 https://registry.example.com")
    return addr


def _normalize_provider(provider: str) -> str:
    value = _require("provider", provider).lower()
    if value not in _PROVIDERS:
        raise ValueError(
            "provider 必须是 acr、tcr、swr、ecr、dockerhub、harbor、nexus 或 native"
        )
    return value


@mcp.tool(name="list_registries", description="列出系统中已集成的镜像仓库。")
def list_registries() -> Annotated[str, Field(description="镜像仓库列表")]:
    """对应 GET /openapi/system/registry。"""
    try:
        return _dump(zadig_request("GET", "/openapi/system/registry"))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="get_registry", description="获取指定镜像仓库信息。")
def get_registry(
    registry_id: Annotated[str, Field(description="镜像仓库主键 ID", example="6308815592abcd995e813035")],
) -> Annotated[str, Field(description="镜像仓库详情")]:
    """对应 GET /openapi/system/registry/:id。"""
    try:
        rid = _require("registry_id", registry_id)
        return _dump(zadig_request("GET", f"/openapi/system/registry/{_enc(rid)}"))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_registry", description="集成镜像仓库，可设为系统默认仓库。")
def create_registry(
    address: Annotated[str, Field(description="镜像仓库地址，需包含协议", example="https://xxxx.tencentcloudcr.com")],
    provider: Annotated[
        str,
        Field(description="提供商：acr、tcr、swr、ecr、dockerhub、harbor、nexus、native", example="tcr"),
    ],
    namespace: Annotated[str, Field(description="镜像仓库命名空间", example="zadigx")],
    is_default: Annotated[bool, Field(description="是否设为默认镜像仓库，系统同时只能有一个默认仓库", example=False)],
    access_key: Annotated[str, Field(description="镜像仓库 Access Key / 用户名", example="")],
    secret_key: Annotated[str, Field(description="镜像仓库 Secret Key / 密码", example="")],
    region: Annotated[str, Field(description="区域信息，provider 为 ecr 时必填", example="")] = "",
    enable_tls: Annotated[bool, Field(description="是否开启 SSL 校验", example=False)] = False,
    tls_cert: Annotated[str, Field(description="TLS 证书内容，enable_tls 为 true 时必填", example="")] = "",
) -> Annotated[str, Field(description="创建结果")]:
    """对应 POST /openapi/system/registry。"""
    try:
        ptype = _normalize_provider(provider)
        payload: dict[str, Any] = {
            "address": _normalize_address(address),
            "provider": ptype,
            "namespace": _require("namespace", namespace),
            "is_default": is_default,
            "access_key": _require("access_key", access_key),
            "secret_key": _require("secret_key", secret_key),
        }
        if ptype == "ecr":
            payload["region"] = _require("region", region)
        elif region.strip():
            payload["region"] = region.strip()
        if enable_tls:
            payload["enable_tls"] = True
            payload["tls_cert"] = _require("tls_cert", tls_cert)
        else:
            payload["enable_tls"] = False
        return _dump(zadig_request("POST", "/openapi/system/registry", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_registry", description="更新指定镜像仓库的地址、提供商、命名空间和默认标记。")
def update_registry(
    registry_id: Annotated[str, Field(description="镜像仓库主键 ID", example="6308815592abcd995e813035")],
    address: Annotated[str, Field(description="镜像仓库地址，需包含协议", example="https://xxxx.tencentyun.com")],
    provider: Annotated[
        str,
        Field(description="提供商：acr、tcr、swr、ecr、dockerhub、harbor、nexus、native", example="native"),
    ],
    namespace: Annotated[str, Field(description="镜像仓库命名空间", example="koderover-demo")],
    is_default: Annotated[bool, Field(description="是否设为默认镜像仓库", example=False)],
    region: Annotated[str, Field(description="区域信息，provider 为 ecr 时必填", example="")] = "",
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/system/registry/:id。"""
    try:
        rid = _require("registry_id", registry_id)
        ptype = _normalize_provider(provider)
        payload: dict[str, Any] = {
            "registry_id": rid,
            "address": _normalize_address(address),
            "provider": ptype,
            "namespace": _require("namespace", namespace),
            "is_default": is_default,
            "region": "",
        }
        if ptype == "ecr":
            payload["region"] = _require("region", region)
        elif region.strip():
            payload["region"] = region.strip()
        return _dump(zadig_request("PUT", f"/openapi/system/registry/{_enc(rid)}", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

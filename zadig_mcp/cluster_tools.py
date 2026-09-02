"""Zadig 集群 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/cluster/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/
"""

from __future__ import annotations

from typing import Any, Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()

_CLUSTER_TYPES = {"agent", "kubeconfig"}
_PROVIDERS = {0, 1, 2, 3, 4, 5, 6, 7}


def _require(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} 不能为空")
    return text


def _enc(value: str) -> str:
    return quote(value, safe="")


def _normalize_project_names(items: list[str]) -> list[str]:
    if not items:
        raise ValueError("project_names 不能为空；全部项目请传 <all_projects>")
    if not isinstance(items, list):
        raise ValueError("project_names 必须是字符串数组")
    out: list[str] = []
    for item in items:
        name = str(item or "").strip()
        if not name:
            raise ValueError("project_names 中不能包含空字符串")
        out.append(name)
    return out


@mcp.tool(name="list_clusters", description="列出系统中的集群信息。")
def list_clusters() -> Annotated[str, Field(description="集群列表")]:
    """对应 GET /openapi/system/cluster。"""
    try:
        return _dump(zadig_request("GET", "/openapi/system/cluster"))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="create_cluster", description="创建 Kubernetes 集群（代理模式或 kubeconfig 直连）。")
def create_cluster(
    name: Annotated[str, Field(description="集群名称", example="local-20220823144517")],
    cluster_type: Annotated[str, Field(description="集群类型：agent（代理模式）或 kubeconfig（直连）", example="agent")],
    production: Annotated[bool, Field(description="是否为生产集群", example=False)],
    provider: Annotated[
        int,
        Field(
            description="供应商：0 标准 Kubernetes，1 ACK，2 TKE，3 CCE，4 EKS，5 TKE Serverless，6 GKE，7 AKS",
            example=0,
        ),
    ],
    description: Annotated[str, Field(description="集群描述", example="本地集群")],
    project_names: Annotated[
        list[str],
        Field(description="可使用该集群的项目标识列表；全部项目传 <all_projects>", example=["<all_projects>"]),
    ],
    kube_config: Annotated[str, Field(description="Kubeconfig 内容；type 为 kubeconfig 时必填，agent 时可为空", example="")] = "",
) -> Annotated[str, Field(description="创建结果，含 cluster；agent 模式还会返回 agent_cmd")]:
    """对应 POST /openapi/system/cluster。"""
    try:
        ctype = _require("cluster_type", cluster_type)
        if ctype not in _CLUSTER_TYPES:
            raise ValueError("cluster_type 必须是 agent 或 kubeconfig")
        if int(provider) not in _PROVIDERS:
            raise ValueError("provider 必须是 0 到 7")
        kube = kube_config.strip()
        if ctype == "kubeconfig" and not kube:
            raise ValueError("直连模式必须提供 kube_config")
        payload: dict[str, Any] = {
            "name": _require("name", name),
            "type": ctype,
            "kube_config": kube,
            "production": production,
            "provider": int(provider),
            "description": description if description is not None else "",
            "project_names": _normalize_project_names(project_names),
        }
        return _dump(zadig_request("POST", "/openapi/system/cluster", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="update_cluster", description="更新指定集群的名称、描述和可用项目范围。")
def update_cluster(
    cluster_id: Annotated[str, Field(description="集群主键 ID", example="0123456789abcdef12345678")],
    name: Annotated[str, Field(description="集群名称", example="local-20220823144517-new")],
    description: Annotated[str, Field(description="集群描述", example="本地集群")],
    project_names: Annotated[
        list[str],
        Field(description="可使用该集群的项目标识列表；全部项目传 <all_projects>", example=["<all_projects>"]),
    ],
) -> Annotated[str, Field(description="更新结果")]:
    """对应 PUT /openapi/system/cluster/:id。"""
    try:
        cid = _require("cluster_id", cluster_id)
        payload = {
            "name": _require("name", name),
            "description": description if description is not None else "",
            "project_names": _normalize_project_names(project_names),
        }
        return _dump(zadig_request("PUT", f"/openapi/system/cluster/{_enc(cid)}", json_data=payload))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="delete_cluster", description="删除指定集群。")
def delete_cluster(
    cluster_id: Annotated[str, Field(description="集群主键 ID", example="0123456789abcdef12345678")],
) -> Annotated[str, Field(description="删除结果")]:
    """对应 DELETE /openapi/system/cluster/:id。"""
    try:
        cid = _require("cluster_id", cluster_id)
        return _dump(zadig_request("DELETE", f"/openapi/system/cluster/{_enc(cid)}"))
    except Exception as exc:
        return _error(str(exc))


@mcp.tool(name="check_cluster_istio", description="检查指定集群是否已安装 Istio。")
def check_cluster_istio(
    cluster_id: Annotated[str, Field(description="集群主键 ID", example="0123456789abcdef12345678")],
) -> Annotated[str, Field(description="检查结果，true 表示已安装")]:
    """对应 GET /openapi/cluster/istio/check/:id。"""
    try:
        cid = _require("cluster_id", cluster_id)
        data = zadig_request("GET", f"/openapi/cluster/istio/check/{_enc(cid)}")
        if isinstance(data, bool):
            return _dump({"installed": data})
        if isinstance(data, str):
            text = data.strip().lower()
            if text in {"true", "false"}:
                return _dump({"installed": text == "true"})
            return _dump({"result": data})
        return _dump(data)
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

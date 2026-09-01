"""Zadig 模板库 OpenAPI 工具。

文档：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/template/
鉴权：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/usage/

v5.0 模板库 OpenAPI 目前仅提供 Chart 模板列表。
使用模板新建服务见服务接口：https://docs.koderover.com/zadig/cn/Zadig%20v5.0/api/service/
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from utils.zadig import dump as _dump, error as _error, zadig_request

mcp = FastMCP()


@mcp.tool(
    name="list_chart_templates",
    description="获取模板库中的 Chart 模板列表，以及模板支持的系统变量。",
)
def list_chart_templates() -> Annotated[str, Field(description="系统变量与 Chart 模板列表")]:
    """对应 GET /openapi/templates/charts。

    返回 system_variables（key、description）和 chart_templates
    （name、codehost_id、owner、namespace、repo、path、branch）。
    """
    try:
        return _dump(zadig_request("GET", "/openapi/templates/charts"))
    except Exception as exc:
        return _error(str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")

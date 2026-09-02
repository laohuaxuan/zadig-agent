from utils.mcp import get_zadig_mcp_tools


async def get_stdio_tools():
    tools, _client = await get_zadig_mcp_tools()
    return tools

from utils.mcp import create_mcp_stdio_client

async def get_stdio_tools():
    params = {
        "command": "python",
        "args": [
            "./mcp/environment_tools.py",
        ]
    }

    tools, client = await create_mcp_stdio_client("environment_tools", params)
    return tools
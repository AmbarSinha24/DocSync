from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.config import settings


@asynccontextmanager
async def github_mcp_session():
    """Opens an MCP client session against GitHub's hosted remote MCP server."""
    headers = {"Authorization": f"Bearer {settings.github_mcp_token}"}
    async with streamablehttp_client(settings.github_mcp_server_url, headers=headers) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def list_github_mcp_tools() -> list[str]:
    async with github_mcp_session() as session:
        result = await session.list_tools()
        return [tool.name for tool in result.tools]

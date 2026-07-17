import pytest

from app.integrations.github_mcp import list_github_mcp_tools


@pytest.mark.asyncio
async def test_can_list_github_mcp_tools():
    tools = await list_github_mcp_tools()
    assert len(tools) > 0
    assert any("repo" in name.lower() or "file" in name.lower() for name in tools)

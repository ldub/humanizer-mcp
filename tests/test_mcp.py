"""Exercise the actual stdio MCP protocol against a shared controller fixture."""

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from humanizer_mcp.controller import MAX_MESSAGE


async def test_mcp_discovery_rewrite_and_disabled_contract(controller):
    socket = controller.root / "control.sock"
    server = await asyncio.start_unix_server(controller.handle, path=str(socket), limit=MAX_MESSAGE)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "humanizer_mcp.server"],
        env={
            **os.environ,
            "HUMANIZER_DATA_DIR": str(controller.root),
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        },
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert "audience" in initialized.instructions
                tools = (await session.list_tools()).tools
                assert {tool.name for tool in tools} == {"humanize_copy", "humanizer_status"}
                result = await session.call_tool(
                    "humanize_copy", {"fields": [{"id": "copy", "text": "utilize this"}]}
                )
                assert not result.isError
                assert result.structuredContent["fields"][0]["text"] == "use this"
                await controller.set_enabled(False)
                result = await session.call_tool(
                    "humanize_copy", {"fields": [{"id": "copy", "text": "utilize this"}]}
                )
                assert result.structuredContent["status"] == "disabled"
                assert result.structuredContent["fields"][0]["text"] == "utilize this"
                assert controller.worker is None
    finally:
        server.close()
        await server.wait_closed()

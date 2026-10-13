"""A lightweight stdio MCP adapter; the shared menu app owns model lifetime."""

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .client import ensure_app, request
from .copy import CopyField, RewriteRequest, unchanged

mcp = FastMCP(
    "humanizer",
    instructions=(
        "Use humanize_copy for text the user will publish in a website/app, include in an audience-facing "
        "document, or send to someone else. Ordinary assistant conversation stays unchanged. "
        "Review returned rewrites for meaning and factual accuracy before use. If disabled, use the "
        "original draft without retries. Only the user controls the menu bar switch."
    ),
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
async def humanizer_status() -> dict[str, Any]:
    """Check whether local Humanizer is ready, loading, busy, off, or unavailable."""
    return await ensure_app()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
async def humanize_copy(fields: list[CopyField]) -> dict[str, Any]:
    """Rewrite audience-facing copy locally. Submit named text fields, with exact preserve terms and
    optional max_characters. Keep each call around 300 words total to fit the local time budget.
    Use plain for app strings/headlines, markdown for document prose.
    Markdown headings, tables, quotes, and code remain intact; extract headings as plain fields if
    they need rewriting. Returns originals on validation failure or when the user switches it off.
    Mechanical checks do not establish factual fidelity; review every accepted rewrite before use.
    """
    batch = RewriteRequest(fields=fields)
    status = await ensure_app()
    if status["status"] == "unavailable":
        return unchanged(batch, "unavailable", status["message"])
    try:
        # Portable plugin manifests do not expose Codex's tool timeout setting. Finish below
        # the host's usual 60-second limit; disconnecting also cancels the controller job.
        return await request({"action": "rewrite", "request": batch.model_dump()}, timeout=45)
    except TimeoutError:
        return unchanged(batch, "timeout", "Humanizer timed out. Continue with the original draft.")
    except (OSError, ValueError):
        return unchanged(batch, "unavailable", "Humanizer is unavailable. Continue with the original draft.")


def main():
    asyncio.run(ensure_app())
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

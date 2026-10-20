"""Synthetic MCP only; no mailbox, real contacts, user files or network access."""

import asyncio
import hashlib
import os
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP

if marker := os.environ.get("SYNTHETIC_PID_FILE"):
    Path(marker).write_text(str(os.getpid()))

server = FastMCP("Synthetic companion acceptance")


@server.tool()
async def greet(name: str, ctx: Context) -> str:
    await ctx.report_progress(1, 1, "Synthetic progress")
    return "Hello " + name


@server.tool()
def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@server.tool()
async def client_roots(ctx: Context) -> str:
    response = await ctx.session.list_roots()
    return str(response.roots[0].uri)


@server.tool()
async def wait_for_disconnect() -> str:
    await asyncio.sleep(30)
    return "Should not be replayed"


@server.resource("synthetic://status")
def resource() -> str:
    return "Synthetic resource"


@server.prompt()
def synthetic_prompt() -> str:
    return "Synthetic prompt"


if __name__ == "__main__":
    server.run()

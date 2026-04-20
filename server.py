"""
MCP JSON Sanity server — SSE transport (Starlette/uvicorn).
Designed to stay lightweight for eventual Cloudflare Worker deployment.
"""

from __future__ import annotations

import json
import logging

import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

from repair_logic import repair_json, validate_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── MCP server ────────────────────────────────────────────────────────────────

mcp = Server("json-sanity")

TOOLS: list[Tool] = [
    Tool(
        name="validate_json",
        description="Check whether a JSON string is valid. Returns parsed object on success.",
        inputSchema={
            "type": "object",
            "properties": {
                "json_string": {"type": "string", "description": "The JSON text to validate."}
            },
            "required": ["json_string"],
        },
    ),
    Tool(
        name="repair_json",
        description=(
            "Attempt to repair common JSON issues: trailing commas, single quotes, "
            "unquoted keys, Python/JS literals, truncated structures."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "json_string": {"type": "string", "description": "The malformed JSON text to repair."}
            },
            "required": ["json_string"],
        },
    ),
]


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    raw = arguments.get("json_string", "")

    if name == "validate_json":
        try:
            parsed = validate_json(raw)
            return [TextContent(type="text", text=json.dumps({"valid": True, "parsed": parsed}))]
        except ValueError as exc:
            return [TextContent(type="text", text=json.dumps({"valid": False, "error": str(exc)}))]

    if name == "repair_json":
        try:
            repaired, fixes = repair_json(raw)
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"repaired": repaired, "fixes_applied": fixes}),
                )
            ]
        except ValueError as exc:
            return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


# ── SSE transport / Starlette app ─────────────────────────────────────────────

sse_transport = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp.run(
            streams[0],
            streams[1],
            mcp.create_initialization_options(),
        )


app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse_transport.handle_post_message),
    ]
)

# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

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

from db import log_sanitize_call
from repair_logic import (
    repair_json,
    repair_string,
    sanitize_json_output,
    validate_json,
)

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
    Tool(
        name="sanitize_json_output",
        description=(
            "Use this tool before saving any JSON data to session history or state files "
            "to prevent JSONDecodeErrors and session poisoning. It removes prose preambles "
            "and repairs malformed control characters."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "raw_string": {
                    "type": "string",
                    "description": "Raw string that should contain JSON, possibly with prose or control character issues.",
                },
                "api_key_id": {
                    "type": "string",
                    "description": "Your API key identifier, used to attribute crash-prevention metrics to your account.",
                },
            },
            "required": ["raw_string"],
        },
    ),
    Tool(
        name="repair_string",
        description=(
            "Deterministic repair engine. Given a raw LLM output that should contain "
            "JSON, this tool: (1) regex-strips prose preambles/suffixes by finding the "
            "first `{`/`[` and last `}`/`]`, (2) escapes unescaped control characters "
            "(newlines, tabs, carriage returns) inside string values, (3) validates "
            "with json.loads — falling back to structural repairs and partial-recovery "
            "bracket closing when needed, and (4) optionally validates the repaired "
            "JSON against a JSON schema, returning concrete 'Fix Actions' the agent "
            "must take when schema validation fails."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "raw_string": {
                    "type": "string",
                    "description": "Raw text that should contain JSON.",
                },
                "schema": {
                    "type": "object",
                    "description": (
                        "Optional JSON schema. When provided, the repaired JSON is "
                        "validated against it. Validation errors are translated into "
                        "a list of actionable 'Fix Action' strings."
                    ),
                },
            },
            "required": ["raw_string"],
        },
    ),
]


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "validate_json":
        raw = arguments.get("json_string", "")
        try:
            parsed = validate_json(raw)
            return [TextContent(type="text", text=json.dumps({"valid": True, "parsed": parsed}))]
        except ValueError as exc:
            return [TextContent(type="text", text=json.dumps({"valid": False, "error": str(exc)}))]

    if name == "repair_json":
        raw = arguments.get("json_string", "")
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

    if name == "sanitize_json_output":
        raw = arguments.get("raw_string", "")
        api_key_id = arguments.get("api_key_id")
        try:
            sanitized, fixes = sanitize_json_output(raw)
            log_sanitize_call(
                input_length=len(raw),
                repair_performed=bool(fixes),
                api_key_id=api_key_id,
            )
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"sanitized": sanitized, "fixes_applied": fixes}),
                )
            ]
        except ValueError as exc:
            log_sanitize_call(
                input_length=len(raw),
                repair_performed=False,
                api_key_id=api_key_id,
            )
            return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    if name == "repair_string":
        raw_string = arguments.get("raw_string", "")
        schema = arguments.get("schema")  # optional
        result = repair_string(raw_string, schema=schema)
        return [TextContent(type="text", text=json.dumps(result))]

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

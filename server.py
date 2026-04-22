"""
MCP JSON Sanity server — StreamableHTTP transport (Starlette/uvicorn).

Uses stateless=True so every request is handled independently — no
in-process session map is needed, which means the server works correctly
behind Railway's Fastly CDN regardless of replica count.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator

import uvicorn
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from billing import billing_service
from db import log_sanitize_call
from repair_logic import (
    clean_llm_markdown,
    repair_json,
    repair_string,
    sanitize_json_output,
    validate_json,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── MCP server ────────────────────────────────────────────────────────────────

mcp = Server("json-sanity")

_API_KEY_PROP = {
    "api_key_id": {
        "type": "string",
        "description": "Your Stripe Customer ID, used for metered billing ($0.01 per invocation).",
    }
}

TOOLS: list[Tool] = [
    Tool(
        name="validate_json",
        description="Check whether a JSON string is valid. Returns parsed object on success.",
        inputSchema={
            "type": "object",
            "properties": {
                "json_string": {"type": "string", "description": "The JSON text to validate."},
                **_API_KEY_PROP,
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
                "json_string": {"type": "string", "description": "The malformed JSON text to repair."},
                **_API_KEY_PROP,
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
            "JSON, this tool: (1) strips markdown code fences (```json), (2) regex-strips "
            "prose preambles/suffixes, (3) escapes unescaped control characters inside "
            "string values, (4) validates with json.loads — falling back to structural "
            "repairs and partial-recovery bracket closing when needed, and (5) optionally "
            "validates the repaired JSON against a JSON schema."
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
                **_API_KEY_PROP,
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
    api_key_id: str | None = arguments.get("api_key_id")

    # Auth gate — every call must carry a valid Stripe Customer ID.
    if not api_key_id or not api_key_id.startswith("cus_"):
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": "Unauthorized",
                "message": (
                    "api_key_id is required and must be a valid Stripe Customer ID "
                    "(must start with 'cus_')"
                ),
            }),
        )]

    response: list[TextContent]
    success = True

    if name == "validate_json":
        raw = arguments.get("json_string", "")
        try:
            parsed = validate_json(raw)
            response = [TextContent(type="text", text=json.dumps({"valid": True, "parsed": parsed}))]
        except ValueError as exc:
            success = False
            response = [TextContent(type="text", text=json.dumps({"valid": False, "error": str(exc)}))]

    elif name == "repair_json":
        raw = arguments.get("json_string", "")
        try:
            repaired, fixes = repair_json(raw)
            response = [TextContent(type="text", text=json.dumps({"repaired": repaired, "fixes_applied": fixes}))]
        except ValueError as exc:
            success = False
            response = [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    elif name == "sanitize_json_output":
        raw = arguments.get("raw_string", "")
        try:
            sanitized, fixes = sanitize_json_output(raw)
            log_sanitize_call(
                input_length=len(raw),
                repair_performed=bool(fixes),
                api_key_id=api_key_id,
            )
            response = [TextContent(type="text", text=json.dumps({"sanitized": sanitized, "fixes_applied": fixes}))]
        except ValueError as exc:
            success = False
            log_sanitize_call(input_length=len(raw), repair_performed=False, api_key_id=api_key_id)
            response = [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    elif name == "repair_string":
        raw_string = arguments.get("raw_string", "")
        schema = arguments.get("schema")
        result = repair_string(raw_string, schema=schema)
        success = result.get("ok", False)
        response = [TextContent(type="text", text=json.dumps(result))]

    else:
        success = False
        response = [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    if success:
        billing_service.record_invocation(api_key_id=api_key_id, tool_name=name)

    return response


# ── StreamableHTTP transport / Starlette app ──────────────────────────────────

session_manager = StreamableHTTPSessionManager(
    app=mcp,
    stateless=True,   # no in-process session map — safe behind any load balancer
    json_response=False,
)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    async with session_manager.run():
        yield


async def handle_health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "json-sanity"})


async def handle_mcp(request: Request) -> None:
    await session_manager.handle_request(request.scope, request.receive, request._send)


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/", endpoint=handle_health),
        Route("/mcp", endpoint=handle_mcp, methods=["GET", "POST", "DELETE"]),
    ],
)

# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

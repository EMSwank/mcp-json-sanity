"""
Go/No-Go smoke test for the json-sanity MCP server.

Default target: https://json-sanity.up.railway.app
Override:       SMOKE_TEST_URL=http://localhost:8000 python smoke_test.py

WHAT IT CHECKS
  1. GET / returns {"status": "ok"} (health check).
  2. An MCP SSE round-trip calls `sanitize_json_output` with a
     deliberately malformed JSON payload (prose preamble, unquoted keys,
     trailing comma, truncated).
  3. The response contains valid, sanitized JSON and a non-empty
     `fixes_applied` list.

RUNNING
    cd mcp-json-sanity
    python tests/smoke_test.py                              # → hits Railway
    SMOKE_TEST_URL=http://localhost:8000 python tests/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

MALFORMED = (
    "Sure, here is the JSON you asked for: "
    '{name: "Alice", age: 30, tags: ["a", "b",],'
)


def main() -> None:
    import httpx

    base_url = os.environ.get("SMOKE_TEST_URL", "https://json-sanity.up.railway.app").rstrip("/")
    sse_url = f"{base_url}/sse"
    health_url = f"{base_url}/"

    failures: list[str] = []
    payload: dict[str, Any] = {}

    print(f"Targeting: {base_url}")

    # ── 1. Health check ──────────────────────────────────────────────────────
    print("── Check 1: GET / health check ──────────────────────────────────")
    try:
        resp = httpx.get(health_url, timeout=10.0)
        if resp.status_code != 200:
            failures.append(f"Health check returned HTTP {resp.status_code}: {resp.text[:200]}")
            print(f"  FAIL — HTTP {resp.status_code}")
        else:
            body = resp.json()
            if body.get("status") != "ok":
                failures.append(f"Health check body unexpected: {body}")
                print(f"  FAIL — {body}")
            else:
                print(f"  PASS — {body}")
    except Exception as exc:
        failures.append(f"Health check request failed: {exc!r}")
        print(f"  FAIL — {exc!r}")

    # ── 2. MCP SSE round-trip ────────────────────────────────────────────────
    print("── Check 2: MCP SSE round-trip (sanitize_json_output) ───────────")

    async def _call_server() -> Any:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(sse_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(
                    "sanitize_json_output",
                    {"raw_string": MALFORMED},
                )

    result = None
    try:
        result = asyncio.run(asyncio.wait_for(_call_server(), timeout=30.0))
    except Exception as exc:
        failures.append(f"SSE round-trip failed: {exc!r}")
        print(f"  FAIL — {exc!r}")

    if result is not None:
        try:
            if getattr(result, "isError", False):
                failures.append(f"MCP reported isError=True: {result}")
                print(f"  FAIL — isError: {result}")
            elif not getattr(result, "content", None):
                failures.append("MCP result has no content blocks")
                print("  FAIL — empty content")
            else:
                payload = json.loads(result.content[0].text)
                if "sanitized" not in payload:
                    failures.append(f"Response missing 'sanitized' key: {payload}")
                    print(f"  FAIL — {payload}")
                else:
                    json.loads(payload["sanitized"])  # must be valid JSON
                    if not payload.get("fixes_applied"):
                        failures.append("fixes_applied was empty — server didn't record any repair")
                        print("  FAIL — fixes_applied empty")
                    else:
                        print(f"  PASS — sanitized: {payload['sanitized']!r}")
                        print(f"  PASS — fixes    : {payload['fixes_applied']}")
        except Exception as exc:
            failures.append(f"Response parse failed: {exc!r}")
            print(f"  FAIL — {exc!r}")

    # ── Verdict ──────────────────────────────────────────────────────────────
    print("─────────────────────────────────────────────────────────────────")
    if failures:
        print("NO-GO:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)

    print("GO — all checks passed")
    print(f"  target        : {base_url}")
    print(f"  sanitized     : {payload.get('sanitized')!r}")
    print(f"  fixes_applied : {payload.get('fixes_applied')}")


if __name__ == "__main__":
    main()

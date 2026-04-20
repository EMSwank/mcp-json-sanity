"""
Final Go/No-Go smoke test for the json-sanity MCP server.

WHAT IT CHECKS
  1. The server module imports cleanly (no broken wiring between
     server ↔ billing ↔ db ↔ repair_logic).
  2. A real uvicorn process (in a background thread) opens a port and
     accepts SSE connections.
  3. An MCP client round-trip through the SSE transport successfully calls
     `sanitize_json_output` with a deliberately malformed JSON payload
     (prose preamble, unquoted keys, trailing comma, truncated).
  4. The response contains valid, sanitized JSON and a non-empty
     `fixes_applied` list.
  5. `db.log_sanitize_call` was invoked exactly once with the expected
     shape. The real Supabase writer is never called — a spy captures
     the arguments the server would have persisted.
  6. The billing hook was invoked exactly once against the test customer
     ID. Also spied — no Stripe API request leaves the test process.

RUNNING
    cd <project_dir>
    python smoke_test.py

  Exit code 0 = GO. Exit code 1 = NO-GO (failure list printed to stderr).

  No external services are contacted. STRIPE_SECRET_KEY, SUPABASE_URL,
  and SUPABASE_SERVICE_ROLE_KEY are cleared from the test process so
  credentials accidentally sourced in the user's shell can't leak a real
  write or charge.

SCOPE
  This test exercises the server's BOUNDARIES — that malformed JSON in
  over SSE produces a sanitized result, a DB-write intent with the right
  payload, and a billing intent with the right customer. It does NOT test
  the real Supabase insert or the real Stripe MeterEvent; those need a
  staging environment with real credentials.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import threading
import time
import types
from typing import Any


# ── 1. Prime the environment BEFORE any project imports ──────────────────
for var in ("STRIPE_SECRET_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
    os.environ.pop(var, None)


def _install_backend_stubs() -> None:
    """Install minimal sys.modules stubs for supabase and stripe so that
    server.py's transitive imports succeed even when those SDKs aren't
    installed. The spies we install later intercept every call path that
    would otherwise hit these stubs, so reaching them indicates a bug."""

    if "supabase" not in sys.modules:
        supa = types.ModuleType("supabase")

        class _StubClient:
            def table(self, *_a, **_k):  # pragma: no cover
                raise RuntimeError(
                    "supabase stub was reached — log_sanitize_call spy "
                    "should have intercepted this call"
                )

        supa.Client = _StubClient  # type: ignore[attr-defined]
        supa.create_client = lambda *_a, **_k: _StubClient()  # type: ignore[attr-defined]
        sys.modules["supabase"] = supa

    if "stripe" not in sys.modules:
        stripe_stub = types.ModuleType("stripe")
        stripe_stub.api_key = None  # type: ignore[attr-defined]

        class _MeterEvent:
            @staticmethod
            def create(**_kwargs):  # pragma: no cover
                raise RuntimeError(
                    "stripe stub was reached — billing spy should have "
                    "intercepted this call"
                )

        stripe_stub.billing = types.SimpleNamespace(MeterEvent=_MeterEvent)  # type: ignore[attr-defined]
        sys.modules["stripe"] = stripe_stub


_install_backend_stubs()

# Ensure the project root is importable regardless of where the script is invoked from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 2. Import the project (a clean import is itself a Go/No-Go signal) ───
try:
    import server  # noqa: E402
except Exception as exc:
    print(f"NO-GO: failed to import server — {exc!r}", file=sys.stderr)
    sys.exit(1)


# ── 3. Wire spies for the db and billing side effects ────────────────────
db_calls: list[dict[str, Any]] = []
billing_calls: list[dict[str, Any]] = []


def _db_spy(**kwargs: Any) -> None:
    db_calls.append(kwargs)


def _billing_spy(*, api_key_id: str | None, tool_name: str) -> None:
    billing_calls.append({"api_key_id": api_key_id, "tool_name": tool_name})


# server.py did `from db import log_sanitize_call`, so rebind the name in
# the server module's namespace (not in db.py).
server.log_sanitize_call = _db_spy  # type: ignore[attr-defined]

# Billing may be wired in either of two shapes, depending on which
# billing.py the project is currently using:
#   (a) legacy: `from billing import record_tool_invocation`
#   (b) new:    `from billing import billing_service`
#               server calls billing_service.record_invocation(...)
# Patch whichever shape is live. If neither is present, we fail loud —
# that means the server is importing something unexpected and prod would
# silently stop billing.
if hasattr(server, "record_tool_invocation"):
    server.record_tool_invocation = _billing_spy  # type: ignore[attr-defined]
elif hasattr(server, "billing_service"):
    server.billing_service.record_invocation = _billing_spy  # type: ignore[attr-defined]
else:
    try:
        from billing import billing_service  # type: ignore

        billing_service.record_invocation = _billing_spy  # type: ignore[attr-defined]
    except Exception as exc:
        print(
            "NO-GO: could not locate billing hook — server has no "
            "record_tool_invocation and billing.billing_service is absent "
            f"({exc!r})",
            file=sys.stderr,
        )
        sys.exit(1)


# ── 4. Spin up uvicorn on a random loopback port ─────────────────────────
def _pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _pick_port()


def _run_server() -> None:
    import uvicorn

    uvicorn.Server(
        uvicorn.Config(
            server.app,
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
            lifespan="off",
        )
    ).run()


threading.Thread(target=_run_server, daemon=True).start()

deadline = time.time() + 10.0
while time.time() < deadline:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.25):
            break
    except OSError:
        time.sleep(0.1)
else:
    print(f"NO-GO: server never opened port {PORT}", file=sys.stderr)
    sys.exit(1)


# ── 5. Round-trip a malformed JSON payload via the MCP SSE client ────────
MALFORMED = (
    'Sure, here is the JSON you asked for: '
    '{name: "Alice", age: 30, tags: ["a", "b",],'
)
API_KEY_ID = "cus_smoke_test"


async def _call_server() -> Any:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    url = f"http://127.0.0.1:{PORT}/sse"
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(
                "sanitize_json_output",
                {"raw_string": MALFORMED, "api_key_id": API_KEY_ID},
            )


try:
    result = asyncio.run(asyncio.wait_for(_call_server(), timeout=20.0))
except Exception as exc:
    print(f"NO-GO: SSE round-trip failed — {exc!r}", file=sys.stderr)
    sys.exit(1)


# ── 6. Assertions ────────────────────────────────────────────────────────
failures: list[str] = []
payload: dict[str, Any] = {}

# 6a. response shape and content
try:
    if getattr(result, "isError", False):
        failures.append(f"MCP reported isError=True: {result}")
    elif not getattr(result, "content", None):
        failures.append("MCP result has no content blocks")
    else:
        payload = json.loads(result.content[0].text)
        if "sanitized" not in payload:
            failures.append(f"response missing 'sanitized' key: {payload}")
        else:
            # The sanitized string must itself be valid JSON.
            json.loads(payload["sanitized"])
            if not payload.get("fixes_applied"):
                failures.append(
                    "fixes_applied was empty — server didn't record any "
                    f"repair for deliberately malformed input {MALFORMED!r}"
                )
except Exception as exc:
    failures.append(f"response parse failed: {exc!r}")

# 6b. db.log_sanitize_call spied exactly once with expected shape
if len(db_calls) != 1:
    failures.append(f"expected 1 db log call, got {len(db_calls)}: {db_calls}")
else:
    call = db_calls[0]
    if call.get("api_key_id") != API_KEY_ID:
        failures.append(f"db log api_key_id mismatch: {call}")
    if call.get("repair_performed") is not True:
        failures.append(f"db log repair_performed should be True: {call}")
    if call.get("input_length") != len(MALFORMED):
        failures.append(
            f"db log input_length mismatch: expected {len(MALFORMED)}, "
            f"got {call.get('input_length')}"
        )

# 6c. billing spied exactly once
if len(billing_calls) != 1:
    failures.append(
        f"expected 1 billing call, got {len(billing_calls)}: {billing_calls}"
    )
else:
    call = billing_calls[0]
    if call.get("api_key_id") != API_KEY_ID:
        failures.append(f"billing api_key_id mismatch: {call}")
    if call.get("tool_name") != "sanitize_json_output":
        failures.append(f"billing tool_name mismatch: {call}")


# ── 7. Verdict ───────────────────────────────────────────────────────────
if failures:
    print("NO-GO:", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    sys.stderr.flush()
    os._exit(1)  # same reasoning as the success path: don't let the
                 # daemon uvicorn thread log an aborted-SSE trace after
                 # we've already printed the failure reason.

print("GO — all checks passed")
print(f"  response sanitized : {payload.get('sanitized')!r}")
print(f"  response fixes     : {payload.get('fixes_applied')}")
print(f"  db log captured    : {db_calls[0]}")
print(f"  billing captured   : {billing_calls[0]}")
sys.stdout.flush()
# Hard-exit so the uvicorn daemon thread doesn't log the torn-down SSE
# connection after we've already printed GO. Process-level exit code is
# what CI cares about.
os._exit(0)

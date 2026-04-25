# JSON-Sanity: Agent Session Insurance

The deterministic MCP server that stops your long-running agents from eating their own state.

---

## The Death Loop

Every multi-step agentic workflow eventually hits the same failure mode.

An LLM produces output that is *almost* JSON. A stray "Sure, here you go:" preamble. An unescaped newline inside a string value. A trailing comma. A response truncated by the context window one token before the closing brace. Your orchestrator pipes that string into `json.loads`, gets a `JSONDecodeError`, and the session state file never gets written. On the next tick the agent reads a stale or empty state, asks the model to redo the last step, receives a slightly-different-but-equally-broken output, and the cycle begins.

This is the Death Loop. It is cheap to trigger, expensive to debug, and the longer your agent runs the more likely it is that a single malformed token wipes out hours of accumulated reasoning. The tools most teams reach for — retry-until-success, JSON mode, constrained decoding — reduce the rate of failure but do not eliminate it. Each retry spends real tokens on work that should have been spent making progress, and a determined corruption (escaped-control-character drift, schema violations) will survive the retry anyway. When the agent's state is the ground truth for everything it does next, a silent write failure is not a recoverable error; it is amnesia.

## What This Server Does

JSON-Sanity is a Model Context Protocol server whose entire job is to convert *"the JSON your agent just produced"* into *"JSON your agent can safely persist."* It runs deterministically. No additional LLM calls. No retries. No probabilistic anything. When your agent is about to write state, it calls one of the sanity tools and gets back either a guaranteed-parseable JSON string or a concrete, machine-readable list of Fix Actions describing exactly what the agent needs to change before it tries again.

The Death Loop breaks for two reasons. First, the session write never silently fails — malformed output is repaired before it touches durable storage, so the agent's next tick reads real state instead of an empty file. Second, when repair alone is not enough (for example, when output violates a schema your downstream code depends on), the server returns specific, targeted instructions like *"Add required field 'user_id' at $"* or *"Change 'age' from type str to type integer."* The agent retries with a fix plan instead of a vague "please try again," which converts what was a probabilistic loop into a single deterministic correction.

## Why It Is Essential for Long-Running Agents

Short conversational agents can afford to fail a JSON parse. The user will notice, retype, or start over. Long-running agents cannot. When an agent is running unattended — a planner checkpointing every ten minutes, a research workflow accumulating notes over an afternoon, a memory-tiered assistant that lives across sessions, a background job orchestrator handing tasks between sub-agents — every state write is load-bearing. A single corrupted checkpoint is not a failed step; it is a silent rollback of everything that happened after the last good write.

JSON-Sanity sits between the model's output and the state store and makes that failure mode impossible. For any workflow where state persistence is required, it is cheap insurance: one deterministic string pass saves a stateful rollback, and the per-invocation cost of the tool is orders of magnitude below the cost of one replayed agent turn.

## Tools

The server exposes four tools over the MCP StreamableHTTP transport.

**`sanitize_json_output`** — the tool to call before any state write. Strips prose preambles and suffixes, repairs malformed control characters, and delegates structural repairs. This is the tool that most directly prevents session poisoning; each call is logged so you can audit which agents are producing malformed output and how often.

**`repair_string`** — the deterministic repair engine. Given a raw LLM string, it locates the first `{` or `[` and the last `}` or `]`, escapes unescaped control characters found inside string values, validates with `json.loads`, and falls back to a partial-recovery pass that closes any unclosed brackets. Accepts an optional `schema` argument: when supplied, the repaired JSON is validated against it with the `jsonschema` library and any failures are returned as concrete Fix Actions the agent can act on.

**`repair_json`** — a lighter repair that handles the common structural issues (trailing commas, single quotes, unquoted keys, Python/JS literals like `True`/`False`/`None`, truncated structures). Use this when you know the input is nearly-JSON and do not need preamble-stripping or schema validation.

**`validate_json`** — a strict validator. Returns the parsed object on success or a descriptive error locating the exact line and column of the failure. Useful for probing suspect strings before deciding whether to repair.

## Installation

Coming soon on Smithery — for now, configure manually:

```json
{
  "mcpServers": {
    "json-sanity": {
      "url": "https://json-sanity.up.railway.app/mcp"
    }
  }
}
```

Configuration is read from environment variables at startup. The two that matter for production deployment:

```
SUPABASE_URL                  # where sanitize_logs rows are written
SUPABASE_SERVICE_ROLE_KEY     # service-role credentials for that project
STRIPE_SECRET_KEY             # optional; enables metered billing
STRIPE_METER_EVENT_NAME       # optional; defaults to "json_sanity_tool_invocation"
```

If `STRIPE_SECRET_KEY` is unset, billing runs in mock mode — each would-be meter event is printed to stdout so you can see exactly what would have been sent to Stripe without actually sending it. This makes local development and CI deterministic and free.

## Configuration

Add the following to your `claude_desktop_config.json` (or equivalent MCP client config) to connect Claude Desktop to a local instance:

```json
{
  "mcpServers": {
    "json-sanity": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp-json-sanity", "run", "python", "server.py"],
      "env": {
        "SUPABASE_URL": "https://your-project-ref.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "your-service-role-key",
        "STRIPE_SECRET_KEY": "sk_test_...",
        "STRIPE_METER_EVENT_NAME": "json_sanity_tool_invocation"
      }
    }
  }
}
```

`STRIPE_SECRET_KEY` is optional — omit it and billing runs in mock mode (events are printed to stdout). `STRIPE_METER_EVENT_NAME` is optional and defaults to `json_sanity_tool_invocation`.

The config file lives at:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

## Usage

Pass the customer identifier as `api_key_id` on every call to attribute repair volume and (if billing is enabled) charge the right account.

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with streamable_http_client("https://json-sanity.up.railway.app/mcp") as (r, w, _):
    async with ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool(
            "sanitize_json_output",
            {
                "raw_string": raw_model_output,
                "api_key_id": "cus_1234",
            },
        )
```

For schema-enforced outputs:

```python
result = await session.call_tool(
    "repair_string",
    {
        "raw_string": raw_model_output,
        "schema": {
            "type": "object",
            "required": ["user_id", "action"],
            "properties": {
                "user_id": {"type": "string"},
                "action": {"type": "string", "enum": ["create", "update", "delete"]},
            },
        },
        "api_key_id": "cus_1234",
    },
)
```

When the response includes a non-empty `fix_actions` list, feed those strings back to your agent in its next turn. They are written to be actionable in a single pass — the agent does not need to guess what went wrong.

## Pricing

$0.01 per successful tool invocation, billed via Stripe metered billing against the Customer ID you pass as `api_key_id`. Failed calls are not billed. Anonymous calls (no `api_key_id`) are not billed.

## Operational Notes

The server is structured to keep the repair core dependency-free, in case we port to a Worker later. Runs on Starlette/uvicorn. Repair logic has zero heavy dependencies. Schema validation imports `jsonschema` lazily, so workflows that do not use schemas pay no import cost. Billing and persistence failures are always caught and logged — a downed Supabase or a Stripe hiccup will never take down a tool response. The tool either repairs your JSON or tells the agent exactly how to fix it, and nothing between those two states will crash a session.

## License

MIT.

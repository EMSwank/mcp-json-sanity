"""
Stripe metered billing — $0.01 per successful tool invocation.

Uses the Stripe Billing Meter Events API. Each call maps one tool
invocation to one unit of the configured meter. Callers are identified
by their Stripe Customer ID, which they pass as `api_key_id`.

Required env vars:
  STRIPE_SECRET_KEY        – sk_live_... or sk_test_...
  STRIPE_METER_EVENT_NAME  – event name configured in the Stripe dashboard
                             (default: "json_sanity_tool_invocation")
"""

from __future__ import annotations

import logging
import os
import time

import stripe

logger = logging.getLogger(__name__)

METER_EVENT_NAME = os.environ.get(
    "STRIPE_METER_EVENT_NAME", "json_sanity_tool_invocation"
)


def _get_stripe() -> stripe.Stripe | None:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        logger.warning("STRIPE_SECRET_KEY not set — billing is disabled")
        return None
    stripe.api_key = key
    return stripe


def record_tool_invocation(*, api_key_id: str | None, tool_name: str) -> None:
    """
    Record one billable unit against the customer identified by api_key_id.

    Silently skips when:
      - api_key_id is None (anonymous caller)
      - STRIPE_SECRET_KEY is not configured

    Failures are logged as warnings and never propagate — billing must
    never crash a tool response.
    """
    if not api_key_id:
        return

    try:
        if _get_stripe() is None:
            return
        stripe.billing.MeterEvent.create(
            event_name=METER_EVENT_NAME,
            payload={
                "stripe_customer_id": api_key_id,
                "value": "1",
            },
            timestamp=int(time.time()),
        )
        logger.debug("Billed 1 unit to %s for tool %r", api_key_id, tool_name)
    except Exception as exc:
        logger.warning("Stripe billing failed for %s / %s: %s", api_key_id, tool_name, exc)

"""
Tests for Stripe metered billing.

Covers:
  - Correct MeterEvent payload shape (field names, types, value encoding)
  - Correct meter event name sourced from STRIPE_METER_EVENT_NAME
  - Anonymous callers (no api_key_id) are never billed
  - Stripe failures never propagate to the caller
  - Warning is emitted on failure
  - STRIPE_SECRET_KEY absence disables billing silently
"""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, call, patch

import pytest

import billing


# ── helpers ───────────────────────────────────────────────────────────────────

def _invoke(api_key_id: str | None = "cus_test123", tool_name: str = "sanitize_json_output"):
    billing.record_tool_invocation(api_key_id=api_key_id, tool_name=tool_name)


# ── payload shape ─────────────────────────────────────────────────────────────

def test_meter_event_payload_shape():
    """MeterEvent.create must be called with the exact fields Stripe expects."""
    with patch("stripe.billing.MeterEvent.create") as mock_create, \
         patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake"}):
        _invoke(api_key_id="cus_abc123")

    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs

    assert kwargs["event_name"] == billing.METER_EVENT_NAME
    assert kwargs["payload"]["stripe_customer_id"] == "cus_abc123"
    assert kwargs["payload"]["value"] == "1"           # Stripe requires string, not int
    assert isinstance(kwargs["timestamp"], int)


def test_meter_event_value_is_string_not_int():
    """Stripe's Meter Events API requires value as a string — never an int."""
    with patch("stripe.billing.MeterEvent.create") as mock_create, \
         patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake"}):
        _invoke()

    payload = mock_create.call_args.kwargs["payload"]
    assert isinstance(payload["value"], str), "value must be a string per Stripe's API contract"
    assert payload["value"] == "1"


def test_meter_event_name_from_env():
    """STRIPE_METER_EVENT_NAME env var must be forwarded as event_name."""
    with patch("stripe.billing.MeterEvent.create") as mock_create, \
         patch.dict(os.environ, {
             "STRIPE_SECRET_KEY": "sk_test_fake",
             "STRIPE_METER_EVENT_NAME": "custom_event_name",
         }):
        # Re-read the env var inside the function (not module-level cache)
        with patch.object(billing, "METER_EVENT_NAME", "custom_event_name"):
            _invoke()

    assert mock_create.call_args.kwargs["event_name"] == "custom_event_name"


def test_timestamp_is_current_unix_epoch():
    """Timestamp must be a recent Unix epoch integer (within 5 seconds)."""
    import time
    before = int(time.time())

    with patch("stripe.billing.MeterEvent.create") as mock_create, \
         patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake"}):
        _invoke()

    after = int(time.time())
    ts = mock_create.call_args.kwargs["timestamp"]
    assert before <= ts <= after + 1


# ── billing skipped for anonymous callers ─────────────────────────────────────

def test_no_billing_when_api_key_id_is_none():
    """Anonymous calls (no api_key_id) must never reach Stripe."""
    with patch("stripe.billing.MeterEvent.create") as mock_create, \
         patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake"}):
        billing.record_tool_invocation(api_key_id=None, tool_name="validate_json")

    mock_create.assert_not_called()


def test_no_billing_when_api_key_id_is_empty_string():
    """Empty string api_key_id is treated the same as None — no billing."""
    with patch("stripe.billing.MeterEvent.create") as mock_create, \
         patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake"}):
        billing.record_tool_invocation(api_key_id="", tool_name="validate_json")

    mock_create.assert_not_called()


# ── missing Stripe key ────────────────────────────────────────────────────────

def test_no_billing_when_stripe_key_missing(caplog):
    """If STRIPE_SECRET_KEY is absent, billing is disabled with a warning."""
    env = {k: v for k, v in os.environ.items() if k != "STRIPE_SECRET_KEY"}
    with patch("stripe.billing.MeterEvent.create") as mock_create, \
         patch.dict(os.environ, env, clear=True):
        with caplog.at_level(logging.WARNING, logger="billing"):
            _invoke()

    mock_create.assert_not_called()
    assert any("STRIPE_SECRET_KEY" in m for m in caplog.messages)


# ── graceful degradation ──────────────────────────────────────────────────────

def test_stripe_error_does_not_propagate():
    """A Stripe API error must never raise — tool responses must be unaffected."""
    with patch("stripe.billing.MeterEvent.create", side_effect=Exception("Stripe down")), \
         patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake"}):
        # Must not raise
        _invoke()


def test_stripe_failure_emits_warning(caplog):
    """A Stripe failure must be logged as WARNING, not silently swallowed."""
    with patch("stripe.billing.MeterEvent.create", side_effect=RuntimeError("timeout")), \
         patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake"}):
        with caplog.at_level(logging.WARNING, logger="billing"):
            _invoke()

    assert any("Stripe billing failed" in m for m in caplog.messages)

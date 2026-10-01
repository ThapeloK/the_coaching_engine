"""
tracing.py
==========
Optional export of agent runs to Langfuse.

Off by default. With no keys set every function here is a no-op and the API
behaves exactly as it does without this file, which is the only acceptable
shape for observability added three days before a submission: it must not be
able to break the thing it is observing.

Why Langfuse when we already built the glass box: they answer different
questions. /glassbox shows ONE run in full, live, to convince a person in the
room that the reasoning is code. Langfuse shows EVERY run over time, which is
what tells us the corpus has a gap.

The number worth watching is the abstention rate. A rising one is the earliest
signal that the SOP corpus no longer covers what staff are actually hitting,
and it is invisible in any single run.

Nothing here is on the request path: export happens after the response is
built, failures are swallowed, and there is no network call the user waits on.
"""

from __future__ import annotations

import os
from typing import Any

LANGFUSE_PUBLIC = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET = os.environ.get("LANGFUSE_SECRET_KEY", "")
# Langfuse's own setup snippet calls this LANGFUSE_BASE_URL while the SDK
# reads LANGFUSE_HOST. Accept either rather than let a copy-paste from
# their dashboard silently point at the default.
LANGFUSE_HOST = (os.environ.get("LANGFUSE_HOST")
                 or os.environ.get("LANGFUSE_BASE_URL")
                 or "https://cloud.langfuse.com")

_client: Any = None
_disabled = False


def enabled() -> bool:
    return bool(LANGFUSE_PUBLIC and LANGFUSE_SECRET) and not _disabled


def _client_or_none():
    """Import lazily. langfuse is an optional dependency and the service must
    start without it installed."""
    global _client, _disabled
    if _client is not None or _disabled or not enabled():
        return _client
    try:
        from langfuse import Langfuse                         # noqa: PLC0415
        _client = Langfuse(public_key=LANGFUSE_PUBLIC,
                           secret_key=LANGFUSE_SECRET,
                           host=LANGFUSE_HOST)
    except Exception:                                         # noqa: BLE001
        # Missing package, bad keys, unreachable host. Any of them means we
        # carry on without tracing rather than fail a coaching run.
        _disabled = True
        _client = None
    return _client


def export_run(*, staff_id: str, result: dict, trace: dict | None) -> None:
    """Record one agent run. Never raises.

    Written against the langfuse 4.x API: start_observation / update / end,
    rather than the 2.x client.trace(). Worth stating because the first
    version of this called client.trace(), which does not exist in 4.x, and
    the except below swallowed the AttributeError. The product was never at
    risk and tracing never once worked, which is the precise cost of a bare
    except: it protects the caller and hides the feature.
    """
    client = _client_or_none()
    if client is None:
        return
    try:
        trace = trace or {}
        status = result.get("status", "unknown")
        fell_back = any(c.get("fell_back") for c in trace.get("calls", []))

        root = client.start_observation(
            name="coaching_run",
            as_type="agent",
            input={"staff_id": staff_id},
            output={"status": status,
                    "classification": result.get("classification"),
                    "headline": result.get("headline"),
                    "abstain_reason": result.get("abstain_reason")},
            metadata={
                # The fields worth filtering on later. Abstention rate over
                # time is the one that matters: a rising one is the earliest
                # signal that the SOP corpus no longer covers what staff hit.
                "status": status,
                "classification": result.get("classification") or "none",
                "citations": len(result.get("citations", [])),
                "repair_attempts": result.get("repair_attempts"),
                "escalation": (result.get("escalation") or {}).get("rule_id"),
                "decisions_by_code": trace.get("decisions_by_code"),
                "decisions_by_model": trace.get("decisions_by_model"),
                "total_ms": trace.get("total_ms"),
                "total_usd": trace.get("total_usd"),
                "provider_fell_back": fell_back,
            },
        )

        for call in trace.get("calls", []):
            child = root.start_observation(
                name=call.get("task", "call"),
                as_type="generation",
                model=call.get("model"),
                usage_details={"input": call.get("prompt_tokens", 0),
                               "output": call.get("completion_tokens", 0)},
                cost_details={"total": call.get("usd", 0.0)},
                metadata={"provider": call.get("provider"),
                          "ms": call.get("ms"),
                          "fell_back": call.get("fell_back", False)},
            )
            child.end()

        root.end()
        # Flush rather than rely on an atexit hook a container will not run.
        client.flush()
    except Exception:                                         # noqa: BLE001
        # Still swallowed: a tracing outage must not cost a manager their
        # recommendation. selftest() below is how we check it actually works.
        pass


def selftest() -> dict:
    """Send one trace and report what happened, exceptions included.

    export_run() is deliberately silent, so without this there is no way to
    tell a working integration from a broken one short of watching the
    dashboard. Called by check_providers.
    """
    if not enabled():
        return {"ok": False, "reason": "no keys configured"}
    client = _client_or_none()
    if client is None:
        return {"ok": False, "reason": "client could not be constructed"}
    try:
        if not client.auth_check():
            return {"ok": False, "reason": "auth_check failed; keys rejected"}
        span = client.start_observation(
            name="selftest", as_type="span",
            metadata={"source": "check_providers"})
        span.end()
        client.flush()
        return {"ok": True, "host": LANGFUSE_HOST}
    except Exception as exc:                                  # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"[:160]}


def status() -> dict:
    """Surfaced on /health so a misconfigured key is visible before a demo."""
    if not (LANGFUSE_PUBLIC and LANGFUSE_SECRET):
        return {"configured": False}
    return {"configured": True, "host": LANGFUSE_HOST,
            "connected": _client_or_none() is not None}

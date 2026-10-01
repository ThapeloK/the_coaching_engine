"""
spend.py
========
What the AI actually costs, and a cap so it cannot run away unattended.

Measured, not estimated from a pricing page. One real agent run:

    classify   gpt-4o-mini      395 in    65 out
    coach      gpt-4o          1032 in   209 out
    embed      text-embedding-3-small (negligible)

which is about **half a US cent**. Thirteen staff is six cents. A hundred demo
runs is fifty cents.

So the honest finding is that OpenAI is not the thing to ration. The scarce
resource is ElevenLabs: 10,000 characters for the LIFE of the free account,
with roughly five thousand left, and no way to buy more without a card. A
guest line is about 120 characters, so the remaining budget is forty or so
unheard lines. That is what the cache exists for and what the cap below
protects.

The daily ceiling is here for the failure nobody plans for: a loop that retries
forever at three in the morning. It is not a budgeting tool.
"""

from __future__ import annotations

import os
import threading
from datetime import date

# USD per 1,000,000 tokens. Update when the price list moves; being slightly
# stale is fine because this drives a warning, never a billing decision.
PRICES: dict[str, tuple[float, float]] = {
    #  model                      input,  output
    "gpt-4o":                    (2.50,  10.00),
    "gpt-4o-mini":               (0.15,   0.60),
    "text-embedding-3-small":    (0.02,   0.00),
    # Groq's free tier bills nothing. Recorded at zero so the trace still
    # shows the call rather than hiding work that happened.
    "qwen/qwen3.8-27b":          (0.00,   0.00),
    "whisper-large-v3-turbo":    (0.00,   0.00),
}

# A day's ceiling in USD. Generous on purpose: at half a cent per run this is
# thousands of recommendations, so it only ever fires on a runaway.
DAILY_LIMIT_USD = float(os.environ.get("CE_DAILY_USD_LIMIT", "5.00"))

_lock = threading.Lock()
_today = date.today()
_spent = 0.0
_calls = 0


class BudgetExceeded(RuntimeError):
    """Raised instead of spending past the daily ceiling."""


def cost_of(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = PRICES.get(model, (0.0, 0.0))
    return (prompt_tokens * inp + completion_tokens * out) / 1_000_000


def record(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Add one call to today's total. Returns what it cost."""
    global _today, _spent, _calls
    amount = cost_of(model, prompt_tokens, completion_tokens)
    with _lock:
        if date.today() != _today:
            _today, _spent, _calls = date.today(), 0.0, 0
        _spent += amount
        _calls += 1
    return amount


def check() -> None:
    """Raise before a call that would run past the ceiling."""
    with _lock:
        if date.today() != _today:
            return                       # a new day resets it
        if _spent >= DAILY_LIMIT_USD:
            raise BudgetExceeded(
                f"Today's AI spend has reached ${_spent:.2f}, at or over the "
                f"${DAILY_LIMIT_USD:.2f} ceiling. Raise CE_DAILY_USD_LIMIT if "
                f"this is expected; if it is not, something is looping.")


def summary() -> dict:
    """Surfaced on /health, so an unexpected number is visible before a demo."""
    with _lock:
        return {"date": _today.isoformat(),
                "usd_today": round(_spent, 4),
                "calls_today": _calls,
                "limit_usd": DAILY_LIMIT_USD,
                "headroom_usd": round(max(0.0, DAILY_LIMIT_USD - _spent), 4)}

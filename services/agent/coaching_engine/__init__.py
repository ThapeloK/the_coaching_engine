"""The Coaching Engine: deterministic core.

Everything in this package is pure logic with no model calls and no I/O.
That is deliberate. Under the project's first principle, anything that must be
identical every time, and explainable to a works council, lives in code:
thresholds, the transfer gap, calibration statistics, the cite gate and
escalation routing. Synthesis and conversation live elsewhere.

It also means this package is fast to test and needs no API keys, so anyone on
the team can run the suite offline.
"""

__version__ = "0.1.0"

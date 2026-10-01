# Coaching agent: deterministic core

Everything in `coaching_engine/` is pure logic. No model calls, no I/O, no
network. That is deliberate.

Under the project's first principle, anything that must be identical every time
and explainable to a works council lives in code: thresholds, the transfer gap,
calibration statistics, the cite gate and escalation routing. Synthesis and
conversation live elsewhere.

It also means the suite runs offline in under a second and needs no API keys,
so anyone on the team can run it.

```bash
cd services/agent
pip install -r requirements.txt
python -m pytest
```

## What is here

| Module | What it does |
|---|---|
| `transfer_gap.py` | Practice minus floor, recency-weighted, quadrant assignment, trend slope |
| `calibration.py` | Wilson score intervals, agreement states, quadratic weighted kappa |
| `cite_gate.py` | The four checks that stop an ungrounded recommendation being emitted |
| `routing.py` | First-match-wins escalation rules, each recording the rule that fired |

63 tests. They encode the product decisions, so read them as specification
rather than as coverage.

## The four things these modules exist to guarantee

**A dimension with no floor observation has no gap.** It returns
`insufficient_evidence`, not a zero that looks like agreement.

**The gate is code, not a prompt.** The model is never asked whether it was
grounded. Self-assessment of hallucination is not a control.

**Sufficiency means both streams.** A recommendation citing only the practice
transcript is roleplay feedback, which is the product we are differentiating
against. The gate rejects it.

**Every escalation records its `rule_id`.** Under Article 14 we have to be able
to explain why a case reached HR. "Rule RC-SEVERE fired because the floor mean
was 1.4 across three observations" is an explanation. "The model decided" is
not.

## Still to come in this service

The graph itself, the prompt contracts and the model routing. Specs are in
`02C-LLD-Agent-Graph` and `01B-HLD-Agent-Reasoning`. The modules above are the
pieces those nodes call.

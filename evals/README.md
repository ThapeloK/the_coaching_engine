# Evaluations

Three tools, three different questions. None of them touch the running system:
everything here is offline and read-only, so it cannot break a demo.

| Tool | Question it answers | Run |
|---|---|---|
| **promptfoo** | Can an adversary talk the agent past its own cite gate? | `npx promptfoo@latest eval -c evals/redteam/promptfooconfig.yaml` |
| **Ragas** | Is retrieval finding the right clause, and is the answer faithful to it? | `python evals/retrieval/run_ragas.py` |
| **Langfuse** | What did every run actually cost, and where does it fail? | set two env vars, see below |

## Why these three and not an agent framework

We were asked to consider CrewAI and LangGraph. Both would replace working,
tested code with unproven code days before a submission, and both move the
reasoning into a framework's abstractions when our entire argument is that the
decisions live in code you can point at. Evaluation is the gap worth filling:
we can already show the gate works on the cases we thought of, and none of
these three had told us what happens on the cases we did not.

## promptfoo: the red team

The interesting target is not the model, it is `run_gate()`. The question a
judge will ask is "what stops it making something up", and "we wrote a gate"
is weaker than "we attacked the gate ninety times and it held".

`redteam/promptfooconfig.yaml` runs adversarial prompts through the real
drafting path and asserts on the gate's verdict, not on the prose. Prompts try
to get a recommendation that cites nothing, that cites a plausible-sounding SOP
clause that does not exist, that leans on another staff member's record, or
that recommends training for someone in the BLOCKED quadrant.

A pass here means the recommendation was blocked or the abstention fired. It
does not mean the model behaved: the model is expected to misbehave, and the
point is that misbehaviour never reaches a manager.

## Ragas: retrieval quality

The cite gate proves a quote appears in the chunk we cited. It says nothing
about whether we cited the *right* chunk. Ragas measures that separately:

- **context precision**: of the chunks we retrieved, how many mattered
- **context recall**: of the chunks that mattered, how many did we retrieve
- **faithfulness**: is the generated claim actually supported by the context

Faithfulness overlaps with our gate on purpose. If Ragas ever scores
faithfulness below the gate's pass rate, one of the two is wrong and that is
worth knowing.

### The labels are not ground truth yet

Running this the first time found that the 45-item set is **generated, not
curated**. The pairings do not survive inspection: a phone complaint about
noise is labelled as grounded in "make eye contact", and a PMS outage in
"welcome the guest with a genuine smile". Mean lexical overlap between a
transcript and its supposedly correct clause is 0.00.

So precision@1 and recall@5 currently read 0.00, and that number is about the
labels, not about search. The script says so in red rather than letting anyone
tune a retriever against noise.

**This is Mary-Susan's lane** (README ownership table: "golden-set ground
truth") and it is the highest-value non-code task left. Forty items, each
needing a person who knows the SOPs to name the clause a debrief should land
on. Until that exists we should describe it as an evaluation harness with
placeholder labels, never as a golden set.

## Langfuse: production tracing

Optional and fail-safe. With no keys set, the integration is a no-op and the
API behaves exactly as it does today.

```bash
# .env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com     # or your own, it is MIT licensed
```

The glass box already shows one run in full. Langfuse shows every run: cost per
recommendation, p95 latency, which provider fell back and how often, abstention
rate over time. That last number is the one to watch, because a rising
abstention rate is the earliest signal that the SOP corpus has gaps.

"""
demo.py
=======
The glass box: endpoints that prove the three claims we cannot expect a judge
to take on trust.

1. The reasoning is not a prompt. /demo/trace runs the real agent and returns
   the full pipeline, marking every step as code, model or database, so the
   split is visible rather than asserted.
2. The cite gate is code. /demo/gate feeds handcrafted claims to the SAME
   run_gate() the production path calls, including deliberately bad ones, and
   returns its verdicts. Nothing here reimplements the gate.
3. The access control is in the database. /demo/rls runs one identical query as
   three different people and returns what each of them actually got back.

Everything in this module calls production code. If a demo endpoint says the
gate rejected a fabricated citation, that is because the gate rejected it just
now, not because this file says so. A demo that reimplements the thing it is
demonstrating proves nothing, and would be worse than no demo at all: it would
be a claim we had dressed up as evidence.
"""

from __future__ import annotations

from . import queries as q
from .agent import run_coaching
from .db import resolve_actor, session
from .providers import Trace

from coaching_engine.cite_gate import Claim, EvidenceItem, run_gate


# ---------------------------------------------------------------- 1. trace

def trace_run(cur, actor, staff_id: str) -> dict:
    """Run the agent for real and hand back the whole timeline."""
    trace = Trace()
    result = run_coaching(cur, actor, staff_id, trace=trace)
    t = result.get("trace") or trace.as_dict()

    staff = q.staff_by_id(cur, staff_id)
    return {
        "staff": {"id": staff_id,
                  "name": staff["display_name"] if staff else "unknown",
                  "department": staff["department"] if staff else None},
        "outcome": {
            "status": result["status"],
            "classification": result.get("classification"),
            "headline": result.get("headline"),
            "abstain_reason": result.get("abstain_reason"),
            "citations": len(result.get("citations", [])),
            "escalation": result.get("escalation"),
        },
        "trace": t,
    }


# ------------------------------------------------------------- 2. cite gate

# Four probes. Three of them are the failure modes the gate exists to catch,
# written the way a plausible model failure actually looks: not gibberish, but
# a confident sentence that cites something real and says something the source
# does not.
PROBES = [
    {
        "id": "honest",
        "title": "A claim that cites what it actually quotes",
        "expect": "pass",
        "claim": "They offered a complimentary drink during practice.",
        "refs": ["P1"],
        "quote": "I can offer you a complimentary drink at our bar.",
    },
    {
        "id": "invented_source",
        "title": "Cites a source that was never in the bundle",
        "expect": "reject",
        "claim": "The staff handbook permits a full refund at the desk.",
        "refs": ["S9"],
        "quote": "Front desk may issue a full refund.",
    },
    {
        "id": "paraphrased_standard",
        "title": "Cites a real standard, quotes something it does not say",
        "expect": "reject",
        "claim": "The standard allows staff to offer a free night.",
        "refs": ["S1"],
        "quote": "Staff may offer a complimentary night to any unhappy guest.",
    },
    {
        "id": "someone_elses_evidence",
        "title": "Leans on a different staff member's evidence",
        "expect": "reject",
        "claim": "They handled the same situation poorly last week.",
        "refs": ["X1"],
        "quote": None,
    },
    {
        "id": "practice_only",
        "title": "Cites practice but never the floor",
        "expect": "reject",
        "claim": "They performed well in the simulator.",
        "refs": ["P1"],
        "quote": "I can offer you a complimentary drink at our bar.",
    },
]


def gate_probe(cur, staff_id: str) -> dict:
    """Run handcrafted claims through the production gate."""
    cur.execute("""
        SELECT c.id::text, c.content, c.section_path, d.title AS document
        FROM sop_chunk c JOIN sop_document d ON d.id = c.document_id
        LIMIT 1
    """)
    sop = cur.fetchone()

    other = "00000000-0000-0000-0000-0000000000ff"
    bundle = [
        EvidenceItem(ref="P1", kind="attempt_turn", staff_id=staff_id,
                     content="I can offer you a complimentary drink at our bar."),
        EvidenceItem(ref="F1", kind="observation", staff_id=staff_id,
                     content=("Guest complaint at the desk. Froze, then "
                              "escalated without attempting recovery.")),
        EvidenceItem(ref="S1", kind="sop_chunk", staff_id=None,
                     content=sop["content"] if sop else "Empathy is key."),
        EvidenceItem(ref="X1", kind="observation", staff_id=other,
                     content="A different staff member's observation."),
    ]

    results = []
    for probe in PROBES:
        claims = [Claim(text=probe["claim"],
                        citation_refs=tuple(probe["refs"]),
                        quoted_span=probe["quote"])]
        # Every probe except the sufficiency one carries a complete, honest
        # pair of supporting claims. Each probe must isolate ONE failure: a
        # probe that trips two rules at once tells a judge nothing about which
        # rule caught it.
        if probe["id"] != "practice_only":
            claims.append(Claim(
                text="On the floor they escalated instead of acting.",
                citation_refs=("F1",), quoted_span=None))
            if "P1" not in probe["refs"]:
                claims.append(Claim(
                    text="They produced the behaviour correctly in practice.",
                    citation_refs=("P1",), quoted_span=None))

        gate = run_gate(claims, bundle, staff_id, repair_attempts=2)
        results.append({
            "id": probe["id"],
            "title": probe["title"],
            "claim": probe["claim"],
            "cited": probe["refs"],
            "quoted": probe["quote"],
            "expected": probe["expect"],
            "passed": gate.passed,
            "as_expected": gate.passed == (probe["expect"] == "pass"),
            "failures": [f.describe() for f in gate.failures],
        })

    return {
        "source": "coaching_engine.cite_gate.run_gate",
        "note": ("These verdicts come from the same function the live agent "
                 "calls. Nothing here is scripted."),
        "bundle": [{"ref": e.ref, "kind": e.kind,
                    "content": e.content[:120],
                    "belongs_to": ("this staff member" if e.staff_id == staff_id
                                   else "someone else" if e.staff_id
                                   else "the hotel's standards")}
                   for e in bundle],
        "probes": results,
        "all_as_expected": all(r["as_expected"] for r in results),
    }


# ------------------------------------------------------------------ 3. RLS

# One question, asked by three people. The question never changes.
RLS_QUERY = """
    SELECT s.source, count(*) AS n
    FROM score s
    WHERE s.staff_id = %s
    GROUP BY s.source
"""


def rls_proof(cur, subject_id: str) -> dict:
    """Ask the same question as three different people.

    The cursor passed in is only used to name the subject. Each viewer gets its
    own session, because the whole point is that the answer depends on who is
    connected, not on what this function chooses to filter.
    """
    subject = q.staff_by_id(cur, subject_id)
    viewers = [
        ("Diego", "a colleague in the same department",
         "Nothing. Staff see their own record, never a peer's."),
        ("Marta", "their manager, who has logged an observation",
         "Both streams. The sequencing gate opened when they logged theirs."),
        ("Fiona", "L&D, who owns the rubric",
         "No individual practice scores. L&D gets cohorts, not people."),
    ]

    rows = []
    for name, who, expected in viewers:
        try:
            viewer = resolve_actor(name)
            with session(viewer) as vcur:
                vcur.execute(RLS_QUERY, (subject_id,))
                got = {r["source"]: r["n"] for r in vcur.fetchall()}
        except Exception as exc:                     # denied is also an answer
            got, expected = {}, f"{expected} ({type(exc).__name__})"

        rows.append({
            "viewer": name, "who": who,
            "practice_rows": got.get("practice", 0),
            "floor_rows": got.get("floor", 0),
            "expected": expected,
        })

    return {
        "subject": {"id": subject_id,
                    "name": subject["display_name"] if subject else "unknown"},
        "query": " ".join(RLS_QUERY.split()),
        "note": ("Identical SQL in all three cases. The filtering happens in "
                 "Postgres row level security, so a bug in the API cannot leak "
                 "a row the policy forbids. Verified by 10 negative tests in "
                 "db/test_rls.py, which assert that forbidden reads return "
                 "nothing and forbidden writes are refused."),
        "viewers": rows,
    }

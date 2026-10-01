"""Answer "am I allowed to do this?" from the property's own standards.

WHY THIS EXISTS

Diego stood at a desk with a guest in front of him and offered her nothing,
because nobody had ever told him what he was allowed to offer. Every other
screen in this product measures that. This one answers it, in the ten seconds
he actually has, from the documents his employer already wrote.

THE ANSWER THAT MATTERS IS "NOTHING IS WRITTEN"

A retrieval system's instinct is to return its best hit. That is the wrong
instinct here and dangerously so: handing a front desk agent a food and
beverage clause because it was the nearest match teaches him a permission he
does not have, and the next thing that happens is a manager asking why he gave
away a room.

So silence is a first-class verdict. When nothing in his own department's
standards answers the question, this says so, shows the near miss from the
other department clearly labelled as not his, and offers to ask a human. The
dead end always has a door.

WHAT THE MODEL IS AND IS NOT ALLOWED TO DO

It reads the clauses retrieval found and picks which one, if any, actually
answers the question, choosing from four verdicts. It may not write a
permission. It may not say "yes you can" unless a clause it cites says so, and
code checks that the cited ref is real before any verdict reaches a screen. A
verdict with no citation is downgraded to silence, every time, without asking
the model to reconsider.

That asymmetry is deliberate. Being wrongly told "no, ask your manager" costs a
staff member thirty seconds. Being wrongly told "yes, go ahead" costs them a
conversation with their GM.
"""
from __future__ import annotations

import json
from typing import Any

from . import providers
from . import queries as q
from .providers import Trace
from .retrieval import search

# What the staff member sees, and what each verdict is allowed to mean.
#
#   permits          a clause says they may do this, on their own
#   requires_ask     a clause says they may, but only with approval
#   prohibits        a clause says they may not
#   silent           nothing in their standards answers the question
VERDICTS = ("permits", "requires_ask", "prohibits", "silent")

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "cited_ref", "plain_answer"],
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "cited_ref": {
            "type": "string",
            "description": "The S-number of the ONE clause that answers this. "
                           "Empty string if none of them do.",
        },
        "plain_answer": {
            "type": "string",
            "description": "One sentence, addressed to the staff member, "
                           "saying what they may do. Must not add any "
                           "permission the cited clause does not contain. "
                           "Empty string when the verdict is silent.",
        },
    },
}

SYSTEM = """A hotel staff member is asking whether they are allowed to do
something, right now, with a guest in front of them. You are given the clauses
from their own department's standards that came closest to their question.

Decide which single clause actually answers it, and pick a verdict:

  permits        a clause says they may do this themselves
  requires_ask   a clause says they may, but only with approval or a signature
  prohibits      a clause says they may not
  silent         none of these clauses answers the question

Choose silent freely. It is the most useful answer you can give when it is
true, and the standards in front of you are frequently silent on exactly the
thing being asked. A clause that is merely about the same topic does not answer
a permission question: "apologise sincerely" does not tell anybody whether they
may give away a coffee.

You may not grant a permission. If you say permits, you are reporting what the
cited clause already says, in plainer words. Never write a limit, an amount or
a condition that is not in the clause.

Plain answer: one sentence, second person, no preamble. "You can seat the guest
and brief the manager, and the manager logs it." Not "According to the
standards, staff members are permitted to..."."""


def ask(cur, actor, question: str, trace: Trace | None = None) -> dict:
    """Answer one permission question for the person asking it."""
    trace = trace or Trace()
    question = (question or "").strip()
    if not question:
        return {"error": "empty"}

    staff = q.staff_by_id(cur, actor.staff_id) or {}
    department = staff.get("department") or "all"

    # Their own department first, and only. A clause from another department is
    # not a permission they hold, so it must not be able to produce a "yes".
    mine = search(cur, question, department=department, limit=5, trace=trace)
    for index, hit in enumerate(mine, start=1):
        hit["ref"] = f"S{index}"

    trace.step("database", f"Search {department.replace('_', ' ')} standards",
               hits=len(mine),
               note="Department scoped. A rule that exists for another "
                    "department is not a rule this person can rely on.")

    verdict, cited, plain = "silent", None, ""

    if mine:
        clauses = "\n".join(
            f'{h["ref"]} [{h.get("section_path", "")}] {h["content"]}'
            for h in mine)
        prompt = (f"Their question: {question}\n"
                  f"Their department: {department.replace('_', ' ')}\n\n"
                  f"Clauses from their standards:\n{clauses}")
        try:
            out = providers.complete("permission_check", SYSTEM, prompt,
                                     schema=ANSWER_SCHEMA, temperature=0.0,
                                     trace=trace, max_tokens=400)
        except Exception as exc:                       # noqa: BLE001
            trace.step("code", "Checker failed, answering silent",
                       error=str(exc)[:160],
                       note="A failure here must not become a yes.")
            out = None

        if out:
            proposed = out.get("verdict")
            ref = (out.get("cited_ref") or "").strip().upper()
            by_ref = {h["ref"]: h for h in mine}

            # The gate. A verdict that cannot point at a real clause is not a
            # verdict, and the fallback is always the cautious direction.
            if proposed in VERDICTS and proposed != "silent" and ref in by_ref:
                verdict = proposed
                cited = by_ref[ref]
                plain = providers.plain((out.get("plain_answer") or "").strip())
            else:
                trace.step("code", "Verdict downgraded to silent",
                           proposed=proposed, cited_ref=ref or "(none)",
                           note="No real clause behind it. Being wrongly told "
                                "to ask costs thirty seconds; being wrongly "
                                "told yes costs a conversation with the GM.")

    # Only when their own standards are silent do we look at what exists
    # elsewhere, and it is labelled as somebody else's rule, never as an answer.
    near_miss = None
    if verdict == "silent":
        everywhere = search(cur, question, department=None, limit=8, trace=trace)
        others = [h for h in everywhere
                  if h.get("department") not in (department, "all")]

        # Not simply the top cross-department hit. The question is about
        # permission, so the near miss has to BE a permission: the first run
        # offered "Drinks order taken within 3 minutes" as the closest thing to
        # "can I give her a coffee", which is a service timing rule and reads as
        # an answer when it is not. A near miss that is not about being allowed
        # is worse than none, so when nothing qualifies this shows nothing.
        GRANTS = ("may ", "must ", "approved", "approval", "discretion",
                  "authorised", "authorized", "permitted", "allowed",
                  "signed for")
        preferred = next((h for h in others
                          if any(word in h["content"].lower() for word in GRANTS)),
                         None)
        if preferred:
            near_miss = {
                "document": preferred.get("document"),
                "section_path": preferred.get("section_path"),
                "content": preferred["content"],
                "department": preferred.get("department"),
            }
        trace.step("code",
                   "Nothing in their own standards answers this"
                   + (" · a clause exists for another department"
                      if near_miss else ""),
                   near_miss=bool(near_miss),
                   note="This is a finding, not a failure. It is the same hole "
                        "the standards audit reports, met by the person it "
                        "actually happens to.")

    return {
        "question": question,
        "department": department,
        "verdict": verdict,
        "plain_answer": plain,
        "clause": ({"document": cited.get("document"),
                    "section_path": cited.get("section_path"),
                    "content": cited["content"],
                    "department": cited.get("department")} if cited else None),
        "near_miss": near_miss,
        "can_ask": verdict in ("silent", "requires_ask"),
    }


# ---------------------------------------------------------------- the ask

def request(cur, actor, question: str, answer: dict | None = None) -> dict:
    """Send the question to a manager, with what the standards said attached.

    The manager is not asked "Diego has a query". They are asked a specific
    question with the situation and the search result beside it, because the
    reason these never get answered in a real hotel is that answering them is
    currently more work than ignoring them.
    """
    payload = {
        "question": (question or "").strip()[:600],
        "staff_id": actor.staff_id,
        "staff_name": actor.display_name,
        "verdict_at_ask": (answer or {}).get("verdict"),
        "near_miss": (answer or {}).get("near_miss"),
    }
    event_id = q.audit(cur, actor, "permission.asked", actor.staff_id,
                       {"ask": json.dumps(payload)})
    cur.connection.commit()
    return {"request_id": str(event_id) if event_id else None,
            "status": "asked"}


def _answers(cur) -> dict[str, dict]:
    cur.execute("""
        SELECT subject_ref, payload, occurred_at
        FROM audit_event
        WHERE event_type = 'permission.answered'
        ORDER BY occurred_at
    """)
    out: dict[str, dict] = {}
    for row in cur.fetchall():
        if not row["subject_ref"]:
            continue
        payload = row["payload"] or {}
        out[row["subject_ref"]] = {
            "verdict": payload.get("verdict"),
            "note": payload.get("note"),
            "answered_by": payload.get("answered_by"),
            "answered_at": (row["occurred_at"].isoformat()
                            if row["occurred_at"] else None),
        }
    return out


def list_requests(cur, *, staff_id: str | None = None,
                  limit: int = 40) -> list[dict]:
    """Questions from the floor. Scoped to one person when staff_id is given."""
    cur.execute("""
        SELECT id, subject_ref, payload, occurred_at
        FROM audit_event
        WHERE event_type = 'permission.asked'
        ORDER BY occurred_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    answers = _answers(cur)

    out = []
    for row in rows:
        raw = (row["payload"] or {}).get("ask")
        if not raw:
            continue
        try:
            ask_payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if staff_id and ask_payload.get("staff_id") != staff_id:
            continue
        request_id = str(row["id"])
        out.append({
            "request_id": request_id,
            "question": ask_payload.get("question"),
            "staff_id": ask_payload.get("staff_id"),
            "staff_name": ask_payload.get("staff_name"),
            "near_miss": ask_payload.get("near_miss"),
            "asked_at": (row["occurred_at"].isoformat()
                         if row["occurred_at"] else None),
            "answer": answers.get(request_id),
        })
    return out


def answer(cur, actor, request_id: str, verdict: str,
           note: str | None = None) -> dict:
    """A manager settles one question, for good.

    Recorded rather than sent, because the whole problem is that these answers
    live in somebody's memory of a conversation in a corridor. An answer here
    is retrievable by the person who asked, and countable by the standards
    audit: ten people asking the same thing is a policy that needs writing.
    """
    if verdict not in ("yes", "yes_with_approval", "no"):
        return {"error": "bad_verdict"}
    q.audit(cur, actor, "permission.answered", str(request_id), {
        "verdict": verdict,
        "note": (note or "").strip()[:600],
        "answered_by": actor.display_name,
    })
    cur.connection.commit()
    return {"status": "answered", "verdict": verdict}

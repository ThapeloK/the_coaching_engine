"""Write the next practice scenario for one person, from their measured gap.

WHY THIS EXISTS

The loop has been open since the beginning. The transfer gap tells you exactly
what is wrong with one person on one dimension, and then the practice library
offers them the same five seeded scenarios as everybody else. `scenario` has an
`origin` column and a `grounded_chunk_ids` column that have been waiting for
this, and the product has been diagnosing without prescribing.

So: read the gap, write the scenario that answers it, ground it in the hotel's
own standards, and hold it until a manager says yes.

THE IDEA THAT MAKES THIS WORTH BUILDING

The quadrant decides what the scenario is FOR, and that decision is made in
code before any model is called:

  skill_gap    weak in practice and weak on the floor. They have not learned it
               yet. Write a teaching scenario: one dimension, a guest who gives
               them room, a situation they can get right.

  blocked      strong in practice, weak on the floor. They KNOW it. More
               training is the wrong answer and this product exists to say so.
               Write a BOUNDARY scenario instead: a guest who asks for
               something sitting exactly on the edge of what the staff member
               is allowed to give. The point is not to teach them the
               behaviour. It is to find out, in their own words, where they
               believe their authority ends, and hand that transcript to a
               manager who can go and fix the actual rule.

  recalibrate  better on the floor than in practice. The measurement is what is
               wrong, not the person. Write a scenario that looks like their
               real shift: interruptions, time pressure, a queue.

  competent    good at both. Stretch them, or leave them alone.

A model is never asked "should this person be trained". It is asked to write a
scene of a type that code has already chosen. That is the same division of
labour as the coaching agent, and it is the only reason this is allowed to
generate content aimed at a named employee at all.

WHAT IT WILL NOT DO

It never states what the hotel permits. A guest in a generated scene may ask
for anything; the scene may not assert that a free night is available, because
the moment a practice scenario invents policy, staff learn the invention and
the transfer gap starts measuring against fiction.

It never reaches a staff member without a manager publishing it. A proposal is
not a scenario: it lives in the audit log until somebody with a name approves
it, and only then does a row appear in `scenario`.
"""
from __future__ import annotations

import json
from typing import Any

from . import providers
from . import queries as q
from . import standards_audit
from .providers import Trace
from .retrieval import search

STRONG = 3.5  # mirrors coaching_engine.transfer_gap, for wording only

# What a scenario is for, per quadrant. Code picks the row; the model writes
# the scene. The briefs are deliberately different documents, not one prompt
# with a variable in it, because a boundary scenario and a teaching scenario
# are different kinds of writing and blending them produces neither.
JOBS: dict[str, dict[str, str]] = {
    "skill_gap": {
        "label": "Teach it",
        "why": ("Weak in practice and weak on the floor. They have not learned "
                "this yet, and that is what a scenario is actually for."),
        "brief": ("Write a scenario this person can get RIGHT. One dimension. "
                  "A guest who is annoyed but reasonable, who gives them room "
                  "to recover, and who responds to a good answer. The purpose "
                  "is a successful repetition, not a test."),
    },
    "blocked": {
        "label": "Find the boundary",
        "why": ("Strong in practice, weak on the floor. They already know how "
                "to do this, so more training is the wrong answer. This "
                "scenario is not here to teach them."),
        "brief": ("Write a BOUNDARY scenario. The guest asks for something "
                  "that sits exactly on the edge of what a person in this role "
                  "can offer without asking permission: not obviously fine, "
                  "not obviously outrageous. The guest should politely press "
                  "once. The purpose is to surface, in the staff member's own "
                  "words, where they believe their authority ends. Do not "
                  "write a scene with an obviously correct answer."),
    },
    "recalibrate": {
        "label": "Match the real shift",
        "why": ("Better on the floor than in practice, which is a signal about "
                "our measurement rather than about them. The practice "
                "conditions are too clean."),
        "brief": ("Write a scenario that looks like a real shift rather than a "
                  "quiet room. Something interrupts: a phone, a queue, a second "
                  "guest, a handover mid-conversation. The guest is ordinary. "
                  "The difficulty is the conditions, not the person."),
    },
    "competent": {
        "label": "Stretch",
        "why": ("Strong in both streams. There is nothing to fix, so the only "
                "honest reason to write a scenario is to make it harder."),
        "brief": ("Write a harder variant: a guest whose first complaint hides "
                  "a second one, or who is calm and completely immovable. "
                  "Keep it realistic. Do not manufacture drama."),
    },
}

SCENARIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "situation", "opening_line", "guest_persona",
                 "rationale", "cited_refs"],
    "properties": {
        "title": {"type": "string",
                  "description": "Six words at most, as an operations person "
                                 "would name a shift incident."},
        "situation": {"type": "string",
                      "description": "Two or three sentences of setup, written "
                                     "to the staff member: where they are, who "
                                     "is in front of them, what has happened."},
        "opening_line": {"type": "string",
                         "description": "The first thing the guest says, in "
                                        "their own voice. One or two sentences."},
        "guest_persona": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "mood", "wants", "concedes_when"],
            "properties": {
                "name": {"type": "string"},
                "mood": {"type": "string",
                         "enum": ["neutral", "annoyed", "upset", "calm"]},
                "wants": {"type": "string",
                          "description": "What this guest is actually after, "
                                         "which may not be what they first ask "
                                         "for."},
                "concedes_when": {"type": "string",
                                  "description": "What the staff member has to "
                                                 "do for this guest to soften."},
            },
        },
        "rationale": {"type": "string",
                      "description": "Two sentences to the MANAGER explaining "
                                     "why this scene answers this person's gap."},
        "cited_refs": {
            "type": "array",
            "description": "The S-numbers of the standards this scenario puts "
                           "under pressure. At least one.",
            "items": {"type": "string"},
        },
    },
}

SYSTEM = """You write practice scenarios for hotel front-line staff.

You are given one person's measured gap, the job this scenario has to do, and
the property's own written standards. Write a scene that does that job.

Rules that are not stylistic:

Never state what the hotel permits. The guest may ask for anything. You may not
write that a refund is available, that a free night is policy, or that staff may
offer a particular thing, because a staff member will learn whatever the
scenario implies and we will then be measuring them against something we made
up. If the scene needs a limit to exist, have the guest ask and leave the answer
to the person practising.

Never write the correct answer into the situation. You are setting a problem.

Cite the standards the scene puts under pressure by their S-number. If none of
the standards given are relevant, cite the closest one anyway and say so in the
rationale: a scenario testing a rule the hotel has not written down is a finding
in itself, not a failure.

Write like somebody who has worked a shift. Plain, short, no adjectives doing
work that verbs should do."""


def _corpus_for(cur, dimension: str, department: str,
                trace: Trace | None) -> list[dict]:
    """The standards a scene on this dimension would put under pressure.

    Retrieval rather than the whole corpus: a scenario is about one situation,
    and handing the writer sixty unrelated clauses produces a scene that gestures
    at all of them. The department scoping is the same one the coaching agent
    uses, so a front office scenario is grounded in front office rules.
    """
    queries = {
        "service_recovery": "guest complaint resolution escalation what staff may offer",
        "empathy": "listen to the guest acknowledge how they feel",
        "composure": "stay calm under pressure professional conduct with guests",
        "communication": "explain inform the guest greet and brief",
        "anticipation": "anticipate guest needs before being asked",
    }
    hits = search(cur, queries.get(dimension, dimension.replace("_", " ")),
                  department=department, limit=6, trace=trace)
    for index, hit in enumerate(hits, start=1):
        hit["ref"] = f"S{index}"
    return hits


def _audit_context(cur, department: str) -> list[dict]:
    """Open findings from the standards audit that touch this department.

    This is the part that makes the two features worth more together than
    apart. If the audit has already established that nobody has written down
    what a front desk agent may offer, a boundary scenario for a front desk
    agent is not a guess: it is rehearsing a hole we can name.
    """
    report = standards_audit.latest_audit(cur)
    if not report:
        return []
    # A scope gap about front office almost always cites the FOOD AND
    # BEVERAGE clause, because the whole finding is that front office has
    # nothing to cite. Matching on the citation's department therefore misses
    # exactly the findings that matter most, which it did on the first run.
    # So: match the department of the evidence OR the department named in the
    # finding's own words.
    spoken = department.replace("_", " ").replace("f and b", "food")
    relevant = []
    for finding in report.get("findings", []):
        if finding.get("kind") not in ("authority_gap", "scope_gap"):
            continue
        departments = {c.get("department") for c in finding.get("citations", [])}
        words = " ".join([finding.get("title", ""),
                          finding.get("explanation", ""),
                          finding.get("missing_sentence", "")]).lower()
        if (department in departments or "all" in departments
                or not departments or spoken in words):
            relevant.append({"title": finding["title"],
                             "kind": finding["kind"],
                             "missing_sentence": finding.get("missing_sentence", "")})
    return relevant[:3]


def _tidy(draft: dict) -> dict:
    """Strip the quote marks a model wraps dialogue in.

    The UI renders the opening line inside its own quotes, so a model that
    helpfully added a pair produces “"I can't relax in my room"”. Cosmetic,
    and cosmetic things are what make generated content look generated.
    """
    for field in ("title", "opening_line", "situation", "rationale"):
        value = providers.plain((draft.get(field) or "").strip())
        for pair in (('"', '"'), ("“", "”"), ("'", "'")):
            if len(value) > 1 and value.startswith(pair[0]) and value.endswith(pair[1]):
                value = value[1:-1].strip()
        draft[field] = value

    persona = draft.get("guest_persona") or {}
    for field in ("wants", "concedes_when"):
        if persona.get(field):
            persona[field] = providers.plain(persona[field])
    return draft


def _verify(draft: dict, corpus: list[dict]) -> list[str]:
    """Reasons this draft cannot be shown to anybody. Empty means it is fine.

    Lighter than the cite gate, and deliberately so: a scenario is fiction, and
    demanding that invented dialogue quote a document would be nonsense. What
    it must do is point at real standards and avoid asserting policy, which are
    both checkable in code.
    """
    problems: list[str] = []
    by_ref = {row["ref"]: row for row in corpus}

    refs = [r.strip().upper() for r in draft.get("cited_refs", []) if r]
    if not refs:
        problems.append("cites no standard at all")
    unknown = [r for r in refs if r not in by_ref]
    if unknown:
        problems.append(f"cites {', '.join(unknown)}, which was not retrieved")

    for field in ("title", "situation", "opening_line"):
        if not (draft.get(field) or "").strip():
            problems.append(f"{field} is empty")

    # Policy assertion check. The model is told not to state what the hotel
    # permits; this is the part that notices when it did anyway. Phrased as
    # patterns rather than a model call because "did you invent a rule" is
    # exactly the question a model is worst at answering about itself.
    scene = " ".join([draft.get("situation", ""), draft.get("opening_line", "")]).lower()
    asserts = ("you may offer", "you are allowed", "policy allows",
               "you can offer a free", "staff may offer", "hotel policy is",
               "you are permitted", "your authority is")
    for phrase in asserts:
        if phrase in scene:
            problems.append(f'asserts policy: "{phrase}"')

    persona = draft.get("guest_persona") or {}
    for field in ("name", "mood", "wants", "concedes_when"):
        if not (persona.get(field) or "").strip():
            problems.append(f"guest_persona.{field} is empty")

    return problems


def propose(cur, actor, staff_id: str, trace: Trace | None = None) -> dict:
    """Read one person's gap and write the scenario that answers it."""
    trace = trace or Trace()

    staff = q.staff_by_id(cur, staff_id)
    if not staff:
        return {"error": "not_found"}
    department = staff.get("department") or "all"

    gap = q.transfer_gap(cur, staff_id)
    scored = [d for d in gap["dimensions"] if d.get("quadrant")]
    if not scored:
        trace.step("code", "No dimension has both streams yet",
                   note="A scenario aimed at a gap we cannot measure would be "
                        "a guess wearing a lab coat.")
        return {"error": "insufficient_evidence",
                "detail": "This person does not yet have both a practice and a "
                          "floor score on any dimension."}

    # Widest absolute gap wins, exactly as the coaching agent picks its focus.
    # Same rule in both places on purpose: a manager who learns how one screen
    # chooses has learned how the other does.
    focus = max(scored, key=lambda d: abs(d.get("gap") or 0))
    job = JOBS.get(focus["quadrant"], JOBS["skill_gap"])

    trace.step("code", f'Focus: {focus["dimension"]} · {focus["quadrant"]}',
               decisive=True, dimension=focus["dimension"],
               quadrant=focus["quadrant"], gap=focus["gap"],
               practice=focus["practice_mean"], floor=focus["floor_mean"],
               job=job["label"],
               note="The quadrant chooses what the scenario is for, before any "
                    "model is called. A blocked person is never sent a "
                    "teaching scenario.")

    corpus = _corpus_for(cur, focus["dimension"], department, trace)
    trace.step("database", "Retrieve the standards this scene will press on",
               hits=[f'{c["ref"]} · {c.get("document_title") or c.get("document")} '
                     f'· {c.get("section_path", "")}' for c in corpus],
               note="Department scoped, same retrieval the coaching agent uses.")

    audit_notes = _audit_context(cur, department)
    if audit_notes:
        trace.step("code", f"{len(audit_notes)} open standards findings apply",
                   findings=[a["title"] for a in audit_notes],
                   note="The audit already established these holes. A boundary "
                        "scenario aimed at one of them rehearses something we "
                        "can name rather than something we suspect.")

    standards_text = "\n".join(
        f'{c["ref"]} [{c.get("section_path", "")}] {c["content"]}' for c in corpus)
    audit_text = ("\n".join(f'- {a["title"]}' for a in audit_notes)
                  if audit_notes else "none recorded")

    prompt = (
        f'Staff member: {staff["display_name"]}, {department.replace("_", " ")}.\n'
        f'Dimension: {focus["dimension"].replace("_", " ")}.\n'
        f'In practice they score {focus["practice_mean"]}; on the floor '
        f'{focus["floor_mean"]}.\n'
        f'Quadrant: {focus["quadrant"]}.\n\n'
        f'THE JOB THIS SCENARIO HAS TO DO:\n{job["brief"]}\n\n'
        f'Known holes in this property\'s written standards:\n{audit_text}\n\n'
        f'The property\'s standards for this situation:\n{standards_text}')

    attempts = 0
    draft: dict | None = None
    problems: list[str] = []
    while attempts < 2:
        attempts += 1
        extra = ""
        if problems:
            extra = ("\n\nA previous draft was rejected: "
                     + "; ".join(problems)
                     + ". Fix exactly those and change nothing else.")
        try:
            draft = providers.complete(
                "write_scenario", SYSTEM, prompt + extra,
                schema=SCENARIO_SCHEMA,
                # Warmer than the rest of the product. Every other task is a
                # matching problem where non-determinism becomes noise in a
                # statistic; this one is writing, and a scenario generated at
                # zero reads like a form.
                temperature=0.7, trace=trace, max_tokens=1200)
        except Exception as exc:                       # noqa: BLE001
            trace.step("code", "Writer failed", error=str(exc)[:180])
            return {"error": "provider", "detail": str(exc)[:200]}

        draft = _tidy(draft or {})
        problems = _verify(draft, corpus)
        trace.step("code",
                   f'Scenario gate: {"PASSED" if not problems else "REJECTED"}',
                   attempt=attempts, passed=not problems, failures=problems,
                   note="Checks it points at real retrieved standards and does "
                        "not assert what the hotel permits. Invented dialogue "
                        "is fiction; invented policy is a defect.")
        if not problems:
            break

    if problems:
        trace.step("code", "Stopped after two attempts",
                   note="No third try. A writer that cannot stop inventing "
                        "policy in two goes is not going to on the third.")
        return {"error": "rejected", "detail": problems}

    assert draft is not None
    cited = [c for c in corpus if c["ref"] in
             {r.strip().upper() for r in draft.get("cited_refs", [])}]

    proposal = {
        "staff_id": staff_id,
        "staff_name": staff["display_name"],
        "department": department,
        "dimension": focus["dimension"],
        "quadrant": focus["quadrant"],
        "job": job["label"],
        "job_why": job["why"],
        "practice_mean": focus["practice_mean"],
        "floor_mean": focus["floor_mean"],
        "gap": focus["gap"],
        "title": draft["title"],
        "situation": draft["situation"],
        "opening_line": draft["opening_line"],
        "guest_persona": draft["guest_persona"],
        "rationale": draft["rationale"],
        "audit_findings": audit_notes,
        "citations": [{"ref": c["ref"],
                       "chunk_id": c.get("id"),
                       "document": c.get("document_title") or c.get("document"),
                       "section_path": c.get("section_path"),
                       "content": c["content"]} for c in cited],
        "attempts": attempts,
        "status": "proposed",
    }

    event_id = q.audit(cur, actor, "scenario.proposed", staff_id,
                       {"proposal": json.dumps(proposal)[:100000]})
    cur.connection.commit()
    proposal["proposal_id"] = str(event_id) if event_id else None
    proposal["trace"] = trace.as_dict()

    trace.step("code", "Hold for a manager",
               note="Nothing appears in anybody's practice list until a named "
                    "manager publishes it.")
    return proposal


def list_proposals(cur, limit: int = 20) -> list[dict]:
    """Proposals waiting on a manager, newest first, minus the published ones."""
    cur.execute("""
        SELECT id, subject_ref, payload, occurred_at
        FROM audit_event
        WHERE event_type = 'scenario.proposed'
        ORDER BY occurred_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()

    cur.execute("""
        SELECT subject_ref FROM audit_event
        WHERE event_type IN ('scenario.published', 'scenario.discarded')
    """)
    settled = {r["subject_ref"] for r in cur.fetchall() if r["subject_ref"]}

    out = []
    for row in rows:
        if str(row["id"]) in settled:
            continue
        raw = (row["payload"] or {}).get("proposal")
        if not raw:
            continue
        try:
            proposal = json.loads(raw)
        except (TypeError, ValueError):
            continue
        proposal["proposal_id"] = str(row["id"])
        proposal["proposed_at"] = (row["occurred_at"].isoformat()
                                   if row["occurred_at"] else None)
        out.append(proposal)
    return out


def _find_proposal(cur, proposal_id: str) -> dict | None:
    cur.execute("""
        SELECT id, payload FROM audit_event
        WHERE id = %s AND event_type = 'scenario.proposed'
    """, (proposal_id,))
    row = cur.fetchone()
    if not row:
        return None
    raw = (row["payload"] or {}).get("proposal")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def publish(cur, actor, proposal_id: str) -> dict:
    """Turn an approved proposal into a real scenario.

    This is the only function in the file that writes to `scenario`, and it
    only runs behind a manager pressing a button. Origin is manager_assigned
    because that is exactly what happened: a named person assigned it.
    """
    proposal = _find_proposal(cur, proposal_id)
    if not proposal:
        return {"error": "not_found"}

    persona = dict(proposal["guest_persona"])
    # The practice engine opens with this line, so it travels inside the
    # persona rather than being regenerated at temperature 0.8 when somebody
    # starts the attempt. A manager approved these words; the staff member
    # should get these words.
    persona["opening_line"] = proposal["opening_line"]

    chunk_ids = [c["chunk_id"] for c in proposal.get("citations", [])
                 if c.get("chunk_id")]

    cur.execute("""
        INSERT INTO scenario (property_id, origin, title, situation,
                              guest_persona, target_dimensions,
                              grounded_chunk_ids)
        VALUES (%s, 'manager_assigned', %s, %s, %s, %s, %s::uuid[])
        RETURNING id::text
    """, (actor.property_id, proposal["title"], proposal["situation"],
          json.dumps(persona), [proposal["dimension"]], chunk_ids))
    scenario_id = cur.fetchone()["id"]

    q.audit(cur, actor, "scenario.published", proposal_id,
            {"scenario_id": scenario_id, "staff_id": proposal["staff_id"],
             "dimension": proposal["dimension"],
             "quadrant": proposal["quadrant"]})
    cur.connection.commit()
    return {"scenario_id": scenario_id, "status": "published"}


def discard(cur, actor, proposal_id: str, reason: str | None = None) -> dict:
    """Reject a proposal.

    Recorded rather than deleted. A manager rejecting a generated scenario is
    the most useful signal this feature produces and throwing it away would be
    the same mistake as treating a rejected recommendation as telemetry.
    """
    proposal = _find_proposal(cur, proposal_id)
    if not proposal:
        return {"error": "not_found"}
    q.audit(cur, actor, "scenario.discarded", proposal_id,
            {"reason": (reason or "")[:500],
             "staff_id": proposal.get("staff_id"),
             "quadrant": proposal.get("quadrant")})
    cur.connection.commit()
    return {"status": "discarded"}

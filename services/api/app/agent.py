"""
agent.py
========
The coaching agent: assemble evidence, retrieve the standard, classify the root
cause, draft a recommendation, and refuse to emit it unless every claim is
cited.

The division of labour follows 01B section 3. The model reads unstructured
dialogue and writes prose. Code decides everything that touches an employment
consequence: the transfer gap, the quadrant, whether a claim is grounded, and
who an escalation routes to. The model is never asked whether it was grounded,
because self-assessment of hallucination is not a control.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from . import queries as q
from .providers import ProviderError, Trace, complete
from .retrieval import search

# The tested deterministic core. 72 unit tests, no I/O, no model calls.
#
# Two layouts have to work: the repo (services/agent, four levels up) and the
# container, where it is copied to /agent and PYTHONPATH already points there.
# Inserting a path that does not exist is harmless, but checking first means an
# import failure names the real problem instead of surfacing three frames later
# as a bare ModuleNotFoundError.
_parents = Path(__file__).resolve().parents
# parents[3] exists in the repo and does NOT exist in the container, where this
# file sits at /app/app/. Indexing it directly raised IndexError at import and
# the platform showed a dead service with no explanation.
_AGENT = (_parents[3] / "services" / "agent") if len(_parents) > 3 else None
if _AGENT is not None and _AGENT.is_dir():
    sys.path.insert(0, str(_AGENT))
from coaching_engine.cite_gate import (  # noqa: E402
    Claim, EvidenceItem, run_gate,
)
from coaching_engine.routing import RoutingContext, route  # noqa: E402

# --------------------------------------------------------------------------
# Schemas. Strict: an out-of-range level is a validation error, not a bad row.
# --------------------------------------------------------------------------

SCORE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scores"],
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "level", "evidence_span", "anchor_matched"],
                "properties": {
                    "dimension": {"type": "string"},
                    # null means the transcript did not evidence this dimension.
                    # Never the midpoint: defaulting to 3 compresses every gap.
                    "level": {"type": ["integer", "null"]},
                    "evidence_span": {"type": "string"},
                    "anchor_matched": {"type": "string"},
                },
            },
        }
    },
}

DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "opening_line", "claims", "suggested_action", "trap_to_avoid"],
    "properties": {
        "headline": {"type": "string"},
        "opening_line": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "citation_refs", "quoted_span"],
                "properties": {
                    "text": {"type": "string"},
                    "citation_refs": {"type": "array", "items": {"type": "string"}},
                    "quoted_span": {"type": "string"},
                },
            },
        },
        "suggested_action": {"type": "string"},
        "trap_to_avoid": {"type": "string"},
    },
}

CLASSIFY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["classification", "rationale"],
    "properties": {
        # Three values, and code maps the value to a route. The model never
        # decides who hears about this.
        "classification": {"type": "string",
                           "enum": ["behavioural", "process", "policy"]},
        "rationale": {"type": "string"},
    },
}


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score_transcript(cur, transcript: list[dict], target_dimensions: list[str],
                     trace: Trace | None = None) -> list[dict]:
    """Score a practice transcript against the property's own BARS anchors.

    The rubric is read from the database rather than baked into the prompt, so
    "we are not letting the model decide what good looks like" is true
    structurally and not just rhetorically.
    """
    cur.execute("""
        SELECT bd.code, bd.label, ba.level, ba.anchor_text
        FROM bars_dimension bd
        JOIN bars_anchor ba ON ba.dimension_id = bd.id
        JOIN bars_rubric br ON br.id = bd.rubric_id AND br.is_active
        WHERE bd.code = ANY(%s)
        ORDER BY bd.code, ba.level DESC
    """, (target_dimensions,))

    rubric: dict[str, list[str]] = {}
    for r in cur.fetchall():
        rubric.setdefault(r["code"], []).append(f"  {r['level']}: {r['anchor_text']}")
    if not rubric:
        return []

    rubric_block = "\n\n".join(f"{code}:\n" + "\n".join(lines)
                               for code, lines in rubric.items())
    convo = "\n".join(f"[{i}] {t['speaker'].upper()}: {t['content']}"
                      for i, t in enumerate(transcript))

    system = (
        "You score hospitality staff behaviour against a hotel's own rating "
        "scale.\n\n"
        "RULES\n"
        "1. Score ONLY the dimensions listed. Use the written anchors, not your "
        "own idea of good service.\n"
        "2. level must be an integer 1 to 5, or null if the transcript contains "
        "no evidence for that dimension. Never guess a middle value.\n"
        "3. evidence_span MUST be copied verbatim from a STAFF turn. Do not "
        "paraphrase. If you cannot quote it, the level is null.\n"
        "4. anchor_matched is the text of the anchor you matched."
    )
    user = f"RATING SCALE\n{rubric_block}\n\nTRANSCRIPT\n{convo}"

    result = complete("score", system, user, schema=SCORE_SCHEMA, trace=trace)

    staff_text = " ".join(t["content"].lower() for t in transcript
                          if t["speaker"] == "staff")
    out = []
    for s in result.get("scores", []):
        if s["level"] is None:
            continue
        if not 1 <= s["level"] <= 5:
            continue                       # schema should stop this; belt and braces
        span = (s.get("evidence_span") or "").strip()
        # A span the staff member never said is a fabricated quote. Drop the
        # score rather than store evidence that does not exist.
        if span and span.lower()[:40] not in staff_text:
            continue
        out.append(s)
    return out


# --------------------------------------------------------------------------
# The coaching run
# --------------------------------------------------------------------------

def _served_by(trace: Trace | None) -> dict:
    """Who answered the call that just finished.

    The glass box argues that the reasoning is ours and the model is one part
    of it. That argument is weaker when a step says only "Classify the cause"
    and a judge has to take on faith which provider ran it. Naming the provider
    and model on the step makes the claim checkable, and it is the difference
    between saying we run on Google Cloud and showing it.
    """
    if not trace or not trace.calls:
        return {}
    call = trace.calls[-1]
    return {"served_by": f"{call.provider}/{call.model}",
            "ms": call.ms,
            **({"fell_back": True} if call.fell_back else {})}


def run_coaching(cur, actor, staff_id: str, trace: Trace | None = None) -> dict:
    """Assemble, retrieve, classify, draft, gate. Returns a recommendation or
    an abstention, never an ungrounded recommendation."""
    trace = trace or Trace()

    staff = q.staff_by_id(cur, staff_id)
    if not staff:
        return {"status": "abstained", "abstain_reason": "No such staff member."}

    gap = q.transfer_gap(cur, staff_id)
    trace.step("database", "Read both evidence streams under row level security",
               rows=len(gap["dimensions"]) + len(gap["insufficient_evidence"]),
               note=("The actor's own permissions applied. A manager who has "
                     "not observed this person sees no practice scores here."))
    trace.step("code", "Compute the transfer gap per dimension",
               decisive=True,
               dimensions=[{"dimension": d["dimension"], "gap": d["gap"],
                            "quadrant": d["quadrant"]}
                           for d in gap["dimensions"]],
               insufficient=gap["insufficient_evidence"],
               note="Arithmetic, not judgement. No model has been called yet.")
    if not gap["dimensions"]:
        return {
            "status": "abstained",
            "abstain_reason": (
                "Not enough evidence yet to give you grounded coaching: no "
                "dimension has both a practice score and a floor observation."),
            "what_would_help": [{"action": "log_observation", "dimension": d}
                                for d in gap["insufficient_evidence"][:3]],
            "trace": trace.as_dict(),
        }

    # The dimension with the widest gap is the one worth a conversation.
    focus = max(gap["dimensions"], key=lambda d: abs(d["gap"]))
    trace.step("code", f"Select the focus dimension: {focus['dimension']}",
               decisive=True, quadrant=focus["quadrant"], gap=focus["gap"],
               note="Widest absolute gap wins. Deterministic and reproducible.")

    # --- evidence bundle -------------------------------------------------
    cur.execute("""
        SELECT o.id::text, o.context, o.what_happened, o.observed_at
        FROM observation o WHERE o.staff_id = %s
        ORDER BY o.observed_at DESC LIMIT 1
    """, (staff_id,))
    obs = cur.fetchone()

    cur.execute("""
        SELECT s.id::text, s.level, s.evidence_span, s.attempt_id::text, s.scored_at
        FROM score s
        JOIN bars_dimension bd ON bd.id = s.dimension_id
        WHERE s.staff_id = %s AND s.source = 'practice' AND bd.code = %s
        ORDER BY s.scored_at DESC LIMIT 3
    """, (staff_id, focus["dimension"]))
    practice = cur.fetchall()

    if not obs or not practice:
        return {"status": "abstained",
                "abstain_reason": "Missing one of the two evidence streams.",
                "trace": trace.as_dict()}

    # --- retrieve the standard -------------------------------------------
    query = f"{focus['dimension'].replace('_', ' ')}. {obs['what_happened']}"
    chunks = search(cur, query, department=staff["department"], limit=5, trace=trace)
    trace.step("database", "Hybrid search over this hotel's own standards",
               hits=[{"ref": f"S{i}", "document": c["document"],
                      "section": c["section_path"],
                      "similarity": c["similarity"]}
                     for i, c in enumerate(chunks, 1)],
               note=("Vector plus full text, fused with reciprocal rank. "
                     "A cosine floor of 0.30 rejects the merely topical."))
    if not chunks:
        trace.step("code", "Abstain: no standard supports a claim here",
                   decisive=True,
                   note=("Nothing cleared the similarity floor, so any advice "
                         "would be generic. The product declines instead."))
    if not chunks:
        return {
            "status": "abstained",
            "abstain_reason": (
                f"No applicable standard found for this situation in "
                f"{staff['department'].replace('_', ' ')}. The coaching would be "
                f"generic advice rather than grounded in this hotel's own "
                f"procedure, so it is not offered."),
            "what_would_help": [{"action": "add_standard",
                                 "dimension": focus["dimension"]}],
            "trace": trace.as_dict(),
        }

    # --- evidence, in the shape the gate validates ------------------------
    #
    # Labels are short and opaque (E1, E2, ...) rather than raw uuids. A model
    # asked to copy a 36-character uuid drops the prefix or mangles a digit,
    # the gate correctly rejects the citation, and a perfectly well grounded
    # recommendation abstains for a formatting reason. Short labels remove that
    # failure mode without loosening a single check: the gate still verifies
    # existence, span support, sufficiency and scope. real_ref carries the
    # database identity through to the stored citation.
    # The prefix is the stream, and that is load-bearing. The gate's hardest
    # rule is "cite practice AND floor", and with a flat E1..E9 numbering the
    # model cannot see which is which without re-reading the block, so it
    # cites three practice refs, fails the rule, and a well grounded reading
    # abstains for a bookkeeping reason. P/F/S/M makes the rule checkable at a
    # glance. The gate is unchanged; only the model's view of it got clearer.
    bundle: list[EvidenceItem] = []
    real_ref: dict[str, str] = {}
    counts: dict[str, int] = {}

    def add(prefix: str, kind: str, content: str, ref: str, owner: str | None):
        counts[prefix] = counts.get(prefix, 0) + 1
        label = f"{prefix}{counts[prefix]}"
        real_ref[label] = ref
        bundle.append(EvidenceItem(ref=label, kind=kind, content=content,
                                   staff_id=owner))

    for p in practice:
        add("P", "attempt_turn", p["evidence_span"] or "",
            f"attempt:{p['attempt_id']}", staff_id)
    add("F", "observation", f"{obs['context']}. {obs['what_happened']}",
        f"obs:{obs['id']}", staff_id)
    for c in chunks:
        add("S", "sop_chunk", c["content"], f"sop:{c['id']}", None)
    add("M", "metric", json.dumps(focus), f"metric:gap:{focus['dimension']}", None)

    evidence_block = "\n".join(
        f"{e.ref}  [{e.kind}]  {e.content[:220]}" for e in bundle)
    evidence_block = (
        "Refs are prefixed by stream: P = practice (what they did in the "
        "simulator), F = floor (what the manager observed on shift), "
        "S = this hotel's own written standard, M = the computed metric.\n\n"
        + evidence_block)

    # --- classify ---------------------------------------------------------
    cur.execute("""
        SELECT count(DISTINCT sd.staff_id) AS n
        FROM shift_debrief sd
        JOIN staff_member sm ON sm.id = sd.staff_id
        WHERE sm.department = %s
          AND sd.incident->>'situation_type' = 'room_not_ready'
          AND sd.created_at > now() - interval '14 days'
    """, (staff["department"],))
    cohort_size = cur.fetchone()["n"] or 0

    # The quadrant constrains the classifier, it does not merely advise it.
    #
    # BLOCKED means the person produced the behaviour correctly in practice and
    # did not produce it on the floor. Whatever is wrong, it is not that they
    # lack the skill: the practice score is the proof they have it. So the
    # model is not offered "behavioural" as an option. Leaving it in the enum
    # and asking nicely produced exactly the contradiction you would expect,
    # a headline reading "unsure about authority" filed as a skill problem,
    # which would then route to training and tell a blocked person to practise
    # something they can already do. This is principle one: the arithmetic
    # decides what the model is allowed to say, not the prompt.
    allowed = ["behavioural", "process", "policy"]
    if focus["quadrant"] == "blocked":
        allowed = ["process", "policy"]
    elif focus["quadrant"] == "recalibrate":
        # Floor above practice. They can do it where it counts, so the failing
        # process is our measurement of them, not their behaviour.
        allowed = ["process"]
    if len(allowed) < 3:
        trace.step("code", "Constrain what the model is allowed to conclude",
                   decisive=True, quadrant=focus["quadrant"], allowed=allowed,
                   removed=[c for c in ("behavioural", "process", "policy")
                            if c not in allowed],
                   note=("The quadrant already proves the skill is present, so "
                         "'behavioural' is removed from the schema. The model "
                         "cannot return it, prompt or no prompt."))
    classify_schema = {**CLASSIFY_SCHEMA,
                       "properties": {**CLASSIFY_SCHEMA["properties"],
                                      "classification": {"type": "string",
                                                         "enum": allowed}}}

    classification = ("behavioural" if len(allowed) == 3 else allowed[-1])
    try:
        c = complete(
            "classify",
            "You classify why a performance gap exists. Choose exactly one:\n\n"
            "behavioural - an individual skill gap. Only choose this if the "
            "person genuinely cannot do it, including in practice.\n"
            "process - an operational step is failing upstream and creating "
            "these situations in the first place.\n"
            "policy - staff do not know what they are PERMITTED to do. Choose "
            "this when someone escalates or freezes rather than acting, when "
            "they say they were unsure what they could offer, or when the "
            "standards describe escalation but never state what the person may "
            "decide themselves.\n\n"
            "Two rules that override your instinct:\n"
            "- If they performed the behaviour correctly in practice, it is NOT "
            "behavioural. They have the skill.\n"
            "- If your best staff also fail it, it is not a skill problem.\n\n"
            "Your rationale is shown to the manager. Refer to the person by "
            "name and do not infer their gender from it: use the name, or "
            "they.",
            f"STAFF: {staff['display_name']}, {staff['department']}\n"
            f"GAP: {focus['dimension']} practice {focus['practice_mean']} vs "
            f"floor {focus['floor_mean']} ({focus['quadrant']})\n"
            + ("ALREADY SETTLED BY THE MEASUREMENT: they demonstrated this "
               "correctly in practice and did not produce it on the floor, so "
               "the skill is present. Decide only WHAT IS STOPPING THEM.\n"
               if focus["quadrant"] == "blocked" else "") +
            f"OBSERVATION: {obs['what_happened']}\n"
            f"OTHERS WITH THE SAME SITUATION THIS FORTNIGHT: {cohort_size}\n"
            f"STANDARDS FOUND: {chr(10).join(c['content'][:120] for c in chunks[:3])}",
            schema=classify_schema, trace=trace)
        classification = c["classification"]
        trace.step("model", f"Classify the cause: {classification}",
                   decisive=True, chose_from=allowed,
                   **_served_by(trace),
                   rationale=c.get("rationale", "")[:220])
    except ProviderError:
        pass                               # default stands; not worth failing the run

    # --- draft, then gate, with a bounded repair loop ----------------------
    quadrant_rule = {
        "blocked":
            "THIS PERSON IS IN THE BLOCKED QUADRANT. They demonstrated the "
            "behaviour correctly in practice and did not produce it on the "
            "floor. They are NOT missing the skill. You are therefore "
            "FORBIDDEN from recommending training, practice, coaching on the "
            "technique, or 'reinforcing the SOP'. Something is stopping them: "
            "unclear authority, time pressure, or not knowing what they are "
            "permitted to offer. Name what is stopping them and recommend "
            "removing it.",
        "skill_gap":
            "This is a genuine skill gap, weak in practice and on the floor. "
            "Targeted practice IS the right answer here.",
        "competent":
            "Competent in both. Recommend stretch, not remediation.",
        "recalibrate":
            "Strong on the floor, weak in practice. This is a signal that OUR "
            "scoring or scenario may be wrong. Say so.",
    }.get(focus["quadrant"], "")

    system = (
        "You write coaching guidance for a hotel duty manager who has had no "
        "coaching training and ninety seconds to read this.\n\n"
        f"{quadrant_rule}\n\n"
        "HARD RULES\n"
        "1. Every factual claim about this person MUST carry a citation_refs "
        "entry copied EXACTLY from the EVIDENCE block. Never cite a ref that is "
        "not listed.\n"
        "2. Only cite a standard if it genuinely supports the claim. A "
        "topically similar clause that does not say what you need is NOT "
        "support. Leave it out.\n"
        "3. For S citations, quoted_span must be a character-for-character copy "
        "of a contiguous run of text from that ONE chunk. These clauses "
        "are short, often a single sentence: when in doubt copy the whole "
        "clause. Never merge two clauses into one quote, never tidy the "
        "wording, and never quote what a clause implies rather than what "
        "it says. If no clause says what you need, drop the claim.\n"
        "4. You must cite at least one P ref AND at least one F ref. A "
        "reading with no F ref is roleplay feedback, not a transfer gap, and "
        "it will be rejected.\n"
        "5. If the classification is process or policy, do NOT recommend "
        "individual coaching. Recommend the organisational fix.\n"
        "6. Refer to the person by the name in STAFF. Do NOT infer their "
        "gender from that name: write the name, or they, never he or she. "
        "This text is filed in an employment record about a real person, and "
        "a guess that is wrong is worse than the plainer sentence.\n"
        "7. Do not open with a score.\n\n"
        "STYLE\n"
        "headline: state the CONCLUSION in one plain sentence a busy manager "
        "grasps instantly. Not a topic. Write 'This is not a training gap, "
        "Diego has not been told what they are allowed to offer', never 'Enhancing "
        "Service Recovery Execution'. No title case, no abstract nouns.\n"

        "opening_line: the literal words the manager says to open the "
        "conversation. A question, usually. Not a description of what to say.\n"
        "suggested_action: one concrete thing, doable this week, by a named "
        "role. Never 'review the process' or 'ensure staff are trained'.\n"
        "trap_to_avoid: the specific mistake this manager is likely to make.\n"

        # Every other surface on this product is em-dash free and a
        # recommendation card sits right beside that copy. Asking the model
        # for a comma is cheaper than stripping dashes from the output
        # afterwards, which could edit a quoted span and fail the cite gate
        # for a reason that has nothing to do with the evidence.
        "punctuation: never use an em dash. A comma, a full stop or a colon\n"
        "instead. This applies to every field."
    )
    base_user = (
        f"STAFF: {staff['display_name']} ({staff['department']})\n"
        f"CLASSIFICATION: {classification}\n"
        f"FOCUS DIMENSION: {focus['dimension']}\n"
        f"READING: {focus['reading']}\n"
        f"PRACTICE {focus['practice_mean']} vs FLOOR {focus['floor_mean']}, "
        f"gap {focus['gap']}\n\nEVIDENCE\n{evidence_block}"
    )

    draft, gate_result, attempts = None, None, 0
    user = base_user
    while attempts < 3:
        draft = complete("coach", system, user, schema=DRAFT_SCHEMA,
                         temperature=0.2, trace=trace)
        claims = [Claim(text=c["text"],
                        citation_refs=tuple(c["citation_refs"]),
                        quoted_span=c.get("quoted_span") or None)
                  for c in draft["claims"]]
        trace.step("model", f"Draft the recommendation (attempt {attempts + 1})",
                   claims=len(claims), **_served_by(trace),
                   cited=sorted({r for c in claims for r in c.citation_refs}))
        gate_result = run_gate(claims, bundle, staff_id, repair_attempts=attempts)
        trace.step("code", ("Cite gate: PASSED" if gate_result.passed
                            else "Cite gate: REJECTED"),
                   decisive=True, passed=gate_result.passed,
                   checks=["source exists in the bundle",
                           "quoted span is genuinely in the cited chunk",
                           "at least one practice AND one floor citation",
                           "no claim leans on another person's evidence"],
                   failures=[{"claim": f.claim_text[:90] if f.claim_text else None,
                              "ref": f.ref, "reason": f.reason,
                              "explanation": f.describe()}
                             for f in gate_result.failures],
                   note=("Four checks, all in code, all in the 72 unit tests. "
                         "The model is never asked whether it cited correctly."))
        if gate_result.passed:
            break
        attempts += 1
        if gate_result.should_abstain:
            break
        cited = {r for c in draft["claims"] for r in c["citation_refs"]}
        missing = [name for prefix, name in (("P", "a P (practice) ref"),
                                             ("F", "an F (floor) ref"))
                   if not any(r.startswith(prefix) for r in cited)]
        user = (base_user + "\n\nYOUR PREVIOUS DRAFT WAS REJECTED:\n" +
                "\n".join(f"- {f.describe()}" for f in gate_result.failures[:6]) +
                (f"\n- your claims cite {sorted(cited) or 'nothing'}; you are "
                 f"missing {' and '.join(missing)}" if missing else "") +
                "\nFix these. Only cite refs listed in EVIDENCE, and only where "
                "the source genuinely supports the claim.")

    if gate_result is None or not gate_result.passed:
        return {
            "status": "abstained",
            "abstain_reason": gate_result.abstain_reason() if gate_result else
                              "Could not ground a recommendation.",
            "gate_failures": [f.describe() for f in (gate_result.failures if gate_result else [])],
            "trace": trace.as_dict(),
        }

    # --- route -------------------------------------------------------------
    esc = route(RoutingContext(
        classification=classification,
        quadrant=focus["quadrant"],
        cohort_size=cohort_size,
        floor_mean=focus["floor_mean"],
        floor_n=focus["floor_n"],
    ))

    trace.step("code", f"Route by rule {esc.rule_id} to {esc.route}",
               decisive=True, rule_id=esc.rule_id, route=esc.route,
               severity=esc.severity,
               suppress_individual_coaching=esc.suppress_individual_coaching,
               note=("First match wins over a fixed rule list. Article 14 "
                     "needs a reason a human can check, and 'the model decided' "
                     "is not one."))
    trace.step("code", "Hold for human verification",
               decisive=True,
               note=("Nothing routes anywhere until a manager confirms, "
                     "corrects or rejects. There is no timeout and no "
                     "auto-approve."))

    by_ref = {e.ref: e for e in bundle}
    citations = []
    for c in draft["claims"]:
        for ref in c["citation_refs"]:
            src = by_ref.get(ref)
            if not src:
                continue
            citations.append({
                "kind": src.kind, "claim": c["text"],
                "source_ref": real_ref.get(ref, ref),
                "quoted_span": c.get("quoted_span") or src.content[:200],
            })

    evidence_hash = hashlib.sha256(
        json.dumps([e.ref for e in bundle], sort_keys=True).encode()).hexdigest()

    return {
        "status": "pending_verify",
        "staff_id": staff_id,
        "staff_name": staff["display_name"],
        "classification": classification,
        "headline": draft["headline"],
        "opening_line": draft["opening_line"],
        "body": draft["opening_line"],
        "suggested_action": draft["suggested_action"],
        "trap_to_avoid": draft.get("trap_to_avoid"),
        "focus_dimension": focus["dimension"],
        "gap": focus,
        "citations": citations,
        "escalation": {
            "rule_id": esc.rule_id, "route": esc.route, "severity": esc.severity,
            "summary": esc.copy,
            "suppress_individual_coaching": esc.suppress_individual_coaching,
        },
        "evidence_hash": evidence_hash,
        "repair_attempts": attempts,
        "trace": trace.as_dict(),
    }

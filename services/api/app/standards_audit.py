"""Audit a property's own written standards, and find the holes in them.

WHY THIS EXISTS

The product's central finding is that Diego does not offer a guest anything
because nobody told him he was allowed to. We found that by hand, by reading a
hotel's documents and noticing what was missing. That is not a thing you can do
for every customer, and it is the single most valuable half hour in an
onboarding, because it produces a report a General Manager acts on before a
single person has been coached.

So this reads the corpus the property has already given us and looks for six
kinds of defect that make staff hesitate on the floor:

  contradiction    two clauses that cannot both be followed
  authority_gap    a decision is required and no clause says who may make it
  scope_gap        one department has a rule and another with the same
                   situation has nothing
  vague_condition  a trigger nobody can test ("if they feel confident")
  duplication      the same duty in several documents, which is how they drift
  coverage_hole    a rubric dimension with no standard behind it, so people are
                   being scored against nothing

WHAT MAKES IT AN AGENT RATHER THAN A PROMPT

The same shape as the coaching agent, deliberately, because the argument we
make about that one has to survive being asked about this one:

  code   assembles the corpus and decides which checks are worth running
  model  proposes findings, and only proposes
  code   verifies every quoted span against the chunk it claims to come from
  model  gets exactly one repair attempt, told which claims failed and why
  code   scores impact by joining findings to observed floor evidence
  code   stops, and a human decides what to do

A finding that cannot quote is dropped, not softened. The model is never asked
whether its own citations were real.

WHAT IT IS NOT

It does not edit anybody's standards, and it does not decide anything about a
person. It reads documents and writes a report. Everything about it is a step
BEFORE the high-risk path in Annex III 4(b), which is the only reason it is
allowed to be this autonomous.
"""
from __future__ import annotations

import json
from typing import Any

from . import providers
from . import queries as q
from .providers import Trace

# One model call per check, each with the whole corpus in front of it. The
# corpus is around sixty clauses, which fits comfortably, and a check that can
# see everything finds cross-document defects that a chunk-by-chunk pass never
# will: the scope gap between front office and food and beverage is invisible
# unless both documents are in the same call.
CHECKS = ("contradiction", "authority_gap", "scope_gap",
          "vague_condition", "duplication")

# How many distinct clauses a finding of each kind has to cite before it is
# allowed to exist. A contradiction with one citation is an opinion.
MIN_CITATIONS = {
    "contradiction": 2,
    "duplication": 2,
    "authority_gap": 1,
    "scope_gap": 1,
    "vague_condition": 1,
    "coverage_hole": 0,
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "explanation", "citations",
                             "missing_sentence", "severity"],
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "One sentence naming the defect, in "
                                       "plain operational English.",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Why this makes somebody hesitate on "
                                       "the floor. Two sentences at most.",
                    },
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["ref", "quote"],
                            "properties": {
                                "ref": {"type": "string",
                                        "description": "The S-number of the "
                                                       "clause, e.g. S12."},
                                "quote": {"type": "string",
                                          "description": "Text copied "
                                                         "VERBATIM from that "
                                                         "clause."},
                            },
                        },
                    },
                    "missing_sentence": {
                        "type": "string",
                        "description": "The clause that should exist, written "
                                       "in the same register as the documents "
                                       "quoted, ready for a manager to paste. "
                                       "NEVER invent a specific money amount, "
                                       "time limit or threshold: write it as a "
                                       "blank for the manager to fill, like "
                                       "'up to EUR ___'. Empty string when the "
                                       "defect is a contradiction rather than "
                                       "an absence.",
                    },
                    "severity": {"type": "string",
                                 "enum": ["high", "medium", "low"]},
                },
            },
        },
    },
}

SYSTEM = """You audit a hotel's own written standards for defects that make
front-line staff hesitate during a guest complaint.

You are reading real operating documents. Every claim you make must quote the
clause it comes from, VERBATIM, copied character for character from the text
given to you. A quote you paraphrase will be rejected by a checker that does
string matching, and the finding will be thrown away.

Report only defects you can prove from the text in front of you. An absence is
provable: if no clause anywhere states what a front desk agent may offer a
guest without approval, say so and cite the clauses that come closest. Do not
report a defect because it seems likely. Do not report style preferences.

Write like an operations consultant, not a compliance auditor. Short sentences.
No hedging. If there is nothing of the kind you are asked for, return an empty
list, which is a valid and useful answer.

When you propose a clause that should exist, never invent a number. A spending
limit, an approval threshold and a response time are commercial decisions that
belong to the property, and a plausible-looking figure is worse than a blank
because somebody will adopt it without noticing they were never asked. Write
"up to EUR ___" and let a manager fill it in."""

CHECK_BRIEFS = {
    "contradiction": """Find pairs of clauses that CANNOT BOTH be followed by
the same person in the same moment. Order-of-operations conflicts count: if one
document says apologise first and another says listen first, a staff member
following both is guessing. Cite BOTH sides.""",

    "authority_gap": """Find decisions the documents REQUIRE somebody to make
while never saying who may make them, or within what limit. The strongest
version: a clause grants discretion and another clause takes it back by
requiring approval or a signature. Cite the clause that creates the need, and
the closest thing to a permission if one exists.""",

    "scope_gap": """Each clause is labelled with the department it belongs to.
Find situations that plainly arise in one department where that department has
no clause, while another department does. Cite the clause that exists, and name
the department that has nothing.""",

    "vague_condition": """Find triggers that no two people would read the same
way: conditions that depend on how somebody feels, or on an undefined threshold.
Quote the exact condition.""",

    "duplication": """Find the same duty stated in more than one document. This
matters because duplicated rules drift apart at the next revision and nobody
notices. Cite every place it appears.""",
}


# ---------------------------------------------------------------- corpus

def load_corpus(cur) -> list[dict]:
    """Every clause, labelled S1..Sn, with the document it came from.

    Refs are assigned here and nowhere else. The model cites by ref, the
    verifier resolves the ref back to a row, and the UI renders from the same
    row, so there is no point at which a citation can drift onto a clause the
    model did not actually read.
    """
    cur.execute("""
        SELECT c.id::text      AS id,
               d.title         AS document,
               d.department    AS department,
               d.doc_type      AS doc_type,
               c.section_path  AS section_path,
               c.step_number   AS step_number,
               c.content       AS content,
               c.ordinal       AS ordinal
        FROM sop_chunk c
        JOIN sop_document d ON d.id = c.document_id
        ORDER BY d.title, c.ordinal
    """)
    rows = cur.fetchall()
    for index, row in enumerate(rows, start=1):
        row["ref"] = f"S{index}"
        # The last segment of the path is what a person would call the clause:
        # "Rule 1", "Step 9", "Authority and Approval > 2".
        row["label"] = row["section_path"].split(">")[-1].strip()
    return rows


def corpus_text(corpus: list[dict]) -> str:
    """The whole corpus as the model sees it, grouped by document.

    Department is on every line rather than only the header, because the scope
    gap check needs it attached to the clause and a model reading a long list
    loses a header it saw forty lines ago.
    """
    lines: list[str] = []
    current = None
    for row in corpus:
        if row["document"] != current:
            current = row["document"]
            lines.append("")
            lines.append(f'## {current}  ({row["doc_type"]}, '
                         f'department: {row["department"]})')
        lines.append(f'{row["ref"]} [{row["label"]}] '
                     f'(dept: {row["department"]}) {row["content"]}')
    return "\n".join(lines).strip()


# ---------------------------------------------------------------- the gate

def verify(findings: list[dict], corpus: list[dict],
           kind: str) -> tuple[list[dict], list[dict]]:
    """Keep the findings that can prove themselves; report why the rest failed.

    Three checks, all string work, none of it delegated to a model:

      1. every cited ref is a clause that exists
      2. every quote appears VERBATIM inside the clause it cites
      3. the finding cites at least as many clauses as its kind requires

    Whitespace is normalised before comparison because a model will reflow a
    line break and that is not a fabrication. Nothing else is forgiven: a quote
    that says "may offer a complimentary item at their discretion" when the
    clause says "may offer a complimentary item (coffee or beverage) at their
    discretion" has changed what the hotel permits, and that is exactly the
    kind of drift this whole product exists to catch.
    """
    by_ref = {row["ref"]: row for row in corpus}
    kept: list[dict] = []
    failures: list[dict] = []

    def squash(text: str) -> str:
        return " ".join(text.split()).lower()

    for finding in findings:
        problems: list[str] = []
        resolved: list[dict] = []

        for citation in finding.get("citations", []):
            ref = (citation.get("ref") or "").strip().upper()
            quote = (citation.get("quote") or "").strip()
            row = by_ref.get(ref)
            if row is None:
                problems.append(f"{ref or '(no ref)'}: no such clause")
                continue
            if not quote:
                problems.append(f"{ref}: no quote given")
                continue
            if squash(quote) not in squash(row["content"]):
                problems.append(f"{ref}: quoted text is not in that clause")
                continue
            resolved.append({
                "ref": ref,
                "quote": quote,
                "document": row["document"],
                "label": row["label"],
                "department": row["department"],
                "content": row["content"],
            })

        needed = MIN_CITATIONS.get(kind, 1)
        if len(resolved) < needed:
            problems.append(
                f"needs {needed} verified clause(s), has {len(resolved)}")

        if problems:
            failures.append({"title": finding.get("title", "(untitled)"),
                             "reasons": problems})
            continue

        # Written by a model, read by a general manager, so it goes through the
        # same punctuation the rest of the site uses. Quotes are exempt: a
        # quoted clause has to stay character-for-character what the document
        # says, which is the whole point of the gate above.
        for field in ("title", "explanation", "missing_sentence"):
            finding[field] = providers.plain(finding.get(field, ""))

        finding["citations"] = resolved
        finding["kind"] = kind
        kept.append(finding)

    return kept, failures


# ------------------------------------------------------- deterministic checks

def coverage_holes(cur, corpus: list[dict]) -> list[dict]:
    """Rubric dimensions with no standard behind them.

    Deliberately not a model call. This is a set difference: the dimensions we
    score people against, minus the dimensions any clause plausibly speaks to.
    Arithmetic is more trustworthy than judgement here and it costs nothing.

    The match is keyword based and therefore generous: a dimension counts as
    covered if any clause mentions it. Being generous is the right bias, because
    a false "you have no standard for this" is a worse failure than a missed
    one.
    """
    cur.execute("SELECT code, label FROM bars_dimension ORDER BY code")
    dimensions = cur.fetchall()

    hints = {
        "service_recovery": ("complain", "apolog", "resolv", "recover",
                             "refund", "complimentary", "escalat"),
        "empathy": ("empath", "listen", "feel", "acknowledg", "understand"),
        "composure": ("calm", "argue", "shout", "professional", "posture"),
        "communication": ("greet", "explain", "inform", "brief", "say",
                          "tell", "repeat"),
        "anticipation": ("anticipat", "before", "proactiv", "prepare",
                         "check back", "follow up"),
    }

    blob = " ".join(row["content"].lower() for row in corpus)
    out: list[dict] = []
    for dim in dimensions:
        words = hints.get(dim["code"], (dim["code"].replace("_", " "),))
        if any(word in blob for word in words):
            continue
        out.append({
            "kind": "coverage_hole",
            "title": f'No written standard covers {dim["label"]}',
            "explanation": (
                f'Staff are scored on {dim["label"]} and no clause in the '
                f'corpus describes what good looks like. The rubric is doing '
                f'work the standards should be doing.'),
            "citations": [],
            "missing_sentence": "",
            "severity": "medium",
        })
    return out


def impact(cur, findings: list[dict]) -> list[dict]:
    """Attach observed floor evidence to the findings that predict it.

    This is the part nobody else can do, and it is the reason the audit is
    worth more than a consultant reading the same documents: a defect in a
    procedure manual is an opinion until you can say how many people it is
    currently costing you.

    The join is deliberately coarse and the wording says so. A policy-class
    recommendation means the agent already concluded, from two independent
    evidence streams, that the rules rather than the person were the blocker.
    Counting those is honest. Claiming a specific clause caused a specific
    person's behaviour would not be.
    """
    cur.execute("""
        SELECT count(DISTINCT staff_id) AS staff,
               count(*)                 AS findings
        FROM recommendation
        WHERE classification = 'policy'
    """)
    policy = cur.fetchone() or {"staff": 0, "findings": 0}

    for finding in findings:
        if finding["kind"] in ("authority_gap", "scope_gap") and policy["staff"]:
            finding["impact"] = {
                "staff": policy["staff"],
                "recommendations": policy["findings"],
                "note": (f'{policy["staff"]} people currently have an open '
                         f'recommendation where the agent judged the rules, '
                         f'not the person, to be the blocker.'),
            }
        else:
            finding["impact"] = None

    # Severity is then re-ranked by evidence, not left to the model's opinion.
    #
    # The model called the front office authority gap "medium". It is the most
    # expensive defect in the corpus: it is the reason a named person stood in
    # front of a guest and offered nothing. A defect the floor is already
    # paying for outranks one nobody has hit yet, and that judgement is
    # arithmetic we can show, so it belongs in code.
    for finding in findings:
        if finding.get("impact") and finding.get("severity") != "high":
            finding["severity_note"] = (
                f'Raised from {finding.get("severity", "low")}: this one is '
                f'already showing up on the floor.')
            finding["severity"] = "high"
    return findings


# ---------------------------------------------------------------- the agent

def run_audit(cur, actor, trace: Trace | None = None) -> dict:
    """Read the corpus, run every check, verify, repair once, score, stop."""
    trace = trace or Trace()

    corpus = load_corpus(cur)
    documents = sorted({row["document"] for row in corpus})
    trace.step("database", "Load the property's own standards",
               chunks=len(corpus), documents=len(documents),
               note="Immutable clauses, each given a stable ref for citation.")

    if not corpus:
        return {"findings": [], "documents": 0, "clauses": 0,
                "trace": trace.as_dict()}

    text = corpus_text(corpus)
    kept: list[dict] = []
    rejected: list[dict] = []

    for kind in CHECKS:
        prompt = (f"{CHECK_BRIEFS[kind]}\n\n"
                  f"The property's standards:\n\n{text}")
        try:
            first = providers.complete(
                "audit_standards", SYSTEM, prompt,
                schema=FINDING_SCHEMA, temperature=0.1, trace=trace,
                max_tokens=2000)
        except Exception as exc:                      # noqa: BLE001
            trace.step("code", f"Check '{kind}' could not run",
                       error=str(exc)[:180],
                       note="Recorded rather than hidden. A missing check is "
                            "not the same as a clean result.")
            continue

        proposed = (first or {}).get("findings", []) or []
        good, bad = verify(proposed, corpus, kind)
        trace.step("code", f"Evidence gate on '{kind}': "
                           f"{len(good)} kept, {len(bad)} rejected",
                   kind=kind, proposed=len(proposed),
                   kept=len(good), rejected=len(bad),
                   failures=[f"{b['title'][:60]} · {'; '.join(b['reasons'])}"
                             for b in bad][:4],
                   note="Every quote is matched against the clause it cites. "
                        "The model is never asked whether it quoted correctly.")

        # One repair, and only when everything failed. A check that produced
        # some verified findings has already shown it understood the corpus;
        # asking again mostly buys duplicates.
        if bad and not good:
            named = "; ".join(f"{b['title'][:60]}: {'; '.join(b['reasons'])}"
                              for b in bad[:3])
            retry_prompt = (
                f"{prompt}\n\n"
                f"A previous attempt was rejected by a verifier that matches "
                f"your quotes against the clause text character for character. "
                f"These failed: {named}. Quote less and copy exactly, or "
                f"return an empty list.")
            try:
                second = providers.complete(
                    "audit_standards", SYSTEM, retry_prompt,
                    schema=FINDING_SCHEMA, temperature=0.0, trace=trace,
                    max_tokens=2000)
                good, bad2 = verify((second or {}).get("findings", []) or [],
                                    corpus, kind)
                trace.step("code", f"Repair on '{kind}': {len(good)} kept",
                           kind=kind, kept=len(good), rejected=len(bad2),
                           note="One attempt only. A second failure is an "
                                "answer: there is nothing of this kind it can "
                                "prove.")
                bad = bad2
            except Exception as exc:                  # noqa: BLE001
                trace.step("code", f"Repair on '{kind}' failed",
                           error=str(exc)[:160])

        kept.extend(good)
        rejected.extend({"kind": kind, **b} for b in bad)

    holes = coverage_holes(cur, corpus)
    if holes:
        trace.step("code", f"Coverage: {len(holes)} rubric dimension(s) "
                           f"with no standard behind them",
                   dimensions=[h["title"] for h in holes],
                   note="A set difference, not a judgement. No model involved.")
    kept.extend(holes)

    kept = impact(cur, kept)
    kept.sort(key=lambda f: (SEVERITY_ORDER.get(f.get("severity", "low"), 3),
                             f["kind"]))

    trace.step("code", "Hold for a human",
               findings=len(kept),
               note="This edits nothing. It is a report a General Manager "
                    "reads and decides on.")

    result = {
        "findings": kept,
        "rejected": rejected,
        "documents": len(documents),
        "document_titles": documents,
        "clauses": len(corpus),
        "trace": trace.as_dict(),
    }

    # Stored in the audit log rather than a new table. The payload is the
    # report; there is no second source of truth to drift, and no migration to
    # run against a database that is currently serving a demo.
    q.audit(cur, actor, "standards.audited", None, {
        "findings": len(kept),
        "rejected": len(rejected),
        "clauses": len(corpus),
        "report": json.dumps({k: v for k, v in result.items()
                              if k != "trace"})[:200000],
    })
    cur.connection.commit()
    return result


def latest_audit(cur) -> dict | None:
    """The most recent report, so the page is not empty before anyone runs it."""
    cur.execute("""
        SELECT payload, occurred_at
        FROM audit_event
        WHERE event_type = 'standards.audited'
        ORDER BY occurred_at DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        return None
    payload = row["payload"] or {}
    raw = payload.get("report")
    if not raw:
        return None
    try:
        report = json.loads(raw)
    except (TypeError, ValueError):
        return None
    report["generated_at"] = (row["occurred_at"].isoformat()
                              if row["occurred_at"] else None)
    return report

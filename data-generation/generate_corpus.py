"""
generate_corpus.py
==================
Builds a complete, deterministic demo dataset for The Coaching Engine, grounded
in the patterns extracted from the four real SOP sources (see sop_patterns.py).

Everything is seeded, so the same command always produces the same demo. That
matters: NFR N12 requires the demo state to be restorable in under five minutes,
and hand-crafted demo data does not survive a redeploy the night before.

Outputs (into ./output):
    sop_corpus.json      chunked standards with citation metadata, ready to embed
    staff.json           12 staff personas across two departments
    incidents.json       shift debriefs in first-person spoken register
    observations.json    manager floor observations with per-dimension ratings
    attempts.json        practice attempts with per-dimension BARS scores
    transfer_gaps.json   computed gap + quadrant per staff per dimension
    golden_set.jsonl     evaluation items, including abstain and adversarial cases
    seed.sql             Postgres seed matching 02A-LLD-Data-Model
    SUMMARY.md           what was generated and how to check it

Usage:
    python generate_corpus.py
    python generate_corpus.py --seed 42 --outdir output
"""

from __future__ import annotations

import argparse
import json
import os
import random
import textwrap
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timedelta

import sop_patterns as P

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROPERTY = {
    "id": "prop-dublin-01",
    "name": "The Liffey Court Hotel",      # fictional; real property anonymised
    "country_code": "IE",
    "star_rating": 4,
    "room_count": 120,
}

WINDOW_END = date(2026, 9, 11)             # the Friday before the pitch
WINDOW_DAYS = 28                           # overridden by --window-days

# The demo narrative, fixed. Everything else is generated around it.
DEMO = {
    "blocked_staff": "Diego",              # strong practice, weak floor -> BLOCKED
    "competent_staff": "Aoife",            # strong both -> COMPETENT (the control)
    "manager": "Marta",
    "cohort_situation": "room_not_ready",
    "cohort_size": 9,
    "cohort_dept": "front_office",
    # A situation too rare to report, and the reason k-anonymity is not a
    # slide. Three people in eight weeks, all in one department: publishing
    # "3 staff reported guest abuse in F&B" to a team of eighteen identifies
    # them to anyone who works the rota, whatever the interface claims. It is
    # suppressed, and the fact of suppression is shown instead.
    #
    # Deliberately a welfare matter rather than a performance one, because
    # that is where re-identification actually costs somebody something.
    "rare_situation": "guest_abuse_toward_staff",
    "rare_count": 3,
    "rare_dept": "f_and_b",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    id: str
    document_id: str
    document_title: str
    source_ref: str            # S1..S4 - provenance back to Mary-Susan's extract
    doc_type: str              # standard | procedure | template | culture
    department: str            # front_office | f_and_b | all
    section_path: str
    ordinal: int
    step_number: int | None
    content: str
    dimensions: list[str] = field(default_factory=list)


@dataclass
class Staff:
    id: str
    name: str
    department: str
    role: str                  # staff | manager | ld_admin
    persona: str
    tenure_months: int


@dataclass
class Incident:
    id: str
    staff_id: str
    staff_name: str
    occurred_at: str
    situation_type: str
    guest_emotion: str
    staff_actions: list[str]
    outcome: str
    transcript: str            # redacted, first-person, spoken register
    dimensions_touched: list[str]
    grounding_chunk_id: str | None    # None = deliberate abstain case


@dataclass
class Attempt:
    id: str
    staff_id: str
    staff_name: str
    scenario_title: str
    completed_at: str
    scores: dict               # dimension -> 1..5 or None
    turns: int


@dataclass
class Observation:
    id: str
    staff_id: str
    staff_name: str
    manager_name: str
    observed_at: str
    context: str
    what_happened: str
    ratings: dict              # dimension -> 1..5 or None


# ---------------------------------------------------------------------------
# 1. The standards corpus
# ---------------------------------------------------------------------------

def build_corpus() -> list[Chunk]:
    """Turn the extracted SOP patterns into retrievable, citable chunks.

    Chunking rule from 02E-LLD: an ordered procedure is NEVER split. Each step of
    A.L.O.U.D. and of the nine-step complaint procedure becomes its own chunk with
    step_number set, because the demo claim 'you skipped step 3' has to resolve to
    a real numbered clause.
    """
    chunks: list[Chunk] = []
    n = 0

    def add(**kw):
        nonlocal n
        n += 1
        chunks.append(Chunk(id=f"chunk-{n:03d}", ordinal=n, **kw))

    # --- A.L.O.U.D., one chunk per step (S4, F&B) --------------------------
    for num, letter, title, body in P.ALOUD["steps"]:
        add(document_id="sop-fnb-complaint",
            document_title="Complaint Handling (A.L.O.U.D.)",
            source_ref=P.ALOUD["source"],
            doc_type="procedure", department="f_and_b",
            section_path=f"Complaint Handling > A.L.O.U.D. > Step {num}: {title}",
            step_number=num,
            content=f"{letter} - {title}. {body}",
            dimensions=["service_recovery", "empathy"])

    # --- Nine-step complaint procedure (S2, front office) -----------------
    for num, body in P.COMPLAINT_NINE_STEP["steps"]:
        dims = ["service_recovery"]
        if num in (1, 4, 5):
            dims.append("empathy")
        if num == 2:
            dims.append("composure")
        add(document_id="sop-foh-complaint",
            document_title="Complaint Handling Procedure",
            source_ref=P.COMPLAINT_NINE_STEP["source"],
            doc_type="procedure", department="front_office",
            section_path=f"Complaint Handling > Step {num}",
            step_number=num, content=body, dimensions=dims)

    # --- The Service Promise (S2) -----------------------------------------
    for i, principle in enumerate(P.SERVICE_PROMISE["principles"], start=1):
        add(document_id="sop-service-promise",
            document_title="The Service Promise",
            source_ref=P.SERVICE_PROMISE["source"],
            doc_type="standard", department="all",
            section_path=f"Service Promise > Principle {i}",
            step_number=i, content=principle,
            dimensions=["communication", "empathy"])

    # --- Professional ethic (S4 SOP02) ------------------------------------
    for i, line in enumerate(P.PROFESSIONAL_ETHIC["prohibited"], start=1):
        add(document_id="sop02-professional-ethic",
            document_title="Professional Ethic While On Duty",
            source_ref=P.PROFESSIONAL_ETHIC["source"],
            doc_type="standard", department="all",
            section_path=f"Professional Ethic > Prohibited > {i}",
            step_number=None, content=line, dimensions=["composure"])
    for i, line in enumerate(P.PROFESSIONAL_ETHIC["required"], start=1):
        add(document_id="sop02-professional-ethic",
            document_title="Professional Ethic While On Duty",
            source_ref=P.PROFESSIONAL_ETHIC["source"],
            doc_type="standard", department="all",
            section_path=f"Professional Ethic > Required > {i}",
            step_number=None, content=line, dimensions=["composure", "communication"])

    # --- Positive alternatives (S2/S3) ------------------------------------
    for i, (avoid, use) in enumerate(P.POSITIVE_ALTERNATIVES["substitutions"], start=1):
        add(document_id="sop-positive-alternatives",
            document_title="Positive Alternatives and Outcomes",
            source_ref=P.POSITIVE_ALTERNATIVES["source"],
            doc_type="standard", department="all",
            section_path=f"Positive Alternatives > {i}",
            step_number=None,
            content=f"Never say '{avoid}'. Instead: {use}.",
            dimensions=["communication"])

    # --- Anticipation triggers (S4) ---------------------------------------
    for i, trig in enumerate(P.ANTICIPATION_TRIGGERS["triggers"], start=1):
        add(document_id="sop-managing-your-station",
            document_title="Managing Your Station",
            source_ref=P.ANTICIPATION_TRIGGERS["source"],
            doc_type="procedure", department="f_and_b",
            section_path=f"Managing Your Station > Trigger {i}",
            step_number=i, content=trig, dimensions=["anticipation"])

    # --- Service timings (S4 SOP05) ---------------------------------------
    for i, (key, body) in enumerate(P.ELEVEN_STEPS_TIMINGS["timings"], start=1):
        add(document_id="sop05-eleven-steps",
            document_title="11 Steps of Service",
            source_ref=P.ELEVEN_STEPS_TIMINGS["source"],
            doc_type="procedure", department="f_and_b",
            section_path=f"11 Steps of Service > {i}. {key}",
            step_number=i, content=body,
            dimensions=["anticipation", "communication"])

    # --- THE AUTHORITY BOUNDARY -------------------------------------------
    # F&B: documented. This is what makes the front-office absence provable.
    for i, rule in enumerate(P.AUTHORITY_BOUNDARY["f_and_b"]["rules"], start=1):
        add(document_id="sop-fnb-complaint",
            document_title="Complaint Handling (A.L.O.U.D.)",
            source_ref="S4",
            doc_type="procedure", department="f_and_b",
            section_path=f"Complaint Handling > Authority and Approval > {i}",
            step_number=None, content=rule,
            dimensions=["service_recovery"])

    # --- Escalation rules --------------------------------------------------
    for i, (src, ref, rule) in enumerate(P.ESCALATION_RULES, start=1):
        add(document_id="sop-escalation",
            document_title="Escalation and Logging",
            source_ref=src,
            doc_type="procedure", department="all",
            section_path=f"Escalation > Rule {i}",
            step_number=None, content=rule,
            dimensions=["service_recovery"])

    # --- Culture / value statements (S1, S3) - deliberately vague ----------
    # These exist so the cite gate has plausible-but-wrong chunks to reject.
    for i, line in enumerate([
        "All team members anticipate guest needs.",
        "All team members to deliver a positive experience for all customers.",
        "Instil a culture where guest expectations are anticipated and exceeded.",
        "Guests choose a hotel because they feel in good hands.",
        "Create acts of kindness that are voluntary, unscripted and spontaneous.",
    ], start=1):
        add(document_id="culture-deck",
            document_title="Culture and Values",
            source_ref="S1/S3",
            doc_type="culture", department="all",
            section_path=f"Culture > Statement {i}",
            step_number=None, content=line,
            dimensions=["anticipation", "empathy"])

    return chunks


# ---------------------------------------------------------------------------
# 2. Staff
# ---------------------------------------------------------------------------

# Order is load-bearing. Ids are positional (staff-001, staff-002, ...), the
# demo narrative names people by id, and the frontend was built against these,
# so NEW NAMES ARE ONLY EVER APPENDED. Reordering this list silently reassigns
# every staff member's identity and every stored score with it.
FRONT_OFFICE_NAMES = ["Diego", "Niamh", "Tomasz", "Rachel", "Kwame",
                      "Lucia", "Sean", "Priya", "Andrei",
                      # appended for --scale
                      "Yusuf", "Katarzyna", "Emeka", "Siobhan", "Mateusz",
                      "Adaeze", "Ciaran", "Ingrid", "Rafal", "Nuala",
                      "Tomas", "Blessing", "Orla", "Hassan", "Petra",
                      "Declan", "Amara", "Lukasz", "Roisin", "Farid"]
FNB_NAMES = ["Aoife", "Marek", "Chloe", "Bogdan",
             # appended for --scale
             "Giulia", "Padraig", "Zofia", "Kwabena", "Eimear",
             "Dmytro", "Sinead", "Obi", "Magda", "Fionn",
             "Leila", "Cathal", "Anca", "Jibril", "Maeve",
             "Piotr", "Naoise", "Chidi", "Grainne", "Elif"]

PERSONAS = [
    "new starter, six weeks in, follows the script closely",
    "confident but improvises around the standard",
    "long tenure, efficient, occasionally clipped under pressure",
    "English as a second language, careful and precise",
    "strong with regulars, less sure with complaints",
]


def build_staff(rng: random.Random, front_office: int | None = None,
                fnb: int | None = None) -> list[Staff]:
    """Build the roster.

    Defaults reproduce the original thirteen exactly, so an unscaled run is
    byte-identical to what is already seeded and deployed.
    """
    front = FRONT_OFFICE_NAMES[:front_office] if front_office else FRONT_OFFICE_NAMES[:9]
    food = FNB_NAMES[:fnb] if fnb else FNB_NAMES[:4]
    staff: list[Staff] = []
    i = 0
    for name in front:
        i += 1
        staff.append(Staff(
            id=f"staff-{i:03d}", name=name, department="front_office", role="staff",
            persona=("strong in practice, freezes with real guests"
                     if name == DEMO["blocked_staff"] else rng.choice(PERSONAS)),
            tenure_months=rng.randint(2, 48)))
    for name in food:
        i += 1
        staff.append(Staff(
            id=f"staff-{i:03d}", name=name, department="f_and_b", role="staff",
            persona=("consistent in practice and on the floor"
                     if name == DEMO["competent_staff"] else rng.choice(PERSONAS)),
            tenure_months=rng.randint(2, 48)))
    i += 1
    staff.append(Staff(id=f"staff-{i:03d}", name=DEMO["manager"], department="front_office",
                       role="manager", persona="duty manager, ~40 reports, time-poor",
                       tenure_months=61))
    i += 1
    staff.append(Staff(id=f"staff-{i:03d}", name="Fiona", department="all",
                       role="ld_admin", persona="L&D lead, part-time across two properties",
                       tenure_months=30))
    return staff


# ---------------------------------------------------------------------------
# 3. Incidents - first-person, spoken register, redacted
# ---------------------------------------------------------------------------

# Templates written in the register the SOPs imply: tired, mid-sentence, unpolished.
# Placeholders are already in the typed-redaction form from 02E-LLD.
INCIDENT_TEMPLATES = {
    "guest_abuse_toward_staff": [
        "Table by the window got very personal with me when I said the "
        "kitchen had closed. Not about the food, about me. I finished the "
        "shift but I did not say anything to anyone at the time.",
        "One of the guests at the bar kept making comments. I laughed it off "
        "because it was busy and I did not want a scene, but it stayed with "
        "me on the way home.",
        "A guest raised his voice at me in front of the whole section over a "
        "bill that was correct. [MANAGER_NAME] was not on the floor and I did "
        "not want to pull anyone away, so I just took it.",
    ],
    "room_not_ready": [
        "Had a guest in at three, room wasn't ready, [GUEST_NAME] was not happy at all. "
        "I said sorry and offered {offer} but she just got more annoyed and in the end I "
        "got {manager}. I honestly didn't know what I was allowed to give her.",
        "Arrival at half two, room still being turned. I explained and offered {offer}. "
        "Guest asked what else I could do and I didn't have an answer so I went and found "
        "{manager}.",
        "[GUEST_NAME] came in early, room not ready, and I could tell straight away she'd "
        "had a long journey. Apologised, offered {offer}, she wanted something more and I "
        "wasn't sure what I could authorise so I escalated it.",
    ],
    "service_delay_and_order_error": [
        "Table [ROOM] waited about forty minutes and then the starter never came at all. "
        "I apologised and comped the dessert and let {manager} know after.",
        "Mains came out late and one was wrong. I said sorry straight away, took it back, "
        "and offered a complimentary coffee. Told {manager} at the end of service.",
    ],
    "service_delay": [
        "Kitchen was backed up, table waiting nearly half an hour for mains. I kept going "
        "back to update them which helped a bit. Comped a round of coffees.",
    ],
    "billing_dispute": [
        "[GUEST_NAME] checking out disputed a charge on the bill. I explained where it came "
        "from but he wasn't having it. I couldn't take it off myself so I called {manager}.",
    ],
    "noise_complaint": [
        "Guest rang down about noise from the function room. I apologised and said I'd look "
        "into it. Wasn't really sure what I could offer so I just said sorry again.",
    ],
    "system_down": [
        "PMS went down during a busy check-in. Explained to everyone it'd take a bit longer "
        "and did them manually. People were mostly fine about it once I told them what was "
        "happening.",
    ],
    "allergen_query": [
        "Guest asked about a nut allergy on one of the specials. I checked the folder but "
        "wasn't fully sure so I went to the kitchen. Took a while and they were waiting.",
    ],
}

OFFERS = ["a drink at the bar", "a voucher for the bar", "tea and coffee in the lounge",
          "to store the bags", "a complimentary coffee"]


def build_incidents(staff: list[Staff], corpus: list[Chunk],
                    rng: random.Random) -> list[Incident]:
    incidents: list[Incident] = []
    by_dept = {s.department: [] for s in staff}
    for s in staff:
        if s.role == "staff":
            by_dept.setdefault(s.department, []).append(s)

    # Index chunks for grounding lookups
    def find_chunk(dept: str, dims: list[str]) -> str | None:
        cands = [c for c in corpus
                 if c.department in (dept, "all")
                 and c.doc_type in ("procedure", "standard")
                 and any(d in c.dimensions for d in dims)]
        return cands[0].id if cands else None

    n = 0

    def add(staff_obj, sit_type, day_offset, transcript, emotion, actions,
            outcome, dims, grounding):
        nonlocal n
        n += 1
        incidents.append(Incident(
            id=f"inc-{n:03d}", staff_id=staff_obj.id, staff_name=staff_obj.name,
            occurred_at=(WINDOW_END - timedelta(days=day_offset)).isoformat(),
            situation_type=sit_type, guest_emotion=emotion, staff_actions=actions,
            outcome=outcome, transcript=transcript, dimensions_touched=dims,
            grounding_chunk_id=grounding))

    # --- THE COHORT: nine front-office staff, same situation, same week ----
    cohort = [s for s in by_dept["front_office"]][:DEMO["cohort_size"]]
    for idx, s in enumerate(cohort):
        tpl = INCIDENT_TEMPLATES["room_not_ready"][idx % 3]
        text = tpl.format(offer=rng.choice(OFFERS), manager=DEMO["manager"])
        add(s, "room_not_ready", rng.randint(1, 7), text,
            rng.choice(["frustrated", "angry", "upset"]),
            ["apologised", "offered_compensation", "escalated"],
            "escalated", ["service_recovery", "empathy"],
            # deliberately None: front office has NO documented authority rule
            None)

    # --- The rare one, assigned to a fixed handful ------------------------
    #
    # Outside the random pool on purpose. Drawn randomly across forty-eight
    # staff it would land on a dozen of them and clear k=5, which is exactly
    # the outcome that makes a k-anonymity demo prove nothing.
    rare_pool = [s for s in staff
                 if s.role == "staff" and s.department == DEMO["rare_dept"]]
    for idx, s in enumerate(rare_pool[:DEMO["rare_count"]]):
        tpl = INCIDENT_TEMPLATES[DEMO["rare_situation"]][idx % 3]
        add(s, DEMO["rare_situation"], rng.randint(1, WINDOW_DAYS),
            tpl.replace("[MANAGER_NAME]", DEMO["manager"]),
            "upset", ["finished the shift", "did not report it at the time"],
            "unresolved",
            # Composure and empathy are the dimensions a reviewer would reach
            # for, and both are the wrong frame: this is a welfare matter, not
            # a performance one.
            ["composure"],
            # No standard covers it, which is the second finding here: the
            # property documents what staff owe guests and not the reverse.
            None)

    # --- Everyone else, spread across the window --------------------------
    for s in staff:
        if s.role != "staff":
            continue
        pool = [k for k, v in P.SITUATION_TYPES.items()
                if s.department in v["depts"] and k in INCIDENT_TEMPLATES
                and k != "room_not_ready"]
        # Enough volume that the golden set reaches 45 items after filtering
        for _ in range(rng.randint(3, 5)):
            sit = rng.choice(pool)
            tpl = rng.choice(INCIDENT_TEMPLATES[sit])
            text = tpl.format(offer=rng.choice(OFFERS), manager=DEMO["manager"])
            dims = ["service_recovery"] if "complaint" in sit or "error" in sit \
                else ["communication", "anticipation"]
            grounding = (None if sit == "allergen_query"      # confirmed corpus gap
                         else find_chunk(s.department, dims))
            add(s, sit, rng.randint(1, WINDOW_DAYS), text,
                rng.choice(["calm", "frustrated", "angry", "upset", "resigned"]),
                rng.sample(["apologised", "offered_compensation", "explained",
                            "escalated", "resolved_self"], k=2),
                rng.choice(["resolved", "partially_resolved", "unresolved", "escalated"]),
                dims, grounding)

    return incidents


# ---------------------------------------------------------------------------
# 4. Practice attempts and floor observations - engineered to create the gap
# ---------------------------------------------------------------------------

SCENARIOS = [
    ("Room not ready at check-in", "front_office", ["service_recovery", "empathy", "composure"]),
    ("Guest disputes a charge at checkout", "front_office", ["service_recovery", "communication"]),
    ("Late main course, wrong order", "f_and_b", ["service_recovery", "empathy"]),
    ("Guest asks about allergens", "f_and_b", ["communication", "anticipation"]),
    ("Noise complaint at 23:00", "front_office", ["empathy", "composure"]),
]

DIMS = list(P.DIMENSIONS.keys())


# Which dimensions a situation can actually evidence. A room-not-ready
# complaint gives you nothing to say about upselling; a local-area enquiry
# gives you nothing to say about service recovery.
#
# This exists because of the null rule in 02D section 2.4: a dimension with no
# evidence must score NULL, never the midpoint. Defaulting an unevidenced
# dimension to 3 drags every mean toward the middle, compresses the transfer
# gap toward zero, and makes the product look like it has nothing to say.
SITUATION_DIMENSIONS = {
    "room_not_ready":                 {"service_recovery", "empathy", "composure"},
    "service_delay_and_order_error":  {"service_recovery", "empathy", "composure"},
    "service_delay":                  {"service_recovery", "communication", "anticipation"},
    "billing_dispute":                {"service_recovery", "communication", "composure"},
    "noise_complaint":                {"service_recovery", "empathy"},
    "booking_error":                  {"service_recovery", "communication"},
    "special_request_failure":        {"empathy", "anticipation"},
    "order_error":                    {"service_recovery", "empathy"},
    "system_down":                    {"communication", "composure", "anticipation"},
    "local_area_enquiry":             {"communication", "anticipation"},
    "allergen_query":                 {"communication", "anticipation"},
    "other":                          {"communication"},
}

# Non-complaint practice scenarios and observation contexts declare their own
# evidenced set, so nothing is scored on a dimension the situation never tested.
DEFAULT_EVIDENCED = {"communication", "composure"}


def _score_profile(name: str, dept: str, source: str, rng: random.Random,
                   evidenced: set[str] | None = None) -> dict:
    """Per-dimension scores, with unevidenced dimensions returned as None.

    Diego is engineered into the BLOCKED quadrant and Aoife into COMPETENT so
    the demo narrative is reproducible; everyone else is drawn around a
    plausible middle.

    `evidenced` is the set of dimensions the situation actually tested. Anything
    outside it scores None rather than a number, which is the documented rule
    and the thing that keeps a mean honest.
    """
    evidenced = evidenced if evidenced is not None else set(DIMS)
    out = {}
    for d in DIMS:
        if d not in evidenced:
            out[d] = None                 # not evidenced by this situation
            continue

        if name == DEMO["blocked_staff"]:
            base = 4.6 if source == "practice" else 2.0
            if d != "service_recovery":
                base = 4.0 if source == "practice" else 3.2
        elif name == DEMO["competent_staff"]:
            base = 4.3 if source == "practice" else 4.1
        else:
            base = rng.uniform(2.4, 4.4)

        # F&B staff score better on service recovery: they have a documented
        # framework (A.L.O.U.D.) and front office does not. This is the point.
        if d == "service_recovery" and dept == "f_and_b" and source == "floor":
            base += 0.6

        out[d] = max(1, min(5, round(base + rng.uniform(-0.4, 0.4))))
    return out


def build_attempts(staff: list[Staff], rng: random.Random) -> list[Attempt]:
    attempts, n = [], 0
    for s in staff:
        if s.role != "staff":
            continue
        for _ in range(rng.randint(3, 5)):
            n += 1
            title, dept, dims = rng.choice(
                [sc for sc in SCENARIOS if sc[1] == s.department] or SCENARIOS)
            attempts.append(Attempt(
                id=f"att-{n:03d}", staff_id=s.id, staff_name=s.name,
                scenario_title=title,
                completed_at=(WINDOW_END - timedelta(days=rng.randint(1, WINDOW_DAYS))).isoformat(),
                # A scenario only tests what it was designed to test. Scoring
                # outside target_dimensions would be inventing evidence.
                scores=_score_profile(s.name, s.department, "practice", rng,
                                      evidenced=set(dims)),
                turns=rng.randint(6, 10)))
    return attempts


# Each context carries the dimensions a manager could actually have observed
# in it. A busy check-in queue says nothing about service recovery, because no
# service failure occurred.
OBS_CONTEXTS = {
    "front_office": [
        ("Guest complaint at front desk, room not ready at 3pm",
         "Froze, then escalated to me without attempting recovery herself.",
         {"service_recovery", "empathy", "composure"}),
        ("Busy check-in queue, four deep",
         "Kept the queue informed and stayed composed. Handled it well.",
         {"communication", "composure", "anticipation"}),
        ("Checkout billing query",
         "Explained clearly but did not offer any goodwill gesture, went straight to me.",
         {"service_recovery", "communication"}),
    ],
    "f_and_b": [
        ("Late mains on a table of six",
         "Apologised, acknowledged the specific delay, comped coffees. Textbook A.L.O.U.D.",
         {"service_recovery", "empathy", "composure"}),
        ("Guest unhappy with wine recommendation",
         "Listened without interrupting and offered an alternative. Good.",
         {"empathy", "communication"}),
    ],
}


def build_observations(staff: list[Staff], rng: random.Random) -> list[Observation]:
    obs, n = [], 0
    for s in staff:
        if s.role != "staff":
            continue
        for _ in range(rng.randint(1, 3)):
            n += 1
            ctx, what, dims = rng.choice(OBS_CONTEXTS[s.department])
            if s.name == DEMO["blocked_staff"]:
                ctx, what, dims = OBS_CONTEXTS["front_office"][0]
            obs.append(Observation(
                id=f"obs-{n:03d}", staff_id=s.id, staff_name=s.name,
                manager_name=DEMO["manager"],
                observed_at=(WINDOW_END - timedelta(days=rng.randint(1, 14))).isoformat(),
                context=ctx, what_happened=what,
                ratings=_score_profile(s.name, s.department, "floor", rng,
                                       evidenced=dims)))
    return obs


# ---------------------------------------------------------------------------
# 5. Transfer gaps
# ---------------------------------------------------------------------------

STRONG, WEAK = 3.5, 2.5


def quadrant(p, f):
    if p is None or f is None:
        return None
    ps, fs = p >= STRONG, f >= STRONG
    if ps and fs:
        return "competent"
    if ps and not fs:
        return "blocked"
    if not ps and fs:
        return "recalibrate"
    return "skill_gap"


def build_gaps(staff, attempts, observations):
    gaps = []
    for s in staff:
        if s.role != "staff":
            continue
        for d in DIMS:
            pv = [a.scores[d] for a in attempts if a.staff_id == s.id and a.scores.get(d)]
            fv = [o.ratings[d] for o in observations if o.staff_id == s.id and o.ratings.get(d)]
            if not pv or not fv:
                gaps.append({"staff_id": s.id, "staff_name": s.name, "dimension": d,
                             "practice_mean": round(sum(pv)/len(pv), 2) if pv else None,
                             "floor_mean": round(sum(fv)/len(fv), 2) if fv else None,
                             "gap": None, "quadrant": None,
                             "status": "insufficient_evidence"})
                continue
            pm, fm = sum(pv)/len(pv), sum(fv)/len(fv)
            gaps.append({"staff_id": s.id, "staff_name": s.name, "dimension": d,
                         "practice_mean": round(pm, 2), "floor_mean": round(fm, 2),
                         "gap": round(pm - fm, 2), "quadrant": quadrant(pm, fm),
                         "practice_n": len(pv), "floor_n": len(fv), "status": "ok"})
    return gaps


# ---------------------------------------------------------------------------
# 6. Golden set
# ---------------------------------------------------------------------------

def build_golden_set(incidents, corpus, rng):
    """35 grounded + 5 must-abstain + 5 adversarial near-miss = 45 items.

    ground_truth_scores is left NULL on purpose. Mary-Susan fills it in by hand;
    that is what makes it ground truth rather than more generated text.
    """
    items = []
    grounded = [i for i in incidents if i.grounding_chunk_id][:35]
    ungrounded = [i for i in incidents if not i.grounding_chunk_id][:5]

    for i in grounded:
        items.append({"id": f"gs-{len(items)+1:03d}", "kind": "grounded",
                      "incident_id": i.id, "transcript": i.transcript,
                      "situation_type": i.situation_type,
                      "expected_grounding": i.grounding_chunk_id,
                      "must_abstain": False,
                      "ground_truth_scores": {d: None for d in DIMS}})

    for i in ungrounded:
        items.append({"id": f"gs-{len(items)+1:03d}", "kind": "must_abstain",
                      "incident_id": i.id, "transcript": i.transcript,
                      "situation_type": i.situation_type,
                      "expected_grounding": None, "must_abstain": True,
                      "abstain_reason": "no applicable standard in corpus",
                      "ground_truth_scores": {d: None for d in DIMS}})

    # Adversarial: plausible-but-wrong chunk must NOT be cited
    culture = [c for c in corpus if c.doc_type == "culture"]
    for k in range(5):
        src = grounded[k]
        items.append({"id": f"gs-{len(items)+1:03d}", "kind": "adversarial_near_miss",
                      "incident_id": src.id, "transcript": src.transcript,
                      "situation_type": src.situation_type,
                      "expected_grounding": src.grounding_chunk_id,
                      "must_not_cite": culture[k % len(culture)].id,
                      "note": "vague culture statement must not be cited for a procedural failure",
                      "must_abstain": False,
                      "ground_truth_scores": {d: None for d in DIMS}})
    return items


# ---------------------------------------------------------------------------
# 7. SQL seed
# ---------------------------------------------------------------------------

def sql_escape(s):
    return s.replace("'", "''")


def build_sql(corpus, staff, incidents, attempts, observations):
    L = ["-- Generated by generate_corpus.py. Do not edit by hand.",
         "-- Matches the schema in 02A-LLD-Data-Model.", "BEGIN;", ""]
    L.append(f"INSERT INTO property (id, name, country_code, star_rating, room_count) "
             f"VALUES ('{PROPERTY['id']}', '{sql_escape(PROPERTY['name'])}', "
             f"'{PROPERTY['country_code']}', {PROPERTY['star_rating']}, {PROPERTY['room_count']});")
    L.append("")
    for s in staff:
        L.append(f"INSERT INTO staff_member (id, property_id, display_name, department, role) "
                 f"VALUES ('{s.id}', '{PROPERTY['id']}', '{sql_escape(s.name)}', "
                 f"'{s.department}', '{s.role}');")
    L.append("")
    for c in corpus:
        L.append(f"INSERT INTO sop_chunk (id, property_id, document_id, section_path, "
                 f"ordinal, step_number, content) VALUES ('{c.id}', '{PROPERTY['id']}', "
                 f"'{c.document_id}', '{sql_escape(c.section_path)}', {c.ordinal}, "
                 f"{c.step_number if c.step_number is not None else 'NULL'}, "
                 f"'{sql_escape(c.content)}');")
    L.append("")
    for o in observations:
        L.append(f"INSERT INTO observation (id, property_id, staff_id, observed_at, context, "
                 f"what_happened) VALUES ('{o.id}', '{PROPERTY['id']}', '{o.staff_id}', "
                 f"'{o.observed_at}', '{sql_escape(o.context)}', '{sql_escape(o.what_happened)}');")
    L += ["", "COMMIT;"]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260913)
    # Scale. The defaults reproduce the original thirteen-person, four-week
    # world exactly, so an unscaled run stays byte-identical to what is
    # already seeded and deployed.
    ap.add_argument("--front-office", type=int, default=9,
                    help=f"front office staff, 1-{len(FRONT_OFFICE_NAMES)}")
    ap.add_argument("--fnb", type=int, default=4,
                    help=f"food and beverage staff, 1-{len(FNB_NAMES)}")
    ap.add_argument("--window-days", type=int, default=28,
                    help="how many days of history to generate")
    ap.add_argument("--outdir", default="output")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, args.outdir)
    os.makedirs(out, exist_ok=True)

    corpus = build_corpus()
    # Applied before anything reads it: incident dates, attempt timestamps and
    # observation windows are all drawn against WINDOW_DAYS.
    global WINDOW_DAYS
    WINDOW_DAYS = args.window_days

    if args.front_office > len(FRONT_OFFICE_NAMES) or args.fnb > len(FNB_NAMES):
        raise SystemExit(
            f"Not enough names: {len(FRONT_OFFICE_NAMES)} front office and "
            f"{len(FNB_NAMES)} f&b are defined. Add more to the lists (append "
            f"only, never reorder: ids are positional).")
    if args.front_office < DEMO["cohort_size"]:
        # The cohort is the insight panel's whole reason to exist, and below
        # k=5 it would be suppressed anyway.
        raise SystemExit(
            f"--front-office must be at least {DEMO['cohort_size']}, the "
            f"engineered cohort size.")

    staff = build_staff(rng, args.front_office, args.fnb)
    incidents = build_incidents(staff, corpus, rng)
    attempts = build_attempts(staff, rng)
    observations = build_observations(staff, rng)
    gaps = build_gaps(staff, attempts, observations)
    golden = build_golden_set(incidents, corpus, rng)

    def dump(name, obj):
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)

    dump("sop_corpus.json", [asdict(c) for c in corpus])
    dump("staff.json", [asdict(s) for s in staff])
    dump("incidents.json", [asdict(i) for i in incidents])
    dump("attempts.json", [asdict(a) for a in attempts])
    dump("observations.json", [asdict(o) for o in observations])
    dump("transfer_gaps.json", gaps)

    with open(os.path.join(out, "golden_set.jsonl"), "w", encoding="utf-8") as f:
        for item in golden:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with open(os.path.join(out, "seed.sql"), "w", encoding="utf-8") as f:
        f.write(build_sql(corpus, staff, incidents, attempts, observations))

    # --- verification of the demo narrative -------------------------------
    diego = [g for g in gaps if g["staff_name"] == DEMO["blocked_staff"]
             and g["dimension"] == "service_recovery"][0]
    aoife = [g for g in gaps if g["staff_name"] == DEMO["competent_staff"]
             and g["dimension"] == "service_recovery"][0]
    cohort_n = len({i.staff_id for i in incidents
                    if i.situation_type == DEMO["cohort_situation"]})

    summary = textwrap.dedent(f"""\
        # Generated demo dataset

        Seed `{args.seed}`. Regenerate identically with:

            python generate_corpus.py --seed {args.seed}

        | Artefact | Count |
        |---|---|
        | SOP chunks | {len(corpus)} |
        | Staff | {len(staff)} |
        | Shift debriefs | {len(incidents)} |
        | Practice attempts | {len(attempts)} |
        | Floor observations | {len(observations)} |
        | Transfer-gap rows | {len(gaps)} |
        | Golden-set items | {len(golden)} |

        ## Demo narrative checks

        - **{DEMO['blocked_staff']}** (front office), service recovery:
          practice {diego['practice_mean']}, floor {diego['floor_mean']},
          gap **{diego['gap']}**, quadrant **{diego['quadrant']}**
        - **{DEMO['competent_staff']}** (F&B), service recovery:
          practice {aoife['practice_mean']}, floor {aoife['floor_mean']},
          gap **{aoife['gap']}**, quadrant **{aoife['quadrant']}**
        - Cohort on `{DEMO['cohort_situation']}`: **{cohort_n} distinct staff**
          (k-anonymity threshold is 5)

        ## The finding this dataset is built around

        Front-office incidents about `room_not_ready` carry
        `grounding_chunk_id: null` **on purpose**. The four real SOP sources
        document what F&B staff may offer without approval (A.L.O.U.D. authority
        rules, source S4) and document nothing equivalent for front office
        (confirmed gaps in S2 and S3). The agent should therefore classify the
        cohort as a **policy** gap, not nine behavioural problems.

        ## What still needs a human

        `golden_set.jsonl` has `ground_truth_scores` set to null for every
        dimension. **Mary-Susan hand-scores those.** Generated scores would make
        the evaluation circular and worthless.
        """)
    with open(os.path.join(out, "SUMMARY.md"), "w", encoding="utf-8") as f:
        f.write(summary)

    print(f"Wrote {len(corpus)} chunks, {len(staff)} staff, {len(incidents)} incidents, "
          f"{len(attempts)} attempts, {len(observations)} observations, "
          f"{len(golden)} golden items -> {out}")
    print(f"  {DEMO['blocked_staff']:6s} service_recovery: practice {diego['practice_mean']} "
          f"floor {diego['floor_mean']} gap {diego['gap']} -> {diego['quadrant']}")
    print(f"  {DEMO['competent_staff']:6s} service_recovery: practice {aoife['practice_mean']} "
          f"floor {aoife['floor_mean']} gap {aoife['gap']} -> {aoife['quadrant']}")
    print(f"  cohort on {DEMO['cohort_situation']}: {cohort_n} distinct staff")


if __name__ == "__main__":
    main()

"""
seed.py
=======
Load the generated demo dataset into Postgres.

The generator emits readable string ids (staff-001, chunk-014) because they are
easy to debug. The schema uses uuid. Rather than change either, we map string
to uuid with uuid5 over a fixed namespace: deterministic, so re-seeding
produces byte-identical ids and the demo is reproducible.

Connects as the database owner on purpose. Row level security does not apply to
the owner, which is what we want for seeding and emphatically not what we want
for the API, which connects as ce_app.

    python db/seed.py                 # wipe and reload
    python db/seed.py --verify        # report only, change nothing
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data-generation" / "output"
NS = uuid.UUID("6f4d1c2e-0000-4000-8000-000000000001")

DSN = os.environ.get(
    "SEED_DATABASE_URL",
    "postgresql://coaching:coaching@localhost:5433/coaching_engine",
)


def uid(s: str) -> uuid.UUID:
    """Stable string to uuid. Same input always yields the same id."""
    return uuid.uuid5(NS, s)


def load(name: str):
    with open(OUT / name, encoding="utf-8") as f:
        if name.endswith(".jsonl"):
            return [json.loads(line) for line in f if line.strip()]
        return json.load(f)


# ---------------------------------------------------------------------------
# BARS rubric. Anchors are lifted from the property's own frameworks:
# A.L.O.U.D. (S4), the nine-step complaint procedure (S2), the Service Promise
# (S2), Professional Ethic SOP02 (S2/S4) and the Managing Your Station
# triggers (S4). Mary-Susan owns revising these; the structure is what matters
# for the build.
# ---------------------------------------------------------------------------

RUBRIC = {
    "service_recovery": {
        "label": "Service Recovery",
        "description": "Whether the property's recovery sequence is followed under pressure.",
        "anchors": {
            5: "Acknowledges the specific inconvenience in the guest's own terms, owns it "
               "without deflecting, follows the A.L.O.U.D. sequence in order, resolves within "
               "their authority, and confirms the guest is satisfied before closing.",
            4: "Follows the sequence with minor omissions. Acknowledges before offering. "
               "Guest leaves satisfied.",
            3: "Apologises and offers a remedy, but the acknowledgement is generic rather than "
               "specific, or the sequence is partly inverted.",
            2: "Offers compensation before acknowledging the problem, or escalates without "
               "attempting recovery within their own authority.",
            1: "Does not acknowledge, deflects responsibility, or leaves the guest with no "
               "resolution path.",
        },
    },
    "empathy": {
        "label": "Empathy and Active Listening",
        "description": "Acknowledging the guest's actual experience rather than reciting an apology.",
        "anchors": {
            5: "Listens without interrupting, names the guest's feeling back to them accurately, "
               "and demonstrably adapts to their mood.",
            4: "Listens well and acknowledges feeling, though the reflection is slightly generic.",
            3: "Hears the guest out but responds to the facts rather than the feeling.",
            2: "Interrupts, or responds with a scripted apology that does not match what the "
               "guest actually said.",
            1: "Talks over the guest or dismisses the concern.",
        },
    },
    "communication": {
        "label": "Guest Communication",
        "description": "Clarity, tone and appropriate register, including positive alternatives.",
        "anchors": {
            5: "Clear, warm and unhurried. Never says no without offering an alternative. Uses "
               "the guest's name and sets accurate expectations.",
            4: "Clear and courteous, with the occasional missed opportunity to offer an "
               "alternative.",
            3: "Understandable but flat, or leaves the guest unsure what happens next.",
            2: "Uses negative phrasing ('no', 'I can't', 'I don't know') without an alternative.",
            1: "Unclear, abrupt, or leaves the guest with no idea what will happen.",
        },
    },
    "composure": {
        "label": "Composure and Professionalism",
        "description": "Holding the standard under pressure, including body language and register.",
        "anchors": {
            5: "Stays calm and present under real pressure. Full attention on the guest, does "
               "not take the complaint personally, and maintains the professional standard "
               "throughout.",
            4: "Composed, with a brief wobble that does not affect the guest.",
            3: "Visibly flustered but recovers and completes the interaction.",
            2: "Becomes defensive, or freezes and hands off without attempting to hold the "
               "situation.",
            1: "Argues with the guest or a colleague in front of them, or disengages entirely.",
        },
    },
    "anticipation": {
        "label": "Guest Anticipation",
        "description": "Noticing and acting on a need before it is stated.",
        "anchors": {
            5: "Spots the cue and acts before being asked. Sets an expectation proactively when "
               "unable to attend immediately.",
            4: "Notices most cues and responds promptly once they register.",
            3: "Responds well when asked, but rarely anticipates.",
            2: "Misses obvious cues; the guest has to ask twice.",
            1: "Does not observe the station or the guest at all.",
        },
    },
}

DIMS = list(RUBRIC.keys())

PROPERTY_ID = uid("prop-dublin-01")
RUBRIC_ID = uid("rubric-v1")


def wipe(cur):
    """Order matters: children before parents."""
    for table in [
        "verification_label", "verification", "recommendation_citation",
        "recommendation", "escalation", "cohort_pattern", "audit_event",
        "score", "observation_rating", "observation", "shift_debrief",
        "attempt_turn", "scenario_attempt", "scenario",
        "bars_anchor", "bars_dimension", "bars_rubric",
        "sop_chunk", "sop_document", "team_assignment", "staff_member",
        "property",
    ]:
        cur.execute(f"DELETE FROM {table}")


def seed(cur):
    staff = load("staff.json")
    corpus = load("sop_corpus.json")
    attempts = load("attempts.json")
    observations = load("observations.json")
    incidents = load("incidents.json")

    # --- property -----------------------------------------------------------
    cur.execute(
        "INSERT INTO property (id, name, country_code, star_rating, room_count) "
        "VALUES (%s,%s,%s,%s,%s)",
        (PROPERTY_ID, "The Liffey Court Hotel", "IE", 4, 120))

    # --- staff --------------------------------------------------------------
    by_name = {}
    for s in staff:
        sid = uid(s["id"])
        by_name[s["name"]] = sid
        cur.execute(
            "INSERT INTO staff_member (id, property_id, display_name, department, role) "
            "VALUES (%s,%s,%s,%s,%s)",
            (sid, PROPERTY_ID, s["name"], s["department"], s["role"]))

    manager_id = by_name["Marta"]
    for s in staff:
        if s["role"] == "staff":
            cur.execute(
                "INSERT INTO team_assignment (id, property_id, manager_id, staff_id) "
                "VALUES (%s,%s,%s,%s)",
                (uid(f"ta-{s['id']}"), PROPERTY_ID, manager_id, uid(s["id"])))

    # --- rubric -------------------------------------------------------------
    cur.execute(
        "INSERT INTO bars_rubric (id, property_id, version, is_active, authored_by) "
        "VALUES (%s,%s,%s,%s,%s)",
        (RUBRIC_ID, PROPERTY_ID, 1, True, "Mary-Susan McLoughlin"))

    dim_ids = {}
    for code, spec in RUBRIC.items():
        did = uid(f"dim-{code}")
        dim_ids[code] = did
        cur.execute(
            "INSERT INTO bars_dimension (id, rubric_id, code, label, description) "
            "VALUES (%s,%s,%s,%s,%s)",
            (did, RUBRIC_ID, code, spec["label"], spec["description"]))
        for level, text in spec["anchors"].items():
            cur.execute(
                "INSERT INTO bars_anchor (id, dimension_id, level, anchor_text) "
                "VALUES (%s,%s,%s,%s)",
                (uid(f"anchor-{code}-{level}"), did, level, text))

    # --- SOP corpus ---------------------------------------------------------
    seen_docs = set()
    for c in corpus:
        doc_key = c["document_title"]
        if doc_key not in seen_docs:
            seen_docs.add(doc_key)
            cur.execute(
                "INSERT INTO sop_document (id, property_id, title, doc_type, department, "
                "source_ref, version, is_synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (uid(f"doc-{c['document_title']}"), PROPERTY_ID,
                 c["document_title"], c["doc_type"], c["department"],
                 c["source_ref"], 1, True))
        cur.execute(
            "INSERT INTO sop_chunk (id, property_id, document_id, section_path, ordinal, "
            "step_number, content) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (uid(c["id"]), PROPERTY_ID,
             uid(f"doc-{c['document_title']}"),
             c["section_path"], c["ordinal"], c["step_number"], c["content"]))

    # --- scenarios and attempts --------------------------------------------
    scenario_ids = {}
    for a in attempts:
        title = a["scenario_title"]
        if title not in scenario_ids:
            sc_id = uid(f"scenario-{title}")
            scenario_ids[title] = sc_id
            cur.execute(
                "INSERT INTO scenario (id, property_id, origin, title, situation, "
                "guest_persona, target_dimensions) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (sc_id, PROPERTY_ID, "library", title, title,
                 json.dumps({"mood": "frustrated"}),
                 [d for d, v in a["scores"].items() if v is not None]))

    n_scores = 0
    for a in attempts:
        aid = uid(a["id"])
        cur.execute(
            "INSERT INTO scenario_attempt (id, property_id, scenario_id, staff_id, status, "
            "rubric_id, completed_at, turn_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (aid, PROPERTY_ID, scenario_ids[a["scenario_title"]],
             uid(a["staff_id"]), "scored", RUBRIC_ID, a["completed_at"], a["turns"]))

        for dim, level in a["scores"].items():
            if level is None:            # not evidenced by this scenario
                continue
            cur.execute(
                "INSERT INTO score (id, property_id, staff_id, dimension_id, rubric_id, "
                "source, level, attempt_id, scored_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (uid(f"score-p-{a['id']}-{dim}"), PROPERTY_ID, uid(a["staff_id"]),
                 dim_ids[dim], RUBRIC_ID, "practice", level, aid, a["completed_at"]))
            n_scores += 1

    # --- observations -------------------------------------------------------
    for o in observations:
        oid = uid(o["id"])
        cur.execute(
            "INSERT INTO observation (id, property_id, staff_id, manager_id, source, "
            "observed_at, context, what_happened, rubric_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (oid, PROPERTY_ID, uid(o["staff_id"]), manager_id, "manager",
             o["observed_at"], o["context"], o["what_happened"], RUBRIC_ID))

        for dim, level in o["ratings"].items():
            cur.execute(
                "INSERT INTO observation_rating (id, property_id, observation_id, "
                "dimension_id, level) VALUES (%s,%s,%s,%s,%s)",
                (uid(f"or-{o['id']}-{dim}"), PROPERTY_ID, oid, dim_ids[dim], level))
            if level is None:
                continue
            cur.execute(
                "INSERT INTO score (id, property_id, staff_id, dimension_id, rubric_id, "
                "source, level, observation_id, scored_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (uid(f"score-f-{o['id']}-{dim}"), PROPERTY_ID, uid(o["staff_id"]),
                 dim_ids[dim], RUBRIC_ID, "floor", level, oid, o["observed_at"]))
            n_scores += 1

    # --- shift debriefs -----------------------------------------------------
    for i in incidents:
        cur.execute(
            "INSERT INTO shift_debrief (id, property_id, staff_id, status, transcript, "
            "incident, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (uid(i["id"]), PROPERTY_ID, uid(i["staff_id"]), "extracted",
             i["transcript"],
             json.dumps({
                 "situation_type": i["situation_type"],
                 "guest_emotion": i["guest_emotion"],
                 "staff_actions": i["staff_actions"],
                 "outcome": i["outcome"],
                 "dimensions_touched": i["dimensions_touched"],
                 "grounding_chunk_id": i["grounding_chunk_id"],
             }),
             i["occurred_at"]))

    return {"staff": len(staff), "chunks": len(corpus), "attempts": len(attempts),
            "observations": len(observations), "debriefs": len(incidents),
            "scores": n_scores}


def verify(cur):
    cur.execute("""
        SELECT sm.display_name, bd.code,
               round(avg(s.level) FILTER (WHERE s.source='practice'), 2) AS practice,
               round(avg(s.level) FILTER (WHERE s.source='floor'), 2)    AS floor
        FROM score s
        JOIN staff_member sm ON sm.id = s.staff_id
        JOIN bars_dimension bd ON bd.id = s.dimension_id
        WHERE bd.code = 'service_recovery' AND sm.display_name IN ('Diego','Aoife')
        GROUP BY sm.display_name, bd.code ORDER BY sm.display_name
    """)
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if not args.verify:
                wipe(cur)
                counts = seed(cur)
                conn.commit()
                print("seeded: " + "  ".join(f"{k}={v}" for k, v in counts.items()))

            print("\ndemo narrative check:")
            for row in verify(cur):
                p, f = row["practice"], row["floor"]
                gap = round(float(p) - float(f), 2) if p and f else None
                print(f"  {row['display_name']:<6} service_recovery: "
                      f"practice {p}  floor {f}  gap {gap}")


if __name__ == "__main__":
    main()

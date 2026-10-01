"""
queries.py
==========
Read and write helpers. All SQL lives here so the routers stay thin and so
there is one place to look when a query returns something surprising.

Every function takes an already-configured cursor from db.session(actor), which
means row level security is already in force. Nothing here re-checks
permissions in Python: if a manager is not allowed to see a practice score, the
database returns no row and this code never learns it existed. That is the
point of putting the rule in the database.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

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
from coaching_engine.calibration import calibrate                      # noqa: E402
from coaching_engine.transfer_gap import Score, compute_gap, trend_slope  # noqa: E402

DIMENSIONS = ["service_recovery", "empathy", "communication",
              "composure", "anticipation"]


# ---------------------------------------------------------------- staff

def list_staff(cur):
    cur.execute("""
        SELECT id::text, display_name AS name, role, department
        FROM staff_member WHERE is_active ORDER BY display_name
    """)
    return cur.fetchall()


# Same namespace the seeder used, so a readable generator id maps to the same
# uuid it was stored under.
_NS = __import__("uuid").UUID("6f4d1c2e-0000-4000-8000-000000000001")


def resolve_staff_ref(cur, ref: str) -> str | None:
    """Accept a real uuid, a generator id (staff-001), or a display name.

    The frontend's roster still carries the readable ids it was mocked against,
    and those ids came from the same generator that seeded the database. Rather
    than ask Ziyi to re-point every screen three days before submission, the API
    resolves all three forms. It is forgiving at the edge and exact underneath:
    whatever comes in, what goes to the database is a uuid.
    """
    import uuid as _uuid
    try:
        _uuid.UUID(ref)
        return ref
    except (ValueError, AttributeError):
        pass

    candidate = str(_uuid.uuid5(_NS, ref))
    cur.execute("SELECT id::text FROM staff_member WHERE id = %s", (candidate,))
    row = cur.fetchone()
    if row:
        return row["id"]

    # Fall back to a name, including a decorated form like "9f2c-diego".
    name = ref.rsplit("-", 1)[-1]
    cur.execute("SELECT id::text FROM staff_member "
                "WHERE lower(display_name) IN (%s, %s) LIMIT 1",
                (ref.lower(), name.lower()))
    row = cur.fetchone()
    return row["id"] if row else None


def list_observations(cur, limit: int = 50):
    """Observations the actor may see. RLS scopes it; no Python filter."""
    cur.execute("""
        SELECT o.id::text, o.staff_id::text, o.observed_at, o.context,
               o.what_happened, o.logged_at AS created_at,
               coalesce(json_agg(json_build_object(
                   'dimension', bd.code, 'level', orr.level
               ) ORDER BY bd.code) FILTER (WHERE bd.code IS NOT NULL),
               '[]'::json) AS ratings
        FROM observation o
        LEFT JOIN observation_rating orr ON orr.observation_id = o.id
        LEFT JOIN bars_dimension bd ON bd.id = orr.dimension_id
        GROUP BY o.id
        ORDER BY o.observed_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    for r in rows:
        r["observed_at"] = r["observed_at"].isoformat()
        r["created_at"] = r["created_at"].isoformat()
    return rows


def staff_by_id(cur, staff_id: str):
    cur.execute("SELECT id::text, display_name, department, role "
                "FROM staff_member WHERE id = %s", (staff_id,))
    return cur.fetchone()


# ---------------------------------------------------------------- scores

def raw_scores(cur, staff_id: str, source: str | None = None):
    """Scores visible to the current actor. RLS decides what comes back."""
    q = """
        SELECT s.id::text, s.source, bd.code AS dimension, s.level,
               s.scored_at, s.evidence_span, s.attempt_id::text,
               s.observation_id::text
        FROM score s
        JOIN bars_dimension bd ON bd.id = s.dimension_id
        WHERE s.staff_id = %s
    """
    params: list = [staff_id]
    if source:
        q += " AND s.source = %s"
        params.append(source)
    q += " ORDER BY s.scored_at DESC"
    cur.execute(q, params)
    return cur.fetchall()


def scores_response(cur, staff_id: str, source: str):
    """Matches the frontend's ScoresResponse."""
    rows = raw_scores(cur, staff_id, source)
    return {
        "staff_id": staff_id,
        "source": source,
        "scores": [
            {
                "id": f"{r['attempt_id'] or r['observation_id']}:{r['dimension']}",
                "source": r["source"],
                "dimension": r["dimension"],
                "level": r["level"],
                "recorded_at": r["scored_at"].isoformat(),
                "evidence_span": r["evidence_span"],
            }
            for r in rows
        ],
    }


def has_observed(cur, manager_id: str, staff_id: str) -> bool:
    cur.execute("SELECT has_observed(%s, %s) AS ok", (manager_id, staff_id))
    row = cur.fetchone()
    return bool(row and row["ok"])


# ---------------------------------------------------------------- transfer gap

def transfer_gap(cur, staff_id: str):
    """Compute the gap from whatever the actor is allowed to see.

    Note the consequence, which is deliberate: a manager who has not yet logged
    an observation sees no practice scores, so every dimension comes back as
    insufficient_evidence rather than as a gap. The screen is honest about why
    it is empty instead of showing a number built from half the evidence.
    """
    rows = raw_scores(cur, staff_id)
    today = date.today()

    by_dim: dict[str, list[Score]] = {d: [] for d in DIMENSIONS}
    for r in rows:
        if r["level"] is None:
            continue
        by_dim.setdefault(r["dimension"], []).append(
            Score(level=r["level"],
                  scored_at=r["scored_at"].date(),
                  source=r["source"]))

    dimensions, insufficient = [], []
    for dim in DIMENSIONS:
        gap = compute_gap(dim, by_dim.get(dim, []), today)
        if gap.insufficient_evidence:
            insufficient.append(dim)
            continue
        dimensions.append({
            "dimension": dim,
            "practice_mean": gap.practice_mean,
            "practice_n": gap.practice_n,
            "floor_mean": gap.floor_mean,
            "floor_n": gap.floor_n,
            "gap": gap.gap,
            "quadrant": gap.quadrant,
            "reading": gap.reading,
            "trend": _weekly_trend(by_dim.get(dim, []), today),
        })

    return {
        "staff_id": staff_id,
        "computed_at": datetime.now().isoformat(),
        "dimensions": dimensions,
        "insufficient_evidence": insufficient,
    }


def _weekly_trend(scores: list[Score], today: date, weeks: int = 4):
    """Gap per week, oldest first. Only weeks with both streams count."""
    out = []
    for i in range(weeks - 1, -1, -1):
        end = today - timedelta(days=7 * i)
        start = end - timedelta(days=7)
        window = [s for s in scores if start < s.scored_at <= end]
        p = [s.level for s in window if s.source == "practice"]
        f = [s.level for s in window if s.source == "floor"]
        if p and f:
            out.append({"week": end.strftime("%G-W%V"),
                        "gap": round(sum(p) / len(p) - sum(f) / len(f), 2)})
    return out


# ---------------------------------------------------------------- observations

def create_observation(cur, actor, payload: dict):
    """Write the observation, its per-dimension ratings, and the floor scores.

    One transaction. A half-written observation would leave the transfer gap
    reading from an evidence stream that does not fully exist.
    """
    cur.execute("SELECT id FROM bars_rubric WHERE is_active LIMIT 1")
    rubric = cur.fetchone()["id"]

    cur.execute("""
        INSERT INTO observation (property_id, staff_id, manager_id, source,
                                 observed_at, context, what_happened, rubric_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id::text
    """, (actor.property_id, payload["staff_id"], actor.staff_id,
          payload.get("source", "manager"), payload["observed_at"],
          payload["context"], payload["what_happened"], rubric))
    obs_id = cur.fetchone()["id"]

    cur.execute("SELECT id, code FROM bars_dimension WHERE rubric_id = %s", (rubric,))
    dim_ids = {r["code"]: r["id"] for r in cur.fetchall()}

    for rating in payload.get("ratings", []):
        dim = rating["dimension"]
        level = rating.get("level")
        if dim not in dim_ids:
            continue
        cur.execute("""
            INSERT INTO observation_rating (property_id, observation_id,
                                            dimension_id, level)
            VALUES (%s,%s,%s,%s)
        """, (actor.property_id, obs_id, dim_ids[dim], level))

        # A dimension the manager did not witness stays null and produces no
        # score row. Writing a midpoint here would quietly compress the gap.
        if level is None:
            continue
        cur.execute("""
            INSERT INTO score (property_id, staff_id, dimension_id, rubric_id,
                               source, level, observation_id, evidence_span,
                               scored_at)
            VALUES (%s,%s,%s,%s,'floor',%s,%s,%s,%s)
        """, (actor.property_id, payload["staff_id"], dim_ids[dim], rubric,
              level, obs_id, payload["what_happened"], payload["observed_at"]))

    return obs_id


# ---------------------------------------------------------------- calibration

def calibration(cur):
    """Agreement rate per dimension, from stored verification labels."""
    cur.execute("""
        SELECT bd.code AS dimension,
               count(*) FILTER (WHERE vl.agreed) AS agreements,
               count(*) AS n
        FROM verification_label vl
        JOIN bars_dimension bd ON bd.id = vl.dimension_id
        GROUP BY bd.code
    """)
    seen = {r["dimension"]: (r["agreements"], r["n"]) for r in cur.fetchall()}

    out = []
    for dim in DIMENSIONS:
        agreements, n = seen.get(dim, (0, 0))
        c = calibrate(dim, agreements, n)
        out.append({
            "dimension": dim,
            "agreement_rate": c.rate,
            "sample_size": c.n,
            "lower": c.lower,
            "upper": c.upper,
            "state": c.state,
            "advice": c.display,
        })
    return out


# ---------------------------------------------------------------- audit

def audit(cur, actor, event_type: str, subject_ref: str | None = None,
          payload: dict | None = None):
    """Append-only. Article 12: what was recommended, on what, and who decided."""
    import json
    cur.execute("""
        INSERT INTO audit_event (property_id, actor, event_type, subject_ref, payload)
        VALUES (%s,%s,%s,%s,%s)
        RETURNING id
    """, (actor.property_id, f"{actor.role}:{actor.staff_id}", event_type,
          subject_ref, json.dumps(payload or {})))
    # Returned so a caller can address this event later; every existing caller
    # ignores it. A scenario proposal lives in this table until a manager
    # decides on it, and needs an id to be decided on.
    row = cur.fetchone()
    return row["id"] if row else None


def latest_weekly_report(cur):
    """The most recent brief this property commissioned, or None.

    No new table. Commissioning already writes an audit row carrying the Manus
    task id in subject_ref, and the brief itself is re-fetchable from that id
    for as long as the task exists, so the audit trail doubles as the record of
    what was last written. Reading it back is what stops the document vanishing
    the moment somebody clicks another tab.

    Scoped by row level security to the reader's own property, like everything
    else here.
    """
    cur.execute("""
        SELECT subject_ref AS task_id, occurred_at, payload
        FROM audit_event
        WHERE event_type = 'report.commissioned' AND subject_ref IS NOT NULL
        ORDER BY occurred_at DESC
        LIMIT 1
    """)
    return cur.fetchone()


# ---------------------------------------------------------------- insights

K_ANON = 5


def team_insights(cur) -> dict:
    """Cohort patterns, never below k distinct staff.

    Grouped on situation_type rather than free text, because you cannot count
    free text reliably and a pattern you cannot count is an anecdote.
    """
    cur.execute("""
        SELECT sd.incident->>'situation_type' AS situation,
               sm.department,
               count(DISTINCT sd.staff_id) AS staff_count
        FROM shift_debrief sd
        JOIN staff_member sm ON sm.id = sd.staff_id
        WHERE sd.created_at > now() - interval '21 days'
          AND sd.incident->>'situation_type' IS NOT NULL
        GROUP BY 1, 2
        ORDER BY staff_count DESC
    """)
    rows = cur.fetchall()

    patterns, suppressed = [], 0
    for r in rows:
        if r["staff_count"] < K_ANON:
            # Below k a "pattern" identifies individuals, whatever the
            # interface claims. Counted, never shown.
            suppressed += 1
            continue
        situation = (r["situation"] or "other").replace("_", " ")
        # Authority ambiguity is a policy gap, not a coaching problem: the
        # staff escalated because nothing told them what they could decide.
        is_policy = r["situation"] in ("room_not_ready", "billing_dispute")
        patterns.append({
            "id": f"{r['department']}:{r['situation']}",
            "classification": "policy" if is_policy else "process",
            "staff_count": r["staff_count"],
            "dimension": "service_recovery",
            "description": (f"{r['staff_count']} staff in "
                            f"{r['department'].replace('_', ' ')} logged the same "
                            f"situation this period: {situation}."),
            "suggested_action": (
                "Set and communicate what staff may offer without approval."
                if is_policy else
                "Run a ten minute briefing on this before it recurs."),
            "route": "operations",
        })

    end = date.today()
    start = end - timedelta(days=21)
    for pat in patterns:
        # The window is the detection, so the window end is the detection time.
        # Inventing a per-pattern timestamp would imply a precision the
        # aggregate does not have.
        pat["detected_at"] = end.isoformat()

    return {"window": {"start": start.isoformat(), "end": end.isoformat()},
            "k_threshold": K_ANON, "patterns": patterns,
            "suppressed": [{"reason": "below_k_threshold", "count": suppressed}]
                          if suppressed else []}

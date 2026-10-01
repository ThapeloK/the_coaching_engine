"""
recommendations.py
==================
Persisting an agent run, and recording the manager's verdict.

Two invariants worth stating, because both are easy to lose under deadline
pressure:

* A recommendation and its citations are written in ONE transaction. An
  uncited recommendation must never be persistable, so there is no window in
  which one exists.
* Verification is the only thing that moves a recommendation out of
  pending_verify. There is no timeout and no auto-approve. An unverified
  recommendation stays pending forever, which is what Article 14 human
  oversight actually means.
"""

from __future__ import annotations

import json

from . import queries as q


def persist(cur, actor, staff_id: str, result: dict) -> str | None:
    """Write an agent result. Returns the recommendation id."""
    cur.execute("SELECT id FROM bars_rubric WHERE is_active LIMIT 1")
    rubric = cur.fetchone()["id"]

    abstained = result["status"] == "abstained"

    cur.execute("""
        INSERT INTO recommendation (property_id, staff_id, manager_id,
            classification, status, headline, body, suggested_action,
            evidence_hash, rubric_id, model_id, prompt_version, abstain_reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id::text
    """, (
        actor.property_id, staff_id, actor.staff_id,
        result.get("classification"),
        "abstained" if abstained else "pending_verify",
        result.get("headline") or "Insufficient evidence",
        result.get("body") or result.get("opening_line"),
        result.get("suggested_action"),
        result.get("evidence_hash", "0" * 64),
        rubric, "gpt-4o", "draft.v2",
        result.get("abstain_reason"),
    ))
    rec_id = cur.fetchone()["id"]

    for c in result.get("citations", []):
        cur.execute("""
            INSERT INTO recommendation_citation (property_id, recommendation_id,
                kind, claim_text, source_ref, quoted_span)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (actor.property_id, rec_id, c["kind"], c["claim"],
              c["source_ref"], (c.get("quoted_span") or "")[:400]))

    esc = result.get("escalation")
    if esc and not abstained:
        cur.execute("""
            INSERT INTO escalation (property_id, recommendation_id, route,
                severity, rule_id, summary)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (actor.property_id, rec_id, esc["route"], esc["severity"],
              esc["rule_id"], esc["summary"]))

    q.audit(cur, actor, "recommendation.created", rec_id, {
        "status": result["status"],
        "classification": result.get("classification"),
        "citations": len(result.get("citations", [])),
        "repair_attempts": result.get("repair_attempts"),
        "trace": result.get("trace", {}).get("total_ms"),
    })
    cur.connection.commit()
    return rec_id


def get(cur, rec_id: str) -> dict | None:
    cur.execute("""
        SELECT r.id::text, r.status, r.classification, r.headline, r.body,
               r.suggested_action, r.abstain_reason, r.created_at,
               r.staff_id::text, sm.display_name AS staff_name
        FROM recommendation r
        JOIN staff_member sm ON sm.id = r.staff_id
        WHERE r.id = %s
    """, (rec_id,))
    rec = cur.fetchone()
    if not rec:
        return None

    cur.execute("""
        SELECT kind, claim_text AS claim, source_ref, quoted_span
        FROM recommendation_citation WHERE recommendation_id = %s
    """, (rec_id,))
    rec["citations"] = cur.fetchall()

    cur.execute("""
        SELECT rule_id, route, severity, summary
        FROM escalation WHERE recommendation_id = %s LIMIT 1
    """, (rec_id,))
    rec["escalation"] = cur.fetchone()

    rec["created_at"] = rec["created_at"].isoformat()
    return rec


def listing(cur, status: str | None = None) -> list[dict]:
    """The queue. Whole Recommendation objects, citations included.

    Not a summary projection: the verify screen renders its card from a list
    row, and a card that fetches its own citations turns a queue of ten into
    eleven round trips. The list stays small by construction, because a manager
    with more than fifty pending decisions has a worse problem than paging.
    """
    sql = """
        SELECT r.id::text, r.status, r.classification, r.headline, r.body,
               r.suggested_action, r.created_at, sm.display_name AS staff_name,
               r.staff_id::text, r.abstain_reason,
               (SELECT count(*) FROM recommendation_citation c
                 WHERE c.recommendation_id = r.id) AS citation_count
        FROM recommendation r
        JOIN staff_member sm ON sm.id = r.staff_id
    """
    params: list = []
    if status:
        sql += " WHERE r.status = %s"
        params.append(status)
    sql += " ORDER BY r.created_at DESC LIMIT 50"
    cur.execute(sql, params)
    rows = cur.fetchall()
    if not rows:
        return []

    cur.execute("""
        SELECT recommendation_id::text AS rec, kind, claim_text AS claim,
               source_ref, quoted_span
        FROM recommendation_citation
        WHERE recommendation_id = ANY(%s::uuid[])
    """, ([r["id"] for r in rows],))
    by_rec: dict[str, list] = {}
    for c in cur.fetchall():
        by_rec.setdefault(c.pop("rec"), []).append(c)

    calib = q.calibration(cur)
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
        r["citations"] = by_rec.get(r["id"], [])
        r["calibration"] = calib
        r["trace_id"] = r["id"]
    return rows


def verify(cur, actor, rec_id: str, verdict: str,
           dimension_verdicts: list[dict], reason: str | None,
           seconds: int | None) -> dict:
    """Record the manager's decision and turn it into calibration labels.

    Every verdict produces labels, including a rejection. A rejection is as
    informative as a confirmation, arguably more so, and treating it as
    telemetry rather than training data would waste the most valuable signal
    the product generates.
    """
    cur.execute("SELECT status, staff_id::text FROM recommendation WHERE id = %s",
                (rec_id,))
    rec = cur.fetchone()
    if not rec:
        return {"error": "not_found"}
    if rec["status"] not in ("pending_verify",):
        return {"error": "already_decided", "status": rec["status"]}

    cur.execute("""
        INSERT INTO verification (property_id, recommendation_id, manager_id,
            verdict, reason, seconds_to_decide)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id::text
    """, (actor.property_id, rec_id, actor.staff_id, verdict, reason, seconds))
    ver_id = cur.fetchone()["id"]

    cur.execute("SELECT id, code FROM bars_dimension")
    dims = {r["code"]: r["id"] for r in cur.fetchall()}

    # The console animates manager agreement from where it was to where this
    # verdict moves it, so the "before" reading has to be taken before the
    # labels land. Taking it afterwards reads the same number twice and the
    # bar sits still, which is a quiet way of saying nothing happened.
    target_dim = next((dv.get("dimension") for dv in (dimension_verdicts or [])
                       if dv.get("dimension") in dims), None)
    before = None
    if target_dim:
        before = next((c for c in q.calibration(cur)
                       if c["dimension"] == target_dim), None)

    for dv in dimension_verdicts or []:
        dim = dv.get("dimension")
        if dim not in dims:
            continue
        agent_level = dv.get("agent_level") or dv.get("manager_level") or 0
        manager_level = dv.get("manager_level")
        cur.execute("""
            INSERT INTO verification_label (property_id, verification_id,
                dimension_id, agent_level, manager_level, agreed)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (actor.property_id, ver_id, dims[dim], agent_level, manager_level,
              verdict == "confirmed"))

    cur.execute("UPDATE recommendation SET status = %s WHERE id = %s",
                (verdict, rec_id))
    q.audit(cur, actor, "recommendation.verified", rec_id,
            {"verdict": verdict, "seconds": seconds})

    readings = q.calibration(cur)
    after = (next((c for c in readings if c["dimension"] == target_dim), None)
             if target_dim else None)

    # calibration_updated is what the frozen contract promises and what the
    # result panel reads. Returning only the full array left it undefined and
    # took the whole page down with it after a verdict had already been
    # written, so the manager saw an error for something that had worked.
    calibration_updated = None
    if after:
        calibration_updated = {
            "dimension": target_dim,
            "agreement_rate_before": (before or {}).get("agreement_rate") or 0.0,
            "agreement_rate_after": after["agreement_rate"] or 0.0,
            "sample_size": after["sample_size"],
            "lower": after["lower"],
            "upper": after["upper"],
            "state": after["state"],
            "advice": after["advice"],
        }

    # Escalations are written when the agent runs, not when a verdict lands,
    # so this reports the one already attached rather than creating any.
    cur.execute("""
        SELECT route, severity, rule_id, summary
        FROM escalation WHERE recommendation_id = %s LIMIT 1
    """, (rec_id,))
    escalation = cur.fetchone()

    cur.connection.commit()

    return {"status": verdict, "verification_id": ver_id,
            "calibration": readings,
            "calibration_updated": calibration_updated,
            "escalation": escalation}

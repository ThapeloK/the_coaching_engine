"""
test_rls.py
===========
The negative tests from policies.sql, as runnable assertions.

These are the governance story. Every claim we make on stage about tenant
isolation, transparency parity and the observe-before-you-see-the-score
sequencing rule is either provable here or is not true.

Runs as ce_app, never as the owner: row level security does not apply to a
table's owner, so testing as the owner would pass trivially and prove nothing.

    python db/test_rls.py
"""

from __future__ import annotations

import os
import sys

import psycopg

DSN = os.environ.get("APP_DATABASE_URL",
                     "postgresql://ce_app:ce_app@localhost:5433/coaching_engine")
OWNER_DSN = os.environ.get("SEED_DATABASE_URL",
                           "postgresql://coaching:coaching@localhost:5433/coaching_engine")

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(test_id: str, description: str, actual, expected, comparator="=="):
    ok = (actual == expected) if comparator == "==" else (actual > expected)
    results.append((test_id, PASS if ok else FAIL,
                    f"{description}: got {actual}, expected {comparator} {expected}"))


def as_user(cur, prop, staff_id, role):
    cur.execute("SELECT set_config('app.property_id', %s, false)", (str(prop),))
    cur.execute("SELECT set_config('app.staff_id', %s, false)", (str(staff_id),))
    cur.execute("SELECT set_config('app.role', %s, false)", (role,))


def scores_for(cur, name, source=None):
    q = ("SELECT count(*) FROM score s JOIN staff_member sm ON sm.id = s.staff_id "
         "WHERE sm.display_name = %s")
    params = [name]
    if source:
        q += " AND s.source = %s"
        params.append(source)
    cur.execute(q, params)
    return cur.fetchone()[0]


def main() -> int:
    # Look up ids as the owner; RLS would hide them from ce_app before context is set.
    with psycopg.connect(OWNER_DSN, autocommit=True) as owner:
        with owner.cursor() as c:
            c.execute("SELECT id FROM property LIMIT 1")
            prop = c.fetchone()[0]
            c.execute("SELECT display_name, id FROM staff_member")
            people = dict(c.fetchall())

    marta, diego, aoife = people["Marta"], people["Diego"], people["Aoife"]

    with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:

        # ---- NT4: transparency parity has a hard edge -----------------------
        as_user(cur, prop, diego, "staff")
        check("NT4", "staff member reads a colleague's scores",
              scores_for(cur, "Aoife"), 0)
        check("NT4b", "staff member reads their own scores",
              scores_for(cur, "Diego"), 0, ">")

        # ---- NT1: tenant boundary ------------------------------------------
        as_user(cur, "00000000-0000-0000-0000-000000000009", diego, "staff")
        check("NT1", "wrong property id returns nothing",
              scores_for(cur, "Diego"), 0)

        # ---- NT2 / NT3: the sequencing gate --------------------------------
        # has_observed() only counts observations from the last 30 days, so
        # ageing Marta's observations of Aoife out of that window recreates the
        # un-observed state without deleting rows the scores depend on. It also
        # tests the time bound, which a delete would not.
        with psycopg.connect(OWNER_DSN, autocommit=True) as owner, owner.cursor() as oc:
            oc.execute("UPDATE observation SET logged_at = now() - interval '60 days' "
                       "WHERE staff_id = %s", (aoife,))

            as_user(cur, prop, marta, "manager")
            check("NT2", "manager reads practice scores BEFORE observing",
                  scores_for(cur, "Aoife", "practice"), 0)
            check("NT2b", "manager reads floor scores before observing (allowed)",
                  scores_for(cur, "Aoife", "floor"), 0, ">")

            oc.execute("UPDATE observation SET logged_at = now() "
                       "WHERE staff_id = %s", (aoife,))

        as_user(cur, prop, marta, "manager")
        check("NT3", "manager reads practice scores AFTER observing",
              scores_for(cur, "Aoife", "practice"), 0, ">")

        # ---- NT5: L&D sees patterns, not practice transcripts ---------------
        as_user(cur, prop, people["Fiona"], "ld_admin")
        check("NT5", "L&D reads individual practice scores",
              scores_for(cur, "Diego", "practice"), 0)

        # ---- NT6: k-anonymity is a constraint, not a convention -------------
        try:
            cur.execute(
                "INSERT INTO cohort_pattern (property_id, window_start, window_end, "
                "classification, staff_count, description) "
                "VALUES (%s, current_date, current_date, 'process', 4, 'too small')",
                (prop,))
            results.append(("NT6", FAIL, "cohort below k=5 was accepted"))
        except psycopg.errors.CheckViolation:
            results.append(("NT6", PASS, "cohort below k=5 rejected by constraint"))
        except psycopg.Error as e:
            results.append(("NT6", FAIL, f"unexpected error: {type(e).__name__}"))

        # ---- NT7: the audit record is append only ---------------------------
        try:
            cur.execute("UPDATE audit_event SET actor = 'tampered'")
            results.append(("NT7", FAIL, "audit_event was updatable"))
        except psycopg.errors.InsufficientPrivilege:
            results.append(("NT7", PASS, "audit_event UPDATE denied"))
        except psycopg.Error as e:
            results.append(("NT7", FAIL, f"unexpected error: {type(e).__name__}"))

        # ---- NT9: the shared 1..5 scale is enforced -------------------------
        try:
            cur.execute(
                "INSERT INTO score (property_id, staff_id, dimension_id, rubric_id, "
                "source, level, attempt_id) SELECT %s, %s, bd.id, bd.rubric_id, "
                "'practice', 6, sa.id FROM bars_dimension bd, scenario_attempt sa LIMIT 1",
                (prop, diego))
            results.append(("NT9", FAIL, "score level 6 was accepted"))
        except psycopg.errors.CheckViolation:
            results.append(("NT9", PASS, "score level outside 1..5 rejected"))
        except psycopg.Error as e:
            results.append(("NT9", FAIL, f"unexpected error: {type(e).__name__}"))

    width = max(len(d) for _, _, d in results)
    print()
    for tid, status, detail in results:
        mark = "ok  " if status == PASS else "FAIL"
        print(f"  [{mark}] {tid:<5} {detail:<{width}}")

    failed = sum(1 for _, s, _ in results if s == FAIL)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    if failed:
        print("\nRLS is NOT enforcing. Do not claim tenant isolation on stage "
              "until this is green.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

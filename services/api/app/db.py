"""
db.py
=====
Connection pool, and the request-scoped session context that row level
security depends on.

Every request sets app.property_id, app.staff_id and app.role before it runs a
single query. Those three settings are what the policies in db/policies.sql
read. Forget to set them and the policies deny everything, which is the correct
failure direction: a missing identity should return nothing, not everything.

The pool connects as ce_app, never as the database owner. RLS does not apply to
a table's owner, so connecting as the owner would silently disable every policy
and we would ship a governance story that does not run.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ce_app:ce_app@localhost:5433/coaching_engine",
)

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, open=False,
                      kwargs={"row_factory": dict_row})


@dataclass(frozen=True)
class Actor:
    """Who is making this request. Resolved per request, never cached."""
    staff_id: str
    property_id: str
    role: str           # staff | manager | ld_admin
    display_name: str


@contextmanager
def session(actor: Actor | None = None):
    """A connection with the RLS context set for this actor.

    set_config(..., true) makes the setting transaction-local, so it cannot
    leak to the next request that borrows this pooled connection. That detail
    matters more than it looks: a leaked identity on a pooled connection is
    exactly how a multi-tenant system shows one customer another's data.
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            if actor is not None:
                cur.execute("SELECT set_config('app.property_id', %s, true)",
                            (actor.property_id,))
                cur.execute("SELECT set_config('app.staff_id', %s, true)",
                            (actor.staff_id,))
                cur.execute("SELECT set_config('app.role', %s, true)",
                            (actor.role,))
            yield cur


def resolve_actor(name_or_id: str | None) -> Actor | None:
    """Look up an actor by display name or id, as the owner.

    Demo-grade identity. Real deployment resolves this from a verified JWT; the
    lookup has to bypass RLS because the caller has no identity yet, which is
    precisely why this is the one place that connects as the owner and why it
    only ever reads the staff table.
    """
    if not name_or_id:
        return None
    owner_dsn = os.environ.get(
        "SEED_DATABASE_URL",
        DATABASE_URL.replace("ce_app:ce_app", "coaching:coaching"))
    q = ("SELECT id::text, property_id::text, role, display_name "
         "FROM staff_member WHERE lower(display_name) = lower(%s) "
         "   OR id::text = %s LIMIT 1")
    try:
        with psycopg.connect(owner_dsn, row_factory=dict_row) as conn:
            row = conn.execute(q, (name_or_id, name_or_id)).fetchone()
    except psycopg.Error:
        return None
    if not row:
        return None
    return Actor(staff_id=row["id"], property_id=row["property_id"],
                 role=row["role"], display_name=row["display_name"])

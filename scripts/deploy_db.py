"""
deploy_db.py
============
Take a managed Postgres (Neon, Supabase, Render, anything) from empty to a
fully seeded Coaching Engine database.

    # in .env, paste the connection string your provider gave you:
    #   NEON_DATABASE_URL=postgresql://owner:pw@host/db?sslmode=require
    python scripts/deploy_db.py
    python scripts/deploy_db.py --reset     # drop everything first

What it does, in order: schema, policies, an app role with a GENERATED
password, seed data, and the embeddings without which the whole product
abstains. Then it prints the two connection strings the API needs.

Why this is a separate script from bootstrap.py: bootstrap talks to a local
container it controls and can destroy. This talks to a remote database that
may be shared, so it never runs `docker compose down`, it refuses to drop
anything without --reset, and it prints what it is about to do first.

The one thing you cannot skip: the API must connect as a NON-OWNER role.
Row level security does not apply to a table's owner, so deploying with the
owner's connection string silently turns off every policy in policies.sql and
the governance story stops being true.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m")

APP_ROLE = "ce_app"


def say(step: str) -> None:
    print(f"\n{DIM}--{RESET} {step}")


def load_env() -> None:
    from dotenv import load_dotenv                           # noqa: PLC0415
    load_dotenv(ROOT / ".env", override=False)


def owner_dsn() -> str:
    for name in ("NEON_DATABASE_URL", "DEPLOY_DATABASE_URL",
                 "SEED_DATABASE_URL"):
        value = os.environ.get(name, "").strip()
        if value:
            print(f"   using {name}")
            return value
    print(f"{RED}No deployment database configured.{RESET}\n"
          f"Add one line to .env, using the connection string from your\n"
          f"provider (Neon: 'Connect' > show password):\n\n"
          f"   NEON_DATABASE_URL=postgresql://owner:PASSWORD@host/db"
          f"?sslmode=require\n")
    raise SystemExit(1)


def app_dsn_from(owner: str, password: str) -> str:
    """Same host and database, different credentials."""
    return re.sub(r"//[^@]+@", f"//{APP_ROLE}:{password}@", owner, count=1)


def unpooled(dsn: str) -> str:
    """Neon's pooled endpoint cannot run DDL reliably; use the direct one."""
    return dsn.replace("-pooler.", ".")


def redact(dsn: str) -> str:
    return re.sub(r"//([^:]+):[^@]+@", r"//\1:****@", dsn)


def psql(dsn: str, sql: str | None = None, file: Path | None = None,
         quiet: bool = True) -> tuple[int, str]:
    """Run SQL through psycopg rather than the psql binary.

    psql is not installed on every machine that will need to run this, and the
    one place it is guaranteed (the postgres container) cannot reach a remote
    host over TLS without extra flags. psycopg is already a dependency.
    """
    import psycopg                                           # noqa: PLC0415
    body = file.read_text(encoding="utf-8") if file else (sql or "")
    try:
        with psycopg.connect(dsn, connect_timeout=20, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(body)
                try:
                    rows = cur.fetchall()
                    return 0, "\n".join(str(r) for r in rows)
                except psycopg.ProgrammingError:
                    return 0, ""
    except Exception as exc:                                 # noqa: BLE001
        return 1, f"{type(exc).__name__}: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="DROP every table first. Destroys data.")
    ap.add_argument("--password", default="",
                    help="app role password (generated if omitted)")
    args = ap.parse_args()

    load_env()
    print("Coaching Engine: deploy database")
    say("Target")
    owner = owner_dsn()
    ddl = unpooled(owner)
    print(f"   {redact(ddl)}")

    code, out = psql(ddl, "SELECT version()")
    if code:
        print(f"{RED}cannot connect:{RESET} {out}")
        return 1
    print(f"   {GREEN}connected{RESET}  {out.split(',')[0][2:60]}")

    if args.reset:
        say("Dropping everything (--reset)")
        code, out = psql(ddl, "DROP SCHEMA public CASCADE; "
                              "CREATE SCHEMA public;")
        if code:
            print(f"{RED}{out}{RESET}")
            return 1
        print(f"   {GREEN}schema dropped{RESET}")

    code, out = psql(ddl, "SELECT to_regclass('public.staff_member') IS NOT NULL")
    already = out.strip().startswith("(True")
    if already and not args.reset:
        print(f"\n{YELLOW}The schema already exists.{RESET} "
              f"Re-run with --reset to rebuild it from scratch.")

    if not already:
        for name in ("schema.sql", "policies.sql"):
            say(f"Applying {name}")
            code, out = psql(ddl, file=ROOT / "db" / name)
            if code:
                print(f"{RED}{out[:600]}{RESET}")
                return 1
            print(f"   {GREEN}ok{RESET}")

    say(f"Application role ({APP_ROLE})")
    # Generated, not the local 'ce_app' literal. This database is reachable
    # from the internet, and roles.sql's development password would be a
    # published credential the moment the connection string is shared.
    password = args.password or secrets.token_urlsafe(24)
    roles_sql = (ROOT / "db" / "roles.sql").read_text(encoding="utf-8")
    roles_sql = roles_sql.replace(
        "CREATE ROLE ce_app LOGIN PASSWORD 'ce_app';",
        f"DROP ROLE IF EXISTS {APP_ROLE};\n"
        f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{password}';")
    code, out = psql(ddl, roles_sql)
    if code and "already exists" not in out:
        # Reassigning an existing role's password is enough on a re-run.
        code2, out2 = psql(ddl, f"ALTER ROLE {APP_ROLE} PASSWORD '{password}'")
        if code2:
            print(f"{RED}{out[:400]}{RESET}")
            return 1
    print(f"   {GREEN}created{RESET} with a generated password")

    app = app_dsn_from(owner, password)

    say("Seeding")
    code, out = psql(ddl, "SELECT count(*) FROM staff_member")
    seeded = not out.strip().startswith("(0")
    if seeded:
        print(f"   {DIM}already populated{RESET}")
    else:
        env = {**os.environ, "SEED_DATABASE_URL": ddl}
        for script in ("db/seed.py", "db/generate_transcripts.py"):
            proc = subprocess.run([sys.executable, script], cwd=ROOT, env=env,
                                  capture_output=True, text=True)
            if proc.returncode:
                print(f"{RED}{script} failed{RESET}\n"
                      f"{(proc.stderr or proc.stdout)[-1200:]}")
                return 1
            print(f"   {GREEN}ok{RESET}  {script}")

    say("Embedding the standards")
    # The failure this guards against is invisible: with a null vector column
    # every endpoint answers 200 and the agent abstains on everyone with a
    # reason that reads like good judgement.
    os.environ["DATABASE_URL"] = app
    os.environ["SEED_DATABASE_URL"] = ddl
    from app.db import pool, resolve_actor, session            # noqa: PLC0415
    from app.retrieval import backfill_embeddings              # noqa: PLC0415

    pool.open(); pool.wait()
    with session(resolve_actor("Fiona")) as cur:
        cur.execute("SELECT count(*) AS n FROM sop_chunk WHERE embedding IS NULL")
        missing = cur.fetchone()["n"]
    if missing:
        with session(resolve_actor("Fiona")) as cur:
            done = backfill_embeddings(cur)
        print(f"   {GREEN}embedded{RESET} {done} chunk(s)")
    else:
        print(f"   {DIM}already embedded{RESET}")

    say("Verifying row level security is actually on")
    # Deploying with RLS off is the one mistake that would invalidate the whole
    # governance pitch, and it is silent. Prove it here, on the real database.
    with session(resolve_actor("Diego")) as cur:
        cur.execute("SELECT id FROM staff_member WHERE lower(display_name)='aoife'")
        aoife = cur.fetchone()
        cur.execute("SELECT count(*) AS n FROM score WHERE staff_id = %s",
                    (aoife["id"],))
        leaked = cur.fetchone()["n"]
    if leaked:
        print(f"   {RED}FAILED: a colleague read {leaked} of Aoife's score "
              f"rows.{RESET} The API is connecting as an owner, or the "
              f"policies did not apply. Do not deploy this.")
        pool.close()
        return 1
    print(f"   {GREEN}enforced{RESET}  a colleague reads 0 rows")
    pool.close()

    print(f"""
{GREEN}Database ready.{RESET} Set these on your host (Render > Environment):

{DIM}# the API connects as the app role, so RLS applies{RESET}
DATABASE_URL={app}

{DIM}# owner, used only to resolve identity before a request has one{RESET}
SEED_DATABASE_URL={ddl}

Save the app password somewhere: it is generated and not stored anywhere else.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

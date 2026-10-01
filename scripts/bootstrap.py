"""
bootstrap.py
============
Take a fresh clone to a running, populated system. One command.

    python scripts/bootstrap.py            # set up, leave the API to you
    python scripts/bootstrap.py --reset    # destroy the database first
    python scripts/bootstrap.py --coach    # also generate a verify queue

This exists because "works on my machine" is the default state of a project
built by six people in two weeks, and the cost of it lands on whoever is
setting up an hour before a pitch. Every step below is idempotent: run it
twice and nothing breaks.

It deliberately does NOT start uvicorn or next. Those want their own terminal
where you can read their logs; see the README for the two commands.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER_DSN = "postgresql://coaching:coaching@localhost:5433/coaching_engine"

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def say(step: str) -> None:
    print(f"\n{DIM}--{RESET} {step}")


def run(cmd: list[str], *, cwd: Path | None = None,
        env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    full = {**os.environ, **(env or {})}
    proc = subprocess.run(cmd, cwd=cwd or ROOT, env=full,
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        print(f"{RED}failed:{RESET} {' '.join(cmd)}")
        print((proc.stderr or proc.stdout)[-1500:])
        sys.exit(1)
    return proc


def docker_ok() -> bool:
    return run(["docker", "info"], check=False).returncode == 0


def db_ready(timeout: int = 90) -> bool:
    """Wait for Postgres to accept connections AND finish its init scripts.

    pg_isready alone is not enough: the official image starts a temporary
    server to run docker-entrypoint-initdb.d, so there is a window where the
    database answers and the schema does not exist yet. Asking for a table we
    know the schema creates closes that window.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        probe = run(["docker", "exec", "ce-db", "psql", "-U", "coaching",
                     "-d", "coaching_engine", "-tAc",
                     "SELECT to_regclass('public.staff_member') IS NOT NULL"],
                    check=False)
        if probe.returncode == 0 and probe.stdout.strip() == "t":
            return True
        time.sleep(2)
    return False


def table_count(table: str) -> int:
    probe = run(["docker", "exec", "ce-db", "psql", "-U", "coaching",
                 "-d", "coaching_engine", "-tAc", f"SELECT count(*) FROM {table}"],
                check=False)
    try:
        return int(probe.stdout.strip())
    except (ValueError, AttributeError):
        return -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="destroy the database volume and rebuild from schema.sql")
    ap.add_argument("--coach", action="store_true",
                    help="run the agent over the team to fill the verify queue")
    args = ap.parse_args()

    print("The Coaching Engine: bootstrap")

    if not docker_ok():
        print(f"{RED}Docker is not running.{RESET} Start Docker Desktop, then re-run.")
        return 1

    if not (ROOT / ".env").exists():
        print(f"{RED}No .env at the repo root.{RESET} "
              f"Copy .env.example to .env and add at least OPENAI_API_KEY.")
        return 1

    if args.reset:
        say("Destroying the database (--reset)")
        run(["docker", "compose", "down", "-v"], check=False)

    say("Starting Postgres")
    run(["docker", "compose", "up", "-d", "db"])
    if not db_ready():
        print(f"{RED}Postgres did not become ready.{RESET} "
              f"Try: docker compose logs db")
        return 1
    print(f"   {GREEN}ready{RESET} on localhost:5433")

    say("Applying migrations")
    migrations = sorted((ROOT / "db" / "migrations").glob("*.sql"))
    for path in migrations:
        # Every migration is written to be safe to re-run, so this is not
        # conditional on some tracking table we would then have to maintain.
        proc = run(["docker", "exec", "-i", "ce-db", "psql", "-U", "coaching",
                    "-d", "coaching_engine", "-q", "-v", "ON_ERROR_STOP=1"],
                   check=False, env={})
        with open(path, "rb") as fh:
            proc = subprocess.run(
                ["docker", "exec", "-i", "ce-db", "psql", "-U", "coaching",
                 "-d", "coaching_engine", "-q", "-v", "ON_ERROR_STOP=1"],
                stdin=fh, capture_output=True, text=True)
        state = f"{GREEN}ok{RESET}" if proc.returncode == 0 else f"{RED}failed{RESET}"
        print(f"   {state}  {path.name}")
        if proc.returncode != 0:
            print(proc.stderr[-600:])
            return 1
    if not migrations:
        print(f"   {DIM}none{RESET}")

    say("Seeding")
    if table_count("staff_member") > 0:
        print(f"   {DIM}already populated, skipping{RESET} "
              f"(use --reset to start clean)")
    else:
        run([sys.executable, "db/seed.py"], env={"SEED_DATABASE_URL": OWNER_DSN})
        print(f"   {GREEN}seeded{RESET}")
        say("Generating practice transcripts and evidence spans")
        run([sys.executable, "db/generate_transcripts.py"],
            env={"SEED_DATABASE_URL": OWNER_DSN})
        print(f"   {GREEN}done{RESET}")

    say("Embedding the standards")
    # Without this the vector column is null, hybrid search returns nothing,
    # the cite gate finds no standard to ground a claim in, and the agent
    # abstains on every single person. It looks like principled restraint and
    # it is actually an empty index, which is the worst kind of bug: the system
    # reports a sensible-sounding reason for doing nothing.
    sys.path.insert(0, str(ROOT / "services" / "api"))
    os.environ.setdefault(
        "DATABASE_URL", "postgresql://ce_app:ce_app@localhost:5433/coaching_engine")
    from app.db import pool, resolve_actor, session          # noqa: PLC0415
    from app.retrieval import backfill_embeddings            # noqa: PLC0415

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

    say("Checking providers")
    proc = run([sys.executable, "check_providers.py"],
               cwd=ROOT / "services" / "api", check=False)
    for line in proc.stdout.splitlines():
        if line.strip().startswith("["):
            print("  " + line.strip())

    if args.coach:
        say("Filling the verify queue")
        # Imported late: it needs the environment the steps above just built.
        sys.path.insert(0, str(ROOT / "services" / "api"))
        os.environ.setdefault("DATABASE_URL",
                              "postgresql://ce_app:ce_app@localhost:5433/coaching_engine")
        from app import queries as q                       # noqa: PLC0415
        from app.agent import run_coaching                 # noqa: PLC0415
        from app.db import pool, resolve_actor, session    # noqa: PLC0415
        from app import recommendations as recs            # noqa: PLC0415
        from app.providers import Trace                    # noqa: PLC0415

        pool.open(); pool.wait()
        actor = resolve_actor("Marta")
        made = abstained = 0
        with session(actor) as cur:
            staff = [r["id"] for r in q.list_staff(cur) if r["role"] == "staff"]
        for sid in staff:
            try:
                with session(actor) as cur:
                    result = run_coaching(cur, actor, sid, trace=Trace())
                    recs.persist(cur, actor, sid, result)
                if result["status"] == "abstained":
                    abstained += 1
                else:
                    made += 1
            except Exception as exc:                       # noqa: BLE001
                print(f"   {RED}{sid[:8]}{RESET} {type(exc).__name__}: {exc}")
        print(f"   {GREEN}{made}{RESET} recommendations, "
              f"{abstained} abstentions (abstaining is correct behaviour)")
        # Close it explicitly. Left to the garbage collector at interpreter
        # shutdown, the pool's worker threads cannot be joined and Python
        # prints a traceback over an otherwise successful run, which reads to
        # anyone setting this up as though the script failed.
        pool.close()

    counts = {t: table_count(t) for t in
              ("staff_member", "sop_chunk", "score", "observation",
               "shift_debrief", "recommendation")}
    say("Ready")
    for name, n in counts.items():
        print(f"   {name:16} {n}")

    print(f"""
{GREEN}Start the two services, each in its own terminal:{RESET}

   cd services/api && python -m uvicorn app.main:app --reload --port 8000
   cd web && pnpm dev

Then open http://localhost:3000/manager, and http://localhost:3000/glassbox
for the panels that prove the claims.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

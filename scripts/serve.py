"""
serve.py
========
Run the API against a chosen database, without a shell mangling the DSN.

    python scripts/serve.py                # local docker Postgres
    python scripts/serve.py --neon         # the hosted database
    python scripts/serve.py --neon --port 8001

Why this exists rather than `DATABASE_URL=... uvicorn ...`: a Postgres
connection string contains `&` (sslmode=require&channel_binding=require), and
`&` is a shell control operator. Sourcing an env file that contains one
silently truncates the value at the ampersand and backgrounds the rest as a
command. The service then connects somewhere else entirely and the failure
looks like a network problem.

Reading the file in Python removes the shell from the path completely.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def read_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser. No shell, no expansion, no surprises."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--neon", action="store_true",
                    help="use the hosted database from .env.neon")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()

    env = {**os.environ, **read_env_file(ROOT / ".env")}

    if args.neon:
        hosted = read_env_file(ROOT / ".env.neon")
        if not hosted.get("DATABASE_URL"):
            print(f"{RED}No .env.neon.{RESET} Run scripts/deploy_db.py first.")
            return 1
        env.update(hosted)

    dsn = env.get("DATABASE_URL", "")
    host = dsn.split("@")[-1].split("/")[0] if "@" in dsn else "?"
    role = dsn.split("//")[-1].split(":")[0] if "//" in dsn else "?"
    print(f"{DIM}database{RESET} {host}  {DIM}as{RESET} {role}")
    if role != "ce_app":
        # Row level security does not apply to a table's owner. Connecting as
        # one turns every policy off and nothing anywhere reports it.
        print(f"{RED}WARNING: not connecting as ce_app. RLS will not "
              f"apply.{RESET}")

    cmd = [sys.executable, "-m", "uvicorn", "app.main:app",
           "--host", "127.0.0.1", "--port", str(args.port)]
    if args.reload:
        cmd.append("--reload")
    print(f"{GREEN}serving{RESET} http://127.0.0.1:{args.port}\n")
    return subprocess.call(cmd, cwd=ROOT / "services" / "api", env=env)


if __name__ == "__main__":
    raise SystemExit(main())

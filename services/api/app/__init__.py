"""The Coaching Engine API.

Loading .env here, in the package __init__, is deliberate. providers.py reads
its keys at import time, so configuration has to be in the environment before
any submodule is imported. Doing it here means the service is self-configuring
however it is launched: uvicorn from a shell, docker compose, or a test.

The alternative, relying on the launcher to export the right variables, fails
silently: the service starts, /health says the database is up, and every AI
call returns 503 because a key was never set.

In a deployed container there IS no .env, and there are fewer directories above
this file than there are in the repo. Walking a fixed number of parents raised
IndexError on import and the platform showed a dead service with no clue why,
so the search below is bounded by what actually exists.
"""

from pathlib import Path

from dotenv import load_dotenv

# Nearest .env at or above this package, if there is one. In the repo that is
# the root; in a container it is usually nothing, and the platform's own
# environment variables are already set.
for _parent in Path(__file__).resolve().parents:
    _candidate = _parent / ".env"
    if _candidate.is_file():
        load_dotenv(_candidate, override=False)
        break

"""Deploy the API to Cloud Run, without needing the gcloud SDK.

    python scripts/deploy_cloudrun.py --check     # permissions only, changes nothing
    python scripts/deploy_cloudrun.py             # build, push, deploy

Uses the service account JSON in the repo root and talks to the Cloud Run and
Artifact Registry REST APIs directly, so there is nothing to install beyond
Docker, which is already required to run this project locally.

WHY CLOUD RUN AND NOT RENDER
    Render's free tier sleeps after fifteen idle minutes and takes 25 to 50
    seconds to wake. Cloud Run can hold one warm instance (--min-instances 1),
    which removes the cold start entirely. That is the whole reason to move:
    not cost, not scale, just never watching a judge stare at a spinner.

WHAT HAS TO BE TRUE FIRST
    Two separate things, which fail identically to the eye and need different
    people to fix:

      1. The Cloud Run and Artifact Registry APIs are enabled on the project.
         Only an Owner can do that, and no role granted to anybody substitutes
         for it.
      2. The SERVICE ACCOUNT in the key file holds the four roles. Roles
         granted to a person do not apply to a service account: they are
         different identities, and this catches everybody once.

    --check says which of the two is in the way, and who can fix it.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REGION = "europe-west1"          # same region as the Neon database, Frankfurt-ish
SERVICE = "coaching-engine-api"
REPO = "coaching-engine"
GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def credentials():
    from google.oauth2 import service_account
    import google.auth.transport.requests as gr

    files = glob.glob(os.path.join(ROOT, "project-*.json"))
    if not files:
        sys.exit(f"{RED}No service-account JSON in the repo root.{RESET}")
    info = json.load(open(files[0]))
    project = info["project_id"]
    creds = service_account.Credentials.from_service_account_file(
        files[0], scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(gr.Request())
    return files[0], project, creds, info.get("client_email", "unknown")


def api(creds, url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {creds.token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or "{}")
        except Exception:
            return e.code, {}


def env_pairs() -> list[dict]:
    """Everything the container needs, read from the .env used locally.

    Secrets never go in the image and never go in this file. They are sent once
    over TLS as part of the service definition, which is the same trust model
    as pasting them into the Render dashboard.
    """
    # These names are the ones providers.py actually reads. The first version of
    # this list invented VERTEX_PROJECT_ID and VERTEX_LOCATION, which exist
    # nowhere in the codebase, so Vertex would have been silently absent in
    # production while /health still reported the service as up.
    wanted = [
        "DATABASE_URL", "OPENAI_API_KEY", "OPENAI_API_KEY_FALLBACK",
        "GROQ_API_KEY", "ELEVENLABS_API_KEY", "MANUS_API_KEY",
        "GEMINI_API_KEY", "GCP_PROJECT_ID", "GCP_REGION",
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
        "CE_ALLOWED_ORIGINS", "CE_DAILY_USD_LIMIT", "CE_VOICE_RESERVE",
        "CE_MAX_PRACTICE_TURNS", "CE_DEFAULT_ACTOR", "CE_ENV",
    ]
    found: dict[str, str] = {}
    # .env is this laptop's environment and its DATABASE_URL is the Docker
    # Postgres on localhost:5433. Shipping that to Cloud Run produces a service
    # that starts, answers /health, and reports the database as unreachable
    # after a thirty second timeout, because it is dialling a machine that is
    # not there. .env.neon holds the hosted database and is read second so it
    # wins, which is the same precedence scripts/serve.py --neon uses.
    for name in (".env", ".env.neon"):
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in wanted and v:
                found[k] = v            # later wins, matching dotenv
    # Vertex needs the service account as a DOCUMENT, not a path. Locally
    # GOOGLE_APPLICATION_CREDENTIALS points at a file on this machine, which
    # means nothing inside a container, so the file is read and shipped as
    # GOOGLE_CREDENTIALS_JSON, which is what providers.py materialises back to
    # a temp file at startup. Same thing Render is given.
    if "GOOGLE_CREDENTIALS_JSON" not in found:
        key_files = glob.glob(os.path.join(ROOT, "project-*.json"))
        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        source = path if os.path.isfile(path) else (key_files[0] if key_files else "")
        if source:
            with open(source, encoding="utf-8") as fh:
                found["GOOGLE_CREDENTIALS_JSON"] = fh.read()

    # Refuse rather than deploy something that cannot possibly work.
    dsn = found.get("DATABASE_URL", "")
    if "localhost" in dsn or "127.0.0.1" in dsn:
        sys.exit(f"{RED}DATABASE_URL points at localhost.{RESET} Cloud Run "
                 f"cannot reach this machine. Put the hosted database in "
                 f".env.neon (scripts/deploy_db.py writes it).")

    return [{"name": k, "value": v} for k, v in found.items()]


def check(creds, project, email) -> bool:
    """Say which of the two different blockers is in the way.

    These fail identically to the eye and need opposite people to fix them:

      SERVICE_DISABLED   the API is switched off for the whole project. Only
                         an Owner can turn it on, and no role granted to
                         anybody changes it.
      PERMISSION_DENIED  the API is on and THIS identity is not allowed to use
                         it. Turning the API on again does nothing.

    The first version of this script assumed the first case and said so even
    when the second was true, which sent somebody to press a button that was
    already pressed.
    """
    print()
    print(f"Project   {DIM}{project}{RESET}")
    print(f"Acting as {DIM}{email}{RESET}")
    print()

    disabled, denied = [], []
    for label, url in [
        ("Cloud Run",
         f"https://run.googleapis.com/v2/projects/{project}/locations/{REGION}/services"),
        ("Artifact Registry",
         f"https://artifactregistry.googleapis.com/v1/projects/{project}/locations/{REGION}/repositories"),
    ]:
        code, body = api(creds, url)
        error = body.get("error", {}) if isinstance(body, dict) else {}
        status = str(error.get("status", ""))
        message = str(error.get("message", ""))
        if code == 200:
            print(f"  {GREEN}ready{RESET}     {label}")
        elif "SERVICE_DISABLED" in status or "has not been used" in message:
            print(f"  {RED}API off{RESET}   {label}: not enabled on this project")
            disabled.append(label)
        elif code == 403:
            print(f"  {YELLOW}no access{RESET} {label}: API is on, this account may not use it")
            denied.append(label)
        else:
            print(f"  {RED}error{RESET}     {label}: HTTP {code} {message[:70]}")
            denied.append(label)

    if disabled:
        print(f"""
{YELLOW}An Owner has to switch these on: {', '.join(disabled)}.{RESET}
Two clicks each, costs nothing:

  https://console.cloud.google.com/apis/library/run.googleapis.com?project={project}
  https://console.cloud.google.com/apis/library/artifactregistry.googleapis.com?project={project}""")

    if denied and not disabled:
        print(f"""
{YELLOW}The APIs are on. This service account is not allowed to use them.{RESET}

Roles granted to a person do not apply to a service account: they are separate
identities. The four roles have to be granted to this exact email:

  {email}

Someone with Owner or Project IAM Admin does it here, once:

  https://console.cloud.google.com/iam-admin/iam?project={project}

  GRANT ACCESS, paste that email as the principal, and add:
      Cloud Run Admin              deploy and update the service
      Artifact Registry Writer     push the image
      Service Account User         let the service run as an identity
      Storage Object Admin         the layer upload the push uses

Nothing else is needed, and Secret Manager is not needed: the deploy sends the
environment directly with the service definition.

If you would rather deploy as yourself than fix the service account, install
the gcloud SDK, run `gcloud auth login`, and this script is not the path: use
`gcloud run deploy` instead. Granting the four roles is faster.""")

    return not disabled and not denied


def run(cmd: list[str]) -> None:
    print(f"  {DIM}$ {' '.join(cmd[:6])}{'…' if len(cmd) > 6 else ''}{RESET}")
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report readiness and change nothing")
    ap.add_argument("--min-instances", default="1",
                    help="1 keeps an instance warm, which is the point of moving")
    args = ap.parse_args()

    key_file, project, creds, email = credentials()
    if not check(creds, project, email):
        return 1
    if args.check:
        print(f"\n{GREEN}Ready to deploy.{RESET} Re-run without --check.")
        return 0

    host = f"{REGION}-docker.pkg.dev"
    image = f"{host}/{project}/{REPO}/api:{int(time.time())}"

    # 1. a place to put the image.
    #
    # This used to print "already there" for any failure, so a 403 read as
    # success and the run carried on to a docker push that died with
    # "Repository not found" a full image build later. A create that fails for
    # a reason other than "it exists" now stops here and says which reason.
    repo_url = (f"https://artifactregistry.googleapis.com/v1/projects/{project}"
                f"/locations/{REGION}/repositories")

    # Look before creating. An account with Writer but not Administrator gets
    # 403 from the create call whether or not the repository exists, because
    # the permission check runs before the existence check. Creating blindly
    # and reading 403 as "missing" therefore refuses to deploy into a
    # repository that is sitting right there, which is exactly what happened
    # the first time somebody made one by hand.
    code, body = api(creds, f"{repo_url}/{REPO}")
    if code == 200:
        print(f"  {GREEN}repository{RESET} already there")
        code = 200
    else:
        code, body = api(creds, f"{repo_url}?repositoryId={REPO}", "POST",
                         {"format": "DOCKER",
                          "description": "The Coaching Engine API"})
    if code < 400:
        print(f"  {GREEN}repository{RESET} ready")
    elif code == 409:
        print(f"  {GREEN}repository{RESET} already there")
    elif code == 403:
        print(f"""
{YELLOW}This account can push images but cannot create the repository.{RESET}

Artifact Registry Writer allows uploading to a repository that exists. Making
one needs artifactregistry.repositories.create, which comes with Artifact
Registry Administrator. Everything else is already in place: Cloud Run accepts
a deploy from this account, and the image builds.

Someone with Owner or Artifact Registry Administrator does this once:

  https://console.cloud.google.com/artifacts?project={project}

  CREATE REPOSITORY
    Name    {REPO}
    Format  Docker
    Mode    Standard
    Region  {REGION}

Then run this again. No new role is needed afterwards, because pushing into it
is what Writer already allows.""")
        return 1
    else:
        print(f"{RED}Could not create the repository: "
              f"{json.dumps(body)[:300]}{RESET}")
        return 1

    # 2. build and push. Docker authenticates as the service account using the
    #    key directly, which avoids needing gcloud just for a credential helper.
    print("\nBuilding…")
    run(["docker", "build", "-f", "services/api/Dockerfile", "-t", image, "."])
    print("\nPushing…")
    subprocess.run(["docker", "login", "-u", "_json_key", "--password-stdin", host],
                   input=open(key_file, "rb").read(), check=True, cwd=ROOT)
    run(["docker", "push", image])

    # 3. create or update the service
    body = {
        "template": {
            "containers": [{
                "image": image,
                "ports": [{"containerPort": 8000}],
                "env": env_pairs(),
                "resources": {"limits": {"cpu": "1", "memory": "1Gi"}},
            }],
            "scaling": {"minInstanceCount": int(args.min_instances),
                        "maxInstanceCount": 4},
            "timeout": "120s",
        },
    }
    base = f"https://run.googleapis.com/v2/projects/{project}/locations/{REGION}/services"
    code, res = api(creds, f"{base}?serviceId={SERVICE}", "POST", body)
    if code == 409:
        print("\nService exists, updating…")
        code, res = api(creds, f"{base}/{SERVICE}", "PATCH", body)
    if code >= 400:
        print(f"{RED}Deploy failed: {json.dumps(res)[:400]}{RESET}")
        return 1

    # 4. let the public reach it, same as Render does
    api(creds, f"{base}/{SERVICE}:setIamPolicy", "POST",
        {"policy": {"bindings": [{"role": "roles/run.invoker",
                                  "members": ["allUsers"]}]}})

    print("\nWaiting for the revision…")
    url = ""
    for _ in range(40):
        time.sleep(6)
        code, svc = api(creds, f"{base}/{SERVICE}")
        url = svc.get("uri", "")
        conds = {c.get("type"): c.get("state") for c in svc.get("conditions", [])}
        if conds.get("Ready") == "CONDITION_SUCCEEDED" and url:
            break
        if conds.get("Ready") == "CONDITION_FAILED":
            print(f"{RED}Revision failed: {svc.get('conditions')}{RESET}")
            return 1

    print(f"\n{GREEN}Deployed{RESET}  {url}")
    print(f"""
Before you point anything at it:

  curl {url}/health

It must report database up and every provider true. Only then change
NEXT_PUBLIC_API_BASE_URL in Vercel to {url}/api/v1 and redeploy the front end.
Leave Render running until you have done that, so there is always one API that
works.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

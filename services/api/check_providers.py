"""
check_providers.py
==================
Call every provider for real and report exactly what each one does.

Run this before a demo. "The key is set" is not the same as "the call works",
and the difference has bitten us on three of the five providers already: Groq
403s without a User-Agent, Manus wants its key in a header nobody would guess,
and the Google key was live but the API was switched off on the project. A
health check that only looks for a non-empty environment variable would have
reported all three as fine.

    python services/api/check_providers.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import providers as P                                    # noqa: E402

UA = "Mozilla/5.0 (compatible; CoachingEngine/1.0)"
TIMEOUT = 45

OK, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


def _post(url: str, payload: dict | bytes, headers: dict,
          limit: int = 4000) -> tuple[int, str]:
    """limit is generous because the useful part of a cloud error, the project
    number and the machine-readable reason, sits at the END of the body, after
    the human-readable message. Truncating early throws away the half that
    tells you which console to open."""
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read()[:limit].decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:limit].decode("utf-8", "replace")
    except Exception as e:                                  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def _get(url: str, headers: dict, limit: int = 400) -> tuple[int, str]:
    """limit defaults to an excerpt for error reporting. Pass a bigger one when
    the caller needs to parse the body: a truncated JSON document is not a
    parse failure worth swallowing, it is a check that silently stops
    checking."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read()[:limit].decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400].decode("utf-8", "replace")
    except Exception as e:                                  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


# --------------------------------------------------------------- the checks

def check_openai() -> tuple[str, str]:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return SKIP, "OPENAI_API_KEY not set"
    code, body = _post(
        "https://api.openai.com/v1/chat/completions",
        {"model": "gpt-4o-mini", "max_tokens": 5,
         "messages": [{"role": "user", "content": "Reply with the word ok."}]},
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    if code == 200:
        return OK, "chat + embeddings + structured output"
    if code == 429:
        # The distinction that matters before a demo: a per-minute limit
        # clears itself, a per-DAY limit does not.
        spare = " (a spare key is configured)" if os.environ.get(
            "OPENAI_API_KEY_FALLBACK") else " and NO spare key is configured"
        return (WARN if os.environ.get("OPENAI_API_KEY_FALLBACK") else FAIL), (
            f"rate limited{spare}. Free-tier accounts are 50 requests per DAY "
            f"per model; add billing or apply the credits to the org.")
    return FAIL, f"HTTP {code}: {body[:150]}"


def check_groq_chat() -> tuple[str, str]:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        return SKIP, "GROQ_API_KEY not set"
    code, body = _post(
        "https://api.groq.com/openai/v1/chat/completions",
        # Read the model from ROUTES rather than hardcoding one. Groq retired
        # llama-3.3 under us; a check that pins its own model tests a model we
        # do not use and passes while production is broken.
        {"model": P.ROUTES["guest_turn"][1], "max_tokens": 200,
         "messages": [{"role": "user", "content": "Reply with the word ok."}]},
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
         "User-Agent": UA})
    if code == 200:
        return OK, f"{P.ROUTES['guest_turn'][1]} chat"
    if code == 429:
        # The free tier is generous but finite. This is a WARN because the
        # wiring is correct and FALLBACKS will carry the task to OpenAI; it
        # still needs saying, because the demo gets slower when it happens.
        fb = P.FALLBACKS.get("guest_turn")
        return WARN, (f"rate limited on the free tier. Falls back to "
                      f"{fb[0]}/{fb[1]}" if fb else "rate limited, no fallback")
    return FAIL, f"HTTP {code}: {' '.join(body.split())[:130]}"


def check_groq_whisper() -> tuple[str, str]:
    """Transcribe a real WAV we synthesise here, so the check needs no fixture."""
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        return SKIP, "GROQ_API_KEY not set"
    wav = _silence_wav()
    boundary = "----ce-check"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"
        f"{P.ROUTES['transcribe'][1]}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode(),
        wav, f"\r\n--{boundary}--\r\n".encode(),
    ]
    code, body = _post(
        "https://api.groq.com/openai/v1/audio/transcriptions", b"".join(parts),
        {"Authorization": f"Bearer {key}", "User-Agent": UA,
         "Content-Type": f"multipart/form-data; boundary={boundary}"})
    if code == 200:
        return OK, f"{P.ROUTES['transcribe'][1]} accepted audio"
    return FAIL, f"HTTP {code}: {body[:150]}"


def check_elevenlabs() -> tuple[str, str]:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        return SKIP, "ELEVENLABS_API_KEY not set"
    code, body = _get("https://api.elevenlabs.io/v1/user/subscription",
                      {"xi-api-key": key, "User-Agent": UA}, limit=20000)
    if code != 200:
        return FAIL, f"HTTP {code}: {body[:150]}"
    try:
        sub = json.loads(body)
        used = sub.get("character_count", 0)
        cap = sub.get("character_limit", 0)
        left = cap - used
        state = OK if left > 500 else WARN
        return state, f"{left} of {cap} characters left on {sub.get('tier','?')}"
    except Exception as e:                                  # noqa: BLE001
        # Reachable but unreadable is a warning, not a pass. Silence here is
        # how we would walk into a demo with no character budget left.
        return WARN, f"reachable, could not read quota: {type(e).__name__}"


def check_manus() -> tuple[str, str]:
    key = os.environ.get("MANUS_API_KEY", "")
    if not key:
        return SKIP, "MANUS_API_KEY not set"
    # Manus authenticates with a bare API_KEY header, not a bearer token. That
    # is the whole reason this check exists.
    code, body = _post(
        "https://api.manus.ai/v1/tasks",
        {"prompt": "Reply with the single word ok.", "mode": "fast"},
        {"API_KEY": key, "Content-Type": "application/json", "User-Agent": UA})
    if code in (200, 201, 202):
        return OK, "task accepted"
    return FAIL, f"HTTP {code}: {body[:150]}"


def check_google() -> tuple[str, str]:
    """The API-key path to Gemini, which we no longer use.

    Kept as a SKIP rather than deleted: the key is still in .env and someone
    will wonder why nothing checks it. Google is reached through Vertex now,
    with a service account, which is the path that draws on the GCP credits.
    """
    if not any(prov == "gemini" for prov, _ in P.ROUTES.values()):
        return SKIP, "not in use; Google is reached through Vertex AI below"
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return SKIP, "GEMINI_API_KEY not set (no Google model in use)"
    code, body = _post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={key}",
        {"contents": [{"parts": [{"text": "Reply with the word ok."}]}]},
        {"Content-Type": "application/json", "User-Agent": UA})
    if code == 200:
        return OK, "gemini-2.0-flash"
    if code == 429:
        return WARN, "quota exhausted, which is not a configuration problem"

    # Read the structured reason, never a substring of the message. Google's
    # prose mentions several failure modes in one body and grepping it told us
    # to open the wrong console page: the two 403s below look identical in a
    # log and need opposite fixes.
    reason, project = "", ""
    try:
        err = json.loads(body).get("error", {})
        for detail in err.get("details", []):
            if detail.get("@type", "").endswith("ErrorInfo"):
                reason = detail.get("reason", "")
                project = (detail.get("metadata", {})
                           .get("consumer", "")).replace("projects/", "")
    except Exception:                                       # noqa: BLE001
        pass

    where = f"project {project}" if project else "the GCP project"

    # Google alternates between these two reasons on byte-identical requests,
    # so neither one on its own tells you the whole story. Observed: the same
    # call returning SERVICE_DISABLED and then API_KEY_SERVICE_BLOCKED seconds
    # apart. Both conditions are genuinely true here, and fixing only the one
    # you happened to be shown leaves you with the same 403 and no idea why.
    if reason in ("SERVICE_DISABLED", "API_KEY_SERVICE_BLOCKED"):
        return FAIL, (
            f"403 {reason} on {where}. Google alternates between these two "
            f"reasons, so do BOTH: (1) enable the API at console.cloud.google"
            f".com/apis/library/generativelanguage.googleapis.com, and (2) at "
            f"console.cloud.google.com/apis/credentials open the key and under "
            f"'API restrictions' allow Generative Language API.")
    if reason == "API_KEY_INVALID":
        return FAIL, "the key itself is not valid; issue a new one."
    return FAIL, f"HTTP {code} {reason}: {' '.join(body.split())[:130]}"


def check_vertex() -> tuple[str, str]:
    """Vertex AI proper: service account auth, not an API key.

    Every failure below is reported with the exact next action, because the
    setup has five separate places it can be wrong and the error Google
    returns for four of them is an unhelpful 403.
    """
    project = os.environ.get("GCP_PROJECT_ID", "")
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    region = os.environ.get("GCP_REGION", "europe-west1")

    if not project and not creds_path:
        return SKIP, "not configured (GCP_PROJECT_ID + service account JSON)"
    if not project:
        return FAIL, ("GCP_PROJECT_ID is empty. Use the project ID string, "
                      "not the project number.")
    if project.isdigit():
        return FAIL, (f"GCP_PROJECT_ID is '{project}', which is the project "
                      f"NUMBER. Vertex wants the project ID, the string form.")
    if not creds_path:
        return FAIL, ("GOOGLE_APPLICATION_CREDENTIALS is empty. Point it at "
                      "the service account JSON you downloaded.")
    if not Path(creds_path).exists():
        return FAIL, f"no file at GOOGLE_APPLICATION_CREDENTIALS: {creds_path}"

    try:
        import google.auth                                   # noqa: PLC0415
        from google.auth.transport.requests import Request   # noqa: PLC0415
    except ImportError:
        return FAIL, "google-auth not installed: pip install google-auth"

    try:
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
    except Exception as e:                                   # noqa: BLE001
        return FAIL, f"could not mint a token: {type(e).__name__}: {e}"[:180]

    # The model we actually route to. Hardcoding one meant the check failed
    # while production was fine, which is worse than no check at all.
    model = next((m for prov, m in P.ROUTES.values() if prov == "vertex"),
                 "gemini-2.5-flash-lite")
    url = (f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}"
           f"/locations/{region}/publishers/google/models/{model}"
           f":generateContent")
    code, body = _post(url,
                       {"contents": [{"role": "user",
                                      "parts": [{"text": "Reply with ok."}]}]},
                       {"Authorization": f"Bearer {creds.token}",
                        "Content-Type": "application/json"})
    if code == 200:
        return OK, f"{model} in {region}"
    if code == 403 and "aiplatform.googleapis.com" in body:
        # Google renamed Vertex AI to Agent Platform, so the console and the
        # error message use a name the code does not. Link straight to the
        # enable page with the project already selected, because searching for
        # "Vertex AI" in the API library now finds the wrong thing.
        return FAIL, (
            f"the API is not enabled on {project}. One click: "
            f"https://console.cloud.google.com/apis/library/"
            f"aiplatform.googleapis.com?project={project}   "
            f"(it is listed as 'Vertex AI API' / 'Agent Platform API'). "
            f"Everything else already works: the service account "
            f"authenticates and the project resolves.")
    if code == 403:
        return FAIL, (f"the service account lacks the Vertex AI User role on "
                      f"{project}. Grant roles/aiplatform.user, then re-run. "
                      f"({' '.join(body.split())[:90]})")
    if code == 404:
        return FAIL, (f"{model} is not served from {region}. Verified working "
                      f"in europe-west1 and us-central1: gemini-2.5-flash, "
                      f"gemini-2.5-flash-lite, gemini-2.5-pro. The 2.0 names "
                      f"are gone.")
    if code == 429:
        return WARN, "quota exhausted, not a configuration problem"
    return FAIL, f"HTTP {code}: {' '.join(body.split())[:140]}"


def check_langfuse() -> tuple[str, str]:
    """Tracing is deliberately silent in production, so check it explicitly.

    export_run() swallows every exception, because a tracing outage must not
    cost a manager their recommendation. The first version of it called a 2.x
    API that does not exist in 4.x and the swallow hid that completely: the
    product was fine and tracing never once worked. This is the only thing
    that would have caught it.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app import tracing                                   # noqa: PLC0415
    if not tracing.enabled():
        return SKIP, "no keys set; tracing is off and the API is unaffected"
    result = tracing.selftest()
    if result.get("ok"):
        return OK, f"trace accepted by {result['host']}"
    return FAIL, f"configured but not working: {result.get('reason')}"


def check_ollama() -> tuple[str, str]:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    code, body = _get(f"{host}/api/tags", {"User-Agent": UA})
    if code == 200:
        try:
            names = [m["name"] for m in json.loads(body).get("models", [])]
            return OK, f"local, {len(names)} model(s)"
        except Exception:                                   # noqa: BLE001
            return OK, "local daemon reachable"
    return SKIP, "no local daemon (optional, offline fallback only)"


def _silence_wav(ms: int = 400, rate: int = 16000) -> bytes:
    """A valid, tiny mono WAV. Enough to prove the endpoint accepts audio."""
    import struct
    n = int(rate * ms / 1000)
    data = b"\x00\x00" * n
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(data)) + data)


CHECKS = [
    ("OpenAI          chat/embeddings", check_openai),
    ("Groq            chat", check_groq_chat),
    ("Groq            whisper", check_groq_whisper),
    ("ElevenLabs      text to speech", check_elevenlabs),
    ("Manus           agent tasks", check_manus),
    ("Google          gemini API", check_google),
    ("Google          Vertex AI", check_vertex),
    ("Langfuse        tracing", check_langfuse),
    ("Ollama          local fallback", check_ollama),
]


def main() -> int:
    print(f"\nProvider check   routes in use: "
          f"{', '.join(sorted({p for p, _ in P.ROUTES.values()}))}")
    for task, (prov, model) in sorted(P.ROUTES.items()):
        fb = P.FALLBACKS.get(task)
        tail = f"   fallback {fb[0]}/{fb[1]}" if fb else ""
        print(f"    {task:20} {prov}/{model}{tail}")
    print()
    results = []
    for label, fn in CHECKS:
        t0 = time.time()
        try:
            state, detail = fn()
        except Exception as e:                              # noqa: BLE001
            state, detail = FAIL, f"{type(e).__name__}: {e}"
        ms = int((time.time() - t0) * 1000)
        results.append((label, state, detail))
        print(f"  [{state}] {label:32} {ms:>5}ms  {detail}")

    warned = [r for r in results if r[1] == WARN]
    for label, _, detail in warned:
        print(f"  note  {label.split()[0]}: {detail}")
    failed = [r for r in results if r[1] == FAIL]
    print()
    if failed:
        print(f"{len(failed)} provider(s) failing:")
        for label, _, detail in failed:
            print(f"  - {label.split()[0]}: {detail}")
    else:
        print("Every configured provider answered.")
    # A skipped optional provider is not a failure.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

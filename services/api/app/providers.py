"""
providers.py
============
One door to every model provider.

Nothing else in the system calls an AI provider directly. That is deliberate
and it buys three things:

* Tracing. Every call, its token count and its latency pass through one place,
  so "show me what the agent actually did" is a query rather than an
  archaeology exercise.
* Provider swap. Gemini is wired and ready; it is disabled only because the
  Generative Language API has not been enabled on the GCP project. When it is,
  routing a task to Gemini is a one-line change here, not a change at seven
  call sites.
* Failing loudly. A provider outage raises. It never silently falls back to a
  different model, because a silent swap would pollute the calibration series
  that the accuracy claim on stage depends on.

Routing follows 01B section 7: cheap models for schema-constrained extraction,
better models for anything a manager will read.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from . import spend
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

# A bare urllib User-Agent gets a 403 Cloudflare 1010 from Groq. Cost an hour
# to find; leave this here.
UA = "coaching-engine/0.1 (+https://github.com/IronNathanAlvares)"

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
# A second OpenAI key, used only when the first is rate limited.
#
# Not redundancy for its own sake. The organisation key is on the free tier,
# which is FIFTY requests per day per model: one agent run costs three, one
# practice session costs six, and the end-to-end suite costs about twenty. A
# demo would exhaust it in ten minutes and then have no AI at all, with a reset
# that is 24 hours away rather than 24 minutes.
#
# Delete this the moment billing is on the org account. It is a splint.
OPENAI_KEY_FALLBACK = os.environ.get("OPENAI_API_KEY_FALLBACK", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
MANUS_KEY = os.environ.get("MANUS_API_KEY", "")

# Vertex AI is a different product from the Gemini API, and conflating the two
# is why this took three attempts. Same models, different everything else:
#
#   Gemini API   generativelanguage.googleapis.com   an API key (AIza...)
#   Vertex AI    {region}-aiplatform.googleapis.com  a service account
#
# Vertex does not accept API keys at all. It wants an OAuth bearer token minted
# from a service account, which is also why it is the one that draws on GCP
# credits and the one worth citing as our cloud provider.
VERTEX_PROJECT = os.environ.get("GCP_PROJECT_ID", "")
VERTEX_REGION = os.environ.get("GCP_REGION", "europe-west1")


class ProviderError(RuntimeError):
    """Raised when a provider fails. Never swallowed, never silently retried
    against a different model."""


@dataclass
class ModelCall:
    """One call, recorded. Collected per agent run for the trace view."""
    task: str
    provider: str
    model: str
    ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    fell_back: bool = False       # true when the first-choice provider failed
    usd: float = 0.0              # what this call cost, at list price


@dataclass
class Step:
    """One decision in the pipeline, and who made it.

    `actor` is the whole point. A trace of model calls alone invites exactly
    the reading we want to refute, that the product is a prompt with a database
    behind it. Recording the deterministic steps in the same timeline, at the
    same granularity, shows where the reasoning actually lives: the model
    drafts and classifies, and code decides what may be said, who hears about
    it, and whether it ships at all.
    """
    seq: int
    actor: str                    # "code" | "model" | "database"
    label: str
    ms: int = 0
    detail: dict = field(default_factory=dict)


@dataclass
class Trace:
    calls: list[ModelCall] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)

    @property
    def total_ms(self) -> int:
        return sum(c.ms for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return sum(c.prompt_tokens + c.completion_tokens for c in self.calls)

    @property
    def total_usd(self) -> float:
        return round(sum(c.usd for c in self.calls), 6)

    def step(self, actor: str, label: str, ms: int = 0, **detail) -> None:
        self.steps.append(Step(seq=len(self.steps) + 1, actor=actor,
                               label=label, ms=ms, detail=detail))

    def as_dict(self) -> dict:
        decisive = [st for st in self.steps if st.detail.get("decisive")]
        return {
            "calls": [vars(c) for c in self.calls],
            "steps": [vars(st) for st in self.steps],
            "total_ms": self.total_ms,
            "total_tokens": self.total_tokens,
            "total_usd": self.total_usd,
            # Counted here rather than in the page, so the number cannot drift
            # from the trace it describes.
            "decisions_by_code": sum(1 for st in decisive if st.actor == "code"),
            "decisions_by_model": sum(1 for st in decisive if st.actor == "model"),
        }


# --------------------------------------------------------------------------
# Task routing. Change these, not the call sites.
# --------------------------------------------------------------------------

ROUTES: dict[str, tuple[str, str]] = {
    # task                     provider   model
    "score":                   ("openai", "gpt-4o-mini"),
    "coach":                   ("openai", "gpt-4o"),
    # On Vertex, which makes "running on Google Cloud" a fact rather than a
    # slide. classify is the right task to move: one call, a strict enum the
    # code already constrains, and a fallback underneath it. It is slower than
    # gpt-4o-mini (these are reasoning models and spend thinking tokens), so it
    # stays off the guest turn, which is the only thing a human waits on live.
    "classify":                ("vertex", "gemini-2.5-flash-lite"),
    # The guest is the only task a human waits on in real time, and Groq
    # returns in roughly half the time for output we cannot tell apart. Every
    # other task runs behind a spinner or a shift, where latency buys nothing.
    "guest_turn":              ("groq",   "qwen/qwen3.8-27b"),
    "extract_incident":        ("openai", "gpt-4o-mini"),
    # Spanish to English for a staff debrief, with regional glosses retrieved
    # into the prompt. Llama 70B on Groq is what the Glorvox thesis deployed
    # after comparing fourteen models across seven providers: joint-best on
    # conveying regionally marked terms (64.3%) and 1,186 ms.
    "translate":               ("groq",   "llama-3.3-70b-versatile"),
    # Reading a whole corpus and finding what is missing from it is the
    # hardest reasoning task in the product, and it runs once per property at
    # onboarding rather than once per shift, so it gets the better model.
    "audit_standards":         ("openai", "gpt-4o"),
    # Writing a scene is the only genuinely creative task in the product,
    # and the only one that runs warm. gpt-4o rather than mini: a weak
    # scenario is not obviously weak until somebody has practised against
    # it and learned nothing.
    "write_scenario":          ("openai", "gpt-4o"),
    # A staff member is holding a phone with a guest in front of them, so
    # this is the second task in the product where latency is felt by a
    # human in real time. Small model, strict enum, and the gate behind it
    # is code either way.
    "permission_check":        ("openai", "gpt-4o-mini"),
    "embed":                   ("openai", "text-embedding-3-small"),
    "transcribe":              ("groq",   "whisper-large-v3-turbo"),
}

# Where a task goes when its first choice fails.
#
# This exists because of the demo, and it is honest about that. A provider
# outage during a five minute pitch is not a hypothetical: Groq has changed its
# model catalogue under us once already, retiring the exact model id we had
# pinned. Falling back to a slower model beats a stack trace on a projector.
# Every fallback is recorded in the trace, so the glass box still shows what
# actually happened rather than what we hoped would.
FALLBACKS: dict[str, tuple[str, str]] = {
    "guest_turn": ("openai", "gpt-4o-mini"),
    # The coaching draft had no second provider, so any failure on it took the
    # whole run down. gpt-4o-mini writes a weaker headline than gpt-4o, and a
    # weaker headline that ships beats a stack trace on a projector.
    "coach":      ("openai", "gpt-4o-mini"),
    "score":      ("openai", "gpt-4o"),
    "classify":   ("openai", "gpt-4o-mini"),
    # A debrief that cannot be translated is a staff member reading their own
    # words back with no English beside them, so this one needs a second path.
    "translate":  ("openai", "gpt-4o-mini"),
    "audit_standards": ("vertex", "gemini-2.5-flash-lite"),
    "write_scenario": ("openai", "gpt-4o-mini"),
    "permission_check": ("vertex", "gemini-2.5-flash-lite"),
}

# Matches the vector(768) column in db/schema.sql. OpenAI supports shortening
# an embedding via the dimensions parameter, and Gemini's text-embedding-004 is
# natively 768, so both providers land on the same column without a migration.
EMBED_DIMS = 768


_vertex_creds = None


def _vertex_credentials_file() -> str | None:
    """Where the service account JSON lives, materialising it if needed.

    google-auth wants a FILE. A container platform gives you environment
    variables and an ephemeral disk, so GOOGLE_CREDENTIALS_JSON carries the
    whole document and this writes it once to a temp path. Without it Vertex
    works locally and fails in production, which is the worst place to find out.
    """
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if path and Path(path).is_file():
        return path

    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
    if not raw:
        return None
    import json as _json
    import tempfile
    try:
        _json.loads(raw)                       # fail loudly on a mangled paste
    except ValueError:
        raise ProviderError(
            "GOOGLE_CREDENTIALS_JSON is not valid JSON. Paste the whole file "
            "contents, including the braces.") from None
    target = Path(tempfile.gettempdir()) / "ce-vertex-sa.json"
    if not target.exists() or target.read_text(encoding="utf-8") != raw:
        target.write_text(raw, encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(target)
    return str(target)


def _vertex_token() -> str:
    """Mint (and refresh) an access token from the service account.

    GOOGLE_APPLICATION_CREDENTIALS points at the JSON key file. google-auth
    caches the credentials object and refreshes the token when it is within the
    skew window, so this is cheap to call per request and we never hold a token
    past its life.
    """
    global _vertex_creds
    if not VERTEX_PROJECT:
        raise ProviderError("GCP_PROJECT_ID is not set")
    if not _vertex_credentials_file():
        raise ProviderError(
            "No service account. Set GOOGLE_APPLICATION_CREDENTIALS to the "
            "JSON file path, or GOOGLE_CREDENTIALS_JSON to its contents.")
    try:
        from google.auth.transport.requests import Request   # noqa: PLC0415
        import google.auth                                   # noqa: PLC0415
    except ImportError:
        raise ProviderError(
            "google-auth is not installed. pip install google-auth") from None

    if _vertex_creds is None:
        _vertex_creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not _vertex_creds.valid:
        _vertex_creds.refresh(Request())
    return _vertex_creds.token


def _vertex_url(model: str, verb: str = "generateContent") -> str:
    return (f"https://{VERTEX_REGION}-aiplatform.googleapis.com/v1/projects/"
            f"{VERTEX_PROJECT}/locations/{VERTEX_REGION}/publishers/google/"
            f"models/{model}:{verb}")


# One retry, for transport failures only.
#
# A dropped TCP connection, a DNS blip or a TLS handshake that loses a race is
# not a decision the provider made, and it is not something to surface as a 500
# in front of an audience. Observed here: an intermittent
# CERTIFICATE_VERIFY_FAILED from a TLS-inspecting network, roughly one call in
# fifteen, with the same call succeeding immediately afterwards.
#
# HTTP errors are deliberately NOT retried. A 400 is a bug in our payload, a
# 401 is a bad key and a 429 is a rate limit that a retry makes worse; all
# three should fail fast so the fallback in complete() can pick the task up.
_TRANSPORT_RETRIES = 1
_RETRY_BACKOFF_S = 0.6


# Briefs, keyed by task id. A finished document never changes, and the page
# polls every few seconds while a manager watches it.
_BRIEF_CACHE: dict[str, dict] = {}


def _get(url: str, headers: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read()[:400].decode("utf-8", "replace")
        raise ProviderError(f"HTTP {e.code} from {url.split('/')[2]}: {body}") from None


def _get_text(url: str, timeout: int = 60) -> str:
    """Download an attachment. The signed CDN URL carries its own auth, so the
    API key must NOT be attached: sending it to a third party CDN would leak
    the credential for no benefit."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _post(url: str, payload: dict, headers: dict, timeout: int = 90) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": UA, "Content-Type": "application/json", **headers})
    host = url.split("/")[2]

    for attempt in range(_TRANSPORT_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read()[:400].decode("utf-8", "replace")
            raise ProviderError(f"HTTP {e.code} from {host}: {body}") from None
        except Exception as e:
            if attempt < _TRANSPORT_RETRIES:
                time.sleep(_RETRY_BACKOFF_S)
                continue
            raise ProviderError(
                f"{type(e).__name__} calling {host}: {e}") from None
    raise ProviderError(f"{host} unreachable")


# --------------------------------------------------------------------------
# Chat / structured output
# --------------------------------------------------------------------------

def plain(text: str) -> str:
    """Strip em dashes out of anything a model wrote.

    Every other string on the site is written by us and has none. Generated
    prose is the one place they reappear, and one em dash in a suggested clause
    is enough to make a page that is otherwise in the product's own voice read
    as machine output. Replaced with the punctuation a person would have used:
    a comma mid-sentence, nothing at all where it was doing a comma's job
    already.
    """
    if not text:
        return text
    return (text.replace(" — ", ", ")
                .replace("— ", ", ")
                .replace(" —", ", ")
                .replace("—", ", "))


def complete(task: str, system: str, user: str, *, schema: dict | None = None,
             temperature: float = 0.0, trace: Trace | None = None,
             max_tokens: int = 1500) -> Any:
    """Run a task. Returns parsed JSON when a schema is given, else text.

    temperature defaults to 0: scoring a transcript against a written anchor is
    a matching problem, not a creative one, and non-determinism here shows up
    later as noise in the calibration statistic.
    """
    # Before the call, not after. The ceiling exists to stop a runaway loop,
    # and a loop that only notices it has overspent afterwards is not stopped.
    spend.check()

    attempts = [ROUTES[task]]
    if task in FALLBACKS and FALLBACKS[task] != ROUTES[task]:
        attempts.append(FALLBACKS[task])

    last: ProviderError | None = None
    for index, (provider, model) in enumerate(attempts):
        try:
            return _complete_once(task, provider, model, system, user,
                                  schema=schema, temperature=temperature,
                                  trace=trace, max_tokens=max_tokens,
                                  fell_back=index > 0)
        except ProviderError as exc:
            last = exc
            if trace is not None and index + 1 < len(attempts):
                nxt = attempts[index + 1]
                trace.step("code", f"Provider {provider} failed, falling back "
                                   f"to {nxt[0]}",
                           failed_provider=provider, failed_model=model,
                           error=str(exc)[:180],
                           note=("Recorded rather than hidden. A demo that "
                                 "silently swaps models is telling you "
                                 "something untrue about what you just saw."))
    raise last if last else ProviderError(f"task '{task}' had no route")


def _complete_once(task: str, provider: str, model: str, system: str, user: str,
                   *, schema: dict | None, temperature: float,
                   trace: Trace | None, max_tokens: int,
                   fell_back: bool = False) -> Any:
    """One attempt at one provider. complete() owns the retry policy."""
    started = time.time()

    if provider == "openai":
        if not OPENAI_KEY:
            raise ProviderError("OPENAI_API_KEY is not set")
        payload: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            }
        try:
            data = _post("https://api.openai.com/v1/chat/completions", payload,
                         {"Authorization": f"Bearer {OPENAI_KEY}"})
        except ProviderError as exc:
            if "HTTP 429" not in str(exc) or not OPENAI_KEY_FALLBACK:
                raise
            if trace is not None:
                trace.step("code", "Primary OpenAI key rate limited, using "
                                   "the spare",
                           note=("The organisation key is on the free tier. "
                                 "Recorded rather than hidden: the run that "
                                 "follows was not served by the key we say we "
                                 "use."))
            data = _post("https://api.openai.com/v1/chat/completions", payload,
                         {"Authorization": f"Bearer {OPENAI_KEY_FALLBACK}"})
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

    elif provider == "groq":
        # Groq speaks the OpenAI chat protocol, including strict json_schema,
        # so the payload is identical bar the host and the key.
        if not GROQ_KEY:
            raise ProviderError("GROQ_API_KEY is not set")
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True,
                                "schema": schema},
            }
        data = _post("https://api.groq.com/openai/v1/chat/completions", payload,
                     {"Authorization": f"Bearer {GROQ_KEY}"})
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        if not (text or "").strip():
            # Reasoning models on Groq can spend the whole budget thinking and
            # return an empty content field. Empty is a failure, not an answer:
            # say so here so the fallback fires instead of a JSON parse error
            # surfacing three frames away.
            raise ProviderError(f"groq/{model} returned empty content")

    elif provider == "vertex":
        # Same request body as the Gemini API. Only the host and the auth
        # differ, which is the entire practical difference between the two.
        # Gemini 2.5 spends "thinking" tokens before it answers, and they come
        # out of the same budget. A limit sized for the answer alone returns
        # finishReason MAX_TOKENS with an empty candidate, which reads like the
        # model refusing rather than running out of room.
        gen: dict = {"temperature": temperature,
                     "maxOutputTokens": max(max_tokens, 2048)}
        if schema is not None:
            gen["responseMimeType"] = "application/json"
            gen["responseSchema"] = _to_gemini_schema(schema)
        data = _post(_vertex_url(model), {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen,
        }, {"Authorization": f"Bearer {_vertex_token()}"})
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise ProviderError(
                f"vertex/{model} returned no candidate "
                f"(finishReason: "
                f"{(data.get('candidates') or [{}])[0].get('finishReason')})"
            ) from None
        usage_meta = data.get("usageMetadata", {})
        usage = {"prompt_tokens": usage_meta.get("promptTokenCount", 0),
                 "completion_tokens": usage_meta.get("candidatesTokenCount", 0)}

    elif provider == "gemini":
        if not GEMINI_KEY:
            raise ProviderError("GEMINI_API_KEY is not set")
        # v1beta, not v1. Every current model id (the gemini-2.x family
        # included) is only served from v1beta; v1 answers 404 for them, which
        # reads like a bad key and sends you looking in the wrong place.
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={GEMINI_KEY}")
        gen: dict = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if schema is not None:
            gen["responseMimeType"] = "application/json"
            gen["responseSchema"] = _to_gemini_schema(schema)
        data = _post(url, {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": gen,
        }, {})
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = {}

    else:
        raise ProviderError(f"unknown provider '{provider}' for task '{task}'")

    charged = spend.record(model, usage.get("prompt_tokens", 0),
                           usage.get("completion_tokens", 0))
    if trace is not None:
        trace.calls.append(ModelCall(
            task=task, provider=provider, model=model,
            ms=int((time.time() - started) * 1000),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            fell_back=fell_back, usd=charged))

    if schema is None:
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ProviderError(f"task '{task}' returned malformed JSON") from None


def _to_gemini_schema(schema: dict) -> dict:
    """Gemini rejects the JSON Schema keywords OpenAI accepts."""
    drop = {"additionalProperties", "$schema", "strict"}
    out = {}
    for k, v in schema.items():
        if k in drop:
            continue
        if k == "properties":
            out[k] = {pk: _to_gemini_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            out[k] = _to_gemini_schema(v)
        else:
            out[k] = v
    return out


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------

def embed(texts: list[str], trace: Trace | None = None) -> list[list[float]]:
    """Embed a batch. Always EMBED_DIMS long, whichever provider serves it."""
    if not texts:
        return []
    provider, model = ROUTES["embed"]
    started = time.time()

    if provider == "openai":
        if not OPENAI_KEY:
            raise ProviderError("OPENAI_API_KEY is not set")
        try:
            data = _post("https://api.openai.com/v1/embeddings",
                         {"model": model, "input": texts,
                          "dimensions": EMBED_DIMS},
                         {"Authorization": f"Bearer {OPENAI_KEY}"}, timeout=120)
        except ProviderError as exc:
            if "HTTP 429" not in str(exc) or not OPENAI_KEY_FALLBACK:
                raise
            data = _post("https://api.openai.com/v1/embeddings",
                         {"model": model, "input": texts,
                          "dimensions": EMBED_DIMS},
                         {"Authorization": f"Bearer {OPENAI_KEY_FALLBACK}"},
                         timeout=120)
        vectors = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
        spend.record(model, data.get("usage", {}).get("prompt_tokens", 0), 0)
    elif provider == "vertex":
        data = _post(_vertex_url(model, "predict"),
                     {"instances": [{"content": t} for t in texts]},
                     {"Authorization": f"Bearer {_vertex_token()}"}, timeout=120)
        vectors = [p["embeddings"]["values"] for p in data["predictions"]]

    elif provider == "gemini":
        # text-embedding-004 is natively 768-dimensional, which is exactly the
        # width of the vector column. That is why this is a real fallback and
        # not a migration: either provider drops into the same table.
        if not GEMINI_KEY:
            raise ProviderError("GEMINI_API_KEY is not set")
        data = _post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:batchEmbedContents?key={GEMINI_KEY}",
            {"requests": [{"model": f"models/{model}",
                           "content": {"parts": [{"text": t}]}}
                          for t in texts]},
            {}, timeout=120)
        vectors = [e["values"] for e in data["embeddings"]]
    else:
        raise ProviderError(f"embeddings not wired for provider '{provider}'")

    if any(len(v) != EMBED_DIMS for v in vectors):
        # The column is vector(768) and Postgres will refuse a different width
        # anyway. Failing here names the provider that got it wrong.
        raise ProviderError(
            f"{provider}/{model} returned {len(vectors[0])} dimensions, "
            f"expected {EMBED_DIMS}")

    if trace is not None:
        trace.calls.append(ModelCall("embed", provider, model,
                                     int((time.time() - started) * 1000)))
    return vectors


# --------------------------------------------------------------------------
# Speech to text
# --------------------------------------------------------------------------

def transcribe(audio: bytes, filename: str = "debrief.webm",
               trace: Trace | None = None,
               language: str | None = "en") -> tuple[str, str]:
    """Groq Whisper. Returns (text, detected_language).

    Batch, not streaming: post-shift capture has no latency requirement and
    streaming would add a failure mode for nothing.

    language=None lets Whisper detect it. That matters more than it sounds:
    this used to pin language="en" unconditionally, so a room attendant giving
    their debrief in Spanish had it force-decoded as English and got back
    plausible nonsense, which then went on to be scored as if it were what they
    said. Pinning English is still right for a scenario known to be in English,
    like a practice transcript, so it stays the default and the caller opts in
    to detection.
    """
    provider, model = ROUTES["transcribe"]
    if provider != "groq":
        raise ProviderError(f"transcription not wired for '{provider}'")
    if not GROQ_KEY:
        raise ProviderError("GROQ_API_KEY is not set")

    boundary = "----coachingengine"
    parts: list[bytes] = []

    def field(name: str, value: str):
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
            f"{value}\r\n".encode())

    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
        .encode())
    parts.append(audio)
    parts.append(b"\r\n")
    field("model", model)
    # verbose_json so the detected language comes back with the text; plain
    # json omits it and there is no second call that would tell us.
    field("response_format", "verbose_json")
    if language:
        field("language", language)
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    started = time.time()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions", data=body,
        headers={"User-Agent": UA,
                 "Authorization": f"Bearer {GROQ_KEY}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ProviderError(
            f"HTTP {e.code} from groq: {e.read()[:300].decode('utf-8','replace')}") from None

    if trace is not None:
        trace.calls.append(ModelCall("transcribe", provider, model,
                                     int((time.time() - started) * 1000)))
    return (data.get("text", "").strip(),
            (data.get("language") or language or "en").lower())


# --------------------------------------------------------------------------
# Text to speech
# --------------------------------------------------------------------------

# The free tier is 10,000 characters for the lifetime of the account, not per
# month. Three careless demo rehearsals would spend it, so every line is cached
# on disk by (voice, text) and re-synthesised never. The cache is what makes
# this safe to leave switched on.
def _default_voice_cache() -> Path:
    """Repo .cache/voice when there is a repo, otherwise beside the app.

    The container has fewer directories above this file than the checkout does,
    so a fixed parent index raises IndexError on import. CE_VOICE_CACHE is set
    explicitly in every deployed environment anyway; this is the fallback.
    """
    parents = Path(__file__).resolve().parents
    if len(parents) > 3:
        return parents[3] / ".cache" / "voice"
    return parents[1] / ".voice-cache"


_VOICE_CACHE = Path(os.environ.get("CE_VOICE_CACHE", "") or _default_voice_cache())

# ElevenLabs' stock voices. Named here so a scenario can pick a guest that
# sounds like a different person, which matters more than fidelity: the point
# is that the staff member is talking to someone, not to a text box.
VOICES = {
    "guest_female": "EXAVITQu4vr4xnSDxMaL",   # Sarah, calm
    "guest_male":   "TX3LPaxmHKxFdv7VOQHJ",   # Liam, measured
    "guest_upset":  "pFZP5JQG7iQjIQuC4Bku",   # Lily, sharper
}

VOICE_CHAR_BUDGET = 400          # per line; a guest turn is one or two sentences

# Characters held back for the pitch itself.
#
# OpenAI is not the resource to ration: a whole agent run is half a cent. This
# one is. The free tier is 10,000 characters for the LIFE of the account, there
# is no way to buy more without a card, and a guest line is about 120
# characters. Rehearsing freely for two days would spend every line we have and
# the demo would fall back to text on the day, silently.
#
# So synthesis stops while a reserve remains. Cached lines still play, because
# a cache hit costs nothing, which is why the warmed demo lines are committed
# into the image.
VOICE_RESERVE_CHARS = int(os.environ.get("CE_VOICE_RESERVE", "1200"))
_voice_remaining: int | None = None      # refreshed lazily, not per call


def speak(text: str, voice: str = "guest_female", *,
          trace: Trace | None = None) -> bytes | None:
    """Synthesise one guest line. Returns mp3 bytes, or None if unavailable.

    None is a normal return, not an error. Voice is an enhancement on top of a
    conversation that already works as text, so a missing key, an exhausted
    quota or a slow network must degrade to silence rather than break the
    practice session someone is in the middle of.
    """
    text = (text or "").strip()
    if not text or not ELEVENLABS_KEY:
        return None
    if len(text) > VOICE_CHAR_BUDGET:
        # Truncating protects the budget from a runaway generation. A guest
        # turn this long is a bug upstream anyway.
        text = text[:VOICE_CHAR_BUDGET]

    voice_id = VOICES.get(voice, VOICES["guest_female"])
    digest = hashlib.sha256(f"{voice_id}:{text}".encode()).hexdigest()[:32]
    cached = _VOICE_CACHE / f"{digest}.mp3"
    if cached.exists():
        if trace is not None:
            trace.calls.append(ModelCall("speak", "cache", voice_id, 0))
        return cached.read_bytes()

    # Not cached, so this would spend. Check the reserve first.
    if not _voice_has_headroom(len(text)):
        if trace is not None:
            trace.step("code", "Voice budget reserve reached, continuing in text",
                       remaining=_voice_remaining, reserve=VOICE_RESERVE_CHARS,
                       note=("Cached lines still play. The reserve keeps enough "
                             "characters for the pitch itself."))
        return None

    started = time.time()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=json.dumps({
            "text": text,
            "model_id": "eleven_flash_v2_5",     # lowest latency tier
            "voice_settings": {"stability": 0.4, "similarity_boost": 0.7},
        }).encode(),
        headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json",
                 "Accept": "audio/mpeg", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            audio = r.read()
    except Exception as exc:                                  # noqa: BLE001
        # Deliberately swallowed. See the docstring: text still works.
        if trace is not None:
            trace.step("code", "Voice unavailable, continuing in text",
                       error=str(exc)[:160],
                       note="The practice session does not depend on audio.")
        return None

    try:
        _VOICE_CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(audio)
    except OSError:
        pass                                   # a cache miss is not a failure

    if trace is not None:
        trace.calls.append(ModelCall("speak", "elevenlabs", voice_id,
                                     int((time.time() - started) * 1000)))
    return audio


def _voice_has_headroom(chars: int) -> bool:
    """Is there room to synthesise, keeping the reserve intact?

    The remaining count is fetched once and then decremented locally. Asking
    the API before every line would double the request count for a number that
    only ever moves when we move it.
    """
    global _voice_remaining
    if _voice_remaining is None:
        info = voice_budget()
        if not info.get("reachable"):
            return False              # cannot tell, so do not spend
        _voice_remaining = int(info.get("remaining") or 0)
    if _voice_remaining - chars < VOICE_RESERVE_CHARS:
        return False
    _voice_remaining -= chars
    return True


def voice_key(text: str, voice: str = "guest_female") -> str:
    """The cache key for a line. Same computation as speak(), on purpose:
    the API hands this id to the browser and the browser asks for the mp3 by
    it, so no guest text ever travels in a URL."""
    voice_id = VOICES.get(voice, VOICES["guest_female"])
    trimmed = (text or "").strip()[:VOICE_CHAR_BUDGET]
    return hashlib.sha256(f"{voice_id}:{trimmed}".encode()).hexdigest()[:32]


def voice_file(digest: str) -> bytes | None:
    """Read a synthesised line back. None when it was never made."""
    if not digest.isalnum() or len(digest) != 32:
        return None                        # never build a path from free text
    path = _VOICE_CACHE / f"{digest}.mp3"
    return path.read_bytes() if path.exists() else None


def voice_budget() -> dict:
    """Characters left on the account. Checked before a demo, not during one."""
    if not ELEVENLABS_KEY:
        return {"configured": False}
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/user/subscription",
        headers={"xi-api-key": ELEVENLABS_KEY, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            sub = json.loads(r.read().decode())
    except Exception:                                         # noqa: BLE001
        return {"configured": True, "reachable": False}
    used, cap = sub.get("character_count", 0), sub.get("character_limit", 0)
    cached_lines = len(list(_VOICE_CACHE.glob("*.mp3"))) if _VOICE_CACHE.exists() else 0
    return {"configured": True, "reachable": True, "tier": sub.get("tier"),
            "used": used, "limit": cap, "remaining": cap - used,
            "cached_lines": cached_lines}


# --------------------------------------------------------------------------
# Manus: long-running agent tasks
# --------------------------------------------------------------------------

def manus_task(prompt: str, *, mode: str = "fast",
               trace: Trace | None = None) -> dict:
    """Hand a research or drafting job to Manus and return its handle.

    Manus authenticates with a bare API_KEY header rather than a bearer token,
    which is not guessable and cost us an afternoon. It is asynchronous by
    design, so this returns a task id and a URL rather than a result: the work
    it suits, a weekly operations write-up, is measured in minutes and nobody
    is waiting at a screen for it.
    """
    if not MANUS_KEY:
        raise ProviderError("MANUS_API_KEY is not set")
    started = time.time()
    data = _post("https://api.manus.ai/v1/tasks",
                 {"prompt": prompt, "mode": mode},
                 {"API_KEY": MANUS_KEY})
    if trace is not None:
        trace.calls.append(ModelCall("manus_task", "manus", mode,
                                     int((time.time() - started) * 1000)))
    return {"task_id": data.get("task_id") or data.get("id"),
            "task_url": data.get("task_url") or data.get("url"),
            "status": data.get("status", "submitted")}


def manus_brief(task_id: str) -> dict:
    """Fetch what Manus actually wrote, so the manager never leaves our page.

    manus_task() only hands back a handle. The work itself lands as an
    assistant message with a markdown file attached, and it is reachable on the
    v2 API, which is the reason this reaches for v2 while task creation still
    posts to v1:

        GET /v2/task.listMessages?task_id=...     header x-manus-api-key

    v1's GET returns the prompt echoed back and nothing else, which is why the
    first version of this feature could only offer a link out to manus.im.

    The attachment URL is signed and time limited, and Manus deletes session
    files after a couple of days. That is survivable because listing the
    messages again mints a fresh URL, so the brief is re-fetchable for as long
    as the task exists and nothing has to be stored on our side. The markdown
    itself is cached in process, because a manager watching this page polls it
    every few seconds and the document does not change once written.

    Returns status "running" while Manus is still working, "ready" with the
    markdown when it is done, and "empty" if it finished without attaching
    anything.
    """
    if not MANUS_KEY:
        raise ProviderError("MANUS_API_KEY is not set")

    cached = _BRIEF_CACHE.get(task_id)
    if cached is not None:
        return cached

    data = _get(f"https://api.manus.ai/v2/task.listMessages?task_id={task_id}"
                f"&order=asc&limit=100", {"x-manus-api-key": MANUS_KEY})

    summary, attachment = "", None
    for message in data.get("messages", []):
        assistant = message.get("assistant_message") or {}
        if assistant.get("content"):
            summary = assistant["content"]          # last one wins: the closing note
        for item in assistant.get("attachments") or []:
            if (item.get("content_type") or "").startswith("text/"):
                attachment = item

    if attachment is None:
        # Either still writing, or it answered without producing a document.
        running = any((m.get("status_update") or {}).get("agent_status") == "running"
                      for m in data.get("messages", []))
        return {"status": "running" if running or not summary else "empty",
                "summary": summary}

    markdown = _get_text(attachment["url"])
    result = {"status": "ready", "summary": summary, "markdown": markdown,
              "filename": attachment.get("filename", "operations-brief.md")}
    _BRIEF_CACHE[task_id] = result
    return result


def available() -> dict[str, bool]:
    """What is actually configured. Surfaced on /health so a missing key is
    visible before the demo rather than during it.

    Configured is not the same as working: a key can be present and the call
    still refused, which is exactly what happened with Google. Run
    services/api/check_providers.py for the stronger claim.
    """
    return {"openai": bool(OPENAI_KEY), "groq": bool(GROQ_KEY),
            "gemini": bool(GEMINI_KEY), "elevenlabs": bool(ELEVENLABS_KEY),
            "manus": bool(MANUS_KEY),
            "vertex": bool(VERTEX_PROJECT and (
                os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                or os.environ.get("GOOGLE_CREDENTIALS_JSON")))}

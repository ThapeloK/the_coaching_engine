"""
main.py
=======
The Coaching Engine API. Serves contracts/openapi.yaml over the real database.

Design notes worth knowing before changing anything:

* Identity comes from the X-CE-Actor header (a display name or staff id) and is
  resolved per request. That is demo-grade on purpose: real deployment reads a
  verified JWT, and swapping it means changing one function. What is NOT
  demo-grade is what happens next, because the resolved identity is pushed into
  the database session and every policy in db/policies.sql applies from there.

* There is no permission checking in this file. If a manager may not see a
  practice score, the database returns no row. Authorisation implemented twice
  is authorisation implemented wrong.

* The 409 on GET /staff/{id}/scores?source=practice is not a permission error.
  It is a sequencing rule, and the message says so, because the manager has
  done nothing wrong: they simply have to log their own observation first.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import (FastAPI, File, Form, Header, HTTPException, Request,
                     UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from . import demo
from . import queries as q
from . import spend as spend_mod
from . import tracing
from . import practice
from . import recommendations as recs
from . import permissions
from . import scenario_writer
from . import standards_audit
from . import voice_observation as voice_obs
from .agent import run_coaching
import psycopg

from .db import Actor, pool, resolve_actor, session
from .providers import (ProviderError, Trace, available, manus_brief,
                        manus_task,
                        voice_budget, voice_file)

DEFAULT_ACTOR = os.environ.get("CE_DEFAULT_ACTOR", "Marta")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    yield
    pool.close()


app = FastAPI(
    title="The Coaching Engine API",
    version="0.1.0",
    description="Two independent evidence streams per staff member, reasoned "
                "over to produce grounded, cited coaching a manager verifies.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Deployed, the browser is on Vercel and the API is somewhere else, so
    # every request is cross-origin. Hardcoding localhost meant the site would
    # load and then fail every single call with a CORS error that says nothing
    # useful in the console. Extra origins come from CE_ALLOWED_ORIGINS as a
    # comma-separated list; preview deployments get their own subdomain per
    # commit, hence the regex.
    allow_origins=[o for o in (
        ["http://localhost:3000", "http://127.0.0.1:3000"]
        + [x.strip() for x in os.environ.get("CE_ALLOWED_ORIGINS", "").split(",")]
    ) if o],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- errors

def problem(status: int, type_: str, title: str, detail: str, instance=None):
    """RFC 9457 problem+json, matching what the frontend already parses."""
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"type": f"https://coachingengine.app/errors/{type_}",
                 "title": title, "status": status, "detail": detail,
                 "instance": instance},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return problem(exc.status_code, exc.detail.get("type", "error"),
                       exc.detail.get("title", "Error"),
                       exc.detail.get("detail", ""), str(request.url.path))
    return problem(exc.status_code, "error", "Error", str(exc.detail),
                   str(request.url.path))


@app.exception_handler(psycopg.errors.InvalidTextRepresentation)
async def bad_id_handler(request: Request,
                         exc: psycopg.errors.InvalidTextRepresentation):
    """A path parameter that cannot be a uuid is a 404, not a 500.

    Every id column here is a uuid. A readable id from an older link, or a
    judge editing the address bar, reaches Postgres as text and it raises.
    Left alone that is a 500, which reads as a server fault and looks alarming
    on stage, when all that happened is somebody asked for a row that cannot
    exist. The message is deliberately vague about the column: it is the
    caller's id that is wrong, and naming internals helps nobody.
    """
    return problem(404, "not-found", "Not found",
                   "No such record. The id in that link is not a valid "
                   "identifier, so nothing can match it.",
                   str(request.url.path))


def actor_from(header: str | None) -> Actor:
    a = resolve_actor(header or DEFAULT_ACTOR)
    if a is None:
        raise HTTPException(401, {
            "type": "unknown-actor", "title": "Unknown actor",
            "detail": f"No staff member matches '{header or DEFAULT_ACTOR}'. "
                      f"Send X-CE-Actor with a display name, e.g. Marta or Diego."})
    return a


# ---------------------------------------------------------------- meta

@app.get("/health")
def health():
    try:
        with session() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
        # Report the search index, because an unembedded corpus is invisible
        # from the outside: every endpoint answers 200 and the agent abstains
        # on everyone with a reason that reads like good judgement.
        with session() as cur:
            cur.execute("SELECT count(*) FILTER (WHERE embedding IS NULL) AS missing,"
                        "       count(*) AS total FROM sop_chunk")
            idx = cur.fetchone()
        return {"status": "ok", "database": "up", "providers": available(),
                "search_index": {
                    "chunks": idx["total"],
                    "embedded": idx["total"] - idx["missing"],
                    "ready": idx["total"] > 0 and idx["missing"] == 0},
                "tracing": tracing.status(),
                "spend": spend_mod.summary()}
    except Exception as e:
        return JSONResponse(status_code=503,
                            content={"status": "degraded", "database": str(e)[:120]})


@app.get("/api/v1/staff")
def get_staff(x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        return {"staff": q.list_staff(cur), "viewer": {
            "id": actor.staff_id, "name": actor.display_name, "role": actor.role}}


# ---------------------------------------------------------------- scores

@app.get("/api/v1/staff/{staff_id}/scores")
def get_scores(staff_id: str, source: str = "floor",
               x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    if source not in ("practice", "floor"):
        raise HTTPException(422, {"type": "bad-source", "title": "Invalid source",
                                  "detail": "source must be practice or floor"})

    with session(actor) as cur:
        staff_id = q.resolve_staff_ref(cur, staff_id) or staff_id
        # The sequencing gate. Checked explicitly so we can return a 409 that
        # explains itself, rather than an empty list the UI would have to guess
        # the meaning of. RLS enforces it regardless; this is the good error.
        if (source == "practice" and actor.role == "manager"
                and not q.has_observed(cur, actor.staff_id, staff_id)):
            raise HTTPException(409, {
                "type": "observation-required",
                "title": "Observation required before practice scores are readable",
                "detail": "Log your own observation of this staff member before "
                          "viewing their practice history. This keeps the two "
                          "evidence streams independent, which is what makes the "
                          "transfer gap mean anything."})
        return q.scores_response(cur, staff_id, source)


@app.get("/api/v1/staff/{staff_id}/gap")
def get_gap(staff_id: str, x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        staff_id = q.resolve_staff_ref(cur, staff_id) or staff_id
        if not q.staff_by_id(cur, staff_id):
            raise HTTPException(404, {"type": "not-found", "title": "Not found",
                                      "detail": "No such staff member"})
        return q.transfer_gap(cur, staff_id)


# ---------------------------------------------------------------- observations

@app.get("/api/v1/observations")
def get_observations(x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        return q.list_observations(cur)


@app.post("/api/v1/observations", status_code=201)
def post_observation(payload: dict, x_ce_actor: str | None = Header(default=None),
                     idempotency_key: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required", "title": "Manager only",
                                  "detail": "Only a manager can log an observation."})
    for field in ("staff_id", "observed_at", "context", "what_happened"):
        if not payload.get(field):
            raise HTTPException(422, {"type": "missing-field", "title": "Missing field",
                                      "detail": f"'{field}' is required"})

    # Refuse a future observation at the door.
    #
    # The recency weighting in the transfer gap raises ValueError on a score
    # dated after today, which is correct: you cannot weight the age of
    # something that has not happened. But the observation is written and
    # committed BEFORE the agent runs, deliberately, because the manager's
    # judgement is theirs whether or not the coaching draft succeeds. Those two
    # correct decisions combine badly: one future-dated observation commits,
    # the agent then fails, and every later run for that staff member fails the
    # same way until somebody deletes the row by hand. The interface always
    # sends now, so this is unreachable through the product and trivial to hit
    # with a script, which is exactly the kind of thing that gets hit.
    try:
        when = datetime.fromisoformat(
            str(payload["observed_at"]).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, {"type": "bad-timestamp", "title": "Bad timestamp",
                                  "detail": "'observed_at' is not a valid "
                                            "ISO 8601 timestamp."}) from None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if when > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(422, {
            "type": "future-observation", "title": "Observation is in the future",
            "detail": "'observed_at' is in the future. An observation records "
                      "something that already happened."})

    with session(actor) as cur:
        payload["staff_id"] = (q.resolve_staff_ref(cur, payload["staff_id"])
                               or payload["staff_id"])
        obs_id = q.create_observation(cur, actor, payload)
        q.audit(cur, actor, "observation.logged", obs_id,
                {"staff_id": payload["staff_id"],
                 "dimensions": [r["dimension"] for r in payload.get("ratings", [])]})
        cur.connection.commit()

        # True from this moment: the manager's own judgement is recorded, so
        # the practice history is no longer capable of anchoring it.
        unlocked = q.has_observed(cur, actor.staff_id, payload["staff_id"])

    # The agent runs now, synchronously. It takes a few seconds and the manager
    # has just spent twenty of them writing the observation, so making them poll
    # would be worse than making them wait.
    with session(actor) as cur:
        result = run_coaching(cur, actor, payload["staff_id"], trace=Trace())
        rec_id = recs.persist(cur, actor, payload["staff_id"], result)

    return {
        "id": obs_id,
        "unlocked_practice_history": unlocked,
        "recommendation_id": rec_id,
        "recommendation_status": result["status"],
    }


# ----------------------------------------------------- observations by voice

# Roughly ninety seconds of talking. Long enough for a manager to cover a whole
# section of the floor in one go, short enough that a phone left unlocked in a
# pocket cannot record the rest of the shift and then fail the upload.
MAX_OBSERVATION_AUDIO_BYTES = 8 * 1024 * 1024


def _draft_guard(actor):
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required", "title": "Manager only",
                                  "detail": "Only a manager can log an observation."})


@app.post("/api/v1/observations/draft")
def post_observation_draft(payload: dict,
                           x_ce_actor: str | None = Header(default=None),
                           idempotency_key: str | None = Header(default=None)):
    """Typed notes in, reviewable drafts out. Writes nothing.

    This is the same extraction the voice route runs, reachable without a
    microphone. It exists for two reasons: it is the only way to test the
    extraction without recording audio, and it is the fallback on stage if the
    transcription stalls in front of judges, because the text can be pasted.
    """
    actor = actor_from(x_ce_actor)
    _draft_guard(actor)
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(422, {"type": "missing-field", "title": "Missing field",
                                  "detail": "'text' is required"})
    with session(actor) as cur:
        roster = q.list_staff(cur)
    return voice_obs.draft_from_text(text, roster, trace=Trace())


@app.post("/api/v1/observations/voice")
async def post_observation_voice(file: UploadFile = File(...),
                                 x_ce_actor: str | None = Header(default=None),
                                 idempotency_key: str | None = Header(default=None)):
    """Say what you saw. Get drafts back. Nothing is written until you confirm.

    The audio is transcribed and dropped in the same call. It is never written
    to disk, never stored in a column, and never returned. No speaker
    identification and no inference about how anything was said: the recording
    exists to become text and then it stops existing.
    """
    actor = actor_from(x_ce_actor)
    _draft_guard(actor)
    audio = await file.read()
    if not audio:
        raise HTTPException(422, {"type": "empty-upload", "title": "No audio",
                                  "detail": "The recording was empty."})
    if len(audio) > MAX_OBSERVATION_AUDIO_BYTES:
        raise HTTPException(413, {"type": "too-large", "title": "Recording too long",
                                  "detail": "Keep it under about ninety seconds."})

    with session(actor) as cur:
        roster = q.list_staff(cur)
    try:
        return voice_obs.draft_from_audio(
            audio, file.filename or "observation.webm", roster, trace=Trace())
    except ProviderError as exc:
        raise HTTPException(503, {"type": "transcription-unavailable",
                                  "title": "Could not transcribe",
                                  "detail": str(exc)[:200]}) from None


# ---------------------------------------------------------------- calibration

@app.get("/api/v1/calibration")
def get_calibration(x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        return q.calibration(cur)


# ---------------------------------------------------------------- recommendations

@app.get("/api/v1/recommendations")
def list_recommendations(status: str | None = None,
                         x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        return recs.listing(cur, status)


@app.get("/api/v1/recommendations/{rec_id}")
def get_recommendation(rec_id: str, x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        rec = recs.get(cur, rec_id)
        if not rec:
            raise HTTPException(404, {"type": "not-found", "title": "Not found",
                                      "detail": "No such recommendation"})
        rec["calibration"] = q.calibration(cur)
        return rec


@app.post("/api/v1/recommendations/{rec_id}/verify")
def verify_recommendation(rec_id: str, payload: dict,
                          x_ce_actor: str | None = Header(default=None),
                          idempotency_key: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required", "title": "Manager only",
                                  "detail": "Only a manager can verify."})
    verdict = payload.get("verdict")
    if verdict not in ("confirmed", "corrected", "rejected"):
        raise HTTPException(422, {"type": "bad-verdict", "title": "Invalid verdict",
                                  "detail": "verdict must be confirmed, corrected or rejected"})

    with session(actor) as cur:
        out = recs.verify(cur, actor, rec_id, verdict,
                          payload.get("dimension_verdicts", []),
                          payload.get("reason"),
                          payload.get("seconds_to_decide"))
    if out.get("error") == "not_found":
        raise HTTPException(404, {"type": "not-found", "title": "Not found",
                                  "detail": "No such recommendation"})
    if out.get("error") == "already_decided":
        raise HTTPException(409, {"type": "already-decided",
                                  "title": "Already decided",
                                  "detail": f"This was already {out['status']}."})
    return out


@app.post("/api/v1/staff/{staff_id}/coach")
def coach_now(staff_id: str, x_ce_actor: str | None = Header(default=None)):
    """Run the agent on demand. Used by the demo to re-generate without
    logging another observation."""
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        staff_id = q.resolve_staff_ref(cur, staff_id) or staff_id
        result = run_coaching(cur, actor, staff_id, trace=Trace())
        rec_id = recs.persist(cur, actor, staff_id, result)
    # After the work, never during it. A tracing outage must not cost a
    # manager their recommendation.
    tracing.export_run(staff_id=staff_id, result=result,
                       trace=result.get("trace"))
    return {"recommendation_id": rec_id, **result}


# ---------------------------------------------------------------- insights

@app.get("/api/v1/insights/team")
def team_insights(x_ce_actor: str | None = Header(default=None)):
    """k-anonymised cohort patterns.

    `suppressed` is deliberately visible. Telling a manager that two patterns
    were hidden because the group was too small demonstrates the control is
    working; silently omitting them would look like there was nothing there.
    """
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        return q.team_insights(cur)


# ---------------------------------------------------------------- media

MAX_DEBRIEF_BYTES = 25 * 1024 * 1024      # Whisper's own per-file ceiling


@app.get("/api/v1/voice/{digest}.mp3")
def get_voice(digest: str):
    """Serve one synthesised guest line by its content hash.

    Addressed by hash rather than by text so no guest dialogue travels in a
    URL, and so the browser can cache it forever: the same words in the same
    voice are always the same file.
    """
    audio = voice_file(digest)
    if audio is None:
        raise HTTPException(404, {"type": "not-found", "title": "No audio",
                                  "detail": "That line was never synthesised."})
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/v1/voice/budget")
def get_voice_budget():
    """Characters left on the speech account. Check this before a demo."""
    return voice_budget()


@app.post("/api/v1/debriefs/audio", status_code=202)
async def post_debrief_audio(file: UploadFile = File(...),
                             x_ce_actor: str | None = Header(default=None),
                             idempotency_key: str | None = Header(default=None)):
    """Speak a debrief instead of typing it.

    This is the whole point of the debrief for the people who will actually use
    it. A room attendant finishing a shift will not type three paragraphs into
    a phone, but they will say them. The recording is transcribed and then
    dropped: audio_deleted_at is stamped in the same transaction that stores
    the transcript, so the system never holds voice biometrics.
    """
    actor = actor_from(x_ce_actor)
    audio = await file.read()
    if not audio:
        raise HTTPException(422, {"type": "empty-upload", "title": "No audio",
                                  "detail": "The upload was empty."})
    if len(audio) > MAX_DEBRIEF_BYTES:
        raise HTTPException(413, {"type": "too-large", "title": "Recording too long",
                                  "detail": "Keep it under 25MB, roughly ten minutes."})

    try:
        with session(actor) as cur:
            out = practice.create_debrief(
                cur, actor, actor.staff_id, audio=audio,
                filename=file.filename or "debrief.webm", trace=Trace())
    except ProviderError as exc:
        raise HTTPException(503, {"type": "transcription-unavailable",
                                  "title": "Could not transcribe",
                                  "detail": str(exc)[:200]}) from None

    return {"id": out["id"], "status": out["status"], "poll_after_ms": 400,
            **({"heard": out["heard"]} if out.get("heard") else {})}


# ---------------------------------------------------------------- reports

@app.post("/api/v1/reports/weekly", status_code=202)
def post_weekly_report(x_ce_actor: str | None = Header(default=None)):
    """Hand the week's cohort patterns to Manus for a written brief.

    Only k-anonymised aggregates leave the building. The prompt is assembled
    from the same team_insights() the console renders, so nothing reaches an
    external agent that a manager could not already see on screen, and no
    individual is named. Asynchronous because it takes minutes and nobody is
    waiting at a screen for it.
    """
    actor = actor_from(x_ce_actor)
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required", "title": "Manager only",
                                  "detail": "Only a manager or L&D can commission this."})

    with session(actor) as cur:
        insights = q.team_insights(cur)
        calib = q.calibration(cur)

    if not insights["patterns"]:
        return {"status": "nothing_to_report",
                "detail": ("No pattern reached the k-anonymity threshold this "
                           "period. There is nothing to write up.")}

    lines = [f"- {p['description']} Classification: {p['classification']}. "
             f"Suggested: {p['suggested_action']}"
             for p in insights["patterns"]]
    measured = [c for c in calib if c["sample_size"]]

    prompt = (
        "You are writing a one page operations brief for a hotel general "
        "manager, covering "
        f"{insights['window']['start']} to {insights['window']['end']}.\n\n"
        "PATTERNS DETECTED ACROSS TEAMS (each covers at least "
        f"{insights['k_threshold']} staff; no individual is identified):\n"
        + "\n".join(lines)
        + "\n\nAGENT CALIBRATION: "
        + ("; ".join(f"{c['dimension']} {c['advice']}" for c in measured)
           if measured else "not yet measured this period.")
        + "\n\nWrite: what changed, what it costs to leave alone, and the "
          "single action worth taking this week. Name the role that owns each "
          "action. Do not recommend individual coaching for a pattern that "
          "spans a team, and do not invent numbers that are not above."
    )

    try:
        task = manus_task(prompt, mode="fast")
    except ProviderError as exc:
        raise HTTPException(503, {"type": "manus-unavailable",
                                  "title": "Report service unavailable",
                                  "detail": str(exc)[:200]}) from None

    with session(actor) as cur:
        q.audit(cur, actor, "report.commissioned", task.get("task_id"),
                {"patterns": len(insights["patterns"]),
                 "k_threshold": insights["k_threshold"]})
        cur.connection.commit()

    return {"status": "submitted", "patterns_included": len(insights["patterns"]),
            **task}


@app.get("/api/v1/reports/weekly/latest")
def get_latest_weekly_report(x_ce_actor: str | None = Header(default=None)):
    """The brief this property last commissioned, so it survives navigation.

    Without this the document lived only in one component's state: clicking
    Transfer gap and back lost it, and the only way to see it again was to
    commission another one, which is a fresh Manus task for a document that
    already exists.

    Returns {"status": "none"} when nothing has been commissioned yet, which is
    an answer rather than a 404, because "no brief yet" is the ordinary state of
    a new property and not an error worth a red line in anybody's console.
    """
    actor = actor_from(x_ce_actor)
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required", "title": "Manager only",
                                  "detail": "Only a manager or L&D can read this."})
    with session(actor) as cur:
        row = q.latest_weekly_report(cur)
    if not row:
        return {"status": "none"}

    payload = row.get("payload") or {}
    try:
        brief = manus_brief(row["task_id"])
    except ProviderError:
        # The id is real and the document is momentarily unreachable. Say so
        # rather than pretending nothing was ever written.
        return {"status": "unreachable", "task_id": row["task_id"],
                "commissioned_at": row["occurred_at"].isoformat()}

    brief["task_id"] = row["task_id"]
    brief["commissioned_at"] = row["occurred_at"].isoformat()
    brief["patterns_included"] = payload.get("patterns")
    return brief


@app.get("/api/v1/reports/weekly/{task_id}")
def get_weekly_report(task_id: str,
                      x_ce_actor: str | None = Header(default=None)):
    """What Manus wrote, returned as markdown so the console can render it.

    The point of this route is that a manager never has to leave the product to
    read a document the product commissioned. Sending them to a third party
    site mid-shift, to a page with somebody else's branding and a chat
    transcript on it, is a worse experience and a worse demo.

    Polled while the agent works, so "still writing" is a normal answer rather
    than an error.
    """
    actor = actor_from(x_ce_actor)
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required", "title": "Manager only",
                                  "detail": "Only a manager or L&D can read this."})
    try:
        return manus_brief(task_id)
    except ProviderError as exc:
        raise HTTPException(503, {"type": "manus-unavailable",
                                  "title": "Could not fetch the brief",
                                  "detail": str(exc)[:200]}) from None


# ---------------------------------------------------------------- glass box
#
# Three endpoints whose only job is to let someone check our claims instead of
# believing them. They call production code paths; see demo.py.

@app.post("/api/v1/demo/trace/{staff_id}")
def demo_trace(staff_id: str, x_ce_actor: str | None = Header(default=None)):
    """Run the agent and return the whole pipeline, step by step."""
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        staff_id = q.resolve_staff_ref(cur, staff_id) or staff_id
        return demo.trace_run(cur, actor, staff_id)


@app.get("/api/v1/demo/gate")
def demo_gate(staff_id: str = "Diego",
              x_ce_actor: str | None = Header(default=None)):
    """Put deliberately bad citations through the real cite gate."""
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        resolved = q.resolve_staff_ref(cur, staff_id) or staff_id
        return demo.gate_probe(cur, resolved)


@app.get("/api/v1/demo/rls")
def demo_rls(staff_id: str = "Aoife",
             x_ce_actor: str | None = Header(default=None)):
    """Ask one question as three different people."""
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        resolved = q.resolve_staff_ref(cur, staff_id) or staff_id
        return demo.rls_proof(cur, resolved)


# ---------------------------------------------------------------- practice

# ---------------------------------------------------------------- permissions

@app.post("/api/v1/permissions/ask")
def ask_permission(payload: dict,
                   x_ce_actor: str | None = Header(default=None),
                   idempotency_key: str | None = Header(default=None)):
    """Can I do this? Answered from the asker's own department's standards."""
    actor = actor_from(x_ce_actor)
    out = None
    with session(actor) as cur:
        out = permissions.ask(cur, actor, (payload or {}).get("question", ""),
                              trace=Trace())
    if out.get("error") == "empty":
        raise HTTPException(422, {"type": "empty-question",
                                  "title": "No question",
                                  "detail": "Ask something."})
    return out


@app.post("/api/v1/permissions/requests")
def create_permission_request(payload: dict,
                              x_ce_actor: str | None = Header(default=None)):
    """Send it to a manager. Anyone may ask; only a manager may answer."""
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        return permissions.request(cur, actor,
                                   (payload or {}).get("question", ""),
                                   (payload or {}).get("answer"))


@app.get("/api/v1/permissions/requests")
def list_permission_requests(x_ce_actor: str | None = Header(default=None)):
    """A manager sees the floor's questions. Everyone else sees only their own.

    The scoping is by role rather than by a parameter, so there is no id a
    client could send to read somebody else's questions.
    """
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        if actor.role in ("manager", "ld_admin"):
            return permissions.list_requests(cur)
        return permissions.list_requests(cur, staff_id=actor.staff_id)


@app.post("/api/v1/permissions/requests/{request_id}/answer")
def answer_permission_request(request_id: str, payload: dict,
                              x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required",
                                  "title": "Manager only",
                                  "detail": "Only a manager can settle what "
                                            "somebody is allowed to do."})
    with session(actor) as cur:
        out = permissions.answer(cur, actor, request_id,
                                 (payload or {}).get("verdict", ""),
                                 (payload or {}).get("note"))
    if out.get("error") == "bad_verdict":
        raise HTTPException(422, {"type": "bad-verdict", "title": "Bad verdict",
                                  "detail": "verdict must be yes, "
                                            "yes_with_approval or no."})
    return out


# ------------------------------------------------------- generated scenarios

def _manager_only(actor):
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required",
                                  "title": "Manager only",
                                  "detail": "Only a manager or L&D can work "
                                            "with proposed scenarios."})


@app.post("/api/v1/scenarios/propose")
def propose_scenario(payload: dict,
                     x_ce_actor: str | None = Header(default=None),
                     idempotency_key: str | None = Header(default=None)):
    """Write the next scenario for one person, from their measured gap.

    Proposes only. Nothing reaches the person's practice list until a manager
    publishes it, which is a different endpoint and a different decision.
    """
    actor = actor_from(x_ce_actor)
    _manager_only(actor)
    staff_ref = (payload or {}).get("staff_id")
    if not staff_ref:
        raise HTTPException(422, {"type": "missing-field", "title": "No staff",
                                  "detail": "staff_id is required."})
    with session(actor) as cur:
        staff_id = q.resolve_staff_ref(cur, staff_ref) or staff_ref
        out = scenario_writer.propose(cur, actor, staff_id, trace=Trace())
    if out.get("error") == "not_found":
        raise HTTPException(404, {"type": "not-found", "title": "No such staff",
                                  "detail": "No staff member with that id."})
    if out.get("error") == "insufficient_evidence":
        raise HTTPException(409, {"type": "insufficient-evidence",
                                  "title": "Not enough evidence",
                                  "detail": out.get("detail", "")})
    if out.get("error"):
        raise HTTPException(502, {"type": "writer-failed",
                                  "title": "Could not write a scenario",
                                  "detail": str(out.get("detail"))[:300]})
    return out


@app.get("/api/v1/scenarios/proposals")
def list_scenario_proposals(x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    _manager_only(actor)
    with session(actor) as cur:
        return scenario_writer.list_proposals(cur)


@app.post("/api/v1/scenarios/proposals/{proposal_id}/publish")
def publish_scenario_proposal(proposal_id: str,
                              x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    _manager_only(actor)
    with session(actor) as cur:
        out = scenario_writer.publish(cur, actor, proposal_id)
    if out.get("error") == "not_found":
        raise HTTPException(404, {"type": "not-found", "title": "Not found",
                                  "detail": "No such proposal."})
    return out


@app.post("/api/v1/scenarios/proposals/{proposal_id}/discard")
def discard_scenario_proposal(proposal_id: str, payload: dict | None = None,
                              x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    _manager_only(actor)
    with session(actor) as cur:
        out = scenario_writer.discard(cur, actor, proposal_id,
                                      (payload or {}).get("reason"))
    if out.get("error") == "not_found":
        raise HTTPException(404, {"type": "not-found", "title": "Not found",
                                  "detail": "No such proposal."})
    return out


# ---------------------------------------------------------------- standards

@app.get("/api/v1/standards/audit")
def get_standards_audit(x_ce_actor: str | None = Header(default=None)):
    """The last audit, or null if nobody has run one.

    Separate from the POST so a page load never spends money. Running the audit
    is a deliberate act by a named person, not a side effect of opening a tab.
    """
    actor = actor_from(x_ce_actor)
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required", "title": "Manager only",
                                  "detail": "Only a manager or L&D can read the "
                                            "standards audit."})
    with session(actor) as cur:
        return standards_audit.latest_audit(cur) or {"findings": [],
                                                     "clauses": 0,
                                                     "documents": 0}


@app.post("/api/v1/standards/audit")
def run_standards_audit(x_ce_actor: str | None = Header(default=None),
                        idempotency_key: str | None = Header(default=None)):
    """Audit the property's own standards. Six checks, one repair, then stop.

    Slow on purpose: five model calls over the whole corpus. It runs at
    onboarding and when a hotel revises a document, not on a schedule, so
    latency here costs nobody a shift.
    """
    actor = actor_from(x_ce_actor)
    if actor.role not in ("manager", "ld_admin"):
        raise HTTPException(403, {"type": "role-required", "title": "Manager only",
                                  "detail": "Only a manager or L&D can run the "
                                            "standards audit."})
    with session(actor) as cur:
        return standards_audit.run_audit(cur, actor, trace=Trace())


@app.get("/api/v1/scenarios")
def get_scenarios(x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        return practice.list_scenarios(cur, actor.staff_id)


@app.post("/api/v1/scenarios/{scenario_id}/attempts", status_code=201)
def start_attempt(scenario_id: str, x_ce_actor: str | None = Header(default=None),
                  idempotency_key: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        return practice.start_attempt(cur, actor, scenario_id, actor.staff_id)


@app.post("/api/v1/attempts/{attempt_id}/turns")
def add_turn(attempt_id: str, payload: dict,
             x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(422, {"type": "empty-turn", "title": "Empty turn",
                                  "detail": "content is required"})
    with session(actor) as cur:
        out = practice.add_turn(cur, actor, attempt_id, content, trace=Trace())
    if out.get("error") == "turn_limit":
        raise HTTPException(409, {
            "type": "turn-limit", "title": "Conversation is over",
            "detail": "This practice has used all of its turns. Finish it to "
                      "see the notes."})
    if out.get("error"):
        raise HTTPException(404, {"type": "not-found", "title": "Not found",
                                  "detail": "No such attempt"})
    return out


@app.post("/api/v1/attempts/{attempt_id}/complete")
def finish_attempt(attempt_id: str, x_ce_actor: str | None = Header(default=None),
                   idempotency_key: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        out = practice.complete_attempt(cur, actor, attempt_id, trace=Trace())
    if out.get("error"):
        raise HTTPException(404, {"type": "not-found", "title": "Not found",
                                  "detail": "No such attempt"})
    return out


@app.get("/api/v1/attempts")
def list_my_attempts(x_ce_actor: str | None = Header(default=None),
                     limit: int = 20):
    """The caller's own finished practice runs.

    Deliberately no staff_id in the path. Practice scores are the one thing in
    this product a staff member is promised stays theirs, so the only person
    who can list them is the person who did them, and the identity comes from
    the actor rather than from whatever id the browser felt like sending.

    Declared before /attempts/{attempt_id} so the bare path is not captured as
    an attempt id.
    """
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        return practice.list_attempts(cur, actor.staff_id, min(limit, 50))


@app.get("/api/v1/attempts/{attempt_id}")
def read_attempt(attempt_id: str, x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        a = practice.get_attempt(cur, attempt_id)
    if not a:
        raise HTTPException(404, {"type": "not-found", "title": "Not found",
                                  "detail": "No such attempt"})
    return a


# ---------------------------------------------------------------- debrief

@app.post("/api/v1/debriefs", status_code=202)
def post_debrief(payload: dict, x_ce_actor: str | None = Header(default=None),
                 idempotency_key: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        out = practice.create_debrief(cur, actor, actor.staff_id,
                                      text=payload.get("text"), trace=Trace())
    # 202 with a registration, not the finished object. The pipeline is
    # synchronous today, but the client polls by id either way, so the contract
    # already holds when transcription moves off the request thread.
    # "heard" rides back on this response rather than being stored. The client
    # polls the finished debrief by id from the database, and the database has
    # no column for the speaker's original sentence yet, so persisting it is a
    # migration and this is the night before a submission. The client holds it
    # for the session, which is enough to show somebody what was understood
    # from what they just said. Storing it is the next step, and it is the
    # difference between showing it once and showing it in their history.
    return {"id": out["id"], "status": out["status"], "poll_after_ms": 400,
            **({"heard": out["heard"]} if out.get("heard") else {})}


@app.get("/api/v1/debriefs/{debrief_id}")
def get_debrief(debrief_id: str, x_ce_actor: str | None = Header(default=None)):
    actor = actor_from(x_ce_actor)
    with session(actor) as cur:
        cur.execute("""
            SELECT d.id::text, d.status, d.transcript, d.incident,
                   d.standard_why,
                   c.id::text AS chunk_id, c.section_path, c.step_number,
                   c.content AS excerpt, doc.title AS document
            FROM shift_debrief d
            LEFT JOIN sop_chunk c ON c.id = d.standard_chunk_id
            LEFT JOIN sop_document doc ON doc.id = c.document_id
            WHERE d.id = %s
        """, (debrief_id,))
        d = cur.fetchone()
    if not d:
        raise HTTPException(404, {"type": "not-found", "title": "Not found",
                                  "detail": "No such debrief"})

    chunk_id = d.pop("chunk_id", None)
    standard = {
        "chunk_id": chunk_id,
        "document": d.get("document"),
        "section_path": d.get("section_path"),
        "step_number": d.get("step_number") or 0,
        "excerpt": (d.get("excerpt") or "")[:600],
        "why_shown": d.get("standard_why") or "",
    } if chunk_id else None
    for k in ("document", "section_path", "step_number", "excerpt",
              "standard_why"):
        d.pop(k, None)
    d["standard"] = standard
    d["generated_scenario_id"] = None
    return d

"""
practice.py
===========
Scenarios, live roleplay turns, scoring on completion, and the voice debrief.

The guest is played by a model with a persona and a mood that moves in response
to what the staff member actually says. It is not a script: if you acknowledge
the specific problem the guest softens, and if you lead with compensation they
push back, because that is the behaviour the rubric scores.

Scoring happens once, on completion, over the whole transcript. Not per turn.
BARS anchors describe an overall pattern rather than a single utterance, and
per-turn scoring would teach staff to optimise individual lines, which is
exactly the gaming behaviour we designed against.
"""

from __future__ import annotations

import json
import os

from .agent import score_transcript
from .providers import (ProviderError, Trace, complete, speak, transcribe,
                        voice_key)
from .dialect.understand import understand
from .retrieval import search

GUEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["content", "mood"],
    "properties": {
        "content": {"type": "string"},
        "mood": {"type": "string",
                 "enum": ["neutral", "frustrated", "escalating", "calming"]},
    },
}

INCIDENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["situation_type", "guest_emotion", "staff_actions", "outcome",
                 "dimensions_touched"],
    "properties": {
        "situation_type": {"type": "string", "enum": [
            "service_delay", "order_error", "service_delay_and_order_error",
            "room_not_ready", "billing_dispute", "noise_complaint",
            "booking_error", "special_request_failure", "other"]},
        "guest_emotion": {"type": "string", "enum": [
            "calm", "frustrated", "angry", "upset", "resigned"]},
        "staff_actions": {"type": "array", "items": {"type": "string"}},
        "outcome": {"type": "string", "enum": [
            "resolved", "partially_resolved", "unresolved", "escalated"]},
        "dimensions_touched": {"type": "array", "items": {"type": "string"}},
    },
}

# How many turns a staff member gets before the conversation closes.
#
# Eight is right for real practice and too long to show: a demo needs the guest
# to soften, the reply to land and the scoring to appear inside a minute. Four
# does that and still gives the guest room to react to what was actually said,
# which is the point of the scenario.
#
# Env-overridable because nobody pushes code on pitch day: a push restarts the
# API for about three minutes. Changing this is a dashboard edit instead.
MAX_TURNS = int(os.environ.get("CE_MAX_PRACTICE_TURNS", "4"))


# ---------------------------------------------------------------- scenarios

def list_scenarios(cur, staff_id: str) -> list[dict]:
    cur.execute("""
        SELECT sc.id::text, sc.title, sc.situation, sc.origin,
               sc.target_dimensions
        FROM scenario sc
        JOIN staff_member sm ON sm.id = %s
        WHERE sc.property_id = sm.property_id
        ORDER BY (sc.origin = 'debrief_derived') DESC,
                 (sc.origin = 'manager_assigned') DESC,
                 sc.created_at DESC, sc.title
        LIMIT 8
    """, (staff_id,))
    return [{
        "id": r["id"],
        "title": r["title"],
        "description": r["situation"],
        # A scenario built from this person's own shift is the point of the
        # product, so it is labelled differently and sorted first.
        "kind": ("personal" if r["origin"] == "debrief_derived"
                 else "assigned" if r["origin"] == "manager_assigned"
                 else "starter"),
        "source_debrief_id": None,
        "dimensions": r["target_dimensions"],
        "duration_minutes": 3,
    } for r in cur.fetchall()]


def start_attempt(cur, actor, scenario_id: str, staff_id: str) -> dict:
    cur.execute("SELECT id FROM bars_rubric WHERE is_active LIMIT 1")
    rubric = cur.fetchone()["id"]
    cur.execute("""
        INSERT INTO scenario_attempt (property_id, scenario_id, staff_id,
                                      status, rubric_id)
        VALUES (%s,%s,%s,'in_progress',%s) RETURNING id::text
    """, (actor.property_id, scenario_id, staff_id, rubric))
    attempt_id = cur.fetchone()["id"]

    cur.execute("SELECT title, situation, guest_persona FROM scenario WHERE id = %s",
                (scenario_id,))
    sc = cur.fetchone()

    opening = complete(
        "guest_turn",
        "You are a hotel guest with a legitimate complaint. Open the "
        "conversation in one or two sentences, the way a real person would: "
        "direct, a bit tired, not rude. Never a caricature.",
        f"SITUATION: {sc['situation']}", schema=GUEST_SCHEMA, temperature=0.8)

    cur.execute("""
        INSERT INTO attempt_turn (property_id, attempt_id, turn_index, speaker, content)
        VALUES (%s,%s,0,'guest',%s)
    """, (actor.property_id, attempt_id, opening["content"]))
    cur.execute("UPDATE scenario_attempt SET turn_count = 1 WHERE id = %s", (attempt_id,))
    cur.connection.commit()

    # The frozen contract returns a whole PracticeAttempt, with the opening
    # guest line already sitting in turns. The chat component renders straight
    # from attempt.turns, so anything else leaves the screen blank on load.
    return {
        "id": attempt_id,
        "scenario_id": scenario_id,
        "status": "in_progress",
        "turns": [{"turn_index": 0, "guest": _voiced(opening, sc),
                   "turns_remaining": MAX_TURNS, "can_complete": False}],
        "result": None,
    }


def _voiced(guest: dict, scenario) -> dict:
    """Attach an audio id to a guest turn, if we can make one.

    A staff member practising a complaint should hear a person, not read one.
    Tone is most of what makes service recovery hard, and a transcript hides
    exactly the thing being trained. It is strictly additive: when synthesis is
    unavailable the key is absent and the interface stays as it was.
    """
    text = guest.get("content", "")
    # An escalating guest gets a sharper voice. Same words, different problem.
    voice = "guest_upset" if guest.get("mood") in ("frustrated", "escalating") \
        else "guest_female"
    try:
        if speak(text, voice) is not None:
            guest["audio_id"] = voice_key(text, voice)
    except Exception:
        pass                    # voice is a bonus; never fail a turn over it
    return guest


def add_turn(cur, actor, attempt_id: str, content: str,
             trace: Trace | None = None) -> dict:
    cur.execute("""
        SELECT sa.id, sa.turn_count, sc.situation, sc.title
        FROM scenario_attempt sa JOIN scenario sc ON sc.id = sa.scenario_id
        WHERE sa.id = %s
    """, (attempt_id,))
    a = cur.fetchone()
    if not a:
        return {"error": "not_found"}

    # The ceiling has to hold here, not only in the interface. The counter the
    # client renders is a display of this, not the rule itself, and checking
    # before the model call also means a refused turn costs nothing.
    cur.execute("""
        SELECT count(*) AS n FROM attempt_turn
        WHERE attempt_id = %s AND speaker = 'staff'
    """, (attempt_id,))
    if cur.fetchone()["n"] >= MAX_TURNS:
        return {"error": "turn_limit"}

    idx = a["turn_count"]
    cur.execute("""
        INSERT INTO attempt_turn (property_id, attempt_id, turn_index, speaker, content)
        VALUES (%s,%s,%s,'staff',%s)
    """, (actor.property_id, attempt_id, idx, content))

    cur.execute("""
        SELECT speaker, content FROM attempt_turn
        WHERE attempt_id = %s ORDER BY turn_index
    """, (attempt_id,))
    history = cur.fetchall()

    convo = "\n".join(f"{t['speaker'].upper()}: {t['content']}" for t in history)
    guest = complete(
        "guest_turn",
        "You are the hotel guest in this conversation. Reply in one or two "
        "sentences.\n\n"
        "React to what the staff member ACTUALLY said:\n"
        "- If they acknowledged your specific problem before offering "
        "anything, soften. mood 'calming'.\n"
        "- If they led with compensation without acknowledging, push back. "
        "mood 'escalating'.\n"
        "- If they deflected or offered to fetch a manager without trying, "
        "get shorter and more clipped.\n"
        "Never break character. Never coach them.",
        f"SITUATION: {a['situation']}\n\nCONVERSATION SO FAR\n{convo}",
        schema=GUEST_SCHEMA, temperature=0.7, trace=trace)

    cur.execute("""
        INSERT INTO attempt_turn (property_id, attempt_id, turn_index, speaker, content)
        VALUES (%s,%s,%s,'guest',%s)
    """, (actor.property_id, attempt_id, idx + 1, guest["content"]))
    cur.execute("UPDATE scenario_attempt SET turn_count = %s WHERE id = %s",
                (idx + 2, attempt_id))
    cur.connection.commit()

    # history is read after the insert above, so it already includes this turn.
    # The + 1 that used to be here counted it twice, which is why the counter
    # fell from 4 to 2 on the very first reply.
    staff_turns = sum(1 for t in history if t["speaker"] == "staff")
    return {"turn_index": idx + 1, "guest": _voiced(guest, a),
            "turns_remaining": max(0, MAX_TURNS - staff_turns),
            "can_complete": staff_turns >= 2}


def complete_attempt(cur, actor, attempt_id: str,
                     trace: Trace | None = None) -> dict:
    cur.execute("""
        SELECT sa.scenario_id::text, sa.staff_id::text, sa.rubric_id,
               sc.target_dimensions
        FROM scenario_attempt sa JOIN scenario sc ON sc.id = sa.scenario_id
        WHERE sa.id = %s
    """, (attempt_id,))
    a = cur.fetchone()
    if not a:
        return {"error": "not_found"}

    cur.execute("""
        SELECT speaker, content FROM attempt_turn
        WHERE attempt_id = %s ORDER BY turn_index
    """, (attempt_id,))
    turns = cur.fetchall()

    scored = score_transcript(cur, turns, a["target_dimensions"], trace=trace)

    cur.execute("SELECT id, code FROM bars_dimension WHERE rubric_id = %s",
                (a["rubric_id"],))
    dims = {r["code"]: r["id"] for r in cur.fetchall()}

    evidence = []
    for s in scored:
        if s["dimension"] not in dims:
            continue
        cur.execute("""
            INSERT INTO score (property_id, staff_id, dimension_id, rubric_id,
                source, level, attempt_id, evidence_span, model_id, prompt_version)
            VALUES (%s,%s,%s,%s,'practice',%s,%s,%s,'gpt-4o-mini','score.v1')
        """, (actor.property_id, a["staff_id"], dims[s["dimension"]],
              a["rubric_id"], s["level"], attempt_id, s["evidence_span"][:400]))
        evidence.append({"dimension": s["dimension"], "quote": s["evidence_span"],
                         "turn_index": 0, "explains": s.get("anchor_matched", "")})

    cur.execute("""
        UPDATE scenario_attempt SET status='scored', completed_at=now() WHERE id=%s
    """, (attempt_id,))
    cur.connection.commit()

    return {
        "attempt_id": attempt_id, "scenario_id": a["scenario_id"],
        "completed_at": __import__("datetime").datetime.now().isoformat(),
        "scores": [{"dimension": s["dimension"], "level": s["level"]}
                   for s in scored],
        "evidence": evidence,
        "overall_feedback": _feedback(scored),
    }


def _feedback(scored: list[dict]) -> str:
    """Level words, never numbers. Frontline staff read a 2 out of 5 as a
    verdict on them; 'finding this hard' is the same information without the
    sting, and it is what the staff PWA already displays."""
    if not scored:
        return "Not enough in this attempt to score. Try a longer exchange."
    worst = min(scored, key=lambda s: s["level"])
    words = {1: "finding this hard", 2: "still building this",
             3: "getting there", 4: "solid here", 5: "leading here"}
    return (f"You are {words[worst['level']]} on "
            f"{worst['dimension'].replace('_', ' ')}.")


def list_attempts(cur, staff_id: str, limit: int = 20) -> list[dict]:
    """Somebody's finished practice runs, newest first.

    This existed in the database the whole time and nothing read it back. The
    staff app's My practice screen rendered three hardcoded seed rows, so a
    person could finish a scenario, watch their notes appear, go to My
    practice, and not find it. The run was saved; the page just was not asking.

    Only 'scored' rows: an abandoned attempt is not a practice someone did, and
    listing half-finished sessions would make the screen a list of things you
    gave up on.
    """
    cur.execute("""
        SELECT sa.id::text        AS id,
               sa.scenario_id::text AS scenario_id,
               sc.title           AS title,
               sa.completed_at
        FROM scenario_attempt sa
        JOIN scenario sc ON sc.id = sa.scenario_id
        WHERE sa.staff_id = %s AND sa.status = 'scored'
        ORDER BY sa.completed_at DESC NULLS LAST
        LIMIT %s
    """, (staff_id, limit))
    attempts = cur.fetchall()
    if not attempts:
        return []

    # One query for every score rather than one per attempt: this screen is the
    # first thing a staff member opens and it should not cost twenty round
    # trips to draw a list.
    cur.execute("""
        SELECT s.attempt_id::text AS attempt_id,
               bd.code            AS dimension,
               s.level
        FROM score s
        JOIN bars_dimension bd ON bd.id = s.dimension_id
        WHERE s.attempt_id = ANY(%s::uuid[])
    """, ([a["id"] for a in attempts],))
    by_attempt: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        by_attempt.setdefault(r["attempt_id"], []).append(
            {"dimension": r["dimension"], "level": r["level"]})

    return [{
        "id": a["id"],
        "scenario_id": a["scenario_id"],
        "title": a["title"],
        "completed_at": (a["completed_at"].isoformat()
                         if a["completed_at"] else ""),
        "scores": by_attempt.get(a["id"], []),
    } for a in attempts]


def get_attempt(cur, attempt_id: str) -> dict | None:
    cur.execute("""
        SELECT sa.id::text, sa.scenario_id::text, sa.status, sa.completed_at
        FROM scenario_attempt sa WHERE sa.id = %s
    """, (attempt_id,))
    a = cur.fetchone()
    if not a:
        return None

    # 'scored' is a database state, not a UI state. The frontend only
    # distinguishes in_progress from completed, so collapse it here rather than
    # widening the contract with a status the screens would have to ignore.
    a["status"] = "in_progress" if a["status"] == "in_progress" else "completed"

    cur.execute("""
        SELECT turn_index, speaker, content FROM attempt_turn
        WHERE attempt_id = %s ORDER BY turn_index
    """, (attempt_id,))
    rows = cur.fetchall()

    # Rows are stored one speaker per row, which is what a transcript is. The
    # UI wants one entry per guest reply, so fold them back into exchanges.
    guest_rows = [r for r in rows if r["speaker"] == "guest"]
    staff_seen = 0
    turns = []
    for r in rows:
        if r["speaker"] == "staff":
            staff_seen += 1
            continue
        turns.append({
            "turn_index": r["turn_index"],
            "guest": {"content": r["content"], "mood": "neutral"},
            "turns_remaining": max(0, MAX_TURNS - staff_seen),
            "can_complete": staff_seen >= 2,
        })
    a["turns"] = turns or [{"turn_index": 0,
                            "guest": {"content": "", "mood": "neutral"},
                            "turns_remaining": MAX_TURNS,
                            "can_complete": False}]
    _ = guest_rows
    cur.execute("""
        SELECT bd.code AS dimension, s.level, s.evidence_span
        FROM score s JOIN bars_dimension bd ON bd.id = s.dimension_id
        WHERE s.attempt_id = %s
    """, (attempt_id,))
    rows = cur.fetchall()
    a["result"] = {
        "attempt_id": a["id"],
        "scenario_id": a["scenario_id"],
        "completed_at": (a["completed_at"].isoformat()
                         if a["completed_at"] else ""),
        "scores": [{"dimension": r["dimension"], "level": r["level"]} for r in rows],
        "evidence": [{"dimension": r["dimension"], "quote": r["evidence_span"],
                      "turn_index": 0, "explains": ""} for r in rows],
        "overall_feedback": _feedback(
            [{"dimension": r["dimension"], "level": r["level"]} for r in rows]),
    } if rows else None
    a["completed_at"] = a["completed_at"].isoformat() if a["completed_at"] else None
    return a


# ---------------------------------------------------------------- debrief

def create_debrief(cur, actor, staff_id: str, text: str | None = None,
                   audio: bytes | None = None, filename: str = "debrief.webm",
                   trace: Trace | None = None) -> dict:
    """Voice or text in, structured incident and the hotel's own clause out.

    Audio is transcribed and then dropped. It is never stored: once the
    transcript exists the recording has no further purpose, and not holding it
    removes voice biometrics from the system entirely.
    """
    transcript = text or ""
    spoken_language = "en"
    if audio:
        # The filename carries the container format, and Whisper uses it to
        # pick a decoder. A browser MediaRecorder gives us webm on Chrome and
        # mp4 on Safari; passing the wrong extension fails on one of them.
        #
        # language=None so Whisper detects rather than assumes. This used to
        # pin English, which meant a staff member debriefing in their own
        # language got back nonsense and was then scored on it.
        transcript, spoken_language = transcribe(
            audio, filename=filename, trace=trace, language=None)

    # Understood, not just transcribed. A Spanish debrief is translated with
    # the speaker's regional vocabulary retrieved into the prompt, because
    # everything downstream treats this text as evidence: it is scored against
    # the rubric and it becomes half of a transfer gap. Mistranslating it means
    # assessing somebody on a sentence they did not say, and it would only ever
    # happen to the people not working in their first language.
    reading = understand(transcript, spoken_language, trace=trace)
    transcript = reading["english"]

    if len(transcript.split()) < 5:
        # Still a row. The client polls by id, so a failure with no id is a
        # failure the staff member never sees an explanation for.
        cur.execute("""
            INSERT INTO shift_debrief (property_id, staff_id, status, transcript)
            VALUES (%s,%s,'failed',%s) RETURNING id::text
        """, (actor.property_id, staff_id, transcript))
        failed_id = cur.fetchone()["id"]
        cur.connection.commit()
        return {"id": failed_id, "status": "failed",
                "detail": "That was too short to work with. Try again."}

    incident = complete(
        "extract_incident",
        "Extract a structured incident from a staff member's spoken shift "
        "debrief. Report only what they said. Do not infer an outcome they did "
        "not describe.",
        transcript, schema=INCIDENT_SCHEMA, trace=trace)

    # The hotel's own words for this situation, resolved once and recorded.
    # This is the difference between coaching and advice: the staff member is
    # shown the clause their employer actually wrote, with its section path, so
    # they can go and read the rest of it.
    chunk_id, why = None, None
    try:
        cur.execute("SELECT department FROM staff_member WHERE id = %s", (staff_id,))
        row = cur.fetchone()
        hits = search(cur, transcript[:600],
                      department=row["department"] if row else None,
                      limit=1, trace=trace)
        if hits:
            chunk_id = hits[0]["id"]
            why = (f"You described a "
                   f"{incident['situation_type'].replace('_', ' ')}. "
                   f"This is what your property's standard says about it.")
    except Exception:
        # Retrieval is an enhancement here, not the point of the endpoint. A
        # debrief that extracted cleanly must not fail because search did.
        chunk_id, why = None, None

    cur.execute("""
        INSERT INTO shift_debrief (property_id, staff_id, status, transcript,
                                   incident, audio_deleted_at,
                                   standard_chunk_id, standard_why)
        VALUES (%s,%s,'extracted',%s,%s, CASE WHEN %s THEN now() ELSE NULL END,
                %s,%s)
        RETURNING id::text
    """, (actor.property_id, staff_id, transcript, json.dumps(incident),
          bool(audio), chunk_id, why))
    debrief_id = cur.fetchone()["id"]
    cur.connection.commit()

    # "heard" travels back only when the debrief was not given in English. The
    # staff member gets to see their own sentence beside the English the system
    # worked from, and which regional terms it looked up. This product refuses
    # to let a manager act on evidence they cannot inspect; holding the staff
    # member to a lower standard about their own words would be strange.
    response = {"id": debrief_id, "status": "extracted", "transcript": transcript,
                "incident": incident}
    if reading["translated"]:
        response["heard"] = {
            "original": reading["original"],
            "language": reading["language"],
            "country": reading["country"],
            "terms": reading["terms"],
        }
    return response

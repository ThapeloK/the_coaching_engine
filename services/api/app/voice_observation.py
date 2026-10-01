"""Speak the shift, get drafts back. The manager still decides.

WHY THIS EXISTS

The mentor session put it plainly: "Voice notes and voice control were
identified as especially valuable for recording observations during a busy
workday", and "Convenience on the hospitality floor is another differentiator
because employees are unlikely to return to a workstation to enter detailed
information."

The tap-through capture takes about twenty seconds per person. That is fast for
a form and slow for a duty manager with forty staff, because the real cost is
not the twenty seconds, it is stopping at all. Nobody stops. So the observation
never gets logged, and the floor half of the transfer gap stays empty, and the
whole product has nothing to compare practice against.

Talking does not require stopping. A manager walking back from the restaurant
can say four observations into a phone in thirty seconds, and this turns that
into four drafts.

WHAT THIS DOES NOT DO, DELIBERATELY

The same meeting floated "tone analysis". We are not building it and we should
not be talked into it. Inferring emotion from a worker's voice in a workplace
is prohibited outright by EU AI Act Article 5(1)(f), not merely high risk, and
it is the same line we already refused to cross under Annex III 4(c) when we
declined live guest monitoring. Our entire governance story in the Q&A rests on
having refused things. Refusing this one costs nothing: the manager's judgement
is the signal, and they can just say what they saw.

So the audio is used for exactly one thing, transcription, and is then dropped.
No voiceprint, no speaker identification, no affect, no stress score. Same
promise the staff debrief already makes.

THE RULE THAT MAKES THIS TRUSTWORTHY

A draft is not an observation. Nothing here writes to the database. The
extraction proposes, the manager confirms, and only the confirmed version goes
through the ordinary POST /observations path with every existing rule intact.

And a rating survives only if the manager actually said something that supports
it. Every proposed rating must quote a span that appears verbatim in the
transcript; a rating whose quote is not in the transcript is dropped, not
shown. This is the cite gate turned around to face the input: the same
principle that stops the coach inventing evidence stops the extractor inventing
a score. If the manager never mentioned empathy, empathy comes back unrated,
which is exactly what create_observation already does with a null level.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .providers import Trace, complete, transcribe

# The five BARS dimensions the capture surface offers. Kept in step with
# CAPTURE_DIMENSIONS in the web observation form: a dimension the extractor
# invents that the form cannot render is a dimension the manager cannot correct.
DIMENSIONS = [
    "service_recovery",
    "empathy",
    "communication",
    "composure",
    "anticipation",
]

# Matches MOMENT_TYPES in the web form, same reason.
MOMENTS = ["guest_question", "complaint", "proactive", "routine"]

DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["observations"],
    "properties": {
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["staff_name", "moment", "scope", "what_happened",
                             "ratings"],
                "properties": {
                    "staff_name": {
                        "type": "string",
                        "description": "The staff member's name exactly as the "
                                       "manager said it. Do not correct it.",
                    },
                    "moment": {"type": "string", "enum": MOMENTS},
                    "scope": {
                        "type": "string",
                        "enum": ["full", "partial"],
                        "description": "full if the manager saw the whole "
                                       "interaction, partial if they only "
                                       "caught part of it or heard about it.",
                    },
                    "what_happened": {
                        "type": "string",
                        "description": "One short sentence, in the manager's "
                                       "own words, describing what they saw. "
                                       "No interpretation.",
                    },
                    "ratings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["dimension", "level", "quote"],
                            "properties": {
                                "dimension": {"type": "string",
                                              "enum": DIMENSIONS},
                                "level": {"type": "integer", "minimum": 1,
                                          "maximum": 5},
                                "quote": {
                                    "type": "string",
                                    "description": "The exact words from the "
                                                   "transcript that support "
                                                   "this rating. Copy them "
                                                   "character for character.",
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}

SYSTEM = """You turn a hotel manager's spoken notes into draft floor observations.

A manager has just walked off the floor and said what they saw. They may talk
about one person or several. Split the note into one draft per person.

Rate a dimension ONLY when the manager described behaviour that supports it,
and quote their exact words. Copy the quote character for character from the
transcript. Never paraphrase a quote, never tidy their grammar, never quote
words they did not say.

If the manager said nothing about a dimension, leave it out. An unrated
dimension is a correct answer and a guessed one is not: the manager's silence
about empathy means they did not see it, not that it was average.

The five dimensions:
  service_recovery  putting a problem right for the guest
  empathy           reading and acknowledging how the guest feels
  communication     clarity, tone, keeping the guest informed
  composure         staying steady under pressure
  anticipation      seeing the need before the guest asks

Levels run 1 to 5. 1 is well below the standard, 3 meets it, 5 is well above.
Read the manager's words plainly: "stayed calm" is composure around 4, "froze"
is composure around 2, "excellent, took ownership immediately" is service
recovery around 5.

Do not infer emotion, stress or personality from how anything was said. You are
reading what the manager reported, nothing more."""


def _normalise(text: str) -> str:
    """Fold the differences that do not change what was said.

    Whisper punctuates and capitalises on its own judgement, and a model asked
    to quote will often return "he stayed calm" for a transcript that reads
    "He stayed calm,". Comparing those as unequal would throw away a true
    rating on a technicality, so case, punctuation and runs of whitespace all
    fold away. Word order and word choice do not, which is the part that
    matters: a paraphrase still fails.
    """
    text = unicodedata.normalize("NFKD", text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> list[tuple[str, int, int]]:
    """Words with their offsets in the original string."""
    return [(m.group(0).lower(), m.start(), m.end())
            for m in re.finditer(r"\w+", unicodedata.normalize("NFKD", text))]


def _find_span(transcript: str, quote: str) -> tuple[int, int] | None:
    """Locate the quote in the transcript, or report that it is not there.

    Returns character offsets into the ORIGINAL text so the web client can
    highlight the manager's real words rather than the model's copy of them.

    Two passes, the same shape as the cite gate in the agent: exact first, then
    one tolerant fallback, because an exact-only check is too brittle to be
    fair and a similarity score alone is too loose to be a guarantee.

    The fallback allows elision and nothing else. Every word of the quote must
    be a word the manager said, in the order they said it, inside a window
    barely longer than the quote itself. That passes the model's habit of
    lightly compressing as it quotes ("excellent, took ownership" for
    "excellent, she took ownership") and still fails everything this check
    exists to catch: a paraphrase introduces a word that is not there
    ("remained composed" for "stayed calm"), and an invention introduces
    several. The highlighted span is the covering range in the original, so
    what the manager reads back is their own sentence, elision included.
    """
    quote_tokens = _tokens(quote)
    source_tokens = _tokens(transcript)
    if not quote_tokens or not source_tokens:
        return None

    words = [t[0] for t in quote_tokens]
    source_words = [t[0] for t in source_tokens]

    # Pass one: a contiguous run of the same words.
    for start in range(len(source_words) - len(words) + 1):
        if source_words[start:start + len(words)] == words:
            return source_tokens[start][1], source_tokens[start + len(words) - 1][2]

    # Pass two: the same words in order, with small gaps allowed between them.
    #
    # The window may exceed the quote by half its length or three words,
    # whichever is larger. Three covers the short quote losing an article or a
    # pronoun; the proportional term covers a longer quote dropping a couple of
    # connectives. Beyond that the words are no longer one phrase the manager
    # said, they are words collected from across the note, which is exactly the
    # fabrication this is here to refuse.
    allowance = max(3, len(words) // 2)
    limit = len(words) + allowance
    for start in range(len(source_words)):
        if source_words[start] != words[0]:
            continue
        at = start
        matched = 0
        for word in words:
            while at < len(source_words) and source_words[at] != word:
                at += 1
            if at >= len(source_words):
                break
            matched += 1
            at += 1
        if matched == len(words) and (at - start) <= limit:
            return source_tokens[start][1], source_tokens[at - 1][2]

    return None


def _first_name(name: str) -> str:
    return name.strip().split()[0].lower() if name.strip() else ""


def resolve_name(spoken: str, roster: list[dict]) -> dict:
    """Match a spoken name to somebody on the roster, or say why not.

    Never guesses between two people. A manager with a Maria Santos and a Maria
    Oliveira who says "Maria" gets asked which one, because logging a floor
    observation against the wrong person is not a small error: it lands in that
    person's record, moves their transfer gap, and can send them training they
    did not need.
    """
    spoken = (spoken or "").strip()
    if not spoken:
        return {"status": "unmatched", "spoken": spoken, "candidates": []}

    target = spoken.lower()
    exact = [s for s in roster if s["name"].lower() == target]
    if len(exact) == 1:
        return {"status": "matched", "spoken": spoken,
                "staff_id": exact[0]["id"], "name": exact[0]["name"]}

    partial = [s for s in roster if _first_name(s["name"]) == _first_name(spoken)]
    if not partial:
        # "Diego from the restaurant" and similar: try the leading word alone.
        partial = [s for s in roster
                   if _first_name(s["name"]) == target.split()[0]]
    if len(partial) == 1:
        return {"status": "matched", "spoken": spoken,
                "staff_id": partial[0]["id"], "name": partial[0]["name"]}
    if len(partial) > 1:
        return {"status": "ambiguous", "spoken": spoken,
                "candidates": [{"staff_id": s["id"], "name": s["name"],
                                "department": s.get("department")}
                               for s in partial]}
    return {"status": "unmatched", "spoken": spoken, "candidates": []}


def draft_from_text(transcript: str, roster: list[dict],
                    trace: Trace | None = None) -> dict:
    """Transcript in, reviewable drafts out. Writes nothing.

    Returns the transcript alongside the drafts because the web client shows it
    with each quote highlighted. A manager who can see which of their own words
    produced a 2 can correct the rating in one tap; a manager shown a bare
    number has to take it on faith, and taking AI output on faith is the thing
    this whole product exists to stop.
    """
    words = transcript.split()
    if len(words) < 5:
        return {"transcript": transcript, "drafts": [], "dropped_ratings": 0,
                "detail": "That was too short to work with. Try again."}

    result = complete("extract_incident", SYSTEM, transcript,
                      schema=DRAFT_SCHEMA, trace=trace)

    drafts: list[dict] = []
    dropped = 0
    for item in result.get("observations", []):
        ratings = []
        for rating in item.get("ratings", []):
            span = _find_span(transcript, rating.get("quote", ""))
            if span is None:
                # The model produced a score it cannot point at. Drop it in
                # silence rather than show the manager a number with a
                # fabricated justification underneath it.
                dropped += 1
                continue
            level = rating.get("level")
            if not isinstance(level, int) or not 1 <= level <= 5:
                dropped += 1
                continue
            ratings.append({
                "dimension": rating["dimension"],
                "level": level,
                "quote": transcript[span[0]:span[1]],
                "span": [span[0], span[1]],
            })

        # Deduplicate: two quotes for one dimension is the model hedging. Keep
        # the first, which is the one it was most confident enough to lead with.
        seen: set[str] = set()
        unique = []
        for rating in ratings:
            if rating["dimension"] in seen:
                dropped += 1
                continue
            seen.add(rating["dimension"])
            unique.append(rating)

        # A draft with nothing rated still goes back, flagged.
        #
        # Dropping it would be the quiet failure: the manager said a name, the
        # extractor could not tie any of their words to a dimension, and the
        # person simply would not appear. The manager would have to notice an
        # absence, which nobody does. Handing it back empty says what actually
        # happened and leaves them one tap from rating it themselves.
        drafts.append({
            "person": resolve_name(item.get("staff_name", ""), roster),
            "moment": item.get("moment") if item.get("moment") in MOMENTS
                      else "routine",
            "scope": "partial" if item.get("scope") == "partial" else "full",
            "what_happened": (item.get("what_happened") or "").strip(),
            "ratings": unique,
            "needs_rating": not unique,
        })

    return {"transcript": transcript, "drafts": drafts,
            "dropped_ratings": dropped}


def draft_from_audio(audio: bytes, filename: str, roster: list[dict],
                     trace: Trace | None = None) -> dict:
    """Transcribe, then draft. The audio is never stored and never returned."""
    # English by default here: a manager walking a floor in Ireland is dictating
    # names from the roster, and letting Whisper detect would let one Spanish
    # sentence flip the decoder for the whole note.
    transcript, _language = transcribe(audio, filename=filename, trace=trace)
    return draft_from_text(transcript, roster, trace=trace)

"""Understand a debrief given in Spanish, including the regional kind.

WHY THIS IS IN A COACHING PRODUCT

The mentor session put the workforce plainly: frontline staff "come from varied
countries, backgrounds and experience levels, with some entering hospitality
for the first time". In Irish hospitality a large share of that floor speaks
Spanish as a first language, and not one Spanish. A Cuban room attendant and a
Peruvian one do not use the same word for the same thing.

That matters here more than it would in a chat product, because a debrief is
not chat. It is evidence. It gets scored against a rubric, it becomes half of a
transfer gap, and it can send somebody on training. So a mistranslated debrief
is not an inconvenience, it is a staff member being assessed on something they
did not say, and the person it happens to is always the one who was not working
in their first language.

Two failures were possible and both are fixed here.

The first was ours: transcription pinned language="en" unconditionally, so
Spanish speech came back as English-shaped nonsense. Whisper now detects.

The second is the interesting one, and it is the thesis this borrows from.
A general translator treats Spanish as one language. `guagua` is a bus in the
Caribbean and a baby in the Andes. `vaina` is an all-purpose noun in Venezuela.
`parce` is how a Colombian addresses a friend. A model may guess from context
or may produce something plausible and wrong, which is worse, because nothing
downstream can tell the difference.

THE METHOD, AND WHAT IT MEASURED

From Glorvox, "Context-Aware Real-Time Speech Translation Using LLMs" (NCI,
2026). Retrieve the regional terms present in the utterance from a curated
lexicon, put their glosses in the prompt, and let an ordinary model translate
with them in front of it. No retraining, no second model, no new service: the
knowledge is prompt-level, which is the whole reason it can live inside this
API rather than beside it.

    regionally marked term survives translation
        without retrieval   31.2%      with retrieval   46.5%
        n=157, exact McNemar, p=8.05e-07
        replicated: 40.5% -> 70.3%, n=121, p=2.91e-11

WHAT THE STAFF MEMBER SEES

Both. Their own words and the English the system worked from, with the terms it
looked up named. The rest of this product refuses to let a manager act on
evidence they cannot inspect; it would be strange to hold the staff member to a
lower standard about their own sentence.
"""
from __future__ import annotations

from ..providers import ProviderError, Trace, complete
from .rag import build_prompt, retrieve


def is_spanish(language: str) -> bool:
    """Whisper names the language, it does not code it.

    Groq's Whisper returns "spanish", not "es", which a startswith("es") test
    quietly fails: "spanish" begins "sp". That bug is invisible in testing
    because the feature simply never triggers and the debrief still works, in
    English, exactly as it did before. Both spellings are accepted here, and
    the ISO code is kept because a different provider would send it.
    """
    value = (language or "").strip().lower()
    return value in {"es", "spa", "spanish", "castilian", "español", "espanol"}


# Function words that are common in Spanish and rare or absent in English, plus
# the characters English does not use. Deliberately not a language-detection
# library: this only has to separate Spanish from English well enough to decide
# whether to translate, and a wrong guess costs one model call that returns the
# text roughly unchanged.
_SPANISH_MARKERS = {
    "que", "de", "la", "el", "los", "las", "un", "una", "por", "para", "con",
    "pero", "porque", "como", "cuando", "estaba", "está", "fue", "ser", "muy",
    "no", "sí", "le", "me", "se", "y", "en", "del", "al", "su", "yo", "ella",
}
_SPANISH_CHARS = set("ñáéíóúü¿¡")


def looks_spanish(text: str) -> bool:
    """Guess the language of a TYPED debrief, where nothing detected it for us.

    Whisper reports the language of speech, but somebody who types their
    debrief in Spanish arrives with no signal at all, and defaulting that to
    English is the same failure as pinning the ASR language: the words are kept
    as they were, scored as if they were English, and nothing tells the person
    that half their meaning did not survive.

    Two independent signals are required, because one is too easy to trip. "No"
    and "y" appear in English sentences, and a stray accent appears in a name.
    """
    if not text:
        return False
    lowered = text.lower()
    words = [w.strip(".,!?¿¡;:()\"'") for w in lowered.split()]
    if len(words) < 4:
        return False
    marker_hits = sum(1 for w in words if w in _SPANISH_MARKERS)
    marker_ratio = marker_hits / len(words)
    has_spanish_chars = any(c in _SPANISH_CHARS for c in lowered)
    # A quarter of the words being Spanish function words is well clear of
    # anything an English sentence reaches.
    return marker_ratio >= 0.25 or (marker_ratio >= 0.12 and has_spanish_chars)


def understand(transcript: str, language: str,
               trace: Trace | None = None) -> dict:
    """Return the debrief in English, with what was done to get there.

    Keys: original, english, language, translated, terms, country.

    Never raises. Translation is an enhancement on a debrief that already
    exists, so a provider failure degrades to using the original text rather
    than losing the staff member's shift note.
    """
    result = {"original": transcript, "english": transcript,
              "language": language, "translated": False,
              "terms": [], "country": None}

    # Spoken debriefs carry a detected language. Typed ones carry nothing, so
    # the text itself has to be read.
    spanish = is_spanish(language) or (language in ("", "en", "english")
                                       and looks_spanish(transcript))
    if not transcript or not spanish:
        return result
    result["language"] = "spanish" if not is_spanish(language) else language

    context = retrieve(transcript)
    result["country"] = context.predicted_country
    result["terms"] = [
        {"term": hit.term, "gloss": hit.gloss,
         "countries": list(hit.countries[:3]), "ambiguous": hit.polysemous}
        for hit in context.hits[:8]
    ]

    try:
        english = complete(
            "translate",
            "You translate hospitality staff debriefs from Spanish into "
            "English. Keep the speaker's own voice and hedges; do not tidy "
            "them into corporate language, because how tentative somebody "
            "sounds about what they did is part of the evidence.",
            build_prompt(transcript, context),
            temperature=0.0, trace=trace, max_tokens=800)
    except ProviderError:
        # The Spanish stands. Scoring it will be worse than scoring the
        # translation, and far better than losing the debrief.
        return result

    # Asked for "the translation only", the model still tends to hand back a
    # quoted sentence. Those quotes would be stored as part of the debrief and
    # then quoted again as evidence, so they come off here.
    english = (english or "").strip()
    if len(english) > 1 and english[0] in "\"'“" and english[-1] in "\"'”":
        english = english[1:-1].strip()
    if english:
        result["english"] = english
        result["translated"] = True
    return result

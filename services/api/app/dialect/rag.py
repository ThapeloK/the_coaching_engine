"""
Dialect-aware slang retrieval for translation.

Ported unchanged from Glorvox, the MSc thesis this shares an author with:
"Context-Aware Real-Time Speech Translation Using LLMs" (NCI, 2026). The
measured result is that injecting retrieved regional glosses at prompt
level raises how often a regionally marked term survives translation from
31.2% to 46.5% (n=157, exact McNemar p=8.05e-07), replicated at 40.5% to
70.3% (n=121, p=2.91e-11). No retraining and no extra model: the knowledge
goes in the prompt, which is why it can live in this codebase at all.

Motivation
----------
A general translation system treats Spanish as one language. That fails on
regional vocabulary: `guagua` is a bus in the Caribbean and a baby in the
Andes; `vaina` is an all-purpose noun in Venezuela; `parce` is a Colombian
address term. A model may guess from context, or may silently produce a
plausible-but-wrong translation, which is worse.

This module supplies the missing knowledge explicitly. Given an utterance and
(optionally) a predicted dialect, it retrieves the relevant lexicon entries and
formats them for injection into the translation prompt. The translator is then
*told* what the regional terms mean rather than being left to infer them.

This is retrieval-augmented generation, but the retrieval index is a curated
dialect lexicon rather than a document store, and the query is the utterance
itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .slang_lexicon import LexiconHit, find_slang, score_country_affinity


@dataclass
class RetrievedContext:
    """Slang knowledge retrieved for one utterance."""

    hits: list[LexiconHit]
    predicted_country: Optional[str]
    confidence: float

    @property
    def has_slang(self) -> bool:
        return bool(self.hits)

    def to_prompt_block(self, max_terms: int = 8) -> str:
        """
        Render the retrieved glosses as a prompt fragment.

        Ambiguous terms are flagged explicitly: telling the model that `guagua`
        means 'bus' when the speaker is Andean would be worse than saying
        nothing, so polysemous entries carry their alternatives.
        """
        if not self.hits:
            return ""

        lines = []
        for hit in self.hits[:max_terms]:
            regions = ", ".join(hit.countries[:3])
            note = " [regionally ambiguous]" if hit.polysemous else ""
            lines.append(f'  - "{hit.term}" = {hit.gloss} ({regions}){note}')

        header = "Regional vocabulary in this utterance:"
        if self.predicted_country:
            header = (
                f"Speaker's variety appears to be {self.predicted_country}. "
                "Regional vocabulary in this utterance:"
            )
        return header + "\n" + "\n".join(lines)


def retrieve(
    text: str,
    country_hint: Optional[str] = None,
    restrict_to_hint: bool = False,
) -> RetrievedContext:
    """
    Retrieve slang knowledge for an utterance.

    Parameters
    ----------
    country_hint
        A dialect prediction from upstream (classifier or metadata). Used to
        rank and disambiguate, not to filter, unless `restrict_to_hint` is set.
    restrict_to_hint
        Search only the hinted country's lexicon. Higher precision, lower
        recall; appropriate when the dialect prediction is confident.
    """
    countries = [country_hint] if (country_hint and restrict_to_hint) else None
    hits = find_slang(text, countries=countries)

    affinity = score_country_affinity(text)
    if country_hint:
        predicted, confidence = country_hint, affinity.get(country_hint, 0.0)
    elif affinity:
        predicted, confidence = next(iter(affinity.items()))
    else:
        predicted, confidence = None, 0.0

    # Rank so that terms matching the predicted variety come first, then by
    # frequency in the utterance.
    if predicted:
        hits.sort(key=lambda h: (predicted not in h.countries, -h.count))

    return RetrievedContext(hits=hits, predicted_country=predicted,
                            confidence=float(confidence))


def build_prompt(
    text: str,
    context: RetrievedContext,
    target_language: str = "English",
    conversation: Optional[Sequence[str]] = None,
) -> str:
    """Assemble the full translation prompt, with or without retrieved slang."""
    parts = [f"Translate the following Spanish utterance into {target_language}."]

    if conversation:
        history = "\n".join(f"  {turn}" for turn in conversation)
        parts.append(f"\nConversation so far:\n{history}")

    block = context.to_prompt_block()
    if block:
        parts.append("\n" + block)
        parts.append(
            "\nUse these meanings. Render the sense naturally in "
            f"{target_language} rather than transliterating."
        )

    parts.append(f'\nSpanish: "{text}"')
    parts.append(f"\nReply with the {target_language} translation only.")
    return "\n".join(parts)


def gloss_keywords(hit: LexiconHit) -> list[str]:
    """
    Content words from a gloss, used to check whether a translation conveyed it.

    'bus, coach' -> ['bus', 'coach']; short function words are dropped so that
    matching is not satisfied by 'a' or 'to'.
    """
    stop = {"a", "an", "the", "to", "of", "or", "and", "for", "in", "on",
            "is", "be", "used", "something", "someone", "person", "thing"}
    words = []
    for chunk in hit.gloss.replace("/", ",").split(","):
        for word in chunk.strip().lower().split():
            cleaned = word.strip("()[[]'\".!?;:")
            if len(cleaned) > 2 and cleaned not in stop:
                words.append(cleaned)
    return words


def conveys_gloss(translation: str, hit: LexiconHit) -> bool:
    """
    Whether a translation appears to convey a slang term's meaning.

    A deliberately permissive check: any content word from the gloss counts.
    Under-detection would understate the method's benefit, so erring generous
    keeps the headline claim conservative.
    """
    lowered = translation.lower()
    keywords = gloss_keywords(hit)
    if not keywords:
        return False
    return any(k in lowered for k in keywords)

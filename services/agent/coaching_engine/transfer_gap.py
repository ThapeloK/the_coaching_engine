"""
transfer_gap.py
===============
The transfer gap: practice performance minus floor performance, per person,
per behavioural dimension.

This is the number the whole product is built on, so it is deliberately
deterministic. Same inputs, same output, every time, no model call anywhere
in this file. See LLD-D section 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Sequence

Quadrant = Literal["competent", "blocked", "recalibrate", "skill_gap"]

# Thresholds. Deliberately module-level constants rather than magic numbers:
# these are product decisions, and Mary-Susan should be able to find and
# argue with them without reading the code.
STRONG = 3.5          # at or above -> competent on this dimension
WEAK = 2.5            # at or below -> not yet competent
MIN_OBSERVATIONS = 1  # minimum floor scores before a quadrant is assigned
MIN_ATTEMPTS = 1      # minimum practice scores before a quadrant is assigned
HALF_LIFE_DAYS = 28   # recency weighting; see _weight()


@dataclass(frozen=True)
class Score:
    """One score on one dimension, from one evidence stream."""
    level: int                        # 1..5. Never 0, never None, filter first
    scored_at: date
    source: Literal["practice", "floor"]

    def __post_init__(self) -> None:
        if not 1 <= self.level <= 5:
            raise ValueError(f"level must be 1..5, got {self.level}")


@dataclass(frozen=True)
class Gap:
    dimension: str
    practice_mean: float | None
    floor_mean: float | None
    gap: float | None
    quadrant: Quadrant | None
    practice_n: int
    floor_n: int
    insufficient_evidence: bool

    @property
    def reading(self) -> str:
        """Plain-language reading, for the manager UI and the API response."""
        return {
            "competent": "Practice and floor performance align. Stretch them.",
            "blocked": "Knows how. Something is preventing execution on the floor.",
            "recalibrate": "Scores weak in practice but strong on the floor, "
                           "check the rubric and the scenario, not the person.",
            "skill_gap": "Weak in both. Targeted practice is the right answer.",
            None: "Not enough evidence yet on this dimension.",
        }[self.quadrant]


def _weight(scored_at: date, as_of: date) -> float:
    """Exponential recency weight with a 28-day half-life.

    An unweighted mean lets a strong attempt from eleven weeks ago mask a
    decline. Four weeks is chosen to match the learning-transfer literature:
    skills decay without ongoing support, so a month-old practice score should
    carry about half the weight of a fresh one.
    """
    age_days = (as_of - scored_at).days
    if age_days < 0:
        raise ValueError("scored_at is in the future relative to as_of")
    return 2.0 ** (-age_days / HALF_LIFE_DAYS)


def weighted_mean(scores: Sequence[Score], as_of: date) -> float | None:
    if not scores:
        return None
    weights = [_weight(s.scored_at, as_of) for s in scores]
    total = sum(weights)
    if total == 0:
        return None
    return sum(w * s.level for w, s in zip(weights, scores)) / total


def quadrant(practice_mean: float | None, floor_mean: float | None,
             practice_n: int, floor_n: int) -> Quadrant | None:
    """Assign a quadrant, or None when there is not enough evidence.

    Returning None rather than guessing is the whole point. A dimension with no
    floor observation has no gap, and saying so is more useful than showing a
    zero that looks like agreement.
    """
    if practice_n < MIN_ATTEMPTS or floor_n < MIN_OBSERVATIONS:
        return None
    if practice_mean is None or floor_mean is None:
        return None

    practice_strong = practice_mean >= STRONG
    floor_strong = floor_mean >= STRONG

    if practice_strong and floor_strong:
        return "competent"
    if practice_strong and not floor_strong:
        return "blocked"          # the interesting one
    if not practice_strong and floor_strong:
        return "recalibrate"      # a signal about our scoring, not about them
    return "skill_gap"


def compute_gap(dimension: str, scores: Sequence[Score], as_of: date) -> Gap:
    """Compute the transfer gap for one dimension from a mixed list of scores."""
    practice = [s for s in scores if s.source == "practice"]
    floor = [s for s in scores if s.source == "floor"]

    practice_mean = weighted_mean(practice, as_of)
    floor_mean = weighted_mean(floor, as_of)

    q = quadrant(practice_mean, floor_mean, len(practice), len(floor))
    gap_value = (round(practice_mean - floor_mean, 2)
                 if q is not None and practice_mean is not None
                 and floor_mean is not None else None)

    return Gap(
        dimension=dimension,
        practice_mean=round(practice_mean, 2) if practice_mean is not None else None,
        floor_mean=round(floor_mean, 2) if floor_mean is not None else None,
        gap=gap_value,
        quadrant=q,
        practice_n=len(practice),
        floor_n=len(floor),
        insufficient_evidence=q is None,
    )


def trend_slope(weekly_gaps: Sequence[float]) -> float | None:
    """Ordinary least squares slope over a weekly gap series.

    Returns None below three points. Two points always look like a trend and
    never are, showing a slope from two observations would be misleading in a
    product that a manager acts on.
    """
    n = len(weekly_gaps)
    if n < 3:
        return None
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(weekly_gaps) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, weekly_gaps))
    return round(num / denom, 3)

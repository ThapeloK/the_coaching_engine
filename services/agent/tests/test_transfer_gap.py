from datetime import date, timedelta

import pytest

from coaching_engine.transfer_gap import (
    Score, compute_gap, quadrant, trend_slope, weighted_mean,
)

AS_OF = date(2026, 9, 11)


def practice(level, days_ago=0):
    return Score(level=level, scored_at=AS_OF - timedelta(days=days_ago),
                 source="practice")


def floor(level, days_ago=0):
    return Score(level=level, scored_at=AS_OF - timedelta(days=days_ago),
                 source="floor")


# --------------------------------------------------------------- quadrants

def test_diego_is_blocked():
    """The demo case. Strong in practice, weak on the floor.

    This is the one quadrant where more training is the wrong answer, and it is
    the whole reason the product exists.
    """
    scores = [practice(5), practice(4), practice(5), floor(2), floor(2)]
    gap = compute_gap("service_recovery", scores, AS_OF)

    assert gap.quadrant == "blocked"
    assert gap.gap > 1.5
    assert "preventing execution" in gap.reading


def test_aoife_is_competent():
    scores = [practice(4), practice(5), floor(4), floor(5)]
    assert compute_gap("service_recovery", scores, AS_OF).quadrant == "competent"


def test_weak_in_both_is_a_skill_gap():
    scores = [practice(2), practice(2), floor(2), floor(1)]
    assert compute_gap("empathy", scores, AS_OF).quadrant == "skill_gap"


def test_strong_floor_weak_practice_flags_our_own_scoring():
    """Recalibrate is a signal about us, not about them."""
    scores = [practice(2), practice(2), floor(5), floor(4)]
    gap = compute_gap("communication", scores, AS_OF)

    assert gap.quadrant == "recalibrate"
    assert "not the person" in gap.reading


# ----------------------------------------------------- insufficient evidence

def test_no_floor_observation_means_no_quadrant():
    """A dimension with no floor score has no gap. Saying so beats showing a
    zero that looks like agreement."""
    gap = compute_gap("upselling", [practice(4), practice(5)], AS_OF)

    assert gap.quadrant is None
    assert gap.gap is None
    assert gap.insufficient_evidence is True
    assert gap.practice_n == 2 and gap.floor_n == 0


def test_no_practice_attempt_means_no_quadrant():
    gap = compute_gap("upselling", [floor(3)], AS_OF)
    assert gap.insufficient_evidence is True


def test_no_scores_at_all():
    gap = compute_gap("empathy", [], AS_OF)
    assert gap.quadrant is None
    assert gap.practice_mean is None and gap.floor_mean is None


# ------------------------------------------------------- recency weighting

def test_recent_scores_outweigh_old_ones():
    """A strong attempt from eleven weeks ago must not mask a recent decline."""
    recent_weak = weighted_mean([practice(5, days_ago=84), practice(1, days_ago=0)], AS_OF)
    assert recent_weak < 3.0


def test_half_life_is_28_days():
    """A 28-day-old score carries half the weight of a fresh one."""
    mean = weighted_mean([practice(5, days_ago=0), practice(1, days_ago=28)], AS_OF)
    # weights 1.0 and 0.5 -> (5*1.0 + 1*0.5) / 1.5 = 3.667
    assert mean == pytest.approx(3.667, abs=0.01)


def test_future_score_is_rejected():
    future = Score(level=3, scored_at=AS_OF + timedelta(days=1), source="practice")
    with pytest.raises(ValueError):
        weighted_mean([future], AS_OF)


# ------------------------------------------------------------- score bounds

@pytest.mark.parametrize("bad", [0, 6, -1])
def test_scores_outside_one_to_five_are_rejected(bad):
    """One scale, shared with the rules engine. Anything else is a bug we want
    to find at construction, not in a manager's face."""
    with pytest.raises(ValueError):
        Score(level=bad, scored_at=AS_OF, source="practice")


# -------------------------------------------------------------------- trend

def test_trend_needs_three_points():
    """Two points always look like a trend and never are."""
    assert trend_slope([1.0, 2.0]) is None
    assert trend_slope([1.0, 2.0, 3.0]) is not None


def test_widening_gap_has_positive_slope():
    assert trend_slope([1.5, 1.7, 2.0]) > 0


def test_closing_gap_has_negative_slope():
    assert trend_slope([2.0, 1.4, 0.9]) < 0


def test_flat_series_has_zero_slope():
    assert trend_slope([2.0, 2.0, 2.0]) == 0.0


# -------------------------------------------------------- threshold boundary

def test_boundary_is_inclusive_at_strong():
    assert quadrant(3.5, 3.5, 1, 1) == "competent"


def test_just_below_strong_on_the_floor_is_blocked():
    assert quadrant(3.5, 3.49, 1, 1) == "blocked"

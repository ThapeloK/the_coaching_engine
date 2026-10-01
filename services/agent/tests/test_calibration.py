import pytest

from coaching_engine.calibration import (
    calibrate, quadratic_weighted_kappa, wilson_interval,
)


# ------------------------------------------------------------ Wilson bounds

def test_wilson_is_wide_at_small_n():
    """With 7 of 8 agreements a naive read says 87.5%. Wilson says: not so fast."""
    point, lower, upper = wilson_interval(7, 8)
    assert point == pytest.approx(0.875)
    assert lower < 0.55          # genuinely uncertain down here
    assert upper > 0.97


def test_wilson_narrows_as_evidence_accumulates():
    _, lo_small, hi_small = wilson_interval(70, 80)
    _, lo_large, hi_large = wilson_interval(700, 800)
    assert (hi_large - lo_large) < (hi_small - lo_small)


def test_wilson_stays_inside_zero_and_one():
    for agreements, n in [(0, 5), (5, 5), (1, 100), (99, 100)]:
        _, lower, upper = wilson_interval(agreements, n)
        assert 0.0 <= lower <= upper <= 1.0


def test_wilson_rejects_impossible_inputs():
    with pytest.raises(ValueError):
        wilson_interval(5, 0)
    with pytest.raises(ValueError):
        wilson_interval(6, 5)


# ------------------------------------------------------------------ states

def test_unmeasured_when_no_verifications():
    c = calibrate("empathy", 0, 0)
    assert c.state == "unmeasured"
    assert c.rate is None
    assert "Not yet measured" in c.display


def test_provisional_below_ten():
    c = calibrate("empathy", 7, 8)
    assert c.state == "provisional"
    # the sample size must be visible: a bare percentage at n=8 is a lie
    assert "8 checks" in c.display


def test_reliable_needs_a_high_lower_bound():
    c = calibrate("empathy", 84, 100)
    assert c.state == "reliable"
    assert c.lower >= 0.75


def test_unreliable_routes_to_a_human_first():
    """This is what makes calibration active learning rather than a vanity
    metric: the agent asks for help exactly where it is weakest."""
    c = calibrate("upselling", 40, 100)
    assert c.state == "unreliable"
    assert c.route_to_human_first is True
    assert "caution" in c.display


def test_reliable_does_not_route_to_a_human():
    assert calibrate("empathy", 84, 100).route_to_human_first is False


def test_the_pitch_numbers_hold():
    """The two figures we say out loud on stage."""
    empathy = calibrate("empathy", 84, 100)
    upselling = calibrate("upselling", 61, 100)

    assert round(empathy.rate * 100) == 84
    assert round(upselling.rate * 100) == 61
    # naming our weakest dimension is the credibility move; it must be flagged
    assert upselling.state in ("uncertain", "unreliable")


# ------------------------------------------------------------------- kappa

def test_perfect_agreement_is_kappa_one():
    ratings = [1, 2, 3, 4, 5, 3, 3, 2]
    assert quadratic_weighted_kappa(ratings, ratings) == 1.0


def test_kappa_punishes_distant_disagreement_more_than_near():
    human = [3, 3, 3, 4, 4, 2, 5, 1]
    near = [3, 3, 4, 4, 5, 2, 4, 1]     # off by one in places
    far = [1, 5, 1, 5, 1, 5, 1, 5]      # wild

    assert quadratic_weighted_kappa(near, human) > quadratic_weighted_kappa(far, human)


def test_kappa_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        quadratic_weighted_kappa([1, 2], [1, 2, 3])


def test_kappa_rejects_out_of_range_ratings():
    with pytest.raises(ValueError):
        quadratic_weighted_kappa([0, 2], [1, 2])


def test_kappa_on_empty_input_is_none():
    assert quadratic_weighted_kappa([], []) is None

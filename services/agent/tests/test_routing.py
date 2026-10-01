from coaching_engine.routing import (
    K_ANONYMITY, RoutingContext, cohort_is_displayable, route,
)


# --------------------------------------------------------- the demo path

def test_cohort_process_problem_suppresses_individual_coaching():
    """Nine staff hitting the same wall is one process problem, not nine
    behaviour problems. The suppression is the whole point of the feature.
    """
    esc = route(RoutingContext(classification="process", cohort_size=9))

    assert esc.rule_id == "RC-PROCESS-COHORT"
    assert esc.route == "operations"
    assert esc.suppress_individual_coaching is True
    assert "not 9 people needing coaching" in esc.copy


def test_policy_cohort_goes_to_operations():
    esc = route(RoutingContext(classification="policy", cohort_size=4))

    assert esc.rule_id == "RC-POLICY-COHORT"
    assert esc.route == "operations"
    assert esc.suppress_individual_coaching is True
    assert "discretionary limit" in esc.copy


def test_small_process_cohort_does_not_suppress():
    """Below the cohort threshold there is no systemic finding to route."""
    esc = route(RoutingContext(classification="process", cohort_size=2))
    assert esc.rule_id != "RC-PROCESS-COHORT"


# --------------------------------------------------- individual behaviour

def test_lone_behavioural_gap_goes_to_the_manager():
    esc = route(RoutingContext(classification="behavioural"))

    assert esc.rule_id == "RC-BEHAV-DEFAULT"
    assert esc.route == "manager"
    assert esc.suppress_individual_coaching is False


def test_declining_floor_trend_is_flagged_to_the_manager():
    esc = route(RoutingContext(classification="behavioural",
                               floor_trend_slope=-0.8, floor_n=3))
    assert esc.rule_id == "RC-BEHAV-DECLINE"
    assert esc.route == "manager"


def test_a_declining_trend_on_two_observations_does_not_fire():
    esc = route(RoutingContext(classification="behavioural",
                               floor_trend_slope=-0.9, floor_n=2))
    assert esc.rule_id != "RC-BEHAV-DECLINE"


# ------------------------------------------------------------- severity

def test_sustained_low_scores_route_to_ld_as_support():
    esc = route(RoutingContext(classification="behavioural",
                               floor_mean=1.4, floor_n=3))

    assert esc.rule_id == "RC-SEVERE"
    assert esc.route == "ld_hr"
    assert esc.severity == 3
    # framing matters: this must not read as a disciplinary trigger
    assert "not for disciplinary action" in esc.copy


def test_low_mean_on_a_single_observation_does_not_escalate():
    esc = route(RoutingContext(classification="behavioural",
                               floor_mean=1.2, floor_n=1))
    assert esc.rule_id != "RC-SEVERE"


# ----------------------------------------------------------- disengagement

def test_disengagement_is_a_wellbeing_prompt_not_a_performance_flag():
    """The most ethically sensitive rule in the system. It infers something
    about a person from an absence of data, so the copy has to carry the
    innocent explanations explicitly.
    """
    esc = route(RoutingContext(classification="behavioural",
                               days_since_activity=30, prior_activity_days=3))

    assert esc.rule_id == "RC-DISENGAGE"
    assert esc.route == "ld_hr"
    assert "wellbeing check-in" in esc.copy
    assert "not a performance concern" in esc.copy
    assert "broken phone" in esc.copy


def test_someone_who_never_engaged_regularly_is_not_flagged():
    """Only a change in pattern is a signal. Someone who was always occasional
    has not disengaged.
    """
    esc = route(RoutingContext(classification="behavioural",
                               days_since_activity=30, prior_activity_days=60))
    assert esc.rule_id != "RC-DISENGAGE"


# -------------------------------------------------------- rule precedence

def test_severe_outranks_disengagement():
    """First match wins, and the order is the policy. Sustained poor floor
    performance is a more urgent finding than inactivity.
    """
    esc = route(RoutingContext(classification="behavioural",
                               floor_mean=1.3, floor_n=4,
                               days_since_activity=40, prior_activity_days=2))
    assert esc.rule_id == "RC-SEVERE"


def test_cohort_outranks_individual_severity():
    """If it is systemic, it is not a person problem, however bad the scores."""
    esc = route(RoutingContext(classification="process", cohort_size=9,
                               floor_mean=1.2, floor_n=5))
    assert esc.rule_id == "RC-PROCESS-COHORT"


# ---------------------------------------------------- always explainable

def test_every_route_records_the_rule_that_fired():
    """Article 14 requires we can explain why a case reached HR. 'The model
    decided' is not an explanation.
    """
    contexts = [
        RoutingContext(classification="behavioural"),
        RoutingContext(classification="policy"),
        RoutingContext(classification="process", cohort_size=9),
        RoutingContext(classification="behavioural", floor_mean=1.0, floor_n=5),
    ]
    for ctx in contexts:
        esc = route(ctx)
        assert esc.rule_id
        assert esc.rule_id in esc.explain()
        assert esc.route in ("manager", "ld_hr", "operations")


# ------------------------------------------------------------ k-anonymity

def test_cohort_below_k_is_not_displayable():
    assert cohort_is_displayable(K_ANONYMITY - 1) is False


def test_cohort_at_k_is_displayable():
    assert cohort_is_displayable(K_ANONYMITY) is True


def test_the_demo_cohort_of_nine_clears_the_threshold():
    assert cohort_is_displayable(9) is True


# --- the instrument, not the person ----------------------------------------
#
# RECALIBRATE means the floor score is HIGHER than the practice score: they do
# it correctly where it counts and not in the simulator. Routing that at the
# staff member would be the precise failure this product argues against, so it
# is a claim about our scoring and it outranks every other rule.

def test_recalibrate_routes_to_ld_as_a_measurement_concern():
    e = route(RoutingContext(classification="process", quadrant="recalibrate"))
    assert e.rule_id == "RC-MEASUREMENT"
    assert e.route == "ld_hr"
    assert e.suppress_individual_coaching is True


def test_recalibrate_outranks_a_process_cohort():
    # Even with a full cohort behind it, the instrument claim wins.
    e = route(RoutingContext(classification="process", quadrant="recalibrate",
                             cohort_size=9))
    assert e.rule_id == "RC-MEASUREMENT"


def test_recalibrate_outranks_severe_floor_scores():
    # A low floor mean cannot be true at the same time as recalibrate, but if
    # the data ever says both, we must not send a person to HR on the strength
    # of a reading we have just called unreliable.
    e = route(RoutingContext(classification="process", quadrant="recalibrate",
                             floor_mean=1.2, floor_n=4))
    assert e.rule_id == "RC-MEASUREMENT"
    assert e.route == "ld_hr"
    assert e.severity == 1


def test_other_quadrants_are_unaffected():
    assert route(RoutingContext(classification="behavioural",
                                quadrant="skill_gap")).rule_id == "RC-BEHAV-DEFAULT"
    assert route(RoutingContext(classification="policy", quadrant="blocked",
                                cohort_size=6)).rule_id == "RC-POLICY-COHORT"


def test_quadrant_defaults_to_none_and_changes_nothing():
    # Callers that predate the field must route exactly as before.
    assert route(RoutingContext(classification="behavioural")).rule_id == "RC-BEHAV-DEFAULT"

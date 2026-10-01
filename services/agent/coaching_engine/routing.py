"""
routing.py
==========
Escalation routing: turning a finding into somebody's job.

Every rule here is deterministic and first-match-wins, and every fired rule
records its rule_id. That is not fussiness. Under EU AI Act Article 14 we must
be able to explain to a human overseer why a case reached HR, and "the model
decided" is not an explanation. "Rule RC-SEVERE fired because the floor mean was
1.4 across three observations" is.

Nothing in this file calls a model. See LLD-C section 2.10 and LLD-F section 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

Route = Literal["manager", "ld_hr", "operations"]
Classification = Literal["behavioural", "process", "policy"]

K_ANONYMITY = 5   # no cohort insight is displayed below this many staff


@dataclass(frozen=True)
class RoutingContext:
    """Everything the rules are allowed to see. All of it computed, none inferred."""
    classification: Classification
    quadrant: str | None = None         # from the transfer gap, never inferred
    cohort_size: int = 0
    floor_mean: float | None = None
    floor_n: int = 0
    floor_trend_slope: float | None = None
    days_since_activity: int = 0
    prior_activity_days: int = 999      # how regularly they used to engage


@dataclass(frozen=True)
class Escalation:
    rule_id: str
    route: Route
    severity: int                # 1 low, 2 medium, 3 high
    suppress_individual_coaching: bool
    copy: str

    def explain(self) -> str:
        return (f"Rule {self.rule_id} routed this to {self.route} "
                f"at severity {self.severity}.")


# The copy matters as much as the routing. An escalation that reads as an
# accusation produces a defensive manager and a frightened staff member.
COPY = {
    "RC-PROCESS-COHORT":
        "{n} staff hit the same wall this week. This is one process problem, "
        "not {n} people needing coaching. Individual coaching is suppressed.",
    "RC-POLICY-COHORT":
        "{n} staff were unclear on what they are permitted to offer. That is a "
        "policy gap, not a behavioural one. Suggested action: set and "
        "communicate a discretionary limit.",
    "RC-POLICY-SINGLE":
        "This looks like authority ambiguity rather than a skill gap. Worth "
        "confirming what this person believes they are allowed to do.",
    "RC-BEHAV-DECLINE":
        "Floor performance has been declining over the last three observations. "
        "Worth a conversation before it becomes a pattern.",
    "RC-DISENGAGE":
        "No platform activity in {days} days, after previously engaging "
        "regularly. This is a prompt for a wellbeing check-in, not a "
        "performance concern. Non-use has many innocent explanations: leave, "
        "illness, a broken phone, a change of shift pattern.",
    "RC-SEVERE":
        "Sustained low floor scores across multiple observations. Routed to "
        "L&D for support, not for disciplinary action.",
    "RC-BEHAV-DEFAULT":
        "An individual coaching conversation is the right next step.",
    "RC-MEASUREMENT":
        "This person scores HIGHER on the floor than in practice. The floor is "
        "the outcome we actually care about, so the likely fault is ours: the "
        "scenario, the rubric anchors, or the scoring. Routed to L&D to check "
        "the instrument. No coaching action is suggested for this person.",
}


# First match wins. Order is the policy.
RULES: list[tuple[str, Callable[[RoutingContext], bool], Route, int, bool]] = [
    # First, because it is a claim about our own instrument and it outranks
    # every claim about the person. RECALIBRATE means they did the thing on
    # the floor and not in the simulator. The floor is the ground truth we
    # sell, so a disagreement in that direction is evidence against the
    # simulator, not against the staff member. Routing it at the person would
    # be the exact failure this product exists to argue against: sending
    # training to someone whose real-world performance is already good.
    ("RC-MEASUREMENT",
     lambda c: c.quadrant == "recalibrate",
     "ld_hr", 1, True),

    ("RC-PROCESS-COHORT",
     lambda c: c.classification == "process" and c.cohort_size >= K_ANONYMITY,
     "operations", 2, True),

    ("RC-POLICY-COHORT",
     lambda c: c.classification == "policy" and c.cohort_size >= 3,
     "operations", 2, True),

    ("RC-SEVERE",
     lambda c: c.floor_mean is not None and c.floor_mean <= 1.5 and c.floor_n >= 3,
     "ld_hr", 3, False),

    ("RC-DISENGAGE",
     lambda c: c.days_since_activity > 21 and c.prior_activity_days < 7,
     "ld_hr", 2, False),

    ("RC-BEHAV-DECLINE",
     lambda c: (c.floor_trend_slope is not None
                and c.floor_trend_slope < -0.5 and c.floor_n >= 3),
     "manager", 2, False),

    ("RC-POLICY-SINGLE",
     lambda c: c.classification == "policy",
     "manager", 1, False),

    ("RC-BEHAV-DEFAULT",
     lambda c: c.classification == "behavioural",
     "manager", 1, False),
]


def route(ctx: RoutingContext) -> Escalation:
    """Return the first matching escalation. Always returns something."""
    for rule_id, predicate, dest, severity, suppress in RULES:
        if predicate(ctx):
            return Escalation(
                rule_id=rule_id,
                route=dest,
                severity=severity,
                suppress_individual_coaching=suppress,
                copy=COPY[rule_id].format(n=ctx.cohort_size,
                                          days=ctx.days_since_activity),
            )

    # Defensive: the behavioural default should always catch. If it does not,
    # fail toward the least consequential route rather than toward HR.
    return Escalation("RC-FALLBACK", "manager", 1, False,
                      "Routed to the duty manager for review.")


def cohort_is_displayable(distinct_staff: int) -> bool:
    """Below k, a 'pattern' in a hotel department identifies individuals.

    Enforced here and as a database check constraint. Belt and braces on
    purpose: this is the control most likely to be quietly dropped under
    deadline pressure, and it is the one a works council would ask about.
    """
    return distinct_staff >= K_ANONYMITY

"""
calibration.py
==============
The Calibration Score: how often the agent's read agrees with the manager's,
per property, per behavioural dimension.

This is our answer to "how do you know the coaching is any good?", and it is
the feature that lets the product say when it should not be trusted. See
LLD-D section 5.

No model call in this file. It is arithmetic over stored verifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Literal, Sequence

Z_95 = 1.96

# Below this many labels we refuse to present a rate as if it means something.
PROVISIONAL_BELOW_N = 10
RELIABLE_LOWER_BOUND = 0.75   # lower bound of the interval, not the point estimate
UNRELIABLE_UPPER_BOUND = 0.65

State = Literal["unmeasured", "provisional", "reliable", "uncertain", "unreliable"]


@dataclass(frozen=True)
class Calibration:
    dimension: str
    agreements: int
    n: int
    rate: float | None
    lower: float | None
    upper: float | None
    state: State

    @property
    def route_to_human_first(self) -> bool:
        """Low-confidence dimensions get a human before the manager sees them.

        This is what makes the calibration score active learning rather than a
        vanity metric: the agent asks for help precisely where it is weakest.
        """
        return self.state == "unreliable"

    @property
    def _checks(self) -> str:
        """"1 check", not "1 checks". This string is the first thing a manager
        reads about whether to trust the system, and a grammar slip there is
        read as sloppiness about the number itself."""
        return f"{self.n} check" + ("" if self.n == 1 else "s")

    @property
    def display(self) -> str:
        """The sentence a manager actually reads."""
        if self.state == "unmeasured":
            return "Not yet measured on this dimension."
        pct = round((self.rate or 0) * 100)
        if self.state == "provisional":
            return (f"Agrees with your managers {pct}% of the time "
                    f"so far, on only {self._checks}.")
        if self.state == "unreliable":
            return (f"Agrees with your managers {pct}% of the time on this "
                    f"dimension. Treat with caution. We route these to a "
                    f"human first.")
        if self.state == "uncertain":
            return (f"Agrees with your managers {pct}% of the time "
                    f"({self._checks}). Still settling.")
        return f"Agrees with your managers {pct}% of the time ({self._checks})."


def wilson_interval(agreements: int, n: int, z: float = Z_95
                    ) -> tuple[float, float, float]:
    """Wilson score interval. Returns (point_estimate, lower, upper).

    A bare percentage overstates what we know at small n, and small n is exactly
    our situation during a two-week build: with eight verifications, 0.875 and
    0.62 are not meaningfully different. Wilson behaves properly down there,
    where the normal approximation does not.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= agreements <= n:
        raise ValueError("agreements must be between 0 and n")

    p = agreements / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def calibrate(dimension: str, agreements: int, n: int) -> Calibration:
    if n == 0:
        return Calibration(dimension, 0, 0, None, None, None, "unmeasured")

    rate, lower, upper = wilson_interval(agreements, n)

    if n < PROVISIONAL_BELOW_N:
        state: State = "provisional"
    elif lower >= RELIABLE_LOWER_BOUND:
        state = "reliable"
    elif upper < UNRELIABLE_UPPER_BOUND:
        state = "unreliable"
    else:
        state = "uncertain"

    return Calibration(dimension, agreements, n,
                       round(rate, 3), round(lower, 3), round(upper, 3), state)


def quadratic_weighted_kappa(agent: Sequence[int], human: Sequence[int],
                             k: int = 5) -> float | None:
    """Chance-corrected agreement with quadratic weights.

    Raw agreement flatters us when scores cluster: if 70% of all ratings are a
    3, agreeing 70% of the time is worth nothing. Quadratic weights also credit
    near misses (a 4 against a 5) far more than distant ones (a 1 against a 5),
    which is the right behaviour for an ordinal rubric.

    Report raw agreement in the product UI, because managers understand
    percentages. Report this in the eval harness and on stage, because a judge
    who knows the field will ask whether we corrected for chance.
    """
    if len(agent) != len(human):
        raise ValueError("agent and human must be the same length")
    n = len(agent)
    if n == 0:
        return None
    for v in (*agent, *human):
        if not 1 <= v <= k:
            raise ValueError(f"ratings must be 1..{k}, got {v}")

    # Observed matrix
    observed = [[0] * k for _ in range(k)]
    for a, h in zip(agent, human):
        observed[a - 1][h - 1] += 1

    # Expected matrix, from the marginals
    agent_marginal = [sum(observed[i]) for i in range(k)]
    human_marginal = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    expected = [[agent_marginal[i] * human_marginal[j] / n
                 for j in range(k)] for i in range(k)]

    def weight(i: int, j: int) -> float:
        return ((i - j) ** 2) / ((k - 1) ** 2)

    num = sum(weight(i, j) * observed[i][j] for i in range(k) for j in range(k))
    den = sum(weight(i, j) * expected[i][j] for i in range(k) for j in range(k))
    if den == 0:
        return None
    return round(1 - num / den, 3)

"""Cost primitives.

All costs are expressed in basis points of notional unless the name says
``dollars``. The decomposition is deliberately additive:

    expected_cost = half_spread + commission + market_impact

Timing risk is a standard deviation, not an expected cost, and is reported
separately. Mixing the two is the most common way an execution analysis
overstates its precision.
"""

from __future__ import annotations

import math

import numpy as np


def as_bps(fraction: float) -> float:
    """Convert a return fraction to basis points."""
    return float(fraction) * 1e4


def as_fraction(bps: float) -> float:
    """Convert basis points to a return fraction."""
    return float(bps) / 1e4


def half_spread_bps(quoted_spread_bps: float) -> float:
    """Cost of crossing half of a quoted bid-ask spread."""
    if quoted_spread_bps < 0:
        raise ValueError("quoted_spread_bps must be non-negative")
    return float(quoted_spread_bps) / 2.0


def participation(shares: float, adv_shares: float) -> float:
    """Order size as a fraction of average daily volume."""
    if adv_shares <= 0:
        raise ValueError("adv_shares must be positive")
    return abs(float(shares)) / float(adv_shares)


def impact_bps(
    participation_fraction: float,
    sigma_daily: float,
    k: float,
    exponent: float = 0.5,
) -> float:
    """Square-root market impact in basis points.

    ``impact = k * sigma_daily * participation**exponent``, with ``sigma_daily``
    in return units and the result converted to bps. The model is a stylised
    approximation; ``k`` is not identified from daily data.
    """
    if participation_fraction < 0:
        raise ValueError("participation_fraction must be non-negative")
    if sigma_daily < 0:
        raise ValueError("sigma_daily must be non-negative")
    if k < 0:
        raise ValueError("k must be non-negative")
    if exponent <= 0:
        raise ValueError("exponent must be positive")
    if participation_fraction == 0 or sigma_daily == 0 or k == 0:
        return 0.0
    return float(k * sigma_daily * 1e4 * participation_fraction**exponent)


def linear_cost_bps(quoted_spread_bps: float, commission_bps: float) -> float:
    """Half-spread plus commission, with no impact."""
    if commission_bps < 0:
        raise ValueError("commission_bps must be non-negative")
    return half_spread_bps(quoted_spread_bps) + float(commission_bps)


def dollars_from_bps(bps: float, notional: float) -> float:
    """Convert a bps cost to dollars for a given notional."""
    if notional < 0:
        raise ValueError("notional must be non-negative")
    return float(bps) / 1e4 * float(notional)


def bps_from_dollars(dollars: float, notional: float) -> float:
    """Convert a dollar cost to bps of notional."""
    if notional <= 0:
        raise ValueError("notional must be positive")
    return float(dollars) / float(notional) * 1e4


def normal_var_multiplier(level: float = 0.95) -> float:
    """One-sided normal quantile for a cost distribution."""
    if not 0 < level < 1:
        raise ValueError("level must be in (0, 1)")
    # Inverse normal CDF via erfinv; scipy is a dependency but this keeps the
    # primitive dependency-free and exact for the levels we use.
    from statistics import NormalDist

    return NormalDist().inv_cdf(level)


def normal_cvar_multiplier(level: float = 0.95) -> float:
    """Expected shortfall multiplier for a normal distribution."""
    if not 0 < level < 1:
        raise ValueError("level must be in (0, 1)")
    z = normal_var_multiplier(level)
    return math.exp(-0.5 * z * z) / (math.sqrt(2.0 * math.pi) * (1.0 - level))


def total_expected_cost_bps(
    quoted_spread_bps: float,
    commission_bps: float,
    impact_cost_bps: float,
) -> float:
    """Additive expected-cost decomposition."""
    return (
        half_spread_bps(quoted_spread_bps)
        + float(commission_bps)
        + float(impact_cost_bps)
    )


def worry_if_large(participation_fraction: float, cap: float = 0.25) -> bool:
    """Return True when an order is outside the model's comfortable range."""
    return bool(participation_fraction > cap)


def safe_sqrt(value: float) -> float:
    """Square root that returns 0 for non-positive input."""
    return float(np.sqrt(max(float(value), 0.0)))

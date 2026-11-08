"""Frozen model parameters.

Every default is a modelling choice, not a measured constant. The docstrings say
what the choice is and why it is the default. Change a value only with a note in
``docs/DECISIONS.md``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketConfig:
    """Trailing-window parameters for the market-state estimate.

    The windows are short on purpose: they are what a trader could actually know
    before the order. A 20-day window is a compromise between noise and
    responsiveness; it is not an estimated optimum.
    """

    adv_window: int = 20
    vol_window: int = 20
    spread_window: int = 20
    spread_floor_bps: float = 1.0
    spread_cap_bps: float = 100.0
    spread_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if self.adv_window < 2:
            raise ValueError("adv_window must be at least 2")
        if self.vol_window < 2:
            raise ValueError("vol_window must be at least 2")
        if self.spread_window < 2:
            raise ValueError("spread_window must be at least 2")
        if not 0 <= self.spread_floor_bps <= self.spread_cap_bps:
            raise ValueError("spread floor must be between 0 and the cap")
        if self.spread_multiplier <= 0:
            raise ValueError("spread_multiplier must be positive")


@dataclass(frozen=True)
class CostConfig:
    """Cost-model parameters.

    Parameters
    ----------
    commission_bps:
        All-in commission and fees in basis points of notional. The default
        0.5 bp is conservative for a modern institutional ETF order; retail
        commissions are often zero but exchange/regulatory fees are not.
    impact_k:
        Coefficient in ``impact_bps = k * sigma_bps * participation**exponent``.
        The default 0.5 is a deliberate middle of the plausible range. The model
        is not identified from daily data; report a range, never this point
        estimate alone.
    impact_exponent:
        Square-root law by default. An exponent of 1 gives a linear model, which
        is useful as a falsification case.
    impact_mode:
        ``"per_slice"`` lets the schedule change impact by changing the
        participation of each slice. ``"total"`` applies impact to the total
        order once, so schedules differ only in timing risk. The latter is a
        sensitivity case, not the primary model.
    risk_aversion:
        Weight on timing-risk standard deviation in the schedule objective:
        ``expected_cost + risk_aversion * timing_risk``. 0.05 is a small
        penalty, chosen so the demo does not mechanically prefer immediate
        execution for every order. It is not a measured preference: the demo
        reports the frontier so the reader can choose another.
    fixed_bps:
        The naive fixed-cost baseline used in the ranking comparison.
    participation_cap:
        A warning threshold, not a hard constraint. Orders above it are
        extrapolations of the square-root model.
    """

    commission_bps: float = 0.5
    impact_k: float = 0.5
    impact_exponent: float = 0.5
    impact_mode: str = "per_slice"
    risk_aversion: float = 0.05
    fixed_bps: float = 10.0
    participation_cap: float = 0.25

    def __post_init__(self) -> None:
        if self.commission_bps < 0:
            raise ValueError("commission_bps must be non-negative")
        if self.impact_k < 0:
            raise ValueError("impact_k must be non-negative")
        if self.impact_exponent <= 0:
            raise ValueError("impact_exponent must be positive")
        if self.impact_mode not in {"per_slice", "total"}:
            raise ValueError("impact_mode must be 'per_slice' or 'total'")
        if self.risk_aversion < 0:
            raise ValueError("risk_aversion must be non-negative")
        if self.fixed_bps < 0:
            raise ValueError("fixed_bps must be non-negative")
        if not 0 < self.participation_cap <= 1:
            raise ValueError("participation_cap must be in (0, 1]")

    def with_overrides(self, **kwargs: float | str) -> "CostConfig":
        """Return a copy with selected fields replaced."""
        values = {field: getattr(self, field) for field in self.__dataclass_fields__}
        values.update(kwargs)
        return CostConfig(**values)


#: Sensitivity grid for the impact coefficient. The point is the range, not one
#: number. 0.1 is optimistic, 2.0 is punitive.
DEFAULT_K_GRID: tuple[float, ...] = (0.1, 0.25, 0.5, 1.0, 2.0)

#: Risk-aversion grid for the schedule frontier. 0 = pure expected cost.
DEFAULT_RISK_AVERSIONS: tuple[float, ...] = (0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0)

#: Participation grid for the single-order cost curve.
DEFAULT_PARTICIPATION_GRID: tuple[float, ...] = (
    0.001,
    0.005,
    0.01,
    0.02,
    0.05,
    0.10,
    0.20,
    0.30,
)

#: AUM grid for the scale sensitivity. The point is where a strategy loses its
#: absolute edge, not the precise AUM at which that happens. The upper end is
#: deliberately beyond a plausible small-fund size: capacity is a stress test,
#: not a forecast.
DEFAULT_AUM_GRID: tuple[float, ...] = (
    25e6,
    100e6,
    250e6,
    500e6,
    1e9,
    2.5e9,
    5e9,
    10e9,
    25e9,
    50e9,
)

#: The naive baseline a student backtest usually subtracts.
NAIVE_COST_BPS = 10.0

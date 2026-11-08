"""Execution-cost simulator.

The simulator answers one question: given an order, a market state, and a
schedule, what is the expected cost and the timing risk?

It is intentionally an *expectation* engine. It does not simulate a price path,
because a daily-data model cannot credibly identify intraday path dynamics. The
timing-risk term is the standard deviation of the implementation shortfall under
a zero-drift random walk, which is the smallest defensible risk model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .config import CostConfig
from .costs import (
    dollars_from_bps,
    half_spread_bps,
    impact_bps,
    normal_cvar_multiplier,
    normal_var_multiplier,
)
from .schedules import Schedule


class SimulationError(ValueError):
    """Raised when an order cannot be simulated."""


@dataclass
class ExecutionResult:
    """Cost decomposition for one parent order under one schedule."""

    ticker: str
    side: str
    shares: float
    price: float
    notional: float
    schedule: str
    horizon_days: float
    volume_days: float
    participation: float
    spread_bps: float
    half_spread_bps: float
    commission_bps: float
    impact_bps: float
    expected_cost_bps: float
    expected_cost_dollars: float
    timing_risk_bps: float
    timing_risk_dollars: float
    objective_bps: float
    var95_bps: float
    cvar95_bps: float
    risk_aversion: float
    impact_k: float
    participation_warning: bool
    slices: pd.DataFrame

    def to_dict(self) -> dict[str, float | str | bool]:
        """JSON-friendly summary (the slice table is omitted)."""
        return {
            "ticker": self.ticker,
            "side": self.side,
            "shares": self.shares,
            "price": self.price,
            "notional": self.notional,
            "schedule": self.schedule,
            "horizon_days": self.horizon_days,
            "volume_days": self.volume_days,
            "participation": self.participation,
            "spread_bps": self.spread_bps,
            "half_spread_bps": self.half_spread_bps,
            "commission_bps": self.commission_bps,
            "impact_bps": self.impact_bps,
            "expected_cost_bps": self.expected_cost_bps,
            "expected_cost_dollars": self.expected_cost_dollars,
            "timing_risk_bps": self.timing_risk_bps,
            "timing_risk_dollars": self.timing_risk_dollars,
            "objective_bps": self.objective_bps,
            "var95_bps": self.var95_bps,
            "cvar95_bps": self.cvar95_bps,
            "risk_aversion": self.risk_aversion,
            "impact_k": self.impact_k,
            "participation_warning": self.participation_warning,
        }


def _validate_order(
    shares: float,
    price: float,
    adv_shares: float,
    sigma_daily: float,
    spread_bps: float,
) -> None:
    if not np.isfinite(shares) or shares == 0:
        raise SimulationError("shares must be finite and non-zero")
    if not np.isfinite(price) or price <= 0:
        raise SimulationError("price must be finite and positive")
    if not np.isfinite(adv_shares) or adv_shares <= 0:
        raise SimulationError("adv_shares must be finite and positive")
    if not np.isfinite(sigma_daily) or sigma_daily < 0:
        raise SimulationError("sigma_daily must be finite and non-negative")
    if not np.isfinite(spread_bps) or spread_bps < 0:
        raise SimulationError("spread_bps must be finite and non-negative")


def _timing_risk_bps(schedule: Schedule, sigma_daily: float) -> float:
    """Standard deviation of implementation shortfall, in bps of notional.

    For fractions ``x`` and execution times ``t`` in days, the variance of the
    weighted average price under a zero-drift random walk is

        sigma_daily^2 * x' M x,    M_ij = min(t_i, t_j).

    Immediate execution has all times equal to zero, so the risk is exactly zero
    relative to the arrival price.
    """
    x = schedule.fractions
    times = schedule.times_days
    covariance = np.minimum.outer(times, times)
    variance = float(x @ covariance @ x)
    return float(sigma_daily * 1e4 * np.sqrt(max(variance, 0.0)))


def simulate_order(
    ticker: str,
    shares: float,
    price: float,
    adv_shares: float,
    sigma_daily: float,
    spread_bps: float,
    schedule: Schedule,
    config: CostConfig | None = None,
) -> ExecutionResult:
    """Decompose the expected cost and timing risk of one parent order.

    Parameters
    ----------
    ticker:
        Label only; the simulator does not look anything up.
    shares:
        Signed parent order. The sign sets the side; costs are symmetric.
    price, adv_shares, sigma_daily, spread_bps:
        Point-in-time market state. Use :func:`compute_market_state` to obtain
        these without look-ahead.
    schedule:
        A validated :class:`~execution_lab.schedules.Schedule`.
    config:
        Cost parameters. Defaults are conservative but are not estimates.
    """
    config = config or CostConfig()
    _validate_order(shares, price, adv_shares, sigma_daily, spread_bps)

    side = "buy" if shares > 0 else "sell"
    quantity = abs(float(shares))
    notional = quantity * float(price)
    n = schedule.n_slices

    participation_by_slice = schedule.participation(quantity, adv_shares)
    if config.impact_mode == "total":
        total_participation = quantity / (adv_shares * schedule.volume_days)
        impact_by_slice = np.full(
            n,
            impact_bps(
                total_participation,
                sigma_daily,
                config.impact_k,
                config.impact_exponent,
            ),
        )
    else:
        impact_by_slice = np.array(
            [
                impact_bps(
                    p,
                    sigma_daily,
                    config.impact_k,
                    config.impact_exponent,
                )
                for p in participation_by_slice
            ]
        )

    impact_total = float(np.sum(schedule.fractions * impact_by_slice))
    half_spread = half_spread_bps(spread_bps)
    commission = float(config.commission_bps)
    expected_bps = half_spread + commission + impact_total

    timing_bps = _timing_risk_bps(schedule, sigma_daily)
    objective_bps = expected_bps + config.risk_aversion * timing_bps
    var95_bps = expected_bps + normal_var_multiplier(0.95) * timing_bps
    cvar95_bps = expected_bps + normal_cvar_multiplier(0.95) * timing_bps

    expected_dollars = dollars_from_bps(expected_bps, notional)
    timing_dollars = dollars_from_bps(timing_bps, notional)

    slice_shares = schedule.slice_shares(quantity)
    slice_notional = slice_shares * float(price)
    slice_cost_bps = half_spread + commission + impact_by_slice
    slice_cost_dollars = slice_notional * slice_cost_bps / 1e4
    slices = pd.DataFrame(
        {
            "slice": np.arange(n, dtype=int),
            "day": np.floor(schedule.times_days).astype(int),
            "time_days": schedule.times_days,
            "fraction": schedule.fractions,
            "volume_fraction": schedule.volume_fractions,
            "shares": slice_shares,
            "notional": slice_notional,
            "participation": participation_by_slice,
            "impact_bps": impact_by_slice,
            "cost_bps": slice_cost_bps,
            "cost_dollars": slice_cost_dollars,
        }
    )

    # The decomposition must add up. A tolerance of 1e-9 dollars is generous
    # relative to notional but tight enough to catch a dropped term.
    if not np.isclose(slice_cost_dollars.sum(), expected_dollars, rtol=1e-9, atol=1e-6):
        raise SimulationError("slice costs do not sum to the total expected cost")
    if not np.isclose(slice_shares.sum(), quantity, rtol=1e-9, atol=1e-9):
        raise SimulationError("slice shares do not sum to the parent order")

    overall_participation = quantity / (adv_shares * schedule.volume_days)
    return ExecutionResult(
        ticker=ticker,
        side=side,
        shares=quantity,
        price=float(price),
        notional=notional,
        schedule=schedule.name,
        horizon_days=schedule.horizon_days,
        volume_days=schedule.volume_days,
        participation=float(overall_participation),
        spread_bps=float(spread_bps),
        half_spread_bps=float(half_spread),
        commission_bps=commission,
        impact_bps=impact_total,
        expected_cost_bps=float(expected_bps),
        expected_cost_dollars=float(expected_dollars),
        timing_risk_bps=float(timing_bps),
        timing_risk_dollars=float(timing_dollars),
        objective_bps=float(objective_bps),
        var95_bps=float(var95_bps),
        cvar95_bps=float(cvar95_bps),
        risk_aversion=float(config.risk_aversion),
        impact_k=float(config.impact_k),
        participation_warning=bool(overall_participation > config.participation_cap),
        slices=slices,
    )


def compare_schedules(
    ticker: str,
    shares: float,
    price: float,
    adv_shares: float,
    sigma_daily: float,
    spread_bps: float,
    schedules: Iterable[Schedule],
    config: CostConfig | None = None,
) -> pd.DataFrame:
    """Simulate a menu of schedules and return a tidy comparison table."""
    rows = [
        simulate_order(
            ticker=ticker,
            shares=shares,
            price=price,
            adv_shares=adv_shares,
            sigma_daily=sigma_daily,
            spread_bps=spread_bps,
            schedule=schedule,
            config=config,
        ).to_dict()
        for schedule in schedules
    ]
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table = table.sort_values(["objective_bps", "expected_cost_bps", "schedule"])
    table["objective_rank"] = np.arange(1, len(table) + 1)
    return table.drop(columns=[]).reset_index(drop=True)


def choose_schedule(
    ticker: str,
    shares: float,
    price: float,
    adv_shares: float,
    sigma_daily: float,
    spread_bps: float,
    schedules: Iterable[Schedule],
    config: CostConfig | None = None,
) -> tuple[ExecutionResult, pd.DataFrame]:
    """Return the schedule with the lowest objective and the full comparison."""
    table = compare_schedules(
        ticker=ticker,
        shares=shares,
        price=price,
        adv_shares=adv_shares,
        sigma_daily=sigma_daily,
        spread_bps=spread_bps,
        schedules=schedules,
        config=config,
    )
    if table.empty:
        raise SimulationError("no schedules supplied")
    best_name = str(table.iloc[0]["schedule"])
    best_schedule = next(s for s in schedules if s.name == best_name)
    result = simulate_order(
        ticker=ticker,
        shares=shares,
        price=price,
        adv_shares=adv_shares,
        sigma_daily=sigma_daily,
        spread_bps=spread_bps,
        schedule=best_schedule,
        config=config,
    )
    return result, table


def cost_curve(
    ticker: str,
    price: float,
    adv_shares: float,
    sigma_daily: float,
    spread_bps: float,
    participation_grid: Iterable[float],
    schedule: Schedule,
    config: CostConfig | None = None,
) -> pd.DataFrame:
    """Expected cost and timing risk as order size varies, holding the schedule."""
    rows = []
    for p in participation_grid:
        if p <= 0:
            raise ValueError("participation must be positive")
        shares = p * adv_shares
        result = simulate_order(
            ticker=ticker,
            shares=shares,
            price=price,
            adv_shares=adv_shares,
            sigma_daily=sigma_daily,
            spread_bps=spread_bps,
            schedule=schedule,
            config=config,
        )
        row = result.to_dict()
        row["target_participation"] = p
        rows.append(row)
    return pd.DataFrame(rows)

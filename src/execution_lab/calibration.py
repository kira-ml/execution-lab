"""Calibration and implied-impact diagnostics.

The square-root coefficient ``k`` is not identified from daily OHLCV alone. This
module therefore does two honest things:

1. If a user has *observed execution costs* with the matching volatility and
   participation, it fits ``cost_bps = k * sigma_bps * participation**exponent``
   by least squares and reports a standard error and bootstrap interval.
2. If the user does not, it reports the *implied* k for each observation and the
   break-even k at which a strategy's net Sharpe crosses a threshold. The output
   is a range, not a point estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


class CalibrationError(ValueError):
    """Raised when calibration inputs are inconsistent."""


@dataclass
class KFit:
    """Least-squares fit of the impact coefficient."""

    k: float
    standard_error: float
    r_squared: float
    n_observations: int
    exponent: float

    @property
    def ci95(self) -> tuple[float, float]:
        return (
            self.k - 1.96 * self.standard_error,
            self.k + 1.96 * self.standard_error,
        )

    def to_dict(self) -> dict[str, float | int]:
        lo, hi = self.ci95
        return {
            "k": self.k,
            "standard_error": self.standard_error,
            "ci95_low": lo,
            "ci95_high": hi,
            "r_squared": self.r_squared,
            "n_observations": self.n_observations,
            "exponent": self.exponent,
        }


def implied_k(
    cost_bps: float,
    sigma_daily: float,
    participation_fraction: float,
    exponent: float = 0.5,
) -> float:
    """Invert the impact model for ``k``.

    ``cost_bps = k * sigma_bps * participation**exponent``. The result is the
    coefficient that would make the model exactly match the observation. It is
    only meaningful if ``cost_bps`` is the *impact* component, not the total
    cost; subtract spread and commission first.
    """
    if cost_bps < 0:
        raise CalibrationError("cost_bps must be non-negative")
    if sigma_daily <= 0:
        raise CalibrationError("sigma_daily must be positive")
    if participation_fraction <= 0:
        raise CalibrationError("participation_fraction must be positive")
    if exponent <= 0:
        raise CalibrationError("exponent must be positive")
    return float(cost_bps / (sigma_daily * 1e4 * participation_fraction**exponent))


def fit_k(
    cost_bps: Iterable[float],
    sigma_daily: Iterable[float],
    participation_fraction: Iterable[float],
    exponent: float = 0.5,
) -> KFit:
    """Fit ``k`` by ordinary least squares through the origin.

    The regressor is ``x = sigma_bps * participation**exponent``. The model is
    ``y = k x + error``. With fewer than two observations the standard error is
    reported as NaN; a single observation is an assumption, not a calibration.
    """
    y = np.asarray(list(cost_bps), dtype=float)
    sigma = np.asarray(list(sigma_daily), dtype=float)
    p = np.asarray(list(participation_fraction), dtype=float)
    if not (len(y) == len(sigma) == len(p)):
        raise CalibrationError("inputs must have the same length")
    if len(y) == 0:
        raise CalibrationError("no observations")
    if (y < 0).any() or (sigma <= 0).any() or (p <= 0).any():
        raise CalibrationError("costs must be non-negative and sigma/participation positive")
    x = sigma * 1e4 * p**exponent
    denominator = float(x @ x)
    if denominator == 0:
        raise CalibrationError("regressor is identically zero")
    k = float(x @ y) / denominator
    residual = y - k * x
    rss = float(residual @ residual)
    tss = float(y @ y)
    r_squared = 1.0 - rss / tss if tss > 0 else float("nan")
    if len(y) > 1:
        variance = rss / (len(y) - 1)
        standard_error = math.sqrt(variance / denominator)
    else:
        standard_error = float("nan")
    return KFit(
        k=k,
        standard_error=standard_error,
        r_squared=r_squared,
        n_observations=len(y),
        exponent=exponent,
    )


def bootstrap_k(
    cost_bps: Iterable[float],
    sigma_daily: Iterable[float],
    participation_fraction: Iterable[float],
    exponent: float = 0.5,
    n_boot: int = 1000,
    seed: int = 20261108,
) -> tuple[float, float, float]:
    """Percentile bootstrap interval for ``k``.

    Returns ``(k, lower_95, upper_95)``. The bootstrap resamples observations; it
    does not create information that the sample lacks. With a small sample the
    interval will be wide, which is the point.
    """
    y = np.asarray(list(cost_bps), dtype=float)
    sigma = np.asarray(list(sigma_daily), dtype=float)
    p = np.asarray(list(participation_fraction), dtype=float)
    if not (len(y) == len(sigma) == len(p)):
        raise CalibrationError("inputs must have the same length")
    if len(y) < 2:
        raise CalibrationError("bootstrap needs at least two observations")
    rng = np.random.default_rng(seed)
    estimates = np.empty(n_boot)
    n = len(y)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        estimates[i] = fit_k(y[idx], sigma[idx], p[idx], exponent=exponent).k
    return (
        fit_k(y, sigma, p, exponent=exponent).k,
        float(np.quantile(estimates, 0.025)),
        float(np.quantile(estimates, 0.975)),
    )


def calibration_table(
    observations: pd.DataFrame,
    *,
    cost_column: str = "cost_bps",
    sigma_column: str = "sigma_daily",
    participation_column: str = "participation",
    exponent: float = 0.5,
) -> pd.DataFrame:
    """Add implied-k and fitted-value columns to an observation table."""
    required = {cost_column, sigma_column, participation_column}
    missing = required - set(observations.columns)
    if missing:
        raise CalibrationError(f"missing columns: {sorted(missing)}")
    table = observations.copy()
    table["implied_k"] = [
        implied_k(c, s, p, exponent)
        for c, s, p in zip(
            table[cost_column], table[sigma_column], table[participation_column]
        )
    ]
    fit = fit_k(
        table[cost_column],
        table[sigma_column],
        table[participation_column],
        exponent=exponent,
    )
    table["fitted_bps"] = (
        fit.k
        * table[sigma_column]
        * 1e4
        * table[participation_column] ** exponent
    )
    table["residual_bps"] = table[cost_column] - table["fitted_bps"]
    return table


def break_even_k_from_costs(
    base_cost_bps: float,
    impact_unit_bps: float,
    threshold_bps: float,
) -> float | None:
    """Analytic break-even for a fixed base cost and unit impact.

    ``base + k * unit = threshold``. Returns ``None`` if the threshold is not
    reachable with a non-negative k.
    """
    if impact_unit_bps <= 0:
        return None
    if threshold_bps < base_cost_bps:
        return 0.0
    return float((threshold_bps - base_cost_bps) / impact_unit_bps)

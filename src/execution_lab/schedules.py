"""Execution schedules: immediate, TWAP, VWAP, and POV.

A schedule is a set of slices. Each slice has three numbers:

``fraction``
    Share of the parent order executed in the slice. Fractions sum to one.
``volume_fraction``
    Share of *one average day's volume* available in the slice. A full day
    contributes 1.0; an intraday bin contributes its share of that day's volume.
    The sum is the number of ADV-days spanned by the schedule (``volume_days``).
``time_days``
    Time of the slice's midpoint, in trading days from arrival. Immediate
    execution is at time zero.

The separation matters. TWAP is equal *time*, not equal volume; VWAP is equal
*volume*, so its participation is constant across slices. With a non-uniform
intraday volume profile, TWAP over-participates in quiet periods and therefore
has higher expected impact than VWAP over the same horizon.

Everything here is deterministic and pre-trade. There is no adaptation to
realised prices or volume, and no order-book model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

import numpy as np


class ScheduleError(ValueError):
    """Raised when a schedule violates its accounting constraints."""


def default_intraday_profile(bins: int = 8) -> np.ndarray:
    """A U-shaped intraday volume profile, normalised to one.

    The profile is a stylised fact, not an estimate from this dataset: ETF
    volume is typically concentrated near the open and close. The exact shape is
    a modelling choice and the demo varies the horizon rather than tuning it.
    """
    if bins < 1:
        raise ValueError("bins must be at least 1")
    x = (np.arange(bins) + 0.5) / bins
    raw = 1.0 + 1.2 * (2.0 * x - 1.0) ** 2
    return raw / raw.sum()


@dataclass
class Schedule:
    """A validated execution schedule."""

    name: str
    fractions: np.ndarray
    volume_fractions: np.ndarray
    times_days: np.ndarray
    horizon_days: float
    metadata: dict[str, float | str | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.fractions = np.asarray(self.fractions, dtype=float)
        self.volume_fractions = np.asarray(self.volume_fractions, dtype=float)
        self.times_days = np.asarray(self.times_days, dtype=float)
        self.horizon_days = float(self.horizon_days)
        self.metadata = dict(self.metadata)

        n = len(self.fractions)
        if n == 0:
            raise ScheduleError("schedule must have at least one slice")
        if len(self.volume_fractions) != n or len(self.times_days) != n:
            raise ScheduleError("schedule arrays must have the same length")
        for name, array in (
            ("fractions", self.fractions),
            ("volume_fractions", self.volume_fractions),
            ("times_days", self.times_days),
        ):
            if not np.all(np.isfinite(array)):
                raise ScheduleError(f"{name} contains non-finite values")
        if (self.fractions <= 0).any():
            raise ScheduleError("fractions must be strictly positive")
        if (self.volume_fractions <= 0).any():
            raise ScheduleError("volume_fractions must be strictly positive")
        if not np.isclose(self.fractions.sum(), 1.0, atol=1e-10):
            raise ScheduleError("fractions must sum to 1")
        if (self.times_days < 0).any():
            raise ScheduleError("times_days must be non-negative")
        if (np.diff(self.times_days) < -1e-12).any():
            raise ScheduleError("times_days must be non-decreasing")
        if self.horizon_days < 0:
            raise ScheduleError("horizon_days must be non-negative")

    @property
    def n_slices(self) -> int:
        return len(self.fractions)

    @property
    def volume_days(self) -> float:
        """Expected volume available, expressed in average daily volumes."""
        return float(self.volume_fractions.sum())

    @property
    def average_participation_multiplier(self) -> float:
        """``Q/ADV`` multiplier for the average slice participation.

        For a schedule with total order ``Q`` and ADV ``V``, the notional-weighted
        average participation is ``Q/V``; individual slices vary with the
        schedule. This property is the simple ``1 / volume_days`` benchmark.
        """
        return 1.0 / self.volume_days if self.volume_days > 0 else float("inf")

    def participation(self, order_shares: float, adv_shares: float) -> np.ndarray:
        """Participation of each slice, as a fraction of that slice's volume."""
        if order_shares <= 0:
            raise ValueError("order_shares must be positive")
        if adv_shares <= 0:
            raise ValueError("adv_shares must be positive")
        return order_shares * self.fractions / (adv_shares * self.volume_fractions)

    def slice_shares(self, order_shares: float) -> np.ndarray:
        """Signed shares executed in each slice for a positive parent order."""
        if order_shares <= 0:
            raise ValueError("order_shares must be positive")
        return order_shares * self.fractions

    def describe(self) -> dict[str, float | str | int]:
        return {
            "name": self.name,
            "slices": self.n_slices,
            "horizon_days": self.horizon_days,
            "volume_days": self.volume_days,
            "max_fraction": float(self.fractions.max()),
            "min_fraction": float(self.fractions.min()),
        }


def immediate(name: str = "immediate") -> Schedule:
    """Cross the spread now. One slice, zero timing risk by construction."""
    return Schedule(
        name=name,
        fractions=np.array([1.0]),
        volume_fractions=np.array([1.0]),
        times_days=np.array([0.0]),
        horizon_days=0.0,
        metadata={"kind": "immediate"},
    )


def twap(
    horizon_days: int = 1,
    bins_per_day: int = 8,
    volume_profile: np.ndarray | None = None,
    name: str | None = None,
) -> Schedule:
    """Time-weighted average price: equal shares per time bin.

    The order is split equally across ``horizon_days * bins_per_day`` slices.
    The volume available in each slice follows the intraday profile, so
    participation is *not* constant when the profile is non-uniform.
    """
    if horizon_days < 1:
        raise ValueError("horizon_days must be at least 1")
    if bins_per_day < 1:
        raise ValueError("bins_per_day must be at least 1")
    profile = (
        default_intraday_profile(bins_per_day)
        if volume_profile is None
        else np.asarray(volume_profile, dtype=float)
    )
    if profile.shape != (bins_per_day,):
        raise ValueError("volume_profile has the wrong length")
    if (profile <= 0).any() or not np.isclose(profile.sum(), 1.0, atol=1e-10):
        raise ValueError("volume_profile must be positive and sum to 1")

    fractions = []
    volumes = []
    times = []
    for day in range(horizon_days):
        for k in range(bins_per_day):
            fractions.append(1.0 / (horizon_days * bins_per_day))
            volumes.append(profile[k])
            times.append(day + (k + 0.5) / bins_per_day)
    return Schedule(
        name=name or f"twap_{horizon_days}d",
        fractions=np.array(fractions),
        volume_fractions=np.array(volumes),
        times_days=np.array(times),
        horizon_days=float(horizon_days),
        metadata={
            "kind": "twap",
            "bins_per_day": bins_per_day,
            "profile": ",".join(f"{v:.6f}" for v in profile),
        },
    )


def vwap(
    horizon_days: int = 1,
    bins_per_day: int = 8,
    volume_profile: np.ndarray | None = None,
    day_weights: np.ndarray | None = None,
    name: str | None = None,
) -> Schedule:
    """Volume-weighted average price: shares proportional to expected volume.

    With ``day_weights`` proportional to expected daily volume, participation is
    constant across every slice. That is the defining property of VWAP and the
    reason it is the impact-efficient schedule for a fixed horizon under a
    concave impact model.
    """
    if horizon_days < 1:
        raise ValueError("horizon_days must be at least 1")
    if bins_per_day < 1:
        raise ValueError("bins_per_day must be at least 1")
    profile = (
        default_intraday_profile(bins_per_day)
        if volume_profile is None
        else np.asarray(volume_profile, dtype=float)
    )
    if profile.shape != (bins_per_day,):
        raise ValueError("volume_profile has the wrong length")
    if (profile <= 0).any() or not np.isclose(profile.sum(), 1.0, atol=1e-10):
        raise ValueError("volume_profile must be positive and sum to 1")

    if day_weights is None:
        day_weights = np.full(horizon_days, 1.0 / horizon_days)
    else:
        day_weights = np.asarray(day_weights, dtype=float)
        if day_weights.shape != (horizon_days,):
            raise ValueError("day_weights has the wrong length")
        if (day_weights <= 0).any() or not np.isclose(
            day_weights.sum(), 1.0, atol=1e-10
        ):
            raise ValueError("day_weights must be positive and sum to 1")

    fractions = []
    volumes = []
    times = []
    for day in range(horizon_days):
        for k in range(bins_per_day):
            fractions.append(day_weights[day] * profile[k])
            # One day's volume is 1 ADV; a horizon day's volume is day_weight
            # times horizon_days ADV when the weights are shares of the horizon.
            volumes.append(day_weights[day] * horizon_days * profile[k])
            times.append(day + (k + 0.5) / bins_per_day)
    return Schedule(
        name=name or f"vwap_{horizon_days}d",
        fractions=np.array(fractions),
        volume_fractions=np.array(volumes),
        times_days=np.array(times),
        horizon_days=float(horizon_days),
        metadata={
            "kind": "vwap",
            "bins_per_day": bins_per_day,
            "profile": ",".join(f"{v:.6f}" for v in profile),
            "day_weights": ",".join(f"{v:.6f}" for v in day_weights),
        },
    )


def pov(
    order_shares: float,
    adv_shares: float,
    participation_rate: float = 0.10,
    bins_per_day: int = 8,
    max_days: int = 20,
    volume_profile: np.ndarray | None = None,
    day_weights: np.ndarray | None = None,
    name: str | None = None,
) -> Schedule:
    """Participation-of-volume schedule.

    The horizon is the shortest integer number of days for which the order is at
    most ``participation_rate`` of expected volume. Within that horizon the
    schedule is VWAP, so participation is constant at the achieved rate. If the
    required horizon exceeds ``max_days`` the schedule is capped and the achieved
    rate is higher than requested; the metadata records both.
    """
    if order_shares <= 0 or adv_shares <= 0:
        raise ValueError("order_shares and adv_shares must be positive")
    if not 0 < participation_rate <= 1:
        raise ValueError("participation_rate must be in (0, 1]")
    if max_days < 1:
        raise ValueError("max_days must be at least 1")

    required_days = int(np.ceil(order_shares / (participation_rate * adv_shares)))
    required_days = max(required_days, 1)
    capped = required_days > max_days
    horizon = min(required_days, max_days)
    actual_rate = order_shares / (adv_shares * horizon)

    base = vwap(
        horizon_days=horizon,
        bins_per_day=bins_per_day,
        volume_profile=volume_profile,
        day_weights=day_weights,
        name=name or f"pov_{int(round(participation_rate * 100))}pct",
    )
    base.metadata.update(
        {
            "kind": "pov",
            "target_participation": float(participation_rate),
            "actual_participation": float(actual_rate),
            "capped": bool(capped),
            "required_days": int(required_days),
        }
    )
    return base


def make_schedule(
    kind: str,
    *,
    order_shares: float | None = None,
    adv_shares: float | None = None,
    horizon_days: int = 1,
    participation_rate: float = 0.10,
    bins_per_day: int = 8,
    max_days: int = 20,
    volume_profile: np.ndarray | None = None,
    day_weights: np.ndarray | None = None,
    name: str | None = None,
) -> Schedule:
    """Factory used by the CLI and the portfolio layer."""
    kind = kind.lower().strip()
    if kind == "immediate":
        return immediate(name=name or "immediate")
    if kind == "twap":
        return twap(
            horizon_days=horizon_days,
            bins_per_day=bins_per_day,
            volume_profile=volume_profile,
            name=name,
        )
    if kind == "vwap":
        return vwap(
            horizon_days=horizon_days,
            bins_per_day=bins_per_day,
            volume_profile=volume_profile,
            day_weights=day_weights,
            name=name,
        )
    if kind == "pov":
        if order_shares is None or adv_shares is None:
            raise ValueError("pov requires order_shares and adv_shares")
        return pov(
            order_shares=order_shares,
            adv_shares=adv_shares,
            participation_rate=participation_rate,
            bins_per_day=bins_per_day,
            max_days=max_days,
            volume_profile=volume_profile,
            day_weights=day_weights,
            name=name,
        )
    raise ValueError(f"unknown schedule kind: {kind}")


def schedule_candidates(
    order_shares: float,
    adv_shares: float,
    horizons: Iterable[int] = (1, 3, 5),
    bins_per_day: int = 8,
    pov_rates: Iterable[float] = (0.05, 0.10, 0.20),
    max_days: int = 20,
    volume_profile: np.ndarray | None = None,
) -> list[Schedule]:
    """A small, pre-declared menu of schedules for comparison.

    The menu is not optimised over a large grid; it is the four families the
    charter asks for, with a few horizons. That keeps the comparison honest and
    the multiple-testing problem small.
    """
    candidates = [immediate()]
    for horizon in horizons:
        candidates.append(
            twap(
                horizon_days=horizon,
                bins_per_day=bins_per_day,
                volume_profile=volume_profile,
            )
        )
        candidates.append(
            vwap(
                horizon_days=horizon,
                bins_per_day=bins_per_day,
                volume_profile=volume_profile,
            )
        )
    for rate in pov_rates:
        candidates.append(
            pov(
                order_shares=order_shares,
                adv_shares=adv_shares,
                participation_rate=rate,
                bins_per_day=bins_per_day,
                max_days=max_days,
                volume_profile=volume_profile,
            )
        )

    # A POV rate at or above the order's participation collapses to one day and
    # is then identical to VWAP 1d. Keep one copy rather than pretending the
    # four families are four independent observations.
    unique: list[Schedule] = []
    seen: set[tuple[bytes, bytes, bytes]] = set()
    for schedule in candidates:
        signature = (
            schedule.fractions.tobytes(),
            schedule.volume_fractions.tobytes(),
            schedule.times_days.tobytes(),
        )
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(schedule)

    # Guard against accidental duplicate names; the menu must be unambiguous.
    names = [s.name for s in unique]
    if len(names) != len(set(names)):
        raise ScheduleError(f"duplicate schedule names: {names}")
    return unique


def schedule_summary(schedules: Iterable[Schedule]) -> list[dict[str, float | str | int]]:
    """Tabular summary used by reports."""
    return [s.describe() for s in schedules]


def profile_from_mapping(mapping: Mapping[int, float], bins: int) -> np.ndarray:
    """Build a normalised profile from ``{bin_index: weight}``; useful in tests."""
    weights = np.zeros(bins, dtype=float)
    for k, value in mapping.items():
        if not 0 <= k < bins:
            raise ValueError(f"bin index out of range: {k}")
        weights[k] = float(value)
    if (weights < 0).any() or weights.sum() <= 0:
        raise ValueError("profile weights must be non-negative and sum positive")
    return weights / weights.sum()

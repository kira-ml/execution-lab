from __future__ import annotations

import numpy as np
import pytest

from execution_lab.schedules import (
    ScheduleError,
    default_intraday_profile,
    immediate,
    make_schedule,
    pov,
    schedule_candidates,
    twap,
    vwap,
)


def test_immediate_properties():
    schedule = immediate()
    assert schedule.n_slices == 1
    assert schedule.fractions.tolist() == [1.0]
    assert schedule.volume_fractions.tolist() == [1.0]
    assert schedule.times_days.tolist() == [0.0]
    assert schedule.horizon_days == 0.0
    assert schedule.volume_days == 1.0


def test_twap_accounting():
    schedule = twap(horizon_days=5)
    assert schedule.n_slices == 40
    assert np.isclose(schedule.fractions.sum(), 1.0)
    assert np.isclose(schedule.volume_days, 5.0)
    assert np.all(schedule.fractions > 0)
    assert np.all(np.diff(schedule.times_days) >= 0)
    assert schedule.times_days[0] == pytest.approx(0.5 / 8)
    assert schedule.times_days[-1] < 5.0


def test_vwap_constant_participation():
    schedule = vwap(horizon_days=5)
    p = schedule.participation(order_shares=100_000, adv_shares=1_000_000)
    assert np.allclose(p, p[0])
    assert p[0] == pytest.approx(0.02)


def test_twap_participation_varies_with_intraday_profile():
    schedule = twap(horizon_days=1)
    p = schedule.participation(order_shares=100_000, adv_shares=1_000_000)
    assert p.max() > p.min()
    assert np.all(p > 0)


def test_pov_target_rate():
    schedule = pov(order_shares=300_000, adv_shares=1_000_000, participation_rate=0.10)
    assert schedule.metadata["actual_participation"] <= 0.10 + 1e-12
    assert schedule.horizon_days == 3
    p = schedule.participation(300_000, 1_000_000)
    assert np.allclose(p, schedule.metadata["actual_participation"])


def test_pov_caps_horizon():
    schedule = pov(
        order_shares=10_000_000,
        adv_shares=100_000,
        participation_rate=0.01,
        max_days=5,
    )
    assert schedule.horizon_days == 5
    assert schedule.metadata["capped"] is True
    assert schedule.metadata["actual_participation"] > 0.01


def test_vwap_day_weights():
    schedule = vwap(horizon_days=2, day_weights=np.array([0.75, 0.25]))
    assert np.isclose(schedule.fractions.sum(), 1.0)
    assert np.isclose(schedule.volume_days, 2.0)
    p = schedule.participation(100_000, 1_000_000)
    assert np.allclose(p, 0.05)


def test_invalid_schedule_rejected():
    with pytest.raises(ScheduleError):
        from execution_lab.schedules import Schedule

        Schedule(
            name="bad",
            fractions=np.array([0.5, 0.4]),
            volume_fractions=np.array([1.0, 1.0]),
            times_days=np.array([0.0, 1.0]),
            horizon_days=2.0,
        )


def test_candidates_have_unique_signatures():
    schedules = schedule_candidates(order_shares=200_000, adv_shares=1_000_000)
    names = [s.name for s in schedules]
    assert len(names) == len(set(names))
    signatures = {
        (s.fractions.tobytes(), s.volume_fractions.tobytes(), s.times_days.tobytes())
        for s in schedules
    }
    assert len(signatures) == len(schedules)
    families = {s.metadata.get("kind") for s in schedules}
    assert {"immediate", "twap", "vwap", "pov"} <= families


def test_make_schedule_factory():
    assert make_schedule("immediate").name == "immediate"
    assert make_schedule("twap", horizon_days=2).name == "twap_2d"
    assert make_schedule("vwap", horizon_days=2).name == "vwap_2d"
    assert (
        make_schedule(
            "pov", order_shares=100_000, adv_shares=1_000_000, participation_rate=0.05
        ).name
        == "pov_5pct"
    )
    with pytest.raises(ValueError):
        make_schedule("unknown")


def test_profile_normalised():
    for bins in (1, 2, 8, 13):
        profile = default_intraday_profile(bins)
        assert len(profile) == bins
        assert np.isclose(profile.sum(), 1.0)
        assert np.all(profile > 0)

from __future__ import annotations

import pytest

from execution_lab.config import CostConfig
from execution_lab.schedules import immediate, pov, twap, vwap
from execution_lab.simulator import SimulationError, compare_schedules, simulate_order

MARKET = dict(
    ticker="TEST",
    price=100.0,
    adv_shares=1_000_000.0,
    sigma_daily=0.01,
    spread_bps=4.0,
)


def _run(shares=100_000.0, schedule=None, **config_kwargs):
    config = CostConfig(**config_kwargs)
    return simulate_order(
        shares=shares,
        schedule=schedule or vwap(horizon_days=5),
        config=config,
        **MARKET,
    )


def test_decomposition_adds_up():
    result = _run()
    expected = (
        result.half_spread_bps + result.commission_bps + result.impact_bps
    )
    assert result.expected_cost_bps == pytest.approx(expected)
    assert result.expected_cost_dollars == pytest.approx(
        result.expected_cost_bps / 1e4 * result.notional
    )
    assert result.slices["cost_dollars"].sum() == pytest.approx(
        result.expected_cost_dollars, rel=1e-9
    )
    assert result.slices["shares"].sum() == pytest.approx(result.shares)


def test_immediate_has_zero_timing_risk():
    result = _run(schedule=immediate())
    assert result.timing_risk_bps == 0.0
    assert result.timing_risk_dollars == 0.0
    assert result.objective_bps == pytest.approx(result.expected_cost_bps)


def test_longer_horizon_has_more_timing_risk():
    one = _run(schedule=vwap(horizon_days=1))
    five = _run(schedule=vwap(horizon_days=5))
    assert five.timing_risk_bps > one.timing_risk_bps > 0


def test_spreading_reduces_impact():
    one = _run(schedule=vwap(horizon_days=1))
    five = _run(schedule=vwap(horizon_days=5))
    assert five.impact_bps < one.impact_bps


def test_vwap_has_lower_impact_than_twap_same_horizon():
    twap_result = _run(schedule=twap(horizon_days=5))
    vwap_result = _run(schedule=vwap(horizon_days=5))
    assert vwap_result.impact_bps < twap_result.impact_bps
    assert twap_result.timing_risk_bps != vwap_result.timing_risk_bps


def test_total_mode_is_schedule_independent_for_same_horizon():
    twap_result = _run(schedule=twap(horizon_days=5), impact_mode="total")
    vwap_result = _run(schedule=vwap(horizon_days=5), impact_mode="total")
    assert twap_result.impact_bps == pytest.approx(vwap_result.impact_bps)


def test_sell_is_symmetric():
    buy = _run(shares=100_000)
    sell = _run(shares=-100_000)
    assert sell.side == "sell"
    assert sell.expected_cost_bps == pytest.approx(buy.expected_cost_bps)
    assert sell.notional == pytest.approx(buy.notional)


def test_impact_increases_with_order_size():
    small = _run(shares=10_000, schedule=immediate())
    large = _run(shares=100_000, schedule=immediate())
    assert large.impact_bps > small.impact_bps


def test_impact_increases_with_k():
    low = _run(impact_k=0.1)
    high = _run(impact_k=1.0)
    assert high.impact_bps > low.impact_bps


def test_var_and_cvar_exceed_expected_when_risk_positive():
    result = _run(schedule=vwap(horizon_days=5))
    assert result.var95_bps > result.expected_cost_bps
    assert result.cvar95_bps > result.var95_bps


def test_objective_includes_risk_aversion():
    result = _run(schedule=vwap(horizon_days=5), risk_aversion=0.2)
    assert result.objective_bps == pytest.approx(
        result.expected_cost_bps + 0.2 * result.timing_risk_bps
    )


def test_participation_warning():
    result = _run(shares=300_000, schedule=immediate(), participation_cap=0.25)
    assert result.participation == pytest.approx(0.3)
    assert result.participation_warning is True


def test_invalid_order_rejected():
    with pytest.raises(SimulationError):
        simulate_order(
            ticker="TEST",
            shares=0.0,
            price=100.0,
            adv_shares=1_000_000,
            sigma_daily=0.01,
            spread_bps=4.0,
            schedule=immediate(),
        )
    with pytest.raises(SimulationError):
        simulate_order(
            ticker="TEST",
            shares=100.0,
            price=0.0,
            adv_shares=1_000_000,
            sigma_daily=0.01,
            spread_bps=4.0,
            schedule=immediate(),
        )


def test_compare_schedules_sorted_by_objective():
    schedules = [immediate(), twap(horizon_days=3), vwap(horizon_days=3), pov(100_000, 1_000_000)]
    table = compare_schedules(schedules=schedules, shares=100_000, **MARKET)
    assert list(table["objective_bps"]) == sorted(table["objective_bps"])
    assert list(table["objective_rank"]) == list(range(1, len(table) + 1))

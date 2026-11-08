from __future__ import annotations

import math

import pytest

from execution_lab.costs import (
    bps_from_dollars,
    dollars_from_bps,
    half_spread_bps,
    impact_bps,
    linear_cost_bps,
    normal_cvar_multiplier,
    normal_var_multiplier,
    participation,
    total_expected_cost_bps,
)


def test_half_spread():
    assert half_spread_bps(10.0) == 5.0
    with pytest.raises(ValueError):
        half_spread_bps(-1.0)


def test_participation():
    assert participation(100, 1000) == 0.1
    assert participation(-100, 1000) == 0.1
    with pytest.raises(ValueError):
        participation(100, 0)


def test_impact_monotonic_in_participation():
    values = [impact_bps(p, 0.01, 0.5) for p in (0.001, 0.01, 0.1, 0.3)]
    assert values == sorted(values)
    assert values[0] > 0


def test_impact_monotonic_in_sigma():
    values = [impact_bps(0.1, s, 0.5) for s in (0.005, 0.01, 0.02, 0.04)]
    assert values == sorted(values)


def test_impact_monotonic_in_k():
    values = [impact_bps(0.1, 0.01, k) for k in (0.0, 0.1, 0.5, 1.0, 2.0)]
    assert values == sorted(values)
    assert values[0] == 0.0


def test_impact_linear_exponent():
    a = impact_bps(0.1, 0.01, 0.5, exponent=1.0)
    b = impact_bps(0.2, 0.01, 0.5, exponent=1.0)
    assert b == pytest.approx(2.0 * a)
    c = impact_bps(0.1, 0.02, 0.5, exponent=1.0)
    assert c == pytest.approx(2.0 * a)


def test_impact_square_root_shape():
    a = impact_bps(0.01, 0.01, 0.5, exponent=0.5)
    b = impact_bps(0.04, 0.01, 0.5, exponent=0.5)
    assert b == pytest.approx(2.0 * a)


def test_linear_cost():
    assert linear_cost_bps(10.0, 0.5) == 5.5
    with pytest.raises(ValueError):
        linear_cost_bps(10.0, -1.0)


def test_total_cost_additive():
    spread = 10.0
    commission = 0.5
    impact = 3.0
    total = total_expected_cost_bps(spread, commission, impact)
    assert total == pytest.approx(5.0 + 0.5 + 3.0)


def test_dollar_conversion_roundtrip():
    assert dollars_from_bps(10.0, 1_000_000) == 1000.0
    assert bps_from_dollars(1000.0, 1_000_000) == 10.0
    with pytest.raises(ValueError):
        bps_from_dollars(1.0, 0.0)


def test_normal_multipliers():
    assert normal_var_multiplier(0.95) == pytest.approx(1.6448536, rel=1e-6)
    assert normal_cvar_multiplier(0.95) == pytest.approx(2.0627, rel=1e-3)
    assert math.isfinite(normal_cvar_multiplier(0.99))
    with pytest.raises(ValueError):
        normal_var_multiplier(1.0)

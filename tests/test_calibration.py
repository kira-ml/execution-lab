from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from execution_lab.calibration import (
    CalibrationError,
    bootstrap_k,
    break_even_k_from_costs,
    calibration_table,
    fit_k,
    implied_k,
)


def test_implied_k_roundtrip():
    k = implied_k(cost_bps=10.0, sigma_daily=0.01, participation_fraction=0.04)
    assert k == pytest.approx(10.0 / (100.0 * 0.2))


def test_fit_k_recovers_known_coefficient():
    rng = np.random.default_rng(7)
    sigma = rng.uniform(0.005, 0.03, size=100)
    p = rng.uniform(0.001, 0.2, size=100)
    y = 0.7 * sigma * 1e4 * np.sqrt(p)
    fit = fit_k(y, sigma, p)
    assert fit.k == pytest.approx(0.7)
    assert fit.r_squared == pytest.approx(1.0)
    assert fit.n_observations == 100


def test_fit_k_reports_uncertainty_with_noise():
    rng = np.random.default_rng(8)
    sigma = rng.uniform(0.005, 0.03, size=200)
    p = rng.uniform(0.001, 0.2, size=200)
    y = 0.5 * sigma * 1e4 * np.sqrt(p) + rng.normal(0, 1.0, size=200)
    fit = fit_k(y, sigma, p)
    assert fit.standard_error > 0
    assert fit.ci95[0] < fit.k < fit.ci95[1]


def test_fit_k_rejects_bad_inputs():
    with pytest.raises(CalibrationError):
        fit_k([], [], [])
    with pytest.raises(CalibrationError):
        fit_k([1.0], [0.0], [0.1])


def test_bootstrap_interval():
    rng = np.random.default_rng(9)
    sigma = rng.uniform(0.005, 0.03, size=80)
    p = rng.uniform(0.001, 0.2, size=80)
    y = 0.6 * sigma * 1e4 * np.sqrt(p) + rng.normal(0, 0.5, size=80)
    k, lo, hi = bootstrap_k(y, sigma, p, n_boot=200)
    assert lo <= k <= hi


def test_calibration_table():
    frame = pd.DataFrame(
        {
            "cost_bps": [5.0, 10.0, 20.0],
            "sigma_daily": [0.01, 0.01, 0.01],
            "participation": [0.01, 0.04, 0.16],
        }
    )
    table = calibration_table(frame)
    assert "implied_k" in table
    assert "fitted_bps" in table
    assert np.allclose(table["implied_k"], table["implied_k"].iloc[0])
    assert np.allclose(table["residual_bps"], 0.0)


def test_break_even_k_from_costs():
    assert break_even_k_from_costs(5.0, 2.0, 11.0) == pytest.approx(3.0)
    assert break_even_k_from_costs(5.0, 0.0, 11.0) is None
    assert break_even_k_from_costs(5.0, 2.0, 1.0) == 0.0

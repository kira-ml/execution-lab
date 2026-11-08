from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from execution_lab.data import (
    DataError,
    Panel,
    compute_market_state,
    corwin_schultz_spread_bps,
    default_demo_data_path,
    load_panel_csv,
    make_synthetic_panel,
    save_panel_csv,
)


def test_panel_shapes_and_tickers(panel):
    assert panel.close.shape == (520, 6)
    assert panel.tickers == ["SPY", "TLT", "GLD", "EEM", "HYG", "VNQ"]
    assert panel.spread_bps is not None
    assert panel.close.index.is_monotonic_increasing


def test_save_load_roundtrip(panel, tmp_path):
    path = tmp_path / "panel.csv"
    save_panel_csv(panel, path)
    loaded = load_panel_csv(path)
    assert loaded.tickers == panel.tickers
    assert loaded.close.index.equals(panel.close.index)
    assert np.allclose(loaded.close.to_numpy(), panel.close.to_numpy(), equal_nan=True)
    assert np.allclose(loaded.volume.to_numpy(), panel.volume.to_numpy(), equal_nan=True)
    assert loaded.content_hash() == panel.content_hash()


def test_validation_rejects_negative_price(panel):
    close = panel.close.copy()
    close.iloc[3, 2] = -1.0
    with pytest.raises(DataError, match="negative"):
        Panel(
            close=close,
            high=panel.high,
            low=panel.low,
            open=panel.open,
            volume=panel.volume,
            spread_bps=panel.spread_bps,
        )


def test_validation_rejects_high_below_low(panel):
    high = panel.high.copy()
    low = panel.low.copy()
    high.iloc[5, 0] = low.iloc[5, 0] - 1.0
    with pytest.raises(DataError, match="high < low"):
        Panel(
            close=panel.close,
            high=high,
            low=low,
            open=panel.open,
            volume=panel.volume,
            spread_bps=panel.spread_bps,
        )


def test_load_rejects_missing_column(panel, tmp_path):
    long = panel.to_long().drop(columns=["volume"])
    path = tmp_path / "bad.csv"
    long.to_csv(path, index=False)
    with pytest.raises(DataError, match="missing columns"):
        load_panel_csv(path)


def test_market_state_is_point_in_time(panel):
    asof = panel.close.index[400]
    full = compute_market_state(panel, asof)
    truncated = compute_market_state(panel.slice_until(asof), asof)
    pd.testing.assert_series_equal(full.price, truncated.price)
    pd.testing.assert_series_equal(full.adv_shares, truncated.adv_shares)
    pd.testing.assert_series_equal(full.sigma_daily, truncated.sigma_daily)
    pd.testing.assert_series_equal(full.spread_bps, truncated.spread_bps)


def test_spread_multiplier_scales_the_proxy(panel):
    from execution_lab.config import MarketConfig

    asof = panel.close.index[-1]
    base = compute_market_state(panel, asof, MarketConfig())
    doubled = compute_market_state(panel, asof, MarketConfig(spread_multiplier=2.0))
    expected = (base.spread_bps * 2.0).clip(1.0, 100.0)
    pd.testing.assert_series_equal(doubled.spread_bps, expected, check_names=False)


def test_market_state_uses_trailing_windows(panel):
    asof = panel.close.index[-1]
    state = compute_market_state(panel, asof)
    expected_adv = panel.volume.tail(20).mean()
    pd.testing.assert_series_equal(state.adv_shares, expected_adv, check_names=False)
    expected_sigma = panel.close.pct_change(fill_method=None).tail(20).std(ddof=1)
    pd.testing.assert_series_equal(state.sigma_daily, expected_sigma, check_names=False)


def test_synthetic_panel_deterministic():
    a = make_synthetic_panel(periods=200, start="2021-01-04")
    b = make_synthetic_panel(periods=200, start="2021-01-04")
    c = make_synthetic_panel(periods=200, start="2021-01-04", seed=1)
    assert a.content_hash() == b.content_hash()
    assert a.content_hash() != c.content_hash()


def test_default_demo_data_path_exists():
    path = default_demo_data_path()
    assert path.exists()
    assert path.name == "etf_daily.csv"


def test_corwin_schultz_positive(panel):
    no_spread = Panel(
        close=panel.close,
        high=panel.high,
        low=panel.low,
        open=panel.open,
        volume=panel.volume,
        spread_bps=None,
    )
    spread = corwin_schultz_spread_bps(no_spread)
    assert spread.shape == panel.close.shape
    assert np.nanmedian(spread.to_numpy()) > 0
    assert np.nanmax(spread.to_numpy()) < 1000

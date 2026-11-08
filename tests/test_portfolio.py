from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from execution_lab.portfolio import (
    CostModel,
    PortfolioError,
    apply_cost_model,
    break_even_k,
    linear_cost_components,
    load_weights_csv,
    net_pv_at_k,
    run_backtest,
    run_ranking_experiment,
    strategy_weights,
    target_trades,
)


@pytest.mark.parametrize(
    "strategy",
    ["equal_weight", "inverse_vol", "min_variance", "momentum", "sixty_forty"],
)
def test_strategy_weights_are_long_only_and_sum_to_one(panel, strategy):
    weights = strategy_weights(strategy, panel.close)
    assert np.isclose(weights.sum(), 1.0)
    assert (weights >= 0).all()
    assert set(weights.index) == set(panel.tickers)


def test_min_variance_respects_cap(panel):
    weights = strategy_weights("min_variance", panel.close)
    assert weights.max() <= 0.60 + 1e-8


def test_sixty_forty(panel):
    weights = strategy_weights("sixty_forty", panel.close)
    assert weights["SPY"] == pytest.approx(0.60)
    assert weights["TLT"] == pytest.approx(0.40)


def test_sixty_forty_resolves_tickers_by_name(panel):
    reordered = panel.close[["EEM", "SPY", "TLT", "GLD", "HYG", "VNQ"]]
    weights = strategy_weights("sixty_forty", reordered)
    assert weights["SPY"] == pytest.approx(0.60)
    assert weights["TLT"] == pytest.approx(0.40)
    assert weights["EEM"] == 0.0


def test_run_backtest_gross_value(panel):
    start = panel.close.index[300]
    end = panel.close.index[-1]
    backtest = run_backtest(panel, "equal_weight", start=start, end=end, portfolio_value=10e6)
    assert backtest.strategy == "equal_weight"
    assert len(backtest.rebalances) >= 3
    assert backtest.pv.iloc[0] == pytest.approx(10e6)
    assert backtest.pv.index[0] == start
    assert backtest.pv.index[-1] == end


def test_backtest_is_point_in_time(panel):
    start = panel.close.index[300]
    end = panel.close.index[400]
    full = run_backtest(panel, "momentum", start=start, end=end, portfolio_value=10e6)
    truncated = panel.slice_until(end)
    part = run_backtest(truncated, "momentum", start=start, end=end, portfolio_value=10e6)
    assert full.pv.equals(part.pv)
    assert len(full.rebalances) == len(part.rebalances)


def test_fixed_cost_reduces_net_value(panel):
    start = panel.close.index[300]
    end = panel.close.index[-1]
    backtest = run_backtest(panel, "equal_weight", start=start, end=end, portfolio_value=10e6)
    gross = apply_cost_model(backtest, CostModel("gross", "gross"))
    fixed = apply_cost_model(backtest, CostModel("fixed", "fixed", fixed_bps=10.0))
    assert fixed.net_pv.iloc[-1] < gross.net_pv.iloc[-1]
    assert fixed.summary["cost_drag_bps"] > 0
    assert fixed.summary["turnover"] > 0


def test_linear_decomposition_matches_direct_cost(panel):
    start = panel.close.index[300]
    end = panel.close.index[-1]
    backtest = run_backtest(panel, "equal_weight", start=start, end=end, portfolio_value=10e6)
    model = CostModel("impact", "impact", schedule="vwap_5d", impact_k=1.0)
    cost0, cost1 = linear_cost_components(backtest, model)
    direct = apply_cost_model(backtest, model).net_pv
    reconstructed = net_pv_at_k(backtest, cost0, cost1, 1.0)
    assert np.allclose(direct.to_numpy(), reconstructed.to_numpy(), rtol=1e-10, atol=1e-4)


def test_ranking_table(panel):
    start = panel.close.index[300]
    end = panel.close.index[-1]
    models = [
        CostModel("gross", "gross"),
        CostModel("fixed", "fixed", fixed_bps=10.0),
        CostModel("linear", "linear"),
    ]
    result = run_ranking_experiment(
        panel,
        ["equal_weight", "min_variance"],
        models,
        start=start,
        end=end,
        portfolio_value=10e6,
    )
    assert len(result.table) == 6
    for model in ("gross", "fixed", "linear"):
        subset = result.table[result.table["model"] == model]
        assert sorted(subset["rank"].tolist()) == [1, 2]
    assert result.sharpes().shape == (2, 3)
    assert not result.decomposition().empty


def test_break_even_k_is_inside_bracket(panel):
    start = panel.close.index[300]
    end = panel.close.index[-1]
    backtest = run_backtest(panel, "equal_weight", start=start, end=end, portfolio_value=50e6)
    model = CostModel("impact", "impact", schedule="vwap_5d", impact_k=0.5)
    fixed = apply_cost_model(backtest, CostModel("fixed", "fixed", fixed_bps=10.0))
    k = break_even_k(backtest, model, target_sharpe=fixed.summary["sharpe"])
    if k is not None:
        assert 0.0 <= k <= 10.0


def test_target_trades_sum_to_zero(panel):
    weights = strategy_weights("equal_weight", panel.close)
    current = weights.copy()
    current["SPY"] += 0.05
    current["TLT"] -= 0.05
    prices = panel.close.iloc[-1]
    trades = target_trades(current, weights, prices, 10e6)
    assert abs(float(trades.sum())) < 1e-6


def test_load_weights_long_and_wide(tmp_path):
    long_path = tmp_path / "long.csv"
    pd.DataFrame({"ticker": ["A", "B"], "weight": [0.6, 0.4]}).to_csv(long_path, index=False)
    long = load_weights_csv(long_path)
    assert long.to_dict() == {"A": 0.6, "B": 0.4}

    wide_path = tmp_path / "wide.csv"
    pd.DataFrame({"date": ["2024-01-31"], "A": [0.5], "B": [0.5]}).to_csv(wide_path, index=False)
    wide = load_weights_csv(wide_path)
    assert wide.to_dict() == {"A": 0.5, "B": 0.5}


def test_load_weights_rejects_bad_sum(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"ticker": ["A", "B"], "weight": [0.6, 0.6]}).to_csv(path, index=False)
    with pytest.raises(PortfolioError):
        load_weights_csv(path)


def test_bad_window_rejected(panel):
    with pytest.raises(PortfolioError):
        run_backtest(
            panel,
            "equal_weight",
            start=panel.close.index[-1],
            end=panel.close.index[-2],
        )

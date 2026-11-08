"""Portfolio integration: weights, rebalances, cost models, and ranking.

The unit of analysis is a rebalance record: the trades needed to move from the
current book to a target book, together with the point-in-time market state used
to price them. A backtest records those trades once; cost models are then applied
to the same records. That separation is what makes the ranking comparison fair:
every cost model sees exactly the same trade list and the same gross return path.

Look-ahead conventions
----------------------
* Target weights at rebalance date ``d`` use prices through the *previous*
  trading day.
* The execution price is the close of ``d``.
* ADV, volatility, and spread are measured through the previous trading day, so
  the execution day's volume is not used to size the order.
* Gross returns are close-to-close. Costs are deducted in dollars on the
  rebalance date and compound thereafter.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .config import CostConfig, MarketConfig
from .costs import half_spread_bps
from .data import Panel, compute_market_state
from .schedules import Schedule, make_schedule, schedule_candidates
from .simulator import ExecutionResult, choose_schedule, simulate_order


class PortfolioError(ValueError):
    """Raised when a portfolio input is inconsistent."""


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


@dataclass
class Trade:
    """One ticker's child order inside a rebalance."""

    ticker: str
    shares: float
    price: float
    adv_shares: float
    sigma_daily: float
    spread_bps: float

    @property
    def side(self) -> str:
        return "buy" if self.shares > 0 else "sell"

    @property
    def notional(self) -> float:
        return abs(self.shares) * self.price


@dataclass
class RebalanceRecord:
    """Trades and market state at one rebalance date."""

    date: pd.Timestamp
    pv_pre: float
    current_weights: pd.Series
    target_weights: pd.Series
    trades: list[Trade] = field(default_factory=list)

    @property
    def traded_notional(self) -> float:
        return float(sum(t.notional for t in self.trades))

    @property
    def one_way_turnover(self) -> float:
        return self.traded_notional / (2.0 * self.pv_pre) if self.pv_pre > 0 else 0.0


@dataclass
class Backtest:
    """Gross, buy-and-hold backtest of a target-weight strategy."""

    strategy: str
    dates: pd.DatetimeIndex
    pv: pd.Series
    rebalances: list[RebalanceRecord]

    @property
    def returns(self) -> pd.Series:
        return self.pv.pct_change().dropna()

    @property
    def years(self) -> float:
        return len(self.dates) / 252.0

    def summary(self) -> dict[str, float]:
        return performance_summary(self.returns, self.pv, self.rebalances, 0.0)


@dataclass
class TradeCost:
    """Cost of one child order under one model."""

    ticker: str
    side: str
    shares: float
    notional: float
    schedule: str
    spread_bps: float
    commission_bps: float
    impact_bps: float
    expected_bps: float
    timing_risk_bps: float
    dollars: float


@dataclass
class RebalanceCost:
    """Cost of one rebalance under one model."""

    date: pd.Timestamp
    pv_pre: float
    total_cost: float
    cost_bps: float
    trades: list[TradeCost] = field(default_factory=list)


@dataclass
class CostedBacktest:
    """A gross backtest with one cost model applied."""

    strategy: str
    model: str
    gross_pv: pd.Series
    net_pv: pd.Series
    gross_returns: pd.Series
    net_returns: pd.Series
    costs: list[RebalanceCost]
    rebalances: list[RebalanceRecord] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, float]:
        total_cost = float(sum(c.total_cost for c in self.costs))
        return performance_summary(
            self.net_returns,
            self.net_pv,
            self.rebalances,
            total_cost,
        )

    def cost_table(self) -> pd.DataFrame:
        rows = []
        for cost in self.costs:
            for trade in cost.trades:
                rows.append(
                    {
                        "date": cost.date,
                        "ticker": trade.ticker,
                        "side": trade.side,
                        "shares": trade.shares,
                        "notional": trade.notional,
                        "schedule": trade.schedule,
                        "spread_bps": trade.spread_bps,
                        "commission_bps": trade.commission_bps,
                        "impact_bps": trade.impact_bps,
                        "expected_bps": trade.expected_bps,
                        "timing_risk_bps": trade.timing_risk_bps,
                        "cost_dollars": trade.dollars,
                    }
                )
        return pd.DataFrame(rows)


@dataclass
class RankingResult:
    """Table and artefacts from a strategy-ranking experiment."""

    table: pd.DataFrame
    backtests: dict[str, Backtest]
    costed: dict[tuple[str, str], CostedBacktest]

    def ranks(self) -> pd.DataFrame:
        return self.table.pivot(index="strategy", columns="model", values="rank")

    def sharpes(self) -> pd.DataFrame:
        return self.table.pivot(index="strategy", columns="model", values="sharpe")

    def decomposition(self) -> pd.DataFrame:
        rows = []
        for (strategy, model), result in self.costed.items():
            table = result.cost_table()
            if table.empty:
                continue
            notional = table["notional"].sum()
            rows.append(
                {
                    "strategy": strategy,
                    "model": model,
                    "weighted_spread_bps": float(
                        (table["spread_bps"] * table["notional"]).sum() / notional
                    ),
                    "weighted_commission_bps": float(
                        (table["commission_bps"] * table["notional"]).sum() / notional
                    ),
                    "weighted_impact_bps": float(
                        (table["impact_bps"] * table["notional"]).sum() / notional
                    ),
                    "weighted_expected_bps": float(
                        (table["expected_bps"] * table["notional"]).sum() / notional
                    ),
                    "weighted_timing_risk_bps": float(
                        (table["timing_risk_bps"] * table["notional"]).sum() / notional
                    ),
                }
            )
        return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Cost models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CostModel:
    """A named cost assumption.

    ``kind`` is one of ``gross``, ``fixed``, ``linear``, ``impact``, ``optimal``.
    ``schedule`` is parsed for impact models: ``immediate``, ``twap_<n>d``,
    ``vwap_<n>d``, or ``pov_<n>pct``. ``optimal`` chooses from the pre-declared
    schedule menu per trade using the config's risk aversion.
    """

    name: str
    kind: str
    fixed_bps: float = 0.0
    schedule: str = "vwap_5d"
    impact_k: float | None = None
    risk_aversion: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"gross", "fixed", "linear", "impact", "optimal"}:
            raise PortfolioError(f"unknown cost model kind: {self.kind}")
        if self.fixed_bps < 0:
            raise PortfolioError("fixed_bps must be non-negative")
        if self.impact_k is not None and self.impact_k < 0:
            raise PortfolioError("impact_k must be non-negative")
        if self.risk_aversion is not None and self.risk_aversion < 0:
            raise PortfolioError("risk_aversion must be non-negative")

    def resolved_config(self, config: CostConfig) -> CostConfig:
        overrides = {}
        if self.impact_k is not None:
            overrides["impact_k"] = self.impact_k
        if self.risk_aversion is not None:
            overrides["risk_aversion"] = self.risk_aversion
        return config.with_overrides(**overrides) if overrides else config


def _parse_schedule_spec(spec: str) -> tuple[str, int | float]:
    spec = spec.lower().strip()
    if spec == "immediate":
        return "immediate", 0
    match = re.fullmatch(r"(twap|vwap)_(\d+)d", spec)
    if match:
        return match.group(1), int(match.group(2))
    match = re.fullmatch(r"pov_(\d+)pct", spec)
    if match:
        return "pov", int(match.group(1)) / 100.0
    raise PortfolioError(f"cannot parse schedule spec: {spec}")


def _schedule_for_trade(
    trade: Trade,
    spec: str,
    config: CostConfig,
) -> Schedule:
    kind, value = _parse_schedule_spec(spec)
    if kind == "immediate":
        return make_schedule("immediate")
    if kind in {"twap", "vwap"}:
        return make_schedule(kind, horizon_days=int(value))
    if kind == "pov":
        return make_schedule(
            "pov",
            order_shares=abs(trade.shares),
            adv_shares=trade.adv_shares,
            participation_rate=float(value),
        )
    raise PortfolioError(f"unsupported schedule: {spec}")


def _linear_trade_cost(trade: Trade, config: CostConfig) -> TradeCost:
    spread_cost = half_spread_bps(trade.spread_bps)
    expected = spread_cost + config.commission_bps
    return TradeCost(
        ticker=trade.ticker,
        side=trade.side,
        shares=trade.shares,
        notional=trade.notional,
        schedule="linear",
        spread_bps=spread_cost,
        commission_bps=config.commission_bps,
        impact_bps=0.0,
        expected_bps=expected,
        timing_risk_bps=0.0,
        dollars=expected / 1e4 * trade.notional,
    )


def _trade_cost(
    trade: Trade,
    model: CostModel,
    config: CostConfig,
) -> tuple[TradeCost, ExecutionResult | None]:
    cfg = model.resolved_config(config)
    if model.kind == "gross":
        return (
            TradeCost(
                ticker=trade.ticker,
                side=trade.side,
                shares=trade.shares,
                notional=trade.notional,
                schedule="gross",
                spread_bps=0.0,
                commission_bps=0.0,
                impact_bps=0.0,
                expected_bps=0.0,
                timing_risk_bps=0.0,
                dollars=0.0,
            ),
            None,
        )
    if model.kind == "fixed":
        return (
            TradeCost(
                ticker=trade.ticker,
                side=trade.side,
                shares=trade.shares,
                notional=trade.notional,
                schedule=f"fixed_{model.fixed_bps:g}bps",
                spread_bps=model.fixed_bps,
                commission_bps=0.0,
                impact_bps=0.0,
                expected_bps=model.fixed_bps,
                timing_risk_bps=0.0,
                dollars=model.fixed_bps / 1e4 * trade.notional,
            ),
            None,
        )
    if model.kind == "linear":
        return _linear_trade_cost(trade, cfg), None

    common = dict(
        ticker=trade.ticker,
        shares=trade.shares,
        price=trade.price,
        adv_shares=trade.adv_shares,
        sigma_daily=trade.sigma_daily,
        spread_bps=trade.spread_bps,
        config=cfg,
    )
    if model.kind == "impact":
        schedule = _schedule_for_trade(trade, model.schedule, cfg)
        result = simulate_order(schedule=schedule, **common)
    elif model.kind == "optimal":
        candidates = schedule_candidates(
            abs(trade.shares),
            trade.adv_shares,
            horizons=(1, 3, 5),
            pov_rates=(0.05, 0.10, 0.20),
        )
        result, _ = choose_schedule(schedules=candidates, **common)
    else:  # pragma: no cover - guarded by CostModel
        raise PortfolioError(f"unsupported cost model kind: {model.kind}")

    return (
        TradeCost(
            ticker=trade.ticker,
            side=trade.side,
            shares=trade.shares,
            notional=trade.notional,
            schedule=result.schedule,
            spread_bps=result.half_spread_bps,
            commission_bps=result.commission_bps,
            impact_bps=result.impact_bps,
            expected_bps=result.expected_cost_bps,
            timing_risk_bps=result.timing_risk_bps,
            dollars=result.expected_cost_dollars,
        ),
        result,
    )


def rebalance_cost(
    record: RebalanceRecord,
    model: CostModel,
    config: CostConfig,
) -> RebalanceCost:
    """Apply a cost model to one rebalance record."""
    trades = [_trade_cost(trade, model, config)[0] for trade in record.trades]
    total = float(sum(t.dollars for t in trades))
    return RebalanceCost(
        date=record.date,
        pv_pre=record.pv_pre,
        total_cost=total,
        cost_bps=total / record.pv_pre * 1e4 if record.pv_pre > 0 else 0.0,
        trades=trades,
    )


# --------------------------------------------------------------------------- #
# Performance
# --------------------------------------------------------------------------- #


def performance_summary(
    returns: pd.Series,
    pv: pd.Series,
    rebalances: Sequence[RebalanceRecord],
    total_cost: float,
) -> dict[str, float]:
    """Annualised performance and cost metrics."""
    returns = returns.dropna()
    pv = pv.dropna()
    n = len(returns)
    if n < 2 or len(pv) < 2:
        raise PortfolioError("not enough observations to summarise performance")
    years = n / 252.0
    growth = float((1.0 + returns).prod())
    annual_return = growth ** (1.0 / years) - 1.0
    vol = float(returns.std(ddof=1) * math.sqrt(252.0))
    sharpe = float(returns.mean() / returns.std(ddof=1) * math.sqrt(252.0))
    drawdown = float((pv / pv.cummax() - 1.0).min())
    traded = float(sum(r.traded_notional for r in rebalances))
    mean_pv = float(pv.mean())
    turnover = traded / (2.0 * mean_pv) / years if mean_pv > 0 else 0.0
    cost_drag_bps = total_cost / mean_pv / years * 1e4 if mean_pv > 0 else 0.0
    avg_cost_bps = total_cost / traded * 1e4 if traded > 0 else 0.0
    return {
        "annual_return": annual_return,
        "annual_vol": vol,
        "sharpe": sharpe,
        "max_drawdown": drawdown,
        "turnover": turnover,
        "cost_drag_bps": cost_drag_bps,
        "avg_cost_bps": avg_cost_bps,
        "total_cost": total_cost,
        "n_days": float(n),
        "years": years,
        "ending_value": float(pv.iloc[-1]),
    }


# --------------------------------------------------------------------------- #
# Strategy weights
# --------------------------------------------------------------------------- #


def _normalise(weights: pd.Series) -> pd.Series:
    weights = weights.clip(lower=0.0)
    total = float(weights.sum())
    if not np.isfinite(total) or total <= 0:
        return pd.Series(1.0 / len(weights), index=weights.index)
    return weights / total


def equal_weight(prices: pd.DataFrame, **_: object) -> pd.Series:
    return pd.Series(1.0 / prices.shape[1], index=prices.columns)


def inverse_vol(prices: pd.DataFrame, window: int = 60, **_: object) -> pd.Series:
    returns = prices.pct_change(fill_method=None).tail(window)
    vol = returns.std(ddof=1)
    if (vol <= 0).any() or vol.isna().any():
        return equal_weight(prices)
    return _normalise(1.0 / vol)


def min_variance(
    prices: pd.DataFrame,
    lookback: int = 252,
    shrink: float = 0.20,
    max_weight: float = 0.60,
    **_: object,
) -> pd.Series:
    returns = prices.pct_change(fill_method=None).tail(lookback).dropna()
    if len(returns) < 20:
        return inverse_vol(prices)
    cov = returns.cov().to_numpy() * 252.0
    cov = 0.5 * (cov + cov.T)
    diagonal = np.diag(np.diag(cov))
    cov = (1.0 - shrink) * cov + shrink * diagonal
    cov += np.eye(cov.shape[0]) * 1e-10
    n = cov.shape[0]
    cap = max(max_weight, 1.0 / n)
    cap = min(cap, 1.0)
    x0 = np.full(n, 1.0 / n)
    bounds = [(0.0, cap)] * n
    constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]
    result = minimize(
        lambda w: float(w @ cov @ w),
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-12},
    )
    if not result.success:
        return inverse_vol(prices)
    weights = pd.Series(result.x, index=prices.columns).clip(lower=0.0)
    return _normalise(weights)


def momentum(
    prices: pd.DataFrame,
    lookback: int = 252,
    skip: int = 21,
    top_n: int = 3,
    **_: object,
) -> pd.Series:
    if len(prices) <= skip + 2:
        return equal_weight(prices)
    lookback = min(lookback, len(prices) - 1)
    if lookback <= skip:
        return equal_weight(prices)
    start = prices.iloc[-lookback]
    end = prices.iloc[-skip]
    score = end / start - 1.0
    score = score.replace([np.inf, -np.inf], np.nan).dropna()
    if score.empty:
        return equal_weight(prices)
    top = score.nlargest(min(top_n, len(score))).index
    weights = pd.Series(0.0, index=prices.columns)
    weights.loc[top] = 1.0 / len(top)
    return weights


def sixty_forty(prices: pd.DataFrame, **_: object) -> pd.Series:
    """60% SPY / 40% TLT, falling back to the first two columns.

    Resolving the tickers by name, rather than by column position, prevents a
    silent strategy change when a panel is loaded in a different order. That
    matters: the real-data panel starts SPY, EFA, EEM, TLT, so a positional
    implementation would be 60/40 SPY/EFA while still calling itself 60/40.
    """
    weights = pd.Series(0.0, index=prices.columns)
    tickers = list(prices.columns)
    if len(tickers) < 2:
        return equal_weight(prices)
    equity = "SPY" if "SPY" in tickers else tickers[0]
    bond = "TLT" if "TLT" in tickers else next(t for t in tickers if t != equity)
    weights.loc[equity] = 0.60
    weights.loc[bond] = 0.40
    return weights


STRATEGIES: dict[str, Callable[..., pd.Series]] = {
    "equal_weight": equal_weight,
    "inverse_vol": inverse_vol,
    "min_variance": min_variance,
    "momentum": momentum,
    "sixty_forty": sixty_forty,
}


def strategy_weights(
    strategy: str | Callable[..., pd.Series],
    prices: pd.DataFrame,
    *,
    lookback: int = 252,
) -> pd.Series:
    """Compute target weights from a price history ending at the decision date."""
    if isinstance(strategy, str):
        if strategy not in STRATEGIES:
            raise PortfolioError(f"unknown strategy: {strategy}")
        function = STRATEGIES[strategy]
    elif callable(strategy):
        function = strategy
    else:
        raise PortfolioError("strategy must be a name or a callable")
    if prices.empty or prices.shape[1] == 0:
        raise PortfolioError("prices are empty")
    if prices.isna().any().any():
        raise PortfolioError("prices passed to a strategy must be complete")
    weights = function(prices, lookback=lookback)
    weights = weights.reindex(prices.columns).fillna(0.0).clip(lower=0.0)
    return _normalise(weights)


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #


def month_end_dates(index: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Actual last trading day of each month in ``[start, end]``."""
    selected = index[(index >= start) & (index <= end)]
    if len(selected) == 0:
        raise PortfolioError("no trading days in the requested window")
    frame = pd.Series(selected, index=selected)
    grouped = frame.groupby([selected.year, selected.month]).max()
    return pd.DatetimeIndex(sorted(grouped.to_list()))


def run_backtest(
    panel: Panel,
    strategy: str | Callable[..., pd.Series],
    *,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    portfolio_value: float = 250e6,
    lookback: int = 252,
    market_config: MarketConfig | None = None,
) -> Backtest:
    """Run a gross, buy-and-hold backtest of a target-weight strategy.

    The first rebalance is funded from cash, so the strategy pays the entry
    cost. No liquidation is forced at the end. Prices must be complete for the
    selected universe over the simulation window; assets with gaps are rejected
    rather than silently forward-filled.
    """
    market_config = market_config or MarketConfig()
    if portfolio_value <= 0:
        raise PortfolioError("portfolio_value must be positive")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts:
        raise PortfolioError("start must be before end")

    index = pd.DatetimeIndex(panel.close.index)
    sim_mask = (index >= start_ts) & (index <= end_ts)
    if sim_mask.sum() < 2:
        raise PortfolioError("simulation window has fewer than two trading days")
    sim_dates = index[sim_mask]
    start_pos = int(index.get_loc(sim_dates[0]))
    if start_pos == 0:
        raise PortfolioError("need at least one trading day of history before start")

    # Complete-case universe over the simulation window.
    window_close = panel.close.loc[sim_dates]
    window_volume = panel.volume.loc[sim_dates]
    usable = [
        ticker
        for ticker in panel.tickers
        if window_close[ticker].notna().all()
        and window_volume[ticker].notna().all()
        and (window_close[ticker] > 0).all()
    ]
    if len(usable) == 0:
        raise PortfolioError("no ticker has complete data in the window")
    prices = panel.close[usable]

    rebalance_dates = month_end_dates(index, start_ts, end_ts)
    strategy_name = strategy if isinstance(strategy, str) else getattr(strategy, "__name__", "strategy")

    shares = pd.Series(0.0, index=usable)
    cash = float(portfolio_value)
    pv_values: dict[pd.Timestamp, float] = {}
    rebalances: list[RebalanceRecord] = []
    rebalance_set = set(rebalance_dates)

    for position, date in enumerate(sim_dates):
        if date in rebalance_set:
            global_position = start_pos + position
            previous = index[global_position - 1]
            history = prices.loc[:previous].dropna(how="any")
            if len(history) < 2:
                raise PortfolioError(f"not enough history before {date.date()}")
            target = strategy_weights(strategy, history, lookback=lookback)
            target = target.reindex(usable).fillna(0.0)
            if not np.isclose(float(target.sum()), 1.0, atol=1e-8):
                raise PortfolioError("target weights must sum to 1")

            execution_prices = prices.loc[date]
            pv_pre = float(cash + (shares * execution_prices).sum())
            if pv_pre <= 0:
                raise PortfolioError(f"portfolio value is non-positive at {date.date()}")

            current_weights = shares * execution_prices / pv_pre
            target_shares = target * pv_pre / execution_prices
            delta = target_shares - shares

            state = compute_market_state(panel, previous, market_config)
            state.require_finite(usable)
            trades: list[Trade] = []
            for ticker in usable:
                if abs(float(delta[ticker])) <= 1e-9:
                    continue
                trades.append(
                    Trade(
                        ticker=ticker,
                        shares=float(delta[ticker]),
                        price=float(execution_prices[ticker]),
                        adv_shares=float(state.adv_shares[ticker]),
                        sigma_daily=float(state.sigma_daily[ticker]),
                        spread_bps=float(state.spread_bps[ticker]),
                    )
                )
            rebalances.append(
                RebalanceRecord(
                    date=date,
                    pv_pre=pv_pre,
                    current_weights=current_weights,
                    target_weights=target,
                    trades=trades,
                )
            )
            shares = target_shares
            cash = 0.0

        pv_values[date] = float(cash + (shares * prices.loc[date]).sum())

    pv = pd.Series(pv_values).sort_index()
    return Backtest(
        strategy=str(strategy_name),
        dates=pd.DatetimeIndex(pv.index),
        pv=pv,
        rebalances=rebalances,
    )


# --------------------------------------------------------------------------- #
# Applying a cost model
# --------------------------------------------------------------------------- #


def apply_cost_model(
    backtest: Backtest,
    model: CostModel,
    config: CostConfig | None = None,
) -> CostedBacktest:
    """Deduct a cost model's expected cost from a gross backtest."""
    config = config or CostConfig()
    costs = [rebalance_cost(record, model, config) for record in backtest.rebalances]
    cost_by_date = {cost.date: cost.total_cost for cost in costs}

    gross_pv = backtest.pv
    net_values: list[float] = []
    previous_net: float | None = None
    for i, (date, gross) in enumerate(gross_pv.items()):
        charge = cost_by_date.get(pd.Timestamp(date), 0.0)
        if i == 0:
            net = float(gross) - charge
        else:
            previous_gross = float(gross_pv.iloc[i - 1])
            gross_return = float(gross) / previous_gross - 1.0
            net = float(previous_net) * (1.0 + gross_return) - charge
        net_values.append(net)
        previous_net = net

    net_pv = pd.Series(net_values, index=gross_pv.index)
    net_returns = net_pv.pct_change().dropna()
    return CostedBacktest(
        strategy=backtest.strategy,
        model=model.name,
        gross_pv=gross_pv,
        net_pv=net_pv,
        gross_returns=backtest.returns,
        net_returns=net_returns,
        costs=costs,
        rebalances=backtest.rebalances,
    )


# --------------------------------------------------------------------------- #
# Ranking experiment
# --------------------------------------------------------------------------- #


def run_ranking_experiment(
    panel: Panel,
    strategies: Iterable[str | Callable[..., pd.Series]],
    cost_models: Sequence[CostModel],
    *,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    portfolio_value: float = 250e6,
    lookback: int = 252,
    market_config: MarketConfig | None = None,
    config: CostConfig | None = None,
) -> RankingResult:
    """Run every strategy under every cost model and rank net Sharpe."""
    config = config or CostConfig()
    backtests: dict[str, Backtest] = {}
    costed: dict[tuple[str, str], CostedBacktest] = {}
    rows: list[dict[str, float | str]] = []

    for strategy in strategies:
        name = strategy if isinstance(strategy, str) else getattr(strategy, "__name__", "strategy")
        backtest = run_backtest(
            panel,
            strategy,
            start=start,
            end=end,
            portfolio_value=portfolio_value,
            lookback=lookback,
            market_config=market_config,
        )
        backtests[str(name)] = backtest
        for model in cost_models:
            result = apply_cost_model(backtest, model, config)
            costed[(str(name), model.name)] = result
            summary = result.summary
            rows.append(
                {
                    "strategy": str(name),
                    "model": model.name,
                    "annual_return": summary["annual_return"],
                    "annual_vol": summary["annual_vol"],
                    "sharpe": summary["sharpe"],
                    "max_drawdown": summary["max_drawdown"],
                    "turnover": summary["turnover"],
                    "cost_drag_bps": summary["cost_drag_bps"],
                    "avg_cost_bps": summary["avg_cost_bps"],
                    "total_cost": summary["total_cost"],
                    "ending_value": summary["ending_value"],
                }
            )

    table = pd.DataFrame(rows)
    table["rank"] = table.groupby("model")["sharpe"].rank(
        method="min", ascending=False
    ).astype(int)
    gross_name = "gross" if "gross" in set(table["model"]) else table["model"].iloc[0]
    gross_rank = (
        table[table["model"] == gross_name]
        .set_index("strategy")["rank"]
        .to_dict()
    )
    table["rank_change_vs_gross"] = table.apply(
        lambda row: int(row["rank"] - gross_rank.get(row["strategy"], row["rank"])),
        axis=1,
    )
    return RankingResult(table=table, backtests=backtests, costed=costed)


# --------------------------------------------------------------------------- #
# Sensitivity helpers
# --------------------------------------------------------------------------- #


def linear_cost_components(
    backtest: Backtest,
    model: CostModel,
    config: CostConfig | None = None,
) -> tuple[dict[pd.Timestamp, float], dict[pd.Timestamp, float]]:
    """Split expected cost into a k-independent and a k-linear component.

    For a fixed schedule, impact bps are linear in ``k``. The dollar cost at any
    ``k`` is therefore ``cost0 + k * cost1``. This makes a full k-sensitivity
    curve cheap: run the backtest once and evaluate the curve analytically.
    """
    config = config or CostConfig()
    if model.kind != "impact":
        raise PortfolioError("linear decomposition is only defined for impact models")
    cost0: dict[pd.Timestamp, float] = {}
    cost1: dict[pd.Timestamp, float] = {}
    cfg1 = model.resolved_config(config).with_overrides(impact_k=1.0)
    for record in backtest.rebalances:
        base = 0.0
        unit = 0.0
        for trade in record.trades:
            schedule = _schedule_for_trade(trade, model.schedule, cfg1)
            result = simulate_order(
                ticker=trade.ticker,
                shares=trade.shares,
                price=trade.price,
                adv_shares=trade.adv_shares,
                sigma_daily=trade.sigma_daily,
                spread_bps=trade.spread_bps,
                schedule=schedule,
                config=cfg1,
            )
            unit += result.impact_bps / 1e4 * trade.notional
            base += (result.half_spread_bps + result.commission_bps) / 1e4 * trade.notional
        cost0[record.date] = base
        cost1[record.date] = unit
    return cost0, cost1


def net_pv_at_k(
    backtest: Backtest,
    cost0: Mapping[pd.Timestamp, float],
    cost1: Mapping[pd.Timestamp, float],
    k: float,
) -> pd.Series:
    """Net portfolio value when impact scales linearly with ``k``."""
    gross_pv = backtest.pv
    values: list[float] = []
    previous: float | None = None
    for i, (date, gross) in enumerate(gross_pv.items()):
        charge = cost0.get(pd.Timestamp(date), 0.0) + k * cost1.get(pd.Timestamp(date), 0.0)
        if i == 0:
            net = float(gross) - charge
        else:
            previous_gross = float(gross_pv.iloc[i - 1])
            gross_return = float(gross) / previous_gross - 1.0
            net = float(previous) * (1.0 + gross_return) - charge
        values.append(net)
        previous = net
    return pd.Series(values, index=gross_pv.index)


def sharpe_at_k(
    backtest: Backtest,
    cost0: Mapping[pd.Timestamp, float],
    cost1: Mapping[pd.Timestamp, float],
    k: float,
) -> float:
    pv = net_pv_at_k(backtest, cost0, cost1, k)
    returns = pv.pct_change().dropna()
    if len(returns) < 2 or returns.std(ddof=1) == 0:
        return float("nan")
    return float(returns.mean() / returns.std(ddof=1) * math.sqrt(252.0))


def break_even_k(
    backtest: Backtest,
    model: CostModel,
    target_sharpe: float,
    config: CostConfig | None = None,
    bracket: tuple[float, float] = (0.0, 10.0),
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float | None:
    """Find the ``k`` at which net Sharpe equals ``target_sharpe``.

    Returns ``None`` when the target is outside the bracketed range. The function
    is not assumed to be globally monotonic; the caller should inspect the
    sensitivity table. In the square-root model it is monotonically decreasing
    for a long-only book, which is why bisection is defensible here.
    """
    cost0, cost1 = linear_cost_components(backtest, model, config)
    lo, hi = bracket
    f_lo = sharpe_at_k(backtest, cost0, cost1, lo) - target_sharpe
    f_hi = sharpe_at_k(backtest, cost0, cost1, hi) - target_sharpe
    if not np.isfinite(f_lo) or not np.isfinite(f_hi):
        return None
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = sharpe_at_k(backtest, cost0, cost1, mid) - target_sharpe
        if abs(f_mid) < tol or (hi - lo) < tol:
            return mid
        if f_lo * f_mid <= 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return 0.5 * (lo + hi)


def k_sensitivity_table(
    backtest: Backtest,
    model: CostModel,
    k_grid: Iterable[float],
    config: CostConfig | None = None,
) -> pd.DataFrame:
    """Net Sharpe and cost drag over a grid of impact coefficients."""
    cost0, cost1 = linear_cost_components(backtest, model, config)
    rows = []
    for k in k_grid:
        pv = net_pv_at_k(backtest, cost0, cost1, k)
        returns = pv.pct_change().dropna()
        before = backtest.pv
        total_cost = float(
            sum(
                cost0.get(pd.Timestamp(r.date), 0.0)
                + k * cost1.get(pd.Timestamp(r.date), 0.0)
                for r in backtest.rebalances
            )
        )
        summary = performance_summary(returns, pv, backtest.rebalances, total_cost)
        rows.append(
            {
                "k": float(k),
                "annual_return": summary["annual_return"],
                "sharpe": summary["sharpe"],
                "cost_drag_bps": summary["cost_drag_bps"],
                "ending_value": float(pv.iloc[-1]),
                "gross_ending_value": float(before.iloc[-1]),
            }
        )
    return pd.DataFrame(rows)


def run_aum_sensitivity(
    panel: Panel,
    strategies: Iterable[str | Callable[..., pd.Series]],
    model: CostModel,
    aum_grid: Iterable[float],
    *,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    lookback: int = 252,
    market_config: MarketConfig | None = None,
    config: CostConfig | None = None,
) -> pd.DataFrame:
    """Net Sharpe as assets under management varies, for one cost model."""
    rows = []
    for aum in aum_grid:
        if aum <= 0:
            raise PortfolioError("AUM must be positive")
        for strategy in strategies:
            name = strategy if isinstance(strategy, str) else getattr(strategy, "__name__", "strategy")
            backtest = run_backtest(
                panel,
                strategy,
                start=start,
                end=end,
                portfolio_value=float(aum),
                lookback=lookback,
                market_config=market_config,
            )
            result = apply_cost_model(backtest, model, config)
            summary = result.summary
            rows.append(
                {
                    "strategy": str(name),
                    "aum": float(aum),
                    "sharpe": summary["sharpe"],
                    "annual_return": summary["annual_return"],
                    "cost_drag_bps": summary["cost_drag_bps"],
                    "avg_cost_bps": summary["avg_cost_bps"],
                }
            )
    table = pd.DataFrame(rows)
    table["rank"] = table.groupby("aum")["sharpe"].rank(method="min", ascending=False).astype(int)
    return table


# --------------------------------------------------------------------------- #
# Weights I/O
# --------------------------------------------------------------------------- #


def load_weights_csv(path: str | Path) -> pd.Series:
    """Load target weights from a long or wide CSV.

    Long format: ``ticker,weight`` (optionally ``date,ticker,weight``; the last
    date is used). Wide format: one row per date, one column per ticker.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    columns = {c.lower(): c for c in frame.columns}
    if "ticker" in columns and "weight" in columns:
        if "date" in columns:
            dates = pd.to_datetime(frame[columns["date"]])
            frame = frame.loc[dates == dates.max()]
        weights = pd.Series(
            frame[columns["weight"]].to_numpy(dtype=float),
            index=frame[columns["ticker"]].astype(str),
        )
    else:
        if "date" in columns:
            dates = pd.to_datetime(frame[columns["date"]])
            frame = frame.loc[dates == dates.max()].drop(columns=[columns["date"]])
        if len(frame) != 1:
            raise PortfolioError("wide weights CSV must have exactly one row after date filtering")
        weights = pd.Series(frame.iloc[0].to_numpy(dtype=float), index=frame.columns.astype(str))
    if (weights < 0).any():
        raise PortfolioError("weights must be non-negative")
    total = float(weights.sum())
    if not np.isclose(total, 1.0, atol=1e-6):
        raise PortfolioError(f"weights must sum to 1, got {total:.6f}")
    return weights.sort_index()


def target_trades(
    current_weights: pd.Series,
    target_weights: pd.Series,
    prices: pd.Series,
    portfolio_value: float,
) -> pd.Series:
    """Dollar trade vector from current to target weights."""
    if portfolio_value <= 0:
        raise PortfolioError("portfolio_value must be positive")
    tickers = target_weights.index
    current = current_weights.reindex(tickers).fillna(0.0)
    target = target_weights.reindex(tickers).fillna(0.0)
    if not np.isclose(float(target.sum()), 1.0, atol=1e-8):
        raise PortfolioError("target weights must sum to 1")
    delta = (target - current) * portfolio_value
    return delta


def dollar_trades_to_shares(dollar_trades: pd.Series, prices: pd.Series) -> pd.Series:
    """Convert dollar trades to signed shares."""
    prices = prices.reindex(dollar_trades.index)
    if (prices <= 0).any() or prices.isna().any():
        raise PortfolioError("prices must be positive and complete")
    return dollar_trades / prices

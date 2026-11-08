"""One-command demo.

The demo is the public reproduction path. It uses the checked-in synthetic ETF
panel, writes every table and figure to ``results/demo``, and generates a
Markdown report from the same objects. No network access, no vendor data, no
live-trading claim.
"""

from __future__ import annotations

import json
import platform
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from . import __version__
from .config import (
    DEFAULT_AUM_GRID,
    DEFAULT_K_GRID,
    DEFAULT_PARTICIPATION_GRID,
    DEFAULT_RISK_AVERSIONS,
    CostConfig,
    MarketConfig,
)
from .data import (
    Panel,
    compute_market_state,
    default_demo_data_path,
    load_or_make_demo_panel,
    load_panel_csv,
)
from .portfolio import (
    CostModel,
    apply_cost_model,
    break_even_k,
    k_sensitivity_table,
    month_end_dates,
    run_aum_sensitivity,
    run_backtest,
    run_ranking_experiment,
)
from .report import (
    md_table,
    pct,
    plot_aum_sensitivity,
    plot_cost_curve,
    plot_cost_decomposition,
    plot_k_sensitivity,
    plot_ranking_heatmap,
    plot_schedule_frontier,
    write_csv,
    write_text,
)
from .schedules import make_schedule, schedule_candidates
from .simulator import compare_schedules, simulate_order

STRATEGIES = ("equal_weight", "inverse_vol", "min_variance", "momentum", "sixty_forty")

DEFAULT_COST_MODELS = (
    CostModel("gross", "gross"),
    CostModel("fixed_10bps", "fixed", fixed_bps=10.0),
    CostModel("spread_plus_fee", "linear"),
    CostModel("impact_immediate", "impact", schedule="immediate"),
    CostModel("impact_twap_5d", "impact", schedule="twap_5d"),
    CostModel("impact_vwap_5d", "impact", schedule="vwap_5d"),
    CostModel("impact_pov_10pct", "impact", schedule="pov_10pct"),
    CostModel("impact_optimal", "optimal"),
)


def _pick_order_asset(state) -> str:
    """Least-liquid *usable* asset by dollar ADV: where impact is visible."""
    usable = (
        state.price.notna()
        & state.adv_shares.notna()
        & state.sigma_daily.notna()
        & state.spread_bps.notna()
        & (state.price > 0)
        & (state.adv_shares > 0)
        & (state.sigma_daily > 0)
    )
    if not usable.any():
        raise ValueError("no ticker has a complete market state")
    adv_notional = (state.adv_shares * state.price)[usable]
    return str(adv_notional.idxmin())


def _single_order_tables(
    panel: Panel,
    asof: pd.Timestamp,
    config: CostConfig,
    market_config: MarketConfig,
    k_grid: Iterable[float],
    participation_grid: Iterable[float],
) -> dict[str, object]:
    state = compute_market_state(panel, asof, market_config)
    ticker = _pick_order_asset(state)
    state.require_finite([ticker])
    price = float(state.price[ticker])
    adv = float(state.adv_shares[ticker])
    adv_notional = price * adv
    order_notional = 0.10 * adv_notional
    shares = order_notional / price

    schedules = schedule_candidates(shares, adv)
    comparison = compare_schedules(
        ticker=ticker,
        shares=shares,
        price=price,
        adv_shares=adv,
        sigma_daily=float(state.sigma_daily[ticker]),
        spread_bps=float(state.spread_bps[ticker]),
        schedules=schedules,
        config=config,
    )
    comparison.insert(0, "order_notional", order_notional)
    comparison.insert(1, "adv_notional", adv_notional)

    k_rows = []
    for k in k_grid:
        cfg = config.with_overrides(impact_k=float(k))
        for schedule in schedules:
            result = simulate_order(
                ticker=ticker,
                shares=shares,
                price=price,
                adv_shares=adv,
                sigma_daily=float(state.sigma_daily[ticker]),
                spread_bps=float(state.spread_bps[ticker]),
                schedule=schedule,
                config=cfg,
            )
            row = result.to_dict()
            row["k"] = float(k)
            k_rows.append(row)
    k_table = pd.DataFrame(k_rows)

    # Cost curve for four representative families. POV is rebuilt at each order
    # size because its horizon is endogenous.
    curve_rows = []
    for p in participation_grid:
        p = float(p)
        if p <= 0:
            raise ValueError("participation grid must be positive")
        order_shares = p * adv
        curve_schedules = [
            make_schedule("immediate"),
            make_schedule("twap", horizon_days=5),
            make_schedule("vwap", horizon_days=5),
            make_schedule(
                "pov",
                order_shares=order_shares,
                adv_shares=adv,
                participation_rate=0.05,
            ),
        ]
        for schedule in curve_schedules:
            result = simulate_order(
                ticker=ticker,
                shares=order_shares,
                price=price,
                adv_shares=adv,
                sigma_daily=float(state.sigma_daily[ticker]),
                spread_bps=float(state.spread_bps[ticker]),
                schedule=schedule,
                config=config,
            )
            row = result.to_dict()
            row["target_participation"] = p
            row["target_notional"] = order_shares * price
            curve_rows.append(row)
    curve = pd.DataFrame(curve_rows)

    frontier_rows = []
    for risk_aversion in DEFAULT_RISK_AVERSIONS:
        cfg = config.with_overrides(risk_aversion=float(risk_aversion))
        for schedule in schedules:
            result = simulate_order(
                ticker=ticker,
                shares=shares,
                price=price,
                adv_shares=adv,
                sigma_daily=float(state.sigma_daily[ticker]),
                spread_bps=float(state.spread_bps[ticker]),
                schedule=schedule,
                config=cfg,
            )
            frontier_rows.append(
                {
                    "risk_aversion": float(risk_aversion),
                    "schedule": result.schedule,
                    "expected_cost_bps": result.expected_cost_bps,
                    "timing_risk_bps": result.timing_risk_bps,
                    "objective_bps": result.objective_bps,
                    "expected_cost_dollars": result.expected_cost_dollars,
                }
            )
    frontier = pd.DataFrame(frontier_rows)
    best_frontier = (
        frontier.sort_values(["risk_aversion", "objective_bps", "schedule"])
        .groupby("risk_aversion", as_index=False)
        .first()
    )

    return {
        "state": state,
        "ticker": ticker,
        "price": price,
        "adv": adv,
        "adv_notional": adv_notional,
        "order_notional": order_notional,
        "shares": shares,
        "comparison": comparison,
        "k_table": k_table,
        "curve": curve,
        "frontier": frontier,
        "best_frontier": best_frontier,
    }


def _ranking_tables(
    panel: Panel,
    start: pd.Timestamp,
    end: pd.Timestamp,
    aum: float,
    config: CostConfig,
    market_config: MarketConfig,
    models=DEFAULT_COST_MODELS,
):
    result = run_ranking_experiment(
        panel,
        STRATEGIES,
        models,
        start=start,
        end=end,
        portfolio_value=aum,
        market_config=market_config,
        config=config,
    )
    sharpes = result.sharpes()
    ranks = result.ranks()

    gross_rank = (
        result.table[result.table["model"] == "gross"].set_index("strategy")["rank"]
    )
    change_rows = []
    for model in result.table["model"].unique():
        if model == "gross":
            continue
        subset = result.table[result.table["model"] == model]
        for _, row in subset.iterrows():
            change_rows.append(
                {
                    "model": model,
                    "strategy": row["strategy"],
                    "gross_rank": int(gross_rank.get(row["strategy"], row["rank"])),
                    "model_rank": int(row["rank"]),
                    "rank_change": int(row["rank"] - gross_rank.get(row["strategy"], row["rank"])),
                }
            )
    changes = pd.DataFrame(change_rows)

    gross_sharpe = (
        result.table[result.table["model"] == "gross"].set_index("strategy")["sharpe"]
    )
    impact_model = "impact_vwap_5d"
    if impact_model in set(result.table["model"]):
        impact_sharpe = (
            result.table[result.table["model"] == impact_model]
            .set_index("strategy")["sharpe"]
        )
        fragility = pd.DataFrame(
            {
                "strategy": gross_sharpe.index,
                "gross_sharpe": gross_sharpe.values,
                "impact_sharpe": [impact_sharpe.get(s, np.nan) for s in gross_sharpe.index],
            }
        )
        fragility["sharpe_lost"] = fragility["gross_sharpe"] - fragility["impact_sharpe"]
        fragility = fragility.sort_values("sharpe_lost", ascending=False)
    else:
        fragility = pd.DataFrame()

    return {
        "result": result,
        "table": result.table,
        "sharpes": sharpes,
        "ranks": ranks,
        "changes": changes,
        "fragility": fragility,
        "decomposition": result.decomposition(),
    }


def _k_tables(
    panel: Panel,
    start: pd.Timestamp,
    end: pd.Timestamp,
    aum: float,
    config: CostConfig,
    market_config: MarketConfig,
    k_grid: Iterable[float],
):
    model = CostModel("impact_vwap_5d", "impact", schedule="vwap_5d")
    fixed = CostModel("fixed_10bps", "fixed", fixed_bps=10.0)
    rows = []
    break_rows = []
    for strategy in STRATEGIES:
        backtest = run_backtest(
            panel,
            strategy,
            start=start,
            end=end,
            portfolio_value=aum,
            market_config=market_config,
        )
        table = k_sensitivity_table(backtest, model, k_grid, config)
        table.insert(0, "strategy", strategy)
        rows.append(table)
        fixed_sharpe = apply_cost_model(backtest, fixed, config).summary["sharpe"]
        break_rows.append(
            {
                "strategy": strategy,
                "fixed_10bps_sharpe": fixed_sharpe,
                "break_even_k_vs_fixed": break_even_k(
                    backtest, model, target_sharpe=fixed_sharpe, config=config
                ),
                "break_even_k_vs_zero": break_even_k(
                    backtest, model, target_sharpe=0.0, config=config
                ),
            }
        )
    return pd.concat(rows, ignore_index=True), pd.DataFrame(break_rows)


def _aum_tables(
    panel: Panel,
    start: pd.Timestamp,
    end: pd.Timestamp,
    config: CostConfig,
    market_config: MarketConfig,
    aum_grid: Iterable[float],
):
    model = CostModel("impact_vwap_5d", "impact", schedule="vwap_5d")
    table = run_aum_sensitivity(
        panel,
        STRATEGIES,
        model,
        aum_grid,
        start=start,
        end=end,
        market_config=market_config,
        config=config,
    )
    ranks = table.pivot(index="strategy", columns="aum", values="rank")
    return table, ranks


def _aum_label(value: float) -> str:
    if value >= 1e9:
        billions = value / 1e9
        return f"${billions:,.0f}B" if billions == int(billions) else f"${billions:,.1f}B"
    return f"${value / 1e6:,.0f}M"


def _report(
    *,
    data_label: str,
    synthetic: bool,
    panel: Panel,
    start: pd.Timestamp,
    end: pd.Timestamp,
    aum: float,
    config: CostConfig,
    single: dict[str, object],
    ranking: dict[str, object],
    k_table: pd.DataFrame,
    break_table: pd.DataFrame,
    aum_table: pd.DataFrame,
    aum_ranks: pd.DataFrame,
) -> str:
    comparison = single["comparison"]
    ticker = single["ticker"]
    order_notional = single["order_notional"]
    adv_notional = single["adv_notional"]
    best_frontier = single["best_frontier"]

    best_at_config = comparison.iloc[0]
    cheapest = comparison.sort_values("expected_cost_bps").iloc[0]
    safest = comparison.sort_values("timing_risk_bps").iloc[0]

    top_table = comparison[
        [
            "schedule",
            "participation",
            "half_spread_bps",
            "impact_bps",
            "expected_cost_bps",
            "timing_risk_bps",
            "objective_bps",
        ]
    ].copy()
    top_table["participation"] = top_table["participation"].map(lambda v: pct(v, 2))

    guess_rows = ranking["table"][
        ranking["table"]["model"].isin(
            ["gross", "fixed_10bps", "spread_plus_fee", "impact_vwap_5d", "impact_optimal"]
        )
    ]
    sharpe_view = guess_rows.pivot(index="strategy", columns="model", values="sharpe")
    sharpe_view = sharpe_view[
        [
            c
            for c in ["gross", "fixed_10bps", "spread_plus_fee", "impact_vwap_5d", "impact_optimal"]
            if c in sharpe_view.columns
        ]
    ]
    rank_view = guess_rows.pivot(index="strategy", columns="model", values="rank")
    rank_view = rank_view[
        [
            c
            for c in ["gross", "fixed_10bps", "spread_plus_fee", "impact_vwap_5d", "impact_optimal"]
            if c in rank_view.columns
        ]
    ]

    fragility = ranking["fragility"]
    changes = ranking["changes"]
    changed = changes[changes["rank_change"] != 0]
    k_breaks = break_table.copy()
    aum_rank_view = aum_ranks.copy()

    gross_sharpes = (
        ranking["table"][ranking["table"]["model"] == "gross"]
        .set_index("strategy")["sharpe"]
        .sort_values(ascending=False)
    )
    adjacent_gap = (
        float(gross_sharpes.diff().abs().dropna().min())
        if len(gross_sharpes) > 1
        else float("nan")
    )
    max_cost_loss = float(fragility["sharpe_lost"].max()) if not fragility.empty else float("nan")

    zero_crossings = []
    for strategy, group in aum_table.groupby("strategy"):
        group = group.sort_values("aum")
        crossing = None
        for i in range(1, len(group)):
            previous = group.iloc[i - 1]
            current = group.iloc[i]
            if previous["sharpe"] > 0 >= current["sharpe"]:
                fraction = previous["sharpe"] / (previous["sharpe"] - current["sharpe"])
                crossing = float(previous["aum"] + fraction * (current["aum"] - previous["aum"]))
                break
        zero_crossings.append(
            {
                "strategy": strategy,
                "first_non_positive_aum": crossing,
            }
        )
    zero_crossing_table = pd.DataFrame(zero_crossings).sort_values(
        "first_non_positive_aum", na_position="last"
    )

    lines: list[str] = []
    title = (
        "# Execution & Market-Impact Lab — demo results\n"
        if synthetic
        else "# Execution & Market-Impact Lab — local real-data results\n"
    )
    lines.append(title)
    if synthetic:
        lines.append(
            "**Status:** generated by `execution-lab demo`. This is a method demonstration "
            "on synthetic data, not an empirical claim about real ETFs.\n"
        )
    else:
        lines.append(
            "**Status:** generated by `execution-lab demo --panel`. This is a local "
            "validation on a licensed panel; only aggregate results are shown. The raw "
            "data are not redistributed, and this is still not an execution simulator.\n"
        )
    lines.append(f"- **Data:** {data_label}")
    lines.append(f"- **Panel:** {panel.close.shape[1]} tickers, {panel.close.shape[0]} daily rows")
    lines.append(f"- **Simulation window:** {start.date()} to {end.date()}")
    lines.append(f"- **Assets under management:** ${aum:,.0f}")
    lines.append(f"- **Model:** half-spread + {config.commission_bps:g} bp commission + "
                 f"k={config.impact_k:g} square-root impact; risk aversion {config.risk_aversion:g}")
    lines.append("")

    lines.append("## 1. One order, many schedules\n")
    lines.append(
        f"The least-liquid asset in the panel is **{ticker}**. A 10%-of-ADV order is "
        f"**${order_notional:,.0f}** against **${adv_notional:,.0f}** of daily dollar volume. "
        "The table is the cost decomposition, not a forecast of a particular day.\n"
    )
    lines.append(md_table(top_table, floatfmt=".2f"))
    lines.append("")
    lines.append(
        f"- Cheapest expected cost: **{cheapest['schedule']}** at "
        f"{cheapest['expected_cost_bps']:.2f} bps."
    )
    lines.append(
        f"- Lowest timing risk: **{safest['schedule']}** at "
        f"{safest['timing_risk_bps']:.2f} bps (immediate execution has none by construction)."
    )
    lines.append(
        f"- Lowest objective at risk aversion {config.risk_aversion:g}: "
        f"**{best_at_config['schedule']}** at {best_at_config['objective_bps']:.2f} bps."
    )
    lines.append("")
    lines.append(
        "The key trade-off is visible: spreading the order lowers impact but adds timing "
        "risk measured against the arrival price. A VWAP schedule is cheaper than TWAP at "
        "the same horizon because it matches expected volume instead of dividing time "
        "equally. POV chooses its horizon endogenously; when the target rate is above the "
        "order's participation, it collapses to a one-day VWAP and is not counted twice.\n"
    )

    lines.append("## 2. Risk-aversion frontier\n")
    lines.append(
        "The optimal schedule is a function of the risk-aversion parameter. The same order "
        "can rationally be executed immediately or spread over days depending on that "
        "preference. This table reports the best schedule at each setting.\n"
    )
    lines.append(
        md_table(
            best_frontier[
                [
                    "risk_aversion",
                    "schedule",
                    "expected_cost_bps",
                    "timing_risk_bps",
                    "objective_bps",
                ]
            ],
            floatfmt=".2f",
        )
    )
    lines.append("")

    lines.append("## 3. Does the strategy ranking survive costs?\n")
    lines.append(
        "Every strategy is run on the same gross return path, then charged under each cost "
        "assumption. The ranking is by net Sharpe. `impact_optimal` chooses a schedule per "
        "trade from the pre-declared menu.\n"
    )
    lines.append(md_table(sharpe_view, floatfmt=".3f"))
    lines.append("")
    lines.append("**Ranks** (1 = best net Sharpe):\n")
    lines.append(md_table(rank_view, floatfmt=".0f"))
    lines.append("")
    if changed.empty:
        lines.append(
            "At this AUM the ranking is unchanged across the cost models. That is a "
            "property of this synthetic panel and this order size, not evidence that "
            "implementation costs never matter. The reason is arithmetic: the cost "
            "*differences* between adjacent strategies are smaller than their gross "
            "Sharpe gaps. The largest absolute loss to impact is "
            f"{max_cost_loss:.3f} Sharpe, but it belongs to momentum, which is already "
            f"last by a wide margin; the smallest gross gap is {adjacent_gap:.3f}. The "
            "AUM and k tables below show where absolute edges, rather than ranks, break."
        )
    else:
        lines.append(
            "The ranking changes under at least one cost assumption. The rows below isolate "
            "the changes relative to gross Sharpe.\n"
        )
        lines.append(
            md_table(
                changed[["model", "strategy", "gross_rank", "model_rank", "rank_change"]],
                floatfmt=".0f",
            )
        )
    lines.append("")
    if not fragility.empty:
        lines.append("**Implementation fragility** — Sharpe lost to 5-day VWAP impact:\n")
        lines.append(md_table(fragility, floatfmt=".3f"))
        lines.append("")

    lines.append("## 4. Sensitivity to the impact coefficient\n")
    lines.append(
        "`k` is not identified from daily data. The honest output is a range and a "
        "break-even, not a point estimate. The break-even below is the `k` at which the "
        "strategy's net Sharpe equals its fixed-10bps Sharpe, or zero (no edge). "
        "`None` means the target is outside the `[0, 10]` bracket. A common reason on "
        "`vs_fixed` is that the fixed-10bps baseline is already cheaper than the "
        "spread-plus-commission cost, so no non-negative impact coefficient can restore "
        "parity; the naive baseline is not conservative for that asset.\n"
    )
    lines.append(md_table(k_breaks, floatfmt=".3f"))
    lines.append("")
    k_view = k_table[
        k_table["k"].isin([0.1, 0.5, 1.0, 2.0])
    ][["strategy", "k", "sharpe", "cost_drag_bps"]]
    lines.append(md_table(k_view, floatfmt=".3f", max_rows=30))
    lines.append("")

    lines.append("## 5. Capacity: the same strategy at different AUM\n")
    lines.append(
        "Impact scales with the square root of participation, so it grows faster than "
        "linearly in AUM while return does not. The table is the net-Sharpe rank at each "
        "AUM level. A rank need not change for capacity to bind: a strategy can lose its "
        "absolute edge while keeping its ordinal position.\n"
    )
    aum_rank_view = aum_rank_view.copy()
    aum_rank_view.columns = [_aum_label(float(c)) for c in aum_rank_view.columns]
    lines.append(md_table(aum_rank_view, floatfmt=".0f"))
    lines.append("")
    aum_sharpe_view = aum_table.pivot(index="strategy", columns="aum", values="sharpe")
    aum_sharpe_view.columns = [_aum_label(float(c)) for c in aum_sharpe_view.columns]
    lines.append(md_table(aum_sharpe_view, floatfmt=".3f"))
    lines.append("")
    lines.append(
        "**AUM at which net Sharpe first crosses zero** (linear interpolation between "
        "grid points; not a capacity estimate):\n"
    )
    zero_crossing_table = zero_crossing_table.copy()
    zero_crossing_table["first_non_positive_aum"] = zero_crossing_table[
        "first_non_positive_aum"
    ].map(lambda value: "—" if pd.isna(value) else _aum_label(float(value)))
    lines.append(md_table(zero_crossing_table))
    lines.append("")

    lines.append("## 6. What this does not show\n")
    lines.append(
        "- **No order-book realism.** The model uses daily OHLCV and a high-low spread "
        "proxy, not quotes or depth.\n"
        "- **No intraday path.** Timing risk is a zero-drift random-walk standard deviation; "
        "it is not a simulated execution path."
        "\n- **No identified `k`.** The coefficient is a sensitivity parameter. The demo is "
        "designed to show how the answer moves with it."
        "\n- **No live-trading claim.** There is no routing, brokerage connection, or alpha "
        "claim."
    )
    if synthetic:
        lines.append(
            "- **Synthetic data.** The strategy dispersion is generated, not observed. The "
            "ranking results illustrate the method; they are not evidence about real ETFs."
        )
    else:
        lines.append(
            "- **Local data, not redistributed.** The panel is a licensed snapshot used "
            "for a local check. The aggregate tables are shown; the raw data are not. The "
            "spread proxy is still a daily high-low estimate, not a quote."
        )
    lines.append("## Reproduce\n")
    lines.append("```bash\npip install -e .\nexecution-lab demo --out results/demo\n```\n")
    lines.append(
        "The checked-in demo panel is generated by `scripts/make_demo_data.py` from a fixed "
        "seed. A run manifest with the panel hash and parameter values is written next to "
        "this report.\n"
    )
    return "\n".join(lines)


def run_demo(
    out_dir: str | Path = "results/demo",
    *,
    data_path: str | Path | None = None,
    seed: int = 20261108,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    aum: float = 250e6,
    force_data: bool = False,
    k_grid: Iterable[float] = DEFAULT_K_GRID,
    participation_grid: Iterable[float] = DEFAULT_PARTICIPATION_GRID,
    aum_grid: Iterable[float] = DEFAULT_AUM_GRID,
    config: CostConfig | None = None,
    market_config: MarketConfig | None = None,
) -> dict[str, object]:
    """Run the full demo and write tables, figures, report, and manifest."""
    config = config or CostConfig()
    market_config = market_config or MarketConfig()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if data_path is None:
        panel = load_or_make_demo_panel(
            default_demo_data_path(), seed=seed, force=force_data
        )
        data_label = f"synthetic ETF panel, seed {seed}"
    else:
        panel = load_panel_csv(data_path)
        data_label = f"local panel: {Path(data_path).name} (not redistributed)"

    end_ts = pd.Timestamp(end) if end is not None else pd.Timestamp(panel.close.index[-1])
    if start is None:
        seed_date = panel.close.index[min(252, len(panel.close) - 2)]
        start_ts = month_end_dates(panel.close.index, seed_date, end_ts)[0]
    else:
        start_ts = pd.Timestamp(start)
    if start_ts >= end_ts:
        raise ValueError("start must be before end")

    # Single-order view at the end of the panel.
    single = _single_order_tables(
        panel,
        end_ts,
        config,
        market_config,
        k_grid,
        participation_grid,
    )

    # Ranking experiment.
    ranking = _ranking_tables(panel, start_ts, end_ts, aum, config, market_config)

    # Sensitivity.
    k_table, break_table = _k_tables(
        panel, start_ts, end_ts, aum, config, market_config, k_grid
    )
    aum_table, aum_ranks = _aum_tables(
        panel, start_ts, end_ts, config, market_config, aum_grid
    )

    # Tables.
    write_csv(single["comparison"], out / "order_schedule_comparison.csv")
    write_csv(single["k_table"], out / "order_k_sensitivity.csv")
    write_csv(single["curve"], out / "cost_curve.csv")
    write_csv(single["frontier"], out / "schedule_frontier.csv")
    write_csv(single["best_frontier"], out / "optimal_by_risk_aversion.csv")
    write_csv(ranking["table"], out / "ranking.csv")
    write_csv(ranking["sharpes"].reset_index(), out / "ranking_sharpes.csv")
    write_csv(ranking["ranks"].reset_index(), out / "ranking_ranks.csv")
    write_csv(ranking["changes"], out / "rank_changes.csv")
    write_csv(ranking["fragility"], out / "fragility.csv")
    write_csv(ranking["decomposition"], out / "cost_decomposition.csv")
    write_csv(k_table, out / "k_sensitivity.csv")
    write_csv(break_table, out / "break_even_k.csv")
    write_csv(aum_table, out / "aum_sensitivity.csv")
    write_csv(aum_ranks.reset_index(), out / "aum_ranks.csv")

    # Figures.
    plot_cost_curve(single["curve"], out / "fig_cost_curve.png")
    plot_schedule_frontier(single["comparison"], out / "fig_schedule_frontier.png")
    plot_ranking_heatmap(ranking["sharpes"], out / "fig_ranking_heatmap.png")
    plot_k_sensitivity(k_table, out / "fig_k_sensitivity.png")
    plot_aum_sensitivity(aum_table, out / "fig_aum_sensitivity.png")
    decomposition = ranking["decomposition"]
    if not decomposition.empty:
        impact_decomp = decomposition[decomposition["model"] == "impact_vwap_5d"]
        if not impact_decomp.empty:
            plot_cost_decomposition(impact_decomp, out / "fig_cost_decomposition.png")

    report = _report(
        data_label=data_label,
        synthetic=data_path is None,
        panel=panel,
        start=start_ts,
        end=end_ts,
        aum=aum,
        config=config,
        single=single,
        ranking=ranking,
        k_table=k_table,
        break_table=break_table,
        aum_table=aum_table,
        aum_ranks=aum_ranks,
    )
    write_text(report, out / "report.md")

    manifest = {
        "package": "execution-lab",
        "version": __version__,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "data": data_label,
        "panel_hash": panel.content_hash(),
        "start": str(start_ts.date()),
        "end": str(end_ts.date()),
        "aum": aum,
        "seed": seed,
        "cost_config": asdict(config),
        "market_config": asdict(market_config),
        "k_grid": list(k_grid),
        "participation_grid": list(participation_grid),
        "aum_grid": list(aum_grid),
        "strategies": list(STRATEGIES),
        "outputs": sorted(p.name for p in out.iterdir() if p.is_file()),
    }
    write_text(json.dumps(manifest, indent=2, default=str) + "\n", out / "manifest.json")

    return {
        "single": single,
        "ranking": ranking,
        "k_table": k_table,
        "break_table": break_table,
        "aum_table": aum_table,
        "aum_ranks": aum_ranks,
        "report": report,
        "manifest": manifest,
        "out_dir": out,
    }

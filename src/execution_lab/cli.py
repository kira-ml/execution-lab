"""Command-line interface.

Examples
--------
Run the full synthetic demo::

    execution-lab demo --out results/demo

Price one order::

    execution-lab simulate --ticker VNQ --shares 250000 --price 90 \
        --adv 2000000 --sigma 0.014 --spread-bps 6 --schedule vwap --horizon 5

Fit the impact coefficient from observed execution costs::

    execution-lab calibrate --observations costs.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd

from . import __version__
from .calibration import bootstrap_k, fit_k
from .config import (
    DEFAULT_K_GRID,
    DEFAULT_PARTICIPATION_GRID,
    CostConfig,
    MarketConfig,
)
from .data import load_panel_csv
from .demo import DEFAULT_COST_MODELS, STRATEGIES, run_demo
from .portfolio import run_ranking_experiment
from .report import md_table
from .schedules import make_schedule, schedule_candidates
from .simulator import compare_schedules, cost_curve, simulate_order


def _add_cost_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--k", type=float, default=0.5, help="impact coefficient")
    parser.add_argument("--commission-bps", type=float, default=0.5)
    parser.add_argument("--risk-aversion", type=float, default=0.05)
    parser.add_argument("--impact-mode", choices=("per_slice", "total"), default="per_slice")


def _config(args: argparse.Namespace) -> CostConfig:
    return CostConfig(
        commission_bps=args.commission_bps,
        impact_k=args.k,
        impact_mode=args.impact_mode,
        risk_aversion=args.risk_aversion,
    )


def _schedule(args: argparse.Namespace):
    if args.schedule == "immediate":
        return make_schedule("immediate")
    if args.schedule in {"twap", "vwap"}:
        return make_schedule(args.schedule, horizon_days=args.horizon)
    return make_schedule(
        "pov",
        order_shares=args.shares,
        adv_shares=args.adv,
        participation_rate=args.pov_rate,
    )


def _cmd_demo(args: argparse.Namespace) -> int:
    config = CostConfig(
        commission_bps=args.commission_bps,
        impact_k=args.k,
        impact_mode=args.impact_mode,
        risk_aversion=args.risk_aversion,
    )
    result = run_demo(
        out_dir=args.out,
        data_path=args.panel,
        seed=args.seed,
        start=args.start,
        end=args.end,
        aum=args.aum,
        force_data=args.force_data,
        config=config,
    )
    print(f"wrote {result['out_dir']}")
    print(f"report: {Path(result['out_dir']) / 'report.md'}")
    print(f"panel hash: {result['manifest']['panel_hash']}")
    ranking = result["ranking"]["table"]
    view = ranking[ranking["model"].isin(["gross", "fixed_10bps", "impact_vwap_5d"])]
    pivot = view.pivot(index="strategy", columns="model", values="sharpe")
    print("\nNet Sharpe (selected models):")
    print(md_table(pivot, floatfmt=".3f"))
    return 0


def _cmd_simulate(args: argparse.Namespace) -> int:
    config = _config(args)
    schedule = _schedule(args)
    result = simulate_order(
        ticker=args.ticker,
        shares=args.shares,
        price=args.price,
        adv_shares=args.adv,
        sigma_daily=args.sigma,
        spread_bps=args.spread_bps,
        schedule=schedule,
        config=config,
    )
    print(json.dumps(result.to_dict(), indent=2, default=str))
    if args.slices_out:
        path = Path(args.slices_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        result.slices.to_csv(path, index=False)
        print(f"\nslices: {path}", file=sys.stderr)
    return 0


def _cmd_sensitivity(args: argparse.Namespace) -> int:
    config = _config(args)
    if args.compare:
        schedules = schedule_candidates(args.shares, args.adv)
        table = compare_schedules(
            ticker=args.ticker,
            shares=args.shares,
            price=args.price,
            adv_shares=args.adv,
            sigma_daily=args.sigma,
            spread_bps=args.spread_bps,
            schedules=schedules,
            config=config,
        )
        if args.out:
            path = Path(args.out)
            path.parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(path, index=False)
        print(
            md_table(
                table[
                    [
                        "schedule",
                        "participation",
                        "expected_cost_bps",
                        "timing_risk_bps",
                        "objective_bps",
                    ]
                ],
                floatfmt=".3f",
            )
        )
        return 0

    schedule = _schedule(args)
    table = cost_curve(
        ticker=args.ticker,
        price=args.price,
        adv_shares=args.adv,
        sigma_daily=args.sigma,
        spread_bps=args.spread_bps,
        participation_grid=args.participation,
        schedule=schedule,
        config=config,
    )
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path, index=False)
    print(
        md_table(
            table[
                [
                    "target_participation",
                    "expected_cost_bps",
                    "timing_risk_bps",
                    "objective_bps",
                ]
            ],
            floatfmt=".3f",
        )
    )
    return 0


def _cmd_rank(args: argparse.Namespace) -> int:
    panel = load_panel_csv(args.panel)
    if args.start is None:
        start = panel.close.index[min(252, len(panel.close) - 2)]
    else:
        start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else panel.close.index[-1]
    config = CostConfig(
        commission_bps=args.commission_bps,
        impact_k=args.k,
        risk_aversion=args.risk_aversion,
    )
    result = run_ranking_experiment(
        panel,
        STRATEGIES,
        DEFAULT_COST_MODELS,
        start=start,
        end=end,
        portfolio_value=args.aum,
        market_config=MarketConfig(),
        config=config,
    )
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        result.table.to_csv(path, index=False)
    print(md_table(result.sharpes(), floatfmt=".3f"))
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    frame = pd.read_csv(args.observations)
    columns = {c.lower(): c for c in frame.columns}
    needed = [args.cost_column, args.sigma_column, args.participation_column]
    missing = [c for c in needed if c not in columns]
    if missing:
        raise SystemExit(f"missing columns: {missing}")
    fit = fit_k(
        frame[columns[args.cost_column]],
        frame[columns[args.sigma_column]],
        frame[columns[args.participation_column]],
        exponent=args.exponent,
    )
    payload = fit.to_dict()
    if args.bootstrap and fit.n_observations >= 2:
        _, lo, hi = bootstrap_k(
            frame[columns[args.cost_column]],
            frame[columns[args.sigma_column]],
            frame[columns[args.participation_column]],
            exponent=args.exponent,
            n_boot=args.n_boot,
            seed=args.seed,
        )
        payload["bootstrap_95_low"] = lo
        payload["bootstrap_95_high"] = hi
    print(json.dumps(payload, indent=2))
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execution-lab",
        description="Transparent execution-cost and market-impact laboratory.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run the full synthetic demo")
    demo.add_argument("--out", default="results/demo")
    demo.add_argument("--panel", default=None, help="optional long-format CSV panel")
    demo.add_argument("--seed", type=int, default=20261108)
    demo.add_argument("--start", default=None)
    demo.add_argument("--end", default=None)
    demo.add_argument("--aum", type=float, default=250e6)
    demo.add_argument("--force-data", action="store_true")
    _add_cost_args(demo)
    demo.set_defaults(func=_cmd_demo)

    simulate = subparsers.add_parser("simulate", help="price one parent order")
    simulate.add_argument("--ticker", default="ASSET")
    simulate.add_argument("--shares", type=float, required=True)
    simulate.add_argument("--price", type=float, required=True)
    simulate.add_argument("--adv", type=float, required=True, help="average daily volume in shares")
    simulate.add_argument("--sigma", type=float, required=True, help="daily return volatility")
    simulate.add_argument("--spread-bps", type=float, required=True)
    simulate.add_argument("--schedule", choices=("immediate", "twap", "vwap", "pov"), default="vwap")
    simulate.add_argument("--horizon", type=int, default=5)
    simulate.add_argument("--pov-rate", type=float, default=0.10)
    simulate.add_argument("--slices-out", default=None)
    _add_cost_args(simulate)
    simulate.set_defaults(func=_cmd_simulate)

    sensitivity = subparsers.add_parser("sensitivity", help="cost curve or schedule comparison")
    sensitivity.add_argument("--ticker", default="ASSET")
    sensitivity.add_argument("--shares", type=float, required=True)
    sensitivity.add_argument("--price", type=float, required=True)
    sensitivity.add_argument("--adv", type=float, required=True)
    sensitivity.add_argument("--sigma", type=float, required=True)
    sensitivity.add_argument("--spread-bps", type=float, required=True)
    sensitivity.add_argument("--schedule", choices=("immediate", "twap", "vwap", "pov"), default="vwap")
    sensitivity.add_argument("--horizon", type=int, default=5)
    sensitivity.add_argument("--pov-rate", type=float, default=0.10)
    sensitivity.add_argument("--compare", action="store_true", help="compare the schedule menu")
    sensitivity.add_argument(
        "--participation",
        type=float,
        nargs="+",
        default=list(DEFAULT_PARTICIPATION_GRID),
    )
    sensitivity.add_argument("--out", default=None)
    _add_cost_args(sensitivity)
    sensitivity.set_defaults(func=_cmd_sensitivity)

    rank = subparsers.add_parser("rank", help="run the strategy-ranking experiment")
    rank.add_argument("--panel", required=True, help="long-format CSV panel")
    rank.add_argument("--start", default=None)
    rank.add_argument("--end", default=None)
    rank.add_argument("--aum", type=float, default=250e6)
    rank.add_argument("--out", default=None)
    _add_cost_args(rank)
    rank.set_defaults(func=_cmd_rank)

    calibrate = subparsers.add_parser("calibrate", help="fit the impact coefficient")
    calibrate.add_argument("--observations", required=True)
    calibrate.add_argument("--cost-column", default="cost_bps")
    calibrate.add_argument("--sigma-column", default="sigma_daily")
    calibrate.add_argument("--participation-column", default="participation")
    calibrate.add_argument("--exponent", type=float, default=0.5)
    calibrate.add_argument("--bootstrap", action="store_true")
    calibrate.add_argument("--n-boot", type=int, default=1000)
    calibrate.add_argument("--seed", type=int, default=20261108)
    calibrate.add_argument("--out", default=None)
    calibrate.set_defaults(func=_cmd_calibrate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

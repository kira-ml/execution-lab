"""Spread-proxy sensitivity for the real-data rank flip.

The real-data check uses the Corwin-Schultz high-low estimator as the spread
proxy. That estimator can overstate the quoted spread, especially on volatile
days. This script reruns the ranking at several multipliers of the proxy and
reports whether the equal-weight-over-momentum flip survives.

Only aggregate results are written to ``docs/real-data``. The licensed snapshot
is read locally and is not redistributed.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from execution_lab.config import CostConfig, MarketConfig
from execution_lab.demo import STRATEGIES
from execution_lab.portfolio import CostModel, run_ranking_experiment
from execution_lab.report import (
    md_table,
    plot_spread_sensitivity,
    write_csv,
    write_text,
)

# ``run_real_data`` lives next to this script. Running the script directly puts
# this directory on sys.path, so the import is intentional and local.
from run_real_data import START, load_snapshot

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REAL = DOCS / "real-data"
MULTIPLIERS = (0.5, 0.75, 1.0, 1.5, 2.0)
AUM = 250e6
MODELS = (
    CostModel("gross", "gross"),
    CostModel("fixed_10bps", "fixed", fixed_bps=10.0),
    CostModel("impact_vwap_5d", "impact", schedule="vwap_5d"),
)


def main() -> None:
    panel = load_snapshot()
    end = panel.close.index[-1]
    rows = []
    for multiplier in MULTIPLIERS:
        result = run_ranking_experiment(
            panel,
            STRATEGIES,
            MODELS,
            start=START,
            end=end,
            portfolio_value=AUM,
            market_config=MarketConfig(spread_multiplier=multiplier),
            config=CostConfig(),
        )
        table = result.table.copy()
        table["spread_multiplier"] = float(multiplier)
        rows.append(table)
        print(f"spread x{multiplier:g}: done")

    all_rows = pd.concat(rows, ignore_index=True)
    REAL.mkdir(parents=True, exist_ok=True)
    write_csv(all_rows, REAL / "spread_sensitivity.csv")

    impact = all_rows[all_rows["model"] == "impact_vwap_5d"].copy()
    sharpes = impact.pivot(
        index="strategy", columns="spread_multiplier", values="sharpe"
    )
    ranks = impact.pivot(index="strategy", columns="spread_multiplier", values="rank")
    write_csv(sharpes.reset_index(), REAL / "spread_sensitivity_sharpes.csv")
    write_csv(ranks.reset_index(), REAL / "spread_sensitivity_ranks.csv")

    gap_rows = []
    for multiplier in MULTIPLIERS:
        subset = impact[impact["spread_multiplier"] == multiplier].set_index("strategy")
        gap_rows.append(
            {
                "spread_multiplier": multiplier,
                "equal_weight_sharpe": float(subset.loc["equal_weight", "sharpe"]),
                "momentum_sharpe": float(subset.loc["momentum", "sharpe"]),
                "equal_weight_minus_momentum": float(
                    subset.loc["equal_weight", "sharpe"]
                    - subset.loc["momentum", "sharpe"]
                ),
                "equal_weight_rank": int(subset.loc["equal_weight", "rank"]),
                "momentum_rank": int(subset.loc["momentum", "rank"]),
                "equal_weight_ahead": bool(
                    subset.loc["equal_weight", "rank"]
                    < subset.loc["momentum", "rank"]
                ),
            }
        )
    gaps = pd.DataFrame(gap_rows)
    write_csv(gaps, REAL / "spread_sensitivity_gap.csv")
    plot_spread_sensitivity(impact, REAL / "fig_spread_sensitivity.png")

    survives = bool(gaps["equal_weight_ahead"].all())
    disappears_at = gaps.loc[~gaps["equal_weight_ahead"], "spread_multiplier"].tolist()
    if survives:
        verdict = (
            "The equal-weight-over-momentum flip survives every multiplier in the "
            "grid. That makes it more credible, but it is still conditional on the "
            "impact model and the daily-data spread proxy."
        )
    else:
        verdict = (
            "The flip does **not** survive the full multiplier grid. It disappears at "
            f"spread multiplier(s) {disappears_at}. The honest headline is therefore "
            "that momentum is implementation-fragile, not that the rank order is "
            "robustly changed."
        )

    lines = [
        "# Spread-Proxy Sensitivity — Real-Data Check",
        "",
        "> **Data note:** local validation on the owner's licensed Yahoo Finance ETF "
        "snapshot. The raw data are not redistributed. This is a daily-data exercise, "
        "not an execution simulator.",
        "",
        "The real-data check uses the Corwin-Schultz high-low estimator as the spread "
        "proxy. That estimator can overstate the quoted spread. This analysis reruns "
        "the ranking at 0.5x, 0.75x, 1x, 1.5x, and 2x the proxy, holding everything "
        "else fixed.",
        "",
        "## Net Sharpe under 5-day VWAP impact",
        "",
        md_table(sharpes, floatfmt=".3f"),
        "",
        "## Ranks (1 = best)",
        "",
        md_table(ranks, floatfmt=".0f"),
        "",
        "## Equal weight vs momentum",
        "",
        md_table(gaps, floatfmt=".3f"),
        "",
        "![Spread sensitivity](real-data/fig_spread_sensitivity.png)",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## What this does and does not settle",
        "",
        "- It tests sensitivity to the *level* of the spread proxy, not to its "
        "cross-sectional shape or its correlation with volatility.",
        "- It does not identify the true quoted spread; that requires quote data.",
        "- It does not change the synthetic demo, which is a separate reproduction path.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python scripts/run_spread_sensitivity.py",
        "```",
        "",
    ]
    write_text("\n".join(lines), DOCS / "SPREAD_SENSITIVITY.md")
    print(f"wrote {DOCS / 'SPREAD_SENSITIVITY.md'}")
    print(f"flip survives all multipliers: {survives}")
    if disappears_at:
        print(f"flip disappears at: {disappears_at}")


if __name__ == "__main__":
    main()

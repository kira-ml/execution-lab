"""Local real-data check on the owner's licensed ETF snapshot.

This script is **not** part of the public reproduction path. It reads a vendor
snapshot from the sibling ``robustfolio`` repository, converts it to the lab's
long CSV contract in a temporary directory, runs the same pipeline, and copies
only aggregate tables and figures into ``docs/real-data/``. No raw prices are
committed or redistributed.

Usage::

    python scripts/run_real_data.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pandas as pd

from execution_lab.data import Panel, save_panel_csv
from execution_lab.demo import run_demo

ROOT = Path(__file__).resolve().parents[1]
TICKERS = [
    "SPY",
    "EFA",
    "EEM",
    "TLT",
    "IEF",
    "GLD",
    "HYG",
    "VNQ",
    "LQD",
    "IWM",
    "MDY",
    "AGG",
]
START = "2013-01-31"
OUT = ROOT / "results" / "real"
DOCS = ROOT / "docs" / "real-data"
REPORT = ROOT / "docs" / "REAL_DATA_CHECK.md"


def load_snapshot() -> Panel:
    candidates = list(
        (ROOT / "../robustfolio/data/snapshots")
        .resolve()
        .glob("yahoo-usetf*/prices_raw.parquet")
    )
    if not candidates:
        raise FileNotFoundError("no robustfolio yahoo-usetf snapshot found")
    path = candidates[0]
    raw = pd.read_parquet(path)
    missing = [t for t in TICKERS if t not in raw["close"].columns]
    if missing:
        raise ValueError(f"snapshot is missing tickers: {missing}")
    panel = Panel(
        close=raw["close"][TICKERS],
        high=raw["high"][TICKERS],
        low=raw["low"][TICKERS],
        open=raw["open"][TICKERS],
        volume=raw["volume"][TICKERS],
        spread_bps=None,
        source=f"licensed snapshot {path.name}",
    )
    return panel


def main() -> None:
    panel = load_snapshot()
    end = panel.close.index[-1]
    temp_path = Path(tempfile.gettempdir()) / "execution-lab-real-panel.csv"
    save_panel_csv(panel, temp_path)
    print(f"snapshot: {panel.close.shape[1]} tickers, {panel.close.index[0].date()} to {end.date()}")
    print(f"temporary panel: {temp_path}")

    result = run_demo(
        out_dir=OUT,
        data_path=temp_path,
        start=START,
        end=end,
        aum=250e6,
    )

    DOCS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT / "report.md", REPORT)
    header = (
        "# Real-Data Check — Execution & Market-Impact Lab\n\n"
        "> **Data note:** this is a local validation on the owner's licensed Yahoo "
        "Finance ETF snapshot. The raw snapshot is **not** redistributed. Only "
        "aggregate tables and figures are committed. This is not the public "
        "reproduction path; run `execution-lab demo` for the synthetic path.\n\n"
        "> **What it is:** a 12-ETF, daily-data exercise of the same accounting and "
        "sensitivity pipeline. It is still not an execution simulator and it still "
        "cannot identify `k`.\n\n"
        "> **Provenance:** this uses the separate Robustfolio ETF snapshot; it does "
        "not evaluate or consume the Epistemic DRO 2025–2026 holdout.\n\n"
        "> **Robustness:** the rank flip in this report is conditional on the spread "
        "proxy. See `SPREAD_SENSITIVITY.md` for the 0.5x–2x check; the flip disappears "
        "at 0.5x and is a tie at 0.75x.\n\n"
        "---\n\n"
    )
    original = REPORT.read_text(encoding="utf-8")
    if original.startswith("# "):
        original = "## Generated report\n\n" + original.split("\n", 1)[1].lstrip("\n")
    REPORT.write_text(header + original, encoding="utf-8")

    for name in (
        "ranking.csv",
        "ranking_sharpes.csv",
        "ranking_ranks.csv",
        "rank_changes.csv",
        "fragility.csv",
        "cost_decomposition.csv",
        "break_even_k.csv",
        "k_sensitivity.csv",
        "aum_sensitivity.csv",
        "aum_ranks.csv",
        "order_schedule_comparison.csv",
        "optimal_by_risk_aversion.csv",
        "manifest.json",
        "fig_ranking_heatmap.png",
        "fig_k_sensitivity.png",
        "fig_aum_sensitivity.png",
        "fig_cost_decomposition.png",
        "fig_schedule_frontier.png",
    ):
        source = OUT / name
        if source.exists():
            shutil.copy2(source, DOCS / name)

    print(f"wrote {REPORT}")
    print(f"aggregate artefacts: {DOCS}")
    print(f"report: {OUT / 'report.md'}")
    print(f"panel hash: {result['manifest']['panel_hash']}")


if __name__ == "__main__":
    main()

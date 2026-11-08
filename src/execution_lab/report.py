"""Report tables, Markdown, and figures.

The report is generated, not hand-edited. Figures use the non-interactive Agg
backend so the one-command demo works on a headless CI runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update(
    {
        "figure.dpi": 130,
        "savefig.dpi": 160,
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
    }
)


def _path(value: str | Path) -> Path:
    path = Path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def md_table(frame: pd.DataFrame, *, floatfmt: str = ".3f", max_rows: int = 40) -> str:
    """Render a compact GitHub-flavoured Markdown table without tabulate."""
    if frame.empty:
        return "_No rows._"
    view = frame.head(max_rows).copy()
    include_index = view.index.name is not None and view.index.name not in view.columns
    if include_index:
        view = view.reset_index()
    else:
        view = view.reset_index(drop=True)
    columns = [str(c) for c in view.columns]
    lines = ["| " + " | ".join(columns) + " |"]
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for _, row in view.iterrows():
        cells = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                if np.isnan(value):
                    cells.append("—")
                else:
                    cells.append(format(float(value), floatfmt))
            elif isinstance(value, (int, np.integer)):
                cells.append(str(int(value)))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    if len(frame) > max_rows:
        lines.append(f"\n_Showing {max_rows} of {len(frame)} rows._")
    return "\n".join(lines)


def pct(value: float, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return f"{100.0 * value:.{digits}f}%"


def write_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    path = _path(path)
    frame.to_csv(path, index=False)
    return path


def write_text(text: str, path: str | Path) -> Path:
    path = _path(path)
    path.write_text(text, encoding="utf-8")
    return path


def plot_cost_curve(frame: pd.DataFrame, path: str | Path) -> Path:
    """Expected cost vs participation for each schedule."""
    path = _path(path)
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for schedule, group in frame.groupby("schedule", sort=False):
        group = group.sort_values("target_participation")
        ax.plot(
            group["target_participation"] * 100.0,
            group["expected_cost_bps"],
            marker="o",
            markersize=3,
            linewidth=1.4,
            label=str(schedule),
        )
    ax.set_xscale("log")
    ax.set_xlabel("Order size (% of average daily volume, log scale)")
    ax.set_ylabel("Expected cost (bps of notional)")
    ax.set_title("Cost curve: spread + commission + square-root impact")
    ax.legend(fontsize=7, ncol=2, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_schedule_frontier(frame: pd.DataFrame, path: str | Path) -> Path:
    """Expected cost vs timing risk for the schedule menu."""
    path = _path(path)
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.scatter(
        frame["timing_risk_bps"],
        frame["expected_cost_bps"],
        s=38,
        color="#1f4e79",
        zorder=3,
    )
    for _, row in frame.iterrows():
        ax.annotate(
            str(row["schedule"]),
            (row["timing_risk_bps"], row["expected_cost_bps"]),
            textcoords="offset points",
            xytext=(4, 4),
            fontsize=7,
        )
    ax.set_xlabel("Timing risk (std. dev., bps of notional)")
    ax.set_ylabel("Expected cost (bps of notional)")
    ax.set_title("The execution trade-off: impact falls, timing risk rises")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_ranking_heatmap(sharpes: pd.DataFrame, path: str | Path) -> Path:
    """Strategy x cost-model net Sharpe heatmap."""
    path = _path(path)
    values = sharpes.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(max(6.5, 1.1 * sharpes.shape[1]), 3.6))
    image = ax.imshow(values, aspect="auto", cmap="RdYlGn")
    ax.set_xticks(np.arange(sharpes.shape[1]))
    ax.set_xticklabels(sharpes.columns, rotation=30, ha="right", fontsize=7)
    ax.set_yticks(np.arange(sharpes.shape[0]))
    ax.set_yticklabels(sharpes.index, fontsize=8)
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            value = values[i, j]
            text = "—" if not np.isfinite(value) else f"{value:.2f}"
            ax.text(j, i, text, ha="center", va="center", fontsize=7)
    ax.set_title("Net Sharpe by strategy and cost assumption")
    fig.colorbar(image, ax=ax, shrink=0.8, label="Sharpe")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_k_sensitivity(frame: pd.DataFrame, path: str | Path) -> Path:
    """Net Sharpe vs impact coefficient for each strategy."""
    path = _path(path)
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for strategy, group in frame.groupby("strategy", sort=False):
        group = group.sort_values("k")
        ax.plot(group["k"], group["sharpe"], marker="o", markersize=3, label=str(strategy))
    ax.set_xscale("log")
    ax.set_xlabel("Impact coefficient k (log scale)")
    ax.set_ylabel("Net Sharpe")
    ax.set_title("How much impact is too much?")
    ax.legend(fontsize=7, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_aum_sensitivity(frame: pd.DataFrame, path: str | Path) -> Path:
    """Net Sharpe vs AUM for each strategy."""
    path = _path(path)
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for strategy, group in frame.groupby("strategy", sort=False):
        group = group.sort_values("aum")
        ax.plot(group["aum"] / 1e6, group["sharpe"], marker="o", markersize=3, label=str(strategy))
    ax.set_xscale("log")
    ax.set_xlabel("Assets under management ($ millions, log scale)")
    ax.set_ylabel("Net Sharpe")
    ax.set_title("The capacity question: when does the ranking break?")
    ax.legend(fontsize=7, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_spread_sensitivity(frame: pd.DataFrame, path: str | Path) -> Path:
    """Net Sharpe vs spread multiplier for each strategy.

    ``frame`` must have ``spread_multiplier``, ``strategy``, and ``sharpe``
    columns, already filtered to one cost model.
    """
    path = _path(path)
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for strategy, group in frame.groupby("strategy", sort=False):
        group = group.sort_values("spread_multiplier")
        ax.plot(
            group["spread_multiplier"],
            group["sharpe"],
            marker="o",
            markersize=3,
            label=str(strategy),
        )
    ax.axvline(1.0, color="black", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.set_xlabel("Spread multiplier applied to the Corwin-Schultz proxy")
    ax.set_ylabel("Net Sharpe (5-day VWAP impact)")
    ax.set_title("Does the ranking survive a different spread assumption?")
    ax.legend(fontsize=7, frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_cost_decomposition(frame: pd.DataFrame, path: str | Path) -> Path:
    """Stacked average cost decomposition by strategy for one model."""
    path = _path(path)
    if frame.empty:
        return path
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    bottom = np.zeros(len(frame))
    for column, label in (
        ("weighted_spread_bps", "half-spread"),
        ("weighted_commission_bps", "commission"),
        ("weighted_impact_bps", "impact"),
    ):
        values = frame[column].to_numpy(dtype=float)
        ax.bar(frame["strategy"], values, bottom=bottom, label=label)
        bottom += values
    ax.set_ylabel("Weighted average cost (bps)")
    ax.set_title("Cost decomposition by strategy")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(fontsize=7, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def table_rows(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Select and copy columns, preserving order, for report tables."""
    available = [c for c in columns if c in frame.columns]
    return frame[available].copy()

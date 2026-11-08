"""Execution & Market-Impact Lab.

A transparent, daily-data execution-cost laboratory. It is deliberately small:
the contribution is the accounting, the schedule comparison, and the sensitivity
analysis, not a production execution engine.

Public API
----------
``Panel`` / ``make_synthetic_panel`` / ``load_panel_csv``
    Market data.
``CostConfig`` / ``MarketConfig``
    Frozen model parameters.
``make_schedule`` / ``schedule_candidates``
    Execution schedules.
``simulate_order`` / ``compare_schedules``
    Cost decomposition and schedule comparison.
``run_backtest`` / ``run_ranking_experiment``
    Portfolio integration and ranking sensitivity.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .config import CostConfig, MarketConfig
from .data import Panel, compute_market_state, load_panel_csv, make_synthetic_panel
from .portfolio import (
    Backtest,
    CostModel,
    apply_cost_model,
    run_backtest,
    run_ranking_experiment,
)
from .schedules import Schedule, make_schedule, schedule_candidates
from .simulator import ExecutionResult, compare_schedules, simulate_order

__all__ = [
    "__version__",
    "Panel",
    "MarketConfig",
    "CostConfig",
    "compute_market_state",
    "load_panel_csv",
    "make_synthetic_panel",
    "Schedule",
    "make_schedule",
    "schedule_candidates",
    "ExecutionResult",
    "simulate_order",
    "compare_schedules",
    "Backtest",
    "CostModel",
    "apply_cost_model",
    "run_backtest",
    "run_ranking_experiment",
]

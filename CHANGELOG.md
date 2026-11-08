# Changelog

## 0.1.0 — 2026-11-08

Initial build.

### Added

- `execution_lab` package with:
  - long-format panel validation, synthetic ETF generator, and point-in-time
    market state;
  - Corwin-Schultz high-low spread proxy;
  - half-spread, commission, and square-root impact cost primitives;
  - immediate, TWAP, VWAP, and POV schedules;
  - cost decomposition, timing risk, 95% cost, and CVaR;
  - target-weight portfolio backtest and cost-model integration;
  - strategy ranking across cost models, `k`, and AUM;
  - break-even `k`, analytic `k` decomposition, and calibration module;
  - Markdown/CSV/PNG reporting.
- `execution-lab` CLI: `demo`, `simulate`, `sensitivity`, `rank`, `calibrate`.
- Checked-in synthetic demo panel (seed `20261108`, 6 tickers, 2018–2024).
- 76 tests covering data validation, point-in-time state, cost accounting,
  schedule constraints, impact monotonicity, portfolio accounting, cost-model
  equivalence, calibration, CLI, and an end-to-end demo.
- GitHub Actions CI for Python 3.10–3.12.
- Method, limitations, data-license, decision, and results documentation.
- One-page brief.
- Local real-data check on the owner's licensed 12-ETF snapshot, aggregate-only:
  `docs/REAL_DATA_CHECK.md` and `docs/real-data/`.
- Spread-proxy sensitivity (0.5x–2x Corwin-Schultz): the rank flip is not robust;
  it disappears at 0.5x and is a tie at 0.75x. `docs/SPREAD_SENSITIVITY.md`.

### Known limitations

- Daily data cannot identify `k`; the model reports a range and a break-even.
- No order-book data, no intraday path, no live execution.
- The public demo is synthetic and is not an empirical claim.
- External review is pending.

### Decisions

- Owner override of the activation gate; recorded in `PROJECT_STATE.md` and
  `docs/DECISIONS.md`.
- Synthetic public demo to avoid vendor-data redistribution.
- No ML slippage model: there is no out-of-sample execution data to justify one.

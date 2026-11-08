# Project State — Execution & Market-Impact Lab

**Version:** 0.1.0  
**Date:** 2026-11-08  
**Status:** built, tested, demo-generated; external review and GitHub upload pending.

---

## Activation gate

The project was originally parked. The owner requested activation on 2026-11-08.
The gate in `../FUTURE_FLAGSHIPS_PLAN_2026-11-08.md` was **not** fully met:

- Robustfolio has `v1.1`, not `v1.1.1`.
- Robustfolio DOI and external check are pending.
- Epistemic DRO external reader and launch decision are pending.
- Portfolio page/synthesis status was not verified.

This is an **owner override**, recorded here and in `docs/DECISIONS.md`. It is
not described as a satisfied gate.

---

## Verified

These are facts from commands that were actually run:

- `python -m pytest` passes **75 tests**.
- `python -m execution_lab.cli demo --out results/demo` completes and writes
  `report.md`, tables, figures, and a manifest.
- The checked-in synthetic panel is `data/demo/etf_daily.csv`, 1,825 rows × 6
  tickers, hash `2d232864f1f92561` when loaded through the pipeline.
- The demo report labels the data as synthetic and makes no live-trading claim.
- The cost decomposition sums to the parent cost; slice shares sum to the order.
- Point-in-time market state on a truncated panel equals the full-panel state.
- The analytic `k` decomposition matches a direct cost run.
- The project builds and imports as an editable package.
- The local real-data check completed on the owner's licensed 12-ETF snapshot
  (2013-01-31 to 2026-09-29), producing aggregate-only tables in
  `docs/real-data/` and `docs/REAL_DATA_CHECK.md`. On that panel the ranking
  changes: equal weight overtakes momentum under realistic spread and impact.
  Momentum's net Sharpe crosses zero at roughly $28.8B AUM in the sample.

## Assumed

These are modelling choices, not measured facts:

- square-root impact with default `k = 0.5`;
- a 0.5 bp commission;
- a U-shaped 8-bin intraday volume profile;
- zero-drift random-walk timing risk;
- risk aversion `λ = 0.05` for the baseline schedule choice;
- the synthetic panel's factor structure and dispersion.

The demo reports sensitivity to `k`, AUM, and `λ` because these assumptions are
not identified by the data.

## Proposed / pending

- External reviewer with execution or microstructure experience.
- Tagged `v0.1.0` GitHub release.
- Public GitHub repository upload.
- External read of `docs/REAL_DATA_CHECK.md`; the local run is complete and the
  aggregate evidence is committed.
- Decide whether the real-data rank flip is robust enough to headline, or
  whether it stays a secondary check behind the synthetic public demo.

---

## Real-data check

The script `scripts/run_real_data.py` reads the owner's licensed Yahoo Finance ETF
snapshot from the sibling `robustfolio` repository, converts it to a temporary
long-format CSV, runs the same pipeline on 12 ETFs from 2013-01-31, and copies
**aggregate** tables and figures into `docs/real-data/`.

The raw snapshot is not committed or redistributed. The generated
`docs/REAL_DATA_CHECK.md` is the evidence, and it is still a daily-data exercise,
not an execution simulator.

**Status:** completed. The report and aggregate artifacts exist. The run is a
daily-data exercise, not an execution simulator; the ranking flip is a
model-conditional result, not a tradable claim.

---

## GitHub

The repository has not been uploaded. The in-app browser was opened at
`https://github.com/new`; GitHub redirected to the sign-in page, and the owner
will log in and create the public repository. The local directory is ready for a
first commit once the real-data check and final docs are in place.

---

## Definition of done for this project

- [x] Core decision and assumptions documented.
- [x] Baseline and evaluation explicit.
- [x] Tests pass.
- [x] One-command demo works from synthetic data.
- [x] Limitations and data-licensing constraints stated.
- [ ] One external reviewer/user recorded, or a documented attempt.
- [x] Release-ready brief.
- [ ] Tagged release and public repository.
- [ ] Frozen; no endless polishing.

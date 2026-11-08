# TODO — Execution & Market-Impact Lab

**Status:** v0.1.0 built. Remaining work is external review and release hygiene.

---

## Activation gate (historical)

- [ ] Robustfolio `v1.1.1` tag/release exists or documented hold.
- [ ] Robustfolio DOI published or documented hold.
- [ ] Robustfolio external check recorded or documented no-response.
- [ ] Epistemic DRO frozen at `v1.0.0`; no v4; holdout untouched. **`v1.0.0` tag observed; holdout untouched is not independently verified.**
- [ ] Epistemic DRO external reader recorded or documented no-response.
- [ ] Epistemic DRO launch decision recorded.
- [ ] Portfolio page and synthesis committed/published.
- [ ] Owner has 8–10 weeks of consistent weekly time — **overridden**; the build was requested on 2026-11-08.

**The gate was overridden by the owner on 2026-11-08.** See `PROJECT_STATE.md`.

---

## Phase 0 — Frame

- [x] Write the one-page problem/decision statement.
- [x] Define the user and the decision.
- [x] List non-goals and data constraints.
- [x] Write the pre-mortem and kill criteria.
- [x] Define the acceptance evidence.

## Phase 1 — Data and baseline

- [x] Choose the ETF universe and period for the demo.
- [x] Build the daily OHLCV/volume ingestion with validation.
- [x] Define the spread proxy and document limitations.
- [x] Build a naive fixed-bps baseline.
- [x] Build a conservative square-root impact baseline.
- [x] Freeze a small synthetic panel for public reproduction.
- [x] Add the Corwin-Schultz high-low spread estimator as the fallback proxy.

## Phase 2 — Simulator

- [x] Implement immediate, TWAP, VWAP, and POV schedules.
- [x] Compute expected cost and timing variance.
- [x] Add sensitivity to impact coefficient \(k\).
- [x] Add tests for monotonicity, limits, and accounting.
- [x] Produce a one-command demo.
- [x] Add a risk-aversion frontier.
- [x] Add 95% cost and CVaR.

## Phase 3 — Integration

- [x] Define a target-weight CSV schema compatible with Robustfolio exports.
- [x] Compare gross, fixed-cost, linear-cost, and impact-aware results.
- [x] Show ranking sensitivity across cost models and AUM.
- [x] Document when the ranking changes — and when it does not.
- [x] Write the limitations.

## Phase 4 — Evidence

- [x] Tests and CI.
- [x] Calibration module.
- [x] Short paper/brief.
- [x] Public GitHub repository and CI.
- [ ] One external reviewer.
- [ ] Tagged release.
- [ ] Freeze.

## Optional real-data check

- [x] Run the pipeline on the owner's licensed ETF snapshot locally.
- [x] Record aggregate results without redistributing raw data.
- [x] Record the observed rank flip: equal weight overtakes momentum under
      realistic spread and impact on the 12-ETF sample.
- [x] Record the capacity result: momentum's net Sharpe crosses zero around
      $28.8B AUM in the sample (interpolated, not a forecast).
- [ ] Ask an external reviewer to inspect the real-data aggregation.

## Open questions

- Which public intraday data, if any, is legally usable for a future calibration?
- Is a daily-data impact model defensible for a teaching project? Under what assumptions? **Current answer:** only as a ranking/sensitivity tool, never as a live simulator.
- Which existing portfolio should be the primary integration case? **Current answer:** the generic target-weight schema, with a synthetic demo book; a Robustfolio export can be plugged in without code changes.
- What is the minimum evidence that makes the cost model credible? **Current answer:** documented accounting, monotonicity tests, a `k` range, break-even analysis, and an honest statement that `k` is not identified.

# Reviewer Brief

**Project:** Execution & Market-Impact Lab v0.1.0  
**Reviewer profile sought:** execution, market microstructure, or quantitative
portfolio implementation.

The review is not a request to endorse a trading strategy. It is a request to
check whether the cost accounting and the claims are internally coherent and
honestly bounded.

---

## What to review

1. **Cost accounting**
   - Does the decomposition add up (half-spread + commission + impact)?
   - Are the units consistent (bps vs dollars vs notional)?
   - Is the half-spread treatment defensible for a marketable order?

2. **Schedule definitions**
   - Are the TWAP, VWAP, and POV fractions and volume fractions coherent?
   - Does VWAP have constant participation, as claimed?
   - Does POV respect its target or explicitly record when it is capped?

3. **Timing risk**
   - Is `σ · sqrt(x' M x)` the right implementation-shortfall risk under a
     zero-drift random walk?
   - Is it clearly separated from expected cost?
   - Is the arrival-price benchmark stated?

4. **Point-in-time discipline**
   - Do target weights use only data through `d−1`?
   - Is ADV/volatility/spread measured before the execution date?
   - Does the truncated-panel test actually catch leakage?

5. **Ranking experiment**
   - Do all cost models see the same trade list and gross path?
   - Is the rank-change arithmetic correct?
   - Does the report avoid claiming a rank flip when the cost difference is
     smaller than the gross gap?

6. **Claims and limits**
   - Is `k` presented as unidentified, with a range and break-even?
   - Is the synthetic demo clearly labelled?
   - Is the real-data check aggregate-only and clearly model-conditional?
   - Is there any live-trading or alpha claim that should be removed?

---

## Questions for the reviewer

- Is the square-root impact model with `k ∈ [0.1, 2.0]` a reasonable
  conservative range for ETF execution, or is the range wrong?
- Is the VWAP-vs-TWAP impact ordering (VWAP lower at the same horizon) a
  modelling artifact or an economically meaningful result?
- Is the timing-risk formula too large because it is measured against arrival
  rather than a VWAP benchmark? If so, what benchmark would you use?
- Is the Corwin-Schultz proxy appropriate for ETFs, or does it overstate the
  spread on high-volatility days?
- Does the POV horizon treatment (integer days, capped at `max_days`) match
  practice?
- Is the capacity stress (up to $50B) informative, or is it outside the model's
  range?

---

## How to reproduce

```bash
pip install -e ".[dev]"
python -m pytest
execution-lab demo --out results/review
```

Then read `results/review/report.md`. The checked-in synthetic panel is used by
default. The real-data check is aggregate-only and cannot be reproduced without
the licensed snapshot.

---

## What would block a release

- A cost-accounting error (a dropped term, a unit error, a double count).
- A look-ahead path in the portfolio backtest.
- A schedule that silently violates its own constraints.
- A claim of live-trading validity or tradable alpha.
- A report that presents `k` as a measured point estimate.

---

## What would improve the project but not block it

- An intraday dataset for out-of-sample calibration.
- A second benchmark (VWAP) for timing risk.
- A cross-asset impact extension.
- A reviewer note on the spread proxy.

---

## Ready-to-send request

**Subject:** Review request — execution-cost lab (30–45 minutes)

> I have built a small, reproducible execution-cost laboratory for ETF
> portfolios: https://github.com/kira-ml/execution-lab
>
> It decomposes cost into half-spread, commission, square-root impact, and
> timing risk; compares immediate, TWAP, VWAP, and POV; and shows how a strategy
> ranking changes with impact and AUM. The public demo is synthetic. A separate
> aggregate-only real-data check is included.
>
> I am looking for a 30–45 minute review of the accounting and the claims, not
> an endorsement of a strategy. The specific questions are in
> `docs/REVIEW.md`: is the Corwin-Schultz proxy appropriate for ETFs, is
> arrival-price timing risk the right benchmark, and is the square-root `k`
> range reasonable?
>
> If you can, please point to the strongest objection or the first place the
> accounting breaks. A short written response is enough.

## Record

| Date | Request | Status | Reviewer | Response | Strongest objection |
|---|---|---|---|---|---|
| 2026-11-08 | Initial reviewer brief prepared | Not sent | — | — | — |
| 2026-11-08 | Spread-proxy sensitivity completed; rank flip demoted | Not sent | — | — | — |
| 2026-11-08 | Request finalized; awaiting owner approval to send | Prepared, not sent | — | — | — |
| 2026-11-09 | Owner approved sending | Approved; no recipient specified | — | — | — |

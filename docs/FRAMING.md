# Framing — Applying the Mental Models

This project uses the 12-root mental-models framework as its decision discipline.
The purpose of this file is to make the reasoning auditable: which models were
selected, what artifact each produced, and which gates pass or remain open.

---

## 1. Decision and selector

**Decision:** build a transparent execution-cost laboratory that tests whether a
portfolio edge survives realistic costs.

**Selector:** a new project/feature calls for **1, 3, 4, 5, 9 + parsimony**. The
risk/uncertainty/deployment character of this project adds **2, 6, 8, 10, 12**.

| Model | Role in this project |
|---|---|
| 1. First Principles | Define cost as size × volatility × liquidity × urgency × schedule; set the noise floor |
| 2. Constraints / Opportunity Cost | The binding constraint is data identifiability; every extra feature trades against review time |
| 3. Decomposition | Data → costs → schedules → simulator → portfolio → report, with explicit contracts |
| 4. Orders of Magnitude | Fermi estimate the cost and timing-risk terms before building |
| 5. Inversion | Attack leakage, unit errors, synthetic overreach, and forced rank flips |
| 6. Bayesian | `k` has a prior range, not a posterior point estimate; report calibration limits |
| 7. Causal Hierarchy | Accounting identity + behavioral assumption; no causal market claim |
| 8. Information | Daily OHLCV has signal for ranking, not for intraday impact |
| 9. Expected Value | Choose the simplest model that supports the decision: schedule choice and ranking sensitivity |
| 10. Fat Tails / Ruin | Capacity stress; no live trading, so no capital ruin; capacity can still ruin the edge |
| 11. Convexity | Small reusable cost layer; downside bounded by research-only scope |
| 12. Feedback / Selection | Public demo, tests, CI, external review; no deployed policy to monitor |

---

## 2. Phase 1 — Frame and ground

### First principles

The irreducible facts:

- A trade consumes liquidity; the price paid depends on size relative to available
  volume, volatility, spread, and urgency.
- A schedule allocates the order across time and volume.
- Spreading reduces impact but exposes the order to price drift (timing risk).
- Daily OHLCV observes the day's range and volume, not the intraday path.

**Noise floor:** with daily data, the model cannot resolve intraday impact. The
smallest defensible claim is a conditional ranking under an assumed impact law.

### Constraint table

| Constraint | Binding? | Consequence |
|---|---|---|
| No order-book data | Yes | Stylised impact, no microstructure claim |
| `k` not identified | Yes | Range + break-even, not a point estimate |
| No vendor redistribution | Yes | Synthetic public demo |
| 8–10 week cap | Yes | No UI, no platform, small schedule menu |
| No live trading | Yes | No broker, no routing, no capital at risk |
| Reproducibility | Yes | Checked-in panel, fixed seed, one command |

### Architecture and interfaces

```
data.Panel ──► compute_market_state ──► MarketState
                                      │
schedules.Schedule ──► simulator.simulate_order ──► ExecutionResult
                                      │
portfolio.run_backtest ──► Backtest ──► apply_cost_model ──► CostedBacktest
                                      │
                              report / demo / CLI
```

Invariants:

- `Panel` fields share the same index and tickers; prices positive; high ≥ low.
- `Schedule.fractions` sum to 1; `volume_fractions` sum to the ADV-days used.
- `ExecutionResult` slice costs sum to the parent cost; slice shares sum to `Q`.
- `Backtest` weights sum to 1; trades are self-financing in the gross path.
- Cost models see the same trade list; only the cost assumption changes.

### Fermi estimate

Take a 10%-of-ADV order, daily volatility 1.4%, `k = 0.5`, quoted spread 7 bps:

```
impact ≈ 0.5 × 140 bps × sqrt(0.10) ≈ 22 bps
half-spread ≈ 3.5 bps
commission ≈ 0.5 bps
expected cost ≈ 26 bps
```

Timing risk for a 1-day VWAP ≈ `σ × sqrt(1/3) ≈ 0.58σ ≈ 81 bps`; for a 5-day
VWAP ≈ `σ × sqrt(5/3) ≈ 1.29σ ≈ 181 bps`.

**Implication:** timing risk dominates expected cost for volatile assets. The
optimal schedule is a risk-preference decision, not a pure cost minimisation.
This estimate is why the demo reports a frontier instead of a single “best”
schedule.

---

## 3. Phase 2 — Invert and falsify

| Failure vector | Test / kill criterion |
|---|---|
| Look-ahead in target weights | Weights use `d−1`; truncated-panel test |
| Units off by 1e4 or notional | bps↔dollar tests; decomposition sums |
| Impact decreases with size/vol | Monotonicity tests |
| Timing risk double-counted | Risk reported separately; objective labels λ |
| POV silently exceeds target | Metadata records target, actual, capped |
| Duplicate schedule inflates menu | Signature de-duplication |
| Synthetic results read as empirical | Prominent label; separate real-data check |
| Ranking forced to flip | Report stability with arithmetic reason |
| Scope creep to platform | No broker/network in package; non-goals |

**Kill criteria:** if the accounting does not add up, if point-in-time tests fail,
or if the demo cannot run from public data, the build is not acceptable.

---

## 4. Phase 3 — Audit information and causality

| Source | Signal | Limit |
|---|---|---|
| Daily close | returns, volatility | no intraday path |
| Daily high/low | range, spread proxy | range includes news |
| Daily volume | ADV, participation | no intraday profile |
| Synthetic panel | controlled dispersion | not a market |
| Observed execution costs | direct `k` evidence | needs external data |
| Order book | true liquidity | unavailable |

**Causal hierarchy:** the cost decomposition is an accounting identity given its
inputs. The impact equation is an observational approximation. The schedule
comparison is a counterfactual *under the model*. No claim is made that executing
a schedule would cause a particular market outcome.

**Bayesian stance:** `k` has a plausible prior range (roughly 0.1–2.0). Daily
data do not update it enough to justify a posterior point estimate. The output is
a sensitivity range and a break-even, not a posterior mean.

---

## 5. Phase 4 — Decide and build the simplest baseline

**Decision memo:** build the smallest model that supports the decision:

1. Gross returns (no cost).
2. Fixed 10 bps (the naive baseline).
3. Spread + commission (linear).
4. Square-root impact (conservative).
5. Schedule comparison (immediate/TWAP/VWAP/POV).

No ML model is added. There is no out-of-sample execution dataset to justify one,
and a learned slippage model would not change the main conclusion: the ranking is
conditional on an unidentified `k`.

**Payoff map:**

- Downside bounded: research-only, no capital, no live orders.
- Upside open: reusable cost layer for Robustfolio/Epistemic DRO; public
  demonstration of implementation awareness; a bridge to a risk cockpit.
- Cost: a small package, a synthetic demo, and documentation.

---

## 6. Phase 5 — Deploy and monitor

There is no deployed trading policy, so the monitoring plan is about the
**research artefact**, not the market:

- CI runs tests and the demo on Python 3.10–3.12.
- The demo manifest records the panel hash and parameters.
- The report pairs cost with timing risk, turnover, ranking, and capacity.
- The real-data check is aggregate-only and separate from the public demo.
- External review is the remaining gate; if it does not happen after two asks,
  freeze and document rather than polish indefinitely.

**Goodhart counter-metrics:** cost alone is gameable. The report always pairs it
with timing risk, turnover, rank sensitivity, and the AUM at which the edge
crosses zero.

---

## 7. Gates

| Gate | Status | Evidence |
|---|---|---|
| No silent leakage | Pass | Point-in-time state test; `d−1` weights |
| No complexity without a baseline | Pass | Gross → fixed → linear → impact |
| No single-metric deployment | Pass | Cost + risk + turnover + rank + capacity |
| No causal policy without a causal argument | N/A | No policy intervention |
| No optimization without a binding constraint | Pass | Data identifiability is binding |
| No feasibility claim without an order-of-magnitude estimate | Pass | Fermi estimate above |
| No architecture without interfaces | Pass | Module map and invariants |
| No scale without a feedback/holdout plan | Partial | Capacity stress; no live deployment |
| No ruinous downside | Pass | No live trading |
| No uncalibrated certainty | Pass | `k` range, break-even, bootstrap module |

---

## 8. What would change the decision

- A legally usable intraday dataset that identifies `k` out of sample.
- An external reviewer who finds a unit/accounting error.
- A portfolio integration that shows the ranking is unstable on real data.
  **Observed:** the local 12-ETF check does show a rank flip — equal weight
  overtakes momentum under realistic spread and impact. That is evidence against
  treating the synthetic stability as general.
- A scope request for live routing — that is a different project, and the answer
  is no.

The one question that routes every future choice:

> **What decision does this change, what is the binding constraint, and how could
> I be wrong?**

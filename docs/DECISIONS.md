# Decisions, Constraints, and Pre-Mortem

This file records the decisions that shaped v0.1.0. It follows the project's
default reasoning protocol: frame the mechanism, invert the claim, audit the
information, choose the simplest baseline, and define the deployment boundary.

---

## 1. Decision memo

**Decision:** build a transparent execution-cost laboratory that answers whether
a portfolio edge survives realistic costs, and how the strategy ranking changes
with order size, impact coefficient, and AUM.

**Why now:** the owner requested it on 2026-11-08. The original plan parked the
project behind an activation gate. The gate was not fully met:

- Robustfolio has `v1.1`, not `v1.1.1`;
- the Robustfolio DOI and external check are pending;
- the Epistemic DRO external reader and launch decision are pending;
- the portfolio page/synthesis status was not verified.

**Decision:** proceed on explicit owner override, record the override, and do not
describe the gate as satisfied. The build is scoped to the part that does not
depend on the missing gate items: the cost model, simulator, portfolio
integration, sensitivity, tests, and demo.

**What would reverse the decision:** if the owner wants the parked gate enforced,
stop and archive the build. If the model cannot be made internally consistent or
if the demo cannot run from public data, stop and narrow to a method note.

---

## 2. Constraint table

| Constraint | Type | What it binds | Response |
|---|---|---|---|
| No order-book data | Data | Cannot claim microstructure realism | Daily-data stylised model; explicit limitation |
| `k` not identified | Statistical | Cannot report a point estimate | Grid, implied `k`, break-even `k` |
| One asset class | Scope | Cannot claim cross-asset generality | ETFs only |
| 8–10 week effort cap | Time | Cannot build a platform | Small package, one demo, no UI |
| No vendor redistribution | Legal | Public demo cannot use raw prices | Synthetic panel; local real-data check aggregate only |
| No live trading | Safety | Cannot validate fills | No broker, no routing |
| Reproducibility | Engineering | Demo must run offline | Checked-in synthetic panel and fixed seed |
| Multiple comparisons | Statistical | A large schedule grid would overfit | Pre-declared menu of four families |

**Binding constraint:** data. Daily OHLCV cannot identify intraday impact. The
entire design follows from that: the contribution is the accounting and the
sensitivity, not a calibrated execution simulator.

---

## 3. Pre-mortem

| Failure vector | How it would show up | Mitigation |
|---|---|---|
| The model looks precise but is not identified | A single `k` and a single cost number | Always report a range and a break-even |
| Synthetic results are read as empirical | “Momentum has Sharpe 0.24” without the label | Prominent synthetic-data label; separate real-data check |
| Ranking experiment is rigged by a cost model | One schedule gets a hidden advantage | Same trade list for every model; pre-declared menu |
| Timing risk is double-counted | Risk added to expected cost | Risk is separate; objective explicitly labels λ |
| Span/impact units are wrong | Costs off by 1e4 or by notional | Unit tests on bps↔dollars; decomposition sums |
| Look-ahead in the portfolio backtest | Target weights use the execution close | Weights through `d-1`; truncated-panel test |
| POV silently violates its target | Actual rate above the target | Metadata records target, actual, capped |
| A duplicate schedule inflates the menu | POV equals VWAP 1d | De-duplicate by fractions/volume/time signature |
| Scope creep into a trading platform | Broker adapters, UI, live data | Hard non-goals; no network in the package |
| External review never happens | “Done” without a reader | Record attempts; freeze rather than polish |

**Kill criteria:** if the cost decomposition does not add up, if the point-in-time
tests fail, or if the demo cannot run from the checked-in panel, the build is not
acceptable.

---

## 4. Information audit

| Source | Signal | Noise / limitation | Use |
|---|---|---|---|
| Daily close | Return, volatility | Close-to-close, no intraday path | Strategy returns, timing-risk scale |
| Daily high/low | Range, spread proxy | Range includes volatility and news | Corwin-Schultz spread |
| Daily volume | ADV, participation | Daily aggregate, no intraday profile | Order sizing, impact |
| Synthetic panel | Controlled dispersion | Not a market | Exercise the method |
| Observed execution costs | Direct `k` evidence | Requires a separate dataset | Calibration, if available |
| Order book | True liquidity | Not available | Not used |

**Information conclusion:** the daily data has enough signal to rank schedules
under a common impact assumption and to show capacity sensitivity. It does not
have enough signal to estimate intraday impact. The lab is honest about the
difference.

---

## 5. Causal hierarchy

The model is an **accounting identity plus a behavioral assumption**:

- the cost decomposition is an identity given the assumed spread, commission,
  and impact;
- the impact equation is an observational approximation, not a causal estimate
  of a price response;
- the schedule comparison is a counterfactual under the model, not a randomized
  experiment.

There is no policy intervention and no causal claim about markets. The correct
reading is: “under this model, schedule A costs less than schedule B.” Not:
“executing schedule A would have caused a better fill in the market.”

---

## 6. Risk register

| Risk | Severity | Mitigation | Residual |
|---|---|---|---|
| Model risk: square-root impact is wrong | High | Sensitivity to `k`, exponent, and mode | Unresolved; stated |
| Data risk: spread proxy is noisy | Medium | Floor/cap, trailing median, limitation | Unresolved; stated |
| Capacity risk: impact grows with AUM | High | AUM stress to $50B; zero-crossing table | Model-dependent |
| Metric risk: lower cost hides higher risk | High | Cost + timing risk + turnover + rank | Managed by reporting |
| Overfitting risk: schedule menu too large | Medium | Pre-declared 10-schedule menu | Low |
| Reproducibility risk: synthetic data drift | Low | Fixed seed, manifest hash, test | Low |
| Scope risk: trading platform | High | No broker, no routing, no UI | Controlled |
| Review risk: no external reader | Medium | Record attempts; freeze | Pending |

No ruinous downside: the project cannot place orders or lose capital. The
“survival” constraint applies to the research claim, not to a trading book.

---

## 7. Gates

| Gate | Status | Evidence |
|---|---|---|
| No silent leakage | Pass | Point-in-time state test; weights through `d-1` |
| No complexity without a baseline | Pass | Gross, fixed 10bps, linear, impact |
| No single-metric deployment | Pass | Cost + timing risk + turnover + rank + capacity |
| No causal policy without a causal argument | N/A | No policy intervention |
| No optimization without a binding constraint | Pass | Data/identifiability is the binding constraint |
| No feasibility claim without an order-of-magnitude estimate | Pass | 10% ADV order costs ~16–31 bps in the demo |
| No architecture without interfaces | Pass | `data → costs → schedules → simulator → portfolio → report` |
| No scale without a feedback/holdout plan | Partial | AUM stress and `k` grid; no live monitoring (no deployment) |
| No ruinous downside | Pass | No live trading; research-only |
| No uncalibrated certainty | Pass | `k` range, break-even, bootstrap module |

---

## 8. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-11-08 | Activate on owner override | Explicit owner request; gate not met |
| 2026-11-08 | Synthetic public demo | No vendor redistribution; offline reproducibility |
| 2026-11-08 | Daily-data square-root model | Simplest defensible model; `k` not identified |
| 2026-11-08 | Four schedule families, small menu | Charter requirement; limits multiple testing |
| 2026-11-08 | Default risk aversion 0.05 | Small penalty; demo reports frontier |
| 2026-11-08 | Timing risk vs arrival | Standard implementation shortfall; documented |
| 2026-11-08 | De-duplicate POV/VWAP | Avoid counting the same schedule twice |
| 2026-11-08 | No ML slippage model | No out-of-sample execution data; would be decorative |
| 2026-11-08 | Real-data check aggregate only | License and redistribution constraints |

---

## 9. Open questions

1. Which legally usable intraday dataset would identify `k` out of sample?
2. Should the primary benchmark be arrival or VWAP for a real desk?
3. Which portfolio should be the first production integration: Robustfolio or
   Epistemic DRO weights?
4. What is the minimum external review that makes the cost model credible?
5. Does the ranking stability in the synthetic demo survive on real data, or is
   it an artifact of the generated dispersion?

Question 5 is the most important. The real-data check is the first attempt at an
answer; it is not a substitute for an external reader.

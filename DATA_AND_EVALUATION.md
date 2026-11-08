# Data and Evaluation — Execution & Market-Impact Lab

**Status:** implemented in v0.1.0. The public demo uses a synthetic panel; the
real-data path is a documented CSV contract.

---

## 1. Data sources

| Layer | Implementation | Notes |
|---|---|---|
| ETF daily OHLCV | Long-format CSV: `date,ticker,open,high,low,close,volume[,spread_bps]` | Validate splits/dividends; no raw redistribution |
| Dollar volume | Derived from price × volume | Use a consistent price convention |
| Spread proxy | Observed `spread_bps` if supplied; otherwise Corwin-Schultz (2012) high-low estimator | The proxy is not a live quote |
| Intraday bars | Not used | The schedules use a stylised U-shaped intraday volume profile |
| Order book | Not available | Do not claim order-book realism |
| Demo panel | Synthetic, seed `20261108`, six stylised ETFs, 2018-01-02 to 2024-12-30 | Checked in at `data/demo/etf_daily.csv` |

### Why synthetic for the public demo

The public repository must be reproducible without redistributing vendor data.
The synthetic panel is deterministic and deliberately stylised: a common market
factor with volatility clustering, fat-tailed idiosyncratic returns, a 2020-like
shock, volume seasonality, and time-varying spreads. It is **not** calibrated to
real ETFs. Its purpose is to exercise the accounting and sensitivity machinery.

### Real-data path

The real-data check uses the 12-ETF Robustfolio US ETF universe. Equal weight is
one of Robustfolio's published baselines, reconstructed from prices; the actual
walk-forward weights are not exported by that project, so the integration is via
the documented target-weight schema rather than a live cross-repo import.

A user with a licensed snapshot converts it to the long-format CSV outside the
repository and runs:

```bash
execution-lab rank --panel path/to/panel.csv --start 2013-01-31 --end 2026-09-29
execution-lab demo --panel path/to/panel.csv --out results/local
```

The repository does not include the vendor snapshot. A local validation on the
owner's licensed ETF snapshot is recorded separately in
[`docs/REAL_DATA_CHECK.md`](docs/REAL_DATA_CHECK.md), with aggregate results only.

---

## 2. Licensing

- No raw vendor data in the public repo, release, or demo.
- No snapshot redistribution.
- Public demos use synthetic or aggregate data.
- Check terms before publishing any derived figure that reconstructs raw values.
- The synthetic generator and the code are MIT-licensed.

See [`docs/DATA_LICENSES.md`](docs/DATA_LICENSES.md).

---

## 3. Baselines

1. **Gross** — no cost.
2. **Fixed 10 bps** — the naive assumption used by many student backtests.
3. **Spread + fixed fee** — a slightly more realistic linear baseline.
4. **Square-root impact** — conservative range, not a point estimate.
5. **Schedule comparison** — immediate vs TWAP vs VWAP vs POV.
6. **Optimal schedule** — minimum expected cost + risk-aversion × timing risk, chosen from a pre-declared menu.

---

## 4. Core metrics

- Expected cost in bps: half-spread + commission + impact.
- Timing risk: standard deviation of implementation shortfall vs arrival.
- 95% cost and 95% CVaR under a normal approximation.
- Turnover: one-way annualised.
- Cost drag: annualised bps of average portfolio value.
- Net return and net Sharpe.
- Ranking change versus gross and versus fixed 10 bps.
- Sensitivity to impact coefficient \(k\): grid and break-even.
- Sensitivity to AUM: net Sharpe and rank.
- Out-of-sample calibration error if observed execution costs are available.

---

## 5. Validation

- Unit tests for cost accounting and schedule constraints.
- Monotonicity checks: larger orders, higher volatility, and larger `k` do not reduce impact under the model.
- VWAP has lower impact than TWAP at the same horizon under a concave impact model.
- Immediate execution has exactly zero timing risk.
- Point-in-time checks: `compute_market_state` on the full and truncated panel agree.
- Portfolio accounting: gross PV starts at the initial capital; fixed costs reduce net PV.
- Cost-model equivalence: the analytic `k` decomposition matches a direct cost run.
- Sensitivity table for \(k\).
- Spread-proxy sensitivity for the real-data check: 0.5x, 0.75x, 1x, 1.5x, and 2x
  the Corwin-Schultz estimate, with the rank-flip verdict.
- One-command demo on synthetic data.
- A reviewer with execution/microstructure experience — **pending**.

---

## 6. Honest limitations

- Daily data cannot identify intraday liquidity or order-book shape.
- The square-root model is a stylised approximation.
- Spread proxies are noisy.
- Timing risk is measured against the arrival price, not a VWAP benchmark.
- The model prices expected cost; it does not simulate an execution path.
- The project is a teaching/engineering tool, not a production execution system.
- No live-trading claim.

---

## 7. Counter-metrics

Do not report only “lower cost.” Pair cost with:

- timing risk;
- turnover;
- ranking sensitivity;
- implementation complexity;
- capacity (AUM at which the edge crosses zero).

A lower-cost schedule that creates more timing risk or requires unavailable data
is not obviously better.

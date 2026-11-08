# Method — Execution & Market-Impact Lab

This document is the model contract. It states the equations, the units, the
point-in-time rules, and what the model deliberately does not do. If the code and
this document disagree, the code is wrong.

---

## 1. Notation

| Symbol | Meaning | Units |
|---|---|---|
| `Q` | Parent order size (absolute shares) | shares |
| `P` | Arrival price | currency / share |
| `N = QP` | Parent order notional | currency |
| `V` | Average daily volume (ADV) | shares / day |
| `σ` | Daily return volatility | return / day |
| `s` | Quoted bid-ask spread | bps |
| `k` | Impact coefficient | dimensionless |
| `x_i` | Fraction of the parent order in slice `i` | dimensionless, Σx = 1 |
| `v_i` | Volume available in slice `i`, in ADV-days | ADV-days |
| `t_i` | Slice midpoint time from arrival | trading days |
| `p_i` | Participation of slice `i` | fraction of slice volume |

All costs are reported in basis points of the parent notional unless the name
says dollars. One basis point is `1e-4` in return units.

---

## 2. Point-in-time rules

For a rebalance at date `d`:

1. Target weights use prices through the **previous trading day** `d-1`.
2. The execution price is the close of `d`.
3. ADV, volatility, and spread are measured through `d-1`, so the execution
   day's volume is not used to size the order.
4. The gross return path is close-to-close.
5. Costs are deducted in dollars on `d` and compound thereafter.

`compute_market_state(panel, asof)` slices the panel first and computes second.
A test asserts that calling it on the full panel and on a panel truncated at
`asof` returns identical values.

The one deliberate exception is the single-order illustration in the demo: it
prices an order at the final panel date using that day's observed state. It is an
ex-post illustration, not a backtest and not a tradable signal.

---

## 3. Cost decomposition

```
expected_cost_bps = s/2 + commission_bps + impact_bps
expected_cost      = expected_cost_bps / 1e4 · N
```

The half-spread is the cost of crossing the quoted spread. The commission is a
flat bps fee. Impact is the square-root model below. The decomposition is
additive by construction, and a test checks that the slice costs sum to the
parent cost.

### Why half-spread, not the full spread

A marketable order pays roughly half the quoted spread to cross; the other half
is the compensation to the resting side. Using the full spread would double-count
the cost for a one-way order. If the order is patient and posts, the sign could
reverse; the model does not simulate limit orders.

---

## 4. Spread proxy

If the panel supplies `spread_bps`, it is treated as an observed quoted spread,
winsorised to the configured floor and cap, and a trailing median is used. If it
does not, the Corwin-Schultz (2012) high-low estimator is computed:

```
H_t, L_t              daily high and low
h_t = ln(H_t / L_t)

β  = h_t² + h_{t+1}²
γ  = [ln(max(H_t, H_{t+1}) / min(L_t, L_{t+1}))]²
α  = (√(2β) − √β) / (3 − 2√2) − √(γ / (3 − 2√2))
S  = 2(e^α − 1) / (1 + e^α)
```

Negative `S` values are set to NaN rather than zero: a negative estimate means
the estimator is outside its assumptions, not that the spread is zero. The
trailing median is taken over `spread_window` days, then floored and capped.

This is a daily-data proxy. It is not a quote, and it cannot separate spread from
news-driven range on a given day.

---

## 5. Impact model

For each slice:

```
participation_i = Q · x_i / (V · v_i)
impact_i        = k · σ_bps · participation_i^exponent
impact_total    = Σ x_i · impact_i
```

where `σ_bps = σ · 1e4`. The default exponent is `0.5` (square-root law); `1.0`
is available as a linear falsification case.

Two modes:

- **`per_slice` (default):** impact is computed slice by slice. A schedule that
  trades more in a high-volume slice has lower impact. This is the economically
  meaningful mode.
- **`total`:** impact is computed once on the total order using
  `Q / (V · Σv_i)`, so schedules with the same horizon have the same impact and
  differ only in timing risk. This is a sensitivity case, not the primary model.

### The coefficient is not identified

Daily OHLCV cannot identify `k`. The demo therefore reports:

- a grid `k ∈ {0.1, 0.25, 0.5, 1.0, 2.0}`;
- a break-even `k` at which a strategy's net Sharpe equals its fixed-10bps
  Sharpe or zero;
- an implied `k` for any observed cost, if the user has execution data.

A point estimate of `k` from this dataset would be false precision. The range is
the result.

---

## 6. Schedules

A schedule is a vector of slices, each with `(x_i, v_i, t_i)`.

### Immediate

```
x = [1], v = [1], t = [0]
```

Impact is paid on the full order against one day's volume. Timing risk is zero
relative to arrival by construction.

### TWAP

Equal shares per time bin:

```
x_i = 1 / (D · B)
v_i = profile_b
t_i = d + (b + 0.5) / B
```

for day `d = 0..D-1` and bin `b = 0..B-1`, where `profile` is a U-shaped
intraday volume profile summing to one. Because `x` is uniform but `v` is not,
TWAP over-participates in quiet periods and has higher impact than VWAP at the
same horizon.

### VWAP

Shares proportional to expected volume:

```
x_i = w_d · profile_b
v_i = w_d · D · profile_b
t_i = d + (b + 0.5) / B
```

where `w_d` are day weights summing to one. Then:

```
participation_i = Q · x_i / (V · v_i) = Q / (V · D)
```

constant across every slice. That is the defining property of VWAP and the reason
it is impact-efficient for a fixed horizon under a concave impact model.

### POV

Given a target participation rate `p`:

```
D = ceil(Q / (p · V))
```

The schedule is VWAP over `D` days. The achieved rate is `Q / (V · D) ≤ p`.
If `D` exceeds `max_days`, the horizon is capped and the achieved rate is higher
than requested; the metadata records `capped=True`, `required_days`, and both
rates. A POV rate above the order's participation collapses to one day and is
identical to VWAP 1d; the menu de-duplicates it rather than counting the same
schedule twice.

### The menu

The comparison menu is pre-declared, not optimised over a large grid:

```
immediate
twap_{1,3,5}d
vwap_{1,3,5}d
pov_{5,10,20}pct
```

with 8 intraday bins. This keeps the multiple-testing problem small and the
comparison interpretable.

---

## 7. Timing risk

For slice fractions `x` and midpoint times `t` in trading days, the
implementation shortfall under a zero-drift random walk has variance:

```
Var = σ² · x' M x,    M_ij = min(t_i, t_j)
timing_risk_bps = σ_bps · sqrt(x' M x)
```

The dollar risk is `timing_risk_bps / 1e4 · N`. Immediate execution has all
`t_i = 0`, so `M = 0` and the risk is exactly zero. A 1-day VWAP has
`x' M x ≈ 1/3`; a 5-day VWAP has `≈ 5/3`, so the risk grows with the square root
of the horizon.

This is a risk measure, not an expected cost. It is never added to expected cost
unless the schedule objective explicitly does so.

Under a normal approximation:

```
95% cost = expected_cost + 1.6449 · timing_risk
95% CVaR = expected_cost + 2.0627 · timing_risk
```

The normal approximation is a reporting convenience, not a claim about the tail.
Real execution cost can be more skewed.

---

## 8. Schedule objective and frontier

The default objective is:

```
objective = expected_cost_bps + λ · timing_risk_bps
```

`λ` is a preference, not a measured constant. The demo uses `λ = 0.05` as a small
penalty and reports the frontier over:

```
λ ∈ {0, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0}
```

At `λ = 0` the cheapest expected-cost schedule wins. At high `λ` immediate
execution wins because its timing risk is zero. The switch point is an output,
not an assumption.

---

## 9. Portfolio integration

A target-weight strategy produces weights `w_t`. At each rebalance:

```
PV_pre       = cash + Σ shares_i · price_i
current_i    = shares_i · price_i / PV_pre
target_i     = w_i
target_shares_i = w_i · PV_pre / price_i
trade_i      = target_shares_i − shares_i
```

The first rebalance is funded from cash. The backtest is buy-and-hold between
rebalances: shares are constant, cash is zero after the first rebalance, and the
portfolio value is `Σ shares_i · price_i`. There is no forced liquidation at the
end.

Costs are deducted in dollars on the rebalance date:

```
net_PV_t = net_PV_{t−1} · (1 + gross_return_t) − cost_t
```

This compounds the net path rather than subtracting a constant bps drag. The
gross path is scale-free; only the cost depends on AUM.

### Cost models

| Name | Definition |
|---|---|
| `gross` | zero |
| `fixed_10bps` | 10 bps × trade notional |
| `spread_plus_fee` | half-spread + commission |
| `impact_*` | schedule-specific square-root impact |
| `impact_optimal` | min objective over the pre-declared menu, per trade |

Every model sees the same trade list and the same gross path. That is what makes
the ranking comparison fair.

---

## 10. Ranking experiment

For each strategy and cost model, report:

- annualised net return and volatility;
- net Sharpe (risk-free rate zero);
- maximum drawdown;
- one-way annualised turnover;
- annualised cost drag in bps;
- average cost per traded notional in bps;
- rank by net Sharpe.

`rank_change_vs_gross = rank_model − rank_gross`; positive means worse.

A rank change requires the **cost difference** between two strategies to exceed
their **gross Sharpe gap**. If the gap is larger, the ranking is stable even when
costs are material. The report says which case occurred rather than forcing a
rank flip.

---

## 11. Break-even `k` and capacity

Because impact is linear in `k` for a fixed schedule:

```
cost_t(k) = cost0_t + k · cost1_t
```

The demo runs the backtest once, extracts `cost0` and `cost1` per rebalance, and
evaluates net Sharpe at any `k` analytically. `break_even_k` bisects for the `k`
at which net Sharpe equals a target (the fixed-10bps Sharpe or zero). The bracket
is `[0, 10]`; a target outside it is reported as `None`.

The AUM sensitivity reruns the backtest at each AUM and reports net Sharpe and
rank. The zero-crossing AUM is a linear interpolation between grid points, not a
capacity estimate.

---

## 12. Calibration

If observed execution costs are available:

```
cost_bps = k · σ_bps · participation^exponent + error
```

Fit `k` by OLS through the origin, report the standard error and a percentile
bootstrap interval. With one observation, report the implied `k` and say it is an
assumption, not a calibration. With no observations, report the sensitivity
range.

---

## 13. Validation that could fail

The tests are designed to fail if the model is internally inconsistent:

- slice costs sum to the parent cost;
- slice shares sum to the parent order;
- immediate timing risk is exactly zero;
- longer horizons have higher timing risk;
- VWAP has lower impact than TWAP at the same horizon;
- spreading reduces impact under `per_slice`;
- total mode is schedule-independent for the same horizon;
- larger orders, higher volatility, and larger `k` do not reduce impact;
- the analytic `k` decomposition matches a direct cost run;
- point-in-time state on a truncated panel equals the full-panel state.

What the tests cannot establish is external validity: that the model predicts
real fills. That requires execution data and an out-of-sample calibration.

---

## 14. References

- Almgren, R., Thum, C., Hauptmann, E., & Li, H. (2005). Direct estimation of
  equity market impact. *Risk*, 18(7), 57–62.
- Corwin, S. A., & Schultz, P. (2012). A simple way to estimate bid-ask spreads
  from daily high and low prices. *Journal of Finance*, 67(2), 719–760.
- Perold, A. F. (1988). The implementation shortfall: Paper versus reality.
  *Journal of Portfolio Management*, 14(3), 4–9.

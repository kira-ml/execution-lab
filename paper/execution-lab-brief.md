# Does the edge survive implementation?

**A one-page brief for the Execution & Market-Impact Lab**  
Ken Ira Lacson Talingting · 2026-11-08 · v0.1.0

---

## The question

A backtest that subtracts 10 bps assumes away the hardest part of implementation.
Real cost depends on order size, volatility, liquidity, spread, urgency, and
schedule. The lab asks three questions:

1. For a target portfolio and rebalance, which schedule minimizes expected cost
   plus timing risk?
2. How much does realistic impact change the ranking of strategies?
3. Which strategies are implementation-fragile, and at what AUM does the edge
   disappear?

## The method

For an order of `Q` shares at price `P`, daily volatility `σ`, average daily
volume `V`, and quoted spread `s`:

```
expected_cost = s/2 + commission + k · σ · (Q/V)^0.5
```

A schedule changes the participation of each slice and therefore impact. Timing
risk is the standard deviation of implementation shortfall against the arrival
price:

```
timing_risk = σ · sqrt(x' M x),    M_ij = min(t_i, t_j)
```

where `x` are slice fractions and `t` are times in days. Immediate execution has
zero timing risk by construction; spreading the order lowers impact but adds
risk. The schedule objective is `expected_cost + λ · timing_risk`.

The lab compares immediate, TWAP, VWAP, and POV. VWAP is impact-efficient because
it matches expected volume; POV chooses its horizon from the target participation
rate. The model is deliberately small: daily data, no order book, no intraday
path, no live trading.

## The demo result

On a **synthetic** six-ETF panel (seed `20261108`, 2018–2024), a 10%-of-ADV order
in the least-liquid asset:

| Schedule | Expected cost (bps) | Timing risk (bps) | Objective at λ = 0.05 |
|---|---:|---:|---:|
| VWAP 5-day | 16.12 | 221.41 | **27.19** |
| TWAP 5-day | 16.39 | 221.63 | 27.47 |
| VWAP 3-day | 19.65 | 171.26 | 28.21 |
| Immediate | 31.12 | 0.00 | 31.12 |

The cheapest schedule is not the best schedule. At `λ = 0.05`, the 5-day VWAP
wins; at `λ ≥ 0.10`, immediate execution wins. The conclusion is a function of the
risk preference, not a universal fact.

For the strategy ranking at $250M AUM, the ordering is stable across gross,
fixed-10bps, linear, and impact-aware costs. The reason is arithmetic: the cost
differences between adjacent strategies are smaller than their gross Sharpe gaps.
The largest impact loss belongs to momentum (0.026 Sharpe), which is already last
by a wide margin.

Capacity still binds. As AUM rises, momentum's net Sharpe falls from 0.23 at $25M
to −0.07 at $50B; the low-turnover strategies survive. The AUM at which momentum's
net Sharpe crosses zero is roughly $32B in this synthetic panel. That is a stress
test, not a capacity forecast.

On the **local real-data check** (12 ETFs, 2013–2026, aggregate only), the
ranking changes at the base spread proxy, but the change is not robust. At 0.5×
the Corwin-Schultz proxy, momentum's net Sharpe (0.429) is above equal weight
(0.411); at 0.75× the two are effectively tied (0.410 vs 0.407); at 1× equal
weight is ahead by 0.024. The robust finding is momentum's implementation
fragility, not a reliable rank flip. The VNQ Corwin-Schultz half-spread proxy is
about 20 bps, but it is a proxy, not a quote. Momentum's break-even `k` against
zero Sharpe is 5.38, and its net Sharpe crosses zero near $28.8B AUM in that
sample. The result is model-conditional; the spread-proxy sensitivity is the
first evidence that the synthetic stability is not guaranteed.

The more useful output is the **break-even `k`**: the impact coefficient at which
a strategy's net Sharpe equals its fixed-10bps Sharpe. In the demo:

| Strategy | Fixed-10bps Sharpe | Break-even `k` vs fixed |
|---|---:|---:|
| Inverse volatility | 0.734 | 1.45 |
| Min variance | 0.638 | 1.45 |
| Equal weight | 0.718 | 1.40 |
| 60/40 | 0.465 | 1.81 |
| Momentum | 0.214 | **0.53** |

Momentum is fragile: a modest impact coefficient is enough to erase its advantage
over the naive 10-bps assumption. The low-turnover strategies require a much
larger `k`.

## What this means

- **Cost is a schedule decision, not a constant.** A fixed 10 bps is a baseline,
  not an estimate.
- **The ranking can survive costs and still be capacity-constrained.** A stable
  ordinal ranking is not evidence that the edge is scalable.
- **`k` is not identified from daily data.** Report a range and a break-even, not
  a point estimate.
- **The honest answer is conditional.** The optimal schedule depends on the
  benchmark (arrival vs VWAP) and the risk aversion.

## What it does not show

Daily OHLCV cannot identify intraday liquidity, order-book shape, or a specific
fill. The spread is a high-low proxy; on VNQ it is wide enough to exceed the naive
10-bps assumption, which is itself a finding. The impact model is a stylised
square-root law. The public demo is synthetic; the real-data check is
aggregate-only and still a daily-data exercise. There is no live-trading claim and
no alpha claim.

## Reproduce

```bash
pip install -e .
execution-lab demo --out results/demo
```

The checked-in synthetic panel is generated from a fixed seed. A run manifest
records the panel hash and every parameter. The tests cover cost accounting,
schedule constraints, timing-risk limits, point-in-time state, portfolio
accounting, and the end-to-end demo.

**Full method:** `docs/METHOD.md` · **Limitations:** `docs/LIMITATIONS.md` ·
**Results:** `docs/RESULTS.md`

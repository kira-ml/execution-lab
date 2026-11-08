# Real-Data Aggregate Artefacts

These files are **aggregate** outputs from a local run on the owner's licensed
Yahoo Finance ETF snapshot. The raw snapshot is not included and is not
redistributed.

- **Source:** 12 US ETFs (SPY, EFA, EEM, TLT, IEF, GLD, HYG, VNQ, LQD, IWM, MDY,
  AGG) from the sibling `robustfolio` snapshot. The universe overlaps the
  Robustfolio US ETF universe; equal weight is one of its published baselines,
  reconstructed here from prices. The actual Robustfolio walk-forward weights
  are not exported by that project; the target-weight loader is ready for them.
- **Window:** 2013-01-31 to 2026-09-29.
- **AUM:** $250M for the ranking table; capacity stress from $25M to $50B.
- **Generator:** `scripts/run_real_data.py`.
- **Full narrative:** [`../REAL_DATA_CHECK.md`](../REAL_DATA_CHECK.md).

## Headline

The ranking changes under realistic costs: equal weight overtakes momentum once
spread and impact are charged. The VNQ half-spread proxy is about 20 bps, so the
naive 10-bps baseline is not conservative for that asset. Momentum's break-even
`k` against zero Sharpe is 5.38; its net Sharpe crosses zero around $28.8B AUM in
this sample (linear interpolation, not a capacity forecast).

## Files

| File | Contents |
|---|---|
| `ranking.csv` | strategy × cost-model net Sharpe and metrics |
| `ranking_sharpes.csv` | Sharpe pivot |
| `ranking_ranks.csv` | rank pivot |
| `rank_changes.csv` | rank changes vs gross |
| `fragility.csv` | Sharpe lost to 5-day VWAP impact |
| `cost_decomposition.csv` | weighted spread, commission, impact, timing risk |
| `break_even_k.csv` | break-even `k` vs fixed and zero |
| `k_sensitivity.csv` | net Sharpe over the `k` grid |
| `aum_sensitivity.csv` | net Sharpe and rank over AUM |
| `aum_ranks.csv` | rank pivot over AUM |
| `order_schedule_comparison.csv` | one-order schedule comparison |
| `optimal_by_risk_aversion.csv` | best schedule by risk aversion |
| `fig_*.png` | aggregate figures |

## Caveat

This is a daily-data exercise. The spread is a high-low proxy, `k` is not
identified, and the ranking is conditional on the model. It is not an execution
simulator and not a tradable-alpha claim.

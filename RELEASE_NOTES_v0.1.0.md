# execution-lab v0.1.0

**Release date:** 2026-11-08

A transparent execution-cost and market-impact laboratory for ETF portfolios.
This is a research and engineering tool, not a live execution system.

## Highlights

- Cost decomposition: half-spread + commission + square-root impact + timing risk.
- Schedule comparison: immediate, TWAP, VWAP, and POV, with a risk-aversion
  frontier.
- Portfolio integration: target weights → trades → costs → net returns.
- Ranking sensitivity across cost models, impact coefficient `k`, and AUM.
- Break-even `k` and capacity stress, so the output is a range rather than a
  point estimate.
- One-command synthetic demo, 76 tests, CI, and a one-page brief.

## Demo headline (synthetic)

A 10%-of-ADV order in the least-liquid demo asset costs 16.12 bps under a 5-day
VWAP, versus 31.12 bps immediate, at a timing risk of 221.41 bps versus zero. At
`λ = 0.05` the 5-day VWAP wins; at `λ ≥ 0.10` immediate wins. The ranking is
stable at $250M AUM but momentum loses its absolute edge as AUM rises.

## Real-data check (aggregate only)

On the owner's licensed 12-ETF snapshot (2013–2026), realistic costs change the
ranking at the base spread proxy, but the change is not robust: at 0.5× the
Corwin-Schultz proxy, momentum is ahead of equal weight. The robust finding is
momentum's implementation fragility, not a reliable rank flip. The VNQ
Corwin-Schultz half-spread proxy is about 20 bps, but it is a proxy, not a
quote. The raw snapshot is not redistributed.

The 0.5x and 1x gaps are both small relative to sampling error for a 13-year
sample; the defensible claim is that the ordering is indistinguishable across
the plausible spread range, while momentum's cost drag is robust.

**Provenance:** this uses the separate Robustfolio ETF snapshot; it does not
evaluate or consume the Epistemic DRO 2025–2026 holdout.

## What is not claimed

- No live trading, routing, or brokerage connection.
- No tradable alpha.
- No order-book realism.
- No identified `k` from daily data.
- The synthetic demo is not an empirical claim about real ETFs.

## Known gaps

- External review is pending.
- The actual Robustfolio walk-forward weights are not loaded; the target-weight
  loader is ready for them.
- The real-data check is aggregate-only and model-conditional.

## Reproduce

```bash
pip install -e ".[dev]"
python -m pytest
execution-lab demo --out results/demo
```

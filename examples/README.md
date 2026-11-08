# Examples

`target_weights.csv` is a generic six-ETF target book matching the synthetic
demo panel. It is a placeholder for a real portfolio export, not an investment
recommendation.

The loader accepts either long format:

```csv
ticker,weight
SPY,0.25
TLT,0.20
```

or wide format with one row per date:

```csv
date,SPY,TLT
2024-12-31,0.60,0.40
```

The weights must be non-negative and sum to one. A Robustfolio or Epistemic DRO
export can be used without code changes once it is written in this schema.

```python
from execution_lab.portfolio import load_weights_csv

weights = load_weights_csv("examples/target_weights.csv")
```

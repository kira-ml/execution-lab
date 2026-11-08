# Data Licenses and Provenance

## 1. Code and synthetic demo

The code and the synthetic demo panel are released under the MIT License. The
panel is generated deterministically by `scripts/make_demo_data.py` from
`execution_lab.data.make_synthetic_panel` with seed `20261108`. It contains no
vendor data. You may redistribute it with the repository.

## 2. Vendor market data

No raw vendor market data is included in this repository, its releases, or its
public demo. The `data/` directory contains only the synthetic demo panel. The
`results/` directory is generated and ignored by git.

If you use a licensed vendor snapshot:

- keep the raw snapshot outside the repository;
- convert it to the documented long-format CSV in a local or temporary path;
- do not commit the raw file, a parquet snapshot, or a derived series that
  reconstructs raw values;
- check the vendor's terms before publishing derived tables or figures.

The owner's local check on a Yahoo Finance ETF snapshot (via the sibling
`robustfolio` project) is recorded in [`REAL_DATA_CHECK.md`](REAL_DATA_CHECK.md)
as **aggregate** results only. The snapshot itself is not redistributed.

## 3. Spread proxy

The Corwin-Schultz estimator is implemented from the published formula. It is a
statistical proxy computed from high, low, and close prices. It is not a quote and
carries no vendor quote license.

## 4. Third-party references

- Almgren, Thum, Hauptmann, and Li (2005), *Direct estimation of equity market
  impact*.
- Corwin and Schultz (2012), *A simple way to estimate bid-ask spreads from daily
  high and low prices*.
- Perold (1988), *The implementation shortfall*.

These are cited for method, not redistributed.

## 5. What a user may publish

Safe to publish:

- the code and synthetic panel;
- aggregate cost tables and figures produced by the demo;
- the method and limitations;
- a description of a local data run without raw values.

Not safe without a license check:

- raw or snapshot prices and volumes;
- a derived series that reconstructs a vendor's raw values;
- intraday bars or order-book data from an unauthorized source.

When in doubt, publish the method and the aggregate result, not the data.

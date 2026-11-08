"""Regenerate the checked-in synthetic demo panel.

The panel is deterministic; this script is the only producer. It is deliberately
small (six stylised ETFs, seven years of business days) so the repository stays
light and the demo is reproducible without a network connection.
"""

from __future__ import annotations

from pathlib import Path

from execution_lab.data import make_synthetic_panel, save_panel_csv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo" / "etf_daily.csv"


def main() -> None:
    panel = make_synthetic_panel(seed=20261108, start="2018-01-02", periods=1825)
    save_panel_csv(panel, OUT)
    print(f"wrote {OUT}")
    print(f"shape: {panel.close.shape}; hash: {panel.content_hash()}")
    print(f"period: {panel.close.index[0].date()} to {panel.close.index[-1].date()}")


if __name__ == "__main__":
    main()

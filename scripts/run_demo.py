"""One-command demo wrapper (equivalent to ``execution-lab demo``)."""

from __future__ import annotations

import argparse

from execution_lab.demo import run_demo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="results/demo")
    parser.add_argument("--aum", type=float, default=250e6)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args()
    result = run_demo(out_dir=args.out, aum=args.aum, start=args.start, end=args.end)
    print(f"wrote {result['out_dir']}")
    print(f"panel hash: {result['manifest']['panel_hash']}")


if __name__ == "__main__":
    main()

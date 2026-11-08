from __future__ import annotations

import json

import pandas as pd

from execution_lab.cli import main


def test_simulate_cli(capsys):
    code = main(
        [
            "simulate",
            "--ticker",
            "TEST",
            "--shares",
            "100000",
            "--price",
            "100",
            "--adv",
            "1000000",
            "--sigma",
            "0.01",
            "--spread-bps",
            "4",
            "--schedule",
            "vwap",
            "--horizon",
            "5",
            "--k",
            "0.5",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["ticker"] == "TEST"
    assert payload["schedule"] == "vwap_5d"
    assert payload["expected_cost_bps"] > 0


def test_sensitivity_compare_cli(capsys):
    code = main(
        [
            "sensitivity",
            "--ticker",
            "TEST",
            "--shares",
            "100000",
            "--price",
            "100",
            "--adv",
            "1000000",
            "--sigma",
            "0.01",
            "--spread-bps",
            "4",
            "--compare",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "immediate" in output
    assert "vwap_5d" in output


def test_calibrate_cli(tmp_path, capsys):
    path = tmp_path / "obs.csv"
    pd.DataFrame(
        {
            "cost_bps": [5.0, 10.0, 20.0],
            "sigma_daily": [0.01, 0.01, 0.01],
            "participation": [0.01, 0.04, 0.16],
        }
    ).to_csv(path, index=False)
    code = main(["calibrate", "--observations", str(path)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["k"] == 0.5
    assert payload["n_observations"] == 3

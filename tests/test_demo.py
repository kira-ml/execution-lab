from __future__ import annotations

from pathlib import Path

from execution_lab.data import make_synthetic_panel, save_panel_csv
from execution_lab.demo import run_demo


def test_demo_end_to_end(tmp_path):
    panel = make_synthetic_panel(periods=340, start="2021-01-04")
    panel_path = save_panel_csv(panel, tmp_path / "panel.csv")
    out = tmp_path / "out"
    result = run_demo(
        out_dir=out,
        data_path=panel_path,
        start=panel.close.index[260],
        end=panel.close.index[-1],
        aum=10e6,
        k_grid=(0.1, 0.5),
        participation_grid=(0.01, 0.05, 0.10),
        aum_grid=(10e6, 100e6),
    )
    assert (out / "report.md").exists()
    assert (out / "manifest.json").exists()
    assert (out / "ranking.csv").exists()
    assert (out / "break_even_k.csv").exists()
    assert (out / "fig_ranking_heatmap.png").exists()
    assert result["manifest"]["panel_hash"] == panel.content_hash()
    report = Path(out / "report.md").read_text(encoding="utf-8")
    assert "synthetic" in report.lower() or "local panel" in report.lower()
    assert "No live-trading claim" in report

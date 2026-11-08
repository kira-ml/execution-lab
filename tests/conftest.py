from __future__ import annotations

import pytest

from execution_lab.config import CostConfig
from execution_lab.data import compute_market_state, make_synthetic_panel


@pytest.fixture(scope="session")
def panel():
    return make_synthetic_panel(periods=520, start="2020-01-02")


@pytest.fixture(scope="session")
def state(panel):
    return compute_market_state(panel, panel.close.index[-1])


@pytest.fixture()
def config():
    return CostConfig()

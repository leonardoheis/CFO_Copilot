from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from app.data.schema import FINANCIAL_COLUMNS, MACRO_COLUMNS, MARKET_COLUMNS
from app.injections import configure_container
from app.injections.test import TestContainer

PanelFactory = Callable[..., pd.DataFrame]


def pytest_configure() -> None:
    container = configure_container()
    container.override(TestContainer)
    container.wire(packages=["tests"])  # pylint: disable=no-member


@pytest.fixture
def make_panel() -> PanelFactory:
    def _make(
        *, ticker: str = "AAA", quarters: int = 24, sector: str = "Technology"
    ) -> pd.DataFrame:
        steps = np.arange(quarters)
        panel = pd.DataFrame({
            "date": pd.date_range("2015-03-31", periods=quarters, freq="QE"),
            "company": ticker,
            "ticker": ticker,
            "sector": sector,
            "is_public": True,
        })
        panel["revenue_usd_m"] = 100 * np.exp(
            0.01 * steps + 0.1 * np.sin(steps * np.pi / 2)
        )
        market_columns = (*MARKET_COLUMNS, "market_cap_usd_m", "pe_ratio")
        other_columns = [*FINANCIAL_COLUMNS[1:], *market_columns, *MACRO_COLUMNS]
        for offset, column in enumerate(other_columns):
            panel[column] = np.cos(steps / 3) + offset
        return panel

    return _make

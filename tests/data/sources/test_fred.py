from datetime import date

import pandas as pd
import pytest

from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError
from app.data.schema import MACRO_COLUMNS
from app.data.sources.fred import FredSource
from app.settings import Settings


@pytest.fixture
def fred_source() -> FredSource:
    api_key = Settings.FRED_API_KEY or "test-key"
    return FredSource(api_key=api_key)


@pytest.mark.vcr
def test_fetch_macro_series_returns_data(fred_source: FredSource) -> None:
    series = fred_source.fetch_macro_series(
        "FEDFUNDS",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
    )

    assert not series.empty
    assert isinstance(series.index, pd.DatetimeIndex)


@pytest.mark.vcr
def test_fetch_macro_panel_has_macro_columns(fred_source: FredSource) -> None:
    start = date(2020, 1, 1)
    end = date(2020, 6, 30)
    panel = fred_source.fetch_macro_panel(start, end)
    expected_rows = len(quarter_end_dates(start, end))

    assert list(panel.columns) == ["date", *MACRO_COLUMNS]
    assert len(panel) == expected_rows
    assert panel.loc[0, "fed_funds"] == pytest.approx(0.65, rel=1e-2)
    assert panel["gdp_yoy"].notna().any()


def test_fetch_macro_series_raises_without_api_key() -> None:
    source = FredSource(api_key="")

    with pytest.raises(DataSourceUnavailableError, match="FRED_API_KEY"):
        source.fetch_macro_series(
            "FEDFUNDS",
            start=date(2020, 1, 1),
            end=date(2020, 6, 30),
        )

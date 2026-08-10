from datetime import date

import pytest

from app.data.dates import quarter_end_dates
from app.data.exceptions import TickerNotFoundError
from app.data.schema import MARKET_COLUMNS
from app.data.sources.yfinance_source import YfinanceSource


@pytest.fixture
def yfinance_source() -> YfinanceSource:
    return YfinanceSource()


@pytest.mark.vcr
def test_fetch_stock_history_returns_data(yfinance_source: YfinanceSource) -> None:
    history = yfinance_source.fetch_stock_history(
        "AMZN",
        start=date(2020, 1, 1),
        end=date(2020, 6, 30),
    )

    assert not history.empty
    assert "Close" in history.columns


@pytest.mark.vcr
def test_fetch_market_panel_has_market_columns(yfinance_source: YfinanceSource) -> None:
    start = date(2020, 1, 1)
    end = date(2020, 6, 30)
    panel = yfinance_source.fetch_market_panel("AMZN", start, end)
    expected_rows = len(quarter_end_dates(start, end))

    assert list(panel.columns) == ["date", *MARKET_COLUMNS]
    assert len(panel) == expected_rows
    assert panel.loc[0, "stock_price_usd"] == pytest.approx(97.49, rel=1e-2)
    assert panel.loc[0, "dividend_yield"] == pytest.approx(0.0)


@pytest.mark.vcr
def test_fetch_splits_returns_amazon_split_history(
    yfinance_source: YfinanceSource,
) -> None:
    splits = yfinance_source.fetch_splits("AMZN")

    split = splits.loc[splits.index.strftime("%Y-%m-%d") == "2022-06-06"]
    assert split.iloc[0] == pytest.approx(20.0)


@pytest.mark.vcr
def test_fetch_stock_history_raises_for_unknown_ticker(
    yfinance_source: YfinanceSource,
) -> None:
    with pytest.raises(TickerNotFoundError, match="INVALIDTICKER123"):
        yfinance_source.fetch_stock_history(
            "INVALIDTICKER123",
            start=date(2020, 1, 1),
            end=date(2020, 6, 30),
        )

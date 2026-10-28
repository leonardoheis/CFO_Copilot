from datetime import date

import pandas as pd
import pytest

from app.data.companies import CompanyRegistry
from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError, TickerNotFoundError
from app.data.schema import MARKET_COLUMNS
from app.data.sources.yfinance_source import YfinanceSource
from tests.data.conftest import FakeYahooTicker


@pytest.fixture
def yfinance_source(company_registry: CompanyRegistry) -> YfinanceSource:
    return YfinanceSource(registry=company_registry)


TICKER_TARGET = "app.data.sources.yfinance_source.source.yf.Ticker"


def test_fetch_stock_history_returns_the_tickers_history(
    yfinance_source: YfinanceSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = pd.DataFrame(
        {"Close": [90.0, 97.49]},
        index=pd.DatetimeIndex(["2020-03-30", "2020-03-31"]),
    )
    monkeypatch.setattr(TICKER_TARGET, lambda _ticker: FakeYahooTicker(history=history))

    fetched = yfinance_source.fetch_stock_history(
        "AMZN", start=date(2020, 1, 1), end=date(2020, 6, 30)
    )

    pd.testing.assert_frame_equal(fetched, history)


def test_fetch_market_panel_has_market_columns(
    yfinance_source: YfinanceSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    start, end = date(2020, 1, 1), date(2020, 6, 30)
    history = pd.DataFrame(
        {"Close": [97.49, 137.94]},
        index=pd.DatetimeIndex(["2020-03-31", "2020-06-30"]),
    )
    monkeypatch.setattr(TICKER_TARGET, lambda _ticker: FakeYahooTicker(history=history))

    panel = yfinance_source.fetch_market_panel("AMZN", start, end)

    assert list(panel.columns) == ["date", *MARKET_COLUMNS]
    assert len(panel) == len(quarter_end_dates(start, end))
    assert panel["stock_price_usd"].tolist() == pytest.approx([97.49, 137.94])
    assert panel["dividend_yield"].tolist() == pytest.approx([0.0, 0.0])


def test_fetch_market_panel_divides_trailing_dividends_by_price(
    yfinance_source: YfinanceSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = pd.DataFrame(
        {"Close": [50.0, 40.0]},
        index=pd.DatetimeIndex(["2020-03-31", "2020-06-30"]),
    )
    dividends = pd.Series(
        [0.5, 0.5], index=pd.DatetimeIndex(["2020-02-14", "2020-05-15"])
    )
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda _ticker: FakeYahooTicker(history=history, dividends=dividends),
    )

    panel = yfinance_source.fetch_market_panel(
        "KO", date(2020, 1, 1), date(2020, 6, 30)
    )

    assert panel["dividend_yield"].tolist() == pytest.approx([0.5 / 50.0, 1.0 / 40.0])


def test_fetch_splits_returns_the_tickers_split_history(
    yfinance_source: YfinanceSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    amazon_splits = pd.Series(
        [2.0, 20.0], index=pd.DatetimeIndex(["1999-09-02", "2022-06-06"])
    )
    monkeypatch.setattr(
        TICKER_TARGET, lambda _ticker: FakeYahooTicker(splits=amazon_splits)
    )

    splits = yfinance_source.fetch_splits("AMZN")

    assert splits.loc["2022-06-06"] == pytest.approx(20.0)


def test_fetch_market_panel_combines_googl_with_older_goog_history(
    yfinance_source: YfinanceSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GOOGL trades only from 2014; GOOG fills the quarters before it."""
    tickers = {
        "GOOGL": FakeYahooTicker(
            history=pd.DataFrame(
                {"Close": [560.0]}, index=pd.DatetimeIndex(["2014-06-30"])
            )
        ),
        "GOOG": FakeYahooTicker(
            history=pd.DataFrame(
                {"Close": [550.0, 555.0]},
                index=pd.DatetimeIndex(["2014-03-31", "2014-06-30"]),
            )
        ),
    }
    monkeypatch.setattr(TICKER_TARGET, lambda ticker: tickers[ticker])

    panel = yfinance_source.fetch_market_panel(
        "GOOGL", date(2014, 1, 1), date(2014, 6, 30)
    )

    assert panel["stock_price_usd"].tolist() == pytest.approx([550.0, 560.0])


def test_fetch_stock_history_raises_for_unknown_ticker(
    yfinance_source: YfinanceSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        TICKER_TARGET, lambda _ticker: FakeYahooTicker(history=pd.DataFrame())
    )

    with pytest.raises(TickerNotFoundError, match="INVALIDTICKER123"):
        yfinance_source.fetch_stock_history(
            "INVALIDTICKER123", start=date(2020, 1, 1), end=date(2020, 6, 30)
        )


def test_fetch_splits_returns_empty_series_when_yahoo_returns_none(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `None` splits payload is treated as no data, not an AttributeError."""
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda _ticker: FakeYahooTicker(splits=None),
    )
    source = YfinanceSource(registry=company_registry)

    assert source.fetch_splits("AMZN").empty


def test_fetch_splits_propagates_api_failure_as_data_source_error(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda _ticker: FakeYahooTicker(error=RuntimeError("connection reset")),
    )
    source = YfinanceSource(registry=company_registry)

    with pytest.raises(DataSourceUnavailableError, match="connection reset"):
        source.fetch_splits("AMZN")


def test_fetch_stock_history_treats_none_payload_as_missing(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda _ticker: FakeYahooTicker(history=None),
    )
    source = YfinanceSource(registry=company_registry)
    start, end = date(2020, 1, 1), date(2020, 6, 30)

    with pytest.raises(TickerNotFoundError, match="AMZN"):
        source.fetch_stock_history("AMZN", start, end)


def test_fetch_stock_history_propagates_api_failure_as_data_source_error(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda _ticker: FakeYahooTicker(error=RuntimeError("connection reset")),
    )
    source = YfinanceSource(registry=company_registry)
    start, end = date(2020, 1, 1), date(2020, 6, 30)

    with pytest.raises(DataSourceUnavailableError, match="connection reset"):
        source.fetch_stock_history("AMZN", start, end)


def test_fetch_splits_returns_empty_series_when_every_market_ticker_is_empty(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = YfinanceSource(registry=company_registry)
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda _ticker: FakeYahooTicker(splits=None),
    )

    assert source.fetch_splits("GOOGL").empty


def test_fetch_splits_skips_empty_ticker_and_uses_fallback(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """GOOGL yields nothing, so the GOOG fallback must supply the split history."""
    goog_splits = pd.Series(
        [2.0],
        index=pd.DatetimeIndex([pd.Timestamp("2014-04-03")]),
    )
    tickers = {
        "GOOGL": FakeYahooTicker(splits=None),
        "GOOG": FakeYahooTicker(splits=goog_splits),
    }
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda ticker: tickers[ticker],
    )
    source = YfinanceSource(registry=company_registry)

    with caplog.at_level("WARNING"):
        splits = source.fetch_splits("GOOGL")

    assert splits.iloc[0] == pytest.approx(2.0)
    assert "No split data available for GOOGL" in caplog.text


def test_fetch_market_panel_raises_when_every_ticker_is_empty(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda _ticker: FakeYahooTicker(history=pd.DataFrame()),
    )
    source = YfinanceSource(registry=company_registry)
    start, end = date(2020, 1, 1), date(2020, 6, 30)

    with pytest.raises(TickerNotFoundError, match="GOOGL"):
        source.fetch_market_panel("GOOGL", start, end)


def test_fetch_market_panel_skips_empty_ticker_and_uses_fallback(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    goog_history = pd.DataFrame(
        {"Close": [100.0, 110.0]},
        index=pd.DatetimeIndex(
            [pd.Timestamp("2020-03-31"), pd.Timestamp("2020-06-30")],
        ),
    )
    tickers = {
        "GOOGL": FakeYahooTicker(history=pd.DataFrame()),
        "GOOG": FakeYahooTicker(history=goog_history),
    }
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda ticker: tickers[ticker],
    )
    source = YfinanceSource(registry=company_registry)

    with caplog.at_level("WARNING"):
        panel = source.fetch_market_panel("GOOGL", date(2020, 1, 1), date(2020, 6, 30))

    assert panel.loc[0, "stock_price_usd"] == pytest.approx(100.0)
    assert "No price history available for GOOGL" in caplog.text


def test_fetch_index_return_panel_lags_quarterly_return_by_one_quarter(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closes = {
        "2019-09-30": 100.0,
        "2019-12-31": 110.0,
        "2020-03-31": 132.0,
        "2020-06-30": 99.0,
    }
    history = pd.DataFrame(
        {"Close": list(closes.values())},
        index=pd.DatetimeIndex([pd.Timestamp(day) for day in closes]),
    )
    monkeypatch.setattr(
        TICKER_TARGET,
        lambda _ticker: FakeYahooTicker(history=history),
    )
    source = YfinanceSource(registry=company_registry)

    panel = source.fetch_index_return_panel(date(2020, 1, 1), date(2020, 6, 30))

    assert list(panel.columns) == ["date", "sp500_return_lag1"]
    assert panel["sp500_return_lag1"].tolist() == pytest.approx([0.10, 0.20])

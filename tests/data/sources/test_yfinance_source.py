from datetime import date

import pandas as pd
import pytest

from app.data.companies import CompanyRegistry
from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError, TickerNotFoundError
from app.data.schema import MARKET_COLUMNS
from app.data.sources.yfinance_source import YfinanceSource


@pytest.fixture
def yfinance_source(company_registry: CompanyRegistry) -> YfinanceSource:
    return YfinanceSource(registry=company_registry)


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

    split = splits.loc[
        pd.to_datetime(splits.index).strftime("%Y-%m-%d") == "2022-06-06"
    ]
    assert split.iloc[0] == pytest.approx(20.0)


@pytest.mark.vcr
def test_fetch_market_panel_uses_goog_history_for_googl(
    yfinance_source: YfinanceSource,
) -> None:
    start = date(2010, 1, 1)
    end = date(2010, 6, 30)
    panel = yfinance_source.fetch_market_panel("GOOGL", start, end)

    stock_prices = panel["stock_price_usd"].astype(float)

    assert stock_prices.notna().all()
    assert stock_prices.gt(0.0).all()


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


class FakeYahooTicker:
    """A `_YahooTicker` stand-in returning canned values, including `None`."""

    def __init__(
        self,
        splits: pd.Series | None = None,
        history: pd.DataFrame | None = None,
        error: Exception | None = None,
    ) -> None:
        self._splits = splits
        self._history = history
        self._error = error

    @property
    def splits(self) -> pd.Series:
        if self._error is not None:
            raise self._error
        return self._splits  # type: ignore[return-value]

    @property
    def dividends(self) -> pd.Series:
        return pd.Series(dtype=float)

    def history(
        self,
        *,
        start: str,
        end: str,
        auto_adjust: bool,
    ) -> pd.DataFrame:
        del start, end, auto_adjust
        if self._error is not None:
            raise self._error
        return self._history  # type: ignore[return-value]


def test_fetch_splits_returns_empty_sentinel_when_yahoo_returns_none(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `None` splits payload is treated as no data, not an AttributeError."""
    monkeypatch.setattr(
        "app.data.sources.yfinance_source.source.yf.Ticker",
        lambda _ticker: FakeYahooTicker(splits=None),
    )
    source = YfinanceSource(registry=company_registry)

    with pytest.raises(TickerNotFoundError, match="AMZN"):
        source.fetch_splits("AMZN")


def test_fetch_splits_propagates_api_failure_as_data_source_error(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.data.sources.yfinance_source.source.yf.Ticker",
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
        "app.data.sources.yfinance_source.source.yf.Ticker",
        lambda _ticker: FakeYahooTicker(history=None),
    )
    source = YfinanceSource(registry=company_registry)

    with pytest.raises(TickerNotFoundError, match="AMZN"):
        source.fetch_stock_history("AMZN", date(2020, 1, 1), date(2020, 6, 30))


def test_fetch_stock_history_propagates_api_failure_as_data_source_error(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.data.sources.yfinance_source.source.yf.Ticker",
        lambda _ticker: FakeYahooTicker(error=RuntimeError("connection reset")),
    )
    source = YfinanceSource(registry=company_registry)

    with pytest.raises(DataSourceUnavailableError, match="connection reset"):
        source.fetch_stock_history("AMZN", date(2020, 1, 1), date(2020, 6, 30))


def test_fetch_splits_raises_when_every_market_ticker_is_empty(
    company_registry: CompanyRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = YfinanceSource(registry=company_registry)
    monkeypatch.setattr(
        "app.data.sources.yfinance_source.source.yf.Ticker",
        lambda _ticker: FakeYahooTicker(splits=None),
    )

    with pytest.raises(TickerNotFoundError, match="GOOGL"):
        source.fetch_splits("GOOGL")


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
        "app.data.sources.yfinance_source.source.yf.Ticker",
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
        "app.data.sources.yfinance_source.source.yf.Ticker",
        lambda _ticker: FakeYahooTicker(history=pd.DataFrame()),
    )
    source = YfinanceSource(registry=company_registry)

    with pytest.raises(TickerNotFoundError, match="GOOGL"):
        source.fetch_market_panel("GOOGL", date(2020, 1, 1), date(2020, 6, 30))


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
        "app.data.sources.yfinance_source.source.yf.Ticker",
        lambda ticker: tickers[ticker],
    )
    source = YfinanceSource(registry=company_registry)

    with caplog.at_level("WARNING"):
        panel = source.fetch_market_panel("GOOGL", date(2020, 1, 1), date(2020, 6, 30))

    assert panel.loc[0, "stock_price_usd"] == pytest.approx(100.0)
    assert "No price history available for GOOGL" in caplog.text

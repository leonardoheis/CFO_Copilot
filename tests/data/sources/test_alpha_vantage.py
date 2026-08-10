from datetime import date
from pathlib import Path

import pytest

from app.data.exceptions import DataSourceError
from app.data.sources.alpha_vantage import AlphaVantageSource


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    @staticmethod
    def raise_for_status() -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def _payloads() -> dict[str, dict[str, object]]:
    return {
        "INCOME_STATEMENT": {
            "quarterlyReports": [
                {
                    "fiscalDateEnding": "2006-03-31",
                    "totalRevenue": "1000000000",
                    "grossProfit": "400000000",
                    "operatingExpenses": "200000000",
                    "operatingIncome": "200000000",
                    "ebitda": "250000000",
                    "netIncome": "100000000",
                    "dilutedEPS": "0.25",
                },
            ],
        },
        "CASH_FLOW": {
            "quarterlyReports": [
                {
                    "fiscalDateEnding": "2006-03-31",
                    "operatingCashflow": "100000000",
                    "capitalExpenditures": "-10000000",
                },
            ],
        },
        "BALANCE_SHEET": {
            "quarterlyReports": [
                {
                    "fiscalDateEnding": "2006-03-31",
                    "commonStockSharesOutstanding": "1000000000",
                },
            ],
        },
        "EARNINGS": {
            "quarterlyEarnings": [
                {
                    "fiscalDateEnding": "2006-03-31",
                    "reportedEPS": "0.25",
                },
            ],
        },
    }


def _source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payloads: dict[str, dict[str, object]],
) -> AlphaVantageSource:
    def get(_url: str, *, params: dict[str, str], timeout: int) -> FakeResponse:
        del timeout
        return FakeResponse(payloads[params["function"]])

    monkeypatch.setattr("app.data.sources.alpha_vantage.requests.get", get)
    return AlphaVantageSource("test-key", tmp_path)


def test_fetch_financials_panel_maps_quarterly_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(tmp_path, monkeypatch, _payloads())

    panel = source.fetch_financials_panel(
        "AMZN",
        date(2006, 1, 1),
        date(2006, 3, 31),
    )

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(1000.0)
    assert panel.loc[0, "free_cash_flow_usd_m"] == pytest.approx(90.0)
    assert panel.loc[0, "eps"] == pytest.approx(0.25)
    assert panel.loc[0, "shares_outstanding"] == pytest.approx(1_000_000_000)


def test_cache_is_reused_without_second_http_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = _payloads()
    source = _source(tmp_path, monkeypatch, payloads)
    source.fetch_financials_panel("AMZN", date(2006, 1, 1), date(2006, 3, 31))

    def fail_get(*_args: object, **_kwargs: object) -> None:
        msg = "cache should avoid HTTP"
        raise AssertionError(msg)

    monkeypatch.setattr("app.data.sources.alpha_vantage.requests.get", fail_get)
    cached = AlphaVantageSource("test-key", tmp_path)
    panel = cached.fetch_financials_panel(
        "AMZN",
        date(2006, 1, 1),
        date(2006, 3, 31),
    )

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(1000.0)


def test_api_quota_payload_raises_data_source_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get(
        _url: str,
        *,
        params: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        del params, timeout
        return FakeResponse({"Note": "Thank you for using Alpha Vantage!"})

    monkeypatch.setattr("app.data.sources.alpha_vantage.requests.get", get)
    source = AlphaVantageSource("test-key", tmp_path)

    with pytest.raises(DataSourceError, match="Alpha Vantage Note"):
        source.fetch_financials_panel(
            "AMZN",
            date(2006, 1, 1),
            date(2006, 3, 31),
        )


def test_missing_api_key_fails_before_http(
    tmp_path: Path,
) -> None:
    source = AlphaVantageSource("", tmp_path)

    with pytest.raises(DataSourceError, match="ALPHA_VANTAGE_API_KEY"):
        source.fetch_financials_panel(
            "AMZN",
            date(2006, 1, 1),
            date(2006, 3, 31),
        )

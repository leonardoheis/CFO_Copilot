from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from app.data.exceptions import DataSourceError, MalformedPayloadError
from app.data.sources.alpha_vantage import AlphaVantageSource
from app.data.sources.alpha_vantage.parsing import number, report_date, reports


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

    monkeypatch.setattr("app.data.sources.alpha_vantage.source.requests.get", get)
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

    monkeypatch.setattr("app.data.sources.alpha_vantage.source.requests.get", fail_get)
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

    monkeypatch.setattr("app.data.sources.alpha_vantage.source.requests.get", get)
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


def test_reported_zero_diluted_eps_is_not_replaced_by_basic_eps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A breakeven quarter reports 0.00, which must not fall through to basicEPS."""
    payloads = _payloads()
    income_report = payloads["INCOME_STATEMENT"]["quarterlyReports"][0]  # type: ignore[index]
    income_report["dilutedEPS"] = "0.00"
    income_report["basicEPS"] = "1.50"
    payloads["EARNINGS"]["quarterlyEarnings"][0]["reportedEPS"] = "1.50"  # type: ignore[index]
    source = _source(tmp_path, monkeypatch, payloads)

    panel = source.fetch_financials_panel("AMZN", date(2006, 1, 1), date(2006, 3, 31))

    assert panel.loc[0, "eps"] == pytest.approx(0.0)


def test_missing_diluted_eps_still_falls_back_to_basic_eps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = _payloads()
    income_report = payloads["INCOME_STATEMENT"]["quarterlyReports"][0]  # type: ignore[index]
    del income_report["dilutedEPS"]
    income_report["basicEPS"] = "1.50"
    source = _source(tmp_path, monkeypatch, payloads)

    panel = source.fetch_financials_panel("AMZN", date(2006, 1, 1), date(2006, 3, 31))

    assert panel.loc[0, "eps"] == pytest.approx(1.5)


def test_zero_revenue_quarter_yields_no_margins_instead_of_dividing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = _payloads()
    payloads["INCOME_STATEMENT"]["quarterlyReports"][0]["totalRevenue"] = "0"  # type: ignore[index]
    source = _source(tmp_path, monkeypatch, payloads)

    panel = source.fetch_financials_panel("AMZN", date(2006, 1, 1), date(2006, 3, 31))

    assert pd.isna(panel.loc[0, "gross_margin"])
    assert pd.isna(panel.loc[0, "net_margin"])


def test_unparsable_fiscal_date_raises_instead_of_dropping_the_quarter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed date means the payload changed shape, not that data is absent."""
    payloads = _payloads()
    payloads["INCOME_STATEMENT"]["quarterlyReports"][0]["fiscalDateEnding"] = (  # type: ignore[index]
        "2006-13-45"
    )
    source = _source(tmp_path, monkeypatch, payloads)

    with pytest.raises(MalformedPayloadError, match="not an ISO date"):
        source.fetch_financials_panel("AMZN", date(2006, 1, 1), date(2006, 3, 31))


def test_absent_fiscal_date_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = _payloads()
    del payloads["INCOME_STATEMENT"]["quarterlyReports"][0]["fiscalDateEnding"]  # type: ignore[index]
    source = _source(tmp_path, monkeypatch, payloads)

    with pytest.raises(MalformedPayloadError, match="no usable fiscalDateEnding"):
        source.fetch_financials_panel("AMZN", date(2006, 1, 1), date(2006, 3, 31))


def test_fiscal_date_outside_the_tolerance_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unreachable at the shipped 46-day tolerance; guards a future tightening."""
    monkeypatch.setattr(
        "app.data.sources.alpha_vantage.parsing.QUARTER_END_TOLERANCE_DAYS",
        5,
    )

    with pytest.raises(MalformedPayloadError, match="cannot be placed"):
        report_date({"fiscalDateEnding": "2006-02-10"})


def test_every_calendar_date_maps_to_a_quarter_at_the_shipped_tolerance() -> None:
    """46 days is exactly half the longest quarter, so no date falls outside one."""
    day = date(2006, 1, 1)
    while day <= date(2006, 12, 31):
        assert report_date({"fiscalDateEnding": day.isoformat()}) is not None
        day += timedelta(days=1)


def test_out_of_bounds_fiscal_date_raises_with_placement_message() -> None:
    with pytest.raises(MalformedPayloadError, match="cannot be placed"):
        report_date({"fiscalDateEnding": "9999-12-31"})


def test_unparsable_number_warns_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        result = number({"totalRevenue": "not-a-number"}, "totalRevenue")

    assert result is None
    assert "not a number" in caplog.text


def test_reports_rejects_non_list_payload() -> None:
    with pytest.raises(MalformedPayloadError, match="must be a list"):
        reports({"quarterlyReports": {}}, "quarterlyReports")


def test_reports_warns_and_skips_non_dict_entries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        result = reports(
            {"quarterlyReports": [{"fiscalDateEnding": "2006-03-31"}, "invalid"]},
            "quarterlyReports",
        )

    assert result == [{"fiscalDateEnding": "2006-03-31"}]
    assert "Skipping non-object" in caplog.text

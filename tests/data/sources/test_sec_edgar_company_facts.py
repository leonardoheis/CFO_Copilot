from http import HTTPStatus

import pytest
import requests

from app.data.exceptions import DataSourceUnavailableError, MalformedPayloadError
from app.data.sources.sec_edgar import SecEdgarSource, SecTicker, fetch_sec_tickers
from app.data.sources.sec_edgar.parsing import concept_facts, sec_tickers
from app.data.sources.sec_edgar.xbrl import XbrlFact

GET_TARGET = "app.data.sources.sec_edgar.source.requests.get"
REVENUE_FACT: XbrlFact = {
    "start": "2024-01-01",
    "end": "2024-03-31",
    "val": 10.0,
    "filed": "2024-05-01",
}
PAYLOAD: dict[str, object] = {
    "facts": {
        "us-gaap": {
            "Revenues": {"units": {"USD": [REVENUE_FACT]}},
            "NetIncomeLoss": {"units": {"USD": [REVENUE_FACT]}},
        },
    },
}


class FakeResponse:
    def __init__(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._payload = payload
        self._status = status
        self.status_code = int(status)

    def raise_for_status(self) -> None:
        if self._status is not HTTPStatus.OK:
            error_response = requests.Response()
            error_response.status_code = self._status
            raise requests.HTTPError(response=error_response)

    def json(self) -> object:
        return self._payload


def _fake_get(monkeypatch: pytest.MonkeyPatch, response: FakeResponse) -> list[str]:
    """Answer every SEC request with ``response``.

    Returns:
        The URLs requested, in order, filled as the test runs.
    """
    requested: list[str] = []

    def get(url: str, *, headers: dict[str, str], timeout: int) -> FakeResponse:
        del headers, timeout
        requested.append(url)
        return response

    monkeypatch.setattr(GET_TARGET, get)
    return requested


def test_concept_facts_returns_the_unit_list() -> None:
    assert concept_facts(PAYLOAD, "Revenues", "USD") == [REVENUE_FACT]


def test_concept_facts_is_empty_for_an_unfiled_tag() -> None:
    assert concept_facts(PAYLOAD, "SalesRevenueNet", "USD") == []


def test_concept_facts_is_empty_for_an_unreported_unit() -> None:
    assert concept_facts(PAYLOAD, "Revenues", "USD/shares") == []


def test_concept_facts_is_empty_for_a_company_without_us_gaap_facts() -> None:
    assert concept_facts({}, "Revenues", "USD") == []


def test_concept_facts_rejects_a_unit_that_is_not_a_list() -> None:
    # The shape SEC's per-concept endpoint returned for ABT and KO: it must
    # never read as "the company does not file this tag".
    payload: dict[str, object] = {
        "facts": {"us-gaap": {"Revenues": {"units": {"USD": {}}}}}
    }

    with pytest.raises(MalformedPayloadError, match="Revenues"):
        concept_facts(payload, "Revenues", "USD")


@pytest.mark.parametrize(
    "payload",
    [
        {"facts": []},
        {"facts": {"us-gaap": "none"}},
        {"facts": {"us-gaap": {"Revenues": None}}},
        {"facts": {"us-gaap": {"Revenues": {"units": ["USD"]}}}},
    ],
)
def test_concept_facts_rejects_a_level_that_is_not_an_object(
    payload: dict[str, object],
) -> None:
    with pytest.raises(MalformedPayloadError, match="Revenues"):
        concept_facts(payload, "Revenues", "USD")


def test_one_company_facts_request_serves_every_tag(
    monkeypatch: pytest.MonkeyPatch,
    sec_source: SecEdgarSource,
) -> None:
    requested = _fake_get(monkeypatch, FakeResponse(PAYLOAD))

    revenue = sec_source.fetch_concept("1800", "Revenues")
    net_income = sec_source.fetch_concept("1800", "NetIncomeLoss")

    assert revenue == [REVENUE_FACT]
    assert net_income == [REVENUE_FACT]
    assert requested == [
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000001800.json"
    ]


def test_a_cik_without_xbrl_filings_has_no_facts(
    monkeypatch: pytest.MonkeyPatch,
    sec_source: SecEdgarSource,
) -> None:
    requested = _fake_get(monkeypatch, FakeResponse({}, HTTPStatus.NOT_FOUND))

    assert sec_source.fetch_concept("1800", "Revenues") == []
    assert sec_source.fetch_concept("1800", "NetIncomeLoss") == []
    assert len(requested) == 1


def test_a_server_error_is_reported_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    sec_source: SecEdgarSource,
) -> None:
    _fake_get(monkeypatch, FakeResponse({}, HTTPStatus.SERVICE_UNAVAILABLE))

    with pytest.raises(DataSourceUnavailableError, match="CIK0000001800"):
        sec_source.fetch_concept("1800", "Revenues")


def test_a_company_facts_body_that_is_not_an_object_is_malformed(
    monkeypatch: pytest.MonkeyPatch,
    sec_source: SecEdgarSource,
) -> None:
    _fake_get(monkeypatch, FakeResponse(["facts"]))

    with pytest.raises(MalformedPayloadError, match="CIK0000001800"):
        sec_source.fetch_concept("1800", "Revenues")


def test_a_ticker_file_server_error_is_reported_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    sec_source: SecEdgarSource,
) -> None:
    _fake_get(monkeypatch, FakeResponse({}, HTTPStatus.SERVICE_UNAVAILABLE))

    with pytest.raises(DataSourceUnavailableError, match="company_tickers"):
        sec_source.resolve_ciks("QCOM")


def test_a_malformed_ticker_entry_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    sec_source: SecEdgarSource,
) -> None:
    _fake_get(monkeypatch, FakeResponse({"0": {"ticker": "QCOM"}}))

    with pytest.raises(MalformedPayloadError, match="Malformed SEC ticker entry"):
        sec_source.resolve_ciks("QCOM")


def test_sec_tickers_pads_the_cik_and_upper_cases_the_ticker() -> None:
    payload = {"0": {"cik_str": 50863, "ticker": "intc", "title": "INTEL CORP"}}

    assert sec_tickers(payload) == {
        "INTC": SecTicker(cik="0000050863", title="INTEL CORP"),
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (["INTC"], "not a JSON object"),
        ({"0": "INTC"}, "Malformed SEC ticker entry"),
        ({"0": {"cik_str": 50863, "ticker": "INTC"}}, "Malformed SEC ticker entry"),
        (
            {"0": {"cik_str": 12345678901, "ticker": "INTC", "title": "INTEL"}},
            "invalid CIK",
        ),
        (
            {"0": {"cik_str": "-50863", "ticker": "INTC", "title": "INTEL"}},
            "invalid CIK",
        ),
    ],
)
def test_sec_tickers_rejects_a_malformed_file(payload: object, message: str) -> None:
    with pytest.raises(MalformedPayloadError, match=message):
        sec_tickers(payload)


def test_a_missing_ticker_file_is_reported_as_unavailable(
    monkeypatch: pytest.MonkeyPatch, sec_user_agent: str
) -> None:
    monkeypatch.setattr(
        GET_TARGET, lambda *_, **__: FakeResponse({}, HTTPStatus.NOT_FOUND)
    )

    with pytest.raises(DataSourceUnavailableError, match="company_tickers"):
        fetch_sec_tickers(user_agent=sec_user_agent, timeout=1)


def test_fetching_tickers_without_a_user_agent_is_refused() -> None:
    with pytest.raises(DataSourceUnavailableError, match="SEC_USER_AGENT"):
        fetch_sec_tickers(user_agent="", timeout=1)

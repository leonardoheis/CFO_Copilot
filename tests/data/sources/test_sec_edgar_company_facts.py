from http import HTTPStatus

import pytest
import requests

from app.data.companies import CompanyRegistry
from app.data.exceptions import DataSourceUnavailableError, MalformedPayloadError
from app.data.sources.sec_edgar import SecEdgarSource
from app.data.sources.sec_edgar.parsing import concept_facts
from app.data.xbrl import XbrlFact

GET_TARGET = "app.data.sources.sec_edgar.source.requests.get"
TEST_USER_AGENT = "CFO Copilot tests test@example.com"
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

    def raise_for_status(self) -> None:
        if self._status is not HTTPStatus.OK:
            error_response = requests.Response()
            error_response.status_code = self._status
            raise requests.HTTPError(response=error_response)

    def json(self) -> object:
        return self._payload


def _source(
    monkeypatch: pytest.MonkeyPatch,
    company_registry: CompanyRegistry,
    response: FakeResponse,
) -> tuple[SecEdgarSource, list[str]]:
    requested: list[str] = []

    def get(url: str, *, headers: dict[str, str], timeout: int) -> FakeResponse:
        del headers, timeout
        requested.append(url)
        return response

    monkeypatch.setattr(GET_TARGET, get)
    source = SecEdgarSource(user_agent=TEST_USER_AGENT, registry=company_registry)
    return source, requested


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
    payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": {}}}}}}

    with pytest.raises(MalformedPayloadError, match="Revenues"):
        concept_facts(payload, "Revenues", "USD")


def test_one_company_facts_request_serves_every_tag(
    monkeypatch: pytest.MonkeyPatch,
    company_registry: CompanyRegistry,
) -> None:
    source, requested = _source(monkeypatch, company_registry, FakeResponse(PAYLOAD))

    revenue = source.fetch_concept("1800", "Revenues")
    net_income = source.fetch_concept("1800", "NetIncomeLoss")

    assert revenue == [REVENUE_FACT]
    assert net_income == [REVENUE_FACT]
    assert requested == ["https://data.sec.gov/api/xbrl/companyfacts/CIK0000001800.json"]


def test_a_cik_without_xbrl_filings_has_no_facts(
    monkeypatch: pytest.MonkeyPatch,
    company_registry: CompanyRegistry,
) -> None:
    source, requested = _source(
        monkeypatch, company_registry, FakeResponse({}, HTTPStatus.NOT_FOUND)
    )

    assert source.fetch_concept("1800", "Revenues") == []
    assert source.fetch_concept("1800", "NetIncomeLoss") == []
    assert len(requested) == 1


def test_a_server_error_is_reported_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    company_registry: CompanyRegistry,
) -> None:
    source, _ = _source(
        monkeypatch, company_registry, FakeResponse({}, HTTPStatus.SERVICE_UNAVAILABLE)
    )

    with pytest.raises(DataSourceUnavailableError, match="CIK0000001800"):
        source.fetch_concept("1800", "Revenues")

import json
from collections.abc import Callable, Mapping

import pandas as pd
import pytest
from fredapi import Fred

from app.data.companies import CompanyRegistry
from app.data.sources import FredSource
from app.data.sources.sec_edgar import SecEdgarSource
from app.data.sources.sec_edgar.concepts import (
    COST_OF_REVENUE_PARTS,
    D_AND_A_PARTS,
    DILUTED_SHARES_FALLBACK,
    TAG_CHAINS,
)
from app.data.sources.sec_edgar.xbrl import XbrlFact
from app.settings import Settings

_RECORDED_TAGS = frozenset(
    tag
    for spec in (
        *TAG_CHAINS.values(),
        DILUTED_SHARES_FALLBACK,
        *dict(COST_OF_REVENUE_PARTS).values(),
        *dict(D_AND_A_PARTS).values(),
    )
    for tag in spec.tags
)


def _without_unread_tags(
    response: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Trim a ~5 MB companyfacts body to the tags the chains read before recording.

    Returns:
        The response, with any companyfacts body reduced to the chain tags.
    """
    body = response["body"]["string"]
    text = body.decode("utf-8") if isinstance(body, bytes) else str(body)
    if '"facts"' not in text[:200]:
        return response
    payload = json.loads(text)
    us_gaap = payload.get("facts", {}).get("us-gaap", {})
    payload["facts"] = {
        "us-gaap": {
            tag: facts for tag, facts in us_gaap.items() if tag in _RECORDED_TAGS
        },
    }
    response["body"]["string"] = json.dumps(payload).encode("utf-8")
    return response


@pytest.fixture
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": ["api_key"],
        "filter_headers": ["User-Agent"],
        "decode_compressed_response": True,
        "before_record_response": _without_unread_tags,
    }


@pytest.fixture
def company_registry() -> CompanyRegistry:
    return CompanyRegistry.from_path(Settings.COMPANY_REGISTRY_PATH)


@pytest.fixture
def sec_user_agent() -> str:
    # Never Settings.SEC_USER_AGENT: the .env value carries a personal email.
    return "CFO Copilot tests test@example.com"


@pytest.fixture
def fred_source() -> FredSource:
    # Never Settings.FRED_API_KEY: replay needs no key, and cassettes filter it.
    return FredSource(client=Fred(api_key="test-key"))


class FakeYahooTicker:
    """A yfinance ``Ticker`` stand-in returning canned values, including ``None``.

    yfinance talks to Yahoo through curl-cffi, which VCR cannot record, so every
    yfinance test runs against this fake instead of a cassette.
    """

    def __init__(
        self,
        splits: pd.Series | None = None,
        history: pd.DataFrame | None = None,
        dividends: pd.Series | None = None,
        error: Exception | None = None,
    ) -> None:
        self._splits = splits
        self._history = history
        self._dividends = pd.Series(dtype=float) if dividends is None else dividends
        self._error = error

    @property
    def splits(self) -> pd.Series:
        if self._error is not None:
            raise self._error
        return self._splits  # type: ignore[return-value]

    @property
    def dividends(self) -> pd.Series:
        return self._dividends

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


@pytest.fixture
def sec_source(
    company_registry: CompanyRegistry, sec_user_agent: str
) -> SecEdgarSource:
    return SecEdgarSource(
        user_agent=sec_user_agent,
        registry=company_registry,
        timeout=Settings.REQUEST_TIMEOUT,
    )


type ConceptServer = Callable[[Mapping[str, list[XbrlFact]]], list[str]]


@pytest.fixture
def serve_concepts(
    sec_source: SecEdgarSource, monkeypatch: pytest.MonkeyPatch
) -> ConceptServer:
    """Make ``sec_source`` read its XBRL facts from a mapping instead of SEC.

    Returns:
        A function taking the facts per tag (an absent tag has none) and
        returning the tags the source requested, in order.
    """

    def serve(facts_by_tag: Mapping[str, list[XbrlFact]]) -> list[str]:
        requested: list[str] = []

        def fetch_concept(_cik: str, tag: str, _unit: str = "USD") -> list[XbrlFact]:
            requested.append(tag)
            return list(facts_by_tag.get(tag, []))

        monkeypatch.setattr(sec_source, "fetch_concept", fetch_concept)
        return requested

    return serve

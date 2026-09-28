"""Share-count paths of `SecEdgarSource`, which have their own failure modes.

See `docs/specs/shares-outstanding-defects.md`.
"""

from datetime import date
from typing import cast

import pytest

from app.data.companies import CompanyRegistry
from app.data.sources.sec_edgar import SecEdgarSource
from app.data.xbrl import XbrlFact

TEST_USER_AGENT = "CFO Copilot tests test@example.com"


@pytest.fixture
def sec_source(company_registry: CompanyRegistry) -> SecEdgarSource:
    return SecEdgarSource(user_agent=TEST_USER_AGENT, registry=company_registry)


def _duration_fact(start: str, end: str, val: float, *, filed: str) -> XbrlFact:
    return {"start": start, "end": end, "val": val, "filed": filed}


def test_diluted_shares_fallback_weights_a_fiscal_q4_average(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subtracting two weighted averages raw gave PG a negative share count."""
    quarter = date(2026, 6, 30)

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        if tag != "WeightedAverageNumberOfDilutedSharesOutstanding":
            return []
        return [
            _duration_fact("2025-07-01", "2026-03-31", 2_425.8e6, filed="2026-04-20"),
            _duration_fact("2025-07-01", "2026-06-30", 2_422.5e6, filed="2026-08-04"),
        ]

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "shares_outstanding"] == pytest.approx(2_412.6e6, rel=1e-6)


def test_non_positive_share_count_is_discarded(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quarter = date(2026, 6, 30)

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        if tag != "CommonStockSharesOutstanding":
            return []
        # fetch_concept types every payload as a duration fact; the instant tags
        # are narrowed by their caller, exactly as the source itself does.
        return cast(
            "list[XbrlFact]",
            [{"end": "2026-06-30", "val": -3.3e6, "filed": "2026-08-04"}],
        )

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel["shares_outstanding"].isna().all()


def test_share_count_tagged_at_the_wrong_scale_is_discarded(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TXN tagged its 2009-Q3 diluted count as 1,268 rather than 1,268 million."""

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        if tag != "WeightedAverageNumberOfDilutedSharesOutstanding":
            return []
        return [
            _duration_fact("2009-04-01", "2009-06-30", 1_272e6, filed="2009-07-29"),
            _duration_fact("2009-07-01", "2009-09-30", 1_268, filed="2010-11-04"),
            _duration_fact("2009-10-01", "2009-12-31", 1_265e6, filed="2010-02-20"),
        ]

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel(
        "AMZN", date(2009, 6, 30), date(2009, 12, 31)
    )

    assert panel["shares_outstanding"].isna().tolist() == [False, True, False]


def test_implied_shares_from_inconsistent_eps_are_discarded(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A split-restated EPS can disagree in sign with net income, as GIS 2009 did."""
    quarter = date(2009, 6, 30)

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        if tag == "NetIncomeLoss":
            return [
                _duration_fact("2009-04-01", "2009-06-30", 358.8e6, filed="2009-08-01"),
            ]
        if tag == "EarningsPerShareDiluted":
            return [
                _duration_fact("2009-04-01", "2009-06-30", -0.83, filed="2009-08-01"),
            ]
        return []

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel["shares_outstanding"].isna().all()

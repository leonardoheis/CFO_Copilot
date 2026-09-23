import math
from datetime import date

import pandas as pd
import pytest

from app.data.companies import CompanyRegistry
from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError, TickerNotFoundError
from app.data.schema import FINANCIAL_COLUMNS, MILLIONS_DIVISOR
from app.data.sources.sec_edgar import SecEdgarSource, merge_raw_financial_frames
from app.data.xbrl import XbrlFact

TEST_USER_AGENT = "CFO Copilot tests test@example.com"


@pytest.fixture
def sec_source(company_registry: CompanyRegistry) -> SecEdgarSource:
    return SecEdgarSource(user_agent=TEST_USER_AGENT, registry=company_registry)


def _duration_fact(start: str, end: str, val: float, *, filed: str) -> XbrlFact:
    return {"start": start, "end": end, "val": val, "filed": filed}


def test_resolve_cik_for_amazon(sec_source: SecEdgarSource) -> None:
    assert sec_source.resolve_cik("AMZN") == "0001018724"


def test_resolve_ciks_for_alphabet(sec_source: SecEdgarSource) -> None:
    assert sec_source.resolve_ciks("GOOGL") == ("0001288776", "0001652044")
    assert sec_source.resolve_cik("GOOGL") == "0001652044"


def test_merge_raw_financial_frames_prefers_primary_values() -> None:
    preferred = pd.DataFrame(
        {
            "date": [date(2020, 3, 31), date(2020, 6, 30)],
            "revenue": [100.0, math.nan],
            "cogs": [10.0, 20.0],
        },
    )
    fallback = pd.DataFrame(
        {
            "date": [date(2020, 3, 31), date(2020, 6, 30)],
            "revenue": [90.0, 200.0],
            "cogs": [math.nan, 15.0],
        },
    )

    merged = merge_raw_financial_frames(preferred, fallback)

    assert merged.loc[0, "revenue"] == pytest.approx(100.0)
    assert merged.loc[1, "revenue"] == pytest.approx(200.0)
    assert merged.loc[0, "cogs"] == pytest.approx(10.0)
    assert merged.loc[1, "cogs"] == pytest.approx(20.0)


@pytest.mark.vcr
def test_resolve_cik_raises_for_unknown_ticker(
    sec_source: SecEdgarSource,
) -> None:
    with pytest.raises(TickerNotFoundError, match="INVALIDTICKER123"):
        sec_source.resolve_cik("INVALIDTICKER123")


def test_fetch_concept_raises_without_user_agent(
    company_registry: CompanyRegistry,
) -> None:
    source = SecEdgarSource(user_agent="", registry=company_registry)

    with pytest.raises(DataSourceUnavailableError, match="SEC_USER_AGENT"):
        source.fetch_concept("0001018724", "NetIncomeLoss")


@pytest.mark.vcr
def test_fetch_financials_panel_has_financial_columns_for_googl(
    sec_source: SecEdgarSource,
) -> None:
    start = date(2009, 1, 1)
    end = date(2009, 12, 31)

    panel = sec_source.fetch_financials_panel("GOOGL", start, end)

    assert panel["revenue_usd_m"].notna().all()
    assert panel["eps"].notna().all()


@pytest.mark.vcr
def test_fetch_financials_panel_has_financial_columns(
    sec_source: SecEdgarSource,
) -> None:
    start = date(2020, 1, 1)
    end = date(2020, 12, 31)

    panel = sec_source.fetch_financials_panel("AMZN", start, end)

    assert list(panel.columns) == ["date", *FINANCIAL_COLUMNS, "shares_outstanding"]
    assert len(panel) == len(quarter_end_dates(start, end))
    assert panel["revenue_usd_m"].notna().all()
    assert panel["operating_margin"].between(0, 1).all()
    assert panel["eps"].notna().all()
    assert panel["shares_outstanding"].notna().all()


@pytest.mark.vcr
def test_fetch_financials_panel_derives_q4_revenue(
    sec_source: SecEdgarSource,
) -> None:
    panel = sec_source.fetch_financials_panel(
        "AMZN",
        date(2020, 10, 1),
        date(2020, 12, 31),
    )

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(125_555, rel=1e-3)


@pytest.mark.vcr
def test_fetch_financials_panel_recovers_early_opex_and_shares(
    sec_source: SecEdgarSource,
) -> None:
    panel = sec_source.fetch_financials_panel(
        "AMZN",
        date(2009, 1, 1),
        date(2009, 12, 31),
    )

    assert panel["opex_usd_m"].notna().all()
    assert panel["shares_outstanding"].notna().all()


def test_dep_amort_chain_uses_later_tag_when_earlier_tags_are_empty(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dep_amort_value = 42.0
    operating_income_value = 1_000_000.0
    quarter = date(2020, 3, 31)
    requested_tags: list[str] = []

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        requested_tags.append(tag)
        if tag == "OperatingIncomeLoss":
            return [
                _duration_fact(
                    "2020-01-01",
                    "2020-03-31",
                    operating_income_value,
                    filed="2020-05-01",
                ),
            ]
        if tag != "DepreciationAmortizationAndOther":
            return []
        return [
            _duration_fact(
                "2020-01-01", "2020-03-31", dep_amort_value, filed="2020-05-01"
            ),
        ]

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    expected_ebitda = (operating_income_value + dep_amort_value) / MILLIONS_DIVISOR
    assert panel.loc[0, "ebitda_usd_m"] == pytest.approx(expected_ebitda)
    assert "DepreciationAmortizationAndOther" in requested_tags


def test_tag_chain_skips_zero_from_earlier_tag_and_uses_real_value(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero from a superseded tag must not block a later tag's real value.

    Oracle reports 0 under SalesRevenueNet for quarters it actually reports
    under Revenues. Treating that 0 as data writes a false revenue collapse
    into the panel, which is worse than a gap: NaN is visibly missing, 0 is
    silently wrong.
    """
    expected_value = 5_453_000_000.0
    quarter = date(2009, 3, 31)

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        if tag == "SalesRevenueNet":
            return [_duration_fact("2008-12-01", "2009-02-28", 0.0, filed="2009-04-01")]
        if tag == "Revenues":
            return [
                _duration_fact(
                    "2008-12-01",
                    "2009-02-28",
                    expected_value,
                    filed="2009-04-01",
                ),
            ]
        return []

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(
        expected_value / MILLIONS_DIVISOR
    )


def test_tag_chain_prefers_largest_when_a_superseded_tag_reports_a_subtotal(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Oracle kept reporting a segment subtotal under SalesRevenueNet."""
    subtotal = 458_000_000.0
    total = 6_404_000_000.0
    quarter = date(2010, 3, 31)

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        values = {"SalesRevenueNet": subtotal, "Revenues": total}
        if tag not in values:
            return []
        return [
            _duration_fact("2009-12-01", "2010-02-28", values[tag], filed="2010-04-01")
        ]

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(total / MILLIONS_DIVISOR)


def test_tag_chain_keeps_first_tag_when_concept_is_not_a_total(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Basic EPS always exceeds diluted, so the chain order must still win."""
    diluted = 2.45
    basic = 2.46
    quarter = date(2023, 3, 31)

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        values = {
            "EarningsPerShareDiluted": diluted,
            "EarningsPerShareBasic": basic,
        }
        if tag not in values:
            return []
        return [
            _duration_fact("2023-01-01", "2023-03-31", values[tag], filed="2023-04-25")
        ]

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "eps"] == pytest.approx(diluted)


def test_tag_chain_reads_goods_net_when_it_is_the_only_revenue_tag(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coca-Cola reports revenue only under SalesRevenueGoodsNet."""
    expected_value = 10_711_000_000.0
    quarter = date(2015, 3, 31)

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        if tag != "SalesRevenueGoodsNet":
            return []
        return [
            _duration_fact(
                "2015-01-01", "2015-03-31", expected_value, filed="2015-04-23"
            )
        ]

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(
        expected_value / MILLIONS_DIVISOR
    )


def test_tag_chain_keeps_the_total_when_goods_net_is_a_component(
    sec_source: SecEdgarSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """McDonald's reports company-operated sales under SalesRevenueGoodsNet."""
    component = 3_914_000_000.0
    total = 5_959_000_000.0
    quarter = date(2015, 3, 31)

    def fake_fetch_concept(
        _cik: str,
        tag: str,
        _unit: str = "USD",
    ) -> list[XbrlFact]:
        values = {"SalesRevenueGoodsNet": component, "Revenues": total}
        if tag not in values:
            return []
        return [
            _duration_fact("2015-01-01", "2015-03-31", values[tag], filed="2015-04-22")
        ]

    monkeypatch.setattr(sec_source, "fetch_concept", fake_fetch_concept)

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(total / MILLIONS_DIVISOR)

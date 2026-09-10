import math
from datetime import date

import pandas as pd
import pytest

from app.data.companies import CompanyRegistry
from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError, TickerNotFoundError
from app.data.schema import FINANCIAL_COLUMNS
from app.data.sources.sec_edgar import SecEdgarSource, merge_raw_financial_frames

TEST_USER_AGENT = "CFO Copilot tests test@example.com"


@pytest.fixture
def sec_source(company_registry: CompanyRegistry) -> SecEdgarSource:
    return SecEdgarSource(user_agent=TEST_USER_AGENT, registry=company_registry)


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

from datetime import date

import pandas as pd
import pytest

from app.data.companies import CompanyRegistry
from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceUnavailableError, TickerNotFoundError
from app.data.schema import FINANCIALS_FRAME_COLUMNS, MILLIONS_DIVISOR
from app.data.sources.sec_edgar import SecEdgarSource
from app.data.sources.sec_edgar.xbrl import XbrlFact
from app.settings import Settings
from tests.data.conftest import ConceptServer


def test_resolve_cik_for_amazon(sec_source: SecEdgarSource) -> None:
    assert sec_source.resolve_ciks("AMZN") == ("0001018724",)


def test_resolve_ciks_for_alphabet(sec_source: SecEdgarSource) -> None:
    assert sec_source.resolve_ciks("GOOGL") == ("0001288776", "0001652044")


@pytest.mark.vcr
def test_resolve_cik_raises_for_unknown_ticker(
    sec_source: SecEdgarSource,
) -> None:
    with pytest.raises(TickerNotFoundError, match="INVALIDTICKER123"):
        sec_source.resolve_ciks("INVALIDTICKER123")


def test_fetch_concept_raises_without_user_agent(
    company_registry: CompanyRegistry,
) -> None:
    source = SecEdgarSource(
        user_agent="", registry=company_registry, timeout=Settings.REQUEST_TIMEOUT
    )

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

    assert list(panel.columns) == list(FINANCIALS_FRAME_COLUMNS)
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
    serve_concepts: ConceptServer,
) -> None:
    dep_amort_value = 42.0
    operating_income_value = 1_000_000.0
    quarter = date(2020, 3, 31)

    requested_tags = serve_concepts({
        "OperatingIncomeLoss": [
            XbrlFact(
                start="2020-01-01",
                end="2020-03-31",
                val=operating_income_value,
                filed="2020-05-01",
            ),
        ],
        "DepreciationAmortizationAndOther": [
            XbrlFact(
                start="2020-01-01",
                end="2020-03-31",
                val=dep_amort_value,
                filed="2020-05-01",
            ),
        ],
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    expected_ebitda = (operating_income_value + dep_amort_value) / MILLIONS_DIVISOR
    assert panel.loc[0, "ebitda_usd_m"] == pytest.approx(expected_ebitda)
    assert "DepreciationAmortizationAndOther" in requested_tags


def test_tag_chain_skips_zero_from_earlier_tag_and_uses_real_value(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """A zero from a superseded tag must not block a later tag's real value.

    Oracle reports 0 under SalesRevenueNet for quarters it actually reports
    under Revenues. Treating that 0 as data writes a false revenue collapse
    into the panel, which is worse than a gap: NaN is visibly missing, 0 is
    silently wrong.
    """
    expected_value = 5_453_000_000.0
    quarter = date(2009, 3, 31)

    serve_concepts({
        "SalesRevenueNet": [
            XbrlFact(start="2008-12-01", end="2009-02-28", val=0.0, filed="2009-04-01")
        ],
        "Revenues": [
            XbrlFact(
                start="2008-12-01",
                end="2009-02-28",
                val=expected_value,
                filed="2009-04-01",
            ),
        ],
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(
        expected_value / MILLIONS_DIVISOR
    )


def test_tag_chain_prefers_largest_when_a_superseded_tag_reports_a_subtotal(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """Oracle kept reporting a segment subtotal under SalesRevenueNet."""
    subtotal = 458_000_000.0
    total = 6_404_000_000.0
    quarter = date(2010, 3, 31)

    values = {"SalesRevenueNet": subtotal, "Revenues": total}
    serve_concepts({
        tag: [
            XbrlFact(
                start="2009-12-01", end="2010-02-28", val=value, filed="2010-04-01"
            )
        ]
        for tag, value in values.items()
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(total / MILLIONS_DIVISOR)


def _gross_profit_from_cost_tags(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
    cost_tags: dict[str, float],
) -> pd.Series:
    quarter = date(2016, 6, 30)
    millions_by_tag = {"Revenues": 7_164.0, **cost_tags}
    in_usd = {
        tag: millions * MILLIONS_DIVISOR for tag, millions in millions_by_tag.items()
    }

    serve_concepts({
        tag: [
            XbrlFact(
                start="2016-04-01", end="2016-06-30", val=value, filed="2016-07-27"
            )
        ]
        for tag, value in in_usd.items()
    })
    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)
    return panel["gross_profit_usd_m"]


def test_cost_of_revenue_sums_products_and_services_without_a_total(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """SLB 2016-Q2 filed the two parts and no combined cost of revenue."""
    gross_profit = _gross_profit_from_cost_tags(
        sec_source,
        serve_concepts,
        {"CostOfGoodsSold": 2_133.0, "CostOfServices": 4_332.0},
    )

    assert gross_profit.iloc[0] == pytest.approx(7_164.0 - 2_133.0 - 4_332.0)


def test_cost_of_revenue_keeps_a_filed_total_over_its_parts(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """LMT's parts exceed its filed total, which carries unallocated adjustments."""
    gross_profit = _gross_profit_from_cost_tags(
        sec_source,
        serve_concepts,
        {
            "CostOfGoodsAndServicesSold": 5_800.0,
            "CostOfGoodsSold": 5_000.0,
            "CostOfServices": 900.0,
        },
    )

    assert gross_profit.iloc[0] == pytest.approx(7_164.0 - 5_800.0)


def test_a_negative_cost_of_revenue_is_read_as_a_sign_error(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """CAT's 2009 10-Q/A filed 2008-Q2 cost of goods sold as -10,036."""
    gross_profit = _gross_profit_from_cost_tags(
        sec_source, serve_concepts, {"CostOfGoodsSold": -2_133.0}
    )

    assert gross_profit.iloc[0] == pytest.approx(7_164.0 - 2_133.0)


def test_a_sign_error_competes_for_largest_by_its_magnitude(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """BA 2009-Q4: CostOfRevenue -14,508 is the total; products alone are 12,207."""
    gross_profit = _gross_profit_from_cost_tags(
        sec_source,
        serve_concepts,
        {"CostOfRevenue": -6_465.0, "CostOfGoodsSold": 2_133.0},
    )

    assert gross_profit.iloc[0] == pytest.approx(7_164.0 - 6_465.0)


def test_cost_of_revenue_is_products_alone_without_services(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    gross_profit = _gross_profit_from_cost_tags(
        sec_source, serve_concepts, {"CostOfGoodsSold": 2_133.0}
    )

    assert gross_profit.iloc[0] == pytest.approx(7_164.0 - 2_133.0)


OPERATING_INCOME_M = 1_842.0


def _depreciation_and_amortization_from_tags(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
    dep_amort_tags: dict[str, float],
) -> float:
    quarter = date(2026, 3, 31)
    millions_by_tag = {
        "Revenues": 11_164.0,
        "OperatingIncomeLoss": OPERATING_INCOME_M,
        **dep_amort_tags,
    }
    in_usd = {
        tag: millions * MILLIONS_DIVISOR for tag, millions in millions_by_tag.items()
    }

    serve_concepts({
        tag: [
            XbrlFact(
                start="2026-01-01", end="2026-03-31", val=value, filed="2026-04-30"
            )
        ]
        for tag, value in in_usd.items()
    })
    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)
    return float(panel["ebitda_usd_m"].iloc[0]) - OPERATING_INCOME_M


def test_d_and_a_sums_depreciation_and_amortization_without_a_total(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """ABT files depreciation and intangible amortization apart, with no total."""
    dep_amort = _depreciation_and_amortization_from_tags(
        sec_source,
        serve_concepts,
        {"Depreciation": 370.0, "AmortizationOfIntangibleAssets": 360.0},
    )

    assert dep_amort == pytest.approx(370.0 + 360.0)


def test_d_and_a_keeps_a_filed_total_over_its_parts(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    dep_amort = _depreciation_and_amortization_from_tags(
        sec_source,
        serve_concepts,
        {
            "DepreciationDepletionAndAmortization": 800.0,
            "Depreciation": 370.0,
            "AmortizationOfIntangibleAssets": 360.0,
        },
    )

    assert dep_amort == pytest.approx(800.0)


def test_a_negative_amortization_leaves_depreciation_alone(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """BMY 2009 filed intangible amortization as -170, which is not an expense."""
    dep_amort = _depreciation_and_amortization_from_tags(
        sec_source,
        serve_concepts,
        {"Depreciation": 469.0, "AmortizationOfIntangibleAssets": -170.0},
    )

    assert dep_amort == pytest.approx(469.0)


def test_d_and_a_is_depreciation_alone_without_amortization(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    dep_amort = _depreciation_and_amortization_from_tags(
        sec_source, serve_concepts, {"Depreciation": 370.0}
    )

    assert dep_amort == pytest.approx(370.0)


def test_tag_chain_keeps_first_tag_when_concept_is_not_a_total(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """Basic EPS always exceeds diluted, so the chain order must still win."""
    diluted = 2.45
    basic = 2.46
    quarter = date(2023, 3, 31)

    values = {
        "EarningsPerShareDiluted": diluted,
        "EarningsPerShareBasic": basic,
    }
    serve_concepts({
        tag: [
            XbrlFact(
                start="2023-01-01", end="2023-03-31", val=value, filed="2023-04-25"
            )
        ]
        for tag, value in values.items()
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "eps"] == pytest.approx(diluted)


def test_tag_chain_reads_goods_net_when_it_is_the_only_revenue_tag(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """Coca-Cola reports revenue only under SalesRevenueGoodsNet."""
    expected_value = 10_711_000_000.0
    quarter = date(2015, 3, 31)

    serve_concepts({
        "SalesRevenueGoodsNet": [
            XbrlFact(
                start="2015-01-01",
                end="2015-03-31",
                val=expected_value,
                filed="2015-04-23",
            )
        ]
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(
        expected_value / MILLIONS_DIVISOR
    )


def test_tag_chain_keeps_the_total_when_goods_net_is_a_component(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """McDonald's reports company-operated sales under SalesRevenueGoodsNet."""
    component = 3_914_000_000.0
    total = 5_959_000_000.0
    quarter = date(2015, 3, 31)

    values = {"SalesRevenueGoodsNet": component, "Revenues": total}
    serve_concepts({
        tag: [
            XbrlFact(
                start="2015-01-01", end="2015-03-31", val=value, filed="2015-04-22"
            )
        ]
        for tag, value in values.items()
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(total / MILLIONS_DIVISOR)


def test_tag_chain_reads_regulated_operating_revenue_for_a_utility(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """NextEra reports total revenue only as RegulatedAndUnregulatedOperatingRevenue."""
    total = 4_717_000_000.0
    quarter = date(2015, 3, 31)

    serve_concepts({
        "RegulatedAndUnregulatedOperatingRevenue": [
            XbrlFact(
                start="2015-01-01", end="2015-03-31", val=total, filed="2015-05-05"
            )
        ]
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(total / MILLIONS_DIVISOR)


def test_regulated_operating_revenue_wins_over_contract_revenue_it_contains(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """Duke 2018 Q1: contract revenue 5,928 is a component of the 6,135 total."""
    contract_revenue = 5_928_000_000.0
    total = 6_135_000_000.0
    quarter = date(2018, 3, 31)

    values = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": contract_revenue,
        "RegulatedAndUnregulatedOperatingRevenue": total,
    }
    serve_concepts({
        tag: [
            XbrlFact(
                start="2018-01-01", end="2018-03-31", val=value, filed="2018-05-08"
            )
        ]
        for tag, value in values.items()
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "revenue_usd_m"] == pytest.approx(total / MILLIONS_DIVISOR)

from datetime import date

import pandas as pd
import pytest

from app.data.dates import QUARTER_END_TOLERANCE_DAYS, nearest_quarter_end
from app.data.exceptions import MalformedPayloadError
from app.data.xbrl import (
    FactProvenance,
    InstantXbrlFact,
    PeriodMeasure,
    XbrlFact,
    instant_series_from_facts,
    quarterly_facts_from_facts,
)

EXPECTED_Q4_VALUE = 250
EXPECTED_NATIVE_Q2_VALUE = 140
EXPECTED_LATEST_FILING_VALUE = 110.0
EXPECTED_JUNE_FISCAL_Q4 = 40
EXPECTED_DURATION_FACT_VALUE = 100
EXPECTED_AVERAGE_FISCAL_Q4 = 2_412.6
EXPECTED_AVERAGE_FROM_THREE_QUARTERS = 2_400.0


def _fact(
    start: str,
    end: str,
    value: float,
    filed: str = "2021-01-01",
) -> XbrlFact:
    return {
        "start": start,
        "end": end,
        "val": value,
        "filed": filed,
    }


def test_quarterly_facts_keeps_latest_filing() -> None:
    facts = [
        _fact("2020-01-01", "2020-03-31", 100, "2020-05-01"),
        _fact("2020-01-01", "2020-03-31", 110, "2021-02-01"),
    ]

    result = quarterly_facts_from_facts(facts, [date(2020, 3, 31)])
    assert result["value"].iloc[0] == pytest.approx(
        EXPECTED_LATEST_FILING_VALUE,
    )


def test_quarterly_facts_rejects_outvoted_accession() -> None:
    facts = [
        _fact("2020-01-01", "2020-03-31", 100, "2020-05-01") | {"accn": "good-1"},
        _fact("2020-01-01", "2020-03-31", 100, "2021-05-01") | {"accn": "good-2"},
        _fact("2020-01-01", "2020-03-31", 120, "2022-05-01") | {"accn": "bad"},
        _fact("2020-04-01", "2020-06-30", 200, "2020-08-01") | {"accn": "good-1"},
        _fact("2020-04-01", "2020-06-30", 200, "2021-08-01") | {"accn": "good-2"},
        _fact("2020-04-01", "2020-06-30", 220, "2022-08-01") | {"accn": "bad"},
    ]

    result = quarterly_facts_from_facts(
        facts,
        [date(2020, 3, 31), date(2020, 6, 30)],
    )
    assert result["value"].tolist() == [100.0, 200.0]


def test_instant_series_aligns_latest_fact_to_quarter_end() -> None:
    facts: list[InstantXbrlFact] = [
        {"end": "2020-03-31", "val": 400, "filed": "2020-05-01"},
        {"end": "2020-06-30", "val": 410, "filed": "2020-08-01"},
    ]

    result = instant_series_from_facts(
        facts,
        [date(2020, 3, 31), date(2020, 6, 30)],
    )

    assert result["value"].tolist() == [400.0, 410.0]


def test_instant_series_drops_a_snapshot_too_old_for_the_quarter() -> None:
    """A filer that stops reporting the tag must leave gaps, not a flat line."""
    facts: list[InstantXbrlFact] = [
        {"end": "2012-01-31", "val": 3_418, "filed": "2012-03-01"},
    ]

    result = instant_series_from_facts(
        facts,
        [date(2012, 3, 31), date(2020, 6, 30), date(2026, 6, 30)],
    )

    assert result["value"].iloc[0] == pytest.approx(3_418.0)
    assert result["value"].iloc[1:].isna().all()


def test_quarterly_facts_derives_a_period_average_by_day_weighting() -> None:
    """Differencing two averages raw yields noise; the residual must be weighted."""
    facts = [
        _fact("2025-07-01", "2026-03-31", 2_425.8),
        _fact("2025-07-01", "2026-06-30", 2_422.5),
    ]

    result = quarterly_facts_from_facts(
        facts,
        [date(2026, 6, 30)],
        PeriodMeasure.PERIOD_AVERAGE,
    )

    assert result["value"].iloc[0] == pytest.approx(EXPECTED_AVERAGE_FISCAL_Q4)


def test_quarterly_facts_derives_a_period_average_from_annual_minus_quarters() -> None:
    facts = [
        _fact("2020-01-01", "2020-03-31", 2_400),
        _fact("2020-04-01", "2020-06-30", 2_400),
        _fact("2020-07-01", "2020-09-30", 2_400),
        _fact("2020-01-01", "2020-12-31", 2_400),
    ]

    result = quarterly_facts_from_facts(
        facts,
        [date(2020, 12, 31)],
        PeriodMeasure.PERIOD_AVERAGE,
    )

    assert result["value"].iloc[0] == pytest.approx(
        EXPECTED_AVERAGE_FROM_THREE_QUARTERS,
    )


def test_native_quarter_reports_its_own_period_end_and_rule() -> None:
    """A fiscal filer's row must say which period it actually covers."""
    facts = [_fact("2026-05-04", "2026-08-02", 47_861)]

    result = quarterly_facts_from_facts(facts, [date(2026, 6, 30)])

    assert result["period_end"].iloc[0] == date(2026, 8, 2)
    assert result["provenance"].iloc[0] == FactProvenance.NATIVE


def test_derived_quarter_reports_the_rule_that_produced_it() -> None:
    facts = [
        _fact("2020-01-01", "2020-09-30", 750),
        _fact("2020-01-01", "2020-12-31", 1_000),
    ]

    result = quarterly_facts_from_facts(facts, [date(2020, 12, 31)])

    assert result["provenance"].iloc[0] == FactProvenance.YTD_DERIVED


def test_a_quarter_no_rule_can_fill_is_marked_missing() -> None:
    result = quarterly_facts_from_facts([], [date(2020, 12, 31)])

    assert result["provenance"].iloc[0] == FactProvenance.MISSING
    assert result["period_end"].iloc[0] is None


def test_quarterly_facts_still_subtracts_a_flow_unweighted() -> None:
    facts = [
        _fact("2020-01-01", "2020-09-30", 750),
        _fact("2020-01-01", "2020-12-31", 1_000),
    ]

    result = quarterly_facts_from_facts(
        facts,
        [date(2020, 12, 31)],
        PeriodMeasure.FLOW,
    )

    assert result["value"].iloc[0] == EXPECTED_Q4_VALUE


def test_quarterly_facts_derives_q4_from_fy_and_nine_months() -> None:
    facts = [
        _fact("2020-01-01", "2020-09-30", 750),
        _fact("2020-01-01", "2020-12-31", 1_000),
    ]

    result = quarterly_facts_from_facts(facts, [date(2020, 12, 31)])

    assert result["value"].iloc[0] == EXPECTED_Q4_VALUE


def test_quarterly_facts_derives_q4_from_annual_minus_three_native_quarters() -> None:
    facts = [
        _fact("2019-07-01", "2019-09-30", 300),
        _fact("2019-10-01", "2019-12-31", 310),
        _fact("2020-01-01", "2020-03-31", 350),
        _fact("2019-07-01", "2020-06-30", 1_000),
    ]

    result = quarterly_facts_from_facts(facts, [date(2020, 6, 30)])

    assert result["value"].iloc[0] == EXPECTED_JUNE_FISCAL_Q4


def test_quarterly_facts_skips_annual_minus_three_when_year_is_sparse() -> None:
    facts = [
        _fact("2019-07-01", "2019-09-30", 300),
        _fact("2019-10-01", "2019-12-31", 310),
        _fact("2019-07-01", "2020-06-30", 1_000),
    ]

    result = quarterly_facts_from_facts(facts, [date(2020, 6, 30)])

    assert pd.isna(result["value"].iloc[0])


def test_quarterly_facts_prefers_native_quarter_over_ytd_difference() -> None:
    facts = [
        _fact("2020-01-01", "2020-03-31", 100),
        _fact("2020-01-01", "2020-06-30", 250),
        _fact("2020-04-01", "2020-06-30", 140),
    ]

    result = quarterly_facts_from_facts(facts, [date(2020, 6, 30)])

    assert result["value"].iloc[0] == EXPECTED_NATIVE_Q2_VALUE


def test_nearest_quarter_end_accepts_fiscal_period_offset() -> None:
    assert nearest_quarter_end(
        date(2020, 12, 27),
        QUARTER_END_TOLERANCE_DAYS,
    ) == date(2020, 12, 31)


def test_quarterly_facts_returns_nan_for_missing_quarter() -> None:
    result = quarterly_facts_from_facts([], [date(2020, 3, 31)])

    assert pd.isna(result["value"].iloc[0])


def test_malformed_duration_fact_date_raises_data_source_error() -> None:
    facts = [_fact("not-a-date", "2020-03-31", 100)]
    quarter_dates = [date(2020, 3, 31)]

    with pytest.raises(MalformedPayloadError, match="duration fact dates"):
        quarterly_facts_from_facts(facts, quarter_dates)


def test_malformed_fact_value_raises_data_source_error() -> None:
    facts = [_fact("2020-01-01", "2020-03-31", "not-a-number")]  # type: ignore[arg-type]
    quarter_dates = [date(2020, 3, 31)]

    with pytest.raises(MalformedPayloadError, match="fact value"):
        quarterly_facts_from_facts(facts, quarter_dates)


def test_malformed_instant_fact_date_raises_data_source_error() -> None:
    facts: list[InstantXbrlFact] = [
        {"end": "not-a-date", "val": 100, "filed": "2021-01-01"},
    ]
    quarter_dates = [date(2020, 3, 31)]

    with pytest.raises(MalformedPayloadError, match="instant fact date"):
        instant_series_from_facts(facts, quarter_dates)


def test_instant_fact_under_a_duration_concept_is_skipped() -> None:
    """SEC returns the odd instant fact under a duration tag; it has no start."""
    facts: list[XbrlFact] = [
        _fact("2021-04-01", "2021-06-30", 100),
        {"end": "2021-06-30", "val": 900, "filed": "2021-07-22"},  # type: ignore[typeddict-item]
    ]

    result = quarterly_facts_from_facts(facts, [date(2021, 6, 30)])

    assert result["value"].iloc[0] == EXPECTED_DURATION_FACT_VALUE

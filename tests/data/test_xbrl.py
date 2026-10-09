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
    annual_totals_by_end,
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
PFE_2018_Q4_FIRST_REPORTED = 13_977
COP_2010_Q4_FIRST_REPORTED = 51_726
RESTATED_NATIVE_QUARTER = 13_500
PFE_2020_Q3 = 10_277
PFE_2020_Q4_LATEST = 41_651 - 30_224
GOOGL_2012_Q4 = 50_175 - 35_756
ORCL_FY2018_Q4 = 39_383 - 28_579


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


def test_a_restated_year_takes_the_pairing_closer_to_the_previous_quarter() -> None:
    """PFE 2018: the FY2020 10-K restated 2018 for Upjohn; the nine months were not."""
    facts = [
        _fact("2018-07-02", "2018-09-30", 13_298, "2018-11-08"),
        _fact("2018-01-01", "2018-09-30", 39_670, "2018-11-08"),
        _fact("2018-01-01", "2018-12-31", 53_647, "2019-02-28"),
        _fact("2018-01-01", "2018-12-31", 40_825, "2021-02-25"),
    ]

    result = quarterly_facts_from_facts(facts, [date(2018, 9, 30), date(2018, 12, 31)])

    assert result["value"].iloc[1] == PFE_2018_Q4_FIRST_REPORTED
    assert result["filed"].iloc[1] == "2019-02-28"


def test_a_restatement_between_q3_and_the_10k_takes_the_latest_pairing() -> None:
    """PFE 2020: Upjohn left after the Q3 10-Q, so only the restated pair agrees."""
    facts = [
        _fact("2020-06-29", "2020-09-27", PFE_2020_Q3, "2021-11-12"),
        _fact("2020-01-01", "2020-09-27", 35_961, "2020-11-05"),
        _fact("2020-01-01", "2020-09-27", 30_224, "2021-11-12"),
        _fact("2020-01-01", "2020-12-31", 41_908, "2021-02-25"),
        _fact("2020-01-01", "2020-12-31", 41_651, "2022-02-24"),
    ]

    result = quarterly_facts_from_facts(facts, [date(2020, 9, 30), date(2020, 12, 31)])

    assert result["value"].iloc[1] == PFE_2020_Q4_LATEST
    assert result["provenance"].iloc[1] == FactProvenance.YTD_DERIVED


@pytest.mark.xfail(
    strict=True,
    reason="known limit (spec D7): nearest-previous-quarter misses a seasonal peak",
)
def test_a_restated_year_respects_last_years_seasonal_step() -> None:
    """GOOGL 2012: Motorola Home left between the Q3 10-Q and the 10-K.

    The right Q4 (14,419) is a seasonal peak above Q3 (13,304); the mixed one
    (13,215) sits next to Q3, so the rule picks it. Kept as a strict xfail so a
    future rule that fixes it without the regressions shows up here.
    """
    facts = [
        _fact("2011-07-01", "2011-09-30", 9_720, "2012-10-30"),
        _fact("2011-10-01", "2011-12-31", 10_583, "2013-01-29"),
        _fact("2012-07-01", "2012-09-30", 13_304, "2013-10-24"),
        _fact("2012-01-01", "2012-09-30", 36_960, "2012-10-30"),
        _fact("2012-01-01", "2012-09-30", 35_756, "2013-10-24"),
        _fact("2012-01-01", "2012-12-31", 50_175, "2013-01-29"),
        _fact("2012-01-01", "2012-12-31", 50_175, "2014-02-12"),
    ]
    quarters = [date(2011, 9, 30), date(2011, 12, 31)]
    quarters += [date(2012, 3, 31), date(2012, 6, 30)]
    quarters += [date(2012, 9, 30), date(2012, 12, 31)]

    result = quarterly_facts_from_facts(facts, quarters)

    assert result["value"].iloc[-1] == GOOGL_2012_Q4


def test_a_quarter_tagged_with_the_full_years_value_is_not_a_quarter() -> None:
    """ORCL FY2018: the 10-K tagged the year's revenue with a 91-day context."""
    facts = [
        _fact("2017-06-01", "2018-02-28", 28_579, "2018-03-21"),
        _fact("2017-06-01", "2018-05-31", 39_383, "2019-06-21"),
        _fact("2018-03-01", "2018-05-31", 39_383, "2020-06-22"),
    ]

    result = quarterly_facts_from_facts(facts, [date(2018, 6, 30)])

    assert result["value"].iloc[0] == ORCL_FY2018_Q4
    assert result["provenance"].iloc[0] == FactProvenance.YTD_DERIVED


def test_a_quarter_equal_to_another_tags_full_year_is_not_a_quarter() -> None:
    """ORCL FY2020: the 91-day Revenues fact equals the year filed under another tag."""
    facts = [
        _fact("2019-06-01", "2020-02-29", 28_812, "2020-03-12"),
        _fact("2019-06-01", "2020-05-31", 39_068, "2020-06-22"),
        _fact("2020-03-01", "2020-05-31", 39_068, "2020-06-22"),
    ]
    other_tag_years = annual_totals_by_end([
        [_fact("2019-06-01", "2020-05-31", 39_068, "2020-06-22")]
    ])

    result = quarterly_facts_from_facts(
        facts[:1] + facts[2:], [date(2020, 6, 30)], annual_totals=other_tag_years
    )

    assert result["provenance"].iloc[0] != FactProvenance.NATIVE


def test_a_quarterly_average_may_equal_the_annual_average() -> None:
    """A stable share count averages the same over a quarter and a year."""
    facts = [
        _fact("2019-07-01", "2020-06-30", 2_400),
        _fact("2020-04-01", "2020-06-30", 2_400),
    ]

    result = quarterly_facts_from_facts(
        facts, [date(2020, 6, 30)], PeriodMeasure.PERIOD_AVERAGE
    )

    assert result["provenance"].iloc[0] == FactProvenance.NATIVE


def test_a_restated_year_without_a_previous_quarter_is_left_missing() -> None:
    facts = [
        _fact("2018-01-01", "2018-09-30", 39_670, "2018-11-08"),
        _fact("2018-01-01", "2018-12-31", 53_647, "2019-02-28"),
        _fact("2018-01-01", "2018-12-31", 40_825, "2021-02-25"),
    ]

    result = quarterly_facts_from_facts(facts, [date(2018, 12, 31)])

    assert pd.isna(result["value"].iloc[0])
    assert result["provenance"].iloc[0] == FactProvenance.MISSING


def test_annual_minus_three_ignores_a_later_restatement_of_the_year() -> None:
    """COP 2010: the FY2012 10-K restated 2010 for the Phillips 66 spin-off."""
    facts = [
        _fact("2010-01-01", "2010-03-31", 44_821, "2010-05-04"),
        _fact("2010-04-01", "2010-06-30", 45_686, "2010-08-05"),
        _fact("2010-07-01", "2010-09-30", 47_208, "2010-11-02"),
        _fact("2009-12-31", "2010-12-31", 189_441, "2011-02-23"),
        _fact("2009-12-31", "2010-12-31", 56_215, "2013-02-19"),
    ]

    result = quarterly_facts_from_facts(facts, [date(2010, 9, 30), date(2010, 12, 31)])

    assert result["value"].iloc[1] == COP_2010_Q4_FIRST_REPORTED


def test_native_quarter_still_takes_its_latest_restatement() -> None:
    facts = [
        _fact("2018-07-01", "2018-09-30", 13_298, "2018-11-08"),
        _fact("2018-07-01", "2018-09-30", RESTATED_NATIVE_QUARTER, "2019-11-07"),
    ]

    result = quarterly_facts_from_facts(facts, [date(2018, 9, 30)])

    assert result["value"].iloc[0] == RESTATED_NATIVE_QUARTER


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

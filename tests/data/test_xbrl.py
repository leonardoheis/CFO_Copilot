from datetime import date

import pandas as pd

from app.data.dates import nearest_quarter_end
from app.data.xbrl import (
    InstantXbrlFact,
    XbrlFact,
    deduplicate_facts,
    instant_series_from_facts,
    quarterly_series_from_facts,
)

EXPECTED_Q4_VALUE = 250
EXPECTED_NATIVE_Q2_VALUE = 140


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


def test_deduplicate_facts_keeps_latest_filing() -> None:
    facts = [
        _fact("2020-01-01", "2020-03-31", 100, "2020-05-01"),
        _fact("2020-01-01", "2020-03-31", 110, "2021-02-01"),
    ]

    assert deduplicate_facts(facts) == {
        (date(2020, 1, 1), date(2020, 3, 31)): 110.0,
    }


def test_deduplicate_facts_rejects_outvoted_accession() -> None:
    facts = [
        _fact("2020-01-01", "2020-03-31", 100, "2020-05-01") | {"accn": "good-1"},
        _fact("2020-01-01", "2020-03-31", 100, "2021-05-01") | {"accn": "good-2"},
        _fact("2020-01-01", "2020-03-31", 120, "2022-05-01") | {"accn": "bad"},
        _fact("2020-04-01", "2020-06-30", 200, "2020-08-01") | {"accn": "good-1"},
        _fact("2020-04-01", "2020-06-30", 200, "2021-08-01") | {"accn": "good-2"},
        _fact("2020-04-01", "2020-06-30", 220, "2022-08-01") | {"accn": "bad"},
    ]

    assert deduplicate_facts(facts) == {
        (date(2020, 1, 1), date(2020, 3, 31)): 100.0,
        (date(2020, 4, 1), date(2020, 6, 30)): 200.0,
    }


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


def test_quarterly_series_derives_q4_from_fy_and_nine_months() -> None:
    facts = [
        _fact("2020-01-01", "2020-09-30", 750),
        _fact("2020-01-01", "2020-12-31", 1_000),
    ]

    result = quarterly_series_from_facts(facts, [date(2020, 12, 31)])

    assert result.iloc[0] == EXPECTED_Q4_VALUE


def test_quarterly_series_prefers_native_quarter_over_ytd_difference() -> None:
    facts = [
        _fact("2020-01-01", "2020-03-31", 100),
        _fact("2020-01-01", "2020-06-30", 250),
        _fact("2020-04-01", "2020-06-30", 140),
    ]

    result = quarterly_series_from_facts(facts, [date(2020, 6, 30)])

    assert result.iloc[0] == EXPECTED_NATIVE_Q2_VALUE


def test_nearest_quarter_end_accepts_fiscal_period_offset() -> None:
    assert nearest_quarter_end(date(2020, 12, 27)) == date(2020, 12, 31)


def test_quarterly_series_returns_nan_for_missing_quarter() -> None:
    result = quarterly_series_from_facts([], [date(2020, 3, 31)])

    assert pd.isna(result.iloc[0])

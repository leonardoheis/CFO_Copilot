from datetime import date

import pandas as pd
import pytest

from app.data.dates import QUARTER_END_TOLERANCE_DAYS, nearest_quarter_end
from app.data.exceptions import MalformedPayloadError
from app.data.xbrl import (
    InstantXbrlFact,
    XbrlFact,
    instant_series_from_facts,
    quarterly_facts_from_facts,
)

EXPECTED_Q4_VALUE = 250
EXPECTED_NATIVE_Q2_VALUE = 140
EXPECTED_LATEST_FILING_VALUE = 110.0


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


def test_quarterly_facts_derives_q4_from_fy_and_nine_months() -> None:
    facts = [
        _fact("2020-01-01", "2020-09-30", 750),
        _fact("2020-01-01", "2020-12-31", 1_000),
    ]

    result = quarterly_facts_from_facts(facts, [date(2020, 12, 31)])

    assert result["value"].iloc[0] == EXPECTED_Q4_VALUE


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
    with pytest.raises(MalformedPayloadError, match="duration fact dates"):
        quarterly_facts_from_facts(
            [_fact("not-a-date", "2020-03-31", 100)],
            [date(2020, 3, 31)],
        )


def test_malformed_fact_value_raises_data_source_error() -> None:
    with pytest.raises(MalformedPayloadError, match="fact value"):
        quarterly_facts_from_facts(
            [_fact("2020-01-01", "2020-03-31", "not-a-number")],  # type: ignore[arg-type]
            [date(2020, 3, 31)],
        )


def test_malformed_instant_fact_date_raises_data_source_error() -> None:
    with pytest.raises(MalformedPayloadError, match="instant fact date"):
        instant_series_from_facts(
            [{"end": "not-a-date", "val": 100, "filed": "2021-01-01"}],
            [date(2020, 3, 31)],
        )

from datetime import date

import pandas as pd
import pytest

from app.data.coverage import COVERAGE_FIELDS, evaluate_coverage
from app.data.dates import quarter_end_dates

ALL_DATES = quarter_end_dates(date(2006, 1, 1), date(2012, 12, 31))
SEC_DATES = quarter_end_dates(date(2008, 4, 1), date(2012, 12, 31))
EXPECTED_REVENUE_ERROR = 0.5


def _panel(dates: list[date], value: float = 100.0) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for quarter_date in dates:
        row: dict[str, object] = {"date": quarter_date}
        row.update(dict.fromkeys(COVERAGE_FIELDS, value))
        rows.append(row)
    return pd.DataFrame(rows)


def test_coverage_report_passes_all_gates_for_complete_data() -> None:
    report = evaluate_coverage(
        "AMZN",
        _panel(ALL_DATES),
        _panel(SEC_DATES),
        ALL_DATES,
    )

    assert report.passed is True
    assert all(report.gates.values())
    assert report.oldest_alpha_quarter == "2006-03-31"
    assert report.newest_alpha_quarter == "2012-12-31"


def test_coverage_report_fails_when_pre_xbrl_field_is_missing() -> None:
    alpha = _panel(ALL_DATES)
    alpha.loc[alpha["date"] == date(2007, 6, 30), "eps"] = float("nan")

    report = evaluate_coverage("AMZN", alpha, _panel(SEC_DATES), ALL_DATES)

    assert report.passed is False
    assert report.gates["pre_xbrl_complete"] is False
    assert report.pre_xbrl["eps"].missing_dates == ("2007-06-30",)


def test_coverage_report_fails_when_overlap_values_disagree() -> None:
    sec = _panel(SEC_DATES)
    sec.loc[sec["date"] == date(2010, 3, 31), "revenue_usd_m"] = 200.0

    report = evaluate_coverage("AMZN", _panel(ALL_DATES), sec, ALL_DATES)

    assert report.passed is False
    assert report.gates["overlap_agreement"] is False
    assert report.overlap_max_relative_error["revenue_usd_m"] == pytest.approx(
        EXPECTED_REVENUE_ERROR,
    )

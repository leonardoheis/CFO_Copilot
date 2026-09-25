from datetime import date

import pandas as pd
import pytest

from app.data.exceptions import MalformedPayloadError
from app.data.sources.alpha_vantage.parsing import number, report_date, reports


def test_fiscal_date_outside_the_tolerance_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unreachable at the shipped 46-day tolerance; guards a future tightening."""
    monkeypatch.setattr(
        "app.data.sources.alpha_vantage.parsing.QUARTER_END_TOLERANCE_DAYS",
        5,
    )

    with pytest.raises(MalformedPayloadError, match="cannot be placed"):
        report_date({"fiscalDateEnding": "2006-02-10"})


def test_every_calendar_date_maps_to_a_quarter_at_the_shipped_tolerance() -> None:
    """46 days is exactly half the longest quarter, so no date falls outside one."""
    for day in pd.date_range(date(2006, 1, 1), date(2006, 12, 31)):
        assert report_date({"fiscalDateEnding": day.date().isoformat()}) is not None


def test_out_of_bounds_fiscal_date_raises_with_placement_message() -> None:
    with pytest.raises(MalformedPayloadError, match="cannot be placed"):
        report_date({"fiscalDateEnding": "9999-12-31"})


def test_unparsable_number_warns_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        result = number({"totalRevenue": "not-a-number"}, "totalRevenue")

    assert result is None
    assert "not a number" in caplog.text


def test_reports_rejects_non_list_payload() -> None:
    with pytest.raises(MalformedPayloadError, match="must be a list"):
        reports({"quarterlyReports": {}}, "quarterlyReports")


def test_reports_warns_and_skips_non_dict_entries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        result = reports(
            {"quarterlyReports": [{"fiscalDateEnding": "2006-03-31"}, "invalid"]},
            "quarterlyReports",
        )

    assert result == [{"fiscalDateEnding": "2006-03-31"}]
    assert "Skipping non-object" in caplog.text

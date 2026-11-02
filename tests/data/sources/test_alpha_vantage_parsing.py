from datetime import date

import pandas as pd
import pytest

from app.data.exceptions import MalformedPayloadError
from app.data.schema import FinancialQuarterValues
from app.data.sources.alpha_vantage.parsing import (
    fill_eps_from_net_income,
    number,
    report_date,
    reports,
)


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


def test_reports_rejects_a_payload_with_a_non_object_entry() -> None:
    payload: dict[str, object] = {
        "quarterlyReports": [{"fiscalDateEnding": "2006-03-31"}, "invalid"]
    }

    with pytest.raises(MalformedPayloadError, match="quarterlyReports"):
        reports(payload, "quarterlyReports")


def test_reports_returns_every_entry_of_a_well_formed_payload() -> None:
    entries = [{"fiscalDateEnding": "2006-03-31"}, {"fiscalDateEnding": "2006-06-30"}]

    assert reports({"quarterlyReports": entries}, "quarterlyReports") == entries


def test_reports_is_empty_when_the_key_is_absent() -> None:
    assert reports({}, "quarterlyReports") == []


SHARES = 440_000_000.0


def _quarter(
    net_income_usd_m: float | None,
    eps: float | None,
    shares: float | None = SHARES,
) -> FinancialQuarterValues:
    return FinancialQuarterValues(
        net_income_usd_m=net_income_usd_m, eps=eps, shares_outstanding=shares
    )


def _agreeing_history() -> dict[date, FinancialQuarterValues]:
    # COST's shape: reported EPS tracks net income / shares to within 1%.
    return {
        date(2010, 3, 31): _quarter(299.0, 0.68),
        date(2010, 9, 30): _quarter(432.0, 0.98),
        date(2010, 12, 31): _quarter(312.0, 0.71),
    }


def test_missing_eps_is_derived_when_the_filer_agrees_with_its_own_eps() -> None:
    values = {**_agreeing_history(), date(2010, 6, 30): _quarter(306.0, None)}

    fill_eps_from_net_income(values)

    assert values[date(2010, 6, 30)].eps == pytest.approx(306.0e6 / SHARES)


def test_reported_eps_is_never_overwritten() -> None:
    values = _agreeing_history()

    fill_eps_from_net_income(values)

    assert values[date(2010, 3, 31)].eps == pytest.approx(0.68)


def test_nothing_is_derived_for_a_filer_reporting_adjusted_eps() -> None:
    """MRK's shape: reported EPS runs ~35% above net income / shares."""
    values = {
        date(2015, 3, 31): _quarter(953.0, 0.85),
        date(2015, 9, 30): _quarter(1_830.0, 0.96),
        date(2015, 12, 31): _quarter(976.0, 0.93),
        date(2015, 6, 30): _quarter(1_000.0, None),
    }

    fill_eps_from_net_income(values)

    assert values[date(2015, 6, 30)].eps is None


def test_a_quarter_without_shares_stays_empty() -> None:
    values = {**_agreeing_history(), date(2010, 6, 30): _quarter(306.0, None, None)}

    fill_eps_from_net_income(values)

    assert values[date(2010, 6, 30)].eps is None


def test_nothing_is_derived_without_evidence_for_the_gate() -> None:
    values = {date(2010, 6, 30): _quarter(306.0, None)}

    fill_eps_from_net_income(values)

    assert values[date(2010, 6, 30)].eps is None


def test_a_derived_eps_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    values = {**_agreeing_history(), date(2010, 6, 30): _quarter(306.0, None)}

    fill_eps_from_net_income(values)

    assert "2010-06-30" in caplog.text
    assert "derived" in caplog.text

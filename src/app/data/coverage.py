from dataclasses import asdict, dataclass
from datetime import date
from typing import Final

import pandas as pd

from app.data.pipeline import XBRL_HISTORY_START
from app.data.schema import FINANCIAL_COLUMNS

COVERAGE_FIELDS: Final[tuple[str, ...]] = (
    *FINANCIAL_COLUMNS,
    "shares_outstanding",
)
OVERLAP_START: Final = date(2008, 4, 1)
OVERLAP_END: Final = date(2012, 12, 31)
EPS_RELATIVE_TOLERANCE: Final = 0.10
DEFAULT_RELATIVE_TOLERANCE: Final = 0.02
MIN_ABSOLUTE_TOLERANCE: Final = 1.0


@dataclass(frozen=True, slots=True)
class FieldCoverage:
    expected_quarters: int
    available_quarters: int
    completeness: float
    missing_dates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoverageReport:
    ticker: str
    oldest_alpha_quarter: str | None
    newest_alpha_quarter: str | None
    pre_xbrl: dict[str, FieldCoverage]
    handoff_missing_dates: tuple[str, ...]
    overlap_max_relative_error: dict[str, float]
    gates: dict[str, bool]
    passed: bool


def evaluate_coverage(
    ticker: str,
    alpha_panel: pd.DataFrame,
    sec_panel: pd.DataFrame,
    expected_dates: list[date],
) -> CoverageReport:
    alpha = _indexed_panel(alpha_panel)
    sec = _indexed_panel(sec_panel)
    pre_xbrl_dates = [
        quarter_date
        for quarter_date in expected_dates
        if quarter_date < XBRL_HISTORY_START
    ]
    pre_xbrl = {
        field: _field_coverage(alpha, field, pre_xbrl_dates)
        for field in COVERAGE_FIELDS
    }
    handoff_dates = [
        quarter_date
        for quarter_date in expected_dates
        if XBRL_HISTORY_START <= quarter_date <= OVERLAP_END
    ]
    handoff_missing = _missing_dates(sec, COVERAGE_FIELDS, handoff_dates)
    overlap_errors = _overlap_errors(alpha, sec)
    gates = {
        "pre_xbrl_complete": all(
            coverage.available_quarters == coverage.expected_quarters
            for coverage in pre_xbrl.values()
        ),
        "handoff_complete": not handoff_missing,
        "overlap_agreement": _overlap_passes(overlap_errors),
    }
    return CoverageReport(
        ticker=ticker.upper(),
        oldest_alpha_quarter=_oldest_date(alpha),
        newest_alpha_quarter=_newest_date(alpha),
        pre_xbrl=pre_xbrl,
        handoff_missing_dates=tuple(
            quarter_date.isoformat() for quarter_date in handoff_missing
        ),
        overlap_max_relative_error=overlap_errors,
        gates=gates,
        passed=all(gates.values()),
    )


def report_as_dict(report: CoverageReport) -> dict[str, object]:
    return asdict(report)


def _indexed_panel(panel: pd.DataFrame) -> pd.DataFrame:
    indexed = panel.copy()
    indexed["date"] = pd.to_datetime(indexed["date"]).dt.date
    return indexed.set_index("date")


def _field_coverage(
    panel: pd.DataFrame,
    field: str,
    expected_dates: list[date],
) -> FieldCoverage:
    missing_dates = _missing_dates(panel, (field,), expected_dates)
    available = len(expected_dates) - len(missing_dates)
    completeness = available / len(expected_dates) if expected_dates else 1.0
    return FieldCoverage(
        expected_quarters=len(expected_dates),
        available_quarters=available,
        completeness=completeness,
        missing_dates=tuple(item.isoformat() for item in missing_dates),
    )


def _missing_dates(
    panel: pd.DataFrame,
    fields: tuple[str, ...],
    expected_dates: list[date],
) -> list[date]:
    missing: list[date] = []
    for quarter_date in expected_dates:
        if quarter_date not in panel.index:
            missing.append(quarter_date)
            continue
        if any(
            field not in panel.columns or pd.isna(panel.loc[quarter_date, field])
            for field in fields
        ):
            missing.append(quarter_date)
    return missing


def _overlap_errors(
    alpha: pd.DataFrame,
    sec: pd.DataFrame,
) -> dict[str, float]:
    dates = [
        value
        for value in alpha.index
        if OVERLAP_START <= value <= OVERLAP_END and value in sec.index
    ]
    errors: dict[str, float] = {}
    for field in COVERAGE_FIELDS:
        differences: list[float] = []
        for quarter_date in dates:
            if field not in alpha.columns or field not in sec.columns:
                continue
            left = alpha.loc[quarter_date, field]
            right = sec.loc[quarter_date, field]
            if pd.isna(left) or pd.isna(right):
                continue
            denominator = max(abs(float(right)), MIN_ABSOLUTE_TOLERANCE)
            differences.append(abs(float(left) - float(right)) / denominator)
        errors[field] = max(differences, default=float("nan"))
    return errors


def _overlap_passes(errors: dict[str, float]) -> bool:
    for field, error in errors.items():
        if pd.isna(error):
            return False
        tolerance = (
            EPS_RELATIVE_TOLERANCE if field == "eps" else DEFAULT_RELATIVE_TOLERANCE
        )
        if error > tolerance:
            return False
    return True


def _oldest_date(panel: pd.DataFrame) -> str | None:
    if panel.empty:
        return None
    return min(panel.index).isoformat()


def _newest_date(panel: pd.DataFrame) -> str | None:
    if panel.empty:
        return None
    return max(panel.index).isoformat()

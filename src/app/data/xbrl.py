import logging
import math
import operator
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from enum import StrEnum
from typing import Final, TypedDict

import pandas as pd

from app.data.dates import QUARTER_END_TOLERANCE_DAYS, nearest_quarter_end
from app.data.xbrl_facts import (
    InstantXbrlFact,
    QuarterlyFact,
    XbrlFact,
    deduplicate_instant_facts,
    fact_period,
    fact_value,
    first_reported_fact_per_period,
    latest_fact_per_period,
)

__all__ = [
    "DerivedQuarter",
    "FactProvenance",
    "InstantXbrlFact",
    "PeriodMeasure",
    "QuarterlyFact",
    "XbrlFact",
    "annual_totals_by_end",
    "instant_series_from_facts",
    "quarterly_facts_from_facts",
]

MIN_QUARTER_DAYS: Final = 80
MAX_QUARTER_DAYS: Final = 100
TYPICAL_QUARTER_DAYS: Final = 91
MIN_YEAR_TO_DATE_DAYS: Final = 160
NATIVE_QUARTERS_BEFORE_YEAR_END: Final = 3
MAX_INSTANT_STALENESS_DAYS: Final = 100
SAME_BASIS_TOLERANCE: Final = 0.01
MIN_ANNUAL_DAYS: Final = 300
ANNUAL_TOTAL_TOLERANCE: Final = 0.001
logger = logging.getLogger(__name__)


class PeriodMeasure(StrEnum):
    """How a duration fact relates to the period it covers.

    A ``FLOW`` accumulates, so a quarter is the arithmetic difference between two
    cumulative filings. A ``PERIOD_AVERAGE`` does not accumulate: differencing two
    averages yields noise around zero, so the residual must be weighted by how
    many days each average covers.
    """

    FLOW = "flow"
    PERIOD_AVERAGE = "period_average"


class FactProvenance(StrEnum):
    """Which rule produced a quarter's value, and therefore how much to trust it."""

    NATIVE = "native"
    YTD_DERIVED = "ytd_derived"
    ANNUAL_MINUS_3Q = "annual_minus_3q"
    MISSING = "missing"


class DerivedQuarter(TypedDict):
    """A quarter's value together with what it was derived from.

    ``period_end`` is the filing's own period end, which for a fiscal filer is
    not the calendar quarter the value is stored against.
    """

    value: float
    filed: str
    period_end: date | None
    provenance: FactProvenance


def annual_totals_by_end(
    fact_lists: Iterable[list[XbrlFact]],
) -> dict[date, tuple[float, ...]]:
    """Collect every year-long value by its end date, across a concept's tags.

    Returns:
        End date to the annual values any of the tags filed for it.
    """
    totals: defaultdict[date, set[float]] = defaultdict(set)
    for facts in fact_lists:
        for fact in facts:
            if "start" not in fact:
                continue
            start, end = fact_period(fact)
            if (end - start).days >= MIN_ANNUAL_DAYS:
                totals[end].add(fact_value(fact))
    return {end: tuple(values) for end, values in totals.items()}


def quarterly_facts_from_facts(
    facts: list[XbrlFact],
    quarter_dates: list[date],
    measure: PeriodMeasure = PeriodMeasure.FLOW,
    annual_totals: Mapping[date, tuple[float, ...]] | None = None,
) -> pd.DataFrame:
    """Convert duration facts to values and their filing dates.

    ``annual_totals`` adds the years other tags of the same concept filed, so a
    quarter carrying another tag's annual value is caught too (ORCL FY2020).

    Returns:
        A dataframe with ``value`` and ``filed`` columns.
    """
    latest_by_period = latest_fact_per_period(facts)
    first_reported_by_period = first_reported_fact_per_period(facts)
    known_years = annual_totals_by_end([facts])
    for end, values in (annual_totals or {}).items():
        known_years[end] = known_years.get(end, ()) + values
    records: list[DerivedQuarter] = []

    for quarter_date in quarter_dates:
        native = _find_native_fact(latest_by_period, quarter_date)
        if native is not None and not (
            measure is PeriodMeasure.FLOW and _is_annual_total(known_years, native)
        ):
            records.append(native)
            continue

        previous_value = records[-1]["value"] if records else math.nan
        records.append(
            _same_basis_quarter(
                _derive_quarter(first_reported_by_period, quarter_date, measure),
                _derive_quarter(latest_by_period, quarter_date, measure),
                previous_value,
                quarter_date,
            )
        )

    return pd.DataFrame(records, index=quarter_dates)


def _is_annual_total(
    known_years: Mapping[date, tuple[float, ...]],
    native: DerivedQuarter,
) -> bool:
    """Spot a full year's flow filed under a quarter's dates (ORCL FY2018-22 Q4).

    Returns:
        Whether a year-long value ending on the same day equals the quarter's.
    """
    if native["period_end"] is None:
        return False
    return any(
        _agree(annual, native["value"], ANNUAL_TOTAL_TOLERANCE)
        for annual in known_years.get(native["period_end"], ())
    )


def _derive_quarter(
    values_by_period: dict[tuple[date, date], QuarterlyFact],
    quarter_date: date,
    measure: PeriodMeasure,
) -> DerivedQuarter | None:
    return _find_ytd_fact(
        values_by_period, quarter_date, measure
    ) or _find_annual_minus_three_quarters(values_by_period, quarter_date, measure)


def _same_basis_quarter(
    first_reported: DerivedQuarter | None,
    latest: DerivedQuarter | None,
    previous_value: float,
    quarter_date: date,
) -> DerivedQuarter:
    """Pick the subtraction whose two sides share a reporting basis.

    A restatement between the nine-month filing and the 10-K puts one pairing
    on two bases: first-reported values break when it lands after Q3 (PFE
    2020-Q4), latest values when the year is restated later (PFE 2018-Q4, COP
    2010-Q4). When they disagree, the one nearer the previous quarter wins.

    Returns:
        The chosen quarter, or a missing one when nothing can arbitrate.
    """
    if first_reported is None or latest is None:
        return first_reported or latest or _absent()
    if _agree(first_reported["value"], latest["value"]):
        return first_reported
    if math.isnan(previous_value):
        logger.warning(
            "Restated year leaves %s ambiguous (%s vs %s) and no previous quarter",
            quarter_date,
            first_reported["value"],
            latest["value"],
        )
        return _absent()
    # ponytail: nearest-previous-quarter heuristic; it misses a seasonal peak
    # (GOOGL 2012-Q4) and lumpy flows. A seasonal variant was measured and was
    # worse overall (spec D7). Both candidates are filed figures, never invented.
    return min(
        (first_reported, latest),
        key=lambda candidate: abs(candidate["value"] - previous_value),
    )


def _agree(left: float, right: float, tolerance: float = SAME_BASIS_TOLERANCE) -> bool:
    return abs(left - right) <= tolerance * max(abs(left), abs(right), 1.0)


def _absent() -> DerivedQuarter:
    return {
        "value": math.nan,
        "filed": "",
        "period_end": None,
        "provenance": FactProvenance.MISSING,
    }


def _period_weight(days: int, measure: PeriodMeasure) -> float:
    """Scale a value so that totals and parts are commensurable.

    Returns:
        ``1`` for a flow, whose values already sum; the day count for an
        average, whose values must be re-weighted before they do.
    """
    return float(days) if measure is PeriodMeasure.PERIOD_AVERAGE else 1.0


def _residual_value(
    total: float,
    total_days: int,
    parts: list[tuple[float, int]],
    measure: PeriodMeasure,
) -> float | None:
    """Recover the period a total covers but its parts do not.

    Returns:
        The residual, or ``None`` when the parts leave no period to attribute it
        to.
    """
    residual_days = total_days - sum(days for _value, days in parts)
    if residual_days <= 0:
        return None

    weighted_total = total * _period_weight(total_days, measure)
    weighted_parts = sum(value * _period_weight(days, measure) for value, days in parts)
    return (weighted_total - weighted_parts) / _period_weight(residual_days, measure)


def instant_series_from_facts(
    facts: list[InstantXbrlFact],
    quarter_dates: list[date],
) -> pd.DataFrame:
    """Align instant facts to quarter ends and retain filing dates.

    A snapshot describes the day it was taken, so it may only stand in for a
    quarter it is close to. Carrying the last known one forward without limit
    turns a filer that stopped reporting the tag into a flat line that reads as
    data; leaving those quarters empty is what lets a fallback fill them.

    Returns:
        A dataframe with ``value`` and ``filed`` columns.
    """
    selected = deduplicate_instant_facts(facts)
    records: list[QuarterlyFact] = []
    for quarter_date in quarter_dates:
        recent = [
            fact
            for end, fact in selected.items()
            if quarter_date >= end
            and (quarter_date - end).days <= MAX_INSTANT_STALENESS_DAYS
        ]
        if not recent:
            records.append({"value": math.nan, "filed": ""})
            continue
        latest = max(recent, key=operator.itemgetter("end"))
        records.append({"value": fact_value(latest), "filed": latest["filed"]})
    return pd.DataFrame(records, index=quarter_dates)


def _find_native_fact(
    values_by_period: dict[tuple[date, date], QuarterlyFact],
    quarter_date: date,
) -> DerivedQuarter | None:
    candidates: list[int] = []
    for period in values_by_period:
        start, end = period
        if (
            _matches_quarter(end, quarter_date)
            and MIN_QUARTER_DAYS <= (end - start).days <= MAX_QUARTER_DAYS
        ):
            candidates.append((end - start).days)
    if not candidates:
        return None

    target_duration = min(
        candidates, key=lambda duration: abs(duration - TYPICAL_QUARTER_DAYS)
    )
    for period in values_by_period:
        start, end = period
        if (
            _matches_quarter(end, quarter_date)
            and end > start
            and (end - start).days == target_duration
        ):
            fact = values_by_period[start, end]
            return {
                "value": fact["value"],
                "filed": fact["filed"],
                "period_end": end,
                "provenance": FactProvenance.NATIVE,
            }
    return None


def _find_ytd_fact(
    values_by_period: dict[tuple[date, date], QuarterlyFact],
    quarter_date: date,
    measure: PeriodMeasure = PeriodMeasure.FLOW,
) -> DerivedQuarter | None:
    candidates: list[tuple[int, DerivedQuarter]] = []
    previous_quarter = _previous_quarter_end(quarter_date)

    for (start, end), current_value in values_by_period.items():
        duration = (end - start).days
        if _matches_quarter(end, quarter_date) and duration >= MIN_YEAR_TO_DATE_DAYS:
            previous = next(
                (
                    (value, (fact_end - fact_start).days)
                    for (fact_start, fact_end), value in values_by_period.items()
                    if fact_start == start
                    and _matches_quarter(fact_end, previous_quarter)
                ),
                None,
            )
            if previous is None:
                continue
            previous_value, previous_days = previous
            residual = _residual_value(
                current_value["value"],
                duration,
                [(previous_value["value"], previous_days)],
                measure,
            )
            if residual is not None:
                candidates.append(
                    (
                        duration,
                        {
                            "value": residual,
                            "filed": current_value["filed"],
                            "period_end": end,
                            "provenance": FactProvenance.YTD_DERIVED,
                        },
                    ),
                )

    if not candidates:
        return None
    return min(candidates, key=operator.itemgetter(0))[1]


def _find_annual_minus_three_quarters(
    values_by_period: dict[tuple[date, date], QuarterlyFact],
    quarter_date: date,
    measure: PeriodMeasure = PeriodMeasure.FLOW,
) -> DerivedQuarter | None:
    """Derive a fiscal year-end quarter as annual minus three native quarters.

    Returns:
        The residual quarter value, or ``None`` when the year is incomplete.
    """
    annual_candidates: list[tuple[int, date, date, QuarterlyFact]] = []
    for (start, end), current_value in values_by_period.items():
        duration = (end - start).days
        if _matches_quarter(end, quarter_date) and duration >= MIN_YEAR_TO_DATE_DAYS:
            annual_candidates.append((duration, start, end, current_value))
    if not annual_candidates:
        return None

    annual_days, fiscal_start, fiscal_end, annual = max(
        annual_candidates,
        key=operator.itemgetter(0),
    )
    native_periods = [
        (value["value"], (end - start).days)
        for (start, end), value in values_by_period.items()
        if MIN_QUARTER_DAYS <= (end - start).days <= MAX_QUARTER_DAYS
        and fiscal_start <= start
        and fiscal_start < end < fiscal_end
    ]
    if len(native_periods) != NATIVE_QUARTERS_BEFORE_YEAR_END:
        return None
    residual = _residual_value(
        annual["value"],
        annual_days,
        native_periods,
        measure,
    )
    if residual is None:
        return None
    return {
        "value": residual,
        "filed": annual["filed"],
        "period_end": fiscal_end,
        "provenance": FactProvenance.ANNUAL_MINUS_3Q,
    }


def _matches_quarter(value: date, quarter_date: date) -> bool:
    try:
        return (
            nearest_quarter_end(
                value,
                tolerance_days=QUARTER_END_TOLERANCE_DAYS,
            )
            == quarter_date
        )
    except ValueError:
        logger.warning(
            "SEC fact date %s cannot be placed on a calendar quarter",
            value,
        )
        return False


def _previous_quarter_end(value: date) -> date:
    quarter = pd.Period(value, freq="Q")
    return (quarter - 1).end_time.date()

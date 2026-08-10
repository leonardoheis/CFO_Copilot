import operator
from collections import defaultdict
from datetime import date
from typing import Final, NotRequired, TypedDict

import pandas as pd

from app.data.dates import nearest_quarter_end

MIN_QUARTER_DAYS: Final = 80
MAX_QUARTER_DAYS: Final = 100
MIN_YEAR_TO_DATE_DAYS: Final = 160
MIN_REJECTED_PERIODS: Final = 2


class XbrlFact(TypedDict):
    start: str
    end: str
    val: int | float
    filed: str
    accn: NotRequired[str]


class InstantXbrlFact(TypedDict):
    end: str
    val: int | float
    filed: str
    accn: NotRequired[str]


class QuarterlyFact(TypedDict):
    value: float
    filed: str


def deduplicate_facts(
    facts: list[XbrlFact],
) -> dict[tuple[date, date], float]:
    """Select trusted values for each XBRL period.

    Returns:
        A mapping from each reported period to its trusted value.
    """
    return {
        period: fact["value"]
        for period, fact in _deduplicate_fact_records(facts).items()
    }


def quarterly_facts_from_facts(
    facts: list[XbrlFact],
    quarter_dates: list[date],
) -> pd.DataFrame:
    """Convert duration facts to values and their filing dates.

    Returns:
        A dataframe with ``value`` and ``filed`` columns.
    """
    values_by_period = _deduplicate_fact_records(facts)
    records: list[QuarterlyFact] = []

    for quarter_date in quarter_dates:
        native = _find_native_fact(values_by_period, quarter_date)
        if native is not None:
            records.append(native)
            continue

        derived = _find_ytd_fact(values_by_period, quarter_date)
        records.append(
            derived if derived is not None else {"value": float("nan"), "filed": ""},
        )

    return pd.DataFrame(records, index=quarter_dates)


def instant_series_from_facts(
    facts: list[InstantXbrlFact],
    quarter_dates: list[date],
) -> pd.DataFrame:
    """Align instant facts to quarter ends and retain filing dates.

    Returns:
        A dataframe with ``value`` and ``filed`` columns.
    """
    selected = _deduplicate_instant_facts(facts)
    records: list[QuarterlyFact] = []
    for quarter_date in quarter_dates:
        matching = [fact for end, fact in selected.items() if end <= quarter_date]
        if not matching:
            records.append({"value": float("nan"), "filed": ""})
            continue
        latest = max(matching, key=operator.itemgetter("end"))
        records.append({"value": float(latest["val"]), "filed": latest["filed"]})
    return pd.DataFrame(records, index=quarter_dates)


def quarterly_series_from_facts(
    facts: list[XbrlFact],
    quarter_dates: list[date],
) -> pd.Series:
    """Convert SEC duration facts, including YTD facts, to calendar quarters.

    Returns:
        A series indexed by the requested quarter-end dates.
    """
    values_by_period = _deduplicate_fact_records(facts)
    result: list[float] = []

    for quarter_date in quarter_dates:
        native = _find_native_fact(values_by_period, quarter_date)
        if native is not None:
            result.append(native["value"])
            continue

        derived = _find_ytd_fact(values_by_period, quarter_date)
        result.append(derived["value"] if derived is not None else float("nan"))

    return pd.Series(result, index=quarter_dates, dtype="float64")


def _find_native_fact(
    values_by_period: dict[tuple[date, date], QuarterlyFact],
    quarter_date: date,
) -> QuarterlyFact | None:
    candidates = [
        (end - start).days
        for start, end in values_by_period
        if _matches_quarter(end, quarter_date)
        and MIN_QUARTER_DAYS <= (end - start).days <= MAX_QUARTER_DAYS
    ]
    if not candidates:
        return None

    target_duration = min(candidates, key=lambda duration: abs(duration - 91))
    for period in values_by_period:
        start, end = period
        if (
            _matches_quarter(end, quarter_date)
            and end > start
            and (end - start).days == target_duration
        ):
            return values_by_period[start, end]
    return None


def _find_ytd_fact(
    values_by_period: dict[tuple[date, date], QuarterlyFact],
    quarter_date: date,
) -> QuarterlyFact | None:
    candidates: list[tuple[int, QuarterlyFact]] = []
    previous_quarter = _previous_quarter_end(quarter_date)

    for (start, end), current_value in values_by_period.items():
        duration = (end - start).days
        if _matches_quarter(end, quarter_date) and duration >= MIN_YEAR_TO_DATE_DAYS:
            previous_value = next(
                (
                    value
                    for (fact_start, fact_end), value in values_by_period.items()
                    if fact_start == start
                    and _matches_quarter(fact_end, previous_quarter)
                ),
                None,
            )
            if previous_value is not None:
                candidates.append(
                    (
                        duration,
                        {
                            "value": current_value["value"] - previous_value["value"],
                            "filed": current_value["filed"],
                        },
                    ),
                )

    if not candidates:
        return None
    return min(candidates, key=operator.itemgetter(0))[1]


def _deduplicate_fact_records(
    facts: list[XbrlFact],
) -> dict[tuple[date, date], QuarterlyFact]:
    grouped: dict[tuple[date, date], list[XbrlFact]] = defaultdict(list)
    for fact in facts:
        period = (date.fromisoformat(fact["start"]), date.fromisoformat(fact["end"]))
        grouped[period].append(fact)

    outvoted_counts: dict[str, int] = defaultdict(int)
    for period_facts in grouped.values():
        majority = _majority_value(period_facts)
        if majority is None:
            continue
        for fact in period_facts:
            accession = fact.get("accn")
            if accession and not _values_match(float(fact["val"]), majority):
                outvoted_counts[accession] += 1
    rejected = {
        accession
        for accession, count in outvoted_counts.items()
        if count >= MIN_REJECTED_PERIODS
    }

    selected: dict[tuple[date, date], QuarterlyFact] = {}
    for period, period_facts in grouped.items():
        candidates = [fact for fact in period_facts if fact.get("accn") not in rejected]
        if not candidates:
            candidates = period_facts
        fact = max(candidates, key=operator.itemgetter("filed"))
        selected[period] = {
            "value": float(fact["val"]),
            "filed": fact["filed"],
        }
    return selected


def _deduplicate_instant_facts(
    facts: list[InstantXbrlFact],
) -> dict[date, InstantXbrlFact]:
    grouped: dict[date, list[InstantXbrlFact]] = defaultdict(list)
    for fact in facts:
        grouped[date.fromisoformat(fact["end"])].append(fact)
    selected: dict[date, InstantXbrlFact] = {}
    for end, period_facts in grouped.items():
        selected[end] = max(period_facts, key=operator.itemgetter("filed"))
    return selected


def _majority_value(facts: list[XbrlFact]) -> float | None:
    values = [float(fact["val"]) for fact in facts]
    for candidate in values:
        matches = sum(_values_match(candidate, value) for value in values)
        if matches > len(values) / 2:
            return candidate
    return None


def _values_match(left: float, right: float) -> bool:
    return abs(left - right) <= max(0.01, abs(right) * 0.001)


_FISCAL_TOLERANCE_DAYS: Final = 46


def _matches_quarter(value: date, quarter_date: date) -> bool:
    try:
        return (
            nearest_quarter_end(value, tolerance_days=_FISCAL_TOLERANCE_DAYS)
            == quarter_date
        )
    except ValueError:
        return False


def _previous_quarter_end(value: date) -> date:
    quarter = pd.Period(value, freq="Q")
    return (quarter - 1).end_time.date()

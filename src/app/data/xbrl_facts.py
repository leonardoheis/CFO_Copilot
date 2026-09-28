"""Choosing the authoritative SEC fact for a period.

A filer restates, and the same period arrives under several accession numbers
with different values. Nothing here derives a quarter; it only decides which
reported number for a period is the one to believe.
"""

import logging
import operator
from collections import defaultdict
from datetime import date
from typing import Final, NotRequired, TypedDict

from app.data.exceptions import MalformedPayloadError

MIN_REJECTED_PERIODS: Final = 2
logger = logging.getLogger(__name__)


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



def fact_period(fact: XbrlFact) -> tuple[date, date]:
    try:
        return (
            date.fromisoformat(fact["start"]),
            date.fromisoformat(fact["end"]),
        )
    except ValueError as error:
        msg = f"Malformed SEC duration fact dates: {fact!r}"
        raise MalformedPayloadError(msg) from error


def _group_facts_by_period(
    facts: list[XbrlFact],
) -> dict[tuple[date, date], list[XbrlFact]]:
    grouped: dict[tuple[date, date], list[XbrlFact]] = defaultdict(list)
    for fact in facts:
        if "start" not in fact:
            # SEC occasionally files an instant fact under a duration tag. It
            # describes a balance, not a period, so it cannot be a quarter.
            logger.warning("Skipping instant fact under a duration concept: %r", fact)
            continue
        grouped[fact_period(fact)].append(fact)
    return grouped


def _rejected_accessions(grouped: dict[tuple[date, date], list[XbrlFact]]) -> set[str]:
    """Accessions outvoted by the majority value in enough periods to distrust.

    Returns:
        Accession numbers to exclude when a period has an undisputed winner.
    """
    outvoted_counts: dict[str, int] = defaultdict(int)
    for period_facts in grouped.values():
        majority = _majority_value(period_facts)
        if majority is None:
            continue
        for fact in period_facts:
            accession = fact.get("accn")
            if accession and not _values_match(fact_value(fact), majority):
                outvoted_counts[accession] += 1
    return {
        accession
        for accession, count in outvoted_counts.items()
        if count >= MIN_REJECTED_PERIODS
    }


def _select_fact_per_period(
    grouped: dict[tuple[date, date], list[XbrlFact]],
    rejected: set[str],
) -> dict[tuple[date, date], QuarterlyFact]:
    selected: dict[tuple[date, date], QuarterlyFact] = {}
    for period, period_facts in grouped.items():
        candidates = [fact for fact in period_facts if fact.get("accn") not in rejected]
        if not candidates:
            candidates = period_facts
        fact = max(candidates, key=operator.itemgetter("filed"))
        selected[period] = {
            "value": fact_value(fact),
            "filed": fact["filed"],
        }
    return selected


def deduplicate_fact_records(
    facts: list[XbrlFact],
) -> dict[tuple[date, date], QuarterlyFact]:
    grouped = _group_facts_by_period(facts)
    rejected = _rejected_accessions(grouped)
    return _select_fact_per_period(grouped, rejected)


def deduplicate_instant_facts(
    facts: list[InstantXbrlFact],
) -> dict[date, InstantXbrlFact]:
    grouped: dict[date, list[InstantXbrlFact]] = defaultdict(list)
    for fact in facts:
        try:
            end = date.fromisoformat(fact["end"])
        except ValueError as error:
            msg = f"Malformed SEC instant fact date: {fact!r}"
            raise MalformedPayloadError(
                msg,
            ) from error
        grouped[end].append(fact)
    selected: dict[date, InstantXbrlFact] = {}
    for end, period_facts in grouped.items():
        selected[end] = max(period_facts, key=operator.itemgetter("filed"))
    return selected


def _majority_value(facts: list[XbrlFact]) -> float | None:
    values = [fact_value(fact) for fact in facts]
    for candidate in values:
        matches = sum(_values_match(candidate, value) for value in values)
        if matches > len(values) / 2:
            return candidate
    return None


def _values_match(left: float, right: float) -> bool:
    return abs(left - right) <= max(0.01, abs(right) * 0.001)


def fact_value(fact: XbrlFact | InstantXbrlFact) -> float:
    try:
        return float(fact["val"])
    except (TypeError, ValueError) as error:
        msg = f"Malformed SEC fact value: {fact!r}"
        raise MalformedPayloadError(
            msg,
        ) from error



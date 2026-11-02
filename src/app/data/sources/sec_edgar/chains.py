"""SEC accounting rules: tag-chain precedence, sign errors and share recovery."""

import logging
import math
from collections.abc import Callable
from datetime import date
from typing import cast

import pandas as pd

from .concepts import (
    COST_OF_REVENUE_PARTS,
    D_AND_A_PARTS,
    DILUTED_SHARES_FALLBACK,
    PER_SHARE_UNIT,
    TAG_CHAINS,
    USD_UNIT,
    ConceptSpec,
)
from .parsing import (
    cost_of_revenue,
    depreciation_and_amortization,
    implied_shares_from_earnings,
    split_factors_for_filing_dates,
    without_implausible_counts,
)
from .xbrl import (
    FactProvenance,
    InstantXbrlFact,
    PeriodMeasure,
    XbrlFact,
    annual_totals_by_end,
    instant_series_from_facts,
    quarterly_facts_from_facts,
)

logger = logging.getLogger(__name__)

# Called with (tag, unit); read lazily, so a chain stops reading once it is full.
type FactLookup = Callable[[str, str], list[XbrlFact]]
type _ShareRecordsReader = Callable[[list[XbrlFact], list[date]], pd.DataFrame]


def _without_placeholder_zeros(values: pd.Series) -> pd.Series:
    """Treat a superseded tag's 0 as not-reported rather than as data.

    Returns:
        The series with zeros replaced by NaN.
    """
    return values.where(values != 0)


def _with_sign_errors_corrected(
    facts: list[XbrlFact], cik: str, tag: str
) -> list[XbrlFact]:
    """Read a negative filing of a never-negative cost as its magnitude.

    Returns:
        The facts, each negative value replaced by its absolute value.
    """
    negative = [fact for fact in facts if fact["val"] < 0]
    if negative:
        logger.warning(
            "Reading %d negative %s facts for CIK %s as sign errors",
            len(negative),
            tag,
            cik,
        )
    return [fact | {"val": abs(fact["val"])} for fact in facts]


def _empty_chain_records(quarter_dates: list[date]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "value": math.nan,
            "filed": "",
            "period_end": None,
            "provenance": FactProvenance.MISSING,
        },
        index=quarter_dates,
    )


def _take_winning_rows(
    combined: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    prefer_largest: bool,
) -> pd.DataFrame:
    """Replace whole rows, so a value never outlives the origin it came from.

    Returns:
        ``combined`` with the candidate's rows wherever the candidate wins.
    """
    if prefer_largest:
        wins = candidate["value"].notna() & (
            combined["value"].isna() | candidate["value"].gt(combined["value"])
        )
    else:
        wins = combined["value"].isna() & candidate["value"].notna()
    return combined.mask(wins, candidate)


def _none_where_blank(filed: pd.Series) -> list[date | None]:
    """Turn the no-fact placeholder into a null, and a filing date into a date.

    Returns:
        One entry per quarter, null where nothing was filed.
    """
    return [date.fromisoformat(value) if value else None for value in filed]


def _none_where_missing(provenance: pd.Series) -> list[str | None]:
    """Turn the missing marker into a null the fallback can overwrite.

    Returns:
        One entry per quarter, null where no rule produced a value.
    """
    return [
        None if value is FactProvenance.MISSING else str(value) for value in provenance
    ]


def _tag_chain_records(
    cik: str,
    spec: ConceptSpec,
    facts_for: FactLookup,
    quarter_dates: list[date],
    splits: pd.Series | None,
) -> pd.DataFrame:
    """Resolve a concept across its tag chain, keeping each value's origin.

    Returns:
        A frame of ``value``, ``filed``, ``period_end`` and ``provenance``,
        each row taken from whichever tag supplied the winning value.
    """
    combined = _empty_chain_records(quarter_dates)
    facts_by_tag = {tag: facts_for(tag, spec.unit) for tag in spec.tags}
    if spec.never_negative:
        facts_by_tag = {
            tag: _with_sign_errors_corrected(facts, cik, tag)
            for tag, facts in facts_by_tag.items()
        }
    # A quarter equal to another tag's full year is that year (ORCL FY2020).
    annual_totals = (
        annual_totals_by_end(facts_by_tag.values()) if spec.unit == USD_UNIT else None
    )
    for tag in spec.tags:
        facts = facts_by_tag[tag]
        if facts:
            records = quarterly_facts_from_facts(
                facts, quarter_dates, annual_totals=annual_totals
            )
            values = records["value"]
            if spec.unit == PER_SHARE_UNIT:
                values /= split_factors_for_filing_dates(
                    records["filed"],
                    splits,
                )
            records = records.assign(
                value=_without_placeholder_zeros(values),
            )
            combined = _take_winning_rows(
                combined,
                records,
                prefer_largest=spec.prefer_largest,
            )
        if not spec.prefer_largest and combined["value"].notna().all():
            break
    return combined


def _shares_chain(
    cik: str,
    facts_for: FactLookup,
    quarter_dates: list[date],
    splits: pd.Series | None,
) -> pd.Series:
    def share_counts(spec: ConceptSpec, read_records: _ShareRecordsReader) -> pd.Series:
        combined = pd.Series(math.nan, index=quarter_dates, dtype="float64")
        for tag in spec.tags:
            facts = facts_for(tag, spec.unit)
            if facts:
                records = read_records(facts, quarter_dates)
                values = records["value"] * split_factors_for_filing_dates(
                    records["filed"],
                    splits,
                )
                combined = combined.combine_first(
                    without_implausible_counts(values, cik),
                )
        return combined

    outstanding = share_counts(
        TAG_CHAINS["shares_outstanding"],
        lambda facts, dates: instant_series_from_facts(
            cast("list[InstantXbrlFact]", facts), dates
        ),
    )
    if outstanding.notna().all():
        return outstanding

    # Instant shares-outstanding tags cover fewer early quarters than the
    # weighted-average diluted-share duration facts, so fill any remaining
    # gaps rather than only falling back when the primary is wholly empty.
    diluted_average = share_counts(
        DILUTED_SHARES_FALLBACK,
        lambda facts, dates: quarterly_facts_from_facts(
            facts, dates, PeriodMeasure.PERIOD_AVERAGE
        ),
    )
    return outstanding.combine_first(diluted_average)


def quarterly_financials(
    cik: str,
    facts_for: FactLookup,
    quarter_dates: list[date],
    splits: pd.Series | None,
) -> pd.DataFrame:
    """Derive one CIK's raw quarterly financials from its us-gaap facts.

    Returns:
        One row per quarter: every chain's value plus the revenue row's origin.
    """
    # Revenue anchors the row: it is the figure whose filing defines which
    # period the row actually describes, so its origin is the row's origin.
    revenue_records = _tag_chain_records(
        cik,
        TAG_CHAINS["revenue"],
        facts_for,
        quarter_dates,
        splits,
    )

    def chain_values(spec: ConceptSpec) -> pd.Series:
        return _tag_chain_records(cik, spec, facts_for, quarter_dates, splits)["value"]

    series_by_name = {
        name: chain_values(spec)
        for name, spec in TAG_CHAINS.items()
        if name not in {"shares_outstanding", "revenue"}
    }
    series_by_name["revenue"] = revenue_records["value"]
    series_by_name["cogs"] = cost_of_revenue(
        series_by_name["cogs"],
        chain_values(COST_OF_REVENUE_PARTS.total),
        chain_values(COST_OF_REVENUE_PARTS.products),
        chain_values(COST_OF_REVENUE_PARTS.services),
    )
    series_by_name["dep_amort"] = depreciation_and_amortization(
        series_by_name["dep_amort"],
        chain_values(D_AND_A_PARTS.depreciation),
        chain_values(D_AND_A_PARTS.amortization),
    )
    shares = _shares_chain(cik, facts_for, quarter_dates, splits)
    if not shares.notna().all():
        # Some filers (e.g. Google's legacy CIK) report no share-count fact
        # of any kind for their earliest quarters, but do report net income
        # and diluted EPS. Recover the implied share count for those gaps.
        implied = implied_shares_from_earnings(
            series_by_name["net_income"],
            series_by_name["eps"],
        )
        # A split-restated EPS can disagree in sign with its own net income
        # (see _fill_missing_financials), and the quotient of the two is then
        # a negative share count.
        shares = shares.combine_first(
            without_implausible_counts(implied, cik),
        )
    series_by_name["shares_outstanding"] = shares
    return pd.DataFrame(
        {
            "date": quarter_dates,
            **{name: series.tolist() for name, series in series_by_name.items()},
            # Null, not a "missing" marker: a null is what lets the vendor
            # fallback overlay its own provenance where SEC found nothing.
            "period_end": revenue_records["period_end"].tolist(),
            "financials_filed": _none_where_blank(revenue_records["filed"]),
            "financials_provenance": _none_where_missing(
                revenue_records["provenance"],
            ),
        },
    )

# Plan — fix the shares outstanding defects

Implements [`docs/specs/shares-outstanding-defects.md`](../specs/shares-outstanding-defects.md).
Both defects trace to one root cause: a fact's temporal kind is not carried
through the code that combines it. The fix makes that kind explicit.

## Step 1 — teach `xbrl.py` the difference between a flow and a period average

`src/app/data/xbrl.py`

Add `PeriodMeasure`, a `StrEnum` with `FLOW` and `PERIOD_AVERAGE`, and give
`quarterly_facts_from_facts` a `measure` parameter defaulting to `FLOW` so every
existing caller keeps its behaviour.

Both derivation branches currently subtract raw values. Replace that with one
residual helper parameterised by the measure:

| Measure | Weight per period | Residual |
|---|---|---|
| `FLOW` | 1 | `total − Σ parts` |
| `PERIOD_AVERAGE` | period length in days | `(total·days − Σ partᵢ·daysᵢ) / residual_days` |

A single weighted form covers both, so there is no branch inside the arithmetic:
weight each value by 1 or by its day count, subtract, divide by the residual
weight.

Functions touched: `quarterly_facts_from_facts`, `_find_ytd_fact`,
`_find_annual_minus_three_quarters`. New module-level helpers for the weight and
the residual.

Verification: PG's real facts must produce 2,412.6 m, not −3.3 m —
`(2,422.5 × 364 − 2,425.8 × 273) / 91`.

## Step 2 — stop carrying an instant fact forward indefinitely

`src/app/data/xbrl.py`

`instant_series_from_facts` accepts any fact with `end <= quarter_date`. Bound
it: a snapshot may serve a quarter only when it is no more than
`MAX_INSTANT_STALENESS_DAYS` old. One quarter plus the existing quarter-end
tolerance — 100 days — keeps a normally-filed cover-page count while rejecting a
multi-year-old one.

Quarters with no fresh snapshot become NaN and are logged. That is the point:
NaN is what lets Step 3's fallback run.

## Step 3 — let the fallback actually fire, and reject impossible counts

`src/app/data/sources/sec_edgar/source.py`

- `_fetch_diluted_shares_fallback` passes `PeriodMeasure.PERIOD_AVERAGE`, since
  `WeightedAverageNumberOfDilutedSharesOutstanding` is an average.
- A share count of zero or less is not data, and neither is one under 1% of
  the series' positive median — the audit after the re-ingest found 52 such
  quarters, all filer scale errors (TXN 2009-Q3 tagged 1,268 for 1,268 m).
  Add a module-level `_without_implausible_counts` that maps both to NaN with a
  warning, and apply it to the primary chain, the fallback and the
  earnings-implied counts before they are combined.

The early return in `_fetch_shares_chain` (`if combined.notna().all()`) needs no
change once Step 2 makes the stale series honestly incomplete — the guard then
means what it says.

`market_cap_usd_m` in `pipeline.py` needs no change: it is a product, so a NaN
share count propagates and satisfies requirement 4 on its own.

## Step 4 — tests

`tests/data/test_xbrl.py`

- YTD derivation of a period average uses day weighting (PG's numbers)
- annual-minus-three-quarters of a period average uses day weighting
- flow derivation is unchanged by the new parameter
- an instant fact older than the staleness bound yields NaN
- an instant fact inside the bound still serves its quarter

`tests/data/sources/test_sec_edgar.py`

- a weighted-average fallback reaching the Q4 path is not differenced raw
- a non-positive share count does not reach the panel
- a count tagged at the wrong scale does not reach the panel

## Step 5 — verify against the real panel

Re-run the three measurements the spec names as its regression test, against
freshly ingested data for the companies that exercise both paths (PG, NKE, GIS
for defect B; WMT, BA, DIS for defect A):

- repeat quarters attributable to carry-forward
- non-positive or sub-1%-of-median counts
- final-row implied share count vs reported diluted count

Then `uv run poe check`.

## Step 6 — provenance columns (done before the re-ingest)

Requirements 1 and 2 of [`final-row-provenance.md`](../specs/final-row-provenance.md),
added ahead of the batch re-ingest so the quota is spent once rather than twice.

Four new panel columns, anchored on revenue:

| Column | Holds |
|---|---|
| `period_end` | The filing's own period end |
| `period_end_offset_days` | Signed days from the calendar slot; 0 for a calendar filer |
| `financials_provenance` | `native`, `ytd_derived`, `annual_minus_3q`, `alpha_vantage` |
| `financials_filed` | The filing date behind the row (null for the vendor) |

Threaded through: `xbrl.py` reports the rule and period end per quarter;
`_fetch_tag_chain_records` replaces whole rows so a value never outlives the
origin it came from; the SEC path emits nulls rather than a "missing" marker so
the vendor fallback can overlay its own provenance; Alpha Vantage records the
filer's own `fiscalDateEnding` before it is snapped to a calendar quarter.

`xbrl.py` passed the 400-line limit and was split: `xbrl_facts.py` now owns
choosing the authoritative fact for a period, `xbrl.py` owns deriving a quarter
from it. Import direction is one-way.

## Out of scope

- `implied_shares_from_earnings`, whose sign inconsistency is now guarded but
  whose EPS-quotient logic is otherwise untouched.
- Re-ingesting all 60 panels. The parquet files stay as they are; regenerating
  them is a separate decision since it costs a full collection run.

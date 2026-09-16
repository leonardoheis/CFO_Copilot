# Spec — which value wins when a us-gaap concept has several tags

Status: proposed. Implemented by
[`docs/plans/ingestion-tag-precedence-and-cli.md`](../plans/ingestion-tag-precedence-and-cli.md).

## Problem

A panel field maps to an ordered chain of us-gaap tags, because filers do not
all use the same tag and a single filer changes tags over time. Today the
chain fills gaps in order and the first tag that reports a quarter wins.

That rule is wrong when a filer migrates between tags and keeps reporting the
old one with a *partial* figure. Oracle, `revenue`:

| quarter | `SalesRevenueNet` (wins today) | `Revenues` (truth) | ratio |
|---|---|---|---|
| 2009-03-31 … 2009-12-31 | 0 | 5453 … 5858 | 0.00 |
| 2010-03-31 | 458 | 6404 | 0.07 |
| 2010-06-30 | 1832 | 9505 | 0.19 |
| 2011-06-30 | 1829 | 10775 | 0.17 |

The stable 0.07–0.23 ratio is the signature of a segment subtotal, not a
total. The panel therefore carries revenue roughly 5× too low for eight
quarters, and every derived figure — gross margin, operating margin, any model
trained on the series — inherits the error.

## Required behaviour

**R1. A concept declares whether its tags are interchangeable totals.**
`ConceptSpec` carries a flag (`prefer_largest`). The default is false: the
existing first-non-null behaviour.

**R2. For a concept flagged as a total, the largest reported value wins.**
When two or more tags report the same quarter, take the maximum. A value
reported under a narrower tag is a component of the same period's total, so
the larger figure is the total by definition.

**R3. Zero never wins over a reported value.** For every concept, flagged or
not. A tag that reports 0 while another reports a real figure is a superseded
tag that has not stopped emitting, not a company with no revenue.

**R4. A concept that can legitimately be negative must never be flagged.**
"Largest" is meaningless where a later tag may correctly report a loss.

**R5. Fewer HTTP calls must not be preferred over a correct value.** Reading
the whole chain for a flagged concept is acceptable cost.

## Which concepts may be flagged

Only chains with more than one tag are affected. Verified against the six that
have one, and against every panel written so far:

| concept | tags | negatives observed | flag |
|---|---|---|---|
| `revenue` | 3 | **0** | yes |
| `cogs` | 3 | 0 | yes |
| `operating_cash_flow` | 2 | **yes** — TSLA 2017 Q3 is −301M | **no** — fails R4 |
| `capex` | 2 | 0 (reported as magnitude) | yes |
| `dep_amort` | 6 | 0 | yes |
| `eps` | 2 | **45** | **no** — see below |

`costs_and_expenses`, `operating_income`, `net_income` and
`shares_outstanding` have a single tag each, so precedence cannot arise.
`operating_income` (51 negatives) and `net_income` (60) would fail R4 if a tag
were ever added.

`operating_cash_flow` looked safe because free cash flow is derived, but the
tag is `NetCashProvidedByUsedInOperatingActivities` and it does go negative —
TSLA 2017 Q3 reports −301M. Flagging it would prefer the least-negative value
and hide a cash burn, so it stays off.

### The EPS counter-example — why R1 is a per-concept flag, not a global rule

`eps` chains `EarningsPerShareDiluted` → `EarningsPerShareBasic`. Diluted
assumes every convertible instrument is exercised, so its denominator is
larger and **Basic is always ≥ Diluted**. Verified, MSFT 2023:

| quarter | Diluted | Basic |
|---|---|---|
| Q1 | 2.45 | 2.46 |
| Q2 | 2.69 | 2.70 |
| Q3 | 2.99 | 3.00 |
| Q4 | 2.93 | 2.94 |

A global "prefer the largest" would silently switch every EPS in every panel
from Diluted to Basic — a wrong number in place of a right one, in a field
that is already correct. The chain order encodes a real preference here, and
must be left alone.

## Acceptance criteria

1. Re-ingesting **ORCL** yields revenue `6404 / 9505 / 7502 / 8582` for
   2010 Q1–Q4, and no quarter where revenue is 0.
2. Any cell that changes in another panel is justified against the filer's
   reported figure before it is accepted. A changed cell is not automatically
   a regression: `cogs` has the same defect as `revenue`.

   Observed: **MSFT gross profit changed in 8 quarters** (2015 Q3 – 2017 Q2).
   `CostOfGoodsSold` covers products only, `CostOfRevenue` covers products and
   services, and revenue includes services — so the larger figure is the
   correct match. Q2 FY2016: revenue 23,796, old gross profit 17,528, new
   13,924, and Microsoft reported 13,924. The old value overstated gross
   profit by 3,604 per quarter. **AAPL: 0 cells changed.**
3. MSFT EPS after the change equals MSFT EPS before it, quarter for quarter.
4. A `prefer_largest=False` chain still stops at the first tag that reports.
5. A negative value in a non-flagged chain survives unchanged.
6. No panel column that was non-null becomes null.

## Out of scope

- **Fiscal-year alignment.** Oracle's May year-end is a separate defect with
  its own failure mode; this spec does not address it.
- **Cross-source disagreement.** When SEC and Alpha Vantage both report a
  quarter, SEC still wins. Unchanged here.
- **Per-company tag overrides.** Rejected: curation cost grows with every
  ticker and every transition. Revisit only if a filer defeats R2.

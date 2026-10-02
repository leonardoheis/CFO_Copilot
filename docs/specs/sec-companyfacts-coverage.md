# Spec — SEC financials must not silently fall back to Alpha Vantage

Status: proposed. Implemented by
[`docs/plans/sec-companyfacts-coverage.md`](../plans/sec-companyfacts-coverage.md).

## Problem

16% of panel rows (766 of 4,779, COP excluded) take their financials from
Alpha Vantage instead of the filer's own XBRL. For most companies that is
only 2006–2008, before XBRL existed, which is expected. For eleven it is not:

| ticker | Alpha Vantage quarters | span |
|---|---|---|
| NEE | 59 | 2006 – 2026 |
| DUK | 44 | 2006 – 2026 |
| XOM | 43 | 2006 – 2016 |
| DIS | 42 | 2006 – 2016 |
| ABT | 41 | 2006 – 2026 |
| KO | 40 | 2006 – 2026 |
| COST | 30 | 2006 – 2026 |
| MDT | 28 | 2006 – 2013 |
| F | 22 | 2006 – 2026 |
| BBY | 14 | 2006 – 2026 |
| SO | 9 | 2006 – 2026 |

A vendor row has no filing date (`financials_filed` is null), so it cannot be
checked for lookahead, and its EPS is the vendor's `reportedEPS`, which for
most filers is an adjusted, non-GAAP figure (see the EPS section). Revenue
also anchors the row's provenance, so a revenue miss turns the whole row into
a vendor row.

The misses have four independent causes.

### Cause A — SEC's per-concept endpoint returns empty payloads

The source reads one us-gaap tag at a time from
`data.sec.gov/api/xbrl/companyconcept/CIK…/us-gaap/{tag}.json`. For some
company/tag pairs that endpoint answers `200` with `"units":{"USD":{}}` — an
empty object, not even the list the code expects — while the same tag in the
same company's `companyfacts` document is complete:

| CIK / tag | companyconcept | companyfacts |
|---|---|---|
| ABT `RevenueFromContractWithCustomerExcludingAssessedTax` | 0 facts | 122 facts, to 2026-03-31 |
| ABT `NetIncomeLoss` | 0 facts | 217 facts, to 2026-03-31 |
| KO `Revenues` | 0 facts | 106 facts, to 2026-04-03 |
| KO `NetIncomeLoss` | 0 facts | present |
| F `RevenueFromContractWithCustomerExcludingAssessedTax` | 0 facts | 107 facts, to 2026 |

The code reads the empty payload as "this filer does not use the tag", so the
gap is silent: ABT's live SEC fetch leaves revenue empty for every one of the
41 quarters the panel took from Alpha Vantage, and KO for all 40.

Survey of every company (60 tickers, 62 CIKs) against every tag the chains
read (24 tags, 1,488 pairs): of 920 pairs where `companyfacts` has facts,
**32 come back empty from `companyconcept`, all for ABT, F and KO** (11, 11
and 10 pairs). No pair comes back partially filled. For those three filers
the empty set covers nearly every concept — revenue, COGS, operating income,
net income, EPS, cash flow, capex, D&A, diluted shares — so they lose whole
rows, not single cells.

Reading `companyfacts` instead recovers **77 revenue quarters** (ABT 33,
KO 31, F 13).

### Cause B — revenue tags the chain does not read

The chain reads `RevenueFromContractWithCustomerExcludingAssessedTax`,
`SalesRevenueNet`, `SalesRevenueGoodsNet` and `Revenues`. Utilities and some
retailers report total revenue under other us-gaap tags:

| ticker | tag reported instead | years |
|---|---|---|
| NEE | `RegulatedAndUnregulatedOperatingRevenue` | 2009 – 2026 |
| DUK | `RegulatedAndUnregulatedOperatingRevenue` | 2015 – 2026 |

Adding `RegulatedAndUnregulatedOperatingRevenue` to the chain (which stays
`prefer_largest`) gains **85 quarters** (NEE 50, DUK 35) and changes **2**
already-SEC values:

| quarter | before | after | filer reported |
|---|---|---|---|
| DUK 2018 Q1 | 5,928 (contract revenue only) | 6,135 | 6,135 — a fix |
| NEE 2011 Q4 | 3,864 | 3,865 | rounding |

### Counter-example — why `RevenueFromContractWithCustomerIncludingAssessedTax` is not added

NEE, DUK, SO, BBY and GE also report this tag, and it looked like the obvious
second candidate. Simulated across every company it changes **17**
already-SEC values, 15 of them at SO and GE, and the new value is *larger
than the same quarter's total `Revenues`*, which is impossible within one
filing:

| quarter | `Revenues` | `…IncludingAssessedTax` |
|---|---|---|
| SO 2018 Q4 | 5,337 | 7,083 (derived from a restated 25,241 annual vs 23,495 originally filed) |
| SO 2021 Q1 | 5,910 | 6,900 |
| GE 2018 Q3 | 23,392 | 27,465 |

The tag carries values from a different filing vintage, and `prefer_largest`
would let them win. Not added.

### Known side effect of Cause A's fix — KO restatements

Once KO's `Revenues` becomes readable, `prefer_largest` picks its restated
figures over the originally filed `SalesRevenueGoodsNet` in **2** quarters:

| quarter | stored (as filed) | after | filer reported at the time |
|---|---|---|---|
| KO 2017 Q4 | 7,512 | 8,314 | 7,512 |
| KO 2018 Q2 | 8,927 | 9,421 | 8,927 |

Both values are the company's own; the later one is a restatement. This is
accepted and recorded, not fixed here (see Out of scope).

### Cause C — legacy CIKs not registered

Two companies re-registered with the SEC under a new entity, and only the new
CIK is configured:

| ticker | configured CIK | legacy CIK | legacy coverage |
|---|---|---|---|
| DIS | 0001744489 (from 2019) | 0001001039 `WALT DISNEY CO/` | 2007-09 – 2018-12 |
| MDT | 0001613103 (from 2015) | 0000064670 `MEDTRONIC INC` | 2008-04 – 2015-01 |

The registry already supports this shape (`dual_cik`, used by GOOGL and XOM).

### Cause D — the vendor fallback leaves EPS empty

Costco's Alpha Vantage `earnings` feed has no record at all for its May fiscal
quarters in 2008–2013, 2016, 2017 and 2020 (9 quarters), and records a
placeholder `reportedEPS: "0"` against a non-zero estimate for 2014 and 2015
(2 quarters, already discarded as placeholders). Its income statement carries
no `dilutedEPS`/`basicEPS`. Net income is present for all 11 quarters, so the
panel has revenue and net income but no EPS.

## Required behaviour

**R1. An empty SEC payload is not evidence of an unused tag.** The source must
obtain a company's facts from a payload that reports every tag the company
files, so that a tag is treated as unused only when the company truly never
filed it.

**R2. One company's facts are fetched once per ingestion.** Reading every tag
for a company must not cost one HTTP call per tag.

**R3. The revenue chain reads total revenue for filers that use
`RegulatedAndUnregulatedOperatingRevenue`,** keeping `prefer_largest` so a
component never displaces its total. It does not read
`RevenueFromContractWithCustomerIncludingAssessedTax` (counter-example above).

**R4. DIS and MDT read their legacy CIK** for the years before re-registration,
through the existing `dual_cik` registry shape. No code change.

**R5. EPS missing from the vendor fallback may be derived as net income ÷
shares outstanding only for a filer whose own vendor history shows the two
agree.** Agreement is measured on the filer's quarters that report all three
values: the median relative error of `netIncome / commonStockSharesOutstanding`
against `reportedEPS` must be at most 2%. A filer that fails the gate keeps
its EPS empty.

**R6. A derived value is distinguishable from a reported one** in the logs, so
a reviewer can find every derived EPS.

## Evidence for the EPS gate (R5)

A blanket derivation is wrong. Across 4,691 vendor quarters that report net
income, shares and EPS, the median relative error is **7.6%**, the 90th
percentile **60%**:

| ticker | median relative error |
|---|---|
| MRK | 35% |
| PFE | 33% |
| TSLA | 33% |
| F | 31% |
| ABT | 29% |

The vendor's `reportedEPS` is the adjusted figure for these filers, so a
GAAP-style derivation would splice a different metric into the series.

Thirteen filers agree within 2%, COST among them at **0.23%** over 70
quarters: LMT, DE, AAPL, UNP, COST, HD, MSFT, NKE, AMZN, XOM, NFLX, WMT, HON.
For COST the derived values are 0.68 (FY2010 Q3), 0.73 (FY2011 Q3) and 1.89
(FY2020 Q3).

TSLA is the other filer with absent earnings records (ten quarters,
2007–2010), all before its June 2010 listing; it fails the gate, so its
pre-listing EPS stays empty, which is correct.

## Acceptance criteria

1. After re-ingestion, ABT and KO take revenue from SEC for every quarter from
   2008 onward that SEC has filed; `financials_provenance` is a SEC value there.
2. NEE and DUK take revenue from SEC for every quarter from 2009 (NEE) and
   2015 (DUK) onward that SEC has filed.
3. DIS covers 2008–2016 and MDT 2008–2013 from SEC.
4. COST's 11 missing EPS cells are filled, each within 2% of
   net income ÷ shares, and logged as derived.
5. No filer outside the gate gets a derived EPS.
6. Every cell that changes in a panel that was already SEC-sourced is
   justified against the filer's reported figure before it is accepted
   (as in `sec-tag-precedence.md`, criterion 2). Expected revenue changes:
   exactly DUK 2018 Q1, NEE 2011 Q4, KO 2017 Q4 and KO 2018 Q2.
7. No panel column that was non-null becomes null.
8. An ingestion of one company makes one `companyfacts` request per CIK.

## Out of scope

- **XOM 2006–2016.** ExxonMobil filed quarterly revenue for those years under
  a company-specific extension tag, not us-gaap; SEC's API does not publish
  extension tags. The only us-gaap quarterly fact in 2012 Q2 at that scale is
  `CostsAndExpenses`. The Alpha Vantage fallback is the correct outcome.
- **Fiscal-calendar alignment** (COST's 12/12/12/16-week year, ORCL's May
  year-end). Some COST quarters still miss SEC revenue because a May fiscal
  quarter end cannot be placed on a calendar quarter; tracked separately.
- **BBY and SO.** Neither gains from this change: SO's vendor quarters are
  2006–2008 plus the latest quarter, and BBY's recent misses are its
  fiscal calendar (quarters ending early Aug/Nov/Feb/May).
- **Filing vintage.** Choosing between an as-filed and a restated value
  (KO above) needs its own rule.
- **The latest quarter.** Q2 2026 facts that SEC has not yet published fall
  back to the vendor, as intended.
- **Vendor EPS being adjusted EPS** where SEC is absent. Documented here, not
  changed.

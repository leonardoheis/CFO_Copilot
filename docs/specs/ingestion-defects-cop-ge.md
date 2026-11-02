# Spec — Ingestion defects: COP, GE, PFE, UNP, SLB, UNH

Six companies carry values the ingestion produced wrongly. NB01 excludes COP
entirely and blocks opex as a forecast target until this is fixed (EDA spec
Q6; EDA grilling Q16, Q25). PFE, UNP, SLB and UNH were added from the NB01
outlier register (2026-10-07); the file keeps its name because config and tests
point at it.

## Problem

NB01 found the defects by crashing, not by checking: COP's negative revenue made
log growth raise `NonPositiveValueError`. COP, GE and PFE come from quarters the
pipeline **derives by subtraction** (full year minus three quarters, or
year-to-date minus year-to-date) across figures that are not on the same basis.
UNP comes from Alpha Vantage rows that break the accounting identity. SLB and
UNH come from the cost-of-revenue tag chain, which captures only part of the
cost (SLB) or a cost the business does not have (UNH).

The outlier register only ranks suspects; it corrects nothing. The defects
below are still in `panel_long.parquet` until this spec is met.

## Evidence

All numbers from `data/processed/panel_long.parquet`, reported rows only.

**COP revenue.** Q4 2010 = **−81,500** USD m, provenance `annual_minus_3q`.
Neighbours: Q1–Q3 2010 = 44,821 / 45,686 / 47,208; Q1 2011 = 56,530; from
Q2 2011 the native values drop to 17,668 / 16,695 / 14,903. The drop is COP's
restatement for the Phillips 66 spin-off (downstream reported as discontinued).
The Q4 2010 subtraction takes a full-year figure on one basis and three quarters
on the other.

**GE opex.** 12 negative quarters: a run of 7 (2008-06 → 2010-03, −1,644 to
−3,921) and 5 fourth quarters (2013-12 −6,503, 2014-12 −6,171, 2020-12 −10,065,
2021-12 −5,343, 2022-12 −26,662), the Q4s with provenance `ytd_derived`. Against
the identity **opex ≈ gross profit − operating income**, GE agrees within 10% in
only **31%** of quarters (median gap 22%).

**GE opex — why it cannot be repaired (measured 2026-10-07, plan Step 6).**
GE almost never files `OperatingIncomeLoss` (in 2010 only Q2–Q3; none in 2016
or 2021), so its operating income comes from Alpha Vantage cell by cell while
its opex is SEC's `CostsAndExpenses − cogs`. Of GE's 73 SEC quarters:

| Opex from | Operating income from | Quarters | Miss the identity |
|---|---|---|---|
| SEC | Alpha Vantage | 51 | 47 |
| SEC | SEC | 16 | 9 |
| Alpha Vantage | Alpha Vantage | 6 | 0 |

So the identity failure is mostly two sources compared with each other. The
real question is whether GE's opex series is credible on its own. Rebuilt from
SEC with I1 and I7, it is not: opex / revenue is **negative in every quarter of
2008–2009** (median −0.25), reaches **3.06** in 2010, swings **−1.25 to 1.23**
in 2018 and reaches **1.29** in 2023; only 2011–2017 look normal (0.22–0.40).
Negative quarters drop from 12 to 9, not to 0. GE ran a bank inside it (GE
Capital) whose financing costs sit in `CostsAndExpenses`, and it split three
ways (HealthCare 2023, Vernova 2024). No tag rule rebuilds a consistent opex
without inventing figures.

**Counter-examples — the same mix is harmless elsewhere.** 201 SEC rows pair
SEC opex with Alpha Vantage operating income: BMY 71, GE 51, F 41, CVX 37,
COP 1. Outside GE the opex series are stable and never negative: BMY median
opex / revenue 0.49 (middle half 0.42–0.61), F 0.12 (0.11–0.13), CVX 0.31
(0.27–0.36). Their identity misses are an artefact of the check, not defects,
so the rule below names GE only.

**Reference rate for the identity.** Across the other 57 companies (4,578
quarters) the identity holds within 10% in **91%** of quarters, median gap 0.0.

**Counter-example — LMT is not a defect.** LMT's opex is negative in 62 of 81
quarters (median −42 vs revenue median 12,211), which looks like a wrong tag.
It is not: LMT's opex matches gross profit − operating income within 10% in
**98%** of quarters. Lockheed reports nearly all costs inside cost of sales, so
the gap between gross profit and operating income is small and can be negative.
A positivity rule on opex would have "fixed" correct data.

Provenance of all 92 negative opex rows: 67 `native`, 15 `alpha_vantage`,
10 `ytd_derived` — so the sign alone does not identify a defect.

**PFE revenue.** 2018-Q4 = **1,155** and 2019-Q4 = **1,843**, both
`ytd_derived`, between native quarters of 12,680–13,298. SEC companyfacts
(CIK 78003) shows the cause: 2018-Q4 = 40,825 − 39,670, where 40,825 is the
2018 full year **as restated in the FY2020 10-K** (Upjohn moved to discontinued
operations) and 39,670 is the nine-month total from the original 2018 10-Q.
2019-Q4 = 40,905 (FY2021 10-K restatement) − 39,062 (original). On the original
basis the same subtraction gives 53,647 − 39,670 = **13,977** and
51,750 − 39,062 = **12,688**, both in line with their neighbours. Same defect as
COP; the NB01 register lists 2019-Q1 only because that is where the value jumps
back up.

**UNP opex and gross profit.** All 8 UNP `alpha_vantage` quarters with the
needed columns (2006-Q3 → 2008-Q1) miss opex ≈ gross profit − operating income
by more than 10% (**0 of 8** agree; native UNP rows: 83%). The fourth quarters
are worst: opex −5,118 (2006-Q4) and −4,966 (2007-Q4), with gross profit 3,813
and 3,737 against about 1,900 in the other quarters. At the switch to native data
in 2008-Q2, opex steps from about 3,800 to 1,447, a change of definition and not
an economic event.

The cause is not the 2006–2008 rows alone: **UNP files no cost-of-revenue tag
at all** (none of `CostOfGoodsAndServicesSold`, `CostOfGoodsSold`,
`CostOfRevenue`, `CostOfServices`; CIK 100885). Its SEC gross profit and opex are
therefore always empty, and Alpha Vantage fills them cell by cell in every
quarter. UNP's gross margin ranges 0.35–0.96 over the series (0.67–0.86 in
2009–2011, 0.35–0.39 in 2013). A railroad has no cost of goods sold, the same
case as UNH.

**Why an identity check was withdrawn (I2, I6).** Rejecting derived and Alpha
Vantage rows that miss opex ≈ gross profit − operating income by more than 10%
would remove **143** rows. Most belong to companies whose **native** rows miss
it just as often (DIS 58, GE 50, PFE 31, BMY 29, OXY 29, COP 28 native misses):
their opex comes from `CostsAndExpenses − cogs`, a different definition, not
a defect. The rule would punch holes in their fourth quarters only (PFE: 11
`ytd_derived` rows), while Q1–Q3 on the same definition stayed. It would also
reject 2 LMT rows, breaking A4. I1 already removes the mixed-basis subtraction
that I2 was written for.

**SLB gross profit and opex.** 2016-Q2 → 2018-Q1 gross profit is about 5,000
on revenue of about 7,000 (gross margin about 0.70), against about 1,000 before
and after. SEC companyfacts (CIK 87347) shows that for those quarters SLB filed
cost of revenue **split** into `CostOfGoodsSold` (products: 1,983 as first
filed for 2016-Q2, 2,133 as restated a year later) and `CostOfServices` (4,332),
with no combined `CostOfGoodsAndServicesSold`. The tag chain picks up only the
products part. With the restated value a native quarter uses, the sum gives
2016-Q2 gross profit 7,164 − 6,465 = **699** (margin 0.10, against 1,060 / 6,520
= 0.16 in 2016-Q1). Opex is derived from gross profit, so it inherits the error while still
satisfying the identity; the identity check alone cannot catch this.

**Split cost of revenue elsewhere (measured 2026-10-07, every company).** Summing
products + services where no combined total is filed changes exactly three
companies, each toward its own surrounding quarters (median gross margin):

| Ticker | Quarters | Before → after | Outside those quarters |
|---|---|---|---|
| SLB | 2016-Q2 → 2018-Q1 (8) | 0.72 → 0.12 | 0.21 |
| VZ | 2015-Q2 → 2018-Q1 (12) | 0.83 → 0.60 | 0.57 |
| GE | 2008-Q2 → 2017-Q4 (39) | 0.55 → 0.39 | 0.34 |

VZ files cost of services and cost of equipment separately (2015-Q2: 6,994 +
5,455); today the panel holds the equipment part only.

**Counter-examples — where a filed total must win.** Two simpler rules were
measured and rejected:
- *Total always wins over the parts* breaks LLY: 2017-Q1 combined tag 958 against
  `CostOfGoodsSold` 1,348; the current largest-tag choice keeps 1,348. It also
  takes BA's 2009-Q4 combined tag of −14,508.
- *Largest of total and parts* breaks LMT (15 quarters) and touches HON and BA
  2017: LMT's products + services exceed its filed total by 10–500 m in every
  case, because the total carries unallocated adjustments. LMT is this spec's
  counter-example (A4).

So where a combined total is filed, today's choice stands; the parts are summed
only where it is not.

**UNH gross profit.** From 2008-Q2 gross margin is about **0.98**, falling to
about 0.87 from 2015-Q3; the Alpha Vantage era before it is about 0.24–0.27.
UnitedHealth files no cost of revenue. The `CostOfGoodsSold` tag it does file is
the cost of **products** sold, the pharmacy part of Optum: 353 in 2008-Q2,
against revenue 20,272 and medical costs (`PolicyholderBenefitsAndClaimsIncurredNet`)
of **15,257**. The 2015-Q3 step is that tag growing after the Catamaran pharmacy
acquisition (1,111 → 6,100), not a change in profitability. UNH is the highest
median gross margin in the panel (0.89), above ADBE (0.88), a software company.

## Required behaviour

**I1. A subtracted quarter uses one reporting basis.** A quarter derived as
annual minus three quarters, or as a year-to-date difference, is computed twice:
from first-reported figures and from latest-filed figures. When the two agree
within 1%, that value is used. When they disagree the year was restated, and
the value nearer the previous quarter wins. With no previous quarter the
quarter is left missing (D1). Both candidates are filed figures; none is
invented.

**Why neither pairing alone works (review, 2026-10-08).** A first version used
first-reported figures only. Re-ingesting 7 companies showed it breaks when the
restatement lands between the Q3 10-Q and the 10-K:

| Quarter | First-reported | Latest-filed | Correct | Nearer previous quarter picks |
|---|---|---|---|---|
| PFE 2018-Q4 | 13,977 | 1,155 | first | 13,977 |
| PFE 2019-Q4 | 12,688 | 1,843 | first | 12,688 |
| PFE 2020-Q4 | 5,947 | 11,427 | latest (Upjohn left 2020-11, after Q3) | 11,427 |
| PFE 2021-Q4 | 23,635 | 16,186 | first | 23,635 |
| COP 2010-Q4 | 51,726 | −81,500 | first | 51,726 |
| GOOGL 2012-Q4 | 13,215 | 14,419 | latest (Motorola Home left 2012-12, after Q3) | **13,215 — known defect** |

Across all 60 companies the two pairings disagree in **693 of 8,922** derived
values (7.8%, 56 companies): operating cash flow 273, capex 152, cost of
revenue 122, revenue 84, operating income 45, net income 17. 474 of them differ
by under 20% (ordinary reclassifications); 219 by more; 26 flip sign. The
rule changes derived quarters in nearly every company, so **all 60 companies
are re-ingested**, not only those named here (A5). Known ceiling: in a lumpy
series (capex) or at a seasonal peak the rule can pick the wrong pairing.

**Known defect — GOOGL 2012-Q4 (2026-10-08).** The rule chooses 13,215 (mixed
basis: the 10-K full year without Motorola Home minus the nine months as first
filed with it) over the right 14,419 (Google reported $14.42 bn), because Q4 is
Google's seasonal peak: the right value sits above Q3 (13,304) and the mixed one
next to it. GOOGL's revenue seasonal strength becomes 0.510 instead of
Appendix C's 0.279; NB01's A3 check documents GOOGL as an exception.

**A seasonal arbiter was measured and rejected (2026-10-08).** Choosing the
value nearer "previous quarter × last year's step into this quarter" fixes
GOOGL and keeps every PFE and COP case, but on a full re-ingest it changed 188
values and, against Alpha Vantage as an outside reference, was off by more than
50% in 23 of them (option A: 16) and by more than 100% in 10 (option A: 4),
median error 5.6% (option A: 4.8%). It produced impossible values: AAPL
2009-Q3 opex −2,610 (option A 1,421), GE 2018-Q4 revenue 8,675 (option A
26,499; Alpha Vantage 33,279), SBUX 2023-Q2 free cash flow 5,792 (option A
1,071). Each concept chooses its pairing on its own, so a row can mix bases
(AAPL: gross profit and operating income from different pairings). Alpha
Vantage is not ground truth either: many of its values equal the first-reported
subtraction exactly, GOOGL 2012-Q4 included.

**I2. Withdrawn (2026-10-07).** A rejection of derived quarters that miss the
opex identity; see "Why an identity check was withdrawn".

**I3. A change of reporting basis is a structural break.** COP's spin-off
restatement is recorded in the structural-breaks registry, so NB00's
`structural_break` flag and the feature group F see it.

**I4. Only affected companies are re-ingested**, through the existing reingest
path, and the fix is recorded in the reingest ledger.

**I6. Withdrawn (2026-10-07).** The same rejection for Alpha Vantage rows; UNP
is fixed by I8 instead.

**I7. Split cost of revenue is summed.** When a company files cost of products
and cost of services separately for a period with no combined total, cost of
revenue for that period is their sum. Where a combined total is filed, cost of
revenue is chosen exactly as before (see the LLY and LMT counter-examples).

**I8. A company can be declared to have no cost of revenue.** For such a
company, cost of revenue, gross profit, gross margin and any opex derived from
them are missing in every quarter and from every source. The declaration lives
in the company registry (`config/companies.yaml`), so adding a company is a YAML
edit. UNH and UNP are declared today. NB00's missing-value ledger explains the
resulting gaps as `no_cost_of_revenue`.

**I9. A company can be declared to have no reliable opex.** For such a company
opex is missing in every quarter and from every source; gross profit and every
other column stay. The declaration lives in the company registry
(`has_reliable_opex: false`), and NB00's missing-value ledger explains the gaps
as `unreliable_opex`. GE is the only company declared today.

**I10. A quarter that equals its full year is not a quarter.** A flow fact
with a quarter's dates whose value equals (within 0.1%) a year-long fact ending
on the same day, filed under any tag of the same concept, is a mis-tagged
annual total; the quarter is derived instead. Period averages (share counts) are exempt: a stable count
averages the same over a quarter and a year.

**I11. A negative cost of revenue is a sign error.** Cost-of-revenue facts are
read by their magnitude, before tags compete for the largest value, and each
correction is logged.

**I5. Exclusions lift on acceptance.** When A1, A4 and A6 hold, NB01 includes
COP again. Opex becomes a selectable target when A2, A7 and A8 also hold, since
UNP and SLB opex are wrong too. LMT needs nothing: opex is forecast as
the revenue-scaled change, which is defined for LMT's small signed values
(EDA grilling Q26, 2026-09-30).

## Review of the full re-ingest (2026-10-08)

All 60 companies re-ingested with I1 (final rule), I7, I8 and I9. Against the
2026-10-02 panel: A1, A2, A6, A7, A8 and A9 hold; the only new empty cells are
the declared ones (gross profit 160 = UNH + UNP; opex 240 = UNH + UNP + GE); no
quarter was left empty by I1's "no previous quarter" branch.

I1 also repaired defects nobody had listed, all Q4 revenue from mixed-basis
subtractions: IBM 2019–2020 (1,926 → 20,367; the "Kyndryl extreme" NB01 read as
a structural break), OXY 2012–2024 (≈2,000 → ≈7,000), KMB 2022–2023 (≈1,700 →
4,970), MRK 2019 (4,149 → 11,868), GE 2013 (20,971 → 40,187). Sign flips toward
plausible values: CAT 2014-Q4 and T 2008-Q4 operating income; HON, MRK, OXY and
SBUX free cash flow.

Accepted as is:
- SLB opex is −48 to −176 in four 2016–2017 quarters. SLB's opex is ±2% of
  revenue throughout (153–292 on ≈8,000): like LMT, its costs sit almost
  entirely in cost of revenue, so small negatives are noise, not a defect.

Remaining defect:
- **GE 2014-Q4** revenue is 22,675 against neighbours of ≈32,000, before and
  after this work: both I1 pairings straddle GE Capital's removal, and the rule
  picks the less wrong. Its gross profit is now −368 (was 5,017), because cost
  of revenue correctly includes services. GE's opex is already excluded (I9);
  this quarter's revenue and gross profit stay a known GE defect.

## New defects found by NB01 (2026-10-08)

The re-run of NB01 after the full re-ingest put two companies at the top of
its target and register extremes. Both are filer errors in SEC companyfacts.

**ORCL fiscal-Q4 revenue held the whole year.** Oracle's 10-Ks tagged the
fiscal year's `Revenues` with a 91-day context (2018-03-01 → 2018-05-31 =
39,383, the FY2018 total). The chain prefers the largest tag, so the full year
won the quarter. A scan of every company and every chain tag finds the pattern
**only in ORCL**, in five fiscal Q4s; I10 derives them as year minus nine
months: 39,383 / 39,506 / 39,068 / 40,479 / 42,440 → **11,014 / 11,137 /
10,439 / 11,227 / 11,840** (FY2018–FY2022; Oracle reported $11.14 bn, $10.44 bn,
$11.23 bn and $11.84 bn for FY19–FY22 Q4). FY2020 was missed by a first
version that compared only within one tag: its year was filed under
`RevenueFromContractWithCustomerExcludingAssessedTax`, its 91-day "quarter"
under `Revenues`; the rule now compares across the concept's tags, and the
widened scan still finds only ORCL.

**CAT 2008-Q2 and BA 2009-Q4 cost of revenue was filed negative.** Caterpillar's
2009 10-Q/A filed 2008-Q2 `CostOfGoodsSold` as −10,036 (first half −18,645), so
gross profit exceeded revenue (23,660 on 13,624). Boeing filed 2009-Q4
`CostOfRevenue` as −14,508; its magnitude matches its products + services
(14,465) within 0.3%, while the chain had taken products alone. The scan finds
no other negative cost-of-revenue fact. With I11: CAT gross margin 1.74 →
**0.26** (neighbours 0.25–0.27), opex 22,135 → 2,063; BA gross margin 0.32 →
**0.19**.

Re-ingesting ORCL, CAT and BA changes exactly these 11 values and nothing in
the other 57 companies.

**Alpha Vantage EBITDA is built on a different, sometimes broken, EBIT.** NB01's
EBITDA extremes were KMB 2006-Q2 (−10,806) and UNP 2006-Q4 and 2007-Q4 (8,954
and 8,835 against ≈1,100 in their other quarters). All three are Alpha Vantage
rows: its `ebitda` is its own `ebit` plus D&A, and that `ebit` is −11,044 for
KMB (operating income 544) and ≈8,500 for UNP (operating income 810 and 864).
The SEC rows define EBITDA as operating income + D&A, so the panel mixed two
definitions: 1,060 of the 1,697 Alpha Vantage EBITDA cells in the panel differ
from operating income + D&A by more than 1%, in 42 companies (IBM 72, PFE 70,
XOM 69, COP 67). Where Alpha Vantage has no D&A, its `ebitda` simply equals
operating income (ABT 2026-Q2 = 1,782; F 2007-Q1 = 2,267).

**I12. EBITDA is operating income + D&A from every source.** An Alpha Vantage
row takes D&A from its income statement, else from its cash-flow statement
(ABT, GE, SHW 2026-Q2); with neither, EBITDA is missing, never operating
income alone (F 2006-Q2 → 2008-Q1, six quarters, waived in NB00's ledger).
Known limit: Alpha Vantage's operating income is used as reported, and it is
not always right either (BMY 2024-Q1); it is already the panel's operating
income in every row where SEC has none, so I12 makes EBITDA consistent with it.

**T's BellSouth merger is a structural break.** The deal closed on 2006-12-29;
revenue goes from 15,891 (2006-Q4) to 28,969 (2007-Q1) and stays there. T gets
a second break at 2007-Q1, the first quarter on the merged basis.

**Re-ingest with I12 (2026-10-09).** All 60 companies, Alpha Vantage from its
cache. Against the panel before I12, only `ebitda_usd_m` changed: 1,398 cells in
53 companies. KMB 2006-Q2 = 782.7, UNP 2006-Q4 = 1,125 and 2007-Q4 = 1,201.
F's six quarters became missing; COST 2026-Q2 became filled (3,412, D&A 597
like its previous quarters), so F is now the only `unexplained` entry in
NB00's ledger. Seven SEC rows (ADBE, CL, SBUX, UNP) still equal the vendor's
figure because SEC operating income + SEC D&A happens to give the same number.

**ABT's SEC D&A is depreciation only (open).** ABT files `Depreciation` (≈370 a
quarter) and `AmortizationOfIntangibleAssets` (≈420) as separate facts with no
total, and the D&A chain takes the first, so ABT's SEC-era EBITDA leaves out
amortization. ABT has no SEC facts for 2026-Q2 yet, so that quarter is Alpha
Vantage's, which includes it: EBITDA 2,795 against 1,726 in 2026-Q1. Before I12
the same quarter was 1,782 (no D&A at all), so the mixed basis predates I12.
Like I7 for cost of revenue, the fix is to sum the parts when no total is
filed. That needs a scan of all 60 companies first.

## Step 8 results (2026-10-09, panel_long rebuilt by NB00 at 00:15)

| # | Result |
|---|---|
| A1 | Holds: COP has no non-positive revenue; 2010-Q4 = 51,726 between 47,208 and 56,530 |
| A2 | Holds: GE opex empty in 81 of 81 quarters, all `unreliable_opex`; revenue and gross profit present in all 81 |
| A4 | Holds: LMT opex = gross profit − operating income within 1% of revenue in 98% of 81 quarters (−323 to 1,253) |
| A5 | `uv run poe check` green (lint without nbstripout, to keep the notebooks' outputs) |
| A6 | Holds on its example values: 2018-Q4 = 13,977 and 2019-Q4 = 12,688. Both sit just above their neighbours (13,298 / 13,118 and 12,680 / 10,083) because Q4 is PFE's seasonal high; the defect was a drop of 1,100 and 1,800 |
| A7 | Holds: UNP has no gross profit, margin or opex; revenue, operating income and net income equal the 2026-10-02 panel in every quarter |
| A8 | Held at the full re-ingest; since then only I10/I11 (ORCL, CAT, BA 2009-Q4, intended) and I12 (EBITDA only) changed values |
| A9 | Holds: as A7, for UNH |
| A10 | Pending the user's NB01 run |
| A11 | Holds: only EBITDA changed (1,398 cells); KMB and UNP as required; 36 structural-break rows |

Lifted on these results: COP from `excluded_companies` and `opex_usd_m` from
`blocked_targets`. NB01 run offline with COP included (W&B and file writes
stubbed): every cell and assertion passes.

## Acceptance criteria

| # | Check |
|---|---|
| A1 | COP revenue has no non-positive quarter; Q4 2010 is missing or lies within the range of its adjacent reported quarters on the same basis |
| A2 | GE has no opex in any quarter, each gap explained as `unreliable_opex`; GE's gross profit, revenue and other columns are unchanged by I9 (changed 2026-10-07 from an identity rate, see "GE opex — why it cannot be repaired") |
| A3 | Withdrawn with I2 |
| A4 | LMT's opex stays small and signed, matching gross profit − operating income (the counter-example stays correct). Changed 2026-10-08 from "unchanged": the full re-ingest corrects 5 LMT quarters toward that pattern (2014-Q4 gross profit 4,475 → 1,268; 2008-Q4 revenue 9,773 → 11,132) |
| A5 | `uv run poe check` green; all 60 companies re-ingested with the same rules (I1 changes derived quarters almost everywhere) |
| A6 | PFE revenue 2018-Q4 and 2019-Q4 are missing or within the range of their adjacent quarters on the same basis (e.g. 13,977 and 12,688 on the original basis) |
| A7 | UNP has no gross profit, gross margin or opex in any quarter; its revenue, operating income and net income are unchanged |
| A8 | SLB 2016-Q2 → 2018-Q1, VZ 2015-Q2 → 2018-Q1 and GE 2008-Q2 → 2017-Q4 cost of revenue equals products + services; no other company's cost of revenue changes (LLY, LMT, BA unchanged) |
| A9 | UNH has no gross profit, gross margin or derived opex in any quarter; its revenue, operating income and net income are unchanged |
| A10 | Rebuilt, the NB01 outlier register no longer lists any of the defects above |
| A11 | Every Alpha Vantage EBITDA cell equals its operating income + D&A; KMB 2006-Q2 is 783 and UNP 2006-Q4 and 2007-Q4 are 1,125 and 1,201; re-ingesting changes only EBITDA cells; NB00 counts 9 × 4 structural-break rows |

## Out of scope

- LMT opex (correct data; see the counter-example). The revenue-scaled change
  makes it usable as a target without exclusion (EDA grilling Q26).
- Gross profit negatives (26 rows; genuine, e.g. BA's 2019–2020 charges).
- Any other company; a new defect is added here with its own evidence before
  it is fixed.
- The `CostsAndExpenses − cogs` opex definition that makes DIS, SBUX and DE
  differ from revenue − operating income (DIS median gap 3% of revenue). It is
  consistent within each company. Pairing SEC opex with Alpha Vantage operating
  income (BMY, F, CVX) is part of the accepted risk below; GE is I9.
- Alpha Vantage filling gross profit and opex cell by cell: an accepted risk,
  below.
- A guard on derived revenue against its neighbours. I1 fixes PFE on its own;
  add a guard only when a defect appears that I1 does not explain.

## Decisions taken by default — confirm or override

| # | Decision | Reason |
|---|---|---|
| D1 | Prefer leaving a mixed-basis quarter missing over imputing it | Missing is handled everywhere downstream (R2 of the EDA spec: no splicing); a guessed value is not |
| D2 | The 10% identity tolerance comes from the measured 91% reference rate | A rule calibrated on healthy companies, not chosen to make GE pass |

## Decisions taken by the user

| # | Decision | Reason |
|---|---|---|
| D3 | UNH gross profit is missing, not rebuilt from medical costs (2026-10-07) | Gross margin across the panel means revenue minus the cost of making what was sold. An insurer has no such cost; medical costs as COGS would give 1 − medical loss ratio, a different quantity under the same column name. It would also need a UNH-only tag rule. Missing is already handled downstream (D1) |
| D4 | UNP is declared without cost of revenue (2026-10-07) | It files no cost-of-revenue tag; every gross profit it has is Alpha Vantage's, ranging 0.35–0.96. Same reasoning as D3 |
| D5 | Alpha Vantage keeps filling gross profit and opex where SEC has no cost of revenue (2026-10-07) | The user accepts the risk below rather than leave 819 quarters empty |
| D6 | GE's opex is missing in every quarter; GE stays in the panel and opex is lifted as a target for everyone else (2026-10-07) | Its opex cannot be rebuilt from SEC (see the evidence); keeping it would keep opex blocked for all 59 other companies. Same treatment as D3/D4, for one column only |
| D7 | A restated year's derived quarter takes the pairing nearer the previous quarter (2026-10-08) | Chosen over leaving all 693 disagreements empty, which would gap free cash flow across most companies, and over the old latest-only rule, which brought back PFE and COP's defects. A seasonal variant was tried the same day and rejected on its error rate (see I1) |
| D8 | Alpha Vantage EBITDA is rebuilt as operating income + D&A in every row, not only KMB and UNP (2026-10-08) | One definition across sources and across each company's history; patching three quarters would leave 1,057 cells on the other definition |
| D9 | Only T's BellSouth merger is added as a structural break (2026-10-08) | The other large acquisitions in the panel (PFE–Wyeth, MRK–Schering-Plough, CMCSA–NBCUniversal, ECL–Nalco, DUK–Progress, MDT–Covidien) stay unflagged for now |

## Accepted risk — Alpha Vantage fills gross profit cell by cell

**What happens.** The panel takes SEC first and lets Alpha Vantage fill only the
cells SEC left empty (`combine_first`). Gross profit is revenue − cost of
revenue. When a company files no cost-of-revenue tag for a quarter, SEC leaves
gross profit, gross margin and opex empty, and Alpha Vantage's own figures fill
them. The row keeps `financials_provenance = native`, because that column records
only where **revenue** came from.

**How much (measured 2026-10-07, quarters since 2009 with SEC revenue but no SEC
cost of revenue, after I7).** 819 quarters in 22 companies, about a fifth of the
SEC-era panel:

| Pattern | Companies (quarters) |
|---|---|
| Never files cost of revenue | CMCSA 69, UPS 69, DIS 69, NEE 68, DUK 68 |
| Mostly missing | ORCL 63, SO 60, MCD 44, T 41, XOM 38 |
| Partly missing | SLB 34, VZ 33, COP 32, DE 32, CVX 32, SBUX 25, OXY 20, AMGN 11 |
| Negligible | GE 6, GOOGL 3, TSLA 1, BBY 1 |

UNP (69) and UNH are excluded from this risk by I8.

Operating income is filled the same way where a company does not file
`OperatingIncomeLoss`: 201 SEC rows pair SEC opex with Alpha Vantage operating
income (BMY 71, GE 51, F 41, CVX 37, COP 1). Outside GE (I9) those opex series
are stable, so this is accepted under the same decision (D5).

**Why it is a risk.**
- *Two definitions in one series.* Where a company files cost of revenue in some
  quarters and not others (SLB from 2018-Q2, VZ, COP, CVX…), the same column
  switches between "SEC revenue − SEC cost" and "Alpha Vantage's gross profit",
  whose cost definition is not published. A switch can show up as a level shift
  that a model reads as an economic change.
- *Untraceable.* Nothing in the row says the cell came from Alpha Vantage, so the
  provenance audit (EDA spec) cannot see it.
- *No filing date.* Alpha Vantage values carry no SEC filing date, so the
  point-in-time guarantee (no value used before it was public) cannot be checked
  for those cells.
- *Weak meaning for service businesses.* For media, logistics and utilities a
  gross margin is a vendor construct, not a figure the company reports.

**Why it is accepted (D5).** Leaving the cells empty would remove gross profit
and gross margin for five companies entirely and punch gaps in seventeen more;
gross margin feeds the outlier flag and several features. The user prefers
coverage and accepts the risk, on 2026-10-07.

**What would retire it.** For the quarters where both exist, compare Alpha
Vantage's gross profit with SEC revenue − SEC cost. If they agree within the D2
tolerance, the fill is harmless and this section can say so; if not, stop Alpha
Vantage from filling gross profit inside an SEC row and record the gaps.

# Spec — NB01's pending items: D&A, restated quarters, structural breaks

Status: implemented 2026-10-19 (C1, C3 tests and C5 `poe check` green); C2–C5
on real data wait for the NB00 re-ingest.

Plan: [`docs/plans/nb01-pending-items.md`](../plans/nb01-pending-items.md).
Related: [`ingestion-defects-cop-ge.md`](ingestion-defects-cop-ge.md) (I1, I7,
I12; the open "ABT's SEC D&A is depreciation only" section).

## Problem

NB01 and the thesis ("Pendientes") leave five items open. Three are data
defects that reach the forecast targets or their features; two are decisions.
All evidence below comes from SEC `companyfacts` downloaded on 2026-10-19 for
the 60 panel companies, the Alpha Vantage cache in `data/raw/alpha_vantage/`,
and `data/processed/panel_long.parquet` as rebuilt on 2026-10-09.

## Evidence

### E1. Depreciation and amortization filed as parts, with no total

The D&A chain takes the largest of its tags, `Depreciation` among them. When a
filer reports depreciation and intangible amortization (`AmortizationOf-
IntangibleAssets`) as separate facts and no total, the chain takes depreciation
alone and EBITDA leaves out amortization.

**It is not only ABT.** Fiscal years since 2008 with both parts and no total
tag: ABT 18, IBM 18, SHW 18, MSFT 19, ORCL 19, TXN 16, ECL 13, INTC 13, BBY 8,
MRK 6, GOOGL 6 (2008–2013), TSLA 4, NKE 3, BMY 1, LMT 1.

**The sum is the D&A the filer reports.** Against Alpha Vantage's cash-flow
D&A for the same fiscal year, depreciation + amortization matches to the
unit, and depreciation alone does not:

| Company, year | Depreciation | Amortization | Sum | Alpha Vantage |
|---|---|---|---|---|
| ABT 2025 | 1,434 | 1,682 | 3,116 | 3,116 |
| IBM 2025 | 2,284 | 2,737 | 5,021 | 5,021 |
| INTC 2025 | 10,757 | 949 | 11,706 | 11,706 |
| ORCL FY2026 | 7,623 | 1,671 | 9,294 | 9,293 |
| SHW 2025 | 340 | 337 | 677 | 677 |
| ECL 2024 | 635 | 301 | 936 | 935 |
| GOOGL 2013 | 2,781 | 1,158 | 3,939 | 3,939 |

ABT's EBITDA today mixes both bases at the forecast origin: its SEC quarters
carry ≈370 of D&A, and 2026-Q2, an Alpha Vantage row, carries 1,013.

**Counter-examples.**
- **BMY 2009:** amortization is filed as **−170**; the sum (299) is further
  from Alpha Vantage (724) than depreciation alone (469). A negative
  amortization is not an expense.
- **ECL 2025:** Alpha Vantage shows 673, depreciation alone; 2023 and 2024
  matched the sum, so the vendor dropped amortization that year, not ECL.
- **MSFT, TSLA:** the sum is below Alpha Vantage (MSFT FY2026 39,000 against
  43,448), whose line also includes "other" items. The sum is still nearer.
- **BBY 2015–16, TXN 2022–23:** amortization is filed as 0; the sum equals
  depreciation, so nothing changes.

**Alpha Vantage files a negative D&A at the forecast origin.** IBM files no
`OperatingIncomeLoss`, so its operating income and EBITDA come from Alpha
Vantage (I12). For 2026-Q2 the vendor's income statement gives D&A **−1,274**
(the negative of Q1's 1,274) and its cash-flow statement 1,349, so the panel's
EBITDA (1,341) sits below operating income (2,615). Four older rows also have
EBITDA below operating income (APD 2008-Q2, F 2009-Q1 and 2011-Q4, NEE
2017-Q4), all from SEC tags and by less than 300.

### E2. Restated quarters lost or mixed with old ones

Each of the three revenue defects is a quarter whose figures come from two
reporting bases, around a divestiture.

| Quarter | Panel | Neighbours | What the filings hold |
|---|---|---|---|
| ABT 2012-Q4 | 10,837 (native) | 2012-Q1–Q3: 5,284 / 5,313 / 5,265 | Q4 as first filed (FY2012 10-K, 2013-02-15) still includes AbbVie; Q1–Q3 are the 2013 10-Qs' restatement without it. A restated Q4, **5,632**, is filed in the FY2013 10-K (2014-02-21) |
| BMY 2008-Q4 | 2,367 (`ytd_derived`) | 2008-Q2–Q3: 5,203 / 5,254 | Full year **restated** without Mead Johnson (17,715, 10-K 2010-02-19) minus nine months **as filed** with it (15,348, 2009-10-22). No restated 2008 quarter exists in XBRL |
| OXY 2025-Q4 | 1,752 (`ytd_derived`) | 2025-Q1–Q3: 5,813 / 5,258 / 6,682 | Full year without OxyChem (21,593, 10-K 2026-02-18) minus nine months with it (19,841, 2025-11-10). Q1 and Q2 are already restated (2026 10-Qs: 6,911 → 5,813, 6,318 → 5,163); the restated nine months arrive with the Q3 2026 10-Q, ≈November 2026 |

**ABT's 5,632 is dropped by the accession vote.** A filing outvoted by the
majority value in two or more periods is distrusted. A restatement is outvoted
by construction: the FY2013 10-K restates 2011 and 2012, where the older
filings agree with each other, so its 2012-Q4 is discarded and the old-basis
figure wins.

**Relaxing the vote is not safe.** Recomputed for all 60 companies (revenue,
operating income, net income, operating cash flow, capex, cost of revenue,
D&A):

| Variant | Values changed | Companies | Nearer Alpha Vantage: today / variant |
|---|---|---|---|
| No vote | 290 | 36 | 194 / 35 |
| Reject only a filing a later one corrects | 243 | 29 | 183 / 21 |

Alpha Vantage tends to copy first-reported figures, so it is a biased judge of
restatements, but the variants also chain restatements: ABT's 2013 quarters
move to the basis of its 2015 divestiture (2013-Q1 5,378 → 4,847), which is a
new mix with 2014. A narrow, explicit fix is safer than a new general rule.

**OXY's 2025-Q3 (6,682) is also on the old basis** while Q1 and Q2 are restated.
It is a filed quarter, not a subtraction, and is restated by the same
November 10-Q; until then the OXY break (P3) flags 2025's year-over-year
changes.

### E3. EPS jumps at the forecast origin are real

2026-Q2 net income: GOOGL 112,193 (operating income 40,770), AMZN 62,647
(27,461), HON 5,682 (2,240). The filings explain each: GOOGL books a 99,031
gain on equity securities, AMZN 53,415 of other non-operating income, HON a
deconsolidation gain of 6,629. Operating income is ordinary in all three.
EPS is not a model feature; net margin (group M) spikes at the origin for
these three companies, and that spike is real.

### E4. Large acquisitions not registered as structural breaks

Revenue in the quarter the acquired company first appears, against the
quarter before:

| Company | Deal (closing) | Quarter | Before | After | Jump |
|---|---|---|---|---|---|
| PFE | Wyeth (2009-10-15) | 2009-Q4 | 11,621 | 15,797 | +36% |
| MRK | Schering-Plough (2009-11-03) | 2009-Q4 | 6,050 | 10,094 | +67% |
| CMCSA | NBCUniversal (2011-01-28) | 2011-Q1 | 9,721 | 12,128 | +25% |
| ECL | Nalco (2011-12-01) | 2012-Q1 | 1,845 | 2,811 | +52% |
| DUK | Progress Energy (2012-07-02) | 2012-Q3 | 3,577 | 6,722 | +88% |
| MDT | Covidien (2015-01-26) | 2015-Q1 | 4,318 | 7,304 | +69% |

They are breaks of the same kind as T's BellSouth merger (2007-Q1, +82%),
already registered. ECL's break is 2012-Q1, not 2011-Q4: Nalco's one month in
2011-Q4 moved revenue 6%, and a window starting there would leave 2012-Q4's
year-over-year change (against that one-month quarter) unflagged.

**ABT.** 2011 is on the old basis (≈10,000 a quarter, with AbbVie) and 2012-Q1
to Q3 on the restated one (≈5,300). Once 2012-Q4 is withheld (P2), the basis
changes at 2012-Q1, not 2013-Q1.

## Required behaviour

**P1. D&A from its parts.** Where no total D&A tag is filed for a period,
D&A is depreciation plus intangible amortization, when both are filed for
that period. A negative amortization counts as missing, so D&A is depreciation
alone. Where a total tag is filed, it wins as today. Alpha Vantage rows keep
I12, except that a negative income-statement D&A counts as missing, so the
cash-flow statement's D&A is used (IBM 2026-Q2: EBITDA 3,964).

**P2. Withheld quarters.** A quarter whose financials mix two reporting bases,
and for which the pipeline cannot select a single-basis figure, is withheld:
every financial column of that row is missing, including any Alpha Vantage
value, and NB00's missing-value ledger gives the reason `withheld_quarter`, not
`unexplained`. Each withheld quarter is declared in
`config/companies.yaml` under its company, with its reason, like
`has_reliable_opex`. Withheld now: ABT 2012-Q4, BMY 2008-Q4, OXY 2025-Q4. The
accession vote is unchanged. OXY's entry is deleted once its Q3 2026 10-Q
files the restated 2025 nine months; the next re-ingest then derives the
quarter under I1.

**P3. Structural breaks.** `config/structural_breaks.yaml` registers PFE
2009-12-31, MRK 2009-12-31, CMCSA 2011-03-31, ECL 2012-03-31, DUK 2012-09-30,
MDT 2015-03-31 and OXY 2025-03-31, and moves ABT from 2013-03-31 to
2012-03-31, where its basis changes once P2 withholds 2012-Q4. Each entry has its closing date and
revenue jump as a comment, as T has. The master plan's §3.4 list follows.

**P4. Decisions recorded.**
- **GOOGL 2012-Q4 is accepted** as a known defect of I1 (2012 history, far
  from the forecast origin); the thesis names it as a limitation.
- **EBITDA stays a forecast target**, reported next to operating income
  rather than as a separate result (Spearman 0.95 between them, on levels and
  on year-over-year changes).
- **The 2026-Q2 EPS jumps stay** (E3).

## Acceptance criteria

| # | Check |
|---|---|
| C1 | Tests: a filer with depreciation and amortization and no total gets their sum; one with a total keeps it; a negative amortization leaves depreciation alone; a negative Alpha Vantage income-statement D&A falls back to the cash-flow one |
| C2 | After re-ingest, ABT 2025 D&A sums to 3,116 across its four quarters, and its 2026-Q1 EBITDA is on the same basis as 2026-Q2 |
| C3 | Tests: a declared quarter's financial columns are missing even where Alpha Vantage has values; other quarters are untouched; the ledger reports `withheld_quarter`. After re-ingest, ABT 2012-Q4, BMY 2008-Q4 and OXY 2025-Q4 are missing with that reason |
| C4 | `structural_break` flags 4 rows per registered break (now 16 breaks, 64 rows) |
| C5 | `uv run poe check` green; NB00's ledger has no new `unexplained` rows |

## Out of scope

- GOOGL 2012-Q4 (P4).
- Changing Alpha Vantage's D&A or operating income (I12 stands).
- A general detector for restatements that left no trace in XBRL.

## Decisions taken by default — confirm or override

| # | Decision | Reason |
|---|---|---|
| D1 | Sum only depreciation and `AmortizationOfIntangibleAssets` | The two parts the scan found; depletion and other amortizations are already inside the total tags filers use |
| D2 | Withhold ABT 2012-Q4 rather than read its filed 5,632 | Reading a named filing for one quarter needs an override mechanism used once; with the quarter missing, ABT's 2012 is still on one basis |
| D3 | A withheld quarter blanks every financial column, not only revenue | The whole row comes from the same mixed filings (BMY, OXY: every flow is a subtraction; ABT: every flow is the old-basis Q4) |
| D4 | ABT's break moves to 2012-Q1 with P2, not after a restated Q4 | With 2012-Q4 missing, 2012-Q1 is still where the basis changes |

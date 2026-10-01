# Spec — Ingestion defects: COP revenue and GE opex

Two companies carry values the ingestion produced wrongly. NB01 excludes COP
entirely and blocks opex as a forecast target until this is fixed (EDA spec
Q6; EDA grilling Q16, Q25).

## Problem

NB01 found the defects by crashing, not by checking: COP's negative revenue made
log growth raise `NonPositiveValueError`. Both defects come from quarters the
pipeline **derives by subtraction** (full year minus three quarters, or
year-to-date minus year-to-date) across figures that are not on the same basis.

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

## Required behaviour

**I1. A subtracted quarter uses one reporting basis.** A quarter derived as
annual minus three quarters, or as a year-to-date difference, is produced only
when both sides come from the same filing basis. When the annual or year-to-date
figure was restated relative to the quarters it subtracts, the pipeline takes
the quarter from a source on the consistent basis, or leaves it missing. It
never emits the mixed-basis difference.

**I2. Derived values are checked before they enter the panel.** Where the
accounting identity is available (opex ≈ gross profit − operating income), a
derived quarter that misses it by more than 10% is rejected, and the rejection
is logged with ticker, quarter, column, value and provenance.

**I3. A change of reporting basis is a structural break.** COP's spin-off
restatement is recorded in the structural-breaks registry, so NB00's
`structural_break` flag and the feature group F see it.

**I4. Only affected companies are re-ingested**, through the existing reingest
path, and the fix is recorded in the reingest ledger.

**I5. Exclusions lift on acceptance.** When A1–A4 hold, NB01 includes COP again
and opex becomes a selectable target. LMT needs nothing: opex is forecast as
the revenue-scaled change, which is defined for LMT's small signed values
(EDA grilling Q26, 2026-09-30).

## Acceptance criteria

| # | Check |
|---|---|
| A1 | COP revenue has no non-positive quarter; Q4 2010 is missing or lies within the range of its adjacent reported quarters on the same basis |
| A2 | GE opex has no negative quarter, and agrees with gross profit − operating income within 10% in at least 90% of quarters (the reference rate) |
| A3 | No derived quarter in any company misses the identity by more than 10% without a logged rejection |
| A4 | LMT's opex is unchanged (the counter-example stays correct) |
| A5 | `uv run poe check` green; the re-ingest touches only COP and GE |

## Out of scope

- LMT opex (correct data; see the counter-example). The revenue-scaled change
  makes it usable as a target without exclusion (EDA grilling Q26).
- Gross profit negatives (26 rows; genuine, e.g. BA's 2019–2020 charges).
- Any other company, unless A3's check surfaces one; then it is added here
  with its own evidence before it is fixed.

## Decisions taken by default — confirm or override

| # | Decision | Reason |
|---|---|---|
| D1 | Prefer leaving a mixed-basis quarter missing over imputing it | Missing is handled everywhere downstream (R2 of the EDA spec: no splicing); a guessed value is not |
| D2 | The 10% identity tolerance comes from the measured 91% reference rate | A rule calibrated on healthy companies, not chosen to make GE pass |

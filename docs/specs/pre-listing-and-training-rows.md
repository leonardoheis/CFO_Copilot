# Spec — pre-listing quarters and training rows

Status: proposed. Implemented by
[`docs/plans/pre-listing-and-training-rows.md`](../plans/pre-listing-and-training-rows.md).
Follows [`sec-companyfacts-coverage.md`](sec-companyfacts-coverage.md).

## Problem

After the companyfacts re-ingestion the pooled panel (59 companies × 81
quarters, COP excluded) is 0.6% missing. Three sources of missingness are not
data that could be fetched, yet they dominate NB01's automated profiles and
would leak into model training:

| source | cells | why it is not fixable |
|---|---|---|
| TSLA before its listing (2006 Q2 – 2010 Q1) | 16 rows: price, EPS, market cap empty; revenue partly empty | Tesla was private until its first price on 2010-06-30 |
| `financials_filed` | 550 (11.5%) | the vendor fallback publishes no filing date; the column is provenance metadata, not a variable |
| warm-up rows of the feature datasets | 245 – 663 per lag/rolling column (h1) | a YoY lag *k* needs *k* + 4 quarters of history; the last quarter has no target yet |

TSLA is the only company with quarters before its first stock price.

## Required behaviour

**R1. NB00 flags pre-listing quarters.** A quarter is pre-listing when it
falls before the company's first quarter with a stock price. The flag is a
column of `panel_long` beside `covid` and `structural_break`. It is derived
from the data, not configured per ticker, so a future late-listing company is
flagged without editing anything.

**R2. Panels stay rectangular.** Every company keeps all 81 quarters;
pre-listing rows are flagged, not removed. The macro block stays identical
across companies, and NB00's row-count assertions are unchanged.

**R3. NB01's automated profiles exclude pre-listing rows and provenance
metadata** (`financials_filed`, `financials_provenance`, `period_end`,
`period_end_offset_days`).

**R4. Feature datasets have no pre-listing origin rows.** Lags are still
computed on the full history, so the first listed quarter keeps its lookback
into pre-listing financials.

**R5. Training uses only rows with a known target and every feature
present.** Selecting them is a tested library function; NB02 calls it.

## Acceptance criteria

1. `panel_long["pre_listing"].sum() == 16`, all TSLA, 2006-06-30 to 2010-03-31.
2. NB00 still writes 4,860 rows and an 81-row `macro_q`.
3. The NB01 panel and drift profiles show no `financials_filed` column and
   no row dated before TSLA's listing for TSLA.
4. Each feature dataset has `n_rows − 16` rows.
5. The training-row selection keeps a row only if `y` and every feature
   column are non-null, and drops nothing else.
6. NB00 and NB01 run end to end (run by the user).

## Out of scope

- Imputing warm-up features or extending history before 2006.
- Dropping `financials_filed` from the panel itself; it stays as provenance.
- Pre-listing rows in the target analyses of NB01 (sections 3–7).

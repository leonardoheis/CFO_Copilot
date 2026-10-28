# Spec — Dividend yield window includes the quarter-end day

Wave 2, item O2 (`docs/plans/code-smells-wave-2.md`).

## Problem

The trailing-twelve-month dividend yield at a quarter end is dividends paid in
the 365 days to that day, divided by the closing price on that day. Yahoo
stamps each trading day at midnight New York time. Ingestion converts the
stamps to naive UTC, which moves them to 04:00 or 05:00 on the same day, and
then keeps only stamps at or before the quarter end at midnight. Two things
fall out of the window:

- the closing price on the quarter-end day, so the yield divides by the
  previous trading day's close;
- a dividend whose date is the quarter-end day, which joins the window one year
  later instead.

When no price is left at all, the yield is written as **0.0**, which reads as
"pays no dividend" rather than as missing.

## Evidence

Measured 2026-10-27 from `data/processed/`, offline. Exact recomputation needs
Yahoo's dividend history, which is not stored; the figures marked *estimate*
use stored values only.

- **First quarter.** Every window starts on 2006-06-30, a Friday, so Yahoo's
  first close is stamped later than the window bound and no price is found.
  **49 of 60** panels have a first-quarter yield of 0 and a positive yield the
  next quarter, and all 49 have a stored first-quarter price. Estimated true
  first-quarter yield (next quarter's dividends over this quarter's price):
  median **2.0%**, range 0.07%–6.3%. *Estimate.*
- In `panel_long.parquet` all **60** rows dated 2006-06-30 hold 0; 59 of them
  have a price. The 10 priced rows outside the 49 are zero in the second
  quarter too, so they are right by coincidence: AAPL, ADBE, AMGN, AMZN, CMCSA,
  CSCO, GOOGL, NFLX, ORCL, SBUX were not paying then. The 60th row is TSLA,
  before its listing.
- **Quarter-end price.** **57 of 81** quarter ends were weekdays. For each of
  those, the yield divides by the previous trading day's close, while
  `stock_price_usd` uses the quarter-end close. That is a one-day mismatch,
  roughly the size of one daily return. *Cannot be measured offline.*
- **Missing price written as zero.** TSLA's **16** pre-listing quarters
  (2006-06 to 2010-03) have no price and a yield of 0.0 instead of missing.
- **Isolated zero.** UNH 2008-03-31 is 0 between two positive quarters, with a
  price present; it is consistent with an annual dividend dated on a quarter
  end, but this needs the dividend history to confirm.

## Required behaviour

1. A dividend or closing price dated on the quarter-end day, in exchange local
   time, belongs to that quarter.
2. The yield divides by the same closing price that `stock_price_usd` reports
   for that quarter.
3. A quarter with no price has a missing yield, not 0.0. A quarter with a price
   and no dividends in the window has 0.0.
4. The dividend window stays 365 days ending on the quarter-end day, inclusive.

## Acceptance criteria

- A test with New York–stamped dividends and prices: a dividend and a close on
  the quarter-end day both count for that quarter.
- A test: price and yield for one quarter use the same close.
- A test: a quarter before the first price has a missing yield; a payer with no
  dividend in the window has 0.0.
- After re-ingest, no paying company has a zero first-quarter yield, and TSLA's
  pre-listing yields are missing.
- The re-ingested yields are reported against the stored ones: rows changed,
  median and largest change.

## Reruns

Re-ingest all 60 companies, then NB00 onward. `dividend_yield` is a model input
(a ratio column, and one of the pre-listing columns), so NB01's tables and the
exported feature datasets change.

## Out of scope

- Split- or special-dividend adjustment of the dividend history.
- Changing the 365-day window to four payments.

# Plan — Wave 2 output-sensitive fixes (O1–O4)

Implements the four Phase 3 specs of `docs/plans/code-smells-wave-2.md`. Order
is by blast radius, smallest first. Code and tests only: the re-ingest and the
notebook reruns are run by hand afterwards, because they call live APIs and
rewrite `data/processed/` and `data/features/`.

## O4 — Ljung-Box on the d-th difference

Spec: `docs/specs/ljung-box-differencing.md`.

1. `services/diagnostics/series.py`: difference d times at lag 1 before the
   test, as the differencing-order search does.
2. Test in `tests/services/diagnostics/test_series.py`: for a d = 2 series the
   reported p-value equals Ljung-Box on the twice-differenced series and
   differs from the lag-2 difference.

Rerun: NB01.

Status: done (2026-10-27). NB01 rerun pending.

## O1 — EPS repair on every panel

Spec: `docs/specs/eps-split-restatement-repair.md`.

1. `data/pipeline.py`: consult the fallback when SEC left gaps **or** a quarter
   has positive net income and non-positive EPS; apply the EPS repair in both
   cases; warn for an inconsistent quarter the vendor cannot repair.
2. Tests in `tests/data/test_pipeline.py`:
   - gap-free SEC with one inconsistent quarter takes the vendor's EPS there
     and nothing else changes;
   - a gap-free, consistent panel makes no fallback call;
   - an inconsistent quarter without a positive vendor EPS keeps SEC's value
     and warns.

Rerun: none.

Status: done (2026-10-27).

## O2 — Dividend yield window

Spec: `docs/specs/dividend-yield-window.md`.

1. `data/sources/yfinance_source/fetching.py`: compare on calendar days in the
   exchange's own time zone (drop the zone without converting to UTC), so a
   quarter-end stamp falls inside its quarter.
2. Take the price from the same quarter-end close that `stock_price_usd` uses.
3. A quarter with no price gets a missing yield; a priced quarter with no
   dividends gets 0.0.
4. Tests in `tests/data/sources/test_yfinance_source.py` with New York–stamped
   fakes: quarter-end dividend and close count; price matches
   `stock_price_usd`; missing price gives a missing yield.
5. Check the missing-value ledger treats the new missing pre-listing yields as
   pre-listing, not as unexplained.

Rerun: re-ingest all companies, then NB00 onward.

Status: done (2026-10-27). The yield divides by the quarter price that
`stock_price_usd` reports, and dividends are compared on their calendar day.
The shared date normalisation was left alone: it also moves split dates, which
feed the SEC per-share adjustment (see Follow-up). Re-ingest pending.

## O3 — FRED naming (decision: mixed)

Spec: `docs/specs/fred-series-naming.md`.

1. `data/sources/fred/source.py`: `gdp_yoy` reads `A191RO1Q156NBEA`;
   `dxy` is renamed `usd_broad_index` and keeps `DTWEXBGS`.
2. `data/schema.py`, both column snapshots, `tests/data/sources/test_fred.py`
   (and its cassette, if it records the series ID), feature-service tests.
3. NB01 text and code references to `dxy`; master plan macro list.

Rerun: re-ingest (macro), then NB00 onward; done together with O2's re-ingest.

Status: done (2026-10-27). NB01's sources never name either column (only its
stored outputs do), so no notebook edit. The two cassettes holding the GDP
request were re-recorded for `A191RO1Q156NBEA` only; FRED returned 1.4 and
−7.4 for 2020 Q1–Q2, matching the spec's estimate. Re-ingest pending.

## Verification

- `uv run poe check` after each item.
- After the manual re-ingest: O1's panels unchanged; O2's yields reported
  against the stored ones (rows changed, median and largest change); O3's
  2020 Q2 GDP near −7.4.

## Follow-up (not in these specs)

Yahoo's split dates go through the same UTC conversion, so a split dated on a
SEC period end lands at 04:00 that day and is treated as not yet effective,
against the rule that a split on the date itself already applies. Whether any
stored company is affected needs the split history; a spec would come first.

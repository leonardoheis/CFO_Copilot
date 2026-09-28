# Shares outstanding and market cap defects

Two independent defects corrupt `shares_outstanding`, and through it
`market_cap_usd_m`, across the whole panel. Found while resolving E1
([`final-row-provenance.md`](final-row-provenance.md)), measured 2026-09-26
against `data/processed/*.parquet` and live SEC EDGAR.

**No company of the 60 is free of both.**

## Defect A — instant share facts are carried forward indefinitely

`instant_series_from_facts` selects, for each quarter, the latest instant fact
with `end <= quarter_date` (`src/app/data/xbrl.py:73-91`). When a filer stops
reporting the instant tag, the last known value is repeated for every
subsequent quarter with no marker and no decay.

The repair path never runs. `_fetch_shares_chain` only consults
`_fetch_diluted_shares_fallback` when the primary series still has a NaN
(`src/app/data/sources/sec_edgar/source.py:203-208`) — but a carried-forward
series is fully populated, so the guard is satisfied by the very staleness it
should catch.

**Measured:** a share count identical to the previous quarter occurs in
**595 of 4,841** company-quarters (**12.3%**), across **51 of 60** companies.

Worst cases, by consecutive quarters frozen at the panel's final value:

| Ticker | Frozen since | Trailing quarters frozen | Panel shares (m) |
|---|---|---|---|
| BA | 2008-12-31 | 71 | 1,012.3 |
| WMT | 2012-03-31 | 58 | 10,254.0 |
| DIS | 2023-12-31 | 11 | 1,900.0 |
| DUK | 2025-06-30 | 5 | 778.0 |
| APD | 2025-09-30 | 4 | 222.6 |
| SBUX | 2025-09-30 | 4 | 1,136.9 |

Split adjustment is applied to the stale value, which disguises it: WMT's
frozen figure is the ~3,418 m shares of 2012 multiplied by the 3:1 split of
February 2024, giving a plausible-looking 10,254 m.

## Defect B — weighted-average share counts are differenced as flows

`_fetch_diluted_shares_fallback` passes
`WeightedAverageNumberOfDilutedSharesOutstanding` through
`quarterly_facts_from_facts` (`src/app/data/sources/sec_edgar/source.py:212-231`),
which is built for **cumulative flows** — it recovers a quarter by subtracting
the prior year-to-date figure, or by subtracting three quarters from an annual
total.

A weighted-average share count is an average, not a flow. Subtracting one
period's average from another's is meaningless, and on a fiscal Q4 it returns
approximately zero or a large negative number.

**Confirmed against live facts**, reproducing the stored panel values exactly:

| Ticker | Quarter | Computation | Result | Panel value |
|---|---|---|---|---|
| PG | 2026-06-30 | 2,422.5 m (FY, 364 d) − 2,425.8 m (9 mo, 273 d) | −3.3 m | −3.3 m |
| NKE | 2026-06-30 | 1,481.0 m (FY, 364 d) − 1,480.4 m (9 mo, 272 d) | 0.6 m | 0.6 m |

For PG the annual-minus-three-quarters branch would have given −4,854.8 m; the
YTD branch fires first only because it is tried earlier.

**Measured:** **357** company-quarters hold a non-positive or absurdly small
share count (under 1% of that company's own median), across **31 of 60**
companies. Worst: COP 41 quarters, TXN 19, MCD / GIS / JNJ / PG 18 each.

Because these land on fiscal Q4, they recur once a year for an affected
company, for as long as the fallback is in use.

## Consequence for `market_cap_usd_m`

`market_cap_usd_m = stock_price_usd * shares_outstanding / 1e6`
(`src/app/data/pipeline.py:101-104`) inherits both defects directly.

Comparing each panel's implied 2026-Q2 share count against the most recently
reported diluted share count (56 of 60 companies had a usable reference):

| Ticker | Panel (m) | Reported (m) | Error | Cause |
|---|---|---|---|---|
| GIS | −1.5 | 537.9 | −100.3% | B |
| PG | −3.3 | 2,422.5 | −100.1% | B |
| NKE | 0.6 | 1,481.0 | −100.0% | B |
| WMT | 10,254.0 | 7,989.0 | +28.4% | A |
| BA | 1,012.3 | 789.2 | +28.3% | A |
| TSLA | 3,949.0 | 3,538.0 | +11.6% | A |
| DIS | 1,900.0 | 1,769.0 | +7.4% | A |

**46 of 56 are within ±2%**, which is the expected gap between a weighted
average and a period-end count — those are fine. **6 are off by more than 10%,
5 by more than 25%**, and three have no economic meaning at all.

This is the final row only. Defect B recurs annually and Defect A grows
monotonically, so earlier rows are worse, not better.

## Requirements

1. A carried-forward share count must be **impossible to mistake for a
   reported one**. Either the panel records the instant fact's own date, or a
   value is not carried past a stated maximum age.
2. The diluted-share fallback must **not difference weighted averages**. A
   fiscal Q4 average must come from a reported figure or a documented
   weighting, never a subtraction.
3. A share count that is non-positive, or implausible against the company's own
   history, must **fail loudly** rather than propagate into `market_cap_usd_m`.
4. `market_cap_usd_m` must be NaN where the share count is not trustworthy.
   A wrong number is worse than a missing one for a model feature.
5. Whatever fix lands must be **re-measurable**: the three counts in this
   document (repeat quarters, corrupt quarters, final-row error) are the
   regression test.

## Acceptance criteria

- Repeat-value quarters attributable to carry-forward: **0**, or every one
  carries its true as-of date.
- Non-positive or sub-1%-of-median share counts: **0**.
- Final-row implied share count within **±3%** of the reported diluted count
  for every company with a reference, or NaN.
- A test covers a weighted-average fact reaching the Q4 path and asserts it is
  not differenced.

## Out of scope

- How to fix either defect. That is a plan, not a spec.
- The `eps`-based `implied_shares_from_earnings` path, which was not examined.
- The four companies with no diluted-share reference (XOM among them); their
  final-row error is unmeasured.

## Reproducing

Scratch probes, not committed:

- panel-only audit — implied shares from `market_cap_usd_m / stock_price_usd`,
  counting repeats, non-positives and sub-1%-of-median values
- mechanism check — `_find_ytd_fact` and `_find_annual_minus_three_quarters`
  re-run on live `WeightedAverageNumberOfDilutedSharesOutstanding` facts
- magnitude — newest reported diluted count with `end >= 2025-09-01` per
  company, against the panel's final row

These belong in a `data/` audit command if the numbers are to be tracked.

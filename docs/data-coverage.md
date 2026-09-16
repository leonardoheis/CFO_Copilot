# Data coverage by company

What each source actually yields, per company, measured from the written
panels rather than from what the APIs promise.

Covers the 11 companies with an ingested panel. Add a row when you ingest a
new ticker — the registry holds 50, so 39 are registered but not yet scraped.

Last measured: 2026-09-16. Panels span 2006-06-30 → 2026-06-30, 81 quarters.

## How to read this

Each panel column is filled by one of three sources:

| Source | Columns | Notes |
|---|---|---|
| **SEC EDGAR** (XBRL) | revenue, gross profit, opex, operating income, EBITDA, net income, FCF, EPS, shares | Primary. Facts are sparse before 2008-04-01. |
| **Alpha Vantage** | the same financial columns | Fallback only — called where SEC left a gap. 4 requests per ticker, cached permanently under `data/raw/alpha_vantage/<TICKER>/`. |
| **Yahoo Finance** | price, dividend yield, market cap, P/E | Starts at the IPO, not at the panel start. |
| **FRED** | GDP, fed funds, unemployment, CPI, DXY, VIX, WTI | Identical for every company; **100% on all 7 columns, every ticker**. Never the reason a panel is thin. |

## Summary

| Ticker | Company | FY end | Financials | Market | Quarters with revenue |
|---|---|---|---|---|---|
| AAPL | Apple | **Sep** | 100% | 100% | 81 / 81 |
| AMZN | Amazon | Dec | 100% | 98% | 81 / 81 |
| CSCO | Cisco | **Jul** | 100% | 100% | 81 / 81 |
| GOOGL | Alphabet | Dec | 100% | 100% | 81 / 81 |
| IBM | IBM | Dec | 100% | 99% | 81 / 81, two wrong |
| INTC | Intel | Dec | 100% | 96% | 81 / 81 |
| MSFT | Microsoft | **Jun** | 100% | 99% | 81 / 81 |
| ORCL | Oracle | **May** | 99% | 99% | 80 / 81 |
| PEP | PepsiCo | Dec | 100% | 100% | 81 / 81 |
| PG | Procter & Gamble | **Jun** | 100% | 100% | 81 / 81 |
| TSLA | Tesla | Dec | 91% | 77% | 75 / 81 |

Financials and Market are the mean fill rate across that group's columns.
IBM's two wrong quarters are described under Known defect below; they are
populated, not missing, so no percentage reflects them.

## Every gap, explained

There is no unexplained missing data in these 11 panels.

**`pe_ratio` is the only gap in eight of them.** Every null is a quarter where
EPS ≤ 0, and P/E is undefined for a loss. Verified: INTC 14 nulls / 14 loss
quarters, AMZN 8 / 8, TSLA 28 / 28. This is correct behaviour, not a
collection failure — do not "fix" it by filling a value.

**TSLA is genuinely thin at the start, twice over.**
- No price before **2010-06-30**: it IPO'd that June. 16 quarters have no
  price, market cap or P/E, and nothing can recover them.
- No revenue for 6 quarters in 2006–2008: it was private and filed nothing.
  First financials appear 2007-03-31.

**ORCL misses exactly one quarter**, 2006-06-30, which predates SEC's XBRL
era (facts are typically empty before 2008-04-01) and falls outside Alpha
Vantage's history for this ticker.

## Fiscal years — the trap worth knowing

**Five of eleven do not end in December**: AAPL (Sep), CSCO (Jul), MSFT (Jun),
PG (Jun), ORCL (May).

The panel is on calendar quarters, so an offset filer's quarters are mapped,
not matched. That mapping is where Oracle broke: its 2009–2011 revenue was
being read from a superseded tag and written as `0`, then as a segment
subtotal roughly 5× too low. Both are fixed (see
`docs/specs/sec-tag-precedence.md`), but an offset fiscal year remains the
first thing to check when a new panel looks wrong.

Verify a new offset filer against its own 10-Q before trusting the series.

## Alpha Vantage quota

The free tier allows **25 requests/day**; each ticker costs **4**. All 11
above are cached, so re-ingesting them is free. A new ticker costs 4 requests
on its first ingest and nothing thereafter.

At 4 per ticker, the 39 registered-but-unscraped companies need 156
requests — about 7 days on the free tier. Check the tier before batching.

## Adding a company to this report

```bash
uv run poe add-company --ticker XYZ --sector Technology
# add the display name to the pinned set in tests/data/test_companies.py
uv run python -m app.data --ticker XYZ
```

Then add a summary row, and check three things before trusting the panel:

1. **Revenue below opex with positive net income** — arithmetically
   impossible, and the signature of a derivation or tag-precedence bug.
2. **Any revenue of exactly 0** — a superseded tag reporting a placeholder.
   Zero is never a real quarterly revenue for an operating company.
3. **A non-December fiscal year** — check the first and last quarters against
   a filing.

All 11 panels pass check 2. **IBM fails check 1 in two quarters** — see below.

## Known defect: IBM Q4 2019 and Q4 2020

| quarter | revenue in panel | reported | gross profit |
|---|---|---|---|
| 2019-12-31 | **2,344** | ~21,800 | 6,145 |
| 2020-12-31 | **1,926** | ~20,400 | 5,814 |

Gross profit exceeds revenue, which is impossible, so these are derived
values, not reported ones.

**Cause.** SEC holds three different `Revenues` facts for the identical period
`2019-01-01 → 2019-12-31`:

| value | filed | what it is |
|---|---|---|
| 77,147 | 2020-02-25 | the FY2019 figure as originally reported |
| 77,000 | 2020-04-28 | the same, rounded, in a later 10-Q |
| **57,714** | **2022-02-22** | restated **continuing operations** after the Kyndryl spin-off |

Deduplication keeps the latest filing, so 57,714 wins. Q4 is then derived as
annual minus nine months — but the 55,370 nine-month comparator was never
restated. Subtracting a post-spin-off annual from a pre-spin-off comparator
gives 57,714 − 55,370 = 2,344.

This is a **different defect** from the tag-precedence one: the tag is right
and the arithmetic is right, but the two operands describe different
businesses. Any filer with a spin-off, divestiture or discontinued operation
can hit it. Latest-filing-wins is the correct rule for a *correction* and the
wrong one for a *restatement*, and nothing currently distinguishes them.

Not yet fixed. Treat IBM's Q4 2019 and Q4 2020 as unusable until it is.

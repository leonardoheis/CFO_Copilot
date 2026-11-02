# Final-row provenance (E1)

Resolves the blocking task **E1** in `docs/CFO_COPILOT_MASTER_PLAN.md` §0.3:
*"is the 2026-Q2 row reported or projected?"*, and states what must be true of
the final row before NB00 exits.

Window under test: 2006-Q2 → 2026-Q2, 81 quarters, 60 companies, as collected in
`data/processed/<TICKER>_panel.parquet`. Evidence gathered 2026-09-26 against
live SEC EDGAR.

## Verdict

**The 2026-Q2 row is reported, not projected.** No arm of the ingestion pipeline
produces forecasts, and the panel's last row is filled from filings that already
existed when it was collected.

This **independently confirms** the resolution recorded on 2026-09-23 in
[`nb00-ingest-and-consolidate.md`](nb00-ingest-and-consolidate.md), which
reached the same verdict from the panel alone. What the panel could not show is
*how* each value got there — that is what the rest of this document covers, and
it is where the real problems are. In particular, Finding 2 explains the COST
NaNs that spec's acceptance criterion A7 leaves as "unexplained".

Two independent lines of evidence:

1. **A filing covers the slot.** For **59 of 60** companies a 10-Q or 10-K whose
   period end maps to the 2026-Q2 slot exists in SEC EDGAR's submissions index,
   filed between **2026-06-15** (ADBE) and **2026-09-10** (M). The exception is
   **COST** — see *Finding 2*.
2. **The pipeline cannot extrapolate.** `build_panel_skeleton` lays down a fixed
   quarter grid and every source is joined with `how="left"`
   (`src/app/data/pipeline.py:81-99`), so a quarter no source reports stays NaN.
   `align_series_to_quarters` resamples and reindexes with no forward fill
   (`src/app/data/dates.py:43-60`). There is no projection step to remove.

Provenance of the 2026-Q2 revenue value, classified by re-running the branches
of `quarterly_facts_from_facts` against live EDGAR facts:

| Provenance | Companies |
|---|---|
| Native quarterly fact | 47 |
| Derived from YTD minus prior YTD | 5 (CSCO, MSFT, NKE, ORCL, PG) |
| Not resolvable from the SEC tag chains | 8 (ABT, BBY, COST, DUK, F, KO, NEE, SO) |

The YTD-derived five are arithmetic on two reported figures, not estimates.

**So E1 does not block NB00.** The risk it was guarding against is real, but it
is misalignment and staleness, not projection. The three findings below are what
must actually be handled.

## Finding 1 — the final row is fiscal, not calendar

Eight companies' 2026-Q2 row holds a fiscal quarter that ended **one to two
months after** 2026-06-30, because `nearest_quarter_end` snaps within a 46-day
tolerance (`src/app/data/dates.py:16-33`):

| Ticker | Period end in the 2026-Q2 row | Offset from 2026-06-30 |
|---|---|---|
| CSCO | 2026-07-25 | +25 d |
| MDT | 2026-07-31 | +31 d |
| WMT | 2026-07-31 | +31 d |
| M | 2026-08-01 | +32 d |
| BBY | 2026-08-01 | +32 d |
| HD | 2026-08-02 | +33 d |
| DE | 2026-08-02 | +33 d |
| COST | 2026-05-10 | −51 d |

The macro block merged onto that same row (`gdp_yoy`, `fed_funds`, `cpi_yoy`, …)
is calendar-quarter data for Apr–Jun 2026. For these eight the financial and
macro halves of the row describe **different periods**. This is the
"fiscal-calendar misalignment" risk the master plan rates High and assigns to
the NB00 audit; it affects every row of those companies, not only the last.

## Finding 2 — COST loses one fiscal quarter per year to a snap collision

COST's fiscal quarters end mid-February, mid-May, late August and early
September. Two consecutive quarter ends fall within tolerance of the *same*
calendar quarter end:

- `nearest_quarter_end(2026-02-15)` → 2026-03-31 (44 days)
- `nearest_quarter_end(2026-05-10)` → 2026-03-31 (40 days)

Both map to 2026-Q1, and nothing maps to 2026-Q2. Running the SEC path alone
returns **NaN at both 2025-06-30 and 2026-06-30** for COST — the collision
discards one quarter every fiscal year.

The panel is not NaN there because the Alpha Vantage fallback filled it: the
panel's 2026-06-30 revenue of **70,527 USD m** is COST's **2026-02-16 → 2026-05-10**
quarter, which SEC reports under
`RevenueFromContractWithCustomerExcludingAssessedTax` filed 2026-06-03. Alpha
Vantage normalizes `fiscalDateEnding` to a month end, so the same quarter snaps
to 2026-06-30 there and to 2026-03-31 on the SEC path.

Consequence: **COST's series is internally inconsistent about which slot a
fiscal quarter belongs in, depending on which source supplied the row.** Its
2026-Q2 row is still reported data — just the wrong quarter for the slot.

COST is also the one company with a missing financial field in the final row
(7 of 8 present, against 8 of 8 for the other 59).

## Finding 3 — ABT's financials do not come from SEC at all

`SecEdgarSource.fetch_financials_panel("ABT", …)` returns **NaN for every
quarter**. ABT's `SalesRevenueNet` facts stop before 2026, and none of the other
three tags in `TAG_CHAINS["revenue"]` return facts for that CIK. The entire ABT
financial series in the panel is Alpha Vantage data.

The remaining companies in the 8-company "not resolvable" row of the table above
(BBY, DUK, F, KO, NEE, SO) have the same shape of problem and were not
individually traced.

## Adjacent defect found while probing (not part of E1)

`instant_series_from_facts` picks the latest instant fact with `end <= quarter_date`
(`src/app/data/xbrl.py:73-91`), which carries a stale share count forward
indefinitely. For **WMT** the newest `CommonStockSharesOutstanding` fact the tag
chain retrieves ends **2012-01-31**, so shares are frozen at 10,254 M for the
57 quarters from 2012-06-30 to 2026-06-30. Because the carried-forward series is
never NaN, the `_fetch_diluted_shares_fallback` guard in `_fetch_shares_chain`
(`src/app/data/sources/sec_edgar/source.py:203-208`) never fires.

`market_cap_usd_m = stock_price_usd * shares_outstanding / 1e6` inherits this:
WMT's 2026-Q2 market cap reads **1.161e6 USD m** against roughly 0.9e6 actual.

Now measured across all 60, together with a second share-count defect found in
the same probe. **No company is free of both.** See
[`shares-outstanding-defects.md`](shares-outstanding-defects.md).

## Requirements

1. **Satisfied.** The panel carries, per row, the **actual period end** of the
   financial figures in it (`period_end`) and its signed distance from the
   calendar slot (`period_end_offset_days`), so a fiscal row is distinguishable
   from a calendar one without re-querying EDGAR.
2. **Satisfied.** The panel carries the **provenance** of each row's financials
   (`financials_provenance`: `native`, `ytd_derived`, `annual_minus_3q` or
   `alpha_vantage`) and the filing date behind them (`financials_filed`).

Both are anchored on **revenue** — the figure whose filing decides which period
the row describes — not recorded per field.

Verified against live EDGAR: the columns reproduce, from the panel alone, the
offsets this document previously needed a probe to find (WMT +31, HD +33,
CSCO +25, AAPL −3) and the derivation rule per row (MSFT, PG and CSCO all
`ytd_derived`).
3. A fiscal calendar whose quarter ends collide onto one calendar quarter must
   be **detected and reported**, not silently resolved by dropping a quarter.
   COST must not be the only such company by accident.
4. Macro variables must be joined on the **period actually covered** by the
   financial row, or the mismatch must be recorded as a stated limitation with
   its size in days.
5. `is_projected` needs no row-level data check to populate it. This evidence
   independently confirms the resolution already recorded in
   [`nb00-ingest-and-consolidate.md`](nb00-ingest-and-consolidate.md) R4 — the
   flag is driven by `Settings.LAST_REPORTED_QUARTER` and is false for every
   row today. The train/test exclusion E1 was worried about should be driven by
   requirements 1–3 instead, which describe defects `is_projected` cannot see.

## Acceptance criteria

- Every `(ticker, 2026-Q2)` row is traceable to a filing accession number and
  filing date, or explicitly marked as vendor-sourced.
- Re-running the SEC path for all 60 companies reports zero silent snap
  collisions; any collision raises or is logged with both period ends.
- COST's 81 rows contain 81 distinct fiscal quarters, or the gap is recorded.
- The eight companies in Finding 1 are flagged in the panel, not just in this
  document.

## Out of scope

- Fixing the snap collision or the tag chains — this spec states what must be
  true, not how. That belongs in a plan.
- The stale-shares defect, which needs its own measurement across all 60
  companies before anything is designed.
- Macro vintages (D13 / O4) — a separate, already-documented limitation.

## Reproducing the evidence

Probes used, against live EDGAR with `SEC_USER_AGENT` from `.env`:

- filing existence per company — SEC submissions index, form/period/filed
- value provenance — re-ran `_find_native_fact`, `_find_ytd_fact` and
  `_find_annual_minus_three_quarters` per company on fetched facts
- SEC-only panel vs stored panel — `fetch_financials_panel` diffed against the
  parquet for COST and ABT
- instant-fact staleness — newest `end <= 2026-06-30` per shares tag

These were scratch scripts, not committed. They should be rebuilt as a
`data/` audit command if the checks are to run repeatedly.

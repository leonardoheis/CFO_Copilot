# Spec — HON: 2026 separation and 1-for-2 reverse split

Found by the post-O2/O3 comparison (`docs/plans/output-sensitive-fixes.md`,
"Verification record (2026-10-28)"): Honeywell's Q3 2026 10-Q, filed
2026-10-22, changed HON's 2025-Q3 row, and its outlier-register entries and
the Industrials λ in NB01b moved with it.

## Problem

In 2026-Q2 Honeywell did two things at once: it separated a business
(deconsolidation gain 6,629, already recorded in E3 of
`nb01-pending-items.md`) and it did a **1-for-2 reverse split**. Every filing
since then re-reports earlier quarters on the new basis: per-share figures
doubled, share counts halved, and, from the Q3 10-Q on, flows restated to
continuing operations.

The panel takes each quarter from the latest filing that reports it, so the
rows a post-event filing re-reported are on the new basis and their
neighbours are not:

- **Flows.** 2025-Q3 holds the continuing-operations revenue (4,929) between
  whole-company quarters (≈9,300). Revenue, operating income and EBITDA are
  forecast targets, so this reaches NB02.
- **Per share.** 2025-Q2, 2025-Q3 and 2026-Q2 hold EPS and share counts on the
  post-split basis, the other quarters on the pre-split one. EPS, market cap and
  P/E are not model features (no `data/features/` file has them), so this
  stays inside the panel.

## Evidence

Measured 2026-10-28 from SEC companyfacts (CIK 0000773840), Yahoo Finance and
`data/processed/HON_panel.parquet`.

**The reverse split is in the filings.** `StockholdersEquityNoteStockSplitConversionRatio1`
= **0.5**, for 2026-06-29 and 2026-06-30. Weighted diluted shares, same
quarter, as filed before and after:

| Quarter | Filed before (date) | Filed after (date) |
|---|---|---|
| 2025-Q2 | 640.9 m (2025-07-24) | 320.5 m (2026-07-23) |
| 2025-Q3 | 638.8 m (2025-10-23) | 319.4 m (2026-10-22) |
| 2025-Q2 diluted EPS | 2.45 (10-K, 2026-02-17) | 4.90 (2026-07-23) |
| 2025-Q3 diluted EPS | 2.86 (10-K, 2026-02-17) | 5.71 (2026-10-22) |

Net income for both quarters is identical in every filing (1,570 and 1,825).

**Yahoo does not list the split.** Its split series for HON has 1.061 on
2025-10-30 and **0.9535** on 2026-06-29, and no 0.5. The close does not
double across 2026-06-29 (227.80 that day; 215.92 on 06-10, 242.52 on 06-25),
and the dividend per share falls from 1.248 to 0.70. Yahoo encodes a spin-off
as a fractional split; 0.9535 is consistent with the reverse split (0.5) and
a spin-off factor of 1.907 netted into one number. That reading is an
inference: no source states the split of the 0.9535.

**How the panel scales per-share values today.** Each filing's per-share
values and share counts are moved onto Yahoo's adjusted basis by the Yahoo
factors dated after the filing; prices come from Yahoo on the same basis, so
market cap and P/E agree across Yahoo's events. For HON, a filing made after
2026-06-29 gets no factor, although its comparatives for earlier quarters are
on SEC's basis (0.5), not Yahoo's (0.9535). The panel today:

| Quarter | EPS | Shares (market cap / price) | Market cap | Revenue | Filed |
|---|---|---|---|---|---|
| 2025-Q1 | 2.33 | 612.8 m | 128,267 | 8,925 | 2026-04-23 |
| 2025-Q2 | **4.90** | **317.5 m** | **73,087** | 9,322 | 2026-07-23 |
| 2025-Q3 | **5.71** | **317.5 m** | **66,063** | **4,929** | 2026-10-22 |
| 2025-Q4 | −0.19 | 605.8 m | 123,941 | 9,758 | 2026-02-17 |
| 2026-Q1 | 1.35 | 604.2 m | 143,235 | 9,143 | 2026-04-23 |
| 2026-Q2 | 17.83 | 316.9 m | 70,954 | 9,719 | 2026-07-23 |

Scaling the two restated comparatives by SEC's ratio over Yahoo's factor
(0.5 / 0.9535) gives EPS **2.57** and **2.99** and shares **605.5 m**,
matching what the pre-split filings give on the panel's basis (2.45 / 0.9535
= 2.57; 2.86 / 0.9535 = 3.00) and the neighbouring share counts. 2026-Q2 is
already right: it ends after the split, where Yahoo's basis is the actual one.

**Only HON is affected.** Of the 60 companies, 19 have a fractional Yahoo
split since 2006. For the 16 of them that could carry a split, SEC's split
ratio agrees with Yahoo wherever SEC tags one (GE 0.125 in 2021, GOOGL 2 and
20, CMCSA 2; DUK's 0.3333 reverse split matches, and its 0.8708 is the
Progress merger exchange ratio). ABT, APD, COP, DIS, IBM, KMB, MRK, OXY, PFE,
T and VZ tag no split: their Yahoo factors are spin-offs only. HON is the one
company whose filed ratio (0.5) disagrees with Yahoo (0.9535).

**The flows are on three bases.** 2025-Q3 revenue as filed: 10,408 (10-Q,
2025-10-23), 9,437 (10-K, 2026-02-17, after the October 2025 spin-off), 4,929
(10-Q, 2026-10-22, after the 2026 separation). The panel's 2024-Q4 to 2026-Q2
are on the second basis, 2024-Q3 and earlier on the first, 2025-Q3 on the
third. 2025-Q3 net income (1,825) still includes discontinued operations,
so the row's net margin is 37% against 13–17% in the other 2025 quarters.

**Counter-example — the restated quarter is not a defect of the filing.**
4,929 is Honeywell's correct continuing-operations revenue, and 2026-Q3 is
4,994 on the same basis. Once the window covers 2026-Q3, the low level is the
new normal; what is wrong today is one quarter on that basis among quarters on
another.

## Required behaviour

**H1. HON 2025-Q3 is withheld.** Every financial column of the row is missing
and NB00's ledger gives `withheld_quarter`, exactly as for ABT 2012-Q4 and
OXY 2025-Q4 (P2 of `nb01-pending-items.md`). The entry is reviewed when the
window moves past 2026-Q2: by then the 10-K for 2026 restates the other 2025
quarters on the same basis, and the withholding is replaced by a structural
break (H3).

**H2. A filer's own split ratio governs its restated comparatives.** Where a
company tags a split ratio that differs from Yahoo's factor for the same
event, per-share values and share counts that a post-event filing reports for
pre-event quarters are put on the panel's basis using the filer's ratio, not
left unscaled. Where the two agree, or the filer tags no ratio, nothing
changes.

A filer ratio belongs to a Yahoo event when it is dated within a week of it.
If any ratio near the event agrees with Yahoo's factor (within 1%), the event
is taken as agreeing. **Counter-example:** DUK tags 0.8708 (its Progress
merger exchange ratio) on 2012-06-30 and 0.333 on 2012-07-02, three and one
days before Yahoo's 0.3333 reverse split; reading the 0.8708 alone would
rescale correct DUK data. Ratios near one event that disagree with each other
change nothing and are logged. A filer ratio with no Yahoo event nearby
(GOOGL's 20 on 2022-02-01, the announcement of the July split) changes
nothing.

**H3. Out of this window.** When the window includes 2026-Q3, the 2026
separation is registered as a structural break in
`config/structural_breaks.yaml`, at the first quarter the panel holds on the
continuing basis.

## Acceptance criteria

| # | Check |
|---|---|
| A1 | After re-ingesting HON, 2025-Q3 has no financial values and the ledger reports `withheld_quarter`; every other HON quarter's flows are unchanged |
| A2 | HON 2025-Q2 EPS is 2.57 ± 0.01 and its shares are 600–615 m; 2025-Q3 (if not withheld) 2.99 ± 0.01; 2026-Q2 stays 17.83 and 316.9 m |
| A3 | HON's 2025-Q2 market cap, and 2025-Q3's where present, are within 15% of 2025-Q1's (128,267) |
| A4 | Re-ingesting the other 59 companies changes nothing (no other filer's ratio disagrees with Yahoo) |
| A5 | Tests: a filing after a split whose ratio differs from the market factor rescales its comparatives; an agreeing ratio, or none, leaves them alone |
| A6 | After NB00 and NB01 rerun, the HON outlier-register entries that appeared with the 2026-10-22 filing are gone, and NB01b's Industrials λ is recomputed |
| A7 | `uv run poe check` green |

## Out of scope

- **Spin-off factors applied as splits** (the 19 companies). Per-share values
  and share counts share Yahoo's basis with prices, so market cap and P/E are
  right; EPS before a spin-off is "value-adjusted" rather than per actual
  share (ABT before 2013 is divided by 2.08). No model feature uses EPS.
  Moving to an actual-share basis would need unadjusted prices too and is its
  own spec.
- **The basis staircase from latest-filed flows** in general (HON's three
  bases, COP, ABT, OXY, PFE). Each known case has a break or a withheld
  quarter; a general rule is not proposed here.
- E3's conclusion stands: HON's 2026-Q2 net income jump is a real
  deconsolidation gain. Its EPS jump against 2026-Q1 (1.35 → 17.83) is about
  half split and half gain.

## Decisions taken by default — confirm or override

| # | Decision | Reason |
|---|---|---|
| D1 | Withhold 2025-Q3 rather than read an earlier filing's figure | Same as ABT 2012-Q4 (P2 D2): picking a named filing for one quarter needs an override used once; missing is handled downstream. The 10-K's 9,437 would match its neighbours but needs that override |
| D2 | Keep Yahoo's adjusted basis for per-share values (H2) | It is the panel's existing basis and keeps market cap and P/E consistent; only HON's three cells change. An actual-share basis touches 19 companies and prices (out of scope) |
| D3 | H2 is a general rule, not a HON override | The filer's ratio is a filed fact; a rule costs the same as an override and covers the next case |

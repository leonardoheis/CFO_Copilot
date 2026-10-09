# Plan — fix the ingestion defects

Implements [`docs/specs/ingestion-defects-cop-ge.md`](../specs/ingestion-defects-cop-ge.md).
Three root causes, one step each, then re-ingest and lift the exclusions. GE is
not explained by any of them and gets its own investigation (Step 6).

| Root cause | Companies | Rule | Step |
|---|---|---|---|
| Subtraction mixes a restated total with original parts | COP, PFE (GE's Q4s) | I1 | 1 |
| Cost of revenue filed as products + services, no total | SLB, VZ, GE | I7 | 2 |
| Business has no cost of revenue; Alpha Vantage fills it | UNH, UNP | I8 | 4 |

Alpha Vantage filling gross profit for 22 other companies is an **accepted
risk**, not a defect to fix here — see the spec's "Accepted risk" section.

## Step 1 — derive quarters from first-reported figures (I1)

`src/app/data/xbrl_facts.py`, `src/app/data/xbrl.py`

**Root cause.** `_select_fact_per_period` keeps the latest-filed value of each
period independently. A full-year period is restated in later 10-Ks; the
nine-month period it is subtracted from is not. The subtraction then pairs two
vintages:

| | Total (latest) | Parts | Panel | Total (first reported) | Result |
|---|---|---|---|---|---|
| PFE 2018-Q4 | 40,825 (FY2020 10-K) | 39,670 | 1,155 | 53,647 (FY2018 10-K) | **13,977** |
| PFE 2019-Q4 | 40,905 (FY2021 10-K) | 39,062 | 1,843 | 51,750 (FY2019 10-K) | **12,688** |
| COP 2010-Q4 | 56,215 (FY2012 10-K) | 137,715 (3 quarters) | −81,500 | 189,441 (FY2010 10-K) | **51,726** |

All five numbers checked against SEC companyfacts (CIK 78003, 1163165) on
2026-10-07.

**Revised after review (2026-10-08, decision D7).** First-reported alone broke
PFE 2020-Q4 (5,947 instead of 11,427). `quarterly_facts_from_facts` now
derives each non-native quarter from both maps via `_derive_quarter`, and
`_same_basis_quarter` keeps the value when they agree within
`SAME_BASIS_TOLERANCE` (1%), otherwise the one nearer the previous quarter
(a seasonal variant was tried and rejected, see spec D7), or
missing with a warning when there is no previous quarter. Tests cover PFE 2018,
PFE 2020, COP 2010 and the no-previous-quarter case; GOOGL 2012 is a strict
xfail recording the rule's known limit. Checked on live SEC data:
PFE 2018–2021 Q4 = 13,977 / 12,688 / 11,427 / 23,635; COP 2010-Q4 = 51,726.

**Original change (superseded in part).**
- Give `_select_fact_per_period` the choice of vintage (`max` or `min` by
  `filed`) and expose two named selectors: `latest_fact_per_period` (today's
  `deduplicate_fact_records`, renamed) and `first_reported_fact_per_period`.
  Both keep the rejected-accession filter.
- `quarterly_facts_from_facts` builds both maps. `_find_native_fact` keeps the
  latest map — a restated quarter is still the best value for that quarter.
  `_find_ytd_fact` and `_find_annual_minus_three_quarters` take the
  first-reported map for **both** the total and the parts, so the two sides of
  the subtraction come from the same point in time.
- The `filed` date on a derived quarter becomes the first-reported total's
  filing date (it was the latest one); note this in the provenance docstring.

**Tests** (`tests/data/test_xbrl.py`):
- PFE-shaped facts: FY total filed twice (53,647, then 40,825 two years later),
  nine-month YTD filed once → derived Q4 is 13,977.
- COP-shaped facts: FY total restated, three native quarters → Q4 is 51,726.
- A native quarter restated later still returns the latest value.
- Existing tests stay green unchanged.

## Step 2 — sum split cost of revenue (I7)

`src/app/data/sources/sec_edgar/concepts.py`, `source.py`, `parsing.py`

**Root cause.** SLB filed `CostOfGoodsSold` (products, 2,133 in 2016-Q2) and
`CostOfServices` (4,332) with no combined tag. The `cogs` chain does not know
`CostOfServices`, so it takes the products part alone.

**Change (done).**
- The `cogs` chain is unchanged. Three chains are added: `cogs_total`
  (`CostOfGoodsAndServicesSold`, `CostOfRevenue`), `cost_of_products`
  (`CostOfGoodsSold`) and `cost_of_services` (`CostOfServices`).
- `parsing.cost_of_revenue` replaces `cogs` with products + services only where
  no total is filed and both parts are; `source.py` applies it, so the raw
  frame keeps one `cogs` column.

**Gate (run 2026-10-07 on every company's live companyfacts).** Two rules were
rejected first: *total always wins* breaks LLY and BA 2009-Q4; *largest of
total and parts* breaks LMT. The adopted rule changes only SLB (8 quarters),
VZ (12) and GE (39), each toward its own surrounding gross margin — evidence in
the spec. VZ joins the re-ingest list.

**Tests** (`tests/data/sources/` SEC parsing tests):
- Total present → total wins over the parts.
- No total, both parts → sum (SLB 2016-Q2: 2,133 + 4,332 = 6,465; gross profit 699).
- No total, products only → products.

## Step 3 — withdrawn

An identity check on derived and Alpha Vantage rows (I2, I6) was measured
before coding and withdrawn: it would reject 143 rows, mostly companies whose
native rows miss the identity by definition, and two LMT rows (A4). UNP, its
target, is fixed by Step 4. Evidence in the spec.

## Step 4 — declare companies with no cost of revenue (I8)

`src/app/data/companies.py`, `config/companies.yaml`, `src/app/data/pipeline.py`

**Change.**
- `_PanelConfig` and `CompanyPanelMetadata` gain `has_cost_of_revenue: bool`,
  defaulting to `True`, so no other YAML entry changes.
- UNH's and UNP's `panel:` blocks set `has_cost_of_revenue: false`.
- `merge_panel` blanks `gross_profit_usd_m`, `gross_margin` and `opex_usd_m`
  for such a company, after `_fill_missing_financials` (otherwise Alpha
  Vantage's `grossProfit` refills them). Read the flag through
  `sources.registry.company_metadata(ticker)`.

**Tests:**
- `tests/data/test_companies.py`: the flag parses; omitted means `True`.
- `tests/data/test_pipeline.py`: a company with the flag off has the three
  columns NaN in every row, including rows from the fallback; revenue,
  operating income and net income unchanged (A7, A9).

## Step 4b — explain the new gaps in the missing-value ledger

`src/app/data/missing.py`

Step 4 creates NaN cells that NB00 § 3 would list as `unexplained`, which fails
its exit criterion. `missing_value_ledger` gains a `no_cost_of_revenue` ticker
set, which NB00 passes from the registry, and that reason for `opex_usd_m`,
`gross_profit_usd_m` and `gross_margin`.

**Tests** (`tests/data/test_missing.py`): the reason applies to a listed ticker;
the same NaN in an unlisted ticker stays `unexplained`.

## Step 5 — register COP's basis change (I3)

`config/structural_breaks.yaml`

**Done:** `COP: [2011-06-30]`. Confirmed on SEC companyfacts: 2011-Q1 was never
restated (56,530, also in the 2012-Q1 10-Q, filed before the spin-off closed),
while 2011-Q2 onward comes from the 2012 10-Qs' restated comparatives (17,668
against 65,627 as first filed). The break therefore flags 2011-Q2 → 2012-Q1,
the four quarters whose YoY spans the two bases; the spin-off date (2012-Q2)
would flag four quarters already on one basis. NB00's `EXPECTED_BREAK_ROWS`
goes from 7 × 4 to 8 × 4. PFE's 2020-12-31 break was already registered.

## Step 6 — investigate GE before fixing it

**Done (2026-10-07).** 47 of GE's 56 identity misses pair SEC opex with Alpha
Vantage operating income (GE rarely files `OperatingIncomeLoss`). Rebuilt with
Steps 1–2, GE's opex / revenue is still negative through 2008–2009 and swings
−1.25 to 3.06 elsewhere, so it cannot be repaired. BMY, F and CVX share the
source mix but have stable opex: not defects. Evidence in the spec.

**Change (I9, decision D6).** Same pattern as Step 4, one column:
- `_PanelConfig` and `CompanyPanelMetadata` gain `has_reliable_opex: bool`
  (default `True`); GE sets it to `false` with its reason in the YAML.
- `merge_panel` blanks `opex_usd_m` for such a company after the fallback.
- `CompanyRegistry.tickers_without_reliable_opex()`; `missing_value_ledger`
  takes that set and explains the gaps as `unreliable_opex`. The ledger now
  maps each declared column to its reason, so a company can carry both.
- NB00 passes both registry sets to the ledger.

**Tests:** GE's opex is empty while its gross profit is kept; the registry lists
GE only; the ledger reason applies to `opex_usd_m` only.

## Step 7 — re-ingest all companies (I4, A5)

I1 changes derived quarters in 56 of 60 companies, so every company is
re-ingested with the same rules. Alpha Vantage responses are cached under
`data/raw/alpha_vantage/`, so this costs no quota (about 25 minutes, SEC only).

```bash
# clear the ledger, then re-ingest every company
uv run python -c "from app.data.batch import ledger_path; ledger_path().write_text('{}')"
uv run poe reingest-batch --limit 60 --end 2026-06-30  # = Settings.LAST_REPORTED_QUARTER; the default follows today's date
```

Then rebuild `panel_long.parquet` with NB00 — **the user runs the notebook**.

## Step 7b — ORCL annual-as-quarter and negative cost (I10, I11), done

Found by NB01 after the full re-ingest (spec "New defects found by NB01").
- `xbrl.py`: `_is_annual_total` rejects a native flow quarter equal to a
  same-end annual value of any tag in the concept (`annual_totals_by_end`,
  passed by `source.py`; `ANNUAL_TOTAL_TOLERANCE` 0.1%, `MIN_ANNUAL_DAYS` 300);
  period averages exempt. A same-tag first version missed ORCL FY2020.
- `concepts.py` / `source.py`: `ConceptSpec.never_negative` on the four cost
  chains; `_with_sign_errors_corrected` reads negative facts by magnitude
  before the chain compares tags, with a warning.
- Tests: ORCL FY2018 Q4 = 39,383 − 28,579; a period average equal to the year
  stays native; a negative cost is read by magnitude; BA's negative total beats
  the products tag.
- Scan of all 60 companies first, then a re-ingest of ORCL, CAT and BA only;
  every other company's file byte-compared: unchanged.

## Step 7c — Alpha Vantage EBITDA and T's merger (I12, D8, D9)

- `alpha_vantage/parsing.py`: `merge_income` sets EBITDA to operating income +
  income-statement D&A; `merge_cash_flow` fills a still-empty EBITDA from the
  cash-flow D&A. Vendor `ebitda` is no longer read.
- Tests: KMB's broken `ebit` is ignored; cash-flow D&A fills the gap; no D&A
  leaves EBITDA missing.
- `config/structural_breaks.yaml`: `T: [2007-03-31, 2022-06-30]`; NB00
  `EXPECTED_BREAK_ROWS = 9 * 4` and the ledger waiver lists F's six EBITDA gaps.
- Re-ingest only the companies with an Alpha Vantage EBITDA cell in the panel;
  diff every file against a snapshot: only `ebitda_usd_m` may change (A11).

## Step 8 — verify, lift exclusions, update the thesis

Status 2026-10-09: items 1, 2 and 5 done (results in the spec); item 4 done for
the scraper problems, breaks and appendix. Left for after the user's NB01 run:
A10, item 3 and the thesis results chapter.

1. Check A1–A11 (A3 withdrawn) on the rebuilt panel with one `uv run python -c`
   per criterion; record each number in the PR description.
2. A1, A4, A6 hold → delete COP from `config/ingestion_defects.yaml`; A2, A7, A8 hold → delete the `opex_usd_m` block too (I5).
   Do this before the user's NB01 run, so COP enters it.
3. NB01's markdown was rewritten for the four targets on 2026-10-08; after the
   user's run, refresh its numbers and drop the KMB, UNP and T candidates.
4. Thesis: item 6 of the scraper problems gets its solution, a new item records
   I12 (Alpha Vantage EBITDA) and the T break; the results
   chapter covers four targets; the appendix no longer excludes COP.
5. `uv run poe check` green (A5).

## Files touched

| File | Step |
|---|---|
| `src/app/data/xbrl_facts.py`, `src/app/data/xbrl.py` | 1 |
| `src/app/data/sources/sec_edgar/concepts.py`, `source.py`, `parsing.py` | 2 |
| `src/app/data/pipeline.py` | 4, 6 |
| `src/app/data/companies.py`, `config/companies.yaml` | 4, 6 |
| `src/app/data/missing.py`, NB00 ledger call | 4b, 6 |
| `cfo-copilot-thesis/main.tex` (accepted risk, scraper problems) | 8 |
| `config/structural_breaks.yaml` | 5, 7c |
| `src/app/data/sources/alpha_vantage/parsing.py`, `tests/data/sources/test_alpha_vantage.py`, NB00 constants | 7c |
| `config/ingestion_defects.yaml` | 8 |
| `src/app/playground/01_eda_feature_engineering.ipynb` (markdown only) | 8 |
| `tests/data/test_xbrl.py`, `tests/data/sources/…`, `tests/data/test_pipeline.py`, `tests/data/test_companies.py` | 1–4 |

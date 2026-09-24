# Spec — NB00: consolidate the ingested panels, flag them, track them

Status: proposed. Implemented by
[`docs/plans/nb00-ingest-and-consolidate.md`](../plans/nb00-ingest-and-consolidate.md).
Parent: [`docs/CFO_COPILOT_MASTER_PLAN.md`](../CFO_COPILOT_MASTER_PLAN.md)
(§6 NB00, §3.4 hazards, §2.3 W&B, §8 layout).
Unblocks: [`docs/specs/eda-feature-engineering.md`](eda-feature-engineering.md).

## Problem

Ingestion has written 60 per-company panels. The master plan makes NB00 the
gate before any exploration: one consolidated panel, one shared macro table,
the reported-versus-projected question answered in writing, and the flag
columns the later notebooks assume. None of that exists, so the EDA notebook
would have to read 60 separate files and could not use `covid`,
`structural_break`, `outlier_flag` or `is_projected`. The tracking code the
EDA spec relied on is also needed here first, because NB00 owns the
`panel_long` and `macro_q` W&B artifacts.

## Scope

In: validated loading of the per-company panels, consolidation into
`panel_long` and `macro_q`, the four flags, the missing-value ledger, W&B
tracking, and the written answer to E1.

Out: new ingestion (the notebook reads existing panels; the user runs
`poe ingest-data`), any change to sources or `companies.yaml`, and the
fiscal-calendar standardisation, which is a documented limitation (see below).
The playground notebook is `00_ingest_and_consolidate.ipynb`.

## E1 — answered

**2026-Q2 (date 2026-06-30) is reported data, not a projection.** Confirmed by
the project owner on 2026-09-23. The panel evidence agrees: all 60 companies
have revenue for that quarter and none repeats the prior quarter's value. 2026-Q3
ends 2026-09-30 and has not been reported, so it is the quarter to forecast: the
last reported quarter (2026-Q2) is the origin and 2026-Q3 is horizon 1.

## Evidence

Measured on `data/processed/` on 2026-09-23.

| Fact | Value | Consequence |
|---|---|---|
| Panel files | 60 files × 81 rows = 4,860 rows; master says "~4,800" | Row count is asserted against the sum, not against 4,800 |
| 2026-06-30 row | 60 revenue values present; 0 equal the prior quarter; NaN only in `ebitda_usd_m` (COST) and `pe_ratio` (APD, BA, GIS, INTC, MRK, PFE) | Supports E1; the six P/E gaps are non-positive or missing EPS |
| Macro block | Identical across all 60 files, no NaN | It can live once in `macro_q` |
| Constant columns | `is_public` only | It is the one column to drop |
| Flag columns | none of the four exist | NB00 creates them |
| NaN cells | revenue 9; the other financial lines 9 each; EBITDA 10; EPS 25; price 16; market cap 19; P/E 308 | The ledger must account for every one |
| Where they come from | EPS 25 = TSLA 16 + COST 9; EBITDA 10 = the 9 no-revenue rows + COST 1; market cap 19 = TSLA 16 + ADBE, BBY, ORCL 1 each; P/E 308 all have EPS missing or ≤ 0 | Expected unexplained residue: **COST EPS (9) and COST EBITDA (1)**. These are real gaps to look at, not to hide |
| Outlier candidates | Isolation Forest per company on the three margins plus YoY revenue growth flags 120 / 180 / 240 rows at contamination 0.02 / 0.03 / 0.05 (2 / 3 / 4 per company). AMZN 2026-06-30 is flagged at all three | Default 0.03; AMZN 2026-Q2 (net margin 9.9% → 16.7% → 31.2%, EPS 1.95 → 2.78 → 5.75) is the acceptance case |
| Fiscal calendars | Ingestion snaps each fiscal period end to the nearest calendar quarter end within 46 days, so the panel `date` is never a raw fiscal date. The raw cache holds only Alpha Vantage data, so the true period ends are not on disk | Recorded as a limitation, not audited (Q1) |

## Required behaviour

**R1. Per-company panels load through one validated entry point.** Loading a
ticker returns its panel with `date` as datetime, or fails naming the ticker and
the problem: file missing, required column missing, dates not consecutive
calendar quarter-ends. Loading everything returns every panel on disk keyed by
ticker.

**R2. Consolidation.** `panel_long` has one row per (ticker, quarter), sorted by
ticker then date, with exactly as many rows as the per-company panels hold
together, and no macro columns. `macro_q` has one row per quarter with the ten
macro columns. If any company's macro block differs from the others, consolidation
fails naming the companies.

**R3. Only known-constant columns are dropped.** `is_public` is dropped.
If it is not constant, consolidation fails instead of dropping information.

**R4. `is_projected` is true exactly for quarters after the last reported
quarter.** That quarter is a setting (currently 2026-06-30), so no row is
projected today. Adding a newly reported quarter means changing the setting on
purpose.

**R5. `covid` is true for 2020-06-30, 2020-09-30 and 2020-12-31** for every company.

**R6. `structural_break` comes from a hand-entered config file** of
(ticker, break quarter). A company is flagged in its break quarter and the
three quarters after, the window in which a year-over-year comparison
spans the break. The file lists master §3.4's entries: ABT 2013-Q1, BMY 2019-Q4,
PFE 2020-Q4, MRK 2021-Q2, T 2022-Q2, and GE (master says "2023–24"; proposed
2023-Q1 and 2024-Q2). A ticker in the file that is not in the panel, or a
date that is not a quarter end, is an error.

**R7. `outlier_flag` marks rows an Isolation Forest finds unusual, and removes
nothing.** One model per company on the three margins and YoY log revenue
growth, standardised, contamination 0.03, fixed seed. A company with fewer than
16 complete rows gets no flags. Rows missing any input are not flagged.
The flag is fitted on each company's whole history, so it depends on later
quarters: it is an annotation for analysis and evaluation masks, never a model
feature.

**R8. A missing-value ledger accounts for every NaN cell** with a reason:
`pe_undefined_by_rule` (P/E with missing or non-positive EPS), `pre_listing`
(market columns and EPS before the company's first price), `no_filing_data`
(financial lines and market cap in a quarter with no revenue), or
`unexplained`. Unexplained cells are listed for review; each is either fixed by
re-ingestion or carries a written waiver in the notebook.

**R9. Outputs are persisted** as `data/processed/panel_long.parquet` and
`data/processed/macro_q.parquet`, and logged as W&B dataset artifacts `panel_long`
and `macro_q`.

**R10. Tracking goes through a seam, and W&B stays optional.**
- Run names follow the master plan (`{nb}-{model}-{variable}-{protocol}[-H{n}]`,
  variable without its `_usd_m` suffix); the config keys of master §2.3 are
  logged on every run.
- Tables, figures and datasets can be logged; the run always finishes, even
  when the body raises.
- Mode is `online`, `offline` or `disabled`, from settings. `online` without an
  API key fails before any run starts, naming the setting.
- The package imports and the DI container builds when `wandb` is not
  installed, because the image never has it (`uv sync --locked
  --no-default-groups`). Starting a run then fails saying which dependency
  group to install.
- No consolidation or flag code imports W&B.

**R11. The notebook orchestrates only.** No `def` or `class`; it obtains the
panel store and tracker from the DI container and does not run ingestion.

**R12. Project rules hold.** mypy strict; no `# noqa`, `# ruff: ignore` or
`# type: ignore` added; no `@staticmethod`; Pydantic (frozen, `extra="forbid"`)
for config and result types; no exception used to drive a loop iteration; paths
and credentials from `Settings`.

## Known limitation — fiscal calendars

Companies whose fiscal quarters do not end on a calendar quarter end
(master §3.4 lists AAPL, MSFT, PG, NKE, COST, DE, WMT, HD, M, BBY; ORCL, CSCO,
ADBE and others are in the same position) are shifted onto the nearest calendar
quarter end, by up to 46 days. Company values and macro values are therefore
aligned within that margin, not exactly. NB00 does not correct it. NB01's
diagnostics are per-company, so seasonality is unaffected; the macro
sensitivity table inherits the margin.

## Acceptance criteria

- **A1.** Loading all panels returns 60 frames of 81 rows.
- **A2.** `panel_long` has 4,860 rows and no `is_public` or macro column;
  `macro_q` has 81 rows and 11 columns (date plus 10).
- **A3.** `is_projected` is false for all rows and true for none.
- **A4.** `covid` is true on exactly 180 rows (3 quarters × 60).
- **A5.** `structural_break` is true on exactly 28 rows (7 breaks × 4 quarters);
  this changes if the GE entries change.
- **A6.** AMZN 2026-06-30 has `outlier_flag` true; total flagged rows is 180
  ± the rows dropped for missing inputs.
- **A7.** The ledger's NaN cells add up to the counts in the evidence table;
  `unexplained` is COST EPS (9) and COST EBITDA (1), or the difference is
  explained in the notebook.
- **A8.** W&B project `cfo-copilot` shows run `nb00-ingest-panel` with the config
  keys and the `panel_long` and `macro_q` artifacts; run metadata shows the git commit.
- **A9.** `uv run poe check` passes at the 80% gate, and importing `app` works
  in an environment without `wandb`.
- **A10.** The notebook has no `def` or `class`, and the notebook's markdown
  states E1's answer.

## Decisions taken by default — confirm or override

| # | Default | Why |
|---|---|---|
| Q1 | No fiscal-calendar audit; documented limitation | An audit needs hand-entered fiscal year ends for 60 companies and only records an offset; it would not change any value |
| Q2 | Break window is the break quarter plus three | Matches the four-quarter span of the YoY growth the features use |
| Q3 | GE breaks at 2023-Q1 and 2024-Q2 | Master gives only "2023–24"; please confirm the quarters |
| Q4 | Outlier contamination 0.03 | About 3 rows per company; AMZN 2026-Q2 is flagged at 0.02, 0.03 and 0.05 |
| Q5 | `outlier_flag` is never a model feature | It is fitted on the whole history; using it would leak later quarters |
| Q6 | The last reported quarter is a setting, not derived from the clock | A quarter is reported weeks after it ends; the clock cannot know |
| Q7 | `git_sha` is dropped from the logged config | W&B records the commit on every run; a subprocess call would need a lint suppression |
| Q8 | `WANDB_MODE` defaults to `offline` | Nothing leaves the machine until the mode is set to `online` in `.env` |

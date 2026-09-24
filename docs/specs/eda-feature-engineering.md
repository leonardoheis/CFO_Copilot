# Spec — EDA and feature engineering (NB01 + the feature half of NB02)

Status: proposed. Implemented by
[`docs/plans/eda-feature-engineering.md`](../plans/eda-feature-engineering.md).
Parent: [`docs/CFO_COPILOT_MASTER_PLAN.md`](../CFO_COPILOT_MASTER_PLAN.md)
(§6 NB01, and the feature/transform/leakage half of NB02).
**Depends on:** [`docs/specs/nb00-ingest-and-consolidate.md`](nb00-ingest-and-consolidate.md).
NB00 must be built and run first; it produces `panel_long`, `macro_q`, the four
flags, and the W&B tracking this notebook uses.

## Problem

`src/app/playground/01_eda_feature_engineering.ipynb` is four `TODO` cells. The
master plan says notebooks orchestrate and reusable code lives in `src/app/`,
because "a notebook that defines a model class is a notebook whose results the
API cannot reproduce". The API will need the same feature construction at
serving time, so the logic cannot live in a notebook.

## Scope

In: reading the NB00 outputs, per-series diagnostics (master NB01), panel-level
EDA outputs, target transforms with inverses, the feature builder, the leakage
check, the exported feature matrices, and the W&B runs those produce.

Out (own spec later): the `evaluate()` harness, both protocols, baselines,
conformal wrappers, and the `nb02-v1.0.0` freeze. NB00's work (consolidation,
flags, ledger, tracking code) is not repeated here. The playground notebook
keeps its filename; it covers master NB01 plus the feature half of NB02.

## Evidence

Measured on `data/processed/` on 2026-09-23, before NB00.

| Fact | Value | Consequence |
|---|---|---|
| Panels | 60 companies × 81 quarters, 2006-06-30 → 2026-06-30, all calendar quarter-ends, no gaps | Row position is a valid quarter offset |
| E1 | Answered: 2026-Q2 is reported (see NB00 spec). 2026-Q3 is the forecast quarter, horizon 1 from the 2026-Q2 origin | No row is excluded as projected today; the last `h` origins of every company have no target yet and are the rows a live forecast uses |
| Revenue NaN | 9 rows: ADBE 2006-06, ORCL 2006-06, BBY 2006-12, TSLA 2006-06/09/12, 2007-06/09, 2008-06 | TSLA and BBY have **interior** gaps, so dropping NaN would splice the series across missing quarters |
| Non-positive values | revenue 1 row (1 company); operating income 204 (37 cos); EBITDA 116 (32); free cash flow 682 (49) | `log` (master D4) is undefined for three of the four targets on many rows |
| `gross_margin` vs `gross_profit / revenue` | max absolute difference 0.0 | Ratios are exact functions of same-quarter figures: known at the origin, forbidden for the target quarter |
| Outlier flag | Fitted per company on the whole history (NB00 R7) | It depends on later quarters, so it cannot be a feature |

## Required behaviour

**R1. The notebook reads NB00's outputs through one loader.** It returns one
panel per ticker: `panel_long` joined to `macro_q` on `date`, with the four
flags, `date` as datetime, and rows flagged `is_projected` excluded. It fails
naming the missing file when either NB00 output is absent, and naming the
problem when the macro table does not cover every panel date.

**R2. Diagnostics never splice a series and never raise for a bad series.**
Each (company, variable) yields one record. The analysed history is the run of
observed values after the last gap; leading and interior NaN are never
imputed or dropped-and-joined. A record states its observation count and a
status. Fewer than 16 observations yields an `insufficient_data` record, not an
exception. Log-based fields exist only where every analysed value is positive,
and the record says whether that held.

**R3. A diagnostics record carries** the differencing order needed on levels
and on logs (ADF and KPSS agree), seasonal and trend strength (period 4),
Ljung-Box p-value, Box-Cox lambda and coefficient of variation.

**R4. Panel-level EDA produces three persisted results.** A seasonality regime
per company (3 ordered clusters, regime 0 the least seasonal, deterministic for
a fixed seed), a company-growth × macro-variable correlation table that can be
aggregated by sector, and the levels-versus-logs differencing comparison across
all companies. The regimes are the input to feature group S. The sector table
inherits NB00's fiscal-calendar limitation (macro aligned within 46 days).

**R5. Target transforms are invertible and refuse invalid input.** The three
arms of master NB04 (`log_diff1`, `log_diff4`, `seasnaive_residual`) are defined
for an **origin** quarter and a horizon of 1–4:

- `log_diff1`: log level at origin+h minus log level at origin
- `log_diff4`: log level at origin+h minus log level at origin+h−4
- `seasnaive_residual`: the `log_diff4` target minus the YoY log growth
  observed at the origin, so predicting zero reproduces the seasonal-naive
  baseline

Reconstructing a level from a prediction recovers the actual level to 1e-9 when
given the true target, for every arm and horizon. A shrinkage factor scales the
prediction on the residual arm only. Non-positive input raises a typed error
stating how many values failed; it never returns NaN or −inf silently. Missing
values stay missing.

**R6. Features depend only on information known at the origin.** A row is
(company, origin quarter). Whatever changes in any later quarter, that row's
features are unchanged, bit for bit. The convention: origin is the last
reported quarter, "lag 1" is the origin quarter itself, and the target is
origin + h. Groups, from master NB04:

| Group | Content |
|---|---|
| L | YoY log growth of the target variable at lags 1, 2, 3, 4, 5, 8 |
| R | Rolling mean and std of that growth over 4 and 8 quarters; momentum (lag 1 − lag 2) |
| M | The three margin ratios at the origin |
| X | All ten macro columns at the origin |
| XD | Real rate: `fed_funds − cpi_yoy` at the origin |
| C | Calendar quarter (1–4) of the **target** quarter, which is known in advance |
| S | Sector and the seasonality regime from R4 |
| F | `covid` and `structural_break` at the origin (NB00 flags) |

`outlier_flag` is not in any group. Insufficient history yields NaN, never a
filled value; no row is dropped. Asking for S without a regime for that company
is an error, and asking for F without the flag columns is an error.

**R7. The leakage check is itself tested.** It passes for the real builder at
every horizon and group, and fails, naming the column, for a builder that peeks
one quarter ahead.

**R8. Feature matrices are exported once per horizon** as parquet, all
companies pooled, every origin row kept. Each row carries its ticker, origin
date, target date, the actual target level, and the transformed target (NaN
where the target is not yet known: the last `h` origins of each company).

**R9. Tracking uses NB00's seam.** One EDA run per target variable and one
features run, named per master §2.3 and logging its config keys; the
`features_h{1..4}` files are logged as dataset artifacts.

**R10. The notebook orchestrates only.** It contains no `def` or `class`. It
obtains the loader and tracker from the DI container.

**R11. Project rules hold.** mypy strict; no `# noqa`, `# ruff: ignore` or
`# type: ignore` added; no `@staticmethod`; Pydantic (frozen, `extra="forbid"`)
for result and config types; no exception used to drive a loop iteration; paths
and credentials from `Settings`.

## Acceptance criteria

- **A1.** Loading returns 60 frames of 81 rows, each with the four flag columns and all ten macro columns.
- **A2.** Diagnostics for all four target variables give 240 records. Revenue
  `n_obs` is 72 for TSLA, 78 for BBY, 80 for ADBE and ORCL, 81 for every other
  company.
- **A3.** For AAPL, AMZN, GOOGL, MSFT, PEP and PG revenue, the differencing
  orders equal master Appendix C and seasonal strength is within 0.05. Any
  disagreement is recorded with its cause, not tuned away. TSLA is excluded on
  purpose: Appendix C's n=75 comes from dropping NaN across gaps.
- **A4.** The leakage check passes on the real panels for h = 1…4, all groups.
- **A5.** The round trip holds to 1e-9 for 3 arms × 4 horizons on real revenue.
- **A6.** `features_h1…h4.parquet` exist, 4,860 rows each, and labelled rows are
  at most 4,860 − 60·h.
- **A7.** W&B project `cfo-copilot` shows one EDA run per target variable and
  one features run with a `features_h{1..4}` dataset artifact, each with the
  config keys.
- **A8.** `uv run poe check` passes at the 80% gate.
- **A9.** The notebook has no `def` or `class`.

## Decisions taken by default — confirm or override

| # | Default | Why |
|---|---|---|
| Q1 | Harness, baselines, conformal and freeze are a separate spec | Keeps this one testable end to end; `harness_version` stays null in config |
| Q2 | Log-based transforms and features cover **revenue only**; the other three targets get diagnostics on levels | Evidence: 204, 116 and 682 non-positive rows. Which transform fits signed series is master O1 and the EDA's transform comparison decides it |
| Q3 | Group L uses YoY log growth whatever the target arm | One feature matrix per horizon, as the master artifact list has; Appendix D measured YoY lags at 5.2% MAE against 5.8% for QoQ (7 companies) |
| Q4 | Group M is the three margins only; growth of signed lines (EBITDA, opex, FCF) waits on Q2 | Same non-positive problem |
| Q5 | Group F is `covid` and `structural_break`; `outlier_flag` stays out | The outlier flag is fitted on the whole history and would leak later quarters |

# Plan — pre-listing flag, profile frame, training rows

Implements [`docs/specs/pre-listing-and-training-rows.md`](../specs/pre-listing-and-training-rows.md).

Notebooks are edited here but **run by the user**.

## Step 1 — `pre_listing` flag (R1, R2)

**File:** `src/app/data/flags.py`.
- `pre_listing_flag(company)`: `date` before the first date with a non-null
  `stock_price_usd`; all False when the company never has a price.
- `_flag_company` adds it; `add_flags` returns five flag columns.

**Tests:** `tests/data/test_flags.py` — rows before the first price are
flagged, the first priced row and later are not; a company with no price is
all False; `add_flags` emits the column.

**NB00 (source only):** assert `panel_long["pre_listing"].sum() ==
EXPECTED_PRE_LISTING_ROWS` (16).

## Step 2 — profile frame (R3)

**File:** `src/app/services/diagnostics/profiling.py`.
- `profile_frame(pooled)`: drops `date`, the provenance columns, and
  pre-listing rows; tolerates a frame without `pre_listing`.

**Tests:** `tests/services/diagnostics/test_profiling.py`.

**NB01 (source only):** cell 7 builds `profile_frame` with it; the drift
split uses the same frame's dates.

## Step 3 — feature datasets without pre-listing origins (R4)

**File:** `src/app/services/features/service.py` — `_company_rows` drops
pre-listing rows after the builder runs on the full panel.

**Tests:** `tests/services/features/test_service.py` — pre-listing rows are
absent; the first listed row's lag still reads a pre-listing quarter.

**NB01 (source only):** assertion A6 becomes
`len(dataset) == n_rows - n_pre_listing`.

## Step 4 — training rows (R5)

**File:** `src/app/services/features/service.py` — module-level
`training_rows(dataset)` keeps rows with `y` and every column of
`feature_groups_by_column()` present in the dataset non-null; exported from
`app.services.features`.

**Tests:** keeps a complete row; drops a row with NaN `y`; drops a row with a
NaN feature; ignores NaN in non-feature columns (`target_level`).

**NB02 (source only):** a section 0 cell reads the h1 feature file and
applies it.

## Verification

`uv run poe check` green. The user runs NB00, NB01 and NB02.

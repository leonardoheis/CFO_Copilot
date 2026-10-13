# Plan — Target transform comparison (NB01b)

Spec: [`docs/specs/transform-comparison.md`](../specs/transform-comparison.md).

## Step 1 — the comparison service (T1–T6)

- `src/app/services/diagnostics/transform_comparison.py`:
  - `LevelTransform`, `candidates_for(variable)` (power family for revenue,
    signed family otherwise) and `baseline_transform(variable)` (log; revenue-scaled);
  - `TransformComparer.compare(panels, variable=...)`: one row per (ticker,
    transform) with λ, level dependence (size = revenue), Jarque–Bera,
    Anderson–Darling, skewness, excess kurtosis;
  - `summarize_transforms(table, baseline=...)` and
    `preferred_transform(table, baseline=..., normality=...)` (T5, T6).
- Series preparation reuses `with_short_interior_gaps_filled` and
  `observed_since_last_gap` from `series.py` (T2); `stl_remainder` is a new
  public helper there; the 8-quarter window is `DiagnosticsSettings.variance_window`.
- Tests first, in `tests/services/diagnostics/test_transform_comparison.py` (B2).

## Step 2 — wiring and figure

- Export from `app.services.diagnostics`; `transform_comparer` provider in
  `injections/production.py`.
- `EdaFigures.transform_comparison(table)`: box plots of level dependence and
  Jarque–Bera statistic per transform, with a test.

## Step 3 — notebook `01b_transform_comparison.ipynb`

Four targets as in NB01: scores, summaries, decision table (Jarque–Bera and
Anderson–Darling), by sector, figures; one W&B run per target
(`nb01b-transforms-{variable}`); all tables in `nb01b_transform_comparison.csv`.
Run offline with W&B stubbed to check every cell; **the user runs it for real**.

## Step 4 — record the decisions (B3)

After the user's run: the answer cell of NB01b, open question 6 of NB01's
summary, the EDA spec (F3), and the thesis (method and results).

## Verification

`uv run poe check` green (lint skips nbstripout, so notebook outputs are kept).

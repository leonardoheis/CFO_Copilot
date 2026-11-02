# Plan — NB02 evaluation harness

Spec: `docs/specs/nb02-evaluation-harness.md`. Master plan milestone M3
(hard gate before NB03).

**Status: not started.** Decisions D1–D4 of the spec were confirmed on
2026-10-31, each at its default:

- origins per horizon;
- the trailing-revenue error scale plus MASE;
- renumber the notebooks;
- all three phases before the tag.

## Before starting

- Work on the frozen data only (`data/backups/thesis_2026-10-30/`). No
  re-ingest until the harness is tagged.
- Commit the current working tree first (O1–O4, HON H1, docs). That way the
  harness starts from a clean commit, which it records on every result.
## Layout

New service package `src/app/services/evaluation/`, following the
`diagnostics/` and `features/` pattern. Notebooks only orchestrate.

| File | Holds |
|---|---|
| `models.py` | `EvaluationSettings`: levels 0.80/0.90/0.95, 16 origins, 12 folds, histories 8/12/20/40/all, the calibration window and seed. Also `Protocol` (A, B) and the result record type |
| `splits.py` | Protocol A origins and training masks; Protocol B folds and history truncation |
| `scale.py` | Error scale per target (R5): log level for revenue, level over trailing revenue otherwise; level reconstruction via `TargetTransformer.reconstruct` |
| `baselines.py` | Seasonal naive, seasonal naive with growth, naive, drift |
| `metrics.py` | MAE, RMSE, MASE, MAPE (revenue only), out-of-sample R² against the baseline to beat (master plan D25); coverage, width, Winkler; CRPS and pinball when quantiles exist; HLN-corrected Diebold–Mariano |
| `conformal.py` | Protocol A rolling calibration with ACI; Protocol B cross-conformal; MAPIE where its API fits the calibration rule (spec R8) |
| `leakage.py` | The R12 assertions, run inside every evaluation |
| `harness.py` | `EvaluationHarness.evaluate(forecaster, …)` and the report tables |
| `exceptions.py` | `EvaluationLeakageError`, `MissingPredictionsError` (reported, not raised), `UnknownBaselineError` |

Also:

- `src/app/domain/forecaster.py`: a `Forecaster` protocol, `fit(train) -> Self`
  and `predict(test) -> DataFrame` with `y_hat` and optional quantile
  columns. It works in target space; the harness reconstructs levels.
- `src/app/data/results_store.py`: `ResultsStore`, which appends and reads
  `data/results/results.parquet` (partitioned by model). Mirrors
  `FeatureStore`.
- `settings.py`: `RESULTS_DIRECTORY`; `injections/production.py`:
  `evaluation_settings`, `evaluation_harness` and `results_store` providers.

## Steps

Each step ends with `uv run poe check` green.

### Phase 1 — Protocol A, point forecasts

1. **Settings and record types.** Add `models.py` with `EvaluationSettings`
   (`ConfigDict(frozen=True, extra="forbid")`; validators: levels in (0, 1),
   folds divide the company count), `Protocol` and the result record.
   - *Tests:* settings validation.
2. **Splits.** Protocol A origins (the last *n* labelled origins per horizon,
   D1) and the training mask (`target_date <= origin`).
   - *Tests:* a hand-built 2-company, 12-quarter panel. Check the origin list;
     at h = 4 the mask excludes exactly the 3 rows per company whose target is
     after the origin; test rows are only those with a known target.
3. **Error scale and reconstruction.** `scale.py`.
   - *Tests:* revenue on any arm (`log_diff1`, `log_diff4`,
     `seasnaive_residual`) reconstructs the same level from the true `y`, with
     error below 1e-9. Signed targets: the error of a revenue-scaled prediction
     equals its target-space error exactly.
4. **Baselines.** Seasonal naive, seasonal naive with growth, naive and drift,
   predicted on the R5 scale. Each is also wrapped as a `Forecaster`, so it goes
   through the same path as a model.
   - *Tests:* the hand-built panel with known answers.
5. **Point metrics** (spec R7). MAE, RMSE and MASE (in-sample seasonal-naive
   scale from the training rows at the origin); MAPE on levels, revenue only;
   out-of-sample R², 1 − SSE(model) / SSE(baseline to beat) on the same rows.
   Reported per company, per sector and pooled. Asking for MAPE on a signed
   target raises rather than returning a number.
   - *Tests:* known vectors; MASE equals 1 for seasonal naive on its own
     training rows; out-of-sample R² of a forecaster against itself is 0 (A8);
     MAPE on operating income raises.
6. **Leakage assertions** (R12). Run them inside `evaluate`.
   - *Tests (A3):* a forecaster that reads test labels, and one trained with an
     `origin_date` cut-off. Both make `evaluate` raise `EvaluationLeakageError`.
7. **Harness, Protocol A.** `evaluate(forecaster, variable, arm, horizons)`:
   1. build the test set (R2);
   2. fit per origin;
   3. predict;
   4. reconstruct and scale;
   5. score;
   6. return records.

   Missing predictions are counted, not dropped (R4).
   - *Tests (A4):* a forecaster returning NaN for some rows.
8. **Results store.** `ResultsStore` with append and read. Every record carries
   the harness version, the data-freeze identifier (the backup directory name
   plus a hash of the feature files) and the git commit.
   - *Tests:* round-trip; appending twice keeps both runs.

**Checkpoint 1 (A1).** In the notebook, run the four baselines on Protocol A. The
results must reproduce the spec's baseline table to four decimals.

### Phase 2 — Intervals

9. **Conformal, Protocol A.** Rolling calibration over earlier origins (window in
   settings) with ACI level adjustment. Calibration uses only target dates on or
   before the origin. The window starts before the 16 reported origins, so the
   first reported origin already has calibration errors.

   MAPIE is not a dependency yet: `uv add mapie` (ask first; it changes
   `uv.lock`). Try MAPIE's time-series regressor first (EnbPI with partial fit). Keep it
   only if it can be fed exactly the calibration errors allowed by R8; if it
   insists on its own resampling, compute the quantiles in `conformal.py` and
   record why in the spec.
   - *Tests:* exchangeable synthetic errors reach nominal coverage. A
     calibration error dated after the origin raises.
10. **Interval metrics.** Coverage, mean width and Winkler; CRPS and pinball when
    a forecaster supplies quantiles.
    - *Tests:* known vectors.
11. **Diebold–Mariano with the HLN correction**, against the baseline to beat
    (R6, R9).
    - *Tests:* identical forecasts give a statistic of 0; a published example
      reproduces.

**Checkpoint 2 (A5).** Seasonal-naive coverage is within ±5 points of 80, 90 and
95 %, pooled over Protocol A.

### Phase 3 — Protocol B

12. **Folds and truncation.** Seeded fold assignment spread across sectors, 12 × 5.
    History cut to H; features that need more history become NaN.
    - *Tests:* folds are disjoint and cover all 60 companies; no held-out company
      is in its fold's training rows; at H = 8, `growth_yoy_lag8` is NaN.
13. **Cross-conformal** across held-out companies at the same H.
    - *Tests:* calibration never uses the company being scored.
14. **Harness, Protocol B.** `evaluate(..., protocol=B, histories=...)`.

**Checkpoint 3 (A6).** Seasonal-naive Protocol B intervals narrow from H = 8 to
all.

### Phase 4 — Notebook, thesis, freeze

15. **Notebook `02_evaluation_harness.ipynb`** (D3), orchestration only:
    1. load the frozen features;
    2. run the four baselines × four targets × h 1–4 × both protocols, twice,
       and assert byte-identical output (A2);
    3. write `results.parquet`;
    4. log the tables and figures to W&B, group `nb02-baselines-{variable}-{protocol}`.

    Figures: baseline MAE by sector and horizon; the coverage reliability
    diagram; Protocol B error against H.
16. **Renumber the playground notebooks** to the master plan (D3)
    (`02_statistical_models` → `03_statistical_models`, and so on). Update
    references in docs and notebooks.

    The mapping is not a plain +1. Converged with the thesis (`tab:notebooks`)
    on 2026-10-31; renaming files still needs a go-ahead:

    - `02_statistical_models` → `03_statistical_models`;
    - `03_ml_automl_models` splits into `04_ml_models` (linear regression and
      LightGBM) and `07_automl_models` (AutoGluon-TimeSeries);
    - `04_lstm_model` → `05_neural_models`;
    - `06_foundation_models` is new and optional;
    - `05_validation_backtest` merges into `02_evaluation_harness` and
      `08_synthesis`;
    - `06_registry_and_predict` → `09_registry_and_predict`;
    - `07_genai_qa` → `10_genai_qa`.
17. **Thesis.** Run `docs/plans/thesis-update.md`. Add a methods subsection
    (protocols, error scale, baselines, intervals) and a results section with
    the baseline table by sector. The baseline to beat per target and horizon
    becomes the reference that NB03–NB08 results are measured against.
18. **Freeze.** Set the harness version to `nb02-v1.0.0` in the settings. Then
    ask before creating the git tag; tagging needs explicit permission.

## Tests summary

New: `tests/services/evaluation/` with one module per file in the layout
table, and `tests/data/test_results_store.py`. Every test uses hand-built
panels with known answers, never the real data. The real-data checks (A1, A2,
A5, A6) are notebook assertions.

## Verification

- `uv run poe check` green after every step.
- Checkpoints 1–3 recorded here with their numbers, dated.
- A2: two runs hash-identical.
- The spec's acceptance A1–A8 ticked here before the tag.

## Risks

- **Seasonal naive with growth needs year-over-year growth at the origin.** That
  means 8 quarters of history, so under Protocol B at H = 8 it is barely
  defined. If it fails at H = 8, report it as missing (R4) rather than falling
  back silently.
- **Conformal at 16 origins is thin.** The calibration window must reach before
  the reported origins. If coverage misses A5, widen the window before changing
  the method.
- **Scope.** Phase 3 is the largest. If time is tight, D4's alternative (tag after
  Phase 2) is the fallback. Record it as a version bump, not a silent change.

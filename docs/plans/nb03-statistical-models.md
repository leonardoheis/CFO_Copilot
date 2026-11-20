# Plan — NB03 statistical models

Spec: `docs/specs/nb03-statistical-models.md` (decisions N1–N5 accepted
2026-11-19). Master plan: NB03, D5 exception, D26.

**Status: not started.**

## Before starting

- **Step 0, harness version (needs the author's approval to tag).** Since
  `nb02-v1.0.0`, four commits changed the harness: Protocol B takes a
  forecaster factory, records carry a `run_id`, and two merges validate their
  cardinality. The scoring code is untouched, but records still say
  `nb02-v1.0.0`, so they would cite code they did not run on (spec R1).
  Proposal: show that the baseline records are value-identical to the stored
  NB02 records (all columns except `run_id` and `git_commit`), then tag
  `nb02-v1.1.0` and set `EvaluationSettings.harness_version` to it. Spec R1
  then reads "the harness at `nb02-v1.1.0`".
- Frozen data only (`thesis_2026-10-30`), as NB02.
- `statsforecast` 2.1.1 is already in the dependencies.

## Layout

New service package `src/app/services/statistical/`. The notebook only
orchestrates, as in NB02.

| File | Holds |
|---|---|
| `series.py` | A company's series as one fit sees it: quarters up to the origin, the last H under Protocol B, on the fitted scale (log revenue, signed levels), interior gaps interpolated (R2, R3) |
| `models.py` | `StatisticalModel` (`ets`, `theta`, `autoarima`, `sarimax`) and the statsforecast model each one builds for a target family (R4) |
| `sarimax.py` | The three regressors lagged by h (N1, N2), order selection on the first window, fixed-order refits (R5) |
| `forecaster.py` | `StatisticalForecaster`: the `Forecaster` the harness scores (R1, R6) |
| `__init__.py` | Public names |

Also:

- `src/app/services/evaluation/viability.py`: `minimum_viable_history`, from
  pooled Protocol B metric tables (R7). It adds a report and changes no
  scoring code; NB04–NB07 reuse it.
- `src/app/data/model_store.py`: `ModelStore`, which saves and loads
  `models/trained/<notebook>/model_{family}_{variable}_h{h}.joblib` under
  `Settings.LOCAL_MODELS_DIRECTORY` (R9; local-models plan, step 5). Container
  provider `model_store`.

### How the forecaster meets the harness

The harness calls `fit(train).predict(test)` once per origin, with all 60
companies in `test` (Protocol A), or once per held-out company, origin and H
(Protocol B). Like `BaselineForecaster`, the model reads each company's own
panel, not `train`:

- `fit` learns nothing; the work is per company, inside `predict`.
- `predict` forecasts every company at the test's origin and history in one
  `StatsForecast(..., n_jobs=-1)` call, keeps the levels for h = 1 to 4 in a
  cache keyed by (origin, history), and turns the level at the task's horizon
  into the arm's target with `TargetTransformer.target_for`, as the baselines
  do. The harness converts it back to the error scale.
- The cache is shared by the four horizon tasks of one target (one fit serves
  h = 1 to 4, N5) and by Protocol B's folds (`for_fold` copies the forecaster
  and keeps the cache). Protocol B's H = all is then Protocol A's fits.
- SARIMAX caches per (origin, history, horizon): one fit per horizon (N2).
- A4's second run builds new forecasters, so nothing is reused between runs.

### Workload estimate

Each model forecasts 60 companies at about 34 origins per target (the union of
the four horizons' 31 origins), at five histories. AutoARIMA dominates: about
0.5 s per full-history fit, so about an hour per run on one core for
Protocol A. `n_jobs=-1` spreads it over the machine's 12 logical cores.
Checkpoint 1 measures the real time before the full run is started.

## Steps

Each step ends with `uv run poe check` green.

### Phase 1 — Series and the three automatic models

1. **Fitting series** (`series.py`, R2, R3). For one panel, target, origin and
   optional H: the reported quarters on or before the origin, the last H of
   them when given; log for revenue; leading unreported quarters dropped
   (before listing); interior gaps filled by linear interpolation on the
   fitted scale, with the number filled returned beside the series.
   - *Tests:* nothing after the origin is used; H keeps exactly the last H
     quarters; a gap is filled and counted; revenue comes back in logs; a
     signed series keeps its negative quarters; a gap outside the window is
     not counted.
2. **Models** (`models.py`, R4). ETS with automatic error, trend and season;
   for signed targets, additive only. Theta automatic. AutoARIMA with seasonal
   orders. All with `season_length=4`.
   - *Tests:* on a short synthetic series with negative quarters, the fitted
     ETS has no multiplicative component; each model forecasts four steps.
3. **Failure catalogue** (R6). Run the three models over every company,
   origin and H of one target in a scratch session, and record which inputs
   raise or return non-finite values. Turn each known cause into an explicit
   check that returns NaN for that company (a missing prediction). Anything
   else propagates as a bug. No `try`/`except` around a fit (CLAUDE.md, error
   handling).
   - *Tests:* one per known cause, giving NaN and a count.
4. **Forecaster** (`forecaster.py`, R1, R6). `StatisticalForecaster(model,
   panels=, task=)`, `fit`, `predict(test, history=)`, `for_fold`, the shared
   cache, and the filled-quarter and missing-prediction counts.
   - *Tests:* on a 3-company panel: one `StatsForecast` call per (origin,
     history) whatever the number of companies predicted; horizons 1 and 4
     reuse the same fit; `y_hat` round-trips through `TargetTransformer` to the
     forecast level; a company the model cannot fit gives NaN, not a baseline;
     the harness's leakage checks pass on a full `evaluate` and
     `evaluate_new_companies` run.

**Checkpoint 1 (the author runs the notebook).** ETS, Theta and AutoARIMA
through `harness.evaluate` on revenue, h = 1 and 4, all companies. Report the
pooled MAE beside NB02's baselines, the missing predictions and the run time.
Decide from the time whether the full run needs anything else before Phase 3.

### Phase 2 — SARIMAX

5. **Lagged regressors** (`sarimax.py`, N1, N2). For horizon h, the regressor
   at quarter t is the panel's value at t − h; the future values a forecast
   needs are then all on or before the origin.
   - *Tests:* at origin t, every regressor value used in fitting or
     forecasting comes from quarters on or before t (A3); at h = 1 the last
     value used is the origin's own quarter.
6. **Order selection and refits** (R5). AutoARIMA with the regressors picks
   the order once per company and target on the quarters before the first
   calibration origin (Protocol A), or per company, target and H on the first
   window (Protocol B). Each origin refits an `ARIMA` with that order, its
   constant or drift choice, and the regressors. The selected orders are kept
   for the report (R8).
   - *Tests:* the order is selected once, not per origin; the selection window
     ends before the first calibration origin; a refit with a fixed order
     reproduces AutoARIMA's forecast on the selection window.
7. **SARIMAX in the forecaster.** `StatisticalModel.SARIMAX` uses steps 5–6,
   with one fit per horizon.
   - *Tests:* as step 4, plus four fits per (origin, history), one per
     horizon.

**Checkpoint 2 (the author runs the notebook).** SARIMAX on revenue at
h = 1, Protocol A: MAE against seasonal naive and with growth, the HLN-DM
p-value, and the order distribution. This is the exit criterion on one target,
early.

### Phase 3 — Full run, reports and records

8. **Minimum viable H** (`viability.py`, R7). From pooled Protocol B tables
   of a model and of seasonal naive: the smallest H in {8, 12, 20, 40} at
   which, at every horizon, the model has no missing prediction and its MAE
   is no greater than seasonal naive's; else "none".
   - *Tests:* a table where H = 12 qualifies but 8 does not; missing
     predictions at one horizon disqualify an H; no qualifying H gives
     "none".
9. **Model store** (`model_store.py`, R9). `save` and `load` by notebook,
   family, variable and horizon. ETS, Theta and AutoARIMA serve every horizon
   from one fit, so their four files hold the same fits; the name keeps the
   master plan's rule.
   - *Test:* a save-and-load round trip under a temporary
     `LOCAL_MODELS_DIRECTORY` (local-models plan, step 5).
10. **Notebook** `03_statistical_models.ipynb`, replacing the TODO cells:
    - Setup: frozen inputs, provenance, kernel-freshness check (as NB02).
    - Filled quarters per company (R3).
    - The full run: 4 models × 4 targets × h = 1 to 4 × both protocols; twice,
      with new forecasters; `assert_frame_equal` on the records (A4).
    - Missing predictions per model, target, protocol and H (A2).
    - Exit table (R8, A5): SARIMAX against seasonal naive at h = 1, Protocol
      A, per target, with the verdict; where SARIMAX loses, its error by
      sector and the selected orders.
    - Minimum viable H per model and target (R7, A6).
    - Iterated models' error growth with h against the baselines' (N5, "to
      check").
    - Records to the results store; NB02's records re-read and compared with
      their fingerprint (A7).
    - W&B: one run per target and protocol, `nb03-statistical-{variable}-{A|B}`,
      with the NB02 tables and figures; final fits saved by the model store
      and logged as `model_{family}_{variable}_h{h}` artifacts (R9).

## Verification

- `uv run poe check` green.
- The author runs the notebook end to end. A1–A7 hold; the cells assert what
  can be asserted (A2's 1 % bound, A4, A7).
- `git diff nb02-v1.1.0 -- src/app/services/evaluation` shows only the new
  `viability.py` (or `nb02-v1.0.0` if step 0 is declined).
- `git status` shows nothing under `models/` but `README.md`.

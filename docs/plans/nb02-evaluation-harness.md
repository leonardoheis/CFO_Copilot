# Plan — NB02 evaluation harness

Spec: `docs/specs/nb02-evaluation-harness.md`. Master plan milestone M3
(hard gate before NB03).

**Status: Phase 1 done, Checkpoint 1 passed (2026-11-05). Steps 9 (conformal
intervals, normalized per company), 10 (interval metrics) and 11
(Diebold–Mariano) done 2026-11-10; Checkpoint 2 passed and step 12 (folds and
truncation) done 2026-11-11, folds changed to leave-one-company-out
2026-11-12; steps 13 (jackknife intervals) and 14 (harness, Protocol B) done
2026-11-12; Checkpoint 3 passed 2026-11-16; Phase 4 (step 15) next.** Decisions D1–D4 of the spec were confirmed on
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
| `models.py` | `EvaluationSettings`: levels 0.80/0.90/0.95, 16 origins, histories 8/12/20/40/all, the calibration window and seed. Also `Protocol` (A, B) and the result record type |
| `splits.py` | Protocol A origins and training masks; Protocol B leave-one-company-out splits and history truncation |
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
   (`ConfigDict(frozen=True, extra="forbid")`; validators: levels in (0, 1)
   and ascending, histories ascending), `EvaluationProtocol` (in `domain/`) and
   the result record.
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
6. **Leakage assertions** (R12). `check_no_look_ahead(train, test, origin)`
   checks the frames handed to `fit` and `predict`; step 7 runs it inside
   `evaluate` before every fit. The test frame has its labels (`y`,
   `target_level`) dropped, so a model cannot read them; the check refuses a
   test frame that still has them. The held-out-company rule waits for
   Protocol B (step 14), the calibration rule for step 9.
   - *Tests (A3):* an `origin_date` cut-off, test rows with labels, and test
     rows from before a training target all raise `EvaluationLeakageError`.
7. **Harness, Protocol A.** `EvaluationHarness.evaluate(forecaster, dataset,
   panels=, task=)`, one call per horizon: a forecaster is built for one
   horizon, so the notebook loops. `ForecastTask` holds the variable, arm and
   horizon, and refuses an arm the variable cannot use.
   1. build the splits (R2);
   2. per origin: check R12, fit on the training rows, predict the test rows
      without their labels;
   3. reconstruct and scale;
   4. add the baseline to beat (the baseline with the lowest MAE over the test
      rows, R6) and each company's MASE scale at the origin;
   5. score.

   It returns the baseline to beat, the scored test rows and the metric tables.
   Missing predictions are counted, not dropped (R4). Records come in step 8,
   where the harness version, data freeze and commit are known.
   - *Tests (A4):* a forecaster returning NaN for one company; a forecaster
     never sees `y` or `target_level`; the baseline to beat scores out-of-sample
     R² 0 (A8).
8. **Results store.** `ResultsStore` (`app/data/`) appends to and reads
   `data/results/`, a parquet dataset partitioned by model; each append writes
   new files. `Evaluation.records(model=, provenance=)` validates the scored
   rows as `EvaluationRecord`s; `level` is None until Phase 2 adds intervals.
   `RunProvenance` carries the harness version (in `EvaluationSettings`), the
   data freeze ([NB02 frozen inputs](../specs/nb02-frozen-inputs.md)) and the
   full git commit (`head_commit`, read from `.git`). `data/results/` is committed (decided
   2026-11-17), so later models compare against the records without re-running
   NB02; it is kept out of the Docker image.
   - *Tests:* round-trip; appending twice keeps both runs; the freeze id
     changes with a feature or consolidated panel file; the commit is read from
     a loose ref, a packed ref and a detached HEAD; every scored row becomes a
     record.

**Checkpoint 1 (A1).** In the notebook, run the four baselines on Protocol A. The
results must reproduce the spec's baseline table to four decimals.

- **Passed 2026-11-05** (`02_evaluation_harness.ipynb`): 18 of 18 MAEs match;
  revenue has 956 test rows at h = 1 and 958 at h = 4; the baseline to beat is
  seasonal naive with growth for revenue at h = 1 and seasonal naive elsewhere.
- **Finding:** at h = 1, naive and drift beat both seasonal baselines on
  operating income (0.0150 against 0.0163) and EBITDA (0.0150 against
  0.0164). R6 picked the baseline to beat among the seasonal two only, so there
  a model could beat it while still losing to naive.
- **Settled 2026-11-05:** the baseline to beat is now the best of all four
  baselines (spec R6, revised). This changes three cases: naive for operating
  income and EBITDA at h = 1, and drift for EBITDA at h = 4. The notebook's
  assertion lists them.

### Phase 2 — Intervals

9. **Conformal, Protocol A.** Rolling calibration over earlier origins (window in
   settings) with ACI level adjustment. Calibration uses only target dates on or
   before the origin. The window starts before the 16 reported origins, so the
   first reported origin already has calibration errors.

   MAPIE does not fit Protocol A (it refits its own estimator and takes
   target-space residuals), so `conformal.py` computes the quantiles; the
   reason is recorded in spec R8. No `uv add mapie`.

   - **9a. The rule.** `rolling_half_widths(errors, origins, level=, window=,
     step=)`: at origin t, the split-conformal quantile of the absolute errors
     whose target date is on or before t, from the latest `window` origins;
     ACI moves the miscoverage by `step` (`EvaluationSettings.aci_step`, 0.05)
     times the gap to every earlier interval's observed miss rate. Too few
     errors give an unbounded interval rather than a false promise.
     - *Tests:* exchangeable synthetic errors reach nominal coverage at 80, 90
       and 95 %; an error whose target is after the origin does not change
       the width (filtered by construction, so nothing to raise); ACI beats a
       static window after the errors triple; too few errors give infinity.
   - **9b. Into the harness.**
     - Refit the model at `calibration_window` + h − 1 origins before the 16
       reported ones, so the first reported origin already has errors. Those
       origins calibrate only and are never scored. On the frozen data that
       reaches back to 2017-06 (h = 1) and 2015-12 (h = 4), with all 60
       companies.
     - Normalize each error by the company's MASE scale at its origin, and
       multiply the width back by the scale at the reported origin (spec R8,
       decided 2026-11-10).
     - `Evaluation.intervals` holds one row per scored row and level, with
       `lower_scaled` and `upper_scaled`. Records become one per scored row
       and level.
     - *Tests:* calibration origins are never scored; every interval has
       finite, ordered bounds; a higher level is never narrower; width over
       MASE scale is the same for every company at an origin; records carry
       each level.
10. **Interval metrics.** Coverage, mean width and Winkler (the interval score
    of Gneiting and Raftery, 2007), per level, pooled and per sector (R8), in
    `Evaluation.interval_metrics`. As with point metrics, a missing interval
    voids its group's metrics.
    - *Tests:* known vectors; a missing interval voids only its group; the
      harness scores every level.
    - **CRPS and pinball are deferred (2026-11-10).** No forecaster supplies
      quantiles yet: `Forecaster.predict` returns `y_hat` only. Add them with
      the first quantile model (NB04 LightGBM or NB07 AutoGluon). That model
      also needs its quantiles reconstructed onto the error scale, which only
      becomes testable once one exists.
11. **Diebold–Mariano with the HLN correction**, against the baseline to beat
    (R6, R9), on the per-origin mean absolute-error difference, in
    `Evaluation.significance`. statsmodels' `diebold_mariano_test` does the
    statistics; the harness only averages per origin.
    - *Tests:* identical forecasts give a statistic of 0; at h = 1 it matches
      `scipy.stats.ttest_1samp` (the reference in place of a published
      example); two companies per origin test the same as their per-origin
      mean; one value per origin, not per row; a missing prediction voids the
      test.

**Checkpoint 2 (A5).** Seasonal-naive coverage is within ±5 points of 80, 90 and
95 %, pooled over Protocol A.

- **Passed 2026-11-11**, checked per target and h = 1–4 in NB02, after the
  calibration window went from 20 to 12 origins and the ACI step from 0.05 to
  0.2 (spec R8 has the evidence). The first settings over-covered revenue by
  up to 8.8 points. Worst cell now: free cash flow h = 4 at 80 %, +3.5.

### Phase 3 — Protocol B

12. **Folds and truncation.** Leave one company out (scikit-learn's
    `LeaveOneGroupOut` on the ticker). History cut to H; features that need
    more history become NaN.
    - *Tests:* each company is held out once; a held-out company is in none of
      its training rows and is the only one tested; the held-out companies
      test every Protocol A test row once; at H = 8, `growth_yoy_lag8` is NaN.
    - **Done 2026-11-11, folds changed 2026-11-12.** First built as 12 seeded
      folds of 5 dealt across sectors; replaced by leave-one-company-out (spec
      R3 has the evidence). `EvaluationSettings.n_folds` and the record's
      `fold` went with it: the held-out company is the record's ticker.
      `protocol_b_splits` and `truncate_history` in `splits.py`. The quarters
      each growth feature reads live beside the builder
      (`QUARTERS_READ_BY_FEATURE`), tested against the builder's own
      output. Only H = 8 blanks anything: lags 5 and 8 and the 8-quarter
      rolling mean and std; at H ≥ 12 every feature fits.
13. **Cross-conformal** across held-out companies at the same H: with one
    company per fold, the jackknife (Barber et al., 2021), not the jackknife+
    (spec R8).
    - *Tests:* calibration never uses the company being scored; other
      companies' errors whose target is after the origin never calibrate;
      exchangeable companies reach nominal coverage.
    - **Done 2026-11-12.** `jackknife_half_widths` in `conformal.py` runs
      `rolling_half_widths` once per company on the other companies' errors.
      No MAPIE (spec R8). `rolling_half_widths` now filters NumPy arrays
      instead of frames: the jackknife's 40-company coverage test went from
      23 s to under 1 s, with Protocol A's results unchanged.
14. **Harness, Protocol B.** `EvaluationHarness.evaluate_new_companies(...)`
    returns one `Evaluation` per history (8, 12, 20, 40, all).
    - **Done 2026-11-12.** One fit per company and origin serves every H; the
      held-out company's features are cut with `truncate_history`, and its
      baselines and MASE scale are recomputed from its last H quarters.
      `seasonality_regime` is dropped (spec R3). `check_held_out` (R12) runs
      before every fit. `Evaluation` gained `protocol` and `history`.
    - *Tests:* every company scored at each H; a new company is never in its
      model's training rows; the regime is never shown; only H = 8 blanks
      `growth_yoy_lag8`; with all its history a new company is scored exactly
      as under Protocol A; a short history uses its own few quarters for the
      MASE scale; records carry protocol B and H.
    - Seasonal naive on the frozen panel took about 60 s per target and
      horizon (≈ 16 min for all 16). Since 2026-11-17, 18 s: each held-out
      company is scored once on its full panel, because every value at an
      origin reads at most its last five quarters; only drift (from the
      first quarter kept, `baseline_levels(..., history=)`) and the MASE
      scale (running sums over the errors inside H) follow the history.
      Checked against the slice-per-origin version on the frozen panel: all
      16 targets × horizons, 5 histories and 60 companies agree to 2e-15.
    - **Fit isolation ([R3 and A3](../specs/nb02-evaluation-harness.md#r3--protocol-b-new-company)).**
      Accept an unfitted-forecaster factory for Protocol B and call it once
      per nonempty company/origin fold. Adapt the notebook and tests. Each
      baseline fold gets a fresh wrapper while reusing the panel-derived
      target cache across folds. Verify with an accumulating forecaster
      and a cache reuse test, then compare one frozen-data Protocol B
      evaluation against the tagged results without appending records.

**Checkpoint 3 (A6).** Seasonal-naive Protocol B intervals cover within ±5
points of each level at every H, for every target and horizon. Restated from
"narrow from H = 8 to all" on 2026-11-13 (spec A6): seasonal naive's errors are
the same at every H. The short-history scale now leans on the sector peers
(spec R8, `scale_prior_errors = 8`); the trial on the frozen panel passed for
revenue at h = 1 and every target at h = 4.

- **Passed 2026-11-16** in NB02 (15 min 43 s, with a tqdm progress bar): all
  240 cells within ±5 points; the furthest is free cash flow at H = 40,
  h = 4, 84.3 % at 80 %. Checkpoints 1 and 2 reproduced their earlier numbers
  exactly after this phase's refactors. Spec A6 and R8 record three findings:
  intervals widen as H grows (old crises inflate long-history scales),
  revenue covers least at H = 12 (k = 8 is slightly low, not tuned), and
  Protocol A's scale window is open for NB04's spec.
- The per-sector table for Protocol B (cell `898c1acb`) was added after the
  run and filled by a full Restart & Run All the same day (execution counts
  1–11, every assertion passed, Checkpoint 3 in 15 min 44 s). Spec R8 records
  it: Materials and Utilities under-cover as under Protocol A (3 companies,
  48 rows each); Technology revenue under-covers from 2025-Q1, a growth
  regime that seasonal naive cannot follow.

### Phase 4 — Notebook, thesis, freeze

15. **Notebook `02_evaluation_harness.ipynb`** (D3), orchestration only:
    1. load the frozen features;
    2. run the four baselines × four targets × h 1–4 × both protocols, twice,
       and assert byte-identical output (A2);
    3. write `results.parquet`;
    4. log the tables and figures to W&B, group `nb02-baselines-{variable}-{protocol}`.

    Figures: baseline MAE by sector and horizon; the coverage reliability
    diagram; Protocol B error against H.
    - **Built 2026-11-17, awaiting the author's run.** NB02's "Full run (A2)"
      section: provenance (the freeze id, with an assertion that
      `data/features` hashes to it; the git commit; the harness version), two
      full runs compared value for value, `results.parquet`, and one W&B run
      per target and protocol. The three figures are functions in
      `services/evaluation/figures.py`, tested. Smoke-tested on seasonal
      naive, revenue, h = 1 with W&B disabled and a temporary store: every
      cell ran, the two runs matched, 17,208 records. About 19 s per
      baseline, target and horizon, so about 20 minutes per full run.
    - **First run (commit `22774b1`) discarded.** A2 held (1,101,312
      records), but under Protocol B drift scored as a model ignored H: the
      harness blanked the features, and `BaselineForecaster` reads the panel,
      not the features. `Forecaster.predict` now takes `history`, and the
      baseline honours it as the benchmark already did. The store was deleted;
      W&B runs removed by the author.
    - **Second run (labelled `0bbce89`) discarded.** It ran in the first run's
      kernel, which still held the pre-fix modules, while `head_commit` read
      the fixed commit from disk: drift was flat again. The provenance cell now
      stops when a loaded `app` module changed after the kernel imported it
      (`modules_edited_since(CODE_LOADED_AT)`). Store deleted again.
    - **Passed 2026-11-17, commit `741affa`** (records in `490ddda`, outputs
      in `c6b3bae`). Fresh kernel; A2 held: 1,101,312 records, equal value
      for value across two runs of about 20 minutes (in-memory SHA-256
      `1ca61d95dc57…`; the parquet copy hashes differently because its dtypes
      differ, not its values). Eight W&B runs. Drift now follows H: at
      revenue h = 4 its MAE falls from 0.131 at H = 8 to 0.091 at H = 40, and
      is 0.095 with all of it; the other baselines read at most five quarters
      and are flat. The baseline to beat is unchanged from the first run;
      EBITDA h = 4 is drift by 0.7 % under A and B-all, a near-tie, and at
      h = 4 naive and seasonal naive are the same forecast. Seasonal-naive
      coverage is within −2.7 to +4.3 points in every cell (A5, A6); 9 of
      1,152 cells of the other baselines over-cover by 5–7 points.
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
    - **Done 2026-11-17.** Renamed with `git mv`; every model notebook was a
      placeholder, so nothing ran or was lost. Headers follow the master
      plan's NB03–NB10 sections; `06_foundation_models` and
      `07_automl_models` are new placeholders. The spec's D3 keeps the old
      name as history; the architecture report under
      `data/reports/architecture/` links to a pinned commit and is left as
      generated.
17. **Thesis.** Run `docs/plans/thesis-update.md`. Add a methods subsection
    (protocols, error scale, baselines, intervals) and a results section with
    the baseline table by sector. The baseline to beat per target and horizon
    becomes the reference that NB03–NB08 results are measured against.
    The methods subsection explains why there is no validation set, from
    `docs/notes/validation-set-rationale.md`, and why MASE is computed in the
    harness and R² only out of sample, from
    `docs/notes/metric-choices-rationale.md`, and why the jackknife and
    Diebold–Mariano, from `docs/notes/interval-and-significance-rationale.md`.
    Every source the first two notes cite is already in the thesis repo's
    `references.bib`; the third needs Kim et al. (2020), Diebold (2015) and
    Giacomini & White (2006) added. The NB06 row of `tab:notebooks` drops
    "opcional", and the methods gain the foundation-model entry rules from
    `docs/notes/foundation-model-selection-rationale.md` (needs TabArena,
    TabICLv2 and the TabPFN-3 report in `references.bib`).
    - **Done 2026-11-18, awaiting the author's review.** Round logged in
      `docs/plans/thesis-update.md`. Only the sources `main.tex` cites were
      added: Bühlmann & Gisler, TabICLv2, TabArena. Kim et al., Diebold (2015),
      Giacomini & White and the TabPFN-3 report stay in the notes; add them
      if the text ever cites them.
18. **Freeze.** Set the harness version to `nb02-v1.0.0` in the settings. Then
    ask before creating the git tag; tagging needs explicit permission.
    - **Version bumped 2026-11-18** (`EvaluationSettings.harness_version`).
      Not re-run: `git diff 741affa HEAD` touches no code, test, dependency
      or config file, so `nb02-v1.0.0` is the code that produced the
      committed records, which carry `nb02-v0.1.0` from before the bump.
      NB03+ compare against those records by model, not by version label.
    - **One refactor after the bump (2026-11-18), no behaviour change.**
      SonarCloud's gate on PR #7 failed on four "blocker" bugs (S5644) in
      `diebold_mariano`: a false positive on indexing `groupby(...).mean()`.
      The per-origin MAEs are now computed as two Series instead of one
      indexed frame. Old and new returned bit-identical statistics and
      p-values on 2,000 random cases (missing predictions, a forecaster
      equal to its baseline, h = 1–4), so the records stay valid.
    - **Acceptance, ticked 2026-11-18:**

      | | Evidence |
      |---|---|
      | A1 ✓ | NB02 cell 6 asserts the harness MAE equals the spec's "Facts" table to four decimals, plus the test-row counts (956, 958) and the baseline to beat; it ran clean in the `741affa` run |
      | A2 ✓ | NB02 cell `546a8d00`: two full runs equal value for value (`check_exact=True`), 1,101,312 records |
      | A3 ✓ | `test_a_training_cut_off_on_the_origin_date_is_refused`, `test_a_held_out_company_in_its_own_training_rows_is_refused`; the harness runs both checks on every split before scoring (`harness.py`, `_predictions_at` and `_held_out_predictions`) |
      | A4 ✓ | `test_missing_predictions_are_counted_not_dropped`, `test_a_missing_prediction_voids_the_groups_metrics` |
      | A5 ✓ | NB02 cell `1e95fcaf` asserts it per target and horizon, stricter than pooled: 79.5–83.5 %, 89.3–92.3 %, 94.5–96.6 % |
      | A6 ✓ | NB02 cell `d82a6a52`, every target, horizon and H (passed 2026-11-16, unchanged in the full run) |
      | A7 ✓ | The version bump above; `RunProvenance` takes it from `EvaluationSettings`, so every later record carries it with the freeze id |
      | A8 ✓ | `test_a_forecaster_against_itself_has_zero_out_of_sample_r2`; on the real run 91 of the 96 baseline-to-beat cells give R² exactly 0 and 5 (operating income, h = 1, Protocol B) give −2.2 × 10⁻¹⁶, one double-precision unit from the transform round trip. Seasonal-naive revenue MAPE at h = 1 is 0.0891 against the Facts table's 0.089 |

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

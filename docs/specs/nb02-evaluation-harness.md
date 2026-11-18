# Spec — NB02 evaluation harness

Master plan §4 (protocols), §5 (intervals), §6 NB02, §7 (metrics), milestone
M3. Plan: `docs/plans/nb02-evaluation-harness.md`.

## Problem

Every model notebook (NB03–NB07) must be scored the same way: the same test
rows, the same training cut-off, the same error scale, the same baselines. If
each notebook defines its own split or metric, the comparison in NB08 and in
the thesis means nothing. The master plan records one such mistake: comparing
errors across target definitions produced a 33 % phantom improvement in early
testing (risk register).

NB01 already delivers part of what the master plan put in NB02:

- the feature datasets, one per target and horizon;
- the look-ahead check on the features;
- the target transforms with their inverse, round-trip error below 1e-9.

So NB02 is now the **evaluation harness**: protocols, baselines, metrics,
intervals and a results store. It is frozen and tagged before any model
notebook reports a number.

## Facts

Measured 2026-10-31 on the frozen data (`data/backups/thesis_2026-10-30/`).

**Datasets.** 16 feature files (4 targets × h = 1–4), each with 4,844 origin rows
(60 companies × 81 quarters, minus Tesla's 16 pre-listing quarters). Columns:
`ticker, origin_date, target_date`, the 30 features, `target_level` and `y`.
`y` is the default target of each variable:

- revenue: the seasonal-naive residual;
- the other three: the revenue-scaled year-over-year change.

**Origins with a known target.** There are 76 at h = 1 and 73 at h = 4.

| | h = 1 | h = 4 |
|---|---|---|
| Last 16 labelled origins | 2022-Q2 → 2026-Q1 | 2021-Q3 → 2025-Q2 |
| Test rows (revenue) | 956 | 958 |

**Three of the four targets cross zero.** Non-positive quarters in the panel:

| Target | Non-positive quarters | Companies |
|---|---|---|
| Revenue | 0 of 4,847 | 0 |
| Operating income | 203 of 4,847 | 37 |
| EBITDA | 95 of 4,840 | 28 |
| FCF | 678 of 4,847 | 49 |

So the master plan's old rule, "all errors converted to log-level", works for
revenue only.

**MAPE works for revenue only, and R² on levels measures size.** Seasonal naive
at h = 1, last 16 labelled origins, all 60 companies:

| Target | MAPE median | MAPE mean | MAPE max | Test quarters with \|actual\| < 1 % of trailing revenue | R² on levels |
|---|---|---|---|---|---|
| Revenue | 0.063 | 0.089 | — | 0 | 0.981 |
| Operating income | — | 0.714 | 143.3 | 82 | 0.850 |
| FCF | — | 2.211 | 399.9 | 134 | 0.703 |

- Near-zero actuals drive the operating-income and FCF means, so MAPE is not
  reported for the signed targets.
- A naive baseline scores R² = 0.98 on revenue levels because the cross-section
  spans company sizes, not because it forecasts well.
- R² of a scaled change against its own mean is about 0 by construction.
- R² against the baseline to beat (out-of-sample R², Campbell and Thompson,
  2008) is 0 for the baseline and positive only for a model that beats it.

**Two baselines, and neither dominates.** Mean absolute error over the last 16
labelled origins, all 60 companies.

- Revenue is in log level, so 0.09 ≈ 9 %.
- The other targets are in level change divided by the trailing four-quarter
  revenue at the origin.
- "Seasonal naive" predicts the level four quarters before the target.
- "Seasonal naive with growth" also repeats the year-over-year change observed
  at the origin.

| Target | h | Seasonal naive | Seasonal naive with growth | Naive (last level) | Drift |
|---|---|---|---|---|---|
| Revenue | 1 | 0.0906 | **0.0574** | 0.0813 | 0.0810 |
| Revenue | 4 | **0.0906** | 0.1223 | 0.0906 | 0.0953 |
| Operating income | 1 | 0.0163 | 0.0182 | **0.0150** | 0.0150 |
| Operating income | 4 | **0.0170** | 0.0262 | 0.0170 | 0.0171 |
| EBITDA | 1 | 0.0164 | 0.0179 | **0.0150** | 0.0150 |
| EBITDA | 4 | 0.0172 | 0.0258 | 0.0172 | **0.0171** |
| FCF | 1 | **0.0200** | 0.0237 | 0.0269 | 0.0271 |
| FCF | 4 | **0.0209** | 0.0333 | 0.0209 | 0.0215 |

Bold marks the baseline to beat (R6). At h = 4, naive and seasonal naive make
the same forecast, and the tie goes to seasonal naive. Where two values look
equal, the unrounded MAEs decide: operating income at h = 1 is 0.01498 for naive
against 0.01503 for drift, and EBITDA at h = 4 is 0.01708 for drift against
0.01719.

At 7 companies (master plan, Appendix D) seasonal naive with growth was the
only baseline reported as "seasonal naive" (0.0400). At 60 companies it is the
better baseline only for revenue at h = 1. Revenue's default target (the
seasonal-naive residual) is built around that baseline, so a model on it starts
from the weaker baseline at h = 4.

**A training cut-off on `origin_date` leaks.** For an origin t and horizon h, the
rows with origins t − h + 1 … t − 1 have targets after t. At h = 4 that is three
rows per company, 180 rows per origin, whose labels are in the test period.

## Requirements

### R1 — One harness, one split

Every model is scored through the harness. A model supplies predictions, and the
harness alone decides training rows, test rows, the error scale and the
metrics. A model notebook never filters rows for testing.

### R2 — Protocol A (known company)

- **Origins.** For each target and horizon, the last 16 origins with a known
  target (decision D1).
- **Training rows.** A row trains a model at origin t only if its target date is
  on or before t. Every company is in training (pooled models may use all of
  them; local models use their own).
- **Test rows.** Every company's row at origin t with a known target.

### R3 — Protocol B (new company)

- **Leave one company out.** Each of the 60 companies is held out once, and
  the model trains on the other 59. A held-out company is in no training row
  of its fold. This is leave-one-out cross-validation (Müller and Guido,
  2016, ch. 5) with the company, not the row, as the unit: a row held out
  alone would leave its company's other quarters in training.
  - **Why not 12 folds of 5 (decided 2026-11-12).** The folds were to be
    spread across sectors, so a held-out company's peers stay in training as
    they would in production. Stratified group k-fold cannot do that:
    scikit-learn's `StratifiedKFold` and `StratifiedGroupKFold` refuse when
    every sector is smaller than the fold count (checked in 1.7.1 and
    1.9.1), and the largest sector has 9 companies for 12 folds. Plain
    `GroupKFold(12, shuffle=True)` ignores sectors: over 200 seeds, 67 % put
    two companies of Materials, Utilities or Energy in one fold, and 35 %
    leave one of those sectors with at most one training company.
    `StratifiedKFold(6)` keeps the small sectors but trains on 50 companies.
    Holding out one company removes the problem: every sector keeps all but
    the tested company, and training is the closest to production's 60.
  - **Cost.** 60 fits per origin instead of 12, about 5× for models trained
    on the panel. Zero-shot foundation models are not trained on it, so
    holding a company out costs them nothing.
- **History.** Each held-out company is forecast from its own history cut to
  H ∈ {8, 12, 20, 40, all} quarters before the origin. Features that need more
  history than H are missing, not imputed.
  - The cut also applies to the company's baselines (drift runs from the
    first quarter kept) and to its own MASE scale, which averages only the
    seasonal-naive errors inside those H quarters: 4 errors at H = 8 for
    revenue, 1 at h = 4 for a signed target, whose first three quarters have
    no trailing revenue to scale by. R8 blends that scale with the sector
    peers'.
  - **`seasonality_regime` is not used under Protocol B (decided
    2026-11-12).** NB01 computes it from each company's full 2006–2026
    history, which a new company does not have, so Protocol B models neither
    train nor predict with it. `sector` stays: a new company's sector is
    known on day one. Under Protocol A the same label is mild look-ahead (its
    history includes the test quarters); NB04's spec decides whether to
    recompute it per origin.
- **Origins and cut-off.** As in Protocol A, applied to the held-out company.

### R4 — Every model predicts every test row

The test rows are fixed by R2 or R3, not by the model's feature coverage. A
missing prediction counts as a failure of that model, reported as a count. Rows
are not dropped silently.

### R5 — Error scale

Errors are compared on one scale per target, the same for every model and every
target arm (decision D2):

- **Revenue:** the log level at the target date.
- **Operating income, EBITDA, FCF:** the level error divided by the company's
  trailing four-quarter revenue at the origin. This is exactly the space of the
  revenue-scaled target, so the arm's own error is already on this scale.

A model trained on any arm is first turned back into a level, then put on this
scale.

### R6 — Baselines

The harness provides four baselines, and every report includes all of them:

- seasonal naive;
- seasonal naive with growth;
- naive;
- drift.

"The baseline to beat" for a target and horizon is whichever of the four
baselines has the lowest MAE in Protocol A (bold in the table above). Seasonal
naive is still reported in
every table, which keeps master plan D6 (the seasonal baseline is mandatory and
reported even when it wins).

Revised at Checkpoint 1 (2026-11-05). The rule first chose between the two
seasonal baselines only, but at h = 1 naive and drift beat both on operating
income (0.0150 against 0.0163) and EBITDA (0.0150 against 0.0164), and drift
narrowly wins EBITDA at h = 4. These
targets are scaled by revenue, so they behave like margins: slow-moving and
only weakly seasonal, so last quarter is a better forecast than the same
quarter a year earlier. Under the old rule, a model could get a positive
out-of-sample R² while losing to "next quarter equals this quarter". Choosing
among four baselines on the test rows favours the baseline, which makes the
models look worse, never better.

### R7 — Point metrics

The metric set is shared with the thesis (master plan D25). Every metric is
computed on the R5 scale unless stated:

- MAE and RMSE;
- MASE, scaled by the company's in-sample seasonal-naive MAE on its training
  rows at that origin; under Protocol B, by that MAE blended with its sector
  peers' (R8), because a short history's own MAE can rest on one error, and
  on the frozen panel six such errors are exactly zero;
- MAPE, for revenue only, on levels;
- out-of-sample R², 1 − SSE(model) / SSE(baseline to beat) over the same test
  rows.

A zero divisor makes a metric undefined, never infinite (2026-11-13): a row
whose MASE scale is 0 (an error-free history) is left out of MASE but counts
in MAE and RMSE, and also does not calibrate an interval (R8); out-of-sample R²
against a baseline with no error at all is undefined.

Each is reported per company, per sector and pooled. A pooled number never
appears without its sector breakdown (master plan §7).

### R8 — Intervals

- At levels 0.80, 0.90 and 0.95, the harness turns a model's point errors into
  prediction intervals by conformal calibration.
- **Protocol A:** calibration uses only errors whose target date is on or before
  the origin, from a rolling window of earlier origins. Coverage is corrected
  adaptively (EnbPI or ACI).
  - **Each company's errors are normalized by its own scale (2026-11-10).**
    Each error is divided by the company's in-sample seasonal-naive MAE at its
    origin, the MASE scale of R7, which uses training rows only. The interval's
    half-width is the conformal quantile of those ratios times the company's
    scale. This is locally weighted conformal prediction (Lei et al., 2018),
    and the coverage guarantee holds because the ratios are as exchangeable as
    the raw errors.
  - Without this, one pooled width would serve all 60 companies. At h = 1,
    seasonal-naive MAE differs ×3.0–3.6 between the calmest and the most
    volatile sector, and ×4.7–6.1 between the 10th and the 90th percentile
    company. One width would be too wide for stable companies and too narrow
    for volatile ones, while pooled coverage still looked nominal.
  - Calibrating each sector separately was rejected. It leaves the ×5–6 spread
    within sectors and only about 100 errors per sector to calibrate on.
  - **Window 12 origins, ACI step 0.2 (2026-11-11).** The first settings,
    20 and 0.05, failed A5 on revenue: seasonal naive reached 87.2 % at 80 %
    (h = 1) and up to 88.8 % (h = 4). A 20-origin window keeps the 2020–2022
    errors until late 2025, while revenue errors after 2022 are about half
    as large: the half-width stayed near 1.7 × the MASE scale through
    2022–2024 against a median error near 0.45 ×. A step of 0.05 moves the
    miscoverage under one point per over-covering origin, too little over 16
    origins; Gibbs and Candès's 0.005 assumes thousands of steps.
  - Measured on seasonal naive, every target, h = 1–4 (48 pooled cells):

    | Window | Step | Cells outside ±5 | Worst over | Mean Winkler |
    |---|---|---|---|---|
    | 20 | 0.05 | 6 (all revenue) | +8.8 | 0.300 |
    | 20 | 0.10 | 4 | +7.9 | 0.296 |
    | 20 | 0.20 | 0 | +4.9 | 0.292 |
    | **12** | **0.20** | **0** | **+3.5** | **0.293** |
    | 8 | 0.20 | 0 | +2.9 | 0.291 |

    The step does most of the work (window 12 at 0.05 still gives 84.6 % at
    80 %); the shorter window drops the shock years about two years sooner and
    leaves a margin that 20 at 0.2 does not. The larger step makes widths move
    more between origins; the worst pooled under-coverage stays at −0.7.
  - These values were chosen after seeing seasonal naive's test-origin
    coverage. They are harness-wide, fixed before any model is scored, and
    apply to every model alike.
  - Per sector, some cells still under-cover by 13–18 points under every
    setting tried (Materials free cash flow, Utilities revenue at 80 %). A5
    is pooled, so this is reported as a finding, not a failure.
- **Protocol B:** calibration uses the errors of the other held-out
  companies at the same H, with Protocol A's time rule, window and ACI step.
  The interval is centred on the prediction of the model fit without the
  company: the jackknife (Barber et al., 2021), decided 2026-11-12.
  - **Not the jackknife+.** It centres on every other leave-one-out model's
    prediction, and each of those trained on the company being scored, so the
    company would no longer be unseen. A clean jackknife+ needs a model fit
    without both companies, 60 × 59 fits per origin.
  - The jackknife has no worst-case coverage guarantee (the jackknife+ has
    1 − 2α); it covers well when the model is stable. Coverage is measured,
    not assumed.
  - A production app could use the jackknife+: a genuinely new company is in
    none of the 60 models.
  - **The error scale leans on the sector peers (decided 2026-11-13).** A
    held-out company's own MASE scale rests on its few errors inside H
    quarters (1 to 4 at H = 8), too few to trust alone. Credibility weighting
    (Bühlmann and Gisler, 2005) blends it with the median full-history scale
    of its sector peers at the origin (all other companies if it is alone in
    its sector): the peers count as k = 8 errors, so at H = 8 the company's
    own errors weigh 1/9 to 4/12, and at all its history about 70/78. The
    blend scales both MASE (R7) and the interval.
  - k = 8 was fixed before measuring its effect; it is not estimated from
    the data (Bühlmann's k = within-company over between-company variance).
    The Python packages that estimate it (`credibility`, `actuarcredibility`,
    `insurance-credibility`) were checked on 2026-11-13: each is a
    single-author beta first released in 2026, with no outside contributors,
    so none is used. The mature implementation is R's `actuar`.
  - Effect on seasonal naive, 80 % coverage, own scale → blended: revenue
    h = 4 at H = 8 went from 72.2 % to 78.9 %, at H = 12 from 74.7 % to
    78.5 %; revenue h = 1 at H = 12 from 76.5 % to 78.5 %. With the own scale,
    MASE for the signed targets was undefined at H = 8, h = 4 (a zero scale
    for LMT, T, MDT and TXN). With the blend, every target at h = 4 and every
    H covers within 5 points at 80, 90 and 95 %; the furthest is free cash
    flow at H = 40, 84.3 % at 80 %.
  - **k is slightly low for revenue (2026-11-16, not acted on).** Revenue
    covers least at H = 12 (77.3–78.5 % at 80 %), not at H = 8
    (78.8–79.6 %): at H = 12 the company's own errors weigh 8/16 against
    4/12 at H = 8, so a noisy own scale counts more. It is within tolerance,
    and choosing k from these test results would tune on the test set, so
    k stays 8 and the thesis states the pattern.
  - **Per sector (Checkpoint 3, 2026-11-16).** The ten sector cells furthest
    below their level are 15 to 17.5 points under it; nine are at 80 %,
    between 62.5 % and 64.6 %, and the tenth is Materials free cash flow at
    90 % (75.0 %; corrected 2026-11-18, first recorded as "all at 80 %"):
    - **Materials** (free cash flow, operating income; 7 of the 10) and
      **Utilities** (revenue; 2): 3 companies and 48 rows each, so one missed
      quarter moves coverage by about 2 points, and the ten worst of about
      2,160 sector cells (9 sectors × 4 targets × 4 horizons × 3 levels × 5
      histories) are extreme by selection. Protocol A shows the same sectors
      at the same depth; Protocol B does not create them.
    - **Technology revenue is a regime shift, not noise** (9 companies, 144
      rows). Seasonal naive, h = 1, at 80 %: Protocol A 71.5 %; Protocol B
      75.0, 69.4, 64.6, 67.4 and 70.8 % at H = 8, 12, 20, 40 and all; at 95 %
      it covers 93.8–98.6 %. At H = 20 its misses cluster in time: about 2 of
      the 9 companies a quarter in 2022–2024, the rate an 80 % interval
      allows, then 6 to 7 a quarter from 2025-Q1 to 2026-Q1, led by ORCL
      (10 misses), MSFT (8), CSCO (8) and TXN (6). Technology revenue growth
      accelerated in 2025; seasonal naive carries no growth, and intervals
      calibrated across all sectors on calmer quarters cannot follow one
      sector's shift. The cost of rejecting per-sector calibration (above),
      stated as such. For revenue at h = 1 the baseline to beat is seasonal
      naive with growth, and NB04's growth features are the test of whether
      a model covers this regime.
- **Open for NB04's spec: Protocol A's scale window.** Protocol A scales each
  company by its seasonal-naive MAE over its whole history to date. Checkpoint
  3 shows shorter, recent histories give narrower intervals at the same
  coverage, and Protocol A over-covers most where history is longest (free
  cash flow 83.5 %, revenue 81.7 % at 80 %, h = 4). A recent window (for
  example the last 20 quarters) may sharpen Protocol A's intervals. It is not
  changed now: picking the window after these results would tune on the test
  set; NB04's spec decides it, before scoring any model.
- MAPIE (named in the thesis) is the implementation where its API fits the
  calibration rule above. Where it does not, the harness calibrates itself
  rather than bend the rule.
  - **Protocol A does not fit (2026-11-05).** MAPIE's time-series regressor
    wraps a scikit-learn estimator, refits it on its own resamples, and takes
    residuals in target space. The harness's calibration errors come from its
    own refit at each origin and exist only on the R5 scale, after
    reconstruction. So the harness computes the split-conformal quantile and
    the ACI correction itself (Gibbs and Candès, 2021), with no MAPIE
    dependency.
  - **Protocol B does not fit either (2026-11-12).** MAPIE's
    `CrossConformalRegressor` also refits a scikit-learn estimator itself,
    on its own folds; the harness's held-out errors come from its own
    leave-one-company-out refits at each origin, on the R5 scale.
- A model that produces its own interval may report it alongside, never in
  place of the conformal one.
- **Interval metrics:** empirical coverage, mean width and Winkler score,
  each reported per sector as well as pooled. Pooled coverage can sit at the
  nominal level while volatile sectors under-cover and stable ones over-cover.
- CRPS and pinball loss apply when a model supplies quantiles.
- The confidence interval of the conditional mean (master plan §5.1) is the
  model family's responsibility. The harness stores it when supplied.

### R9 — Significance

- Each model is compared with the baseline to beat using the Diebold–Mariano
  test with the Harvey–Leybourne–Newbold small-sample correction (master plan
  D22).
- The test runs on one loss difference per origin: model loss minus baseline
  loss, averaged over the companies at that origin. Companies at one origin
  share the same macro shocks, so their rows are not independent; treating the
  ~960 test rows as independent observations would overstate significance.
  With 16 origins the test has 16 observations, and its variance allows
  autocorrelation up to lag h − 1, because forecasts from consecutive origins
  overlap.
- The loss is the absolute error on the R5 scale (decided 2026-11-10): the
  baseline to beat is chosen by MAE, so the test asks whether a model beats it
  on the same loss. The corrected statistic is compared with Student's t on
  16 − 1 degrees of freedom, two-sided.
- The test is statsmodels' `diebold_mariano_test` (decided 2026-11-11), with
  `lags = h − 1`. Its Newey–West variance weights the lags with a declining
  (Bartlett) kernel, where Harvey et al. (1997) weight them equally. The
  Newey–West variance can never be negative; the equally weighted one can
  be at h > 1. At h = 1 the two coincide, and the statistic equals a
  one-sample t-test on the 16 loss differences.
- A missing prediction voids the test, as it voids the point metrics.
- The Model Confidence Set across families is NB08's job, not the harness's.

### R10 — Results store

- One record per model, target, arm, protocol, H, company, origin, horizon and
  level. Each record holds: the point prediction, the actual, both on the R5
  scale and as levels; and the interval bounds. Under Protocol B the
  held-out company is the record's own ticker, so no fold is stored.
- Each record also carries the harness version, the data-freeze identifier and
  the git commit.
- All notebooks append to the same store.

### R11 — Reproducible

- Running the four baselines twice on the frozen data gives byte-identical
  results.
- With the same seed, a model's results depend only on the data freeze and the
  harness version.

### R12 — No look-ahead

- **Training rows:** every training row's target date is on or before its origin.
- **Test rows:** every test row's origin is on or after every training row's
  target date (a row trained at origin t may have its target on t), and the
  rows a model predicts from carry no label.
- **Protocol B:** no held-out company appears in its own training rows.
- **Conformal calibration:** no calibration error comes from a target date after
  the origin.

These checks run on every evaluation, not only in tests.

## Acceptance

- **A1.** The baselines reproduce the table in "Facts" to four decimals, from the
  frozen data.
- **A2.** Two full baseline runs (both protocols, four targets, h = 1–4) write
  identical results.
  - **Passed 2026-11-17** at commit `741affa`: 1,101,312 records, equal value
    for value. Two earlier runs were discarded: one scored Protocol B drift
    on full history, the other ran pre-fix code in a stale kernel (now
    refused by the provenance cell).
- **A3.** A deliberately leaking model fails. It is trained with an
  `origin_date` cut-off, or it sees a held-out company; either way the harness
  raises before scoring.
- **A4.** A model that leaves predictions missing is reported with its missing
  count and is not scored on fewer rows than the baselines.
- **A5.** Seasonal-naive conformal intervals reach empirical coverage within ±5
  points of each nominal level, pooled over Protocol A.
- **A6.** Seasonal-naive Protocol B intervals reach empirical coverage within
  ±5 points of each nominal level, pooled, at every H (8, 12, 20, 40, all).
  - **Restated 2026-11-13.** It first read "Protocol B intervals narrow as H
    grows from 8 to all". Seasonal naive cannot show that: its forecast, last
    year's same quarter, is identical at every H, so its errors are too. Only
    the error scale changes with H, and with the own scale the 80 % interval
    at h = 1 was narrowest at H = 8 (0.322 against 0.340 at all) while
    covering 78 %. Narrowing with H is a property of models that learn from a
    company's history; it is checked from NB04 on (master plan §5.4), not
    here.
  - **Passed 2026-11-16** (NB02, 16 targets × horizons, 15 min 43 s). All 240
    cells (4 targets × 4 horizons × 3 levels × 5 histories) cover within ±5
    points. At 80 %: operating income 79.5–81.7 %, EBITDA 79.1–81.3 %, free
    cash flow 80.1–84.3 %, revenue 77.3–82.2 %; at 95 %, 93.1–97.2 % overall.
    The furthest cell is free cash flow at H = 40, h = 4: 84.3 % at 80 %.
  - **Finding: intervals widen as H grows**, at about the same coverage.
    80 % width, H = 8 against all: revenue h = 1 0.289 against 0.333
    (+15 %), free cash flow h = 4 0.064 against 0.077 (+19 %), operating
    income h = 1 0.044 against 0.045. A full history includes 2008 and 2020,
    which inflate the average error; a short one sees only recent, calmer
    years, and the peers' median resists old crises. Recent errors describe
    current uncertainty better than all-time averages.
- **A7.** The harness is versioned `nb02-v1.0.0`. After that, NB03–NB08 record
  this version and the data-freeze identifier on every run.
  - **Done 2026-11-18.** The committed NB02 records predate the bump and carry
    `nb02-v0.1.0`; the code is unchanged since they were produced (`741affa`).
- **A8.** For every baseline, out-of-sample R² against itself is exactly 0, and
  the revenue MAPE of seasonal naive at h = 1 reproduces the "Facts" table.
  - **Passed 2026-11-18**, to machine precision: 91 of 96 cells give exactly
    0 and 5 give −2.2 × 10⁻¹⁶ (operating income, h = 1, Protocol B), one
    double-precision unit. MAPE: 0.0891 against 0.089.

A1, A3–A6 passed as well; the evidence for each is in the plan, step 18.

## Out of scope

- Model families (NB03 onward).
- Hyperparameter search. When it comes, it runs inside the training rows of
  each origin (risk register).
- The Model Confidence Set, policy table and routing (NB08).
- Macro vintages (master plan O4).

## Decisions

Confirmed 2026-10-31: the default of each, D1–D4.

- **D1 — Origins.** Default: the last 16 labelled origins per horizon (above).
  - *Alternative:* one shared set of origins for all horizons (2021-Q3 →
    2025-Q2). Horizons become comparable origin by origin, but h = 1 loses its
    three most recent quarters.
- **D2 — Error scale for signed targets.** Default: the level error over the
  trailing four-quarter revenue at the origin.
  - *Alternative:* MASE only. It is scale-free, but the denominator is noisy for
    companies whose seasonal-naive error is small.
- **D3 — Notebook numbering.** The master plan's NB02 is this harness and NB03
  is statistical models, but the playground file is
  `02_statistical_models.ipynb`. Default: add `02_evaluation_harness.ipynb` and
  renumber the playground files to follow the master plan.
  - *Alternative:* keep the file names and call the harness NB02a.
  - *Converged 2026-10-31* with the thesis (`tab:notebooks`): NB02 harness,
    NB03 statistical, NB04 ML on features, NB05 neural, NB06 foundation models
    (optional), NB07 AutoML, NB08 synthesis and final ensemble, NB09 registry,
    NB10 GenAI Q&A. The model roster is master plan D26.
- **D4 — Scope before the tag.** Default: Protocol A, point metrics and
  baselines first; then intervals; then Protocol B. The tag waits for all three,
  as the master plan requires.
  - *Alternative:* tag after Protocol A and start NB03. This is faster, but
    NB03's interval and cold-start results would need a re-run under the next
    version.

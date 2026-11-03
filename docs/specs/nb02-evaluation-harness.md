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

| Target | h | Seasonal naive | Seasonal naive with growth | Naive (last level) |
|---|---|---|---|---|
| Revenue | 1 | 0.0906 | **0.0574** | 0.0813 |
| Revenue | 4 | **0.0906** | 0.1223 | 0.0906 |
| Operating income | 1 | **0.0163** | 0.0182 | — |
| Operating income | 4 | **0.0170** | 0.0262 | — |
| EBITDA | 1 | **0.0164** | 0.0179 | — |
| EBITDA | 4 | **0.0172** | 0.0258 | — |
| FCF | 1 | **0.0200** | 0.0237 | — |
| FCF | 4 | **0.0209** | 0.0333 | — |

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

- **Folds.** The 60 companies form 12 folds of 5. Assignment is seeded,
  deterministic and spread across sectors. A held-out company is in no
  training row of its fold.
- **History.** Each held-out company is forecast from its own history cut to
  H ∈ {8, 12, 20, 40, all} quarters before the origin. Features that need more
  history than H are missing, not imputed.
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

"The baseline to beat" for a target and horizon is whichever of the two seasonal
baselines has the lower MAE in Protocol A. On the frozen data that is the one in
bold in the table above. This keeps master plan D6 (the seasonal baseline is
mandatory and reported even when it wins), without picking the weaker one by
name.

### R7 — Point metrics

The metric set is shared with the thesis (master plan D25). Every metric is
computed on the R5 scale unless stated:

- MAE and RMSE;
- MASE, scaled by the company's in-sample seasonal-naive MAE on its training
  rows at that origin;
- MAPE, for revenue only, on levels;
- out-of-sample R², 1 − SSE(model) / SSE(baseline to beat) over the same test
  rows.

Each is reported per company, per sector and pooled. A pooled number never
appears without its sector breakdown (master plan §7).

### R8 — Intervals

- At levels 0.80, 0.90 and 0.95, the harness turns a model's point errors into
  prediction intervals by conformal calibration.
- **Protocol A:** calibration uses only errors whose target date is on or before
  the origin, from a rolling window of earlier origins. Coverage is corrected
  adaptively (EnbPI or ACI).
- **Protocol B:** calibration uses the errors of the other folds' held-out
  companies at the same H.
- MAPIE (named in the thesis) is the implementation where its API fits the
  calibration rule above. Where it does not, the harness calibrates itself
  rather than bend the rule.
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
- The Model Confidence Set across families is NB08's job, not the harness's.

### R10 — Results store

- One record per model, target, arm, protocol, H, company, origin, horizon and
  level. Each record holds: the point prediction, the actual, both on the R5
  scale and as levels; the interval bounds; and the fold.
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
- **Test rows:** every test row's origin is after every training row's target
  date.
- **Protocol B:** no held-out company appears in its fold's training rows.
- **Conformal calibration:** no calibration error comes from a target date after
  the origin.

These checks run on every evaluation, not only in tests.

## Acceptance

- **A1.** The baselines reproduce the table in "Facts" to four decimals, from the
  frozen data.
- **A2.** Two full baseline runs (both protocols, four targets, h = 1–4) write
  identical results.
- **A3.** A deliberately leaking model fails. It is trained with an
  `origin_date` cut-off, or it sees a held-out company; either way the harness
  raises before scoring.
- **A4.** A model that leaves predictions missing is reported with its missing
  count and is not scored on fewer rows than the baselines.
- **A5.** Seasonal-naive conformal intervals reach empirical coverage within ±5
  points of each nominal level, pooled over Protocol A.
- **A6.** Protocol B intervals narrow as H grows from 8 to all. If they do not,
  the calibration is wrong (master plan §5.4) and the harness is not frozen.
- **A7.** The harness is versioned `nb02-v1.0.0`. After that, NB03–NB08 record
  this version and the data-freeze identifier on every run.
- **A8.** For every baseline, out-of-sample R² against itself is exactly 0, and
  the revenue MAPE of seasonal naive at h = 1 reproduces the "Facts" table.

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

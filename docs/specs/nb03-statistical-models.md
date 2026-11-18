# NB03 — Statistical models

## Problem

The thesis commits to ARIMA/SARIMA (decision D26). NB03 scores the classical
per-company models (ETS, Theta, AutoARIMA with seasonal orders, and SARIMAX
with macro regressors) through the frozen NB02 harness (`nb02-v1.0.0`), on
the four targets and both protocols. These are the first models that have to
beat the NB02 baselines.

Exit criterion (master plan, NB03): **SARIMAX beats seasonal naive on
Protocol A at h = 1, or a documented reason why not.**

## Facts

Measured on the frozen data (`thesis_2026-10-30`, 60 companies, 81 quarters
each), 2026-11-18.

- **History.** Every company has 74 to 81 reported quarters of each target
  (median 81), so every Protocol B history H ∈ {8, 12, 20, 40, all} exists
  for every company.
- **Interior gaps.** Seven companies have 1 to 3 unreported quarters inside a
  series: ABT, BBY, BMY, HON and OXY 1 each, TSLA 3, and F 2 (EBITDA only).
  ARIMA and ETS need a gap-free series.
- **Signed targets.** Quarters at or below zero, of 60 companies and about
  4,860 company-quarters:

  | Target | Companies with at least one such quarter | Such quarters, all companies |
  |---|---|---|
  | Revenue | 0 | 0 |
  | Operating income | 37 | 203 |
  | EBITDA | 28 | 95 |
  | Free cash flow | 49 | 678 |

  The extreme is DUK's free cash flow: 58 of 81 quarters at or below zero.
- **Macro.** The ten macro columns (D24) have no missing values.
- **statsforecast 2.1.1** (`season_length=4`), timed on one series each:

  | Model | Full history | H = 8 to 12 |
  |---|---|---|
  | AutoETS | 10 to 46 ms | 5 ms |
  | AutoTheta | 3 to 13 ms | under 2 ms |
  | AutoARIMA | 330 to 630 ms | 60 to 120 ms |
  | AutoARIMA + 3 regressors | 1,660 ms | — |
  | ARIMA, fixed order + 3 regressors | 47 ms | — |

  All three automatic models fit DUK's free cash flow at every H from 8 to
  all. AutoETS refuses a 4-quarter series ("tiny datasets"). Its smallest
  working length was not searched for: Protocol B's smallest H is 8.
- **Workload.** Protocol A refits at 31 origins per target at h = 4 (16
  reported, 12 calibration, 3 to cover the horizon): 60 × 31 = 1,860 fits per
  model and target if one fit serves h = 1 to 4. Protocol B adds four
  truncated histories, four times that again.
- **The baselines to beat** (NB02, Protocol A, MAE on the error scale): revenue
  0.0574 at h = 1 (seasonal naive with growth) and 0.0906 at h = 4 (seasonal
  naive). Seasonal naive alone is 0.0906 at h = 1 for revenue, 0.0163
  operating income, 0.0164 EBITDA, 0.0200 free cash flow.

## Requirements

### R1 — Through the frozen harness

Every model is scored by the NB02 harness at `nb02-v1.0.0`, unchanged:
splits, error scale, metrics, conformal intervals and the results store. A
model supplies one point forecast per test row and nothing else. The records
carry the harness version, the data freeze and the commit.

### R2 — Per-company fits, on the error scale's series

- Each model fits one company's own series, never other companies' quarters
  (they are local models, NB02 R2).
- Revenue is fitted in logs, the scale its errors are measured on (D4, NB02
  R5); the forecast is turned back into a level. Signed targets are fitted in
  levels: their zero and negative quarters rule out logs and multiplicative
  error, trend or season.
- Seasonal period 4 for every model.
- A fit uses only quarters before its origin. Under Protocol B, only the last
  H of them.

### R3 — Gaps

A gap inside the fitted window is filled for fitting only, by linear
interpolation on the fitted scale (log revenue, signed levels). Filled
quarters are never scored and never become test rows. The number of filled
quarters per company is reported.

### R4 — The models

| Model | Specification |
|---|---|
| ETS | Automatic error, trend and season selection by AICc; additive only for signed targets |
| Theta | Automatic Theta variant |
| AutoARIMA | Automatic (p, d, q)(P, D, Q)₄ selection |
| SARIMAX | AutoARIMA's order, plus macro regressors (R5) |

ETS, Theta and AutoARIMA forecast h = 1 to 4 from one fit per origin (the
iterated forecast these models define). That departs from D5 (direct, one
model per horizon), which was written for the pooled ML models.

### R5 — SARIMAX regressors

- **Set (proposed).** `gdp_yoy`, `cpi_yoy` and `fed_funds`: demand, prices
  and rates, one each. Ten regressors on about 75 quarters would leave too
  few degrees of freedom for a per-company model. Choosing per sector from
  NB01's macro heatmap would select on the test period, because NB01 read the
  full history.
- **No future macro.** At horizon h the regressor at quarter t is its value
  at t − h, so every value the forecast needs is known at the origin. Each
  horizon therefore has its own fit.
- **Order chosen once.** The ARIMA order is chosen once per company and
  target, by AutoARIMA with the regressors, on the quarters before the first
  calibration origin. Each origin then refits only the coefficients (about
  47 ms against 1.7 s). Under Protocol B the order is chosen per company,
  target and H, on the first window, so a new company never borrows an order
  from its full history.
- The macro columns are final revised values (D13); the look-ahead that
  implies is stated with the results.

### R6 — Every test row gets a forecast

A fit that fails or returns a non-finite value is a missing prediction (NB02
R4): counted per model, target, protocol and H, never dropped silently, never
replaced by a baseline.

### R7 — Minimum viable history (Protocol B)

For each model and target, the minimum viable H is the smallest
H ∈ {8, 12, 20, 40} at which, at every horizon:
1. the model predicts every test row (R6); and
2. its pooled MAE is no worse than seasonal naive's at the same H.

If no H qualifies, the result is "none", stated as such.

### R8 — Exit

Protocol A, h = 1, for each target: SARIMAX's pooled MAE against seasonal
naive's, with the HLN-corrected Diebold–Mariano test (NB02 R9). SARIMAX
"beats" seasonal naive when its MAE is lower and the one-sided p-value is
below 0.05. Revenue is also compared with its baseline to beat, seasonal
naive with growth (0.0574). Where SARIMAX does not beat seasonal naive, the
reason is shown with evidence, for example the error by sector or the
selected orders.

### R9 — Records and tracking

The records go to the NB02 results store (one partition per model), with the
same W&B layout as NB02 (one run per target and protocol). Each family's
final fit, at the last reported quarter for every company, is saved under
`models/trained/nb03/` with the master plan's artifact name and logged to W&B.

### R10 — Reproducible

Two runs give identical records. These models have no random seed; A4
checks that their selection is also free of other run-to-run variation.

## Acceptance

| # | Check |
|---|---|
| A1 | All four models have records for both protocols, the four targets, h = 1 to 4, and every H |
| A2 | Missing predictions are reported per model, target, protocol and H, and are under 1 % of test rows for ETS, Theta and AutoARIMA |
| A3 | A run against the leakage checks passes: no fit sees a quarter on or after its origin, and no regressor value after the origin |
| A4 | Two runs give identical records |
| A5 | R8's comparison is reported for the four targets, with the verdict and, where SARIMAX loses, its reason |
| A6 | R7's minimum viable H is reported for each model and target |
| A7 | The baseline records from NB02 are unchanged |

## Out of scope

- Model-native intervals (analytic state-space, `se_mean`). The harness's
  conformal intervals score every model alike. Native intervals can be
  compared in NB08.
- Pooled or hierarchical statistical models, and regressors chosen per
  sector.
- Forecasting the macro regressors themselves.

## Decisions

- **2026-11-18:** statsforecast 2.1.1, as D26 names, added to the
  dependencies.
- **Proposed, for review:** the three regressors (R5), lagging them by h
  (R5), interpolating gaps for fitting (R3), and the definition of minimum
  viable H (R7).

# Spec — Ljung-Box tests the d-th difference

Wave 2, item O4 (`docs/plans/code-smells-wave-2.md`).

## Problem

The diagnostics pick a differencing order d per company and variable by
differencing once per order until ADF and KPSS agree the series is stationary.
The Ljung-Box test is meant to run on that same stationary series. Instead it
differences once **at lag d**: for d = 2 it tests \(y_t - y_{t-2}\), not
\(\Delta^2 y_t = y_t - 2y_{t-1} + y_{t-2}\). For d = 0 and d = 1 the two are
the same.

## Evidence

Measured 2026-10-27 from `data/processed/panel_long.parquet` through the
container, with NB01's inputs and settings (60 companies, Ljung-Box lag 8,
significance 0.05, forecastable bar 50%).

| Target | d = 0 | d = 1 | d = 2 |
|---|---|---|---|
| revenue_usd_m | 3 | 39 | **18** |
| ebitda_usd_m | 8 | 43 | **9** |
| operating_income_usd_m | 8 | 40 | **12** |
| free_cash_flow_usd_m | 14 | 38 | **8** |

- **47** series have d = 2; for the other 193 the p-values are identical both
  ways (largest difference 0.0).
- All 47 are significant both ways. The largest p-value under the correct
  difference is COP revenue, **0.0102** (now 2.1e-05); the largest now is NFLX
  free cash flow, 0.0027.
- The forecastable decision is unchanged for every target:

| Target | Significant now | Significant, d-th difference | Verdict |
|---|---|---|---|
| revenue_usd_m | 52 / 60 (87%) | 52 / 60 (87%) | forecastable |
| ebitda_usd_m | 54 / 60 (90%) | 54 / 60 (90%) | forecastable |
| operating_income_usd_m | 51 / 60 (85%) | 51 / 60 (85%) | forecastable |
| free_cash_flow_usd_m | 57 / 60 (95%) | 57 / 60 (95%) | forecastable |

## Required behaviour

1. Ljung-Box runs on the series differenced d times at lag 1, the same series
   the stationarity tests accepted.
2. d = 0 tests the series as it is.

## Acceptance criteria

- A test: for a d = 2 series, the reported p-value equals Ljung-Box on the
  twice-differenced series and differs from Ljung-Box on the lag-2 difference.
- NB01's forecastable rows are unchanged (expected from the evidence).
- NB01's diagnostics table changes only in `ljung_box_p`, only for the 47
  d = 2 series.

## Reruns

NB01, for the corrected `ljung_box_p` column. No re-ingest; no decision
changes.

## Out of scope

- The choice of lag 8, and whether d should come from levels or logs.

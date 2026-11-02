# Spec — Target transform comparison (master plan O1, NB01b)

Plan: [`docs/plans/transform-comparison.md`](../plans/transform-comparison.md).
Related: [`eda-actionable-framework.md`](eda-actionable-framework.md) (F3, R10).

## Problem

NB01 and the exported features transform each forecast target by a fixed rule
(EDA spec F3): revenue by logs (the three log arms, default
`seasnaive_residual`), operating income, EBITDA and free cash flow by the
revenue-scaled year-over-year change. The master plan lists for NB01 a
transform comparison that was never run: "log vs sqrt vs Box-Cox vs per-sector,
on variance stability and residual normality" (O1). Without it, both choices
are assumptions, not findings. The comparison covers the four targets of the
master plan (§ 3.3), like NB01.

## Evidence

- **Box-Cox λ varies widely across companies.** NB01's diagnostics estimate a
  maximum-likelihood λ for each company's revenue (run of 2026-10-09): median
  0.19, interquartile range −0.21 to 0.90, from −2.24 (BBY) to 4.02 (VZ). 16
  companies are within ±0.25 of 0 (log-like), 10 between 0.25 and 0.75
  (square-root-like), 19 above 0.75 and 15 below −0.25. Sector medians range
  from −0.19 (Utilities) to 1.0 (Consumer Defensive). No single λ is obviously
  right, so the comparison is needed.
- **Maximum-likelihood λ makes the level look normal, not the change.** A
  trending series pulls λ around, so λ alone does not answer O1: each candidate
  is scored on the series the model actually sees.
- **Three targets cannot take the master plan's candidates.** Operating income
  is zero or negative in 204 quarters of 37 companies, EBITDA in 96 of 28 and
  free cash flow in 678 of 49. Log, square root and Box-Cox are undefined there,
  so these targets are compared with transforms defined for signed values.

## Required behaviour

**T1. Candidates, by family.**

- **Revenue** (positive in every quarter): none, log, square root, Box-Cox with
  each company's own λ, and Box-Cox with its sector's λ. Box-Cox with λ = 0 is
  the log. **Baseline: log.**
- **Operating income, EBITDA, free cash flow** (signed): none; the
  revenue-scaled value (the variable divided by its trailing four-quarter
  revenue, whose year-over-year change is the target the models learn);
  inverse hyperbolic sine; Yeo–Johnson with each company's own λ, and with its
  sector's λ. Inverse hyperbolic sine and Yeo–Johnson are applied to the
  variable divided by the median of its absolute value, so they do not depend
  on the currency unit. **Baseline: revenue-scaled.**

A fitted λ is the maximum-likelihood λ; a sector's λ is the median of its
companies' λs.

**T2. Same series as NB01.** Each company's series is prepared exactly as in
NB01's diagnostics: interior gaps of one quarter filled for diagnosis only, the
run after the last longer gap kept, at least 16 quarters required for every
candidate of the company.

**T3. Variance stability.** On each transformed series, take the seasonal
difference (lag 4: the change the models learn). Over rolling 8-quarter
windows, measure the Spearman correlation between the company's mean revenue
(its size) and the standard deviation of the seasonal difference. Its absolute
value is the *level dependence*: near 0, the size of the changes does not
depend on the size of the company; lower is better. Revenue measures size for
every target, because a variable that crosses zero has no size of its own.

**T4. Residual normality.** Fit a robust STL (period 4) to each transformed
series and score its remainder: Jarque–Bera statistic and p-value,
Anderson–Darling statistic, skewness and excess kurtosis. Lower statistics are
closer to normal. Jarque–Bera decides; Anderson–Darling, which weighs the
whole distribution and its tails instead of two moments, is the second opinion.

**T5. Summary, per target and transform.** Companies scored, median level
dependence, median Jarque–Bera and Anderson–Darling statistics, median absolute
skewness, median excess kurtosis, share of companies whose remainder passes
Jarque–Bera at 5%, and the share of companies in which the transform *beats the
baseline*: lower level dependence **and** lower normality statistic, once with
Jarque–Bera and once with Anderson–Darling. The same medians by sector.

**T6. Decision rule, fixed before the run.** Each target keeps its baseline
unless another candidate beats it, in the sense of T5 with Jarque–Bera, in more
than half of the companies. The decision is reported again with
Anderson–Darling; a disagreement is recorded, not resolved by tuning. The
baselines are the defaults because they invert exactly into the targets the
models learn (log growth rates; changes per unit of revenue); a fitted λ would
also have to be stored and inverted for every company.

**T7. Reproducible and logged.** The comparison is a tested service in
`app.services.diagnostics`; the notebook only orchestrates (EDA spec R10). Each
target logs its table, summary and figure to its own W&B run
(`nb01b-transforms-{variable}`).

## Acceptance criteria

| # | Check |
|---|---|
| B1 | For each target, every company whose candidates all have at least 16 quarters has one row per candidate (60 × 5 for revenue on today's panel) |
| B2 | Tests: Box-Cox with λ = 0 equals the log; on revenue whose swings grow with its level, log has a lower level dependence than no transform; on a signed variable whose swings grow with revenue, the revenue-scaled value has a lower level dependence than no transform; a sector λ is the median of its companies; a series under 16 quarters is left out; the decision keeps the baseline unless a candidate beats it in more than half of the companies, on both criteria |
| B3 | The decisions and their numbers are recorded in NB01b, in NB01's summary (open question 6) and in the thesis |

## Out of scope

- Transforming features; only the targets are compared.
- Forecast accuracy: the transforms are compared on statistical properties here;
  the target arms are compared on out-of-sample error in the evaluation harness.

## Decisions taken by default — confirm or override

| # | Decision | Reason |
|---|---|---|
| D1 | Window of 8 quarters for T3 | Two seasonal cycles, the same span as the 8-quarter rolling features |
| D2 | "Beats the baseline" needs both criteria, in more than half of the companies | A transform better on one criterion and worse on the other is a trade-off, not an improvement |
| D3 | Sector λ is the median of company λs | The median resists the extreme λs (−2.24, 4.02) |
| D4 | Size is measured by revenue for every target | A signed variable's own level is not a size; revenue is what the revenue-scaled target divides by |
| D5 | Jarque–Bera decides, Anderson–Darling is the second opinion | Jarque–Bera scores the skewness and kurtosis that make these series hard; on revenue, Anderson–Darling agrees least with it in ranking transforms (0.44 against 0.75 for D'Agostino–Pearson), so it is the most independent check |

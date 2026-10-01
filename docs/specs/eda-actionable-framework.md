# Spec — An actionable EDA and feature framework for NB01

Extends [`eda-feature-engineering.md`](eda-feature-engineering.md), whose
loader, diagnostics, transforms, feature builder, leakage check and export stay
as built. This spec reorganises NB01 so it **starts with an automated profile**
and **ends with decisions**, following the eight-step framework in
"Exploratory Data Analysis (EDA) Best Practices: A Step-by-Step Framework
Using Modern Visualization Tools" (A. Whaval, Medium, 2026). Decisions below come from the grilling session of
2026-09-30 (Q1–Q26).

## Problem

NB01 runs, but its output does not drive any decision:

- Against the article's eight steps, NB01 covers parts of 1 (load), 3 (numeric),
  5 (correlations) and 7 (time). It skips **2 (the target)**, **6 (segments
  against the target)** and **8 (findings and next steps)**, so it ends in
  tables, not decisions.
- Feature engineering only writes files. Nothing shows whether a feature
  carries signal, is redundant, or is mostly missing.
- Only revenue can be forecast, although a CFO forecasts cost and cash too.
- Data defects surface as crashes (COP's negative revenue raised during feature
  building) instead of as findings.

## Scope

In: NB01's structure and content; the services it calls; the selectable target
variables; exports and W&B runs per variable.

Out: model training and evaluation, SHAP, the rolling-origin harness (master
plan NB02); fixing ingestion defects ([`ingestion-defects-cop-ge.md`](ingestion-defects-cop-ge.md));
plotly.

## Evidence

All counts on the NB00 panel without COP: 59 companies, 4,779 reported quarters.

| Variable | Non-positive rows | Companies affected | Nature |
|---|---|---|---|
| revenue | 0 | 0 | positive |
| gross profit | 26 | 11 | genuine (e.g. BA 2019–2020 charges) |
| opex | 92 | 15 | 62 are LMT (correct data), 12 are GE (defect), 18 scattered |
| EBITDA | 114 | 31 | genuine, signed |
| free cash flow | 661 | 48 | genuine, signed |

- Opex is 29.8% of revenue at the median company; LMT's is −0.3% (costs booked
  in cost of sales), the next lowest SLB at 3.7%.
- Opex ≈ gross profit − operating income holds within 10% in 91% of quarters
  for healthy companies and 98% for LMT.
- ydata-profiling on the pooled panel: 40 MB and 70 s with pairwise
  interactions; **2.9 MB and 14 s** without, keeping overview, per-column
  statistics, correlations, missing-value maps and alerts.
- Revenue diagnostics of the current NB01 (59 companies): 38 need one
  difference on levels and logs; seasonal strength spans 0.00–0.97 (median
  0.30); 90% have Ljung-Box p < 0.05; three regimes of 31 / 4 / 24 companies.

## Required behaviour

**F1. NB01 runs in this order**, each section a question the section answers:

| § | Section | Article step |
|---|---|---|
| 0 | Automated profile | 1 (tool tip) |
| 1 | Audit: data dictionary and outlier register | 1 |
| 2 | Target | 2 |
| 3 | Numeric distributions | 3 |
| 4 | Categorical | 4 |
| 5 | Correlations and redundancy | 5 |
| 6 | Segments against the target | 6 |
| 7 | Time: stationarity, seasonality, trend | 7 |
| 8 | Features: build, audit, export | — |
| 9 | Summary and decision table | 8 |

Every plot is preceded by the question it answers and followed by the answer,
in markdown (article Step 8 best practice). Plots use seaborn, styled as the
article's figures.

**F2. One target variable per run.** A single parameter at the top of NB01
selects the forecast target from: revenue, gross profit, opex, EBITDA, free
cash flow. Sections 0–1 and 3–5 cover the whole panel whatever the choice;
sections 2 and 6–9 and report (c) of F4 cover the selected variable.

The decision table comes last because its feature-group rule (F14) needs the
feature audit (F13); the confirmed order had them the other way round, which
could not work.

**F3. Each variable has one target transform, chosen by its data:**

- **revenue** keeps the three log arms of R5 (it has no non-positive value);
- **gross profit, opex, EBITDA, free cash flow** use the **revenue-scaled
  year-over-year change**: the change against the same quarter a year earlier,
  divided by the company's trailing four-quarter revenue at the origin. It is
  defined for negative values, comparable across company sizes, and exactly
  invertible back to a level.

The growth features of groups L and R are built from the selected variable's
own transform. The other groups are the same for every variable.

**F4. The automated profile comes first** and produces three ydata-profiling
reports, pairwise interactions off, each logged to W&B as an HTML panel in its
own run and kept under the data directory's `reports/`:

- (a) the pooled panel, every column but the date;
- (b) a drift comparison: quarters before 2020 against 2020 onward;
- (c) the exported feature dataset of the selected variable (in § 8).

**F5. Every company-value column gets an outlier register** (financial,
market and derived columns; macro columns are the same for every company).
Each quarter's change is made **relative to size** so a company's growth over
20 years does not read as outliers: percent change for columns that must be
positive (revenue, stock price, market cap), the plain change for ratios
(margins, dividend yield, P/E, EPS), and the change divided by trailing
four-quarter revenue for the other signed lines. A quarter is registered when
its **robust z-score** — distance from the company's median change in units of
its median absolute deviation (MAD) — exceeds 10, or when a column that must
be positive is not. Each entry also carries a **Hampel z-score**, the same
distance against a rolling 8-quarter median and MAD (floored at a quarter of
the company's overall MAD so a calm window cannot divide by near zero), which
shows when a quarter is unusual for its period. P/E is left out: it is
derived from stock price and EPS, which are registered themselves, and a
near-zero EPS (UNH 2025-Q4: 0.02) sends it to five digits (D11). Entries are ranked most extreme
first and name ticker, quarter, column, value, relative change, both scores
and direction. The register records; it changes no value.

**F6. The data dictionary is computed:** per column its type, share missing,
unique values, minimum, maximum, invalid-sign count and register count.

**F7. The target section** shows, per arm and horizon, the distribution of the
target, its skewness and kurtosis, the share of rows with a known target, and
the target's register entries (F5's rule applied to the target).

**F8. Numeric distributions are of year-over-year change, not levels** (pooled
levels only show company size), with skewness and kurtosis per column. Positive
columns use the log change, signed columns the revenue-scaled change of F3.

**F9. Correlations are Spearman correlations of year-over-year change** across
the financial and macro columns (levels correlate spuriously through shared
trends), shown as an annotated heatmap, with every pair above |ρ| = 0.85
listed as redundant.

**F10. The target is compared across three segments:** sector, seasonality
regime, and period (before the covid flag, the flagged covid quarters, after
them), as box plots and a
table of medians and spreads per segment.

**F11. The time section** keeps the R2–R4 diagnostics and adds a seasonal
profile per regime (mean target by calendar quarter) and a timeline of the
panel-median target with covid and structural-break quarters shaded.

**F12. Categoricals** are counted per sector and per regime; any sector with
fewer than 3 companies is flagged, since F10 compares segments.

**F13. The feature section audits what it exports:** per feature its share
missing, its Spearman correlation and mutual information with the target, the
pairs above |ρ| = 0.85, and a summary per feature group; features are ranked by
mutual information in one chart.

**F14. NB01 ends with a decision table, one per variable.** Each row is a
finding, its evidence, the action and where the action applies. It covers five
decision types, each by an explicit rule (thresholds in Decisions D3–D6):

| Decision | Rule |
|---|---|
| Target transform | F3 |
| Exclusions | companies excluded by an ingestion spec, and companies whose target has register entries flagged by F5's sign rule |
| Feature groups | a group whose best feature's mutual information is below the floor is a drop candidate |
| Pooled or segmented | when the target differs across regimes (Kruskal-Wallis p < 0.05), the regime feature is kept and per-regime models are named as an option |
| Forecastable | the variable is forecastable when at least half the companies show Ljung-Box p < 0.05 on the target |

The table is shown in NB01 and logged to W&B. Decisions that change behaviour
are carried into this spec's Decisions.

**F15. Exports and runs carry the variable.** Feature files are one per
variable and horizon; W&B run names include the variable, so runs of different
variables never collide.

**F16. Blocked choices fail clearly.** Selecting opex before the GE fix, or
expecting COP before the COP fix, stops NB01 with a message naming the
ingestion spec, rather than running on known-bad data.

**F17. Project rules hold.** Computation lives in injected service classes, the
notebook defines no function or class (R10), mypy strict and `poe check` green.

## Acceptance criteria

| # | Check | How |
|---|---|---|
| B1 | NB01's section headings are § 0–9 in F1's order, the decision table last | notebook inspection |
| B2 | Reports (a), (b) and (c) exist under `reports/` and as HTML panels in three W&B runs, each under 5 MB | run NB01 |
| B3 | Each of the five variables can be selected; opex raises the F16 error until the GE fix | tests + run |
| B4 | The revenue-scaled change reconstructs the level exactly for every horizon, including negative values | test |
| B5 | The register flags a planted jump and a planted negative revenue, nothing on a smooth or seasonal series, ranks the larger jump first, and gives a finite Hampel score on a flat window | test |
| B6 | The data dictionary has one row per numeric column with the F6 fields | test |
| B7 | F9 lists a planted pair with ρ > 0.85 and not a pair below it | test |
| B8 | F10's table has one row per segment value of each of the three segments | test |
| B9 | F13 ranks a planted informative feature above planted noise | test |
| B10 | The decision table has a row for each of the five decision types, per variable | test + run |
| B11 | Feature files and W&B runs of two variables do not overwrite each other | test |
| B12 | `uv run poe check` green; no `def`/`class` in NB01 | shell |

## Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | ydata-profiling, interactions off (was Q7 of the parent spec) | The article's recommended audit tool; 2.9 MB vs 40 MB with interactions |
| D2 | Opex uses the revenue-scaled change, no company excluded (grilling Q26) | Handles LMT's correct but near-zero, signed opex without losing the company |
| D3 | Mutual-information floor for F14's feature-group rule = 0.005 (confirmed 2026-10-01) | Mutual information of independent series is ~0 up to estimator noise. At 0.01 the flags group (0.009 for revenue) would be a drop candidate although covid visibly shifts the target in F10: the flag acts on three quarters, diluted over 81 |
| D4 | Kruskal-Wallis level 0.05 for F14's pooled-or-segmented rule (confirmed 2026-10-01) | The project's significance level (R3); EBITDA's p = 0.078 stays pooled |
| D5 | Forecastable when ≥ 50% of companies have Ljung-Box p < 0.05 (confirmed 2026-10-01) | A majority rule is the simplest defensible bar; revenue 90%, EBITDA 88%, free cash flow 95% |
| D6 | Redundancy threshold |ρ| = 0.85 | The article's Step 5 rule |
| D7 | Periods for F10 follow NB00's `covid` flag: before it, the flagged quarters (2020-Q2 to 2020-Q4, verified), after it | One definition of covid across flags, features and segments |
| D8 | No SHAP and no model in NB01 (grilling Q5, Q7) | Model evaluation belongs with the NB02 harness |
| D9 | Outlier rule: robust z > 10 on size-relative changes, with a Hampel column (decided 2026-09-30) | Measured on 71,685 values: IQR 1.5× on absolute changes flags 7,013 (9.8%), dominated by companies growing; IQR 3× relative 2,854 (4.0%); robust z > 10 flags 1,043 (1.45%) with UNH opex 2008-Q2 (z = 2,952) first. MCD's χ² cutoff flags 31.6% because the changes are heavy-tailed |
| D10 | Isolated single interior gaps are linearly interpolated **for the diagnostics only** (decided 2026-09-30; amends parent R2) | 12 unexplained cells plus one-quarter revenue gaps (ADBE, BBY, ORCL) cut the analysed run short; a one-quarter midpoint uses its neighbours and never reaches features or targets, where the next quarter would leak |
| D11 | P/E is not registered (decided 2026-09-30) | Derived from stock price and EPS, both registered; near-zero EPS (UNH, APD: 0.02 a share) made P/E 16 of the register's top 30 as repeats of one event |
